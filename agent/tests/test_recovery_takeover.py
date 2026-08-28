"""#34 人工接管降级 (RequestHumanTakeover) 单元测试

测试 RecoveryStrategy.request_human_takeover() 及相关功能：
- HumanTakeoverError 异常抛出
- takeover_active 状态标记
- task_pause_fn 回调调用
- webhook 通知发送 (Slack/Discord/自定义)
- clear_takeover 状态清除
- critical 日志记录
"""
import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from core.recovery import HumanTakeoverError, RecoveryStrategy

pytestmark = pytest.mark.e2e


class TestHumanTakeoverError:
    """HumanTakeoverError 异常类测试"""

    def test_is_exception_subclass(self):
        """HumanTakeoverError 应继承 Exception"""
        assert issubclass(HumanTakeoverError, Exception)

    def test_raises_correctly(self):
        """HumanTakeoverError 应能被 raise 并捕获"""
        with pytest.raises(HumanTakeoverError, match="test reason"):
            raise HumanTakeoverError("test reason")

    def test_carries_message(self):
        """异常消息应正确传递"""
        err = HumanTakeoverError("接管原因")
        assert "接管原因" in str(err)


class TestRequestHumanTakeover:
    """request_human_takeover 方法测试"""

    def test_raises_human_takeover_error(self):
        """调用 request_human_takeover 应抛出 HumanTakeoverError"""
        strategy = RecoveryStrategy()
        with pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="测试原因")

    def test_sets_takeover_active(self):
        """调用后 takeover_active 应为 True"""
        strategy = RecoveryStrategy()
        assert strategy.takeover_active is False
        with pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="测试")
        assert strategy.takeover_active is True

    def test_includes_reason_in_error(self):
        """异常消息应包含原因"""
        strategy = RecoveryStrategy()
        with pytest.raises(HumanTakeoverError, match="设备无响应"):
            strategy.request_human_takeover(reason="设备无响应")

    def test_includes_task_id_in_error(self):
        """异常消息应包含任务 ID"""
        strategy = RecoveryStrategy()
        with pytest.raises(HumanTakeoverError, match="task-123"):
            strategy.request_human_takeover(reason="测试", task_id="task-123")

    def test_includes_device_id_in_error(self):
        """异常消息应包含设备 ID"""
        strategy = RecoveryStrategy()
        with pytest.raises(HumanTakeoverError, match="device-456"):
            strategy.request_human_takeover(reason="测试", device_id="device-456")

    def test_includes_consecutive_fails_in_error(self):
        """异常消息应包含连续失败次数"""
        strategy = RecoveryStrategy()
        strategy.consecutive_fails = 7
        with pytest.raises(HumanTakeoverError, match="fails=7"):
            strategy.request_human_takeover(reason="测试")

    def test_sets_current_layer_to_5(self):
        """调用后 current_layer 应为 5"""
        strategy = RecoveryStrategy()
        with pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="测试")
        assert strategy.current_layer == 5


class TestTaskPauseCallback:
    """task_pause_fn 回调测试"""

    def test_calls_task_pause_fn(self):
        """配置 task_pause_fn 后应被调用"""
        pause_fn = MagicMock()
        strategy = RecoveryStrategy(task_pause_fn=pause_fn)
        with pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="测试")
        pause_fn.assert_called_once()

    def test_does_not_call_when_not_configured(self):
        """未配置 task_pause_fn 时不应报错"""
        strategy = RecoveryStrategy()
        with pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="测试")  # should not raise AttributeError

    def test_continues_if_task_pause_fails(self):
        """task_pause_fn 抛异常时不应中断接管流程"""
        pause_fn = MagicMock(side_effect=RuntimeError("暂停失败"))
        strategy = RecoveryStrategy(task_pause_fn=pause_fn)
        with pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="测试")
        pause_fn.assert_called_once()
        assert strategy.takeover_active is True


class TestWebhookNotification:
    """Webhook 通知测试"""

    def test_does_not_send_when_no_webhook_url(self):
        """未配置 webhook_url 时不应尝试发送"""
        strategy = RecoveryStrategy()
        with patch.object(RecoveryStrategy, '_send_webhook') as mock_send:
            with pytest.raises(HumanTakeoverError):
                strategy.request_human_takeover(reason="测试")
            mock_send.assert_not_called()

    def test_sends_webhook_when_configured(self):
        """配置 webhook_url 后应调用 _send_webhook"""
        strategy = RecoveryStrategy(webhook_url="https://example.com/hook")
        with patch.object(RecoveryStrategy, '_send_webhook') as mock_send:
            with pytest.raises(HumanTakeoverError):
                strategy.request_human_takeover(
                    reason="测试原因",
                    task_id="task-1",
                    device_id="dev-1",
                )
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][0] == "https://example.com/hook"
            payload = call_args[0][1]
            assert payload['event'] == 'human_takeover'
            assert payload['reason'] == '测试原因'
            assert payload['task_id'] == 'task-1'
            assert payload['device_id'] == 'dev-1'

    def test_webhook_continues_on_failure(self):
        """Webhook 发送失败时不应中断接管流程"""
        strategy = RecoveryStrategy(webhook_url="https://example.com/hook")
        with patch.object(RecoveryStrategy, '_send_webhook', return_value=False), \
             pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="测试")
        assert strategy.takeover_active is True


class TestSendWebhook:
    """_send_webhook 静态方法测试"""

    def test_sends_custom_webhook_successfully(self):
        """自定义 webhook 应发送 JSON payload"""
        url = "https://example.com/hook"
        payload = {'event': 'human_takeover', 'reason': 'test'}

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response) as mock_urlopen:
            result = RecoveryStrategy._send_webhook(url, payload)
            assert result is True
            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            assert req.get_method() == 'POST'
            body = json.loads(req.data.decode('utf-8'))
            assert body == payload

    def test_returns_false_on_http_error(self):
        """HTTP 非 2xx 状态码应返回 False"""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response):
            result = RecoveryStrategy._send_webhook("https://example.com/hook", {})
            assert result is False

    def test_returns_false_on_url_error(self):
        """URLError 应返回 False"""
        from urllib import error as urllib_error
        with patch('urllib.request.urlopen', side_effect=urllib_error.URLError("connection refused")):
            result = RecoveryStrategy._send_webhook("https://example.com/hook", {})
            assert result is False

    def test_returns_false_on_generic_exception(self):
        """其他异常应返回 False"""
        with patch('urllib.request.urlopen', side_effect=ValueError("unexpected")):
            result = RecoveryStrategy._send_webhook("https://example.com/hook", {})
            assert result is False

    def test_slack_webhook_wraps_in_text_format(self):
        """Slack webhook 应包装为 {'text': ...} 格式"""
        url = "https://hooks.slack.com/services/T000/B000/XXX"
        payload = {
            'event': 'human_takeover',
            'reason': '设备无响应',
            'task_id': 'task-1',
            'device_id': 'dev-1',
            'consecutive_fails': 5,
            'timestamp': 1700000000.0,
        }

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response) as mock_urlopen:
            result = RecoveryStrategy._send_webhook(url, payload)
            assert result is True
            req = mock_urlopen.call_args[0][0]
            body = json.loads(req.data.decode('utf-8'))
            assert 'text' in body
            assert "设备无响应" in body['text']
            assert "task-1" in body['text']
            assert "dev-1" in body['text']

    def test_discord_webhook_wraps_in_text_format(self):
        """Discord webhook 应包装为 {'text': ...} 格式"""
        url = "https://discord.com/api/webhooks/000/XXX"
        payload = {'reason': '测试'}

        mock_response = MagicMock()
        mock_response.status = 204
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response):
            result = RecoveryStrategy._send_webhook(url, payload)
            assert result is True


class TestClearTakeover:
    """clear_takeover 方法测试"""

    def test_clears_takeover_active(self):
        """clear_takeover 应将 takeover_active 设为 False"""
        strategy = RecoveryStrategy()
        with pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="测试")
        assert strategy.takeover_active is True
        strategy.clear_takeover()
        assert strategy.takeover_active is False

    def test_resets_consecutive_fails(self):
        """clear_takeover 应重置 consecutive_fails"""
        strategy = RecoveryStrategy()
        strategy.consecutive_fails = 10
        strategy.clear_takeover()
        assert strategy.consecutive_fails == 0

    def test_resets_current_layer(self):
        """clear_takeover 应重置 current_layer"""
        strategy = RecoveryStrategy()
        strategy.current_layer = 5
        strategy.clear_takeover()
        assert strategy.current_layer == 0

    def test_idempotent(self):
        """clear_takeover 应可重复调用"""
        strategy = RecoveryStrategy()
        strategy.clear_takeover()
        strategy.clear_takeover()
        assert strategy.takeover_active is False


class TestTakeoverLogging:
    """日志记录测试"""

    def test_logs_critical_on_takeover(self, caplog):
        """request_human_takeover 应记录 critical 日志"""
        strategy = RecoveryStrategy()
        with caplog.at_level(logging.CRITICAL, logger='core.recovery'), pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(
                reason="测试原因",
                task_id="task-1",
                device_id="dev-1",
            )
        critical_logs = [r for r in caplog.records if r.levelno == logging.CRITICAL]
        assert len(critical_logs) >= 1
        assert any("HUMAN_TAKEOVER_REQUIRED" in r.getMessage() for r in critical_logs)

    def test_logs_info_on_clear(self, caplog):
        """clear_takeover 应记录 info 日志"""
        strategy = RecoveryStrategy()
        with pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="测试")
        with caplog.at_level(logging.INFO, logger='core.recovery'):
            strategy.clear_takeover()
        info_logs = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any("人工接管状态已清除" in r.getMessage() for r in info_logs)


class TestIntegrationWithRecoveryLayers:
    """与 5 层恢复策略的集成测试"""

    def test_takeover_after_layer_5_alert(self):
        """Layer 5 告警后可触发人工接管"""
        strategy = RecoveryStrategy()
        strategy.trigger_alert("告警消息")
        assert strategy.current_layer == 5
        with pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="告警后接管")
        assert strategy.takeover_active is True

    def test_can_resume_after_clear(self):
        """clear_takeover 后可继续使用其他恢复层"""
        strategy = RecoveryStrategy()
        with pytest.raises(HumanTakeoverError):
            strategy.request_human_takeover(reason="测试")
        strategy.clear_takeover()
        assert strategy.takeover_active is False
        # Should be able to use other layers again
        strategy.trigger_alert("新告警")
        assert strategy.current_layer == 5
