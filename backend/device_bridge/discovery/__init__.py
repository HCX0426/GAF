"""
设备发现模块 — backend 侧设备扫描的**单一来源** (F-2)

包含模拟器自动发现 (`scan_all_emulators`) 和 Windows 窗口发现 (`enum_windows`)。
后端扫描入口（`DeviceScanView` 等）统一经由本包，不得绕过。

两层发现边界（F-2/OQ-9）：本包为 **bridge（后端服务）** 层发现；agent 进程侧
`worker/src/devices/` 的 `DeviceCenter.auto_discover()` 为 **center（进程）** 层
运行时发现，二者互补且写同一 `workers.Device` 表（权威/触发时机见 OQ-9 独立设计项）。
"""

from .emulator import EmulatorInfo, scan_all_emulators
from .windows import GAME_PROCESS_NAMES, WindowInfo, enum_windows

__all__ = [
    'scan_all_emulators',
    'EmulatorInfo',
    'enum_windows',
    'WindowInfo',
    'GAME_PROCESS_NAMES',
]
