import contextlib
import json
import logging
import socket
import time
from typing import Any

from core.exceptions import DeviceError
from core.retry import retry_input
from devices.base import BaseDevice, require_operable

from .adb_constants import ADB_INPUT, HERMIT_INPUT, MAATOUCH_INPUT, MINITOUCH_INPUT, NEMU_IPC_INPUT, U2_INPUT

logger = logging.getLogger(__name__)


class ADBInputMixin(BaseDevice):
    """ADBDevice mixin — see devices/adb/device.py for full class (s36 split)."""

    @require_operable
    def click(self, x: int, y: int) -> None:
        """ADB 点击（MaaTouch→NemuIpc→minitouch→u2→Hermit→adb input 降级链）

        坐标系契约 (N191): 期望 **physical** (raw pixel) 坐标。
        ADB 设备不注入 coord_transformer (transformer 是 Windows 专属),
        publish_match_pos 在 ADB 场景下输出 raw physical 像素, 与本方法契约一致。
        无 DPI 转换, 直接传给底层 ADB 命令。

        Args:
            x: 点击 X 坐标 (physical pixel)
            y: 点击 Y 坐标 (physical pixel)
        """
        if self._input_method != "auto":
            self._click_by_method(self._input_method, x, y)
            return

        if self._best_click_method:
            try:
                self._click_by_method(self._best_click_method, x, y)
                return
            except Exception:
                self._best_click_method = None

        fallback_order = [
            NEMU_IPC_INPUT, MAATOUCH_INPUT, MINITOUCH_INPUT,
            U2_INPUT, HERMIT_INPUT, ADB_INPUT,
        ]
        for method in fallback_order:
            try:
                self._click_by_method(method, x, y)
                self._best_click_method = method
                return
            except Exception as exc:
                logger.warning("点击方法 %s 失败: %s", method, exc)

        raise DeviceError("所有点击方法均失败")

    @require_operable
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> None:
        """ADB 滑动（MaaTouch→NemuIpc→minitouch→u2→adb input 降级链）

        坐标系契约 (N191): 期望 **physical** (raw pixel) 坐标, 同 ``click()``。
        ADB 设备不注入 coord_transformer, 上游 swipe 节点用
        ``ADBCoordinateTransformer.convert_original_to_current_client`` 把 BASE
        坐标缩放到 device.get_resolution() 对应的 physical 像素。
        无 DPI 转换, 直接传给底层 ADB 命令。

        Args:
            x1: 起始 X 坐标 (physical pixel)
            y1: 起始 Y 坐标 (physical pixel)
            x2: 终止 X 坐标 (physical pixel)
            y2: 终止 Y 坐标 (physical pixel)
            duration: 滑动持续时间（毫秒），默认 300ms
        """
        if self._input_method != "auto":
            self._swipe_by_method(self._input_method, x1, y1, x2, y2, duration)
            return

        if self._best_swipe_method:
            try:
                self._swipe_by_method(self._best_swipe_method, x1, y1, x2, y2, duration)
                return
            except Exception:
                self._best_swipe_method = None

        fallback_order = [
            NEMU_IPC_INPUT, MAATOUCH_INPUT, MINITOUCH_INPUT,
            U2_INPUT, ADB_INPUT,
        ]
        for method in fallback_order:
            try:
                self._swipe_by_method(method, x1, y1, x2, y2, duration)
                self._best_swipe_method = method
                return
            except Exception as exc:
                logger.warning("滑动方法 %s 失败: %s", method, exc)

        raise DeviceError("所有滑动方法均失败")

    @require_operable
    def key_press(self, key: str) -> None:
        """ADB 按键（MaaTouch→u2→adb input 降级链）

        Args:
            key: Android keycode 名称或数字
        """
        if self._input_method != "auto":
            self._key_press_by_method(self._input_method, key)
            return

        if self._best_key_method:
            try:
                self._key_press_by_method(self._best_key_method, key)
                return
            except Exception:
                self._best_key_method = None

        fallback_order = [MAATOUCH_INPUT, U2_INPUT, ADB_INPUT]
        for method in fallback_order:
            try:
                self._key_press_by_method(method, key)
                self._best_key_method = method
                return
            except Exception as exc:
                logger.warning("按键方法 %s 失败: %s", method, exc)

        raise DeviceError("所有按键方法均失败")

    @require_operable
    def text_input(self, text: str) -> None:
        """ADB 文本输入（使用 adb shell input text，自动转义特殊字符）

        Args:
            text: 输入的文本内容
        """
        if not self._device:
            raise DeviceError("ADB 设备未连接")
        escaped = text.replace(" ", "%s").replace("&", "\\&").replace("<", "\\<").replace(">", "\\>").replace("(", "\\(").replace(")", "\\)")
        self._device.shell(f"input text {escaped}")
        logger.debug("ADB 文本输入: %s", text[:20])

    def _click_by_method(self, method: str, x: int, y: int) -> None:
        """根据指定方法执行点击

        Args:
            method: 输入方法名称
            x: 点击 X 坐标
            y: 点击 Y 坐标
        """
        if method == NEMU_IPC_INPUT:
            self._input_nemu_ipc_click(x, y)
        elif method == MAATOUCH_INPUT:
            self._input_maatouch_click(x, y)
        elif method == MINITOUCH_INPUT:
            self._input_minitouch_click(x, y)
        elif method == U2_INPUT:
            self._input_u2_click(x, y)
        elif method == HERMIT_INPUT:
            self._input_hermit_click(x, y)
        elif method == ADB_INPUT:
            self._input_adb_click(x, y)
        else:
            logger.warning("未知输入方法: %s，降级到 adb input", method)
            self._input_adb_click(x, y)

    def _swipe_by_method(self, method: str, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> None:
        """根据指定方法执行滑动

        Args:
            method: 输入方法名称
            x1: 起始 X 坐标
            y1: 起始 Y 坐标
            x2: 终止 X 坐标
            y2: 终止 Y 坐标
            duration: 滑动持续时间（毫秒）
        """
        if method == NEMU_IPC_INPUT:
            self._input_nemu_ipc_swipe(x1, y1, x2, y2, duration)
        elif method == MAATOUCH_INPUT:
            self._input_maatouch_swipe(x1, y1, x2, y2, duration)
        elif method == MINITOUCH_INPUT:
            self._input_minitouch_swipe(x1, y1, x2, y2, duration)
        elif method == U2_INPUT:
            self._input_u2_swipe(x1, y1, x2, y2, duration)
        elif method == ADB_INPUT:
            self._input_adb_swipe(x1, y1, x2, y2, duration)
        else:
            logger.warning("未知输入方法: %s，降级到 adb input", method)
            self._input_adb_swipe(x1, y1, x2, y2, duration)

    def _key_press_by_method(self, method: str, key: str) -> None:
        """根据指定方法执行按键

        Args:
            method: 输入方法名称
            key: 按键名称或数字
        """
        if method == MAATOUCH_INPUT:
            self._input_maatouch_key_press(key)
        elif method == U2_INPUT:
            self._input_u2_key_press(key)
        elif method == ADB_INPUT:
            self._input_adb_key_press(key)
        else:
            logger.warning("未知输入方法: %s，降级到 adb input", method)
            self._input_adb_key_press(key)

    @retry_input()
    def _input_maatouch_click(self, x: int, y: int) -> None:
        """使用 MaaTouch 执行点击

        Args:
            x: 点击 X 坐标
            y: 点击 Y 坐标
        """
        try:
            controller = self._get_maatouch_controller()
            controller.click(x, y)
            logger.debug("MaaTouch 点击: (%d, %d)", x, y)
        except ImportError as exc:
            raise NotImplementedError("MaaTouch 库未安装，请安装 MaaTouch") from exc
        except Exception as exc:
            self._maatouch_controller = None
            raise RuntimeError(f"MaaTouch 点击失败: {exc}") from exc

    @retry_input()
    def _input_maatouch_key_press(self, key: str) -> None:
        """MaaTouch 无按键能力 — 显式降级到下一方法 (2026-09-05).

        此前 _key_press_by_method 引用不存在的 _input_maatouch_key_press,
        抛 AttributeError 被当作普通失败, 掩盖了真正的降级链语义.
        """
        raise NotImplementedError("MaaTouch 不支持按键，降级到 u2/adb input")

    @retry_input()
    def _input_maatouch_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> None:
        """使用 MaaTouch 执行滑动

        Args:
            x1: 起始 X 坐标
            y1: 起始 Y 坐标
            x2: 终止 X 坐标
            y2: 终止 Y 坐标
            duration: 滑动持续时间（毫秒）
        """
        try:
            controller = self._get_maatouch_controller()
            duration_sec = duration / 1000.0
            controller.swipe(x1, y1, x2, y2, duration=duration_sec)
            logger.debug("MaaTouch 滑动: (%d,%d) -> (%d,%d)", x1, y1, x2, y2)
        except ImportError as exc:
            raise NotImplementedError("MaaTouch 库未安装，请安装 MaaTouch") from exc
        except Exception as exc:
            self._maatouch_controller = None
            raise RuntimeError(f"MaaTouch 滑动失败: {exc}") from exc

    @retry_input()
    def _input_adb_click(self, x: int, y: int) -> None:
        """使用 adb shell input 命令执行点击

        Args:
            x: 点击 X 坐标
            y: 点击 Y 坐标
        """
        if not self._device:
            raise DeviceError("ADB 设备未连接")
        self._device.click(x, y)
        logger.debug("ADB 点击: (%d, %d)", x, y)

    @retry_input()
    def _input_adb_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> None:
        """使用 adb shell input 命令执行滑动

        Args:
            x1: 起始 X 坐标
            y1: 起始 Y 坐标
            x2: 终止 X 坐标
            y2: 终止 Y 坐标
            duration: 滑动持续时间（毫秒）
        """
        if not self._device:
            raise DeviceError("ADB 设备未连接")
        duration_sec = duration / 1000.0
        self._device.swipe(x1, y1, x2, y2, duration=duration_sec)
        logger.debug("ADB 滑动: (%d,%d) -> (%d,%d)", x1, y1, x2, y2)

    @retry_input()
    def _input_adb_key_press(self, key: str) -> None:
        """使用 adb shell input 命令执行按键

        Args:
            key: 按键名称或数字
        """
        if not self._device:
            raise DeviceError("ADB 设备未连接")
        keycode = self._resolve_keycode(key)
        self._device.keyevent(keycode)
        logger.debug("ADB 按键: %s (keycode=%d)", key, keycode)

    @retry_input()
    def _input_minitouch_click(self, x: int, y: int) -> None:
        """使用 minitouch 执行点击

        通过 socket 发送 touch down + commit + touch up + commit 指令。

        Args:
            x: 点击 X 坐标
            y: 点击 Y 坐标
        """
        try:
            sock = self._get_minitouch_socket()
            # minitouch protocol: d <contact> <x> <y> <pressure>\nc\nu <contact>\nc\n
            cmd = f"d 0 {x} {y} 50\nc\nu 0\nc\n"
            sock.sendall(cmd.encode("utf-8"))
            logger.debug("minitouch 点击: (%d, %d)", x, y)
        except DeviceError:
            raise
        except Exception as exc:
            self._minitouch_socket = None
            raise RuntimeError(f"minitouch 点击失败: {exc}") from exc

    @retry_input()
    def _input_minitouch_swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration: int = 300
    ) -> None:
        """使用 minitouch 执行滑动

        通过 socket 发送一系列 touch down/move/up 指令模拟滑动。

        Args:
            x1: 起始 X 坐标
            y1: 起始 Y 坐标
            x2: 终止 X 坐标
            y2: 终止 Y 坐标
            duration: 滑动持续时间（毫秒）
        """
        try:
            sock = self._get_minitouch_socket()
            steps = max(2, duration // 20)
            delay_per_step = max(0.005, duration / 1000.0 / steps)

            # Send down at start position.
            sock.sendall(f"d 0 {x1} {y1} 50\nc\n".encode())
            # Send move events with one sleep per step (not two).
            for i in range(1, steps + 1):
                ratio = i / steps
                cx = int(x1 + (x2 - x1) * ratio)
                cy = int(y1 + (y2 - y1) * ratio)
                sock.sendall(f"m 0 {cx} {cy} 50\nc\n".encode())
                time.sleep(delay_per_step)
            # Send up at end position.
            sock.sendall(b"u 0\nc\n")
            logger.debug("minitouch 滑动: (%d,%d) -> (%d,%d)", x1, y1, x2, y2)
        except DeviceError:
            raise
        except Exception as exc:
            self._minitouch_socket = None
            raise RuntimeError(f"minitouch 滑动失败: {exc}") from exc

    def _get_u2_device(self) -> Any:
        """获取或初始化 uiautomator2 设备实例"""
        if self._u2_device is not None:
            return self._u2_device
        try:
            import uiautomator2 as u2
        except ImportError as exc:
            raise NotImplementedError(
                "uiautomator2 库未安装，请安装 uiautomator2"
            ) from exc
        self._u2_device = u2.connect(self._serial)
        return self._u2_device

    @retry_input()
    def _input_u2_click(self, x: int, y: int) -> None:
        """使用 uiautomator2 执行点击

        Args:
            x: 点击 X 坐标
            y: 点击 Y 坐标
        """
        try:
            device = self._get_u2_device()
            device.click(x, y)
            logger.debug("u2 点击: (%d, %d)", x, y)
        except NotImplementedError:
            raise
        except Exception as exc:
            self._u2_device = None
            raise RuntimeError(f"u2 点击失败: {exc}") from exc

    @retry_input()
    def _input_u2_swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration: int = 300
    ) -> None:
        """使用 uiautomator2 执行滑动

        Args:
            x1: 起始 X 坐标
            y1: 起始 Y 坐标
            x2: 终止 X 坐标
            y2: 终止 Y 坐标
            duration: 滑动持续时间（毫秒）
        """
        try:
            device = self._get_u2_device()
            duration_sec = duration / 1000.0
            device.swipe(x1, y1, x2, y2, duration=duration_sec)
            logger.debug("u2 滑动: (%d,%d) -> (%d,%d)", x1, y1, x2, y2)
        except NotImplementedError:
            raise
        except Exception as exc:
            self._u2_device = None
            raise RuntimeError(f"u2 滑动失败: {exc}") from exc

    @retry_input()
    def _input_u2_key_press(self, key: str) -> None:
        """使用 uiautomator2 执行按键

        Args:
            key: 按键名称或数字
        """
        try:
            device = self._get_u2_device()
            keycode = self._resolve_keycode(key)
            # u2 uses Android keycode names like "home", "back"; press_key accepts int or str
            device.press_keycode(keycode)
            logger.debug("u2 按键: %s (keycode=%d)", key, keycode)
        except NotImplementedError:
            raise
        except Exception as exc:
            self._u2_device = None
            raise RuntimeError(f"u2 按键失败: {exc}") from exc

    def _get_hermit_session(self) -> Any:
        """获取或初始化 Hermit HTTP session

        通过 adb forward 将设备端 9999 端口映射到本地，建立 requests.Session。
        """
        if self._hermit_session is not None:
            return self._hermit_session
        if not self._device:
            raise DeviceError("ADB 设备未连接")
        try:
            import requests
        except ImportError as exc:
            raise NotImplementedError(
                "Hermit 输入需要 requests 库，请安装 requests"
            ) from exc

        # Forward local port to device's Hermit HTTP port (9999)
        local_port = self._hermit_port
        self._device.forward(f"tcp:{local_port}", "tcp:9999")
        self._forwarded_local_ports.add(local_port)

        session = requests.Session()
        session.trust_env = False  # Ignore system proxy
        self._hermit_session = session
        return session

    def _hermit_send(self, path: str, **params: Any) -> dict[str, Any]:
        """Send a GET request to Hermit HTTP API.

        Args:
            path: API path, e.g. "/click"
            **params: Query parameters (x, y, etc.)

        Returns:
            Parsed JSON response dict, usually {"code": 0, "msg": "ok"}

        Raises:
            RuntimeError: If Hermit returns an error code or invalid JSON
        """
        session = self._get_hermit_session()
        url = f"http://127.0.0.1:{self._hermit_port}{path}"
        try:
            response = session.get(url, params=params, timeout=3)
            result = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Hermit 返回非 JSON 响应: {response.text[:200]}") from exc
        except Exception as exc:
            self._hermit_session = None
            raise RuntimeError(f"Hermit 请求失败: {exc}") from exc

        if result.get("code") != 0:
            raise RuntimeError(f"Hermit 错误响应: {result}")

        # Hermit dispatch takes 2-4ms; add 50ms for game to react
        time.sleep(0.05)
        return result

    @retry_input()
    def _input_hermit_click(self, x: int, y: int) -> None:
        """使用 Hermit 执行点击（HTTP API on port 9999）

        Args:
            x: 点击 X 坐标
            y: 点击 Y 坐标
        """
        self._hermit_send("/click", x=x, y=y)
        logger.debug("Hermit 点击: (%d, %d)", x, y)

    def _nemu_ipc_convert_xy(self, x: int, y: int) -> tuple[int, int]:
        """Convert ADB coordinates to NemuIpc coordinates.

        NemuIpc uses a rotated coordinate system: (height - y, x).

        Returns:
            (nemu_x, nemu_y) tuple
        """
        if self._nemu_ipc_height == 0:
            self._nemu_ipc_get_resolution()
        return self._nemu_ipc_height - int(y), int(x)

    @retry_input()
    def _input_nemu_ipc_click(self, x: int, y: int) -> None:
        """使用 NemuIpc 执行点击（nemu_input_event_touch_down + up）

        Args:
            x: 点击 X 坐标
            y: 点击 Y 坐标
        """
        try:

            if self._nemu_ipc_connect_id == 0:
                self._nemu_ipc_connect()
            lib = self._load_nemu_ipc_lib()

            nx, ny = self._nemu_ipc_convert_xy(x, y)
            ret = lib.nemu_input_event_touch_down(
                self._nemu_ipc_connect_id,
                0,  # display_id
                nx,
                ny,
            )
            if ret != 0:
                from platforms.windows.nemu_ipc_errors import format_nemu_error
                raise RuntimeError(
                    format_nemu_error(ret, context="nemu_input_event_touch_down")
                )

            # Hold for 10-20ms then release
            time.sleep(0.015)
            ret = lib.nemu_input_event_touch_up(
                self._nemu_ipc_connect_id,
                0,  # display_id
            )
            if ret != 0:
                from platforms.windows.nemu_ipc_errors import format_nemu_error
                raise RuntimeError(
                    format_nemu_error(ret, context="nemu_input_event_touch_up")
                )
            time.sleep(0.05)
            logger.debug("NemuIpc 点击: (%d, %d) -> nemu(%d, %d)", x, y, nx, ny)
        except NotImplementedError:
            raise
        except Exception as exc:
            self._nemu_ipc_disconnect()
            raise RuntimeError(f"NemuIpc 点击失败: {exc}") from exc

    @retry_input()
    def _input_nemu_ipc_swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration: int = 300
    ) -> None:
        """使用 NemuIpc 执行滑动（连续 touch_down 模拟 swipe）

        Args:
            x1: 起始 X 坐标
            y1: 起始 Y 坐标
            x2: 终止 X 坐标
            y2: 终止 Y 坐标
            duration: 滑动持续时间（毫秒）
        """
        try:
            if self._nemu_ipc_connect_id == 0:
                self._nemu_ipc_connect()
            lib = self._load_nemu_ipc_lib()

            steps = max(2, duration // 20)
            delay_per_step = max(0.005, duration / 1000.0 / steps)

            for i in range(steps + 1):
                ratio = i / steps
                cx = int(x1 + (x2 - x1) * ratio)
                cy = int(y1 + (y2 - y1) * ratio)
                nx, ny = self._nemu_ipc_convert_xy(cx, cy)
                ret = lib.nemu_input_event_touch_down(
                    self._nemu_ipc_connect_id,
                    0,  # display_id
                    nx,
                    ny,
                )
                if ret != 0:
                    from platforms.windows.nemu_ipc_errors import format_nemu_error
                    raise RuntimeError(
                        format_nemu_error(
                            ret, context="nemu_input_event_touch_down(swipe)"
                        )
                    )
                time.sleep(delay_per_step)

            ret = lib.nemu_input_event_touch_up(
                self._nemu_ipc_connect_id,
                0,  # display_id
            )
            if ret != 0:
                from platforms.windows.nemu_ipc_errors import format_nemu_error
                raise RuntimeError(
                    format_nemu_error(
                        ret, context="nemu_input_event_touch_up(swipe)"
                    )
                )
            time.sleep(0.05)
            logger.debug("NemuIpc 滑动: (%d,%d) -> (%d,%d)", x1, y1, x2, y2)
        except NotImplementedError:
            raise
        except Exception as exc:
            self._nemu_ipc_disconnect()
            raise RuntimeError(f"NemuIpc 滑动失败: {exc}") from exc

    def _get_maatouch_controller(self) -> Any:
        """获取或初始化 MaaTouch 控制器

        Returns:
            MaaTouch 控制器实例
        """
        if self._maatouch_controller is not None:
            return self._maatouch_controller

        from MaaTouch import Controller as MaaTouchController

        self._maatouch_controller = MaaTouchController(self._serial)
        return self._maatouch_controller

    @staticmethod
    def _resolve_keycode(key: str) -> int:
        """将按键名称解析为 Android keycode

        Args:
            key: 按键名称或数字字符串

        Returns:
            Android keycode 整数值
        """
        key_map = {
            "home": 3, "back": 4, "menu": 82,
            "enter": 66, "delete": 67, "del": 67, "backspace": 67,
            "tab": 61, "space": 62,
            "up": 19, "down": 20, "left": 21, "right": 22,
            "volume_up": 24, "volume_down": 25,
            "power": 26, "wake_up": 224,
            "escape": 111, "shift": 59, "ctrl": 113,
            "f1": 131, "f2": 132, "f3": 133, "f4": 134,
            "f5": 135, "f6": 136, "f7": 137, "f8": 138,
            "f9": 139, "f10": 140, "f11": 141, "f12": 142,
        }
        key_lower = key.lower()
        if key_lower in key_map:
            return key_map[key_lower]
        # Single letter a-z → Android keycode 29-54
        if len(key_lower) == 1 and 'a' <= key_lower <= 'z':
            return ord(key_lower) - ord('a') + 29
        # Single digit 0-9 → Android keycode 7-16
        if len(key_lower) == 1 and '0' <= key_lower <= '9':
            return ord(key_lower) - ord('0') + 7
        try:
            return int(key)
        except ValueError:
            logger.warning("未知按键: %s，使用 KEYCODE_UNKNOWN(0)", key)
            return 0

    def _get_minitouch_socket(self) -> socket.socket:
        """获取或初始化 minitouch 的 socket 连接

        通过 adb forward 将本地端口映射到 minitouch 的 Unix socket，
        建立 TCP 连接用于发送触摸事件

        Returns:
            已连接的 socket 对象
        """
        if self._minitouch_socket is not None:
            try:
                # Use non-blocking recv with MSG_PEEK to detect a closed peer.
                # sendall(b"") is a no-op and never reports a closed socket.
                self._minitouch_socket.setblocking(False)
                try:
                    data = self._minitouch_socket.recv(1, socket.MSG_PEEK)
                    if data == b"":
                        # Peer closed the connection. Close the stale socket to
                        # release its file descriptor before discarding the
                        # reference, otherwise the fd leaks until GC runs.
                        with contextlib.suppress(OSError):
                            self._minitouch_socket.close()
                        self._minitouch_socket = None
                    else:
                        self._minitouch_socket.setblocking(True)
                        return self._minitouch_socket
                except BlockingIOError:
                    # No data available but connection is still alive.
                    self._minitouch_socket.setblocking(True)
                    return self._minitouch_socket
                except OSError:
                    # Socket is in an unrecoverable state. Close it to release
                    # the file descriptor before clearing the reference.
                    with contextlib.suppress(OSError):
                        self._minitouch_socket.close()
                    self._minitouch_socket = None
            except Exception:
                # Unexpected failure: still close the socket to avoid leaking
                # the file descriptor when we discard the reference below.
                with contextlib.suppress(Exception):
                    self._minitouch_socket.close()
                self._minitouch_socket = None

        if not self._device:
            raise DeviceError("ADB 设备未连接")

        local_port = 11111
        self._device.forward(f"tcp:{local_port}", "localabstract:minitouch")
        self._forwarded_local_ports.add(local_port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(("127.0.0.1", local_port))

        banner = sock.recv(1024).decode("utf-8", errors="ignore")
        logger.debug("minitouch banner: %s", banner.strip())

        self._minitouch_socket = sock
        return sock
