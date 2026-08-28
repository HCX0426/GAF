"""device constants (s36 split) — imported by device.py + mixins. Do not edit values here."""

SCREENCAP_METHOD = "screencap"
SCREENCAP_NC_METHOD = "screencap_nc"
ASCREENCAP_METHOD = "ascreencap"
ASCREENCAP_NC_METHOD = "ascreencap_nc"
DROIDCAST_METHOD = "droidcast"
DROIDCAST_RAW_METHOD = "droidcast_raw"
U2_METHOD = "u2"
SCRCPY_METHOD = "scrcpy"
NEMU_METHOD = "nemu"
NEMU_IPC_METHOD = "nemu_ipc"
LDOPENGL_METHOD = "ldopengl"

MAATOUCH_INPUT = "maatouch"
MINITOUCH_INPUT = "minitouch"
U2_INPUT = "u2"
ADB_INPUT = "adb"
HERMIT_INPUT = "hermit"
NEMU_IPC_INPUT = "nemu_ipc"

DROIDCAST_DEFAULT_PORT = 53533
SCRCPY_DEFAULT_PORT = 27183
NEMU_DEFAULT_PORT = 7555
HERMIT_DEFAULT_PORT = 9999
ASCREENCAP_REMOTE_PATH = "/data/local/tmp/ascreencap"

# BMZ1 magic number for ascreencap compressed stream header
ASCREENCAP_BMZ1_MAGIC = 828001602
# Hermit package name on Android device
HERMIT_PACKAGE_NAME = "com.lookcos.hermit"

# Timeout (seconds) for NemuIpc / LDOpenGL DLL calls. These calls perform
# shared-memory or GPU-side reads and normally return within tens of ms;
# 5s is the safety net for hung emulator processes (P0-3).
NEMU_IPC_DLL_TIMEOUT_SEC = 5.0
LDOPENGL_DLL_TIMEOUT_SEC = 5.0
