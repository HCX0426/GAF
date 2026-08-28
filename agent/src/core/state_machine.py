"""状态机任务执行引擎：根据界面状态决策下一步操作"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.result import AutoResult, fail_result, success_result

if TYPE_CHECKING:
    from devices.manager import DeviceManager
    from image.processor import ImageProcessor

logger = logging.getLogger(__name__)

DEFAULT_STUCK_THRESHOLD = 3
DEFAULT_RESULT_CACHE_SIZE = 64

_CACHE_MISS = object()


@dataclass
class StateTransition:
    """状态转移，定义从当前状态到目标状态的条件"""
    target: str
    condition: Callable[[Any | None], bool]
    priority: int = 0

    def __post_init__(self):
        """校验转移参数"""
        if not self.target:
            raise ValueError("目标状态名不能为空")
        if not callable(self.condition):
            raise ValueError("转移条件必须是可调用对象")


@dataclass
class StateNode:
    """状态节点，定义一个界面状态及其对应的操作和转移条件"""
    name: str
    action: Callable[[], Any]
    transitions: list[StateTransition] = field(default_factory=list)
    on_enter: Callable[[], None] | None = None
    on_exit: Callable[[], None] | None = None
    is_terminal: bool = False
    stuck_threshold: int = DEFAULT_STUCK_THRESHOLD
    on_stuck: Callable[[], Any] | None = None

    def __post_init__(self):
        """校验节点参数"""
        if not self.name:
            raise ValueError("状态名称不能为空")
        if not callable(self.action):
            raise ValueError("状态动作必须是可调用对象")
        self.transitions.sort(key=lambda t: t.priority)


class StateMachine:
    """状态机任务执行引擎：根据界面状态决策下一步操作

    特性：
    - 界面卡顿检测与自动重试：同一状态连续未转移超过阈值时触发 on_stuck 回调
    - 识别结果缓存：同一截图内容不重复执行识别
    """

    def __init__(
        self,
        device_manager: DeviceManager,
        image_processor: ImageProcessor,
        result_cache_size: int = DEFAULT_RESULT_CACHE_SIZE,
    ):
        self._device_manager = device_manager
        self._image_processor = image_processor
        self._states: dict[str, StateNode] = {}
        self._current_state: str | None = None
        self._initial_state: str | None = None
        self._stop_event = threading.Event()
        self._history: list[dict[str, Any]] = []
        self._iteration_count: int = 0
        self._stuck_counters: dict[str, int] = {}
        self._result_cache: OrderedDict = OrderedDict()
        self._result_cache_size = result_cache_size

    def add_state(self, node: StateNode) -> None:
        """添加状态节点到状态机

        Args:
            node: 状态节点实例
        """
        if node.name in self._states:
            logger.warning("状态 %s 已存在，将被覆盖", node.name)
        self._states[node.name] = node
        logger.debug("已添加状态节点: %s", node.name)

    def set_initial_state(self, name: str) -> None:
        """设置初始状态

        Args:
            name: 初始状态名称

        Raises:
            ValueError: 状态不存在时抛出
        """
        if name not in self._states:
            raise ValueError(f"状态 {name} 不存在，请先添加该状态")
        self._initial_state = name
        logger.debug("初始状态已设置: %s", name)

    def run(self, max_iterations: int = 1000) -> AutoResult:
        """执行状态机循环

        流程：
        1. 截图
        2. 检查当前状态的转移条件（带识别结果缓存）
        3. 如果条件满足，转移到新状态（重置卡顿计数器）
        4. 如果条件不满足，增加卡顿计数器，超阈值触发 on_stuck
        5. 执行当前状态的操作
        6. 检查是否到达终态
        7. 支持中断检查（stop_event）

        Args:
            max_iterations: 最大迭代次数，防止无限循环

        Returns:
            AutoResult 执行结果
        """
        if self._initial_state is None:
            return fail_result(error_msg="未设置初始状态")

        self._current_state = self._initial_state
        self._stop_event.clear()
        self._history.clear()
        self._iteration_count = 0
        self._stuck_counters.clear()
        self._result_cache.clear()
        start_time = time.monotonic()

        self._enter_state(self._current_state)

        while self._iteration_count < max_iterations:
            if self._stop_event.is_set():
                elapsed = time.monotonic() - start_time
                return fail_result(
                    error_msg="状态机被手动停止",
                    data=self._history,
                    elapsed_time=elapsed,
                    is_interrupted=True,
                )

            self._iteration_count += 1
            current_node = self._states.get(self._current_state)
            if current_node is None:
                elapsed = time.monotonic() - start_time
                return fail_result(
                    error_msg=f"当前状态 {self._current_state} 不存在",
                    data=self._history,
                    elapsed_time=elapsed,
                )

            screenshot = self._take_screenshot()

            transitioned = self._check_transitions(current_node, screenshot)
            if transitioned:
                self._stuck_counters[self._current_state] = 0
                continue

            stuck_count = self._stuck_counters.get(self._current_state, 0) + 1
            self._stuck_counters[self._current_state] = stuck_count

            if stuck_count >= current_node.stuck_threshold:
                logger.warning(
                    "状态 %s 卡顿检测触发 (stuck_count=%d >= threshold=%d)",
                    current_node.name, stuck_count, current_node.stuck_threshold,
                )
                self._record_history(current_node.name, "stuck_detected", {
                    "stuck_count": stuck_count,
                    "threshold": current_node.stuck_threshold,
                })

                if current_node.on_stuck and callable(current_node.on_stuck):
                    try:
                        stuck_result = current_node.on_stuck()
                        self._record_history(current_node.name, "stuck_handler", stuck_result)
                        logger.info("状态 %s 卡顿处理回调已执行", current_node.name)
                    except Exception as exc:
                        logger.error("状态 %s 卡顿处理回调异常: %s", current_node.name, exc)

                self._stuck_counters[self._current_state] = 0

            try:
                action_result = current_node.action()
                self._record_history(current_node.name, "action", action_result)
            except Exception as exc:
                logger.error("状态 %s 动作执行异常: %s", current_node.name, exc)
                self._record_history(current_node.name, "action_error", str(exc))

            if current_node.is_terminal:
                elapsed = time.monotonic() - start_time
                logger.info("到达终态 %s，状态机结束", current_node.name)
                return success_result(
                    data=self._history,
                    elapsed_time=elapsed,
                )

        elapsed = time.monotonic() - start_time
        return fail_result(
            error_msg=f"状态机超过最大迭代次数 {max_iterations}",
            data=self._history,
            elapsed_time=elapsed,
        )

    def stop(self) -> None:
        """停止状态机"""
        self._stop_event.set()
        logger.info("状态机停止信号已发送")

    def get_current_state(self) -> str:
        """获取当前状态名

        Returns:
            当前状态名称
        """
        return self._current_state or ""

    def get_execution_history(self) -> list[dict[str, Any]]:
        """获取执行历史

        Returns:
            执行历史列表
        """
        return list(self._history)

    def _take_screenshot(self) -> Any | None:
        """截取当前屏幕画面

        Returns:
            截图数据，失败返回 None
        """
        try:
            device = self._device_manager.get_active_device()
            if device:
                return device.capture_screen()
        except Exception as exc:
            logger.warning("截图失败: %s", exc)
        return None

    def _check_transitions(self, node: StateNode, screenshot: Any | None) -> bool:
        """检查并执行状态转移（带识别结果缓存）

        对同一截图内容，缓存转移条件的识别结果，
        避免同一截图重复执行模板匹配等耗时操作

        Args:
            node: 当前状态节点
            screenshot: 当前截图

        Returns:
            是否发生了状态转移
        """
        for transition in node.transitions:
            try:
                cache_key = self._make_cache_key(node.name, transition.target, screenshot)
                cached = self._get_cached_result(cache_key)
                if cached is not _CACHE_MISS:
                    condition_met = cached
                else:
                    condition_met = transition.condition(screenshot)
                    self._set_cached_result(cache_key, condition_met)

                if condition_met:
                    old_state = self._current_state
                    self._exit_state(old_state)
                    self._current_state = transition.target
                    self._enter_state(self._current_state)
                    self._record_history(old_state, f"transition->{transition.target}", None)
                    logger.info("状态转移: %s -> %s", old_state, transition.target)
                    return True
            except Exception as exc:
                logger.warning(
                    "转移条件 %s->%s 检查异常: %s",
                    node.name, transition.target, exc,
                )
        return False

    def _make_cache_key(self, state_name: str, target_name: str, screenshot: Any | None) -> str:
        """生成识别结果缓存键

        Args:
            state_name: 当前状态名
            target_name: 目标状态名
            screenshot: 截图数据

        Returns:
            缓存键字符串
        """
        if screenshot is not None and hasattr(screenshot, 'tobytes'):
            img_hash = hashlib.md5(screenshot.tobytes()).hexdigest()[:12]
        else:
            img_hash = "none"
        return f"{state_name}:{target_name}:{img_hash}"

    def _get_cached_result(self, key: str) -> Any:
        """从缓存中获取识别结果

        Args:
            key: 缓存键

        Returns:
            缓存的布尔结果，未命中返回 _CACHE_MISS 哨兵
        """
        if key in self._result_cache:
            self._result_cache.move_to_end(key)
            return self._result_cache[key]
        return _CACHE_MISS

    def _set_cached_result(self, key: str, result: bool) -> None:
        """设置识别结果缓存

        Args:
            key: 缓存键
            result: 识别结果
        """
        self._result_cache[key] = result
        if len(self._result_cache) > self._result_cache_size:
            oldest = next(iter(self._result_cache))
            del self._result_cache[oldest]

    def _enter_state(self, state_name: str) -> None:
        """进入状态的回调处理

        Args:
            state_name: 状态名称
        """
        node = self._states.get(state_name)
        if node and node.on_enter:
            try:
                node.on_enter()
            except Exception as exc:
                logger.warning("状态 %s on_enter 回调异常: %s", state_name, exc)

    def _exit_state(self, state_name: str) -> None:
        """离开状态的回调处理

        Args:
            state_name: 状态名称
        """
        node = self._states.get(state_name)
        if node and node.on_exit:
            try:
                node.on_exit()
            except Exception as exc:
                logger.warning("状态 %s on_exit 回调异常: %s", state_name, exc)

    def _record_history(self, state_name: str, event: str, data: Any) -> None:
        """记录执行历史

        Args:
            state_name: 状态名称
            event: 事件类型
            data: 事件数据
        """
        self._history.append({
            "iteration": self._iteration_count,
            "state": state_name,
            "event": event,
            "data": data,
            "timestamp": time.monotonic(),
        })
