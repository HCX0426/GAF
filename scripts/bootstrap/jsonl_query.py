"""jsonl_query.py — JSONL structured log aggregation & query layer (SQLite-backed).

Task 5.3 (P4, 2026-07-29, N193 已知限制解决): 当前 JSONL 是单次执行的扁平日志,
跨执行诊断需手动 grep. 本工具把 ``debug/**/structured.jsonl`` 全部事件导入
SQLite 索引, 支持按 execution_id / node_type / event / error_code / time range /
success/failure 跨执行聚合查询, 让 AI 诊断时能用 SQL 而非 grep.

使用方式:
    # 1. 导入所有 JSONL 到 SQLite 索引 (增量: 只重新导入 mtime 变化的文件)
    conda run -n gaf python scripts/bootstrap/jsonl_query.py ingest

    # 2. 按条件查询事件
    conda run -n gaf python scripts/bootstrap/jsonl_query.py query \\
        --error-code TIMEOUT \\
        --since 2026-07-28

    # 3. 聚合统计 (按 error_code / node_type 分组的失败率 + 平均耗时)
    conda run -n gaf python scripts/bootstrap/jsonl_query.py stats \\
        --group-by error_code

    # 4. 完全重建索引 (清空 + 重新导入)
    conda run -n gaf python scripts/bootstrap/jsonl_query.py rebuild

    # 5. 查看索引状态 (文件数 / 事件数 / 最后导入时间)
    conda run -n gaf python scripts/bootstrap/jsonl_query.py status

设计原则:
- 无新依赖: sqlite3 + json + pathlib 标准库
- 增量导入: 记录每个 jsonl 文件的 mtime + size, 只重新导入变化的文件
- 原始 JSON 保留: events 表有 raw_json 字段, 查询时可取出完整 payload
- 不修改源 JSONL 文件: 只读 + 写自己的 .sqlite 索引

数据库位置: ``debug/.jsonl_index.sqlite`` (与 debug 目录同级, 避免污染源代码).
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: F401  (must be first; reconfigures stdout to UTF-8)

import argparse
import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = _Path(__file__).resolve().parents[2]
DEBUG_DIR = REPO_ROOT / "debug"
DB_PATH = DEBUG_DIR / ".jsonl_index.sqlite"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    timestamp TEXT,             -- ISO 8601 UTC string
    execution_id TEXT,
    node_id TEXT,
    node_type TEXT,
    step_index INTEGER,
    event TEXT,
    success INTEGER,            -- 0/1/NULL (NULL for start/transform events)
    error_code TEXT,
    error_msg TEXT,
    elapsed_ms REAL,
    confidence REAL,
    coord_system TEXT,
    device_type TEXT,
    pipeline_name TEXT,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_execution_id ON events(execution_id);
CREATE INDEX IF NOT EXISTS idx_events_node_type ON events(node_type);
CREATE INDEX IF NOT EXISTS idx_events_event ON events(event);
CREATE INDEX IF NOT EXISTS idx_events_error_code ON events(error_code);
CREATE INDEX IF NOT EXISTS idx_events_success ON events(success);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);

-- 文件级导入状态 (mtime + size 用于增量导入)
CREATE TABLE IF NOT EXISTS files (
    file_path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    line_count INTEGER NOT NULL,
    ingested_at TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


def _connect() -> sqlite3.Connection:
    """打开 SQLite 连接, 确保 DEBUG_DIR 存在."""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def _find_jsonl_files() -> list[Path]:
    """递归扫描 debug 目录下所有 structured.jsonl 文件."""
    if not DEBUG_DIR.exists():
        return []
    return sorted(DEBUG_DIR.rglob("structured.jsonl"))


def _get_file_state(conn: sqlite3.Connection, file_path: str) -> Optional[tuple[float, int]]:
    """返回 (mtime, size) 若文件已导入且 mtime/size 一致; 否则 None."""
    row = conn.execute(
        "SELECT mtime, size FROM files WHERE file_path = ?", (file_path,)
    ).fetchone()
    if row is None:
        return None
    return row["mtime"], row["size"]


def _ingest_one_file(conn: sqlite3.Connection, file_path: Path) -> int:
    """导入单个 JSONL 文件, 返回导入的事件行数.

    若文件 mtime/size 与已记录一致, 跳过 (增量导入).
    """
    file_path_str = str(file_path)
    stat = file_path.stat()
    mtime = stat.st_mtime
    size = stat.st_size

    # 增量检查
    existing = _get_file_state(conn, file_path_str)
    if existing is not None and existing == (mtime, size):
        return 0  # 已是最新, 跳过

    # 文件有变化 (或新文件), 先删旧记录再插入
    conn.execute("DELETE FROM events WHERE file_path = ?", (file_path_str,))
    conn.execute("DELETE FROM files WHERE file_path = ?", (file_path_str,))

    # 提取 pipeline_name: 嵌套结构下从祖父目录名取 (格式 <root>/<date>/<pipeline>/<HHMMSS_suffix>/structured.jsonl)
    # 旧扁平格式: 从父目录名解析 (格式 YYYYMMDD_HHMMSS_<pipeline>_<exec_id>)
    parent_name = file_path.parent.name
    pipeline_name = ""
    # --- 1. 新嵌套格式: <root>/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/structured.jsonl ---
    # parent = HHMMSS_suffix, parent.parent = pipeline, parent.parent.parent = YYYYMMDD
    if re.match(r"^\d{6}_", parent_name):
        grandparent_name = file_path.parent.parent.name
        grandgrandparent_name = file_path.parent.parent.parent.name
        # 确认是嵌套结构: grandgrandparent 是 8 位日期
        if re.match(r"^\d{8}$", grandgrandparent_name):
            pipeline_name = grandparent_name
    # --- 2. 旧扁平格式兼容: YYYYMMDD_HHMMSS_<pipeline>_<exec_id> ---
    if not pipeline_name:
        parts = parent_name.split("_")
        # 至少 4 段 (YYYYMMDD HHMMSS pipeline exec_id); pipeline name 可能含 _
        if len(parts) >= 4 and len(parts[0]) == 8 and parts[0].isdigit():
            # 找最后一个 _exec_id 段, 倒数第一段是 exec_id
            pipeline_name = "_".join(parts[2:-1])

    rows_to_insert = []
    line_count = 0
    try:
        with file_path.open("r", encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, start=1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    payload = json.loads(raw_line)
                except json.JSONDecodeError:
                    # 跳过损坏行 (不阻断整个导入)
                    continue
                if not isinstance(payload, dict):
                    continue
                line_count += 1
                # 扁平化关键字段
                success = payload.get("success")
                success_int = int(bool(success)) if success is not None else None
                rows_to_insert.append((
                    file_path_str,
                    line_no,
                    payload.get("timestamp", ""),
                    payload.get("execution_id", ""),
                    payload.get("node_id", ""),
                    payload.get("node_type", ""),
                    payload.get("step_index"),
                    payload.get("event", ""),
                    success_int,
                    payload.get("error_code", ""),
                    payload.get("error_msg", ""),
                    float(payload.get("elapsed_ms", 0) or 0),
                    float(payload.get("confidence")) if payload.get("confidence") is not None else None,
                    payload.get("coord_system", ""),
                    payload.get("device_type", ""),
                    pipeline_name,
                    raw_line,
                ))
    except OSError as exc:
        print(f"[WARN] failed to read {file_path}: {exc}")
        return 0

    # 批量插入
    conn.executemany(
        """INSERT INTO events (
            file_path, line_no, timestamp, execution_id, node_id, node_type,
            step_index, event, success, error_code, error_msg, elapsed_ms,
            confidence, coord_system, device_type, pipeline_name, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows_to_insert,
    )
    conn.execute(
        "INSERT OR REPLACE INTO files (file_path, mtime, size, line_count, ingested_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (file_path_str, mtime, size, line_count, datetime.utcnow().isoformat() + "Z"),
    )
    conn.commit()
    return len(rows_to_insert)


def ingest(rebuild: bool = False) -> int:
    """扫描 debug 目录所有 structured.jsonl, 导入到 SQLite. 返回导入的事件总数.

    Args:
        rebuild: True 时先清空 events + files 表再全量导入.
    """
    conn = _connect()
    try:
        if rebuild:
            conn.executescript("DELETE FROM events; DELETE FROM files;")
            conn.commit()
            print("[REBUILD] cleared events + files tables")

        files = _find_jsonl_files()
        if not files:
            print(f"[INFO] no structured.jsonl files found under {DEBUG_DIR}")
            return 0

        total_inserted = 0
        skipped = 0
        for f in files:
            n = _ingest_one_file(conn, f)
            if n == 0:
                skipped += 1
            else:
                total_inserted += n
                print(f"[INGEST] {f} -> {n} events")
        print(f"[OK] ingested {total_inserted} events from {len(files)} files "
              f"({skipped} unchanged, skipped)")
        return total_inserted
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def _build_where_clause(args: argparse.Namespace) -> tuple[str, list[Any]]:
    """根据 CLI 参数构建 WHERE clause + params."""
    conditions: list[str] = []
    params: list[Any] = []
    if args.exec_id:
        conditions.append("execution_id = ?")
        params.append(args.exec_id)
    if args.node_type:
        conditions.append("node_type = ?")
        params.append(args.node_type)
    if args.event:
        conditions.append("event = ?")
        params.append(args.event)
    if args.error_code:
        conditions.append("error_code = ?")
        params.append(args.error_code)
    if args.pipeline:
        conditions.append("pipeline_name LIKE ?")
        params.append(f"%{args.pipeline}%")
    if args.failed_only:
        conditions.append("success = 0")
    if args.success_only:
        conditions.append("success = 1")
    if args.since:
        conditions.append("timestamp >= ?")
        params.append(args.since)
    if args.until:
        conditions.append("timestamp <= ?")
        params.append(args.until)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    return where, params


def query_events(args: argparse.Namespace) -> None:
    """按条件查询事件, 打印结果."""
    conn = _connect()
    try:
        where, params = _build_where_clause(args)
        limit = args.limit
        sql = (
            "SELECT timestamp, execution_id, node_id, node_type, event, success, "
            "error_code, elapsed_ms, confidence FROM events"
            + where
            + " ORDER BY timestamp ASC LIMIT ?"
        )
        rows = conn.execute(sql, params + [limit]).fetchall()
        if not rows:
            print("[INFO] no events match the given filters")
            return
        print(f"Found {len(rows)} events (limit={limit}):")
        print("-" * 120)
        print(f"{'timestamp':<28} {'exec_id':<8} {'node_id':<24} {'node_type':<16} "
              f"{'event':<32} {'succ':<5} {'err_code':<18} {'ms':<8} {'conf':<6}")
        print("-" * 120)
        for r in rows:
            succ = "-" if r["success"] is None else ("Y" if r["success"] else "N")
            print(
                f"{r['timestamp'] or '':<28} {(r['execution_id'] or '')[:8]:<8} "
                f"{(r['node_id'] or '')[:24]:<24} {(r['node_type'] or '')[:16]:<16} "
                f"{(r['event'] or '')[:32]:<32} {succ:<5} {(r['error_code'] or '')[:18]:<18} "
                f"{r['elapsed_ms'] or 0:<8.1f} {r['confidence'] or 0:<.3f}"
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def stats(args: argparse.Namespace) -> None:
    """聚合统计: 按 group_by 字段分组, 计算总数 / 失败数 / 失败率 / 平均耗时."""
    valid_groups = {"error_code", "node_type", "event", "pipeline_name", "execution_id"}
    if args.group_by not in valid_groups:
        print(f"[ERROR] --group-by must be one of: {sorted(valid_groups)}")
        return

    conn = _connect()
    try:
        where, params = _build_where_clause(args)
        # 仅统计有 success 字段的事件 (node.execute.complete 等)
        where_with_success = (where + " AND " if where else " WHERE ") + "success IS NOT NULL"
        sql = (
            f"SELECT {args.group_by} AS grp, "
            "COUNT(*) AS total, "
            "SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failed, "
            "ROUND(AVG(elapsed_ms), 2) AS avg_ms, "
            "MIN(elapsed_ms) AS min_ms, "
            "MAX(elapsed_ms) AS max_ms "
            "FROM events" + where_with_success +
            f" GROUP BY {args.group_by} ORDER BY failed DESC, total DESC"
        )
        rows = conn.execute(sql, params).fetchall()
        if not rows:
            print("[INFO] no events to aggregate (run 'ingest' first?)")
            return
        print(f"Aggregation by {args.group_by} ({len(rows)} groups):")
        print("-" * 90)
        print(f"{'group':<32} {'total':<8} {'failed':<8} {'fail%':<8} {'avg_ms':<10} {'min_ms':<10} {'max_ms':<10}")
        print("-" * 90)
        for r in rows:
            total = r["total"]
            failed = r["failed"] or 0
            fail_pct = (failed / total * 100) if total else 0
            grp_display = (r["grp"] or "<empty>")[:32]
            print(
                f"{grp_display:<32} {total:<8} {failed:<8} {fail_pct:<8.1f} "
                f"{r['avg_ms'] or 0:<10.2f} {r['min_ms'] or 0:<10.2f} {r['max_ms'] or 0:<10.2f}"
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def status() -> None:
    """打印索引状态: 文件数 / 事件数 / 最后导入时间."""
    if not DB_PATH.exists():
        print(f"[INFO] index not built yet: {DB_PATH} does not exist")
        print("[HINT] run: python scripts/bootstrap/jsonl_query.py ingest")
        return
    conn = _connect()
    try:
        files_count = conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()["c"]
        events_count = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
        last_ingest = conn.execute(
            "SELECT MAX(ingested_at) AS last FROM files"
        ).fetchone()["last"]
        # 按 event 类型分布
        event_dist = conn.execute(
            "SELECT event, COUNT(*) AS c FROM events GROUP BY event ORDER BY c DESC LIMIT 10"
        ).fetchall()
        # 按 error_code 分布 (失败事件)
        err_dist = conn.execute(
            "SELECT error_code, COUNT(*) AS c FROM events "
            "WHERE success = 0 AND error_code != '' "
            "GROUP BY error_code ORDER BY c DESC LIMIT 10"
        ).fetchall()

        print(f"Index: {DB_PATH}")
        print(f"Files indexed:  {files_count}")
        print(f"Events total:   {events_count}")
        print(f"Last ingest:    {last_ingest or '(none)'}")
        print()
        if event_dist:
            print("Top events:")
            for r in event_dist:
                print(f"  {r['event']:<40} {r['c']}")
        print()
        if err_dist:
            print("Top error codes (failed events):")
            for r in err_dist:
                print(f"  {r['error_code']:<32} {r['c']}")
        else:
            print("No failed events with error_code.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_query_filters(parser: argparse.ArgumentParser) -> None:
    """给子命令添加公共过滤参数."""
    parser.add_argument("--exec-id", help="Filter by execution_id")
    parser.add_argument("--node-type", help="Filter by node_type (e.g. template_match)")
    parser.add_argument("--event", help="Filter by event name (e.g. node.execute.complete)")
    parser.add_argument("--error-code", help="Filter by error_code (e.g. TIMEOUT)")
    parser.add_argument("--pipeline", help="Filter by pipeline name (fuzzy match)")
    parser.add_argument("--failed-only", action="store_true", help="Only failed events (success=0)")
    parser.add_argument("--success-only", action="store_true", help="Only success events (success=1)")
    parser.add_argument("--since", help="Since timestamp (ISO 8601, e.g. 2026-07-28)")
    parser.add_argument("--until", help="Until timestamp (ISO 8601)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JSONL structured log aggregation & query (SQLite-backed).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Scan debug/ and import structured.jsonl into SQLite index (incremental).")
    p_ingest.add_argument("--rebuild", action="store_true", help="Drop all and re-import from scratch.")

    p_query = sub.add_parser("query", help="Query events by filters.")
    _add_query_filters(p_query)
    p_query.add_argument("--limit", type=int, default=50, help="Max rows to print (default 50)")

    p_stats = sub.add_parser("stats", help="Aggregate statistics grouped by a field.")
    p_stats.add_argument("--group-by", default="error_code",
                          choices=["error_code", "node_type", "event", "pipeline_name", "execution_id"],
                          help="Group by field (default: error_code)")
    _add_query_filters(p_stats)

    sub.add_parser("status", help="Show index status (file/event counts, last ingest).")
    sub.add_parser("rebuild", help="Alias for 'ingest --rebuild'.")

    args = parser.parse_args()

    if args.cmd == "ingest":
        ingest(rebuild=args.rebuild)
    elif args.cmd == "rebuild":
        ingest(rebuild=True)
    elif args.cmd == "query":
        ingest()  # 自动增量同步, 确保最新数据
        query_events(args)
    elif args.cmd == "stats":
        ingest()  # 自动增量同步
        stats(args)
    elif args.cmd == "status":
        status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
