"""s36: split devices/adb/device.py (1976 lines) into ADB constants + 3 mixins (TD-365 batch 3).

Generic engine copied from scripts/refactor/split_large_python_file.py (s35),
extended with top-level CONSTANT_BLOCK extraction (new for s36).

Verification: 65/65 methods must move (assertion), references untouched.
"""
import ast
from pathlib import Path

SRC = Path("agent/src/devices/adb/device.py")
OUT = Path("agent/src/devices/adb")

# constants to extract (module-level Assigns L24-58): name -> keep in main too
CONSTANT_BLOCK = [
    "SCREENCAP_METHOD", "SCREENCAP_NC_METHOD", "ASCREENCAP_METHOD",
    "ASCREENCAP_NC_METHOD", "DROIDCAST_METHOD", "DROIDCAST_RAW_METHOD",
    "U2_METHOD", "SCRCPY_METHOD", "NEMU_METHOD", "NEMU_IPC_METHOD",
    "LDOPENGL_METHOD", "MAATOUCH_INPUT", "MINITOUCH_INPUT", "U2_INPUT",
    "ADB_INPUT", "HERMIT_INPUT", "NEMU_IPC_INPUT", "DROIDCAST_DEFAULT_PORT",
    "SCRCPY_DEFAULT_PORT", "NEMU_DEFAULT_PORT", "HERMIT_DEFAULT_PORT",
    "ASCREENCAP_REMOTE_PATH", "ASCREENCAP_BMZ1_MAGIC", "HERMIT_PACKAGE_NAME",
    "NEMU_IPC_DLL_TIMEOUT_SEC", "LDOPENGL_DLL_TIMEOUT_SEC",
]

GROUPS = {
    "adb_capture": [
        "capture_screen", "_capture_by_method", "_capture_nemu", "_capture_droidcast_raw",
        "_capture_scrcpy", "_capture_scrcpy_pyav", "_capture_scrcpy_fallback",
        "_capture_droidcast", "_capture_uiautomator2", "_capture_screencap_nc",
        "_capture_screencap", "_ascreencap_reposition_byte_pointer", "_ascreencap_uncompress",
        "_ascreencap_load_screenshot", "_capture_ascreencap", "_capture_ascreencap_nc",
        "_load_nemu_ipc_lib", "_nemu_ipc_connect", "_nemu_ipc_disconnect",
        "_start_nemu_keepalive", "_stop_nemu_keepalive", "_nemu_ipc_get_resolution",
        "_capture_nemu_ipc", "_capture_ldopengl", "_find_nemu_window",
    ],
    "adb_input": [
        "click", "swipe", "key_press", "text_input", "_click_by_method", "_swipe_by_method",
        "_key_press_by_method", "_input_maatouch_click", "_input_maatouch_swipe",
        "_input_adb_click", "_input_adb_swipe", "_input_adb_key_press",
        "_input_minitouch_click", "_input_minitouch_swipe", "_get_u2_device",
        "_input_u2_click", "_input_u2_swipe", "_input_u2_key_press", "_get_hermit_session",
        "_hermit_send", "_input_hermit_click", "_nemu_ipc_convert_xy",
        "_input_nemu_ipc_click", "_input_nemu_ipc_swipe", "_get_maatouch_controller",
        "_resolve_keycode", "_get_minitouch_socket",
    ],
    "adb_lifecycle": [
        "__init__", "connect", "disconnect", "_cleanup_resources", "get_resolution",
        "get_device_info", "reboot",
    ],
}

# per-domain: header imports (from L3-20) + constants (from CONSTANT_BLOCK)
BASE_IMPORTS = [
    "import contextlib", "import json", "import socket", "import time",
    "from typing import Any", "",
]
CAPTURE_CONSTS = [
    "SCREENCAP_METHOD", "SCREENCAP_NC_METHOD", "ASCREENCAP_METHOD",
    "ASCREENCAP_NC_METHOD", "DROIDCAST_METHOD", "DROIDCAST_RAW_METHOD",
    "U2_METHOD", "SCRCPY_METHOD", "NEMU_METHOD", "NEMU_IPC_METHOD",
    "LDOPENGL_METHOD", "ASCREENCAP_REMOTE_PATH", "ASCREENCAP_BMZ1_MAGIC",
    "NEMU_IPC_DLL_TIMEOUT_SEC",
]
INPUT_CONSTS = [
    "MAATOUCH_INPUT", "MINITOUCH_INPUT", "U2_INPUT", "ADB_INPUT",
    "HERMIT_INPUT", "NEMU_IPC_INPUT",
]
LIFECYCLE_CONSTS = [
    "DROIDCAST_DEFAULT_PORT", "SCRCPY_DEFAULT_PORT", "NEMU_DEFAULT_PORT",
    "HERMIT_DEFAULT_PORT",
]

EXTRA_IMPORTS = {
    "adb_capture": [
        "import importlib", "import io", "import struct",
        "import numpy as np",
        "from core.retry import retry_screenshot",
        "from devices.base import BaseDevice, require_operable",
        "from monitor.resources import record_screenshot",
        "from PIL import Image",
        f"from .adb_constants import {', '.join(CAPTURE_CONSTS)}",
    ],
    "adb_input": [
        "from core.exceptions import DeviceError",
        "from core.retry import retry_input",
        "from devices.base import BaseDevice, require_operable",
        f"from .adb_constants import {', '.join(INPUT_CONSTS)}",
    ],
    "adb_lifecycle": [
        "from core.exceptions import DeviceError",
        "from devices.base import BaseDevice, DeviceStatus, require_operable",
        "from .pool import get_adb_pool",
        f"from .adb_constants import {', '.join(LIFECYCLE_CONSTS)}",
    ],
}

MIXIN_NAMES = {
    "adb_capture": "ADBCaptureMixin",
    "adb_input": "ADBInputMixin",
    "adb_lifecycle": "ADBLifecycleMixin",
}

src = SRC.read_text(encoding="utf-8")
lines = src.splitlines()
tree = ast.parse(src)

# exact method boundaries (decorator_list[0].lineno — N202 item 3)
method_bounds: dict[str, tuple[int, int]] = {}
for cls in tree.body:
    if isinstance(cls, ast.ClassDef) and cls.name == "ADBDevice":
        for m in cls.body:
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = m.decorator_list[0].lineno if m.decorator_list else m.lineno
                method_bounds[m.name] = (start, m.end_lineno)

# constant block boundaries: first constant lineno .. last constant end_lineno
c_first = next(n.lineno for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == CONSTANT_BLOCK[0] for t in n.targets))
c_last = max(n.end_lineno for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id in CONSTANT_BLOCK for t in n.targets))
CONST_BLOCK = lines[c_first - 1:c_last]

# header: docstring + imports + logger (L1-22), drop nothing
header = lines[:22]
while header and header[-1].strip() == "":
    header.pop()

# completeness assertion: every method must be in exactly one group
grouped = [m for g in GROUPS.values() for m in g]
missing = [m for m in method_bounds if m not in grouped]
dup = [m for m in grouped if grouped.count(m) > 1]
assert not missing, f"methods not grouped: {missing}"
assert not dup, f"methods grouped twice: {dup}"
assert len(grouped) == len(method_bounds), f"method count mismatch: {len(grouped)} vs {len(method_bounds)}"
print(f"methods: {len(method_bounds)} grouped OK")


def method_block(name: str) -> str:
    s, e = method_bounds[name]
    block = lines[s - 1:e]
    while block and block[0].strip() == "":
        block.pop(0)
    while block and block[-1].strip() == "":
        block.pop()
    return "\n".join(block)


def build_mixin(module: str) -> str:
    mixin_name = MIXIN_NAMES[module]
    parts = [f"class {mixin_name}(BaseDevice):",
             f'    """ADBDevice mixin — see devices/adb/device.py for full class (s36 split)."""']
    for mname in GROUPS[module]:
        parts.append("")
        parts.append(method_block(mname))
    imports = (BASE_IMPORTS + ["import logging", ""]
               + EXTRA_IMPORTS[module] + ["", "logger = logging.getLogger(__name__)", ""])
    return "\n".join(imports) + "\n\n" + "\n".join(parts) + "\n"


def main() -> None:
    # adb_constants.py
    (OUT / "adb_constants.py").write_text(
        "\n".join(['"""' + SRC.stem + " constants (s36 split) — imported by device.py + mixins. Do not edit values here.\"\"\"",
                   ""] + CONST_BLOCK) + "\n", encoding="utf-8")
    print("wrote adb_constants.py")

    for module in GROUPS:
        out = OUT / f"{module}.py"
        out.write_text(build_mixin(module), encoding="utf-8")
        n = len(out.read_text(encoding="utf-8").splitlines())
        print(f"wrote {module}.py ({n} lines)")

    # main file: header imports + mixin imports + constants re-export + logger + class + __all__
    const_import = ", ".join(CONSTANT_BLOCK)
    main_parts = [
        "\n".join(header[:-2]),  # all imports, drop logger
        "",
        "from .adb_constants import " + const_import,
        "from .adb_capture import ADBCaptureMixin",
        "from .adb_input import ADBInputMixin",
        "from .adb_lifecycle import ADBLifecycleMixin",
        "",
        header[-1],  # logger = logging.getLogger(__name__)
        "",
        "",
        "class ADBDevice(ADBLifecycleMixin, ADBCaptureMixin, ADBInputMixin, BaseDevice):",
        '    """ADB 设备控制器：通过 adbutils 控制 ADB 设备，支持多种截图和输入降级链',
        "",
        "    方法按功能域拆分到 mixin：",
        "    - ADBLifecycleMixin — __init__/connect/disconnect/资源清理/查询/reboot",
        "    - ADBCaptureMixin — capture_screen + 降级链 (_capture_*)",
        "    - ADBInputMixin — click/swipe/key_press/text_input + 降级链 (_input_*)",
        '    """',
        "",
        "__all__ = [" + ", ".join(['"ADBDevice"'] + [f'"{c}"' for c in CONSTANT_BLOCK]) + "]",
    ]
    (OUT / "device.py").write_text("\n".join(main_parts) + "\n", encoding="utf-8")
    print("wrote device.py (main class)")


if __name__ == "__main__":
    main()