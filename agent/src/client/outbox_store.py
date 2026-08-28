"""SQLite-persisted outbox for agent outbound frames.

P3 (2026-08-17): S1 known limitation - the in-memory outbox (deque)
lost all buffered frames on process crash/restart. This module adds
a durable sidecar store: frames are INSERTed on enqueue, replayed
FIFO after reconnect, and deleted only after successful send.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_type TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


class OutboxStore:
    """Durable FIFO store for outbound frames (one row per frame).

    - ``enqueue`` INSERTs a row; ``load_all`` returns rows in id order.
    - ``delete_first_n`` removes the n oldest rows after a successful
      flush (frames already acknowledged by the server).
    - Connection errors (disk full, permission) are caught and logged;
      the caller keeps operating in memory-only mode (degraded).
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.execute(_SCHEMA)
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error(
                "[outbox_store] SQLite 打开失败 (降级为内存模式): path=%s, error=%s",
                self.db_path, exc,
            )
            self._conn = None

    def enqueue(self, msg_type: str, data: dict[str, Any]) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO outbox (msg_type, data, created_at) VALUES (?, ?, ?)",
                (msg_type, json.dumps(data, ensure_ascii=False), _now_iso()),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("[outbox_store] 入队落盘失败: msg_type=%s, error=%s", msg_type, exc)

    def load_all(self) -> list[tuple[str, dict[str, Any]]]:
        if self._conn is None:
            return []
        try:
            rows = self._conn.execute(
                "SELECT msg_type, data FROM outbox ORDER BY id ASC"
            ).fetchall()
            result: list[tuple[str, dict[str, Any]]] = []
            for msg_type, data_json in rows:
                try:
                    result.append((msg_type, json.loads(data_json)))
                except (json.JSONDecodeError, TypeError):
                    logger.warning("[outbox_store] 跳过损坏帧: msg_type=%s", msg_type)
            return result
        except sqlite3.Error as exc:
            logger.error("[outbox_store] 读取失败: error=%s", exc)
            return []

    def delete_first_n(self, n: int) -> None:
        if self._conn is None or n <= 0:
            return
        try:
            self._conn.execute(
                "DELETE FROM outbox WHERE id IN "
                "(SELECT id FROM outbox ORDER BY id ASC LIMIT ?)",
                (n,),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("[outbox_store] 删除失败: n=%d, error=%s", n, exc)

    def count(self) -> int:
        if self._conn is None:
            return 0
        try:
            row = self._conn.execute("SELECT COUNT(*) FROM outbox").fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error as exc:
            logger.error("[outbox_store] count 失败: error=%s", exc)
            return 0

    def __len__(self) -> int:
        return self.count()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error as exc:
                logger.warning("[outbox_store] close 失败: error=%s", exc)
            self._conn = None


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
