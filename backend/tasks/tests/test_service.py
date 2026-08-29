"""Service 层单元测试 — TaskService, SchedulerService, DeviceService

Spec §5: 验证 Service 层封装的业务逻辑正确性，确保 View 层与业务逻辑解耦。
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.django_db
class TestHeartbeatTimeoutNullSafe:
    """monitor_service.check_heartbeat_timeout — NULL-safe 心跳超时检测.

    Regression (2026-08-27): 与 tasks/heartbeat.py 对齐 —— Django ``__lt``
    不匹配 NULL, "从未心跳"的 agent 必须同样被判离线, 否则成为幻影 agent。
    """

    def test_never_heartbeated_agent_flipped_offline(self):
        from django.utils import timezone

        from agents.models import Agent
        from tasks.services.monitor_service import TaskMonitorService

        phantom = Agent.objects.create(
            agent_id='ms-phantom', hostname='h-ms-phantom',
            status=Agent.Status.ONLINE, last_heartbeat=None,
        )
        fresh = Agent.objects.create(
            agent_id='ms-fresh', hostname='h-ms-fresh',
            status=Agent.Status.ONLINE, last_heartbeat=timezone.now(),
        )
        # Agent 离线后其窗口必须联动离线
        from agents.models import Device
        phantom_window = Device.objects.create(
            name='ms-phantom-window', device_type=Device.DeviceType.WINDOWS,
            status=Device.Status.ONLINE, agent=phantom,
        )

        # @shared_task 装饰的静态方法 — 直接调用即同步执行 run()
        TaskMonitorService.check_heartbeat_timeout()

        phantom.refresh_from_db()
        fresh.refresh_from_db()
        phantom_window.refresh_from_db()
        assert phantom.status == Agent.Status.OFFLINE
        assert fresh.status == Agent.Status.ONLINE
        assert phantom_window.status == Device.Status.OFFLINE


@pytest.mark.django_db
class TestTaskService:
    """TaskService 单元测试 (Spec §5 测试场景 1)。"""

    def test_dispatch_delegates_to_execute_task(self):
        """dispatch() 应正确转发参数给 execute_task。"""
        from tasks.services.task_service import TaskService

        service = TaskService()
        mock_task = MagicMock()
        mock_user = MagicMock()

        with patch("tasks.services.task_service.execute_task") as mock_exec:
            mock_exec.return_value = MagicMock(id=999)

            result = service.dispatch(
                task=mock_task,
                agent_id="agent-001",
                user=mock_user,
                device_id=5,
                game_account_id=10,
                resource_pack_id=20,
            )

            mock_exec.assert_called_once_with(
                task=mock_task,
                agent_id="agent-001",
                user=mock_user,
                device_id=5,
                game_account_id=10,
                resource_pack_id=20,
            )
            assert result.id == 999

    def test_cancel_updates_status_and_notifies_agent(self):
        """cancel() 应更新状态、发送 WS 通知、释放资源。"""
        from tasks.services.task_service import TaskService

        service = TaskService()
        mock_execution = MagicMock()
        mock_execution.agent = MagicMock(agent_id="agent-001")
        mock_execution.id = 123

        # channels.layers.get_channel_layer returns a channel layer whose
        # group_send is an async function. We mock it with an async stub so
        # async_to_sync can properly await it.
        _sent = {}

        async def _fake_group_send(group, msg):
            _sent["group"] = group
            _sent["msg"] = msg

        mock_cl = MagicMock()
        mock_cl.group_send = _fake_group_send

        with (
            patch("tasks.services.task_service._release_concurrency_slot") as mock_release,
            patch("tasks.services.task_service._restore_device_status") as mock_restore,
            patch("channels.layers.get_channel_layer", return_value=mock_cl),
        ):
            result = service.cancel(mock_execution, reason="测试取消")

            assert str(result.status) == "cancelled"
            assert result.cancel_reason == "测试取消"
            mock_execution.save.assert_called_once()
            assert "agent_agent-001" in _sent.get("group", "")
            mock_release.assert_called_once_with("agent-001", 123)
            mock_restore.assert_called_once_with(mock_execution)

    def test_cancel_no_agent_skips_ws_notification(self):
        """如果 execution.agent 为 None，不应尝试发送 WS 通知。"""
        from tasks.services.task_service import TaskService

        service = TaskService()
        mock_execution = MagicMock()
        mock_execution.agent = None
        mock_execution.id = 456

        _called = []

        async def _fake_group_send(group, msg):
            _called.append(True)

        mock_cl = MagicMock()
        mock_cl.group_send = _fake_group_send

        with (
            patch("tasks.services.task_service._release_concurrency_slot") as mock_release,
            patch("tasks.services.task_service._restore_device_status"),
            patch("channels.layers.get_channel_layer", return_value=mock_cl),
        ):
            service.cancel(mock_execution)

            assert _called == []  # group_send not called when agent is None
            mock_release.assert_called_once_with(None, 456)


@pytest.mark.django_db
class TestSchedulerService:
    """SchedulerService 单元测试。"""

    def test_get_execution_plan_with_invalid_days(self):
        """days 参数为 0 或负数时应抛出 ValueError。"""
        from scheduler.services.scheduler_service import SchedulerService

        with pytest.raises(ValueError, match="positive integer"):
            SchedulerService.get_execution_plan(days=0)

        with pytest.raises(ValueError, match="positive integer"):
            SchedulerService.get_execution_plan(days=-5)

    def test_get_execution_plan_with_valid_days(self):
        """days 参数有效时应返回包含正确字段的 dict。"""
        from scheduler.services.scheduler_service import SchedulerService

        with patch("scheduler.services.scheduler_service.generate_execution_plan") as mock_gen:
            mock_gen.return_value = [
                {"device_id": 1, "account_id": 2, "time_slot": "10:00"},
                {"device_id": 1, "account_id": 3, "time_slot": "14:00"},
                {"device_id": 2, "account_id": 2, "time_slot": "10:00"},
            ]

            result = SchedulerService.get_execution_plan(days=7)

            assert result["days"] == 7
            assert result["total_events"] == 3
            assert result["device_count"] == 2
            assert result["account_count"] == 2
            assert len(result["events"]) == 3

    def test_validate_time_window_overlap_raises(self):
        """时间窗口重叠时应抛出 DRFValidationError。"""
        from django.utils import timezone
        from rest_framework.exceptions import ValidationError
        from scheduler.services.scheduler_service import SchedulerService

        with patch("scheduler.services.scheduler_service.TimeWindow.objects") as mock_qs:
            mock_window = MagicMock()
            mock_window.start_time = timezone.datetime(2026, 8, 1, 10, 0)
            mock_window.end_time = timezone.datetime(2026, 8, 1, 12, 0)
            mock_window.days_of_week = [0, 1, 2]

            mock_filtered = MagicMock()
            mock_filtered.exclude.return_value = mock_filtered
            mock_filtered.__iter__ = MagicMock(return_value=iter([mock_window]))
            mock_qs.filter.return_value = mock_filtered

            data = {
                "start_time": timezone.datetime(2026, 8, 1, 11, 0),
                "end_time": timezone.datetime(2026, 8, 1, 13, 0),
                "days_of_week": [1],
            }

            with pytest.raises(ValidationError):
                SchedulerService.validate_time_window(data)

    def test_validate_time_window_no_overlap_passes(self):
        """不重叠的时间窗口应通过校验。"""
        from django.utils import timezone
        from scheduler.services.scheduler_service import SchedulerService

        with patch("scheduler.services.scheduler_service.TimeWindow.objects") as mock_qs:
            mock_window = MagicMock()
            mock_window.start_time = timezone.datetime(2026, 8, 1, 10, 0)
            mock_window.end_time = timezone.datetime(2026, 8, 1, 12, 0)
            mock_window.days_of_week = [0, 1, 2]

            mock_filtered = MagicMock()
            mock_filtered.exclude.return_value = mock_filtered
            mock_filtered.__iter__ = MagicMock(return_value=iter([mock_window]))
            mock_qs.filter.return_value = mock_filtered

            data = {
                "start_time": timezone.datetime(2026, 8, 1, 14, 0),
                "end_time": timezone.datetime(2026, 8, 1, 16, 0),
                "days_of_week": [3],
            }

            SchedulerService.validate_time_window(data)

    def test_get_today_schedule_returns_correct_structure(self):
        """get_today_schedule 应返回包含 date/total/items 等字段的正确结构。"""
        from scheduler.services.scheduler_service import SchedulerService

        with patch("scheduler.services.scheduler_service.generate_execution_plan") as mock_gen:
            mock_gen.return_value = [
                {"device_id": 1, "account_id": 2, "task_chain_id": 10,
                 "device_name": "Device A", "account_name": "Account X",
                 "task_chain_name": "Chain Alpha"},
                {"device_id": 2, "account_id": 3, "task_chain_id": 20,
                 "device_name": "Device B", "account_name": "Account Y",
                 "task_chain_name": "Chain Beta"},
            ]

            result = SchedulerService.get_today_schedule()

            assert "date" in result
            assert result["total"] == 2
            assert result["completed"] == 0
            assert result["failed"] == 0
            assert len(result["items"]) == 2

            first = result["items"][0]
            assert first["device_id"] == 1
            assert first["device_name"] == "Device A"
            # N219: 今日日程 = 计划排期, 状态为 planned(计划中), 非 pending
            assert first["status"] == "planned"
            assert first["progress"] == 0
            assert first["error_message"] is None

    def test_get_today_schedule_empty_plan(self):
        """当执行计划为空时，get_today_schedule 应返回 total=0 和空 items 列表。"""
        from scheduler.services.scheduler_service import SchedulerService

        with patch("scheduler.services.scheduler_service.generate_execution_plan") as mock_gen:
            mock_gen.return_value = []

            result = SchedulerService.get_today_schedule()

            assert result["total"] == 0
            assert result["items"] == []
            assert result["completed"] == 0
            assert result["failed"] == 0

    def test_list_executions_default_page(self):
        """list_executions 应返回分页结构，包含 count/page/results。"""
        from scheduler.services.scheduler_service import SchedulerService

        mock_execution = MagicMock()
        mock_execution.id = 100
        mock_execution.task = MagicMock(name="Test Task")
        mock_execution.task.name = "Test Task"
        mock_execution.task.schedules = MagicMock()
        mock_execution.task.schedules.first.return_value = MagicMock(id=50)
        mock_execution.status = "success"
        mock_execution.started_at = None
        mock_execution.completed_at = None
        mock_execution.created_at = MagicMock()
        mock_execution.created_at.isoformat.return_value = "2026-08-08T10:00:00"
        mock_execution.error_message = None

        mock_qs = MagicMock()
        mock_qs.count.return_value = 2
        mock_qs.__getitem__.return_value = [mock_execution, mock_execution]

        with patch("tasks.models.TaskExecution.objects") as mock_objects:
            mock_objects.select_related.return_value = (
                mock_objects
            )
            mock_objects.prefetch_related.return_value = (
                mock_objects
            )
            mock_objects.order_by.return_value = mock_qs

            result = SchedulerService.list_executions(page=1, page_size=20)

            assert result["count"] == 2
            assert result["page"] == 1
            assert result["page_size"] == 20
            assert len(result["results"]) == 2
            assert result["results"][0]["task_name"] == "Test Task"
            assert result["results"][0]["scheduled_task_id"] == "50"

    def test_list_executions_empty(self):
        """当无执行记录时，list_executions 应返回 count=0 和空 results 列表。"""
        from scheduler.services.scheduler_service import SchedulerService

        mock_qs = MagicMock()
        mock_qs.count.return_value = 0
        mock_qs.__getitem__.return_value = []

        with patch("tasks.models.TaskExecution.objects") as mock_objects:
            mock_objects.select_related.return_value = (
                mock_objects
            )
            mock_objects.prefetch_related.return_value = (
                mock_objects
            )
            mock_objects.order_by.return_value = mock_qs

            result = SchedulerService.list_executions(page=1, page_size=20)

            assert result["count"] == 0
            assert result["results"] == []


@pytest.mark.django_db
class TestDeviceService:
    """DeviceService 单元测试。"""

    def test_check_single_device_health_windows(self):
        """Windows 设备健康检查应返回正确的结果结构。"""
        from agents.services.device_service import DeviceService

        service = DeviceService()
        mock_device = MagicMock()
        mock_device.device_type = "windows"
        mock_device.status = "online"
        mock_device.id = 1
        mock_device.name = "Test Device"

        with patch.object(service, "_probe_windows_device", return_value=(True, "OK")):
            result = service.check_single_device_health(mock_device)

            assert result["id"] == 1
            assert result["name"] == "Test Device"
            assert result["is_online"] is True
            assert result["new_status"] == "online"

    def test_check_single_device_health_emulator_fallback(self):
        """模拟器 ADB 不可用时应回退到进程检测。"""
        from agents.services.device_service import DeviceService

        service = DeviceService()
        mock_device = MagicMock()
        mock_device.device_type = "emulator"
        mock_device.status = "online"
        mock_device.extra_info = {"process_name": "dnplayer.exe"}
        mock_device.id = 2
        mock_device.name = "LDPlayer"

        with (
            patch.object(service, "_probe_adb_device", return_value=(False, "ADB offline")),
            patch.object(service, "_probe_process", return_value=(True, "Process running")),
        ):
            result = service.check_single_device_health(mock_device)

            assert result["is_online"] is True
            assert "ADB offline" in result["reason"]
            assert "Process running" in result["reason"]

    def test_update_device_status(self):
        """update_device_status 应正确更新设备状态。"""
        from agents.services.device_service import DeviceService

        service = DeviceService()
        mock_device = MagicMock()
        mock_device.status = "offline"

        with patch("agents.services.device_service.Device.objects.get", return_value=mock_device):
            result = service.update_device_status(device_id=99, status="online")

            assert result.status == "online"
            mock_device.save.assert_called_once()

    def test_update_device_status_not_found(self):
        """设备不存在时应抛出 Device.DoesNotExist。"""
        from agents.models import Device
        from agents.services.device_service import DeviceService

        service = DeviceService()

        with (
            patch("agents.services.device_service.Device.objects.get", side_effect=Device.DoesNotExist),
            pytest.raises(Device.DoesNotExist),
        ):
            service.update_device_status(device_id=999, status="online")

    def test_check_all_devices_health_returns_list(self):
        """check_all_devices_health 应对每个设备执行健康检查并返回结果列表。"""
        from agents.services.device_service import DeviceService

        service = DeviceService()
        mock_device_1 = MagicMock()
        mock_device_1.id = 1
        mock_device_1.name = "Device A"
        mock_device_2 = MagicMock()
        mock_device_2.id = 2
        mock_device_2.name = "Device B"

        mock_qs = MagicMock()
        mock_qs.__iter__.return_value = iter([mock_device_1, mock_device_2])

        with patch("agents.services.device_service.Device.objects") as mock_objects:
            mock_objects.select_related.return_value = mock_qs
            mock_qs.all.return_value = mock_qs

            with patch.object(service, "check_single_device_health") as mock_check:
                mock_check.side_effect = [
                    {"id": 1, "is_online": True, "new_status": "online"},
                    {"id": 2, "is_online": False, "new_status": "offline"},
                ]

                results = service.check_all_devices_health()

                assert len(results) == 2
                assert results[0]["id"] == 1
                assert results[0]["is_online"] is True
                assert results[1]["id"] == 2
                assert results[1]["is_online"] is False
                assert mock_check.call_count == 2

    def test_check_all_devices_health_empty(self):
        """当无设备时，check_all_devices_health 应返回空列表。"""
        from agents.services.device_service import DeviceService

        service = DeviceService()

        mock_qs = MagicMock()
        mock_qs.__iter__.return_value = iter([])

        with patch("agents.services.device_service.Device.objects") as mock_objects:
            mock_objects.select_related.return_value = mock_qs
            mock_qs.all.return_value = mock_qs

            with patch.object(service, "check_single_device_health") as mock_check:
                results = service.check_all_devices_health()

                assert results == []
                mock_check.assert_not_called()
