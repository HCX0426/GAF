"""Agent 任务队列：管理待执行任务的排队和优先级"""

import heapq
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class TaskQueue:
    """Agent 任务队列，管理待执行任务的排队和优先级"""

    def __init__(self, max_concurrent: int = 1):
        """初始化任务队列

        Args:
            max_concurrent: 最大并发任务数（预留，当前仅支持串行）
        """
        self._max_concurrent = max_concurrent
        self._heap: list = []
        self._counter: int = 0
        self._lock = threading.Lock()

    def enqueue(self, task_definition: dict[str, Any], priority: int = 0) -> None:
        """入队任务

        优先级数字越小越先执行。相同优先级按入队顺序执行。

        Args:
            task_definition: 任务定义字典
            priority: 优先级（数字越小优先级越高）
        """
        with self._lock:
            self._counter += 1
            heapq.heappush(self._heap, (priority, self._counter, task_definition))
            logger.debug(
                "任务入队: priority=%d, counter=%d, 队列大小=%d",
                priority, self._counter, len(self._heap),
            )

    def dequeue(self) -> dict[str, Any] | None:
        """出队最高优先级任务

        Returns:
            任务定义字典，队列为空返回 None
        """
        with self._lock:
            if not self._heap:
                return None
            _, _, task_definition = heapq.heappop(self._heap)
            logger.debug("任务出队, 剩余队列大小=%d", len(self._heap))
            return task_definition

    def peek(self) -> dict[str, Any] | None:
        """查看队首任务（不出队）

        Returns:
            队首任务定义字典，队列为空返回 None
        """
        with self._lock:
            if not self._heap:
                return None
            _, _, task_definition = self._heap[0]
            return task_definition

    def is_empty(self) -> bool:
        """队列是否为空

        Returns:
            队列为空返回 True
        """
        with self._lock:
            return len(self._heap) == 0

    def size(self) -> int:
        """队列大小

        Returns:
            队列中任务数量
        """
        with self._lock:
            return len(self._heap)

    def clear(self) -> None:
        """清空队列"""
        with self._lock:
            self._heap.clear()
            self._counter = 0
            logger.debug("任务队列已清空")
