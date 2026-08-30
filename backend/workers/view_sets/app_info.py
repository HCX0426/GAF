import contextlib
import logging
import os
import subprocess

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission
from workers.models import Device
from workers.view_sets.crud import DeviceViewSet

logger = logging.getLogger(__name__)


# Import service-layer helpers (moved to agents/services/device_service.py in Phase 1).


class DeviceAppView(APIView):
    """Device app management endpoint (R10-C)
    POST /api/v2/devices/{id}/app/

    Manage apps on emulator (ADB) devices: launch, force-stop, list, uninstall.
    Windows devices: manage processes (start/kill/list).

    Request body (JSON) - choose one action:
    {
        "action": "launch",        // Launch app by package name
        "package": "com.example.app"
    }
    {
        "action": "force_stop",    // Force stop app
        "package": "com.example.app"
    }
    {
        "action": "list"           // List installed packages (emulator) or running processes (Windows)
    }
    {
        "action": "uninstall",     // Uninstall app (emulator only)
        "package": "com.example.app"
    }

    Response:
    {
        "success": bool,
        "action": str,
        "data": obj | null,        // Action-specific data (e.g. package list)
        "error": str | null
    }
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
        description="Manage apps on emulator (ADB) devices or processes on Windows devices.",
    )
    def post(self, request: Request, id: int):
        """Execute app management action on device"""
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
        if not action:
            return Response(
                {"success": False, "error": "Missing required field: action"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_actions = ["launch", "force_stop", "list", "uninstall"]
        if action not in valid_actions:
            return Response(
                {"success": False, "error": f"Invalid action: {action}. Must be one of {valid_actions}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Emulator devices: use ADB
        if device.device_type == Device.DeviceType.EMULATOR:
            try:
                result = self._execute_adb_app_action(device, action, request.data)
                logger.info(
                    "ADB app action on emulator %s (%s): action=%s success=%s",
                    device.name,
                    id,
                    action,
                    result.get("success"),
                )
                return Response(result)
            except Exception as e:
                logger.error("ADB app action failed for device %d: %s", id, e, exc_info=True)
                return Response(
                    {"success": False, "action": action, "error": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # Windows devices: process management
        if device.device_type == Device.DeviceType.WINDOWS:
            try:
                result = self._execute_windows_app_action(device, action, request.data)
                # Audit log: include requester + target params for security traceability
                target_param = request.data.get("package") or request.data.get("exe_path") or request.data.get("pid")
                logger.info(
                    "Windows app action on device %s (%s): action=%s success=%s requester=%s target=%r",
                    device.name,
                    id,
                    action,
                    result.get("success"),
                    getattr(request.user, "username", ""),
                    target_param,
                )
                return Response(result)
            except Exception as e:
                logger.error("Windows app action failed for device %d: %s", id, e, exc_info=True)
                return Response(
                    {"success": False, "action": action, "error": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(
            {
                "success": False,
                "action": action,
                "error": f"App management not supported for device type {device.device_type}",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _execute_adb_app_action(self, device, action, data):
        """Execute app action via ADB for emulator devices"""
        adb_exe = DeviceViewSet._get_adb_path()
        serial = device.adb_serial or ""
        if not serial:
            return {"success": False, "action": action, "error": "Emulator device has no adb_serial"}

        if action == "launch":
            package = data.get("package")
            if not package:
                return {"success": False, "action": action, "error": "Missing required field: package"}
            # Use monkey to launch app by package name (no need to know main activity)
            proc = subprocess.run(
                [adb_exe, "-s", serial, "shell", "monkey", "-p", str(package), "1"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return {
                "success": proc.returncode == 0,
                "action": action,
                "data": {"package": package, "method": "monkey"},
                "error": proc.stderr.strip() if proc.returncode != 0 else None,
            }

        elif action == "force_stop":
            package = data.get("package")
            if not package:
                return {"success": False, "action": action, "error": "Missing required field: package"}
            proc = subprocess.run(
                [adb_exe, "-s", serial, "shell", "am", "force-stop", str(package)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {
                "success": proc.returncode == 0,
                "action": action,
                "data": {"package": package},
                "error": proc.stderr.strip() if proc.returncode != 0 else None,
            }

        elif action == "list":
            # List installed packages (optional filter via data.get('filter'))
            cmd = [adb_exe, "-s", serial, "shell", "pm", "list", "packages"]
            filter_str = data.get("filter", "")
            if filter_str:
                cmd.append(str(filter_str))
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc.returncode != 0:
                return {
                    "success": False,
                    "action": action,
                    "error": proc.stderr.strip(),
                }
            # Parse "package:com.example.app" lines
            packages = [
                line.replace("package:", "").strip() for line in proc.stdout.splitlines() if line.startswith("package:")
            ]
            return {
                "success": True,
                "action": action,
                "data": {"packages": packages, "count": len(packages)},
                "error": None,
            }

        elif action == "uninstall":
            package = data.get("package")
            if not package:
                return {"success": False, "action": action, "error": "Missing required field: package"}
            proc = subprocess.run(
                [adb_exe, "-s", serial, "uninstall", str(package)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            success = proc.returncode == 0 and "Success" in proc.stdout
            return {
                "success": success,
                "action": action,
                "data": {"package": package, "output": proc.stdout.strip()},
                "error": proc.stderr.strip() if not success else None,
            }

        return {"success": False, "action": action, "error": f"Unknown action: {action}"}

    def _execute_windows_app_action(self, device, action, data):
        """Execute app/process action on Windows devices"""
        if action == "list":
            # List running processes with window titles
            try:
                proc = subprocess.run(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if proc.returncode != 0:
                    return {"success": False, "action": action, "error": proc.stderr.strip()}
                # Parse CSV output: "name","pid","session","sessionnum","mem"
                processes = []
                for line in proc.stdout.splitlines():
                    parts = line.strip().strip('"').split('","')
                    if len(parts) >= 2:
                        processes.append({"name": parts[0], "pid": int(parts[1]) if parts[1].isdigit() else 0})
                return {
                    "success": True,
                    "action": action,
                    "data": {"processes": processes, "count": len(processes)},
                    "error": None,
                }
            except Exception as e:
                logger.warning("ldconsole action %s failed: %s", action, e, exc_info=True)
                return {"success": False, "action": action, "error": str(e)}

        elif action == "launch":
            # Launch executable on Windows (with whitelist + UNC + audit hardening).
            exe_path = data.get("package") or data.get("exe_path")
            if not exe_path:
                return {"success": False, "action": action, "error": "Missing required field: package or exe_path"}
            exe_path = str(exe_path)
            real_path = os.path.realpath(exe_path)
            # Reject UNC paths (SMB attack surface).
            if real_path.startswith("\\\\"):
                logger.warning(
                    "Rejected UNC path launch on device %s: path=%r",
                    device.name,
                    exe_path,
                )
                return {
                    "success": False,
                    "action": action,
                    "error": "UNC paths are not allowed for security reasons",
                }
            # Whitelist enforcement (only when GAF_ALLOWED_WINDOWS_EXES is configured).
            from django.conf import settings

            allowed = getattr(settings, "GAF_ALLOWED_WINDOWS_EXES", None)
            if allowed:
                allowed_real = {os.path.realpath(p).lower() for p in allowed}
                if real_path.lower() not in allowed_real:
                    logger.warning(
                        "Rejected non-whitelisted launch on device %s: path=%r",
                        device.name,
                        exe_path,
                    )
                    return {
                        "success": False,
                        "action": action,
                        "error": f"Executable not in whitelist: {exe_path}. Contact admin to whitelist.",
                    }
            try:
                proc = subprocess.Popen([real_path], shell=False)
                logger.info(
                    "Windows app launched on device %s: path=%r pid=%d",
                    device.name,
                    real_path,
                    proc.pid,
                )
                return {
                    "success": True,
                    "action": action,
                    "data": {"exe_path": real_path, "pid": proc.pid},
                    "error": None,
                }
            except Exception as e:
                logger.error(
                    "Windows app launch failed on device %s: path=%r error=%s",
                    device.name,
                    real_path,
                    e,
                    exc_info=True,
                )
                return {"success": False, "action": action, "error": str(e)}

        elif action == "force_stop":
            # Kill process by name or pid (with system-process protection).
            package = data.get("package") or data.get("exe_path")
            pid = data.get("pid")
            if not package and not pid:
                return {"success": False, "action": action, "error": "Missing required field: package or pid"}
            # Refuse to kill Windows system-critical processes.
            system_protected = {
                "smss.exe",
                "csrss.exe",
                "winlogon.exe",
                "services.exe",
                "lsass.exe",
                "svchost.exe",
                "explorer.exe",
                "fontdrvhost.exe",
                "dwm.exe",
                "wininit.exe",
            }
            if package:
                image_name = os.path.basename(str(package)).lower()
                if image_name in system_protected:
                    logger.warning(
                        "Rejected kill of system process %r on device %s",
                        image_name,
                        device.name,
                    )
                    return {
                        "success": False,
                        "action": action,
                        "error": f"Killing system process {image_name} is not allowed",
                    }
            try:
                if pid:
                    proc = subprocess.run(
                        ["taskkill", "/PID", str(pid), "/F"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                else:
                    # Kill by image name (extract basename)
                    image_name = os.path.basename(str(package))
                    proc = subprocess.run(
                        ["taskkill", "/IM", image_name, "/F"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                success = proc.returncode == 0
                logger.info(
                    "Windows process kill on device %s: target=%r pid=%r success=%s",
                    device.name,
                    package,
                    pid,
                    success,
                )
                return {
                    "success": success,
                    "action": action,
                    "data": {"target": package or pid},
                    "error": proc.stderr.strip() if not success else None,
                }
            except Exception as e:
                logger.warning("ldconsole action %s failed: %s", action, e, exc_info=True)
                return {"success": False, "action": action, "error": str(e)}

        elif action == "uninstall":
            return {
                "success": False,
                "action": action,
                "error": "Uninstall not supported for Windows devices via this API",
            }

        return {"success": False, "action": action, "error": f"Unknown action: {action}"}


class DeviceDetailView(APIView):
    """Device detail query endpoint (R10-D, F-1: was DeviceInfoView)
    POST /api/v2/devices/{id}/info/

    Query device information: battery, screen size, OS version, model, etc.

    Request body (JSON):
    {
        "query": "battery" | "screen" | "system" | "all"  // default: "all"
    }

    Response:
    {
        "success": bool,
        "data": {
            "battery_level": int | null,      // Battery percentage (0-100)
            "battery_charging": bool | null,
            "screen_width": int | null,
            "screen_height": int | null,
            "android_version": str | null,    // Emulator only
            "model": str | null,
            "os_version": str | null,         // Windows OS version
            "device_type": str
        },
        "error": str | null
    }
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
        description="Query device information: battery, screen size, OS version, model, etc.",
    )
    def post(self, request: Request, id: int):
        """Query device information"""
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

        query = request.data.get("query", "all")

        if device.device_type == Device.DeviceType.EMULATOR:
            try:
                data = self._query_adb_info(device, query)
                logger.info("ADB info query on emulator %s (%s): query=%s", device.name, id, query)
                return Response({"success": True, "data": data, "error": None})
            except Exception as e:
                logger.error("ADB info query failed for device %d: %s", id, e, exc_info=True)
                return Response(
                    {"success": False, "data": None, "error": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        if device.device_type == Device.DeviceType.WINDOWS:
            try:
                data = self._query_windows_info(device, query)
                logger.info("Windows info query on device %s (%s): query=%s", device.name, id, query)
                return Response({"success": True, "data": data, "error": None})
            except Exception as e:
                logger.error("Windows info query failed for device %d: %s", id, e, exc_info=True)
                return Response(
                    {"success": False, "data": None, "error": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(
            {"success": False, "data": None, "error": f"Info query not supported for device type {device.device_type}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _query_adb_info(self, device, query):
        """Query device info via ADB (emulator)"""
        adb_exe = DeviceViewSet._get_adb_path()
        serial = device.adb_serial or ""
        if not serial:
            raise RuntimeError("Emulator device has no adb_serial")

        def adb_shell(cmd):
            proc = subprocess.run(
                [adb_exe, "-s", serial, "shell"] + cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.stdout.strip() if proc.returncode == 0 else ""

        data = {
            "battery_level": None,
            "battery_charging": None,
            "screen_width": None,
            "screen_height": None,
            "android_version": None,
            "model": None,
            "device_type": "emulator",
        }

        if query in ("battery", "all"):
            # Battery level via dumpsys
            output = adb_shell(["dumpsys", "battery"])
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("level:"):
                    with contextlib.suppress(ValueError, IndexError):
                        data["battery_level"] = int(line.split(":")[1].strip())
                elif line.startswith("status:"):
                    with contextlib.suppress(ValueError, IndexError):
                        status_val = int(line.split(":")[1].strip())
                        # 2=charging, 3=discharging, 4=not charging, 5=full
                        data["battery_charging"] = status_val == 2

        if query in ("screen", "all"):
            # Screen size via wm size
            output = adb_shell(["wm", "size"])
            # Output: "Physical size: 1080x1920"
            if "Physical size:" in output:
                try:
                    size_str = output.split("Physical size:")[1].strip()
                    w, h = size_str.split("x")
                    data["screen_width"] = int(w)
                    data["screen_height"] = int(h)
                except (ValueError, IndexError):
                    logger.debug("adb wm size output not parseable: %r", output)
            # Fallback to device resolution from DB
            if data["screen_width"] is None and device.resolution_width:
                data["screen_width"] = device.resolution_width
                data["screen_height"] = device.resolution_height

        if query in ("system", "all"):
            # Android version
            data["android_version"] = adb_shell(["getprop", "ro.build.version.release"]) or None
            # Model
            data["model"] = adb_shell(["getprop", "ro.product.model"]) or None

        return data

    def _query_windows_info(self, device, query):
        """Query device info on Windows"""
        data = {
            "battery_level": None,
            "battery_charging": None,
            "screen_width": device.resolution_width,
            "screen_height": device.resolution_height,
            "android_version": None,
            "model": None,
            "os_version": None,
            "device_type": "windows",
        }

        if query in ("system", "all"):
            try:
                proc = subprocess.run(
                    ["cmd", "/c", "ver"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc.returncode == 0:
                    data["os_version"] = proc.stdout.strip()
            except Exception as e:
                logger.warning("Failed to query Windows OS version: %s", e)

        if query in ("screen", "all") and not data["screen_width"]:
            # Query screen resolution via platform abstraction layer (B001 fix).
            from device_bridge.platforms.windows.window_info import get_screen_resolution

            res = get_screen_resolution()
            if res:
                data["screen_width"], data["screen_height"] = res

        return data
