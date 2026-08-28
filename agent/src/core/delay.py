"""延迟管理：带中断检查的延迟"""

import logging
import threading

logger = logging.getLogger(__name__)


class DelayManager:
    """使用 threading.Event.wait 替代 time.sleep，支持中断"""

    def __init__(self):
        self._interrupt_event = threading.Event()
        self._wait_event = threading.Event()

    def wait(self, seconds: float) -> bool:
        """等待指定秒数，可被中断提前返回

        Returns:
            True 表示正常等待完成，False 表示被中断
        """
        if seconds <= 0:
            return True

        self._interrupt_event.clear()
        interrupted = self._interrupt_event.wait(timeout=seconds)
        if interrupted:
            logger.debug("延迟被中断，剩余时间已跳过")
            return False
        return True

    def interrupt(self) -> None:
        """中断当前等待"""
        self._interrupt_event.set()

    def reset(self) -> None:
        """重置中断状态"""
        self._interrupt_event.clear()
