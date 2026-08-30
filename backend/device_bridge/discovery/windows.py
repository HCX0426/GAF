import logging
from dataclasses import dataclass, field

# F-3: single source of truth — 游戏进程名列表与平台层共用一份
# (device_bridge/platforms/windows/discovery.py)，避免两份漂移。
from device_bridge.platforms.windows.discovery import GAME_PROCESS_NAMES  # noqa: F401

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    """窗口信息"""
    title: str
    process_name: str
    hwnd: str
    resolution: dict = field(default_factory=lambda: {'width': 0, 'height': 0})
    is_game: bool = False


def enum_windows() -> list[WindowInfo]:
    """枚举所有顶层可见窗口（委托到平台抽象层）"""
    try:
        from device_bridge.platforms.windows.discovery import _enum_windows as _platform_enum
        raw = _platform_enum()
        return [
            WindowInfo(
                title=w['title'],
                process_name=w['process_name'],
                hwnd=w['hwnd'],
                resolution=w['resolution'],
                is_game=w['is_game'],
            )
            for w in raw
        ]
    except Exception as e:
        logger.warning('窗口枚举失败: %s', e)
        return []
