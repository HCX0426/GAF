"""监控系统：监控规则的加载、启停和事件上报"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from devices.manager import DeviceManager
    from image.processor import ImageProcessor

logger = logging.getLogger(__name__)

# N154: was 5.0s — every screenshot spawns an adb subprocess (screencap) or
# calls ldopengl64.dll capture. At 5s with multiple agent processes stacking
# (admin-elevated agents survive autoreload), this creates an adb storm that
# triggers GPU driver TDR (black screen). 30s matches the heartbeat interval.
DEFAULT_CHECK_INTERVAL = 30.0


@dataclass
class MonitorRule:
    """监控规则定义"""
    name: str
    is_enabled: bool = True
    check_condition: Callable[[Any | None], bool] = lambda _: False
    handle_action: Callable[[], None] = lambda: None
    check_interval: float = DEFAULT_CHECK_INTERVAL
    last_check_time: float = 0.0

    def __post_init__(self):
        """校验规则参数"""
        if not self.name:
            raise ValueError("监控规则名称不能为空")
        if not callable(self.check_condition):
            raise ValueError("检查条件必须是可调用对象")
        if not callable(self.handle_action):
            raise ValueError("处理动作必须是可调用对象")


class MonitorThread(threading.Thread):
    """监控守护线程，循环执行启用的监控任务"""

    def __init__(
        self,
        rules: list[MonitorRule],
        device_manager: DeviceManager,
        image_processor: ImageProcessor,
        callback: Callable[[str, dict[str, Any]], None],
        stop_event: threading.Event,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
    ):
        super().__init__(daemon=True)
        self._rules = rules
        self._device_manager = device_manager
        self._image_processor = image_processor
        self._callback = callback
        self._stop_event = stop_event
        self._check_interval = check_interval

    def run(self) -> None:
        """循环执行监控任务

        流程：
        1. 遍历启用的监控规则
        2. 对每个规则执行 check_condition
        3. 如果条件满足，执行 handle_action
        4. 通过 callback 上报事件
        5. 检查 stop_event
        """
        logger.info("监控线程已启动")
        while not self._stop_event.is_set():
            try:
                self._check_all_rules()
            except Exception as exc:
                logger.error("监控循环异常: %s", exc)

            self._stop_event.wait(timeout=self._check_interval)

        logger.info("监控线程已退出")

    def _check_all_rules(self) -> None:
        """检查所有启用的监控规则"""
        screenshot = self._take_screenshot()
        now = time.monotonic()

        for rule in self._rules:
            if not rule.is_enabled:
                continue

            elapsed = now - rule.last_check_time
            if elapsed < rule.check_interval:
                continue

            rule.last_check_time = now

            try:
                if rule.check_condition(screenshot):
                    logger.info("监控规则 %s 条件满足，执行处理动作", rule.name)
                    rule.handle_action()
                    self._callback(rule.name, {
                        "rule_name": rule.name,
                        "timestamp": time.time(),
                        "action_executed": True,
                    })
            except Exception as exc:
                logger.error("监控规则 %s 执行异常: %s", rule.name, exc)
                self._callback(rule.name, {
                    "rule_name": rule.name,
                    "timestamp": time.time(),
                    "error": str(exc),
                })

    def _take_screenshot(self) -> Any | None:
        """截取当前屏幕画面

        Returns:
            截图数据，失败返回 None
        """
        try:
            device = self._device_manager.get_active_device()
            if not device:
                return None
            # Skip screenshot if device is not operable. Without this guard
            # the @require_operable decorator on capture_screen() raises
            # DeviceError every loop iteration, producing a WARNING per second
            # and eventually filling the log (N154 pattern).
            from devices.base import DeviceStatus
            if device.status not in (DeviceStatus.CONNECTED, DeviceStatus.IDLE):
                return None
            return device.capture_screen()
        except Exception as exc:
            logger.warning("监控截图失败: %s", exc)
        return None


class MonitorManager:
    """监控管理器，管理监控规则的加载、启停和事件上报

    支持与资源包关联：切换资源包时自动切换对应的监控规则
    """

    def __init__(
        self,
        device_manager: DeviceManager,
        image_processor: ImageProcessor,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self._device_manager = device_manager
        self._image_processor = image_processor
        self._event_callback = event_callback or self._default_event_callback
        self._rules: dict[str, MonitorRule] = {}
        self._thread: MonitorThread | None = None
        self._stop_event = threading.Event()
        self._is_running = False
        self._active_resource_pack: str | None = None
        self._pack_rules: dict[str, list[dict[str, Any]]] = {}
        # PopupHandler instance owned by manager — used by monitor PipelineNode
        # via context.monitor_manager.popup_handler.check_and_handle().
        # Templates are registered via register_popup_template() or load_rules().
        from monitor.handlers import PopupHandler
        self._popup_handler = PopupHandler(
            device_manager=device_manager,
            image_processor=image_processor,
            event_callback=self._event_callback,
        )

    @property
    def popup_handler(self):
        """Expose PopupHandler for monitor node / external callers."""
        return self._popup_handler

    def load_rules(self, rules_data: list[dict[str, Any]]) -> None:
        """从 Server 下发的规则数据加载监控规则

        Args:
            rules_data: 规则数据列表，每项包含 name, check_condition, handle_action 等
        """
        for rule_data in rules_data:
            try:
                rule = MonitorRule(
                    name=rule_data.get("name", ""),
                    is_enabled=rule_data.get("is_enabled", True),
                    check_condition=rule_data.get("check_condition", lambda _: False),
                    handle_action=rule_data.get("handle_action", lambda: None),
                    check_interval=rule_data.get("check_interval", DEFAULT_CHECK_INTERVAL),
                )
                self._rules[rule.name] = rule
                logger.info("已加载监控规则: %s", rule.name)
            except Exception as exc:
                logger.error("加载监控规则失败: %s", exc)

    def start(self) -> None:
        """启动监控线程"""
        if self._is_running:
            logger.warning("监控已在运行中")
            return

        self._stop_event.clear()
        rules_list = list(self._rules.values())
        self._thread = MonitorThread(
            rules=rules_list,
            device_manager=self._device_manager,
            image_processor=self._image_processor,
            callback=self._event_callback,
            stop_event=self._stop_event,
        )
        self._thread.start()
        self._is_running = True
        logger.info("监控管理器已启动，共 %d 条规则", len(rules_list))

    def stop(self) -> None:
        """停止监控线程"""
        if not self._is_running:
            return

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        self._is_running = False
        logger.info("监控管理器已停止")

    def force_stop_all(self, agent_id: str | None = None) -> bool:
        """强制停止所有监控线程（Phase 6.3 per task-cancel-design.md §5.2）.

        与 ``stop()`` 的区别：
          * 更短的 join 超时（1 秒 vs 5 秒）—— 强制终止场景下不应
            等待长时间
          * 清空所有已加载规则，防止 ``start()`` 被意外调用时使用
            旧规则
          * 返回 ``True/False`` 表示线程是否在超时内退出，调用方可
            据此判断是否需要走更激进的清理路径

        设计文档 §5.2 中 ``MonitorManager.force_stop_all(agent_id)``
        的本意是 server 端通过 Celery 调用 agent 端停止监控。但
        server 无法直接调用 agent 方法，实际流程是：
          1. Server 端 ``check_cancel_timeout`` Celery 任务标记 DB
             状态为 ``force_terminated``
          2. Server 通过 WebSocket 发送 ``task.force_terminate`` 给 agent
          3. Agent 端 ``MessageHandler`` 收到后调用本方法

        Args:
            agent_id: 可选的 agent ID，仅用于日志诊断。设计文档
                原签名包含此参数，agent 端实现不需要它（每个
                ``MonitorManager`` 实例本身就是 per-agent 的）。

        Returns:
            ``True`` 如果监控线程在 1 秒内退出；``False`` 如果超时
            （线程仍在运行，但 Python 无法安全强制杀死线程，只能
            等待其下次检查 ``_stop_event`` 时退出）。
        """
        log_prefix = f"[agent={agent_id}] " if agent_id else ""
        if not self._is_running and not (self._thread and self._thread.is_alive()):
            # Already stopped — just clear rules for safety
            self._rules.clear()
            logger.info("%s监控管理器 force_stop_all：已是停止状态，规则已清空", log_prefix)
            return True

        logger.warning(
            "%s监控管理器 force_stop_all：强制停止监控线程（1 秒超时）",
            log_prefix,
        )
        self._stop_event.set()
        thread_alive = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            thread_alive = self._thread.is_alive()

        self._thread = None
        self._is_running = False
        # Clear rules so a subsequent start() requires explicit reload
        rules_cleared = len(self._rules)
        self._rules.clear()

        if thread_alive:
            logger.error(
                "%s监控管理器 force_stop_all：线程未在 1 秒内退出，"
                "将等待其下次检查 _stop_event 自行退出（已清空 %d 条规则）",
                log_prefix, rules_cleared,
            )
        else:
            logger.info(
                "%s监控管理器 force_stop_all：线程已退出，已清空 %d 条规则",
                log_prefix, rules_cleared,
            )
        return not thread_alive

    def update_rules(self, rules_data: list[dict[str, Any]]) -> None:
        """热更新监控规则（无需重启）

        Args:
            rules_data: 新的规则数据列表
        """
        was_running = self._is_running
        if was_running:
            self.stop()

        self._rules.clear()
        self.load_rules(rules_data)
        logger.info("监控规则已热更新，共 %d 条规则", len(self._rules))

        if was_running:
            self.start()

    def enable_rule(self, name: str) -> None:
        """启用指定规则

        Args:
            name: 规则名称
        """
        rule = self._rules.get(name)
        if rule:
            rule.is_enabled = True
            logger.info("已启用监控规则: %s", name)
        else:
            logger.warning("监控规则不存在: %s", name)

    def disable_rule(self, name: str) -> None:
        """禁用指定规则

        Args:
            name: 规则名称
        """
        rule = self._rules.get(name)
        if rule:
            rule.is_enabled = False
            logger.info("已禁用监控规则: %s", name)
        else:
            logger.warning("监控规则不存在: %s", name)

    @property
    def is_running(self) -> bool:
        """监控是否正在运行"""
        return self._is_running

    @property
    def rule_count(self) -> int:
        """获取规则数量"""
        return len(self._rules)

    def register_resource_pack(self, pack_name: str, rules_data: list[dict[str, Any]]) -> None:
        """注册资源包及其关联的监控规则

        Args:
            pack_name: 资源包名称
            rules_data: 该资源包关联的监控规则数据
        """
        self._pack_rules[pack_name] = rules_data
        logger.info("已注册资源包 %s 的监控规则（%d 条）", pack_name, len(rules_data))

    def switch_resource_pack(self, pack_name: str) -> None:
        """切换活跃资源包，自动切换对应的监控规则

        切换资源包时，先停止当前监控，加载新资源包的规则，再重启监控

        Args:
            pack_name: 目标资源包名称
        """
        if pack_name == self._active_resource_pack:
            logger.debug("资源包 %s 已是活跃状态，无需切换", pack_name)
            return

        rules_data = self._pack_rules.get(pack_name, [])
        if not rules_data:
            logger.warning("资源包 %s 无关联监控规则", pack_name)

        old_pack = self._active_resource_pack
        self._active_resource_pack = pack_name

        was_running = self._is_running
        if was_running:
            self.stop()

        self._rules.clear()
        if rules_data:
            self.load_rules(rules_data)

        logger.info("资源包切换: %s -> %s，已加载 %d 条规则", old_pack, pack_name, len(rules_data))

        if was_running and self._rules:
            self.start()

    @property
    def active_resource_pack(self) -> str | None:
        """获取当前活跃的资源包名称"""
        return self._active_resource_pack

    @staticmethod
    def _default_event_callback(rule_name: str, data: dict[str, Any]) -> None:
        """默认事件回调，仅记录日志

        Args:
            rule_name: 触发的规则名称
            data: 事件数据
        """
        logger.info("监控事件: rule=%s, data=%s", rule_name, data)
