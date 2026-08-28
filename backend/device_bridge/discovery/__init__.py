"""
设备发现模块
包含模拟器自动发现和 Windows 窗口发现
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
