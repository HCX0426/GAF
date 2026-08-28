"""Windows 窗口自动发现：枚举窗口并发现游戏窗口"""

import ctypes
import ctypes.wintypes
import logging
import re
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

EnumWindowsProc = ctypes.WINFUNCTYPE(
    ctypes.wintypes.BOOL,
    ctypes.wintypes.HWND,
    ctypes.wintypes.LPARAM,
)

GAMING_KEYWORDS = [
    "game", "游戏", "BlueStacks", "MuMu", "雷电", "夜神", "逍遥",
    "Nox", "LDPlayer", "Memu", "Nemu",
    # BD2 (BrownDust II) runs as a native Windows window, not inside an
    # emulator. Without this keyword the discovery filter rejects the
    # BrownDust II window and the agent never adds it to DeviceManager,
    # so pipeline.execute falls back to the disconnected LDPlayer ADB device.
    "BrownDust",
]


class WindowDiscovery:
    """Windows 窗口自动发现：枚举窗口、按游戏关键词过滤、按进程分组"""

    def __init__(self):
        self._gamimg_keywords = list(GAMING_KEYWORDS)

    def add_gaming_keyword(self, keyword: str) -> None:
        """添加游戏窗口关键词

        Args:
            keyword: 游戏关键词
        """
        if keyword not in self._gamimg_keywords:
            self._gamimg_keywords.append(keyword)

    def enum_windows(self) -> list[int]:
        """枚举所有可见顶层窗口

        Returns:
            窗口句柄列表
        """
        hwnds: list[int] = []

        def _callback(hwnd: int, _lparam: int) -> bool:
            if user32.IsWindowVisible(hwnd):
                hwnds.append(hwnd)
            return True

        callback = EnumWindowsProc(_callback)
        user32.EnumWindows(callback, 0)
        return hwnds

    def get_window_title(self, hwnd: int) -> str:
        """获取窗口标题

        Args:
            hwnd: 窗口句柄

        Returns:
            窗口标题字符串
        """
        buf_len = user32.GetWindowTextLengthW(hwnd)
        if buf_len == 0:
            return ""
        buf = ctypes.create_unicode_buffer(buf_len + 1)
        user32.GetWindowTextW(hwnd, buf, buf_len + 1)
        return buf.value

    def get_process_name(self, hwnd: int) -> str:
        """根据窗口句柄获取进程名

        Args:
            hwnd: 窗口句柄

        Returns:
            进程名（如 'notepad.exe'）
        """
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return self._get_process_name_by_pid(pid.value)

    def get_window_rect(self, hwnd: int) -> dict[str, int] | None:
        """获取窗口矩形

        Args:
            hwnd: 窗口句柄

        Returns:
            {x, y, w, h} 字典，失败返回 None
        """
        rect = ctypes.wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return {
            "x": rect.left,
            "y": rect.top,
            "w": rect.right - rect.left,
            "h": rect.bottom - rect.top,
        }

    def get_all_windows_info(self) -> list[dict[str, Any]]:
        """获取所有窗口的详细信息

        Returns:
            窗口信息列表，每项包含 {hwnd, title, process_name, rect, class_name}
        """
        results: list[dict[str, Any]] = []
        for hwnd in self.enum_windows():
            try:
                title = self.get_window_title(hwnd)
                proc_name = self.get_process_name(hwnd)
                rect = self.get_window_rect(hwnd)
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                results.append({
                    "hwnd": hwnd,
                    "title": title,
                    "process_name": proc_name,
                    "rect": rect,
                    "class_name": cls_buf.value,
                    "group": proc_name,
                })
            except Exception as exc:
                logger.debug("窗口枚举异常 hwnd=%s: %s", hwnd, exc)
        return results

    def find_gaming_windows(self, keywords: list[str] | None = None) -> list[dict[str, Any]]:
        """发现游戏窗口（按关键词匹配标题或进程名）

        Args:
            keywords: 自定义关键词列表，默认使用内置游戏关键词

        Returns:
            游戏窗口信息列表，每项包含 {hwnd, title, process_name, rect, group}
        """
        search_keywords = keywords or self._gamimg_keywords
        all_windows = self.get_all_windows_info()
        gaming_windows: list[dict[str, Any]] = []

        for win in all_windows:
            title = win.get("title", "")
            proc = win.get("process_name", "")
            rect = win.get("rect")
            if rect is None:
                continue
            if rect.get("w", 0) < 200 or rect.get("h", 0) < 200:
                continue

            is_gaming = False
            for kw in search_keywords:
                if kw.lower() in title.lower() or kw.lower() in proc.lower():
                    is_gaming = True
                    break

            if is_gaming:
                gaming_windows.append(win)

        logger.info("发现 %d 个游戏窗口", len(gaming_windows))
        return gaming_windows

    def group_windows(
        self,
        windows: list[dict[str, Any]],
        key: str = "process",
        regex_pattern: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """按指定键分组窗口

        Args:
            windows: 窗口信息列表
            key: 分组键名（'process' 按进程名，'title' 按标题）
            regex_pattern: 正则表达式，根据标题匹配分组（key='title'时有效）

        Returns:
            分组字典 {组名: 窗口列表}
        """
        if key == "title" and regex_pattern:
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for win in windows:
                title = win.get("title", "")
                match = re.search(regex_pattern, title)
                if match:
                    group_name = match.group(1) if match.lastindex else match.group(0)
                    grouped[group_name].append(win)
                else:
                    grouped["unknown"].append(win)
            return dict(grouped)

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        field_name = "process_name" if key == "process" else "title"
        for win in windows:
            group_key = win.get(field_name, "unknown")
            grouped[group_key].append(win)
        return dict(grouped)

    @staticmethod
    def _get_process_name_by_pid(pid: int) -> str:
        """根据进程 ID 获取进程名

        Args:
            pid: 进程 ID

        Returns:
            进程名
        """
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
        )
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            if psapi.GetModuleBaseNameW(handle, None, buf, 260):
                return buf.value
            return ""
        finally:
            kernel32.CloseHandle(handle)
