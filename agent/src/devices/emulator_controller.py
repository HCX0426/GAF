"""Emulator lifecycle controller: kill / start / restart / wait_for_boot.

Cross-platform abstraction for emulator process management.
Windows: uses taskkill + ldconsole/MuMuPlayer command line.
Linux/macOS: uses pkill + process signals (limited emulator support).

Used by RecoveryStrategy Layer 4 (device-level reconnect) to restart
emulator when all automated recovery within the emulator fails.
"""
import logging
import platform
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


# Emulator type to process name mapping (Windows)
EMULATOR_PROCESS_NAMES: dict[str, list[str]] = {
    "ldplayer": ["dnplayer.exe", "dnplayer9.exe", "LdVBoxHeadless.exe"],
    "mumu": ["MuMuPlayer.exe", "NemuHeadless.exe"],
    "bluestacks": ["HD-Player.exe", "Bluestacks.exe"],
    "nox": ["Nox.exe", "NoxVMHandle.exe"],
    "memu": ["MEmu.exe", "MEmuHeadless.exe"],
    "xiaoyao": ["XiaoyaoHelper.exe"],
}

# Emulator type to control executable name (Windows)
EMULATOR_CONTROL_EXE: dict[str, str] = {
    "ldplayer": "ldconsole.exe",
    "mumu": "MuMuManager.exe",
    "bluestacks": "HD-RunApp.exe",
}


class EmulatorController:
    """Cross-platform emulator lifecycle controller.

    Provides kill/start/restart/wait_for_boot operations for emulators.
    On Windows, uses ldconsole/MuMuManager command-line tools when available,
    falls back to taskkill. On Linux/macOS, uses pkill (limited support since
    most emulators are Windows-only).
    """

    def __init__(
        self,
        adb_path: str = "adb",
        control_dir: str | None = None,
        boot_timeout: float = 120.0,
        boot_poll_interval: float = 2.0,
    ):
        """Initialize emulator controller.

        Args:
            adb_path: Path to adb executable (used for wait_for_boot)
            control_dir: Directory containing emulator control executables
                         (ldconsole.exe, MuMuManager.exe). If None, relies on PATH.
            boot_timeout: Maximum seconds to wait for emulator boot
            boot_poll_interval: Seconds between boot status polls
        """
        self.adb_path = adb_path
        self.control_dir = Path(control_dir) if control_dir else None
        self.boot_timeout = boot_timeout
        self.boot_poll_interval = boot_poll_interval
        self._is_windows = platform.system() == "Windows"

    def kill_emulator(self, emulator_type: str, instance_id: str | None = None) -> bool:
        """Kill emulator process(es).

        Args:
            emulator_type: Emulator type key (ldplayer/mumu/bluestacks/nox/memu/xiaoyao)
            instance_id: Optional instance ID (e.g. ldconsole index 0/1/2).
                         If None, kills all processes of the given type.

        Returns:
            True if kill command executed successfully, False otherwise
        """
        if emulator_type not in EMULATOR_PROCESS_NAMES:
            logger.warning("Unknown emulator type: %s", emulator_type)
            return False

        # Try control executable first (graceful shutdown)
        if self._is_windows and self._try_control_kill(emulator_type, instance_id):
            return True

        # Fallback: kill by process name
        process_names = EMULATOR_PROCESS_NAMES[emulator_type]
        return self._kill_by_process_names(process_names)

    def start_emulator(self, emulator_type: str, instance_id: str | None = None) -> bool:
        """Start emulator process.

        Args:
            emulator_type: Emulator type key
            instance_id: Optional instance ID

        Returns:
            True if start command executed successfully, False otherwise
        """
        if emulator_type not in EMULATOR_PROCESS_NAMES:
            logger.warning("Unknown emulator type: %s", emulator_type)
            return False

        if not self._is_windows:
            logger.warning("Emulator start not supported on %s", platform.system())
            return False

        return self._try_control_start(emulator_type, instance_id)

    def restart_emulator(
        self,
        emulator_type: str,
        instance_id: str | None = None,
        wait_for_boot: bool = True,
    ) -> bool:
        """Restart emulator: kill + start + wait for boot.

        This is the primary method for Layer 4 device-level recovery.

        Args:
            emulator_type: Emulator type key
            instance_id: Optional instance ID
            wait_for_boot: If True, wait for emulator to fully boot

        Returns:
            True if restart succeeded and (optionally) boot completed
        """
        logger.info(
            "Restarting emulator: type=%s instance=%s wait=%s",
            emulator_type, instance_id, wait_for_boot,
        )

        # Step 1: Kill
        if not self.kill_emulator(emulator_type, instance_id):
            logger.error("Failed to kill emulator %s", emulator_type)
            return False

        # Brief delay to ensure process cleanup
        time.sleep(3.0)

        # Step 2: Start
        if not self.start_emulator(emulator_type, instance_id):
            logger.error("Failed to start emulator %s", emulator_type)
            return False

        # Step 3: Wait for boot (optional)
        if wait_for_boot and not self.wait_for_boot():
            logger.error("Emulator %s failed to boot within %.0fs", emulator_type, self.boot_timeout)
            return False

        logger.info("Emulator %s restarted successfully", emulator_type)
        return True

    def wait_for_boot(self, device_serial: str | None = None) -> bool:
        """Wait for emulator to fully boot via ADB.

        Uses `adb wait-for-device` then polls `getprop sys.boot_completed`
        until it returns 1 or timeout is reached.

        Args:
            device_serial: Optional ADB device serial. If None, waits for any device.

        Returns:
            True if boot completed within timeout, False otherwise
        """
        logger.info("Waiting for emulator boot (timeout=%.0fs)", self.boot_timeout)

        # Step 1: Wait for device to appear in ADB
        cmd_wait = [self.adb_path, "wait-for-device"]
        if device_serial:
            cmd_wait = [self.adb_path, "-s", device_serial, "wait-for-device"]

        try:
            subprocess.run(cmd_wait, timeout=self.boot_timeout, check=False, capture_output=True)
        except subprocess.TimeoutExpired:
            logger.error("ADB wait-for-device timed out after %.0fs", self.boot_timeout)
            return False
        except Exception as e:
            logger.error("ADB wait-for-device failed: %s", e)
            return False

        # Step 2: Poll for boot_completed property
        deadline = time.time() + self.boot_timeout
        cmd_getprop = [self.adb_path, "shell", "getprop", "sys.boot_completed"]
        if device_serial:
            cmd_getprop = [self.adb_path, "-s", device_serial, "shell", "getprop", "sys.boot_completed"]

        while time.time() < deadline:
            try:
                result = subprocess.run(
                    cmd_getprop,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                output = result.stdout.strip()
                if output == "1":
                    logger.info("Emulator boot completed")
                    return True
            except Exception:
                pass
            time.sleep(self.boot_poll_interval)

        logger.error("Emulator boot did not complete within %.0fs", self.boot_timeout)
        return False

    def _get_control_exe_path(self, exe_name: str) -> str | None:
        """Find control executable in control_dir or PATH."""
        if self.control_dir:
            candidate = self.control_dir / exe_name
            if candidate.exists():
                return str(candidate)
        # Try PATH
        found = shutil.which(exe_name)
        return found

    def _try_control_kill(self, emulator_type: str, instance_id: str | None) -> bool:
        """Try to kill emulator using control executable (Windows only)."""
        exe_name = EMULATOR_CONTROL_EXE.get(emulator_type)
        if not exe_name:
            return False

        exe_path = self._get_control_exe_path(exe_name)
        if not exe_path:
            return False

        try:
            if emulator_type == "ldplayer":
                # ldconsole quit <index>
                idx = instance_id or "0"
                cmd = [exe_path, "quit", idx]
            elif emulator_type == "mumu":
                # MuMuManager api -v <instance> shutdown_player
                idx = instance_id or "0"
                cmd = [exe_path, "api", "-v", idx, "shutdown_player"]
            else:
                return False

            subprocess.run(cmd, timeout=15, check=False, capture_output=True)
            logger.info("Killed emulator %s via %s", emulator_type, exe_name)
            return True
        except Exception as e:
            logger.warning("Control kill failed for %s: %s", emulator_type, e)
            return False

    def _try_control_start(self, emulator_type: str, instance_id: str | None) -> bool:
        """Try to start emulator using control executable (Windows only)."""
        exe_name = EMULATOR_CONTROL_EXE.get(emulator_type)
        if not exe_name:
            return False

        exe_path = self._get_control_exe_path(exe_name)
        if not exe_path:
            return False

        try:
            if emulator_type == "ldplayer":
                # ldconsole launch <index>
                idx = instance_id or "0"
                cmd = [exe_path, "launch", idx]
            elif emulator_type == "mumu":
                # MuMuManager api -v <instance> launch_player
                idx = instance_id or "0"
                cmd = [exe_path, "api", "-v", idx, "launch_player"]
            else:
                return False

            subprocess.run(cmd, timeout=15, check=False, capture_output=True)
            logger.info("Started emulator %s via %s", emulator_type, exe_name)
            return True
        except Exception as e:
            logger.warning("Control start failed for %s: %s", emulator_type, e)
            return False

    def _kill_by_process_names(self, process_names: list[str]) -> bool:
        """Kill processes by name (fallback when control exe unavailable)."""
        any_killed = False
        for name in process_names:
            try:
                if self._is_windows:
                    cmd = ["taskkill", "/F", "/IM", name]
                else:
                    # pkill with process name (without .exe)
                    clean_name = name.replace(".exe", "")
                    cmd = ["pkill", "-f", clean_name]

                result = subprocess.run(cmd, capture_output=True, timeout=10, check=False)
                if result.returncode == 0:
                    any_killed = True
                    logger.info("Killed process: %s", name)
            except Exception as e:
                logger.warning("Failed to kill process %s: %s", name, e)

        return any_killed
