"""Tests for TD-421 notification-chain input puncturing.

覆盖:
1. Agent 执行失败 (task.result success=False) → MonitorEvent 落库 (通知链路输入)
2. Agent 执行成功不产生 MonitorEvent (避免刷屏)
3. event.alert 帧 → _handle_event_alert 持久化 MonitorEvent (协议打通)
4. event.alert 自定义 severity 映射
"""

from __future__ import annotations

from unittest.mock import patch

from asgiref.sync import sync_to_async
from django.test import TransactionTestCase, override_settings

from monitors.models import MonitorEvent
from protocol.consumers import WorkerConsumer
from tasks.factories import TaskExecutionFactory
from tasks.models import TaskExecution


def _make_consumer(agent_id: str = "test-alert-agent") -> WorkerConsumer:
    """构造最小可用的 WorkerConsumer 实例 (不连接 WS, 直接调方法)."""
    consumer = WorkerConsumer.__new__(WorkerConsumer)
    consumer.agent_id = agent_id
    return consumer


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestExecutionFailurePuncturing(TransactionTestCase):
    """task.result 失败 → MonitorEvent; 成功 → 不产生."""

    def setUp(self):
        self.consumer = _make_consumer()

    async def test_task_failure_persists_monitor_event(self):
        """执行失败打点: MonitorEvent 新增 agent.task_execution 记录."""
        execution = await sync_to_async(TaskExecutionFactory.create)(
            status=TaskExecution.Status.RUNNING,
        )
        before = await sync_to_async(MonitorEvent.objects.count)()
        await self.consumer._publish_task_failure_event(
            execution_id=str(execution.id),
            error_msg="OCR 低置信度",
            error_code="OCR_LOW_CONFIDENCE",
            frame={"trace_id": "trace-1"},
        )
        after = await sync_to_async(MonitorEvent.objects.count)()
        self.assertEqual(after, before + 1)
        event = await sync_to_async(MonitorEvent.objects.latest)("id")
        self.assertEqual(event.event_type, "agent.task_execution")
        self.assertIn("OCR 低置信度", event.handling_result)
        self.assertEqual(event.severity, MonitorEvent.Severity.P1_HIGH)
        self.assertEqual(event.event_data.get("execution_id"), str(execution.id))
        self.assertEqual(event.event_data.get("error_code"), "OCR_LOW_CONFIDENCE")

    async def test_task_failure_empty_error_uses_code(self):
        """error_msg 为空时 fallback 到 error_code."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        await self.consumer._publish_task_failure_event(
            execution_id=str(execution.id),
            error_msg="",
            error_code="STEP_TIMEOUT",
            frame={"trace_id": "trace-2"},
        )
        event = await sync_to_async(MonitorEvent.objects.latest)("id")
        self.assertIn("STEP_TIMEOUT", event.handling_result)

    async def test_failure_puncturing_never_breaks_result_path(self):
        """打点异常不阻断执行结果处理 (非致命)."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        with patch(
            "monitors.bus.EventBus.broadcast",
            side_effect=RuntimeError("broadcast failed"),
        ):
            # 不抛异常即通过
            await self.consumer._publish_task_failure_event(
                execution_id=str(execution.id),
                error_msg="boom",
                error_code="",
                frame={"trace_id": "trace-3"},
            )

    async def test_success_execution_no_monitor_event(self):
        """执行成功不产生 MonitorEvent (仅失败打点, 避免刷屏)."""
        # 成功路径不调用 _publish_task_failure_event — 通过 handler 级
        # 断言: _handle_task_result success=True 时不触发打点.
        execution = await sync_to_async(TaskExecutionFactory.create)(
            status=TaskExecution.Status.RUNNING,
        )
        payload = {
            "execution_id": str(execution.id),
            "success": True,
            "elapsed_time": 0.5,
            "error_msg": "",
            "data": {},
        }
        with patch.object(
            self.consumer, "_publish_task_failure_event",
        ) as mock_publish:
            await self.consumer._db_update_execution_result(
                execution_id=str(execution.id),
                success=payload["success"],
                elapsed_time=payload["elapsed_time"],
                error_msg=payload["error_msg"],
                result_data=payload["data"],
                structured_log_path="",
                error_code="",
            )
            # success=True → 不产生打点调用
            mock_publish.assert_not_called()


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestEventAlertPersistence(TransactionTestCase):
    """event.alert 帧 → MonitorEvent 持久化 (协议打点打通)."""

    def setUp(self):
        self.consumer = _make_consumer()

    async def test_event_alert_persists(self):
        """agent 上报 event.alert → MonitorEvent.agent.* 记录."""
        before = await sync_to_async(MonitorEvent.objects.count)()
        await self.consumer._db_persist_agent_alert(
            event_type="ocr_low_confidence",
            message="OCR 置信度 0.42 低于阈值",
            severity="P1",
            event_data={"confidence": 0.42, "execution_id": "exec-1"},
            trace_id="trace-alert-1",
        )
        after = await sync_to_async(MonitorEvent.objects.count)()
        self.assertEqual(after, before + 1)
        event = await sync_to_async(MonitorEvent.objects.latest)("id")
        self.assertEqual(event.event_type, "agent.ocr_low_confidence")
        self.assertEqual(event.severity, MonitorEvent.Severity.P1_HIGH)
        self.assertEqual(event.event_data.get("confidence"), 0.42)

    async def test_event_alert_custom_severity(self):
        """severity=P0 → P0_CRITICAL; 非法 severity fallback P1."""
        await self.consumer._db_persist_agent_alert(
            event_type="critical_reboot",
            message="需要重启",
            severity="P0",
            event_data={},
            trace_id="trace-alert-2",
        )
        event = await sync_to_async(MonitorEvent.objects.latest)("id")
        self.assertEqual(event.severity, MonitorEvent.Severity.P0_CRITICAL)

        await self.consumer._db_persist_agent_alert(
            event_type="bogus_severity",
            message="x",
            severity="P9",
            event_data={},
            trace_id="trace-alert-3",
        )
        event2 = await sync_to_async(MonitorEvent.objects.latest)("id")
        self.assertEqual(event2.severity, MonitorEvent.Severity.P1_HIGH)

    async def test_handle_event_alert_invokes_persistence(self):
        """_handle_event_alert 从 frame payload 取数并持久化."""
        frame = {
            "payload": {
                "event_type": "popup_unhandled",
                "message": "弹窗 30s 未处理",
                "severity": "P2",
            },
            "trace_id": "trace-alert-4",
        }
        with patch.object(
            self.consumer, "_db_persist_agent_alert",
        ) as mock_persist:
            await self.consumer._handle_event_alert(frame)
            mock_persist.assert_awaited_once_with(
                event_type="popup_unhandled",
                message="弹窗 30s 未处理",
                severity="P2",
                event_data={},
                trace_id="trace-alert-4",
            )

    async def test_handle_event_alert_non_fatal(self):
        """持久化失败不抛出 (非致命)."""
        frame = {
            "payload": {"event_type": "x", "message": "y"},
            "trace_id": "trace-alert-5",
        }
        consumer = _make_consumer()
        consumer.__dict__["agent_id"] = "t421"
        with patch.object(
            consumer, "_db_persist_agent_alert",
            side_effect=RuntimeError("db down"),
        ):
            # 不抛异常即通过
            await consumer._handle_event_alert(frame)  # type: ignore[abstract]
