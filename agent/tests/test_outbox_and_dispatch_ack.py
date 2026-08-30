"""S1 (2026-08-16) agent 出站队列 + dispatch ack 测试.

覆盖:
- send_message 在 WS 未连接/未就绪时入队而非丢弃
- 重连成功后 _flush_outbox 按 FIFO 重放
- 重放中断时剩余帧重新入队
- handler.handle_task_assign 回 event.ack(task.dispatch)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from client.connection import OUTBOX_MAX_SIZE, WorkerConnection
from core.config import AgentConfig

pytestmark = pytest.mark.unit


def _make_config(**overrides) -> AgentConfig:
    defaults = {
        "server_url": "ws://127.0.0.1:8000/ws/protocol/agents/",
        "agent_token": "test-token",
        "device_type": "windows",
        "heartbeat_interval": 30,
    }
    defaults.update(overrides)
    return AgentConfig(**defaults)


def _make_connection(**kwargs):
    monitor = MagicMock()
    monitor.get_stats.return_value = {"cpu": 1.0, "memory": 50.0, "fps": 30.0}
    outbox_store = kwargs.pop("outbox_store", None)
    conn = WorkerConnection(_make_config(), resource_monitor=monitor, outbox_store=outbox_store)
    for k, v in kwargs.items():
        setattr(conn, k, v)
    return conn


class TestOutboxEnqueue:
    """send_message 在连接不可用时把帧放入出站队列."""

    def test_enqueue_when_ws_is_none(self):
        conn = _make_connection()
        conn._ws = None

        asyncio.run(conn.send_message("task.result", {"execution_id": "1", "success": True}))

        assert len(conn._outbox) == 1
        msg_type, data = conn._outbox[0]
        assert msg_type == "task.result"
        assert data["execution_id"] == "1"

    def test_enqueue_when_not_connected(self):
        conn = _make_connection()
        conn._ws = MagicMock()
        conn._connected = False

        asyncio.run(conn.send_message("task.progress", {"execution_id": "2", "status": "running"}))

        assert len(conn._outbox) == 1
        assert conn._outbox[0][0] == "task.progress"

    def test_outbox_capacity_limited(self):
        conn = _make_connection()
        conn._ws = None

        async def _run():
            for i in range(OUTBOX_MAX_SIZE + 10):
                await conn.send_message("task.progress", {"execution_id": str(i)})

        asyncio.run(_run())

        assert len(conn._outbox) == OUTBOX_MAX_SIZE


class TestOutboxFlush:
    """重连成功后出站队列按 FIFO 重放."""

    def test_flush_replays_fifo(self):
        conn = _make_connection()
        conn._ws = MagicMock()
        conn._ws.send = AsyncMock()
        conn._connected = True
        # 入队两帧
        conn._outbox.append(("task.progress", {"execution_id": "1"}))
        conn._outbox.append(("task.result", {"execution_id": "1", "success": True}))

        with patch.object(conn, "send_message", new=AsyncMock()) as mock_send:
            asyncio.run(conn._flush_outbox())

        assert mock_send.await_count == 2
        sent_types = [call.args[0] for call in mock_send.await_args_list]
        assert sent_types == ["task.progress", "task.result"]
        assert len(conn._outbox) == 0

    def test_flush_noop_when_empty(self):
        conn = _make_connection()

        with patch.object(conn, "send_message", new=AsyncMock()) as mock_send:
            asyncio.run(conn._flush_outbox())

        mock_send.assert_not_awaited()

    def test_flush_skips_when_disconnected(self):
        conn = _make_connection()
        conn._ws = None
        conn._outbox.append(("task.result", {"execution_id": "1"}))

        with patch.object(conn, "send_message", new=AsyncMock()) as mock_send:
            asyncio.run(conn._flush_outbox())

        mock_send.assert_not_awaited()
        assert len(conn._outbox) == 1  # 帧保留

    def test_flush_requeues_remaining_on_disconnect(self):
        conn = _make_connection()
        conn._ws = MagicMock()
        conn._ws.send = AsyncMock()
        conn._connected = True
        conn._outbox.append(("task.progress", {"execution_id": "1"}))
        conn._outbox.append(("task.result", {"execution_id": "1", "success": True}))

        real_send = conn.send_message
        calls = {"n": 0}

        async def _fake_send(msg_type, data, _enqueue_on_failure=True):
            calls["n"] += 1
            if calls["n"] == 2:
                # 第二帧发送前连接断开 → send_message 内部会把帧重新入队
                conn._ws = None
                conn._connected = False
            return await real_send(msg_type, data)

        with patch.object(conn, "send_message", new=AsyncMock(side_effect=_fake_send)):
            asyncio.run(conn._flush_outbox())

        # task.result 发送时连接断开 → 帧重新入队
        assert len(conn._outbox) == 1
        assert conn._outbox[0][0] == "task.result"


class TestDispatchAck:
    """handle_task_assign 应回 event.ack(task.dispatch)."""

    def _make_handler(self):
        orchestrator = MagicMock()
        handler_module = __import__("client.handler", fromlist=["MessageHandler"])
        handler = handler_module.MessageHandler(orchestrator)
        handler._loop = asyncio.new_event_loop()
        return handler

    def test_task_assign_sends_dispatch_ack(self):
        handler = self._make_handler()
        sent = []

        async def fake_send(msg_type, data):
            sent.append((msg_type, data))

        handler.send_callback = fake_send

        data = {
            "execution_id": "exec-1",
            "task_id": "task-1",
            "task_name": "test",
            "task_definition": {"nodes": []},
            "device_info": None,
        }

        async def _run():
            handler._loop = asyncio.get_running_loop()
            handler.handle_task_assign(data)
            await asyncio.sleep(0.1)

        asyncio.run(_run())

        ack_frames = [s for s in sent if s[0] == "event.ack"]
        assert len(ack_frames) == 1
        ack_payload = ack_frames[0][1]
        assert ack_payload["ack_type"] == "task.dispatch"
        assert ack_payload["execution_id"] == "exec-1"
class TestOutboxStoreIntegration:
    """P3 (2026-08-17): outbox SQLite 持久化集成."""

    def _make_store_conn(self, tmp_path):
        from client.outbox_store import OutboxStore

        store = OutboxStore(tmp_path / "outbox.db")
        conn = _make_connection(outbox_store=store)
        return store, conn

    def test_enqueue_persists_to_store(self, tmp_path):
        store, conn = self._make_store_conn(tmp_path)
        conn._ws = None

        asyncio.run(conn.send_message("task.result", {"execution_id": "1"}))

        assert store.count() == 1
        assert store.load_all()[0][0] == "task.result"

    def test_init_restores_persisted_frames(self, tmp_path):
        from client.outbox_store import OutboxStore

        store = OutboxStore(tmp_path / "outbox.db")
        store.enqueue("task.result", {"execution_id": "9", "success": True})

        conn = _make_connection(outbox_store=store)
        assert len(conn._outbox) == 1
        assert conn._outbox[0][0] == "task.result"
        assert conn._outbox[0][1]["execution_id"] == "9"

    def test_flush_success_clears_store(self, tmp_path):
        store, conn = self._make_store_conn(tmp_path)
        conn._ws = MagicMock()
        conn._ws.send = AsyncMock()
        conn._connected = True
        conn._outbox.append(("task.progress", {"execution_id": "1"}))
        conn._outbox.append(("task.result", {"execution_id": "1", "success": True}))
        store.enqueue("task.progress", {"execution_id": "1"})
        store.enqueue("task.result", {"execution_id": "1", "success": True})

        with patch.object(conn, "send_message", new=AsyncMock()) as mock_send:
            asyncio.run(conn._flush_outbox())

        assert mock_send.await_count == 2
        assert store.count() == 0

    def test_flush_interrupt_keeps_remaining_in_store(self, tmp_path):
        store, conn = self._make_store_conn(tmp_path)
        conn._ws = MagicMock()
        conn._ws.send = AsyncMock()
        conn._connected = True
        conn._outbox.append(("task.progress", {"execution_id": "1"}))
        conn._outbox.append(("task.result", {"execution_id": "1", "success": True}))
        store.enqueue("task.progress", {"execution_id": "1"})
        store.enqueue("task.result", {"execution_id": "1", "success": True})

        real_send = conn.send_message
        calls = {"n": 0}

        async def _fake_send(msg_type, data, _enqueue_on_failure=True):
            calls["n"] += 1
            if calls["n"] == 2:
                conn._ws = None
                conn._connected = False
            return await real_send(msg_type, data)

        with patch.object(conn, "send_message", new=AsyncMock(side_effect=_fake_send)):
            asyncio.run(conn._flush_outbox())

        # 第一帧已成功 → store 删 1 行; 第二帧保留在内存 + store
        assert store.count() == 1
        assert len(conn._outbox) == 1
        assert conn._outbox[0][0] == "task.result"
        assert store.load_all()[0][0] == "task.result"

    def test_no_store_behavior_unchanged(self, tmp_path):
        conn = _make_connection()
        conn._ws = None

        asyncio.run(conn.send_message("task.result", {"execution_id": "1"}))

        assert len(conn._outbox) == 1
