import logging

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
from agents.models import Device

logger = logging.getLogger(__name__)


# Import service-layer helpers (moved to agents/services/device_service.py in Phase 1).


class DeviceCompatibilityCheckView(APIView):
    """设备分辨率兼容检查视图 (BE-3.07)
    POST /api/devices/check-compatibility/
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Check resolution compatibility between a device and a resource pack.",
    )
    def post(self, request: Request):
        """检查设备与资源包的分辨率兼容性"""
        device_id = request.data.get("device_id")
        resource_pack_id = request.data.get("resource_pack_id")

        if not device_id:
            return Response({"error": "缺少 device_id"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            device = Device.objects.get(pk=device_id)
        except Device.DoesNotExist:
            return Response({"error": "设备不存在"}, status=status.HTTP_404_NOT_FOUND)

        device_res = {
            "width": device.resolution_width or 1920,
            "height": device.resolution_height or 1080,
        }

        pack_res = self._get_pack_resolution(resource_pack_id)

        is_compatible, scale, message = self._check_compatibility(device_res, pack_res)

        width_ratio = round(device_res["width"] / pack_res["width"], 1) if pack_res["width"] else 1.0
        height_ratio = round(device_res["height"] / pack_res["height"], 1) if pack_res["height"] else 1.0

        return Response(
            {
                "is_compatible": is_compatible,
                "device_resolution": device_res,
                "pack_resolution": pack_res,
                "width_ratio": width_ratio,
                "height_ratio": height_ratio,
                "scale_suggestion": scale,
                "message": message,
            }
        )

    def _get_pack_resolution(self, pack_id):
        """Get resource pack template resolution.

        Returns:
            dict: {'width': int, 'height': int}. Returns {'width': 0, 'height': 0}
            as a failure flag when pack_id is provided but pack is missing or
            resources app is unavailable, so callers can detect the failure
            (existing _check_compatibility already treats (0,0) as "unknown").
            Returns {'width': 1280, 'height': 720} only when pack_id is empty.
        """
        if not pack_id:
            return {"width": 1280, "height": 720}

        try:
            from resources.models import ResourcePack
        except ImportError as e:
            logger.error(
                "resources app not installed but resource_pack_id=%s provided: %s",
                pack_id,
                e,
            )
            return {"width": 0, "height": 0}

        try:
            pack = ResourcePack.objects.get(pk=pack_id)
        except ResourcePack.DoesNotExist:
            logger.warning("ResourcePack %s not found", pack_id)
            return {"width": 0, "height": 0}
        except Exception as e:
            logger.error(
                "Failed to load ResourcePack %s: %s",
                pack_id,
                e,
                exc_info=True,
            )
            return {"width": 0, "height": 0}

        config = pack.config_data or {}
        settings_data = config.get("settings", {}) if isinstance(config, dict) else {}
        base_res = (
            settings_data.get("base_resolution", [1920, 1080]) if isinstance(settings_data, dict) else [1920, 1080]
        )
        if isinstance(base_res, (list, tuple)) and len(base_res) >= 2:
            return {"width": base_res[0] or 1920, "height": base_res[1] or 1080}
        return {"width": 1920, "height": 1080}

    @staticmethod
    def _check_compatibility(device_res, pack_res):
        """判定分辨率兼容性"""
        if not device_res["width"] or not device_res["height"]:
            return True, 1.0, "设备分辨率未知，默认兼容"
        if not pack_res["width"] or not pack_res["height"]:
            return True, 1.0, "资源包分辨率未知，默认兼容"

        device_ratio = device_res["width"] / device_res["height"]
        pack_ratio = pack_res["width"] / pack_res["height"]

        diff = abs(device_ratio - pack_ratio) / pack_ratio

        if diff < 0.03:
            return True, 1.0, "分辨率兼容"
        elif diff < 0.05:
            return True, 1.0, "分辨率基本兼容，差异在可接受范围内"
        else:
            scale = round(device_res["width"] / pack_res["width"], 1)
            return (
                False,
                scale,
                (
                    f'设备分辨率({device_res["width"]}×{device_res["height"]})'
                    f'与资源包模板({pack_res["width"]}×{pack_res["height"]})不匹配，建议缩放至 {scale}×'
                ),
            )


class PlatformCapabilitiesView(APIView):
    """平台能力查询视图
    GET /api/devices/platform-capabilities/
    返回当前平台支持的截图方式、输入方式、设备类型
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'

    SCREENSHOT_METHODS = {
        "windows": [
            {
                "id": "WGC",
                "name": "Windows Graphics Capture",
                "priority": 1,
                "platform": "windows",
                "description": "Win10+ 推荐，支持后台截图",
            },
            {
                "id": "BitBlt",
                "name": "GDI BitBlt",
                "priority": 2,
                "platform": "windows",
                "description": "兼容性最好，DC/Bitmap 缓存加速",
            },
            {
                "id": "PrintWindow",
                "name": "PrintWindow",
                "priority": 3,
                "platform": "windows",
                "description": "后台截图，兼容性一般",
            },
            {
                "id": "DXGI",
                "name": "DXGI Desktop Duplication",
                "priority": 4,
                "platform": "windows",
                "description": "Win8+ 桌面复制，高帧率",
            },
            {
                "id": "GDI",
                "name": "GDI 全屏截图",
                "priority": 5,
                "platform": "windows",
                "description": "最基础方式，全屏捕获",
            },
        ],
        "macos": [
            {
                "id": "CGWindow",
                "name": "CGWindowListCreateImage",
                "priority": 1,
                "platform": "macos",
                "description": "macOS 标准窗口截图",
            },
            {
                "id": "screencapture",
                "name": "screencapture CLI",
                "priority": 2,
                "platform": "macos",
                "description": "命令行截图工具",
            },
        ],
        "linux": [
            {
                "id": "XShm",
                "name": "XShmGetImage (MIT-SHM)",
                "priority": 1,
                "platform": "linux",
                "description": "X11 共享内存截图，速度快",
            },
            {"id": "XGetImage", "name": "XGetImage", "priority": 2, "platform": "linux", "description": "X11 基础截图"},
            {
                "id": "xdg-portal",
                "name": "xdg-desktop-portal",
                "priority": 3,
                "platform": "linux",
                "description": "Wayland 截图方案",
            },
        ],
    }

    ADB_SCREENSHOT_METHODS = [
        {"id": "scrcpy", "name": "scrcpy", "priority": 1, "platform": "cross", "description": "低延迟投屏截图，跨平台"},
        {"id": "DroidCast", "name": "DroidCast", "priority": 2, "platform": "cross", "description": "高性能截图服务"},
        {
            "id": "NemuIpc",
            "name": "NemuIpc (MuMu)",
            "priority": 3,
            "platform": "windows",
            "description": "MuMu 模拟器专用高速截图",
        },
        {
            "id": "LDOpenGL",
            "name": "LDOpenGL (雷电)",
            "priority": 4,
            "platform": "windows",
            "description": "雷电模拟器专用截图",
        },
        {
            "id": "ADB",
            "name": "ADB screencap",
            "priority": 5,
            "platform": "cross",
            "description": "通用 ADB 截图，兼容性好",
        },
    ]

    INPUT_METHODS = {
        "windows": [
            {
                "id": "SendInput",
                "name": "SendInput (前台)",
                "priority": 1,
                "platform": "windows",
                "description": "前台输入，最稳定",
            },
            {
                "id": "PostMessage",
                "name": "PostMessage (后台)",
                "priority": 2,
                "platform": "windows",
                "description": "后台窗口消息输入",
            },
            {
                "id": "SendMessage",
                "name": "SendMessage (后台同步)",
                "priority": 3,
                "platform": "windows",
                "description": "后台窗口同步消息输入",
            },
        ],
        "macos": [
            {
                "id": "CGEventPost",
                "name": "CGEventPost",
                "priority": 1,
                "platform": "macos",
                "description": "macOS 事件注入",
            },
            {
                "id": "AppleScript",
                "name": "AppleScript",
                "priority": 2,
                "platform": "macos",
                "description": "AppleScript 辅助操作",
            },
        ],
        "linux": [
            {
                "id": "XTest",
                "name": "XTest 伪设备",
                "priority": 1,
                "platform": "linux",
                "description": "X11 伪设备输入",
            },
            {
                "id": "uinput",
                "name": "uinput 内核级",
                "priority": 2,
                "platform": "linux",
                "description": "内核级虚拟输入设备",
            },
        ],
    }

    ADB_INPUT_METHODS = [
        {"id": "MaaTouch", "name": "MaaTouch", "priority": 1, "platform": "cross", "description": "高性能触摸输入"},
        {"id": "minitouch", "name": "minitouch", "priority": 2, "platform": "cross", "description": "低延迟触摸输入"},
        {
            "id": "ADB",
            "name": "ADB input",
            "priority": 3,
            "platform": "cross",
            "description": "通用 ADB 输入，兼容性好",
        },
    ]

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="Return platform capabilities (screenshot / input methods, device types).",
    )
    def get(self, request):
        """返回当前平台能力"""
        from device_bridge.platforms.registry import get_current_platform, get_input_handler, get_screenshot_handler

        current_platform = get_current_platform()

        try:
            handler = get_screenshot_handler()
            runtime_screenshot_methods = handler.available_methods()
        except Exception as exc:
            logger.warning("screenshot handler unavailable: %s", exc)
            runtime_screenshot_methods = []

        try:
            input_handler = get_input_handler()
            runtime_input_methods = input_handler.available_methods()
        except Exception as exc:
            logger.warning("input handler unavailable: %s", exc)
            runtime_input_methods = []

        screenshot_methods = self.SCREENSHOT_METHODS.get(current_platform, [])
        for m in screenshot_methods:
            m["available"] = m["id"] in runtime_screenshot_methods or bool(runtime_screenshot_methods)

        input_methods = self.INPUT_METHODS.get(current_platform, [])
        for m in input_methods:
            m["available"] = m["id"] in runtime_input_methods or bool(runtime_input_methods)

        # Control modes: user-facing abstraction that maps to default concrete methods.
        from agents.models import Device

        control_modes = []
        for mode_value, mode_label in Device.ControlMode.choices:
            if mode_value == Device.ControlMode.AUTO:
                # v3 §2.8.1: 'auto' = inherit from GameProfile; no concrete defaults.
                control_modes.append(
                    {
                        "id": mode_value,
                        "name": mode_label,
                        "default_screenshot_method": None,
                        "default_input_method": None,
                    }
                )
                continue
            defaults = Device.get_control_mode_defaults(mode_value)
            control_modes.append(
                {
                    "id": mode_value,
                    "name": mode_label,
                    "default_screenshot_method": defaults["screenshot_method"],
                    "default_input_method": defaults["input_method"],
                }
            )

        return Response(
            {
                "platform": current_platform,
                "control_modes": control_modes,
                "screenshot_methods": screenshot_methods,
                "adb_screenshot_methods": self.ADB_SCREENSHOT_METHODS,
                "input_methods": input_methods,
                "adb_input_methods": self.ADB_INPUT_METHODS,
                "runtime_screenshot_methods": runtime_screenshot_methods,
                "runtime_input_methods": runtime_input_methods,
            }
        )


class EmulatorLifecycleView(APIView):
    """模拟器生命周期控制视图
    提供列出实例、启动/停止/重启/创建/删除、ADB命令执行功能
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="List all emulator instances across configured providers.",
    )
    def get(self, request):
        """列出所有模拟器实例"""
        from device_bridge.discovery.emulator_lifecycle import list_instances

        try:
            instances = list_instances()
            return Response(
                {
                    "instances": [
                        {
                            "name": i.name,
                            "index": i.index,
                            "status": i.status,
                            "is_running": i.is_running,
                            "emulator_type": i.emulator_type,
                        }
                        for i in instances
                    ],
                    "ldconsole_available": True,
                }
            )
        except Exception as e:
            logger.warning("ldconsole: list instances failed: %s", e, exc_info=True)
            return Response(
                {
                    "instances": [],
                    "ldconsole_available": False,
                    "error": str(e),
                }
            )

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Execute an emulator lifecycle action (start/stop/restart/create/delete/adb).",
    )
    def post(self, request: Request):
        """Execute lifecycle operation, ADB command, health check, or auto-restart"""
        action = request.data.get("action", "")
        name_or_index = str(request.data.get("name_or_index", ""))
        adb_serial = request.data.get("adb_serial", "")
        command = request.data.get("command", "")
        instance_name = request.data.get("instance_name", "")

        from device_bridge.discovery.emulator_lifecycle import (
            auto_restart,
            create_instance,
            delete_instance,
            health_check,
            health_check_all,
            list_instances,
            restart_instance,
            run_adb_command,
            start_instance,
            stop_instance,
        )

        if action == "start":
            result = start_instance(name_or_index)
        elif action == "stop":
            result = stop_instance(name_or_index)
        elif action == "restart":
            result = restart_instance(name_or_index)
        elif action == "create":
            result = create_instance(instance_name)
        elif action == "delete":
            result = delete_instance(name_or_index)
        elif action == "adb":
            result = run_adb_command(adb_serial, command)
        elif action == "health_check":
            instances = list_instances()
            target = next(
                (i for i in instances if str(i.index) == name_or_index or i.name == name_or_index),
                None,
            )
            if not target:
                return Response(
                    {"success": False, "message": f"Instance not found: {name_or_index}"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            hc = health_check(target)
            return Response(
                {
                    "success": True,
                    "message": f'Health check for "{target.name}": {"healthy" if hc.is_healthy else "unhealthy"}',
                    "health_check": {
                        "instance_name": hc.instance_name,
                        "instance_index": hc.instance_index,
                        "is_healthy": hc.is_healthy,
                        "adb_connected": hc.adb_connected,
                        "screen_fps": hc.screen_fps,
                        "anr_detected": hc.anr_detected,
                        "response_time_ms": hc.response_time_ms,
                        "details": hc.details,
                        "checked_at": hc.checked_at,
                        "error": hc.error,
                    },
                }
            )
        elif action == "auto_restart":
            instances = list_instances()
            target = next(
                (i for i in instances if str(i.index) == name_or_index or i.name == name_or_index),
                None,
            )
            if not target:
                return Response(
                    {"success": False, "message": f"Instance not found: {name_or_index}"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            max_retries = int(request.data.get("max_retries", 3))
            result = auto_restart(target, max_retries=max_retries)
        elif action == "health_check_all":
            results = health_check_all()
            return Response(
                {
                    "success": True,
                    "message": f"Checked {len(results)} running instance(s)",
                    "health_checks": [
                        {
                            "instance_name": r.instance_name,
                            "instance_index": r.instance_index,
                            "is_healthy": r.is_healthy,
                            "adb_connected": r.adb_connected,
                            "screen_fps": r.screen_fps,
                            "anr_detected": r.anr_detected,
                            "response_time_ms": r.response_time_ms,
                            "error": r.error,
                            "checked_at": r.checked_at,
                        }
                        for r in results
                    ],
                }
            )
        elif action == "get_config":
            from device_bridge.discovery.emulator_lifecycle import get_current_config

            config = get_current_config(name_or_index)
            return Response(
                {
                    "success": True,
                    "message": f'Config for "{name_or_index}"',
                    "config": config,
                }
            )
        elif action == "configure":
            from device_bridge.discovery.emulator_lifecycle import EmulatorConfig, configure_instance

            emulator_config = EmulatorConfig(
                resolution=request.data.get("resolution"),
                dpi=request.data.get("dpi"),
                cpu_count=request.data.get("cpu_count"),
                memory_mb=request.data.get("memory_mb"),
            )
            result = configure_instance(name_or_index, emulator_config)
        else:
            return Response(
                {"success": False, "message": f"Unsupported action: {action}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_data = {
            "success": result.success,
            "message": result.message,
            "raw_output": result.raw_output,
        }
        if result.instance:
            response_data["instance"] = {
                "name": result.instance.name,
                "index": result.instance.index,
                "status": result.instance.status,
                "is_running": result.instance.is_running,
            }

        # Audit log: lifecycle actions (start/stop/restart/create/delete/adb/
        # auto_restart/configure) are sensitive device-level operations.
        # Read-only actions (health_check, health_check_all, get_config) return
        # early above and never reach this point. Redact `command` defensively
        # in case a future adb action accepts credentials-bearing flags.
        try:
            from accounts.audit import log_audit

            log_audit(
                user=getattr(request, "user", None),
                action=AuditAction.EXECUTE,
                resource_type=AuditResourceType.DEVICE,
                resource_id="",
                details=filter_sensitive_fields({
                    "endpoint": "emulator_lifecycle",
                    "action": action,
                    "name_or_index": name_or_index,
                    "instance_name": instance_name,
                    "adb_serial": adb_serial,
                    "command": command,
                    "success": result.success,
                }, extra_sensitive={"agent_token", "secret", "fcm_token", "token"}),
                ip_address=get_client_ip(request),
            )
        except Exception as audit_exc:
            logger.warning("Audit log failed for emulator lifecycle: %s", audit_exc)

        return Response(response_data)
