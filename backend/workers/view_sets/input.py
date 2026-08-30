import logging
import subprocess

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission
from device_bridge.platforms.base import InputResult
from workers.models import Device
from workers.services import _get_emulator_native_resolution, _scale_to_native
from workers.view_sets.crud import DeviceViewSet

logger = logging.getLogger(__name__)





class DeviceClickView(APIView):
    """Device mouse click input endpoint (R10-A)
    POST /api/v2/devices/{id}/click/

    Sends mouse click to target device using WindowsInputHandler.
    Supports foreground (SendInput) and background (PostMessage) modes
    with DPI-aware coordinate conversion.

    Request body (JSON):
    {
        "x": int,              // Client X coordinate (required)
        "y": int,              // Client Y coordinate (required)
        "button": str,         // "left" | "right" | "middle" (default: "left")
        "method": str          // "SendInput" | "PostMessage" | "SendMessage" (optional)
    }

    Response:
    {
        "success": bool,
        "method": str,         // Method used
        "error": str | null    // Error message if failed
    }
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    # Cache and methods moved to ``agents.services.device_service`` (Phase 1).
    # Uses the shared module-level functions for ADB emulator resolution and
    # coordinate scaling — see ``_get_emulator_native_resolution`` and
    # ``_scale_to_native`` imported from ``agents.services``.

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Send a mouse click event to a device.",
    )
    def post(self, request: Request, id: int):
        """Send mouse click to device

        Args:
            request: HTTP request with JSON body
            id: Device primary key

        Returns:
            Response with success status and method used
        """
        try:
            device = Device.objects.select_related("agent").get(pk=id)
        except Device.DoesNotExist:
            return Response(
                {"success": False, "error": f"Device {id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if device.status not in [device.Status.ONLINE, device.Status.BUSY]:
            return Response(
                {"success": False, "error": f"Device {device.name} is not online (status={device.status})"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        x = request.data.get("x")
        y = request.data.get("y")
        button = request.data.get("button", "left")
        method = request.data.get("method", "")

        if x is None or y is None:
            return Response(
                {"success": False, "error": "Missing required fields: x, y"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Emulator devices: use ADB input tap (scale coords to Android native resolution)
        if device.device_type == Device.DeviceType.EMULATOR:
            try:
                adb_exe = DeviceViewSet._get_adb_path()
                serial = device.adb_serial or ""
                if not serial:
                    return Response(
                        {"success": False, "error": "Emulator device has no adb_serial"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Use the resolution of the screenshot frame the user actually
                # clicked on. The frontend passes these values so scaling does
                # not depend on the (possibly stale) device model resolution.
                screenshot_w = request.data.get("screenshot_width") or device.resolution_width or 0
                screenshot_h = request.data.get("screenshot_height") or device.resolution_height or 0
                native_w, native_h = _get_emulator_native_resolution(device, adb_exe)
                tap_x, tap_y = _scale_to_native(
                    x,
                    y,
                    screenshot_w,
                    screenshot_h,
                    native_w,
                    native_h,
                )
                # [INSTRUMENTATION] click coordinate mapping debug
                logger.info(
                    "CLICK_DEBUG device=%s id=%d raw=(%s,%s) frame_res=(%d,%d) " "native=(%d,%d) tap=(%d,%d)",
                    device.name,
                    device.id,
                    x,
                    y,
                    screenshot_w,
                    screenshot_h,
                    native_w,
                    native_h,
                    tap_x,
                    tap_y,
                )
                proc = subprocess.run(
                    [adb_exe, "-s", serial, "shell", "input", "tap", str(tap_x), str(tap_y)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                success = proc.returncode == 0
                error = proc.stderr.strip() if not success else None
                logger.info(
                    "ADB tap sent to emulator %s (%s): screenshot=(%d,%d) native=(%d,%d) success=%s",
                    device.name,
                    id,
                    x,
                    y,
                    tap_x,
                    tap_y,
                    success,
                )
                return Response(
                    {
                        "success": success,
                        "method": "adb_tap",
                        "error": error,
                        # [INSTRUMENTATION] expose scaled tap coordinates for debugging
                        "_debug": {
                            "raw_x": x,
                            "raw_y": y,
                            "screenshot_w": screenshot_w,
                            "screenshot_h": screenshot_h,
                            "native_w": native_w,
                            "native_h": native_h,
                            "tap_x": tap_x,
                            "tap_y": tap_y,
                        },
                    }
                )
            except Exception as e:
                logger.error("ADB tap failed for device %d: %s", id, e, exc_info=True)
                return Response(
                    {"success": False, "error": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        if device.device_type != Device.DeviceType.WINDOWS:
            return Response(
                {
                    "success": False,
                    "error": f"Click only supported for Windows/Emulator devices, got {device.device_type}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from device_bridge.platforms import get_input_handler

            handler = get_input_handler(method=method or "")
            target = device.window_handle or ""

            if not target:
                return Response(
                    {"success": False, "error": "Device has no window_handle"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            result = handler.click(
                target=target,
                x=int(x),
                y=int(y),
                method=method or "",
                button=button,  # type: ignore[call-arg]
            )

            logger.info(
                "Click sent to device %s (%s): x=%d y=%d btn=%s method=%s success=%s",
                device.name,
                id,
                x,
                y,
                button,
                result.method,
                result.success,
            )

            return Response(
                {
                    "success": result.success,
                    "method": result.method,
                    "error": result.error,
                }
            )

        except Exception as e:
            logger.error("Click failed for device %d: %s", id, e, exc_info=True)
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DeviceInputView(APIView):
    """Device keyboard/touch input endpoint (R10-B)
    POST /api/v2/devices/{id}/input/

    Unified input endpoint supporting multiple operations:
      - key_press: Send single key or key combination
      - text_input: Type Unicode text (emoji support in SendInput mode)
      - swipe/drag: Mouse drag gesture with duration control
      - scroll: Mouse wheel scroll at position

    Request body (JSON) - choose one operation:
    {
        "action": "key_press",     // Operation type (required)
        "key": "enter"             // Key name for key_press
    }
    {
        "action": "text_input",
        "text": "Hello 世界"       // Text to type (supports Unicode)
    }
    {
        "action": "swipe",
        "x1": 100, "y1": 200,     // Start coordinates
        "x2": 500, "y2": 200,     // End coordinates
        "duration_ms": 300         // Swipe duration (ms), default 300
    }
    {
        "action": "scroll",
        "x": 500, "y": 300,       // Scroll position
        "delta": -120              // Scroll amount (120=up, -120=down)
    }

    Common optional fields:
    {
        "method": "SendInput"      // Override input method
    }

    Response:
    {
        "success": bool,
        "method": str,
        "action": str,
        "error": str | null
    }
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Send an input command (swipe / text / key) to a device.",
    )
    def post(self, request: Request, id: int):
        """Send input command to device

        Args:
            request: HTTP request with JSON body containing action + params
            id: Device primary key

        Returns:
            Response with execution result
        """
        try:
            device = Device.objects.select_related("agent").get(pk=id)
        except Device.DoesNotExist:
            return Response(
                {"success": False, "error": f"Device {id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if device.status not in [device.Status.ONLINE, device.Status.BUSY]:
            return Response(
                {"success": False, "error": f"Device {device.name} is not online"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action = request.data.get("action")
        method = request.data.get("method", "")

        if not action:
            return Response(
                {"success": False, "error": "Missing required field: action"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_actions = ["key_press", "text_input", "swipe", "scroll"]
        if action not in valid_actions:
            return Response(
                {"success": False, "error": f"Invalid action: {action}. Must be one of {valid_actions}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Emulator devices: use ADB input commands
        if device.device_type == Device.DeviceType.EMULATOR:
            try:
                # Use the resolution of the screenshot frame that produced the
                # coordinates, falling back to the stored device resolution.
                screenshot_w = request.data.get("screenshot_width") or device.resolution_width or 0
                screenshot_h = request.data.get("screenshot_height") or device.resolution_height or 0
                adb_exe = DeviceViewSet._get_adb_path()
                native_w, native_h = _get_emulator_native_resolution(device, adb_exe)
                result = self._execute_adb_action(
                    device,
                    action,
                    request.data,
                    adb_exe=adb_exe,
                    screenshot_w=screenshot_w,
                    screenshot_h=screenshot_h,
                    native_w=native_w,
                    native_h=native_h,
                )
                logger.info(
                    "ADB input sent to emulator %s (%s): action=%s success=%s",
                    device.name,
                    id,
                    action,
                    result.success,
                )
                return Response(
                    {
                        "success": result.success,
                        "method": result.method,
                        "action": action,
                        "error": result.error,
                    }
                )
            except Exception as e:
                logger.error("ADB input failed for device %d: %s", id, e, exc_info=True)
                return Response(
                    {"success": False, "error": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        if device.device_type != Device.DeviceType.WINDOWS:
            return Response(
                {"success": False, "error": "Input only supported for Windows/Emulator devices"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from device_bridge.platforms import get_input_handler

            handler = get_input_handler(method=method or "")
            target = device.window_handle or ""

            if not target:
                return Response(
                    {"success": False, "error": "Device has no window_handle"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            result = self._execute_action(handler, target, action, request.data)

            logger.info(
                "Input sent to device %s (%s): action=%s method=%s success=%s",
                device.name,
                id,
                action,
                result.method,
                result.success,
            )

            return Response(
                {
                    "success": result.success,
                    "method": result.method,
                    "action": action,
                    "error": result.error,
                }
            )

        except Exception as e:
            logger.error("Input failed for device %d: %s", id, e, exc_info=True)
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _execute_adb_action(
        self,
        device,
        action,
        data,
        adb_exe,
        screenshot_w=0,
        screenshot_h=0,
        native_w=0,
        native_h=0,
    ):
        """Execute input action via ADB for emulator devices.

        Args:
            device: Device instance (emulator)
            action: Action type (key_press/text_input/swipe/scroll)
            data: Request data dict
            adb_exe: Path to the adb executable
            screenshot_w: Width of the screenshot frame the coords came from
            screenshot_h: Height of the screenshot frame the coords came from
            native_w: Android native screen width (from wm size)
            native_h: Android native screen height (from wm size)

        Returns:
            InputResult with success status
        """
        serial = device.adb_serial or ""
        if not serial:
            return InputResult(success=False, method="", error="Emulator device has no adb_serial")

        if action == "key_press":
            key = data.get("key")
            if not key:
                return InputResult(success=False, method="", error="Missing required field: key")
            # Map common key names to Android keycodes
            key_map = {
                "enter": "66",
                "back": "4",
                "home": "3",
                "menu": "82",
                "escape": "111",
                "delete": "67",
                "del": "67",
                "tab": "61",
                "up": "19",
                "down": "20",
                "left": "21",
                "right": "22",
                "space": "62",
                "shift": "59",
                "ctrl": "113",
                "volume_up": "24",
                "volume_down": "25",
                "power": "26",
                "wake_up": "224",
            }
            keycode = key_map.get(str(key).lower(), str(key))
            proc = subprocess.run(
                [adb_exe, "-s", serial, "shell", "input", "keyevent", keycode],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return InputResult(
                success=proc.returncode == 0,
                method="adb_keyevent",
                error=proc.stderr.strip() if proc.returncode != 0 else None,
            )

        elif action == "text_input":
            text = data.get("text")
            if text is None:
                return InputResult(success=False, method="", error="Missing required field: text")
            # ADB input text doesn't support spaces well, use %s for spaces
            safe_text = str(text).replace(" ", "%s")
            proc = subprocess.run(
                [adb_exe, "-s", serial, "shell", "input", "text", safe_text],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return InputResult(
                success=proc.returncode == 0,
                method="adb_text",
                error=proc.stderr.strip() if proc.returncode != 0 else None,
            )

        elif action == "swipe":
            x1 = data.get("x1")
            y1 = data.get("y1")
            x2 = data.get("x2")
            y2 = data.get("y2")
            duration_ms = data.get("duration_ms", 300)
            if any(v is None for v in [x1, y1, x2, y2]):
                return InputResult(
                    success=False,
                    method="",
                    error="Missing required fields for swipe: x1, y1, x2, y2",
                )
            tap_x1, tap_y1 = _scale_to_native(x1, y1, screenshot_w, screenshot_h, native_w, native_h)
            tap_x2, tap_y2 = _scale_to_native(x2, y2, screenshot_w, screenshot_h, native_w, native_h)
            # ADB swipe duration is in ms
            proc = subprocess.run(
                [
                    adb_exe,
                    "-s",
                    serial,
                    "shell",
                    "input",
                    "swipe",
                    str(int(tap_x1)),
                    str(int(tap_y1)),
                    str(int(tap_x2)),
                    str(int(tap_y2)),
                    str(int(duration_ms)),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return InputResult(
                success=proc.returncode == 0,
                method="adb_swipe",
                error=proc.stderr.strip() if proc.returncode != 0 else None,
            )

        elif action == "scroll":
            # ADB doesn't have direct scroll, use swipe to simulate
            x = data.get("x", 540)
            y = data.get("y", 960)
            dy = data.get("delta", data.get("dy", 300))
            duration_ms = data.get("duration_ms", 300)
            tap_x, tap_y = _scale_to_native(x, y, screenshot_w, screenshot_h, native_w, native_h)
            # Scale the vertical delta so the scroll distance matches the
            # native screen, not the screenshot coordinate space.
            dy_native = int(int(dy) * native_h / screenshot_h) if screenshot_h > 0 and native_h > 0 else int(dy)
            # Swipe vertically to scroll
            proc = subprocess.run(
                [
                    adb_exe,
                    "-s",
                    serial,
                    "shell",
                    "input",
                    "swipe",
                    str(int(tap_x)),
                    str(int(tap_y)),
                    str(int(tap_x)),
                    str(int(tap_y) - dy_native),
                    str(int(duration_ms)),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return InputResult(
                success=proc.returncode == 0,
                method="adb_scroll",
                error=proc.stderr.strip() if proc.returncode != 0 else None,
            )

        return InputResult(success=False, method="", error=f"Unknown action: {action}")

    def _execute_action(self, handler, target, action, data):
        """Execute the requested input action

        Args:
            handler: WindowsInputHandler instance
            target: Target window handle string
            action: Action type (key_press/text_input/swipe)
            data: Request data dict

        Returns:
            InputResult from handler method call
        """
        method = data.get("method", "")

        if action == "key_press":
            key = data.get("key")
            if not key:
                return InputResult(success=False, method="", error="Missing required field: key")
            return handler.key_press(target=target, key=key, method=method)

        elif action == "text_input":
            text = data.get("text")
            if text is None:
                return InputResult(success=False, method="", error="Missing required field: text")
            return handler.text_input(target=target, text=str(text), method=method)

        elif action == "swipe":
            x1 = data.get("x1")
            y1 = data.get("y1")
            x2 = data.get("x2")
            y2 = data.get("y2")
            duration_ms = data.get("duration_ms", 300)

            if any(v is None for v in [x1, y1, x2, y2]):
                return InputResult(
                    success=False,
                    method="",
                    error="Missing required fields for swipe: x1, y1, x2, y2",
                )
            return handler.swipe(
                target=target,
                x1=int(x1),
                y1=int(y1),
                x2=int(x2),
                y2=int(y2),
                duration_ms=int(duration_ms),
                method=method,
            )

        elif action == "scroll":
            x = data.get("x", 0)
            y = data.get("y", 0)
            delta = data.get("delta", -120)

            return handler.scroll(
                target=target,
                x=int(x),
                y=int(y),
                delta=int(delta),
                method=method,
            )

        return InputResult(success=False, method="", error=f"Unknown action: {action}")
