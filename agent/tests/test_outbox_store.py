"""P3 (2026-08-17) SQLite-persisted outbox store tests.

Covers:
- enqueue -> load_all FIFO order
- delete_first_n partial / full / overshoot safety
- crash recovery: a fresh store on the same db reloads old frames
- corrupted db file degrades gracefully (memory-only mode)
"""


import pytest
from client.outbox_store import OutboxStore

pytestmark = pytest.mark.unit


def _make_store(tmp_path, name="outbox.db"):
    return OutboxStore(tmp_path / name)


class TestEnqueueLoad:
    def test_enqueue_then_load_fifo(self, tmp_path):
        store = _make_store(tmp_path)
        store.enqueue("task.progress", {"execution_id": "1"})
        store.enqueue("task.result", {"execution_id": "1", "success": True})
        store.enqueue("event.ack", {"event_id": "e1"})

        frames = store.load_all()
        assert [f[0] for f in frames] == [
            "task.progress", "task.result", "event.ack",
        ]
        assert frames[1][1] == {"execution_id": "1", "success": True}

    def test_load_empty(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.load_all() == []

    def test_count(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.count() == 0
        store.enqueue("task.result", {"execution_id": "1"})
        assert store.count() == 1
        assert len(store) == 1

    def test_unicode_payload_roundtrip(self, tmp_path):
        store = _make_store(tmp_path)
        store.enqueue("task.result", {"msg": "中文日志: 失败\n换行"})
        frames = store.load_all()
        assert frames[0][1]["msg"] == "中文日志: 失败\n换行"


class TestDeleteFirstN:
    def test_delete_partial(self, tmp_path):
        store = _make_store(tmp_path)
        for i in range(5):
            store.enqueue("task.progress", {"execution_id": str(i)})

        store.delete_first_n(2)
        frames = store.load_all()
        assert [f[1]["execution_id"] for f in frames] == ["2", "3", "4"]

    def test_delete_all(self, tmp_path):
        store = _make_store(tmp_path)
        for i in range(3):
            store.enqueue("task.result", {"execution_id": str(i)})

        store.delete_first_n(3)
        assert store.count() == 0

    def test_delete_overshoot_safe(self, tmp_path):
        store = _make_store(tmp_path)
        store.enqueue("task.result", {"execution_id": "1"})

        store.delete_first_n(10)  # 不抛异常, 只删存在的行
        assert store.count() == 0

    def test_delete_zero_or_negative_noop(self, tmp_path):
        store = _make_store(tmp_path)
        store.enqueue("task.result", {"execution_id": "1"})
        store.delete_first_n(0)
        store.delete_first_n(-1)
        assert store.count() == 1


class TestCrashRecovery:
    def test_new_store_reloads_old_frames(self, tmp_path):
        db = tmp_path / "outbox.db"
        store1 = OutboxStore(db)
        store1.enqueue("task.progress", {"execution_id": "1"})
        store1.enqueue("task.result", {"execution_id": "1", "success": True})
        store1.close()  # 模拟进程退出

        store2 = OutboxStore(db)  # 模拟进程重启
        frames = store2.load_all()
        assert [f[0] for f in frames] == ["task.progress", "task.result"]

    def test_partial_flush_persisted(self, tmp_path):
        db = tmp_path / "outbox.db"
        store1 = OutboxStore(db)
        for i in range(4):
            store1.enqueue("task.progress", {"execution_id": str(i)})
        store1.delete_first_n(2)  # 模拟 flush 成功 2 帧
        store1.close()

        store2 = OutboxStore(db)
        frames = store2.load_all()
        assert [f[1]["execution_id"] for f in frames] == ["2", "3"]

    def test_corrupted_db_degrades_gracefully(self, tmp_path):
        db = tmp_path / "outbox.db"
        db.write_bytes(b"this is not a sqlite file" * 10)

        store = OutboxStore(db)
        # 打开失败 → 降级内存模式, 所有操作安全 noop
        assert store.load_all() == []
        assert store.count() == 0
        store.enqueue("task.result", {"execution_id": "1"})  # 不抛
        store.delete_first_n(1)  # 不抛


class TestJsonDataIntegrity:
    def test_corrupted_row_skipped(self, tmp_path):
        db = tmp_path / "outbox.db"
        store = OutboxStore(db)
        store.enqueue("task.result", {"execution_id": "1"})

        # 手动损坏第二行
        import sqlite3

        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO outbox (msg_type, data, created_at) VALUES (?, ?, ?)",
            ("task.result", "{not valid json", "2026-08-17T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        frames = store.load_all()
        assert len(frames) == 1
        assert frames[0][1]["execution_id"] == "1"
