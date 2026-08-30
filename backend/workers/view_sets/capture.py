import logging
import subprocess
import time

from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission
from protocol.broadcast import broadcast_to_dashboard
from protocol.constants import FrontendEventType
from workers.models import Device
from workers.services import _get_or_cache_available_methods, _refresh_window_handle
from workers.view_sets.crud import DeviceViewSet

logger = logging.getLogger(__name__)





class DeviceScreenshotView(APIView):
    """Device screenshot capture for card preview (BE-3.02)
    POST /api/v2/devices/{id}/screenshot/
    Returns base64 screenshot image for device card thumbnail preview
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Capture a screenshot and return base64-encoded image data.",
    )
    def post(self, request: Request, id: int):
        """Capture screenshot and return base64 data"""
        try:
            device = Device.objects.select_related("agent").get(pk=id)
        except Device.DoesNotExist:
            return Response(
                {"success": False, "error": "Device not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if device.status not in [device.Status.ONLINE, device.Status.BUSY]:
            return Response(
                {
                    "success": True,
                    "screenshot_base64": None,
                    "latency_ms": 0,
                    "width": 0,
                    "height": 0,
                    "screenshot_method": "",
                }
            )

        try:
            from device_bridge.platforms import get_screenshot_handler

            handler = get_screenshot_handler(
                method=device.screenshot_method or "",
            )

            target = device.window_handle or device.adb_serial or ""
            screenshot_result = handler.capture(
                target=target,
                method=device.screenshot_method or "",
            )

            if not screenshot_result.success:
                if device.device_type == Device.DeviceType.WINDOWS and device.name:
                    refreshed_hwnd = _refresh_window_handle(device)
                    if refreshed_hwnd:
                        target = str(refreshed_hwnd)
                        screenshot_result = handler.capture(
                            target=target,
                            method=device.screenshot_method or "",
                        )
                if not screenshot_result.success:
                    return Response(
                        {
                            "success": False,
                            "error": screenshot_result.error or "Screenshot failed",
                            "screenshot_base64": None,
                            "latency_ms": screenshot_result.latency_ms or 0,
                            "width": 0,
                            "height": 0,
                            "screenshot_method": "",
                        }
                    )

            import base64

            image_base64 = (
                base64.b64encode(screenshot_result.image_bytes).decode("utf-8")
                if screenshot_result.image_bytes
                else None
            )

            res = screenshot_result.resolution
            if hasattr(res, "get"):
                width = res.get("width", 0)
                height = res.get("height", 0)
            else:
                width = getattr(res, "width", 0)
                height = getattr(res, "height", 0)

            return Response(
                {
                    "success": True,
                    "screenshot_base64": image_base64,
                    "latency_ms": screenshot_result.latency_ms or 0,
                    "width": width,
                    "height": height,
                    "screenshot_method": screenshot_result.method or "",
                }
            )
        except Exception as e:
            logger.error("Screenshot failed for device %d: %s", id, e)
            return Response(
                {
                    "success": False,
                    "error": str(e),
                    "screenshot_base64": None,
                    "latency_ms": 0,
                    "width": 0,
                    "height": 0,
                    "screenshot_method": "",
                }
            )


class DeviceTestScreenshotView(APIView):
    """设备测试截图视图 (BE-3.03)
    GET /api/devices/{id}/test-screenshot/
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    # Module-level screenshot result cache: device_id -> {data, timestamp}
    _result_cache: dict = {}
    _CACHE_TTL = 5.0  # Cache valid for 5 seconds

    def _benchmark_adb_screenshot(
        self, serial: str, adb_exe: str, emulator_type: str, rounds: int = 3, method: str = ""
    ) -> tuple[float, float]:
        """Run benchmark ADB screenshots to measure FPS and latency.

        Args:
            serial: ADB device serial
            adb_exe: Path to adb executable
            emulator_type: Emulator type string
            rounds: Number of rounds to run
            method: If provided, benchmark only this method; otherwise use the chain.

        Returns:
            (avg_fps, avg_latency_ms) — both 0.0 if no successful captures.
            The latency is the average wall-clock time per capture, matching
            what the Windows handler reports as result.latency_ms.
        """

        from device_bridge.platforms.windows._adb_screenshot import (
            capture as adb_capture,
        )
        from device_bridge.platforms.windows._adb_screenshot import (
            invalidate_cache,
        )

        timestamps = []
        for _i in range(rounds):
            # Clear cache before each round to get real timing
            invalidate_cache(serial)
            start = time.perf_counter()
            img_bytes, _method = adb_capture(
                serial,
                adb_exe,
                emulator_type=emulator_type,
                use_cache=False,
                method=method or None,
            )
            end = time.perf_counter()
            elapsed = end - start
            if img_bytes and elapsed > 0:
                timestamps.append(elapsed)

        if not timestamps:
            return 0.0, 0.0

        avg_time = sum(timestamps) / len(timestamps)
        if avg_time <= 0:
            return 0.0, 0.0
        return 1.0 / avg_time, round(avg_time * 1000, 2)

    def _broadcast_metrics_updated(self, device: Device) -> None:
        """Broadcast device.metrics_updated so the device list / cards refresh
        screenshot metrics (latency, fps, method, resolution) in real time
        without a manual page refresh."""
        try:
            stats = device.device_stats or {}
            broadcast_to_dashboard(
                FrontendEventType.DEVICE_METRICS_UPDATED,
                {
                    "device_id": device.id,
                    "resolution": {
                        "width": device.resolution_width or 0,
                        "height": device.resolution_height or 0,
                    },
                    "method": device.screenshot_method or "",
                    "fps": device.screenshot_fps or 0,
                    "latency_ms": stats.get("screenshot_latency_avg_ms", 0),
                    "timestamp": timezone.now().isoformat(),
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to broadcast device.metrics_updated for device %d: %s",
                device.id,
                e,
            )

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Capture a test screenshot for the given device (with method benchmarking).",
    )
    def get(self, request: Request, id: int):
        """获取设备测试截图"""
        # Screenshot method selection: empty/'auto' means use the recommended chain.
        requested_method = request.query_params.get("method", "")
        if requested_method and requested_method.lower() == "auto":
            requested_method = ""

        def _emulator_methods(device) -> list:
            # Use extra_info-cached available_methods to avoid repeated
            # importlib probing on every screenshot test request. The cache
            # is populated on first call and invalidated when the screenshot
            # method changes (see _invalidate_available_methods_cache).
            return _get_or_cache_available_methods(device)

        try:
            device = Device.objects.select_related("agent").get(pk=id)
        except Device.DoesNotExist:
            return Response(
                {"success": False, "error": "设备不存在"},
                status=status.HTTP_404_NOT_FOUND,
            )

        device_id = device.id

        if device.status == Device.Status.OFFLINE and device.device_type == Device.DeviceType.WINDOWS:
            return Response(
                {
                    "success": False,
                    "error": "设备离线，无法截图",
                    "screenshot_base64": None,
                    "latency_ms": 0,
                    "fps": 0,
                    "resolution": {"width": device.resolution_width or 0, "height": device.resolution_height or 0},
                    "screenshot_method": "",
                }
            )

        # Check result cache for instant response (skip cache when a specific
        # method is requested so the user can compare methods side-by-side).
        import time as _time2

        if not requested_method:
            cached = self._result_cache.get(device_id)
            if cached and (_time2.time() - cached["timestamp"] < self._CACHE_TTL):
                # Return the last measured latency from device_stats (not 0)
                # so the test dialog stays consistent between cached and fresh responses.
                _stats = device.device_stats or {}
                # Prefer the actual resolution captured with the cached frame so the
                # frontend canvas matches the real image dimensions.
                cached_resolution = cached.get("resolution") or {
                    "width": device.resolution_width or 0,
                    "height": device.resolution_height or 0,
                }
                return Response(
                    {
                        "screenshot_base64": cached["data"],
                        "latency_ms": _stats.get("screenshot_latency_avg_ms", 0),
                        "fps": device.screenshot_fps or 0,
                        "resolution": cached_resolution,
                        "screenshot_method": device.screenshot_method or "cached",
                        "available_methods": _emulator_methods(device),
                        "success": True,
                        "error": None,
                    }
                )

        try:
            import base64

            from device_bridge.platforms import get_screenshot_handler
            from device_bridge.platforms.windows._adb_screenshot import (
                capture as adb_capture,
            )

            screenshot_method = device.screenshot_method or ""

            if device.device_type == Device.DeviceType.EMULATOR and device.adb_serial:
                from device_bridge.discovery.emulator import _find_adb_executable

                adb_exe = _find_adb_executable()
                if adb_exe:
                    serials_to_try = [device.adb_serial]
                    if ":" in device.adb_serial:
                        try:
                            port = int(device.adb_serial.split(":")[1])
                            serials_to_try.append(f"emulator-{port - 1}")
                        except ValueError:
                            logger.debug("adb serial not parseable: %r", device.adb_serial)
                    for serial in serials_to_try:
                        img_bytes, adb_method = adb_capture(
                            serial,
                            adb_exe,
                            emulator_type=device.emulator_brand or "",
                            method=requested_method or None,
                        )
                        if img_bytes:
                            # Benchmark: run multiple captures to measure FPS
                            import base64
                            import struct
                            import time as _time

                            import cv2
                            import numpy as np

                            fps, latency_ms = self._benchmark_adb_screenshot(
                                serial,
                                adb_exe,
                                device.emulator_brand or "",
                                rounds=3,
                                method=requested_method,
                            )

                            # Detect format: raw screencap starts with valid dimensions
                            # PNG magic bytes: 89 50 4E 47
                            # JPEG magic bytes: FF D8 FF
                            is_png = len(img_bytes) > 8 and img_bytes[:4] == b"\x89PNG"
                            is_jpeg = len(img_bytes) > 8 and img_bytes[:3] == b"\xff\xd8\xff"
                            is_raw = not is_png and not is_jpeg and len(img_bytes) >= 24

                            if is_raw:
                                # Parse raw BGRA header: w(4LE) + h(4LE) + fmt(4) [+ stride(4)]
                                # LDPlayer Android returns 12-byte header (stride=0)
                                # Standard Android may return 16 or 24-byte header
                                w = struct.unpack("<i", img_bytes[0:4])[0]
                                h = struct.unpack("<i", img_bytes[4:8])[0]
                                # fmt(4) is present in the header but not used for decoding.
                                _ = struct.unpack("<i", img_bytes[8:12])[0]

                                # Determine header size and stride
                                if len(img_bytes) >= 16:
                                    stride = struct.unpack("<i", img_bytes[12:16])[0]
                                    # Some emulators (e.g. LDPlayer14) return stride=1 instead of real stride.
                                    # Treat any stride < w*4 as invalid and fall back to w*4.
                                    if stride < w * 4:
                                        stride = w * 4
                                    hdr_size = 16
                                else:
                                    stride = w * 4
                                    hdr_size = 12

                                pixel_data = img_bytes[hdr_size:]
                                expected = h * stride
                                if len(pixel_data) < expected:
                                    # Fallback: try offset 12
                                    stride = w * 4
                                    hdr_size = 12
                                    pixel_data = img_bytes[hdr_size:]
                                    expected = h * stride

                                # Reshape as RGBA array and convert to BGR for JPEG
                                img_array = np.frombuffer(pixel_data[:expected], dtype=np.uint8)
                                img_rgba = img_array.reshape((h, w, 4))
                                img = cv2.cvtColor(img_rgba, cv2.COLOR_RGBA2BGR)
                            elif is_jpeg:
                                # JPEG format (e.g. LDOpenGL capture) — decode with cv2
                                img_array = np.frombuffer(img_bytes, np.uint8)
                                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                            else:
                                # PNG format — decode with cv2
                                img_array = np.frombuffer(img_bytes, np.uint8)
                                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

                            if img is not None:
                                _, jpeg_buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                                screenshot_base64: str | None = base64.b64encode(jpeg_buf.tobytes()).decode("utf-8")
                                actual_w, actual_h = img.shape[1], img.shape[0]
                            else:
                                # Fallback to raw base64 if decode fails
                                screenshot_base64 = base64.b64encode(img_bytes).decode("utf-8")
                                actual_w, actual_h = 0, 0
                            # [INSTRUMENTATION] screenshot resolution debug
                            logger.info(
                                "SCREENSHOT_DEBUG device=%s id=%d actual=(%d,%d) db=(%d,%d) method=%s",
                                device.name,
                                device_id,
                                actual_w,
                                actual_h,
                                device.resolution_width or 0,
                                device.resolution_height or 0,
                                adb_method or requested_method or "auto",
                            )
                            # Cache the final result for instant subsequent requests.
                            # Store the actual resolution alongside the frame so cached
                            # responses report the real image dimensions to the frontend.
                            self._result_cache[device_id] = {
                                "data": screenshot_base64,
                                "timestamp": _time.time(),
                                "resolution": {"width": actual_w, "height": actual_h},
                            }

                            # Determine actual method name based on the chain result.
                            # Fallback to format detection only when the chain did not report a method.
                            actual_method = adb_method or (
                                "screencap_png" if is_png else ("ld_opengl" if is_jpeg else "screencap")
                            )

                            # Save screenshot results to device.
                            # Write device_stats.screenshot_latency_avg_ms so the
                            # DeviceCard displays the same latency as the test dialog
                            # (both read from device_stats, not the misleading 1000/fps).
                            stats = dict(device.device_stats or {})
                            stats["screenshot_latency_avg_ms"] = latency_ms
                            stats["screenshot_fps"] = round(fps, 1)
                            stats["screenshot_method"] = actual_method
                            stats["total_screenshots"] = stats.get("total_screenshots", 0) + 1
                            device.device_stats = stats
                            device.screenshot_fps = round(fps, 1)
                            device.screenshot_method = actual_method
                            # Update stored resolution to the actual captured frame size.
                            # This keeps click coordinate scaling aligned with the image the
                            # frontend displays, especially when window size differs from the
                            # Android framebuffer (e.g. LDPlayer resized by the user).
                            device.resolution_width = actual_w or device.resolution_width
                            device.resolution_height = actual_h or device.resolution_height
                            device.save(
                                update_fields=[
                                    "screenshot_fps",
                                    "screenshot_method",
                                    "resolution_width",
                                    "resolution_height",
                                    "device_stats",
                                    "updated_at",
                                ]
                            )
                            self._broadcast_metrics_updated(device)
                            return Response(
                                {
                                    "screenshot_base64": screenshot_base64,
                                    "latency_ms": latency_ms,
                                    "fps": round(fps, 1),
                                    "resolution": {
                                        "width": device.resolution_width or 0,
                                        "height": device.resolution_height or 0,
                                    },
                                    "screenshot_method": actual_method,
                                    "available_methods": _emulator_methods(device),
                                    "success": True,
                                    "error": None,
                                }
                            )

            # Honor the method selected in the test dialog; fall back to the
            # device default only when no specific method was requested.
            test_method = requested_method or screenshot_method
            handler = get_screenshot_handler(method=test_method)
            target = device.window_handle or device.adb_serial or ""
            if not target and device.device_type == Device.DeviceType.WINDOWS:
                target = device.name
            result = handler.capture(target=target, method=test_method)

            if not result.success and device.device_type == Device.DeviceType.WINDOWS and device.name:
                refreshed = _refresh_window_handle(device)
                if refreshed:
                    target = str(refreshed)
                    result = handler.capture(target=target, method=test_method)

            if result.success and result.image_bytes:
                screenshot_base64 = base64.b64encode(result.image_bytes).decode("utf-8")
                # Update device stats with latest screenshot test results.
                # Write device_stats.screenshot_latency_avg_ms so the DeviceCard
                # displays the same latency as the test dialog.
                stats = dict(device.device_stats or {})
                stats["screenshot_latency_avg_ms"] = result.latency_ms
                stats["screenshot_fps"] = result.fps
                stats["screenshot_method"] = result.method
                stats["total_screenshots"] = stats.get("total_screenshots", 0) + 1
                device.device_stats = stats
                device.screenshot_fps = result.fps
                device.screenshot_method = result.method
                # Always update device resolution with actual screenshot dimensions.
                # The previous `device.resolution_width or actual` kept stale DB
                # values (e.g. logical 1280x720) even when PrintWindow captured at
                # physical pixel resolution (e.g. 2560x1600), causing the frontend
                # canvas backing store to mismatch the real image.
                actual_w = result.resolution.get("width") or 0
                actual_h = result.resolution.get("height") or 0
                if actual_w and actual_h:
                    device.resolution_width = actual_w
                    device.resolution_height = actual_h
                device.save(
                    update_fields=[
                        "screenshot_fps",
                        "screenshot_method",
                        "resolution_width",
                        "resolution_height",
                        "device_stats",
                        "updated_at",
                    ]
                )
                self._broadcast_metrics_updated(device)
            else:
                screenshot_base64 = None

            return Response(
                {
                    "screenshot_base64": screenshot_base64,
                    "latency_ms": result.latency_ms,
                    "fps": result.fps,
                    "resolution": result.resolution,
                    "screenshot_method": result.method,
                    "available_methods": _emulator_methods(device),
                    "success": result.success,
                    "error": result.error,
                }
            )
        except ImportError:
            return Response(
                {
                    "success": False,
                    "error": "截图模块未安装，请确保 agent 库依赖完整",
                    "screenshot_base64": None,
                    "latency_ms": 0,
                    "fps": 0,
                    "resolution": {"width": device.resolution_width or 0, "height": device.resolution_height or 0},
                    "screenshot_method": "",
                }
            )
        except Exception as e:
            logger.error("Multi-frame screenshot failed for device %d: %s", id, e, exc_info=True)
            return Response(
                {
                    "success": False,
                    "error": f"截图失败: {str(e)}",
                    "screenshot_base64": None,
                    "latency_ms": 0,
                    "fps": 0,
                    "resolution": {"width": device.resolution_width or 0, "height": device.resolution_height or 0},
                    "screenshot_method": "",
                }
            )


def _capture_device_screenshot(device):
    """Capture screenshot from device, return JPEG bytes.

    TD-257 修复 (2026-07-18): extracted from DeviceTemplateMatchView._capture_screenshot
    to module-level function so both DeviceTemplateMatchView and DeviceColorDetectView
    can share the same implementation without inheritance coupling.
    """
    try:
        if device.device_type == Device.DeviceType.EMULATOR:
            adb_exe = DeviceViewSet._get_adb_path()
            serial = device.adb_serial or ""
            if not serial:
                return None
            proc = subprocess.run(
                [adb_exe, "-s", serial, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=15,
            )
            if proc.returncode == 0 and len(proc.stdout) > 100:
                return proc.stdout
            return None
        else:
            # Windows device
            from device_bridge.platforms import get_screenshot_handler

            handler = get_screenshot_handler()
            target = device.window_handle or ""
            result = handler.capture(target=target)
            if result.success and result.image_bytes:
                return result.image_bytes
            return None
    except Exception as e:
        logger.error("Screenshot capture failed: %s", e)
        return None
