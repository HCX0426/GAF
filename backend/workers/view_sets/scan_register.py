import logging
import subprocess

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from gaf_core.audit_constants import (
    AuditAction,
    AuditResourceType,
    filter_sensitive_fields,
    get_client_ip,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission
from protocol.broadcast import broadcast_to_dashboard
from protocol.constants import FrontendEventType
from workers.game_binding import bind_game_profile_by_title
from workers.models import Device, Worker
from workers.serializers import (
    DeviceRegisterSerializer,
    DeviceSerializer,
)
from workers.services import _invalidate_available_methods_cache
from workers.services.device_identity import find_device_by_identity
from workers.view_sets.crud import DeviceViewSet

logger = logging.getLogger(__name__)





class DeviceScanView(APIView):
    """设备扫描视图 (BE-3.01)
    GET /api/devices/scan/?type=android|windows|all
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="Scan online agents for attached devices / emulators.",
    )
    def get(self, request):
        """扫描设备：通过在线 Agent 执行模拟器/窗口发现
        若无在线 Agent，回退到数据库已有设备数据（mock 模式）
        """
        scan_type = request.query_params.get("type", "all")
        agent_id = request.query_params.get("agent_id")

        agent = self._select_agent(agent_id)
        result = self._scan_devices(agent, scan_type)
        return Response(result, status=status.HTTP_200_OK)

    def _select_agent(self, agent_id=None):
        """选择目标 Agent"""
        if agent_id:
            try:
                agent = Worker.objects.get(agent_id=agent_id)
                if agent.status == Worker.Status.OFFLINE:
                    return None
                return agent
            except Worker.DoesNotExist:
                return None
        return Worker.objects.filter(
            Q(status=Worker.Status.ONLINE) | Q(status=Worker.Status.IDLE),
        ).first()

    def _scan_devices(self, agent, scan_type):
        """执行设备扫描，返回扫描结果"""
        result = {"android": [], "windows": []}

        if scan_type in ("android", "all"):
            try:
                from device_bridge.discovery.emulator import scan_all_emulators

                emulators = scan_all_emulators()
                if emulators:
                    for emu in emulators:
                        result["android"].append(
                            {
                                "name": emu.name,
                                "emulator": emu.emulator,
                                "adb_port": emu.adb_port,
                                "adb_serial": getattr(emu, "adb_serial", f"127.0.0.1:{emu.adb_port}"),
                                "status": emu.status,
                                "resolution": emu.resolution,
                                "android_version": emu.android_version,
                            }
                        )
            except ImportError:
                logger.warning("_scan_devices %s failed: emulator module not available", scan_type)
            except Exception as e:
                logger.warning("_scan_devices %s failed: %s", scan_type, e)

            try:
                adb_devices = self._scan_adb_devices()
                existing_serials = {d.get("adb_serial") for d in result["android"] if d.get("adb_serial")}
                for adb_dev in adb_devices:
                    if adb_dev.get("adb_serial") not in existing_serials:
                        result["android"].append(adb_dev)
                        existing_serials.add(adb_dev.get("adb_serial"))
            except Exception as e:
                logger.warning("_scan_devices %s failed: %s", scan_type, e)

            if not result["android"]:
                result["android"] = self._mock_android_scan()

        if scan_type in ("windows", "all"):
            enum_success = False
            try:
                from device_bridge.discovery.windows import enum_windows

                windows = enum_windows()
                enum_success = True
                if windows:
                    for w in windows:
                        result["windows"].append(
                            {
                                "title": w.title,
                                "process_name": w.process_name,
                                "hwnd": w.hwnd,
                                "resolution": w.resolution,
                                "is_game": w.is_game,
                            }
                        )
            except ImportError:
                logger.warning("_scan_devices %s failed: windows module not available", scan_type)
            except Exception as e:
                logger.warning("_scan_devices %s failed: %s", scan_type, e)

            try:
                platform_windows = self._scan_platform_windows()
                existing_hwnds = {d.get("hwnd") for d in result["windows"] if d.get("hwnd")}
                for win in platform_windows:
                    if win.get("hwnd") not in existing_hwnds:
                        result["windows"].append(win)
                        existing_hwnds.add(win.get("hwnd"))
            except Exception as e:
                logger.warning("_scan_devices %s failed: %s", scan_type, e)

            if not enum_success and not result["windows"]:
                result["windows"] = self._mock_windows_scan()

        return result

    def _scan_adb_devices(self):
        """Scan connected devices via ADB command using discovered ADB path"""

        result = []
        adb_path = DeviceViewSet._get_adb_path()
        try:
            proc = subprocess.run(
                [adb_path, "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in proc.stdout.strip().split("\n")[1:]:
                line = line.strip()
                if not line or "daemon" in line.lower():
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serial = parts[0]
                    info = {
                        "adb_serial": serial,
                        "name": serial,
                        "emulator": "adb",
                        "adb_port": 5555,
                        "status": "registerable",
                        "resolution": None,
                        "android_version": "",
                    }
                    for part in parts[2:]:
                        if part.startswith("model:"):
                            info["name"] = part.split(":", 1)[1]
                        elif part.startswith("device:"):
                            info["android_version"] = part.split(":", 1)[1]
                    result.append(info)
        except FileNotFoundError as e:
            logger.warning("ADB not found at %s: %s", adb_path, e)
        except subprocess.TimeoutExpired as e:
            logger.warning("ADB devices timeout: %s", e)
        except Exception as e:
            logger.warning("ADB devices scan error: %s", e)
        return result

    def _scan_platform_windows(self):
        """Scan windows via platform abstraction layer.

        Returns list of dicts matching frontend ScanWindowItem contract:
        title, process_name, hwnd, resolution: {width, height}, is_game.
        """
        result = []
        try:
            from device_bridge.platforms import get_device_discoverer

            discoverer = get_device_discoverer()
            devices = discoverer.discover_windows()
            for d in devices:
                res = d.resolution or {}
                if isinstance(res, dict):
                    width, height = res.get("width", 0), res.get("height", 0)
                else:
                    width, height = getattr(res, "width", 0), getattr(res, "height", 0)
                result.append(
                    {
                        "title": d.name or "",
                        "process_name": getattr(d, "process_name", "") or "",
                        "hwnd": str(d.identifier or ""),
                        "resolution": {"width": width, "height": height},
                        "is_game": bool(getattr(d, "is_game", False)),
                    }
                )
        except Exception as e:
            logger.warning("Platform windows scan failed: %s", e)
        return result

    def _mock_android_scan(self):
        """查询数据库中 Android 类型设备（adb/emulator），返回模拟器扫描格式的数据。"""
        devices = Device.objects.filter(device_type=Device.DeviceType.EMULATOR).select_related("agent")
        if devices.exists():
            return [
                {
                    "name": d.name,
                    "emulator_brand": d.emulator_brand or "adb",
                    "adb_port": (
                        (d.extra_info.get("adb_port") or d.extra_info.get("port") or 5555) if d.extra_info else 5555
                    ),
                    "status": "registerable" if d.status == Device.Status.OFFLINE else "connected",
                    "resolution": (
                        {"width": d.resolution_width, "height": d.resolution_height}
                        if d.resolution_width and d.resolution_height
                        else None
                    ),
                    "android_version": d.extra_info.get("android_version", "") if d.extra_info else "",
                }
                for d in devices
            ]
        agents = Worker.objects.all()
        if not agents.exists():
            return [
                {
                    "name": "默认 Android 设备",
                    "emulator": "avd",
                    "adb_port": 5555,
                    "status": "registerable",
                    "resolution": None,
                    "android_version": "",
                }
            ]
        result = []
        for idx, a in enumerate(agents):
            result.append(
                {
                    "name": f"{a.hostname}-Android-{idx + 1}",
                    "emulator": "adb",
                    "adb_port": 5555,
                    "status": "registerable",
                    "resolution": {"width": 1280, "height": 720},
                    "android_version": "",
                }
            )
        return result

    def _mock_windows_scan(self):
        """Fallback Windows scan returning data shaped to match frontend ScanWindowItem.

        Field contract (frontend/src/types/models.ts: ScanWindowItem):
          title, process_name, hwnd, resolution: {width, height}, is_game.
        """
        devices = Device.objects.filter(device_type=Device.DeviceType.WINDOWS).select_related("agent")
        result = []
        for d in devices:
            extra = d.extra_info or {}
            result.append(
                {
                    "title": d.name or "",
                    "process_name": extra.get("process_name", "") or "",
                    "hwnd": str(extra.get("hwnd", "") or d.window_handle or ""),
                    "resolution": {
                        "width": d.resolution_width or 0,
                        "height": d.resolution_height or 0,
                    },
                    "is_game": bool(extra.get("is_game", False)),
                }
            )
        if result:
            return result
        # No devices in DB: return one synthetic placeholder so UI can render.
        return [
            {
                "title": "默认 Windows 设备",
                "process_name": "",
                "hwnd": "0",
                "resolution": {"width": 1920, "height": 1080},
                "is_game": False,
            }
        ]


class DeviceRegisterView(APIView):
    """设备注册视图 (BE-3.02)
    POST /api/devices/register/
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    def _broadcast_device_registered(self, device: Device, action: str) -> None:
        """Broadcast device.registered so the device list refreshes when a new
        device is registered (or a stale offline record is re-registered)
        via the scan-and-register flow. `action` is "created" or "updated"."""
        try:
            broadcast_to_dashboard(
                FrontendEventType.DEVICE_REGISTERED,
                {
                    "device_id": device.id,
                    "action": action,
                    "device_type": device.device_type,
                    "name": device.name,
                    "timestamp": timezone.now().isoformat(),
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to broadcast device.registered for device %d: %s",
                device.id,
                e,
            )

    @extend_schema(
        request=DeviceRegisterSerializer,
        responses={201: DeviceSerializer, 400: OpenApiTypes.OBJECT},
        description="Register a new device (Android emulator or Windows window).",
    )
    def post(self, request: Request):
        """注册新设备"""
        serializer = DeviceRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        agent_type = data["agent_type"]

        resolution = data.get("resolution") or {}
        res_width = data.get("resolution_width") or resolution.get("width")
        res_height = data.get("resolution_height") or resolution.get("height")

        device_type = Device.DeviceType.EMULATOR if agent_type == "android" else Device.DeviceType.WINDOWS

        initial_status = Device.Status.OFFLINE
        adb_serial = data.get("adb_serial", "")
        if agent_type == "windows":
            # If a window handle is provided, probe it so re-registered windows
            # come back online immediately instead of staying offline until the
            # next heartbeat cycle.
            hwnd_str = data.get("hwnd", "")
            if hwnd_str:
                try:
                    from device_bridge.platforms.windows.window_info import is_window_handle_valid

                    hwnd = int(hwnd_str, 16) if hwnd_str.startswith("0x") else int(hwnd_str)
                    if is_window_handle_valid(hwnd):
                        initial_status = Device.Status.ONLINE
                except Exception as exc:
                    logger.warning(
                        "window_handle validity check failed for hwnd=%s: %s",
                        hwnd_str,
                        exc,
                    )
        elif adb_serial and agent_type == "android":
            try:
                import subprocess

                from device_bridge.discovery.emulator import _find_adb_executable

                adb_exe = _find_adb_executable()
                if adb_exe:
                    proc = subprocess.run(
                        [adb_exe, "devices"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    adb_port = int(adb_serial.split(":")[-1]) if ":" in adb_serial else 0
                    for line in proc.stdout.strip().split("\n")[1:]:
                        line = line.strip()
                        if not line or line.startswith("*"):
                            continue
                        parts = line.split()
                        if len(parts) >= 2 and parts[1] == "device":
                            serial = parts[0]
                            if serial == adb_serial:
                                initial_status = Device.Status.ONLINE
                                break
                            if adb_port and ":" in serial:
                                try:
                                    if int(serial.split(":")[1]) == adb_port:
                                        initial_status = Device.Status.ONLINE
                                        break
                                except ValueError:
                                    logger.debug("adb serial port not parseable: %r", serial)
                            if adb_port and serial.startswith("emulator-"):
                                try:
                                    emulator_port = int(serial.split("-")[1])
                                    if emulator_port == adb_port - 1:
                                        initial_status = Device.Status.ONLINE
                                        break
                                except ValueError:
                                    logger.debug("emulator serial not parseable: %r", serial)
            except Exception as e:
                logger.warning("ADB status check failed during device registration: %s", e)

        # Deduplication (OQ-9, 2026-08-30): single identity resolver shared with
        # the agent device.sync path — no more independent 5-step dedup here.
        # Priority: hwnd (windows) > adb_serial > emulator_brand+empty serial >
        # window_title > name+type (see workers/services/device_identity.py).
        window_title = data.get("window_title", "")
        device = find_device_by_identity(
            device_type,
            hwnd=data.get("hwnd", ""),
            adb_serial=adb_serial,
            emulator_brand=data.get("emulator", ""),
            window_title=window_title,
            name=data["name"],
        )

        # R37-P1: Auto-bind device to GameProfile by window_title (HTTP path).
        # Returns None if window_title is empty OR no GameProfile matches.
        # Bind only when device has no game_profile yet — never override user choice.
        # TD-333: 传 device_type 作为 hint, 避免 windows 设备误绑 emulator GameProfile
        auto_game_profile = bind_game_profile_by_title(
            window_title,
            device_type_hint=device_type,
        )
        # N197: 自动绑定后校验 allowed_device_types — 若设备类型不在允许列表内, 跳过自动绑定
        if (
            auto_game_profile
            and auto_game_profile.allowed_device_types
            and device_type not in auto_game_profile.allowed_device_types
        ):
            logger.info(
                "跳过自动绑定: device_type=%s 不在 GameProfile %s 的 allowed_device_types=%s 中",
                device_type, auto_game_profile.id, auto_game_profile.allowed_device_types,
            )
            auto_game_profile = None

        # Track whether this registration created a new device or updated an
        # existing one, so the WS broadcast can carry the right action verb.
        register_action = "updated" if device else "created"

        if device:
            # Update existing device instead of creating duplicate
            update_fields = ["status", "updated_at"]
            device.name = data["name"]
            update_fields.append("name")
            if device.status != initial_status:
                device.status = initial_status
            else:
                update_fields.remove("updated_at")
            if not device.adb_serial and adb_serial:
                device.adb_serial = adb_serial
                update_fields.append("adb_serial")
            if not device.emulator_brand and data.get("emulator"):
                device.emulator_brand = data["emulator"]
                update_fields.append("emulator_brand")
            # Re-registration often means the window was reopened and got a new
            # handle. Update window_handle so the device can come back online.
            new_hwnd = data.get("hwnd", "")
            if new_hwnd and device.window_handle != new_hwnd:
                device.window_handle = new_hwnd
                update_fields.append("window_handle")
            # Keep the registered window title in sync for stable handle refresh.
            new_title = data.get("window_title", "")
            if new_title:
                extra = dict(device.extra_info or {})
                if extra.get("window_title") != new_title:
                    extra["window_title"] = new_title
                    device.extra_info = extra
                    update_fields.append("extra_info")
            if res_width:
                device.resolution_width = res_width
                update_fields.append("resolution_width")
            if res_height:
                device.resolution_height = res_height
                update_fields.append("resolution_height")
            # R37-P1: auto-bind game_profile if matched and not yet set.
            # Preserves user choice — never overwrites existing game_profile_id.
            if auto_game_profile and not device.game_profile_id:
                device.game_profile = auto_game_profile
                update_fields.append("game_profile")
            device.save(update_fields=update_fields)
            logger.info(
                "Updated existing device %d (%s) instead of creating duplicate",
                device.id,
                device.name,
            )
        else:
            create_kwargs = {
                "name": data["name"],
                "device_type": device_type,
                "status": initial_status,
                "adb_serial": adb_serial,
                "window_handle": data.get("hwnd", ""),
                "emulator_brand": data.get("emulator", ""),
                "resolution_width": res_width,
                "resolution_height": res_height,
                "extra_info": {
                    "window_title": data.get("window_title", ""),
                    "registered_via": "manual",
                },
            }
            # R37-P1: auto-bind game_profile on creation if matched.
            if auto_game_profile:
                create_kwargs["game_profile"] = auto_game_profile
            device = Device.objects.create(**create_kwargs)

        try:
            local_agent = Worker.objects.filter(is_local=True).first()
            if local_agent:
                device.agent = local_agent
                device.save(update_fields=["agent"])
        except Exception as e:
            logger.warning("Failed to associate device with local agent: %s", e)

        # Auto-select optimal screenshot method via benchmark (R9-D)
        if device_type == Device.DeviceType.WINDOWS and device.window_handle:
            try:
                from device_bridge.platforms.windows.screenshot import WindowsScreenshotHandler

                handler = WindowsScreenshotHandler()
                available = handler.available_methods()
                hwnd = device.window_handle

                if len(available) > 1:
                    best_method = None
                    best_fps = 0

                    for method in available[:3]:  # Benchmark top 3 methods
                        try:
                            result = handler.benchmark(hwnd, method, rounds=3)
                            fps = result.get("fps", 0)
                            rate = result.get("success_rate", 0)

                            logger.info(
                                "Benchmark %s for device %s: %.1f fps, rate=%.0f%%",
                                method,
                                device.name,
                                fps,
                                rate * 100,
                            )

                            if fps > best_fps and rate >= 0.8:
                                best_fps = fps
                                best_method = result["method"]
                        except Exception as bench_exc:
                            logger.warning("Benchmark failed for %s: %s", method, bench_exc)

                    if best_method:
                        # Fix N1139: write to model field, not extra_info dict.
                        # extra_info only stores benchmark metadata (fps, timestamp).
                        device.screenshot_method = best_method
                        device.extra_info["benchmark_fps"] = best_fps
                        device.extra_info["benchmark_at"] = timezone.now().isoformat()
                        device.save(update_fields=["screenshot_method", "extra_info"])
                        logger.info(
                            "Auto-selected screenshot method '%s' (%.1f fps) for device %s",
                            best_method,
                            best_fps,
                            device.name,
                        )
                elif available:
                    # Single method available — use it directly without benchmark.
                    device.screenshot_method = available[0]
                    device.save(update_fields=["screenshot_method"])
                    logger.info(
                        "Single screenshot method available, selected '%s' for device %s",
                        available[0],
                        device.name,
                    )
            except Exception as auto_exc:
                logger.warning("Auto benchmark failed for device %s: %s", device.name, auto_exc)

        # Auto-select input method based on device type (N1139).
        # Picks the highest-priority method supported by the platform handler.
        # For Windows devices: use host platform handler (WindowsInputHandler).
        # For emulator devices: ADB-based input (shell input tap/swipe).
        # Users can override via PATCH /devices/{id}/ later.
        try:
            if device_type == Device.DeviceType.WINDOWS:
                from device_bridge.platforms.registry import get_input_handler

                input_handler = get_input_handler()
                supported = input_handler.available_methods()
                if supported:
                    device.input_method = supported[0]
                    device.save(update_fields=["input_method"])
                    logger.info(
                        "Auto-selected input method '%s' for Windows device %s",
                        device.input_method,
                        device.name,
                    )
            elif device_type == Device.DeviceType.EMULATOR:
                # Emulators use ADB shell input. Default to 'adb' which the
                # agent-side EmulatorDevice will route to `adb shell input tap`.
                device.input_method = "adb"
                device.save(update_fields=["input_method"])
                logger.info(
                    "Defaulted input method to 'adb' for emulator device %s",
                    device.name,
                )
        except Exception as input_exc:
            logger.warning("Auto input method selection failed for %s: %s", device.name, input_exc)

        # Invalidate available_methods cache — re-registration may change the
        # emulator type or platform modules, so the cached method list could
        # be stale. The next screenshot test request will redetect and recache.
        _invalidate_available_methods_cache(device)
        self._broadcast_device_registered(device, register_action)

        # Audit log: device registration is a sensitive write (creates or
        # updates a Device record). register_action disambiguates the two
        # paths so auditors can tell new registrations apart from re-registrations.
        # Sensitive fields (adb_serial is kept for traceability; window_handle
        # too) are NOT redacted here because they are needed for forensic
        # correlation. Token-like fields are redacted defensively.
        try:
            from accounts.audit import log_audit

            log_audit(
                user=getattr(request, "user", None),
                action=(
                    AuditAction.CREATE if register_action == "created"
                    else AuditAction.UPDATE
                ),
                resource_type=AuditResourceType.DEVICE,
                resource_id=str(device.pk),
                details=filter_sensitive_fields({
                    "register_action": register_action,
                    "name": device.name,
                    "device_type": device.device_type,
                    "status": device.status,
                    "adb_serial": device.adb_serial,
                    "window_handle": device.window_handle,
                    "emulator_brand": device.emulator_brand,
                }, extra_sensitive={"agent_token", "secret", "fcm_token", "token"}),
                ip_address=get_client_ip(request),
            )
        except Exception as audit_exc:
            logger.warning("Audit log failed for device register: %s", audit_exc)

        return Response(DeviceSerializer(device).data, status=status.HTTP_201_CREATED)
