"""
任务录制引擎
捕获用户的鼠标/键盘操作和屏幕变化，生成录制数据
"""
import json
import logging
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ActionEvent:
    """单次操作事件"""
    event_type: str  # 'click' | 'key' | 'screenshot' | 'wait'
    timestamp: float = field(default_factory=time.time)
    x: int = 0
    y: int = 0
    button: str = 'left'
    key: str = ''
    screenshot_path: str = ''
    duration: float = 0.0


@dataclass
class RecordingData:
    """录制数据"""
    id: str = ''
    name: str = '未命名录制'
    created_at: str = ''
    duration: float = 0.0
    resolution: tuple = (1920, 1080)
    events: list = field(default_factory=list)
    screenshot_dir: str = ''

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at,
            'duration': self.duration,
            'resolution': list(self.resolution),
            'events': [
                {
                    'event_type': e.event_type,
                    'timestamp': e.timestamp,
                    'x': e.x,
                    'y': e.y,
                    'button': e.button,
                    'key': e.key,
                    'screenshot_path': e.screenshot_path,
                    'duration': e.duration,
                }
                for e in self.events
            ],
            'screenshot_dir': self.screenshot_dir,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'RecordingData':
        """从字典反序列化"""
        return cls(
            id=data.get('id', ''),
            name=data.get('name', '未命名录制'),
            created_at=data.get('created_at', ''),
            duration=data.get('duration', 0.0),
            resolution=tuple(data.get('resolution', [1920, 1080])),
            events=[
                ActionEvent(
                    event_type=e['event_type'],
                    timestamp=e.get('timestamp', 0),
                    x=e.get('x', 0),
                    y=e.get('y', 0),
                    button=e.get('button', 'left'),
                    key=e.get('key', ''),
                    screenshot_path=e.get('screenshot_path', ''),
                    duration=e.get('duration', 0),
                )
                for e in data.get('events', [])
            ],
            screenshot_dir=data.get('screenshot_dir', ''),
        )


class RecordingEngine:
    """任务录制引擎"""

    def __init__(self, screenshot_dir: str = './recordings/screenshots'):
        """初始化录制引擎

        Args:
            screenshot_dir: 截图保存目录
        """
        self.screenshot_dir = screenshot_dir
        self.recording: RecordingData | None = None
        self._start_time: float = 0
        self._screenshot_count = 0
        self._on_screenshot: Callable | None = None
        self._capture = None  # WindowsEventCapture instance (lazy import)
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def start(self, name: str = '未命名录制', resolution: tuple = (1920, 1080)):
        """开始录制

        Args:
            name: 录制名称
            resolution: 录制分辨率 (width, height)
        """
        self.recording = RecordingData(
            id=f'rec_{int(time.time() * 1000)}',
            name=name,
            created_at=datetime.now().isoformat(),
            resolution=resolution,
            screenshot_dir=self.screenshot_dir,
        )
        self._start_time = time.time()
        self._screenshot_count = 0
        logger.info(f"录制开始: {name}")

    def start_capture(
        self,
        capture_screenshots: bool = True,
        screenshot_interval: float = 2.0,
        screenshot_scale: float = 0.5,
    ) -> None:
        """Start global event capture (pynput listeners + screenshot thread).

        Must be called after start(). On non-Windows platforms this is a no-op
        with a warning (pynput listeners require a display server).

        Args:
            capture_screenshots: Whether to capture periodic screenshots.
            screenshot_interval: Seconds between screenshot captures.
            screenshot_scale: Downscale factor (0.5 = half resolution).
        """
        if not self.recording:
            logger.warning("start_capture() called before start() — ignoring")
            return

        if sys.platform != 'win32':
            logger.warning("Global event capture is only supported on Windows")
            return

        # Lazy import to avoid pynput dependency on non-Windows / test envs
        from platforms.windows.event_capture import WindowsEventCapture

        self._capture = WindowsEventCapture(
            recording_engine=self,
            capture_screenshots=capture_screenshots,
            screenshot_interval=screenshot_interval,
            screenshot_scale=screenshot_scale,
        )
        self._capture.start()

    def stop_capture(self) -> None:
        """Stop global event capture. Safe to call when capture not running."""
        if self._capture is not None:
            self._capture.stop()
            self._capture = None

    def stop(self) -> RecordingData | None:
        """停止录制并返回录制数据

        Returns:
            RecordingData 或 None（如果未在录制中）
        """
        # Stop global event capture first (if running)
        self.stop_capture()

        if not self.recording:
            return None
        self.recording.duration = time.time() - self._start_time
        result = self.recording
        self.recording = None
        logger.info(f"录制结束: {result.name}, 时长: {result.duration:.1f}s, 事件: {len(result.events)}")
        return result

    def record_click(self, x: int, y: int, button: str = 'left'):
        """记录鼠标点击事件

        Args:
            x: 点击 X 坐标
            y: 点击 Y 坐标
            button: 鼠标按钮 'left' | 'right' | 'middle'
        """
        if not self.recording:
            return
        self.recording.events.append(ActionEvent(
            event_type='click', x=x, y=y, button=button,
            timestamp=time.time() - self._start_time,
        ))

    def record_key(self, key: str):
        """记录键盘按键事件

        Args:
            key: 按键名称或键码
        """
        if not self.recording:
            return
        self.recording.events.append(ActionEvent(
            event_type='key', key=key,
            timestamp=time.time() - self._start_time,
        ))

    def record_screenshot(self, image_data: bytes):
        """记录截图事件

        Args:
            image_data: 截图 PNG 字节数据
        """
        if not self.recording:
            return
        self._screenshot_count += 1
        filename = f"{self.recording.id}_{self._screenshot_count:04d}.png"
        filepath = os.path.join(self.screenshot_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(image_data)
        self.recording.events.append(ActionEvent(
            event_type='screenshot', screenshot_path=filepath,
            timestamp=time.time() - self._start_time,
        ))

    def record_wait(self, duration: float):
        """记录等待事件

        Args:
            duration: 等待时长（秒）
        """
        if not self.recording:
            return
        self.recording.events.append(ActionEvent(
            event_type='wait', duration=duration,
            timestamp=time.time() - self._start_time,
        ))

    def save(self, filepath: str):
        """保存录制数据到 .gafrecord 文件（JSON 格式）

        Args:
            filepath: 保存路径，建议使用 .gafrecord 扩展名
        """
        if not self.recording:
            return
        data = self.recording.to_dict()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"录制保存到: {filepath}")

    @staticmethod
    def load(filepath: str) -> RecordingData:
        """从 .gafrecord 文件加载录制数据

        Args:
            filepath: 录制文件路径

        Returns:
            RecordingData 实例
        """
        with open(filepath, encoding='utf-8') as f:
            data = json.load(f)
        return RecordingData.from_dict(data)
