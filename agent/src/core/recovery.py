"""5层恢复策略实现
Layer 1: 步骤级重试（指数退避）
Layer 2: 任务级重启
Layer 3: 应用级重启
Layer 4: 设备级重连
Layer 5: 系统级告警 + 人工接管降级 (RequestHumanTakeover)
"""
import json
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger(__name__)


class HumanTakeoverError(Exception):
    """Raised when automated recovery is exhausted and human intervention is required.

    N193 Task 5.3: 携带 node_id 让 orchestrator 捕获时能把节点上下文写入
    fail_result, AI 诊断时能定位是哪个节点触发了人工接管.

    Attributes:
        node_id: 触发人工接管的节点 ID. 空字符串表示未绑定具体节点
            (如 orchestrator 层直接抛出, 不经过 recovery_manager).
    """

    def __init__(self, message: str, node_id: str = "") -> None:
        super().__init__(message)
        self.node_id = node_id


class RecoveryStrategy:
    """5层恢复策略管理器"""

    def __init__(
        self,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        max_consecutive_fails: int = 5,
        app_restart_fn: Callable | None = None,
        device_reconnect_fn: Callable | None = None,
        webhook_url: str | None = None,
        task_pause_fn: Callable | None = None,
    ):
        """初始化恢复策略

        Args:
            max_retries: 最大重试次数
            retry_base_delay: 重试基础延迟（秒）
            max_consecutive_fails: 触发任务重启的连续失败阈值
            app_restart_fn: 应用重启回调函数
            device_reconnect_fn: 设备重连回调函数
            webhook_url: Webhook 通知 URL (Slack/Discord/自定义)，用于人工接管告警
            task_pause_fn: 任务暂停回调函数，人工接管时调用以暂停任务执行
        """
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.max_consecutive_fails = max_consecutive_fails
        self.app_restart_fn = app_restart_fn
        self.device_reconnect_fn = device_reconnect_fn
        self.webhook_url = webhook_url
        self.task_pause_fn = task_pause_fn
        self.consecutive_fails = 0
        self.current_layer = 0
        self._takeover_active = False

    def reset(self):
        """重置连续失败计数和当前层级"""
        self.consecutive_fails = 0
        self.current_layer = 0

    def step_retry(self, fn: Callable, *args, **kwargs):
        """Layer 1: 步骤级重试，指数退避

        Args:
            fn: 要重试的可调用对象
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数执行结果

        Raises:
            RuntimeError: 重试次数耗尽后仍失败
        """
        self.current_layer = 1
        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = fn(*args, **kwargs)
                self.reset()
                return result
            except Exception as e:
                last_error = e
                delay = self.retry_base_delay * (2 ** attempt)
                logger.warning("步骤重试 %d/%d, %.1fs后重试: %s", attempt + 1, self.max_retries, delay, e)
                self.consecutive_fails += 1
                if attempt < self.max_retries - 1:
                    time.sleep(delay)
        raise RuntimeError(f"步骤重试{self.max_retries}次后仍失败: {last_error}")

    def should_restart_task(self) -> bool:
        """Layer 2: 检查是否应重启任务

        Returns:
            连续失败次数是否达到阈值
        """
        self.current_layer = 2
        return self.consecutive_fails >= self.max_consecutive_fails

    def restart_app(self) -> bool:
        """Layer 3: 应用级重启

        Returns:
            重启是否成功
        """
        self.current_layer = 3
        if self.app_restart_fn:
            try:
                self.app_restart_fn()
                self.consecutive_fails = 0
                return True
            except Exception as e:
                logger.error("应用重启失败: %s", e)
        return False

    def reconnect_device(self) -> bool:
        """Layer 4: 设备级重连

        Returns:
            重连是否成功
        """
        self.current_layer = 4
        if self.device_reconnect_fn:
            try:
                self.device_reconnect_fn()
                return True
            except Exception as e:
                logger.error("设备重连失败: %s", e)
        return False

    def restart_emulator(
        self,
        emulator_type: str,
        instance_id: str | None = None,
        emulator_controller=None,
    ) -> bool:
        """Layer 4+: 模拟器重启 (异常恢复)

        When device_reconnect_fn fails or is unavailable, restart the emulator
        process entirely. This is a heavier recovery action than reconnect_device.

        Args:
            emulator_type: Emulator type key (ldplayer/mumu/bluestacks/nox/memu/xiaoyao)
            instance_id: Optional emulator instance ID (e.g. ldconsole index)
            emulator_controller: EmulatorController instance. If None, creates one.

        Returns:
            True if emulator restarted and booted successfully, False otherwise
        """
        self.current_layer = 4
        logger.info(
            "Layer 4+ emulator restart: type=%s instance=%s",
            emulator_type, instance_id,
        )

        if emulator_controller is None:
            try:
                from devices.emulator_controller import EmulatorController
                emulator_controller = EmulatorController()
            except ImportError as e:
                logger.error("Cannot import EmulatorController: %s", e)
                return False

        try:
            success = emulator_controller.restart_emulator(
                emulator_type=emulator_type,
                instance_id=instance_id,
                wait_for_boot=True,
            )
            if success:
                self.consecutive_fails = 0
                logger.info("Emulator restart succeeded: %s", emulator_type)
            return success
        except Exception as e:
            logger.error("Emulator restart failed: %s", e)
            return False

    def trigger_alert(self, message: str):
        """Layer 5: 系统级告警

        Args:
            message: 告警消息
        """
        self.current_layer = 5
        logger.critical("ALERT: %s", message)

    def request_human_takeover(
        self,
        reason: str,
        task_id: str | None = None,
        device_id: str | None = None,
        context: dict[str, Any] | None = None,
        node_id: str = "",
    ) -> None:
        """Layer 5+: 人工接管降级 (RequestHumanTakeover)

        当所有自动恢复策略都失败后调用。执行以下操作：
        1. 标记接管状态为活跃
        2. 暂停任务执行（如果 task_pause_fn 已配置）
        3. 发送 Webhook 通知（如果 webhook_url 已配置）
        4. 记录 critical 级别日志
        5. 抛出 HumanTakeoverError 中断当前执行流

        Args:
            reason: 触发人工接管的原因
            task_id: 关联的任务 ID（可选）
            device_id: 关联的设备 ID（可选）
            context: 附加上下文信息（可选）
            node_id: N193 Task 5.3 — 触发人工接管的节点 ID. 空字符串
                表示未绑定具体节点. 传入后 HumanTakeoverError.node_id
                会被设置, orchestrator 捕获时能把 node_id 写入 fail_result.

        Raises:
            HumanTakeoverError: 总是抛出，用于中断执行流
        """
        self.current_layer = 5
        self._takeover_active = True

        # Build alert payload
        payload: dict[str, Any] = {
            'event': 'human_takeover',
            'reason': reason,
            'task_id': task_id,
            'device_id': device_id,
            'consecutive_fails': self.consecutive_fails,
            'timestamp': time.time(),
            'context': context or {},
        }

        # Pause task execution
        if self.task_pause_fn:
            try:
                self.task_pause_fn()
                logger.info("任务已暂停，等待人工接管")
            except Exception as e:
                logger.error("暂停任务失败: %s", e)

        # Send webhook notification
        if self.webhook_url:
            self._send_webhook(self.webhook_url, payload)

        # Log critical alert
        logger.critical(
            "HUMAN_TAKEOVER_REQUIRED: reason=%s task=%s device=%s fails=%d",
            reason, task_id, device_id, self.consecutive_fails,
        )

        raise HumanTakeoverError(
            f"人工接管已触发: {reason} (task={task_id}, device={device_id}, fails={self.consecutive_fails})",
            node_id=node_id,
        )

    @property
    def takeover_active(self) -> bool:
        """Whether human takeover is currently active."""
        return self._takeover_active

    def clear_takeover(self) -> None:
        """Clear human takeover state (called after human intervention resolves the issue)."""
        self._takeover_active = False
        self.reset()
        logger.info("人工接管状态已清除，恢复自动执行")

    @staticmethod
    def _send_webhook(url: str, payload: dict[str, Any]) -> bool:
        """Send webhook notification (Slack/Discord/custom).

        Uses urllib to avoid external dependencies. Payload is sent as JSON.
        For Slack/Discord, wraps payload in {'text': ...} format if 'text' key
        is not present.

        Args:
            url: Webhook URL
            payload: JSON-serializable payload

        Returns:
            True if notification sent successfully, False otherwise
        """
        try:
            # Slack/Discord expect {'text': '...'} format
            if 'slack.com' in url or 'discord.com' in url:
                text = f"[GAF 人工接管告警]\n原因: {payload.get('reason', 'unknown')}\n"
                text += f"任务: {payload.get('task_id', 'N/A')}\n"
                text += f"设备: {payload.get('device_id', 'N/A')}\n"
                text += f"连续失败: {payload.get('consecutive_fails', 0)} 次\n"
                text += f"时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(payload.get('timestamp', time.time())))}"
                body = json.dumps({'text': text}).encode('utf-8')
            else:
                body = json.dumps(payload).encode('utf-8')

            req = urllib_request.Request(
                url,
                data=body,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib_request.urlopen(req, timeout=10) as response:
                if 200 <= response.status < 300:
                    logger.info("Webhook 通知已发送: %s", url)
                    return True
                logger.warning("Webhook 返回非 2xx 状态码: %d", response.status)
                return False
        except urllib_error.URLError as e:
            logger.error("Webhook 发送失败 (URL 错误): %s", e)
            return False
        except Exception as e:
            logger.error("Webhook 发送失败: %s", e)
            return False
