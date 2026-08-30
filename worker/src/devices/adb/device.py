"""ADB 设备控制器：通过 adbutils 控制 ADB 设备，支持多种截图和输入降级链"""

import logging

from devices.base import BaseDevice

from .adb_capture import ADBCaptureMixin
from .adb_constants import (
    ADB_INPUT,
    ASCREENCAP_BMZ1_MAGIC,
    ASCREENCAP_METHOD,
    ASCREENCAP_NC_METHOD,
    ASCREENCAP_REMOTE_PATH,
    DROIDCAST_DEFAULT_PORT,
    DROIDCAST_METHOD,
    DROIDCAST_RAW_METHOD,
    HERMIT_DEFAULT_PORT,
    HERMIT_INPUT,
    HERMIT_PACKAGE_NAME,
    LDOPENGL_DLL_TIMEOUT_SEC,
    LDOPENGL_METHOD,
    MAATOUCH_INPUT,
    MINITOUCH_INPUT,
    NEMU_DEFAULT_PORT,
    NEMU_IPC_DLL_TIMEOUT_SEC,
    NEMU_IPC_INPUT,
    NEMU_IPC_METHOD,
    NEMU_METHOD,
    SCRCPY_DEFAULT_PORT,
    SCRCPY_METHOD,
    SCREENCAP_METHOD,
    SCREENCAP_NC_METHOD,
    U2_INPUT,
    U2_METHOD,
)
from .adb_input import ADBInputMixin
from .adb_lifecycle import ADBLifecycleMixin

logger = logging.getLogger(__name__)


class ADBDevice(ADBLifecycleMixin, ADBCaptureMixin, ADBInputMixin, BaseDevice):
    """ADB 设备控制器：通过 adbutils 控制 ADB 设备，支持多种截图和输入降级链

    方法按功能域拆分到 mixin：
    - ADBLifecycleMixin — __init__/connect/disconnect/资源清理/查询/reboot
    - ADBCaptureMixin — capture_screen + 降级链 (_capture_*)
    - ADBInputMixin — click/swipe/key_press/text_input + 降级链 (_input_*)
    """

__all__ = ["ADBDevice", "SCREENCAP_METHOD", "SCREENCAP_NC_METHOD", "ASCREENCAP_METHOD", "ASCREENCAP_NC_METHOD", "DROIDCAST_METHOD", "DROIDCAST_RAW_METHOD", "U2_METHOD", "SCRCPY_METHOD", "NEMU_METHOD", "NEMU_IPC_METHOD", "LDOPENGL_METHOD", "MAATOUCH_INPUT", "MINITOUCH_INPUT", "U2_INPUT", "ADB_INPUT", "HERMIT_INPUT", "NEMU_IPC_INPUT", "DROIDCAST_DEFAULT_PORT", "SCRCPY_DEFAULT_PORT", "NEMU_DEFAULT_PORT", "HERMIT_DEFAULT_PORT", "ASCREENCAP_REMOTE_PATH", "ASCREENCAP_BMZ1_MAGIC", "HERMIT_PACKAGE_NAME", "NEMU_IPC_DLL_TIMEOUT_SEC", "LDOPENGL_DLL_TIMEOUT_SEC"]
