"""test_jsonl_query.py — Unit tests for JSONL aggregation & query layer.

Covers the main behaviors of scripts/bootstrap/jsonl_query.py:

1. test_ingest_one_file_imports_events — 单文件导入 + 字段扁平化正确
2. test_ingest_incremental_skips_unchanged — mtime/size 一致时增量跳过
3. test_ingest_rebuild_clears_old_data — rebuild=True 清空旧数据
4. test_query_filters_by_error_code — 按 error_code 过滤查询
5. test_stats_groups_by_error_code — 按 error_code 聚合统计 (总数/失败率/avg ms)
6. test_pipeline_name_extracted_from_dir — 从父目录名解析 pipeline_name

Run with: `conda run -n gaf python -m pytest scripts/tests/test_jsonl_query.py -q`
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

pytestmark = pytest.mark.unit


def _load_module():
    """Load jsonl_query.py as an isolated module (avoid import side effects)."""
    mod_path = SCRIPTS_DIR / "bootstrap" / "jsonl_query.py"
    mod_name = "_jsonl_query_test"
    spec = importlib.util.spec_from_file_location(mod_name, mod_path)
    assert spec and spec.loader, "failed to load spec"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    return mod


_JSONL_FIXTURE_LINES = [
    # orchestrator start event (no success field)
    {
        "timestamp": "2026-07-28T10:00:00.000Z",
        "execution_id": "exec-001",
        "node_id": "_orchestrator",
        "node_type": "orchestrator",
        "step_index": -1,
        "event": "orchestrator.task.start",
        "task_state": "running",
        "device_id": "windows-hwnd-1",
        "pipeline_node_count": 3,
    },
    # node.execute.start (no success field)
    {
        "timestamp": "2026-07-28T10:00:00.500Z",
        "execution_id": "exec-001",
        "node_id": "click_login",
        "node_type": "click",
        "step_index": 0,
        "event": "node.execute.start",
        "elapsed_ms": 0.0,
        "retry_count": 0,
    },
    # node.execute.complete success
    {
        "timestamp": "2026-07-28T10:00:01.000Z",
        "execution_id": "exec-001",
        "node_id": "click_login",
        "node_type": "click",
        "step_index": 0,
        "event": "node.execute.complete",
        "elapsed_ms": 500.0,
        "retry_count": 0,
        "success": True,
        "error_msg": "",
        "coord_system": "logical",
        "device_type": "windows",
    },
    # node.execute.complete failed with TIMEOUT
    {
        "timestamp": "2026-07-28T10:00:06.000Z",
        "execution_id": "exec-001",
        "node_id": "wait_email",
        "node_type": "wait",
        "step_index": 1,
        "event": "node.execute.complete",
        "elapsed_ms": 5000.0,
        "retry_count": 0,
        "success": False,
        "error_msg": "节点 wait_email 执行超时 (5.0s)",
        "error_code": "TIMEOUT",
        "coord_system": "logical",
        "device_type": "windows",
    },
    # node.execute.complete failed with NO_MATCH (with confidence)
    {
        "timestamp": "2026-07-28T10:00:10.000Z",
        "execution_id": "exec-001",
        "node_id": "find_button",
        "node_type": "template_match",
        "step_index": 2,
        "event": "node.execute.complete",
        "elapsed_ms": 200.0,
        "retry_count": 1,
        "success": False,
        "error_msg": "no match",
        "error_code": "NO_MATCH",
        "confidence": 0.45,
        "threshold": 0.8,
        "coord_system": "logical",
        "device_type": "windows",
    },
]


def _make_fixture(tmp_path: Path, lines=None) -> Path:
    """Create a structured.jsonl fixture file under tmp_path/debug/ (嵌套结构).

    嵌套格式: tmp_path/debug/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/structured.jsonl
    Returns the path to the JSONL file. Also sets REPO_ROOT/debug to tmp_path
    via monkeypatch in the caller.
    """
    if lines is None:
        lines = _JSONL_FIXTURE_LINES
    # 嵌套结构: <debug>/<date>/<pipeline>/<HHMMSS_suffix>/structured.jsonl
    exec_dir = tmp_path / "debug" / "20260728" / "Test_Pipeline" / "100000_exec-001"
    exec_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = exec_dir / "structured.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for payload in lines:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return jsonl_path


def _setup_mod(tmp_path: Path, monkeypatch):
    """Setup module with DEBUG_DIR + DB_PATH pointed at tmp_path."""
    mod = _load_module()
    debug_dir = tmp_path / "debug"
    db_path = debug_dir / ".jsonl_index.sqlite"
    monkeypatch.setattr(mod, "DEBUG_DIR", debug_dir)
    monkeypatch.setattr(mod, "DB_PATH", db_path)
    return mod


def test_ingest_one_file_imports_events(tmp_path, monkeypatch):
    mod = _setup_mod(tmp_path, monkeypatch)
    jsonl_path = _make_fixture(tmp_path)

    conn = mod._connect()
    try:
        n = mod._ingest_one_file(conn, jsonl_path)
        assert n == 5, f"expected 5 events, got {n}"
        # 验证字段扁平化
        row = conn.execute(
            "SELECT * FROM events WHERE node_id = ? AND event = ?",
            ("wait_email", "node.execute.complete"),
        ).fetchone()
        assert row is not None
        assert row["error_code"] == "TIMEOUT"
        assert row["success"] == 0
        assert row["elapsed_ms"] == 5000.0
        # pipeline_name 从父目录名解析
        assert row["pipeline_name"] == "Test_Pipeline"
        # raw_json 保留原始 payload
        raw = json.loads(row["raw_json"])
        assert raw["error_msg"] == "节点 wait_email 执行超时 (5.0s)"
    finally:
        conn.close()


def test_ingest_incremental_skips_unchanged(tmp_path, monkeypatch):
    mod = _setup_mod(tmp_path, monkeypatch)
    jsonl_path = _make_fixture(tmp_path)

    # 第一次导入
    conn = mod._connect()
    try:
        n1 = mod._ingest_one_file(conn, jsonl_path)
        assert n1 == 5
    finally:
        conn.close()

    # 第二次导入: 文件未变, 应跳过 (返回 0)
    conn = mod._connect()
    try:
        n2 = mod._ingest_one_file(conn, jsonl_path)
        assert n2 == 0, f"unchanged file should be skipped, got {n2}"
        # 数据仍然存在
        count = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
        assert count == 5
    finally:
        conn.close()


def test_ingest_rebuild_clears_old_data(tmp_path, monkeypatch):
    mod = _setup_mod(tmp_path, monkeypatch)
    _make_fixture(tmp_path)

    # 第一次全量导入
    mod.ingest(rebuild=False)
    conn = mod._connect()
    try:
        assert conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"] == 5
    finally:
        conn.close()

    # 添加第二个 fixture (不同的 exec_id, 嵌套结构)
    exec_dir2 = tmp_path / "debug" / "20260728" / "Other_Pipeline" / "110000_exec-002"
    exec_dir2.mkdir(parents=True, exist_ok=True)
    jsonl2 = exec_dir2 / "structured.jsonl"
    jsonl2.write_text(
        json.dumps({
            "timestamp": "2026-07-28T11:00:00.000Z",
            "execution_id": "exec-002",
            "node_id": "n1", "node_type": "click",
            "step_index": 0, "event": "node.execute.complete",
            "elapsed_ms": 100.0, "retry_count": 0,
            "success": True, "error_msg": "",
        }) + "\n",
        encoding="utf-8",
    )

    # 增量导入第二个文件
    mod.ingest(rebuild=False)
    conn = mod._connect()
    try:
        assert conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"] == 6
    finally:
        conn.close()

    # rebuild: 清空 + 全量重新导入
    mod.ingest(rebuild=True)
    conn = mod._connect()
    try:
        # 5 + 1 = 6 events, rebuild 后仍是 6 (不是 12)
        assert conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"] == 6
    finally:
        conn.close()


def test_query_filters_by_error_code(tmp_path, monkeypatch):
    mod = _setup_mod(tmp_path, monkeypatch)
    _make_fixture(tmp_path)
    mod.ingest()

    # 构造 args 模拟 --error-code TIMEOUT
    args = type("Args", (), {})()
    args.exec_id = None
    args.node_type = None
    args.event = None
    args.error_code = "TIMEOUT"
    args.pipeline = None
    args.failed_only = False
    args.success_only = False
    args.since = None
    args.until = None
    args.limit = 50

    # 直接调内部查询逻辑 (避免 stdout 干扰)
    conn = mod._connect()
    try:
        where, params = mod._build_where_clause(args)
        sql = (
            "SELECT timestamp, execution_id, node_id, node_type, event, success, "
            "error_code, elapsed_ms, confidence FROM events"
            + where + " ORDER BY timestamp ASC LIMIT ?"
        )
        rows = conn.execute(sql, params + [args.limit]).fetchall()
        assert len(rows) == 1
        assert rows[0]["error_code"] == "TIMEOUT"
        assert rows[0]["node_id"] == "wait_email"
    finally:
        conn.close()


def test_stats_groups_by_error_code(tmp_path, monkeypatch, capsys):
    mod = _setup_mod(tmp_path, monkeypatch)
    _make_fixture(tmp_path)
    mod.ingest()

    args = type("Args", (), {})()
    args.exec_id = None
    args.node_type = None
    args.event = None
    args.error_code = None
    args.pipeline = None
    args.failed_only = False
    args.success_only = False
    args.since = None
    args.until = None
    args.group_by = "error_code"

    mod.stats(args)
    captured = capsys.readouterr()
    # 3 个分组: TIMEOUT (1), NO_MATCH (1), <empty> (1, success path 无 error_code)
    assert "TIMEOUT" in captured.out
    assert "NO_MATCH" in captured.out
    # 失败率 100% (1/1)
    assert "100.0" in captured.out


def test_pipeline_name_extracted_from_dir(tmp_path, monkeypatch):
    mod = _setup_mod(tmp_path, monkeypatch)
    # 嵌套结构: <debug>/<date>/<pipeline>/<HHMMSS_suffix>/structured.jsonl
    # pipeline name 含下划线, 直接作为目录名 (嵌套结构下不需要解析, 直接取祖父目录名)
    exec_dir = tmp_path / "debug" / "20260728" / "Get_Email_New" / "120000_exec-003"
    exec_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = exec_dir / "structured.jsonl"
    jsonl_path.write_text(
        json.dumps({
            "timestamp": "2026-07-28T12:00:00.000Z",
            "execution_id": "exec-003",
            "node_id": "n1", "node_type": "click",
            "step_index": 0, "event": "node.execute.complete",
            "elapsed_ms": 100.0, "retry_count": 0,
            "success": True, "error_msg": "",
        }) + "\n",
        encoding="utf-8",
    )

    conn = mod._connect()
    try:
        mod._ingest_one_file(conn, jsonl_path)
        row = conn.execute(
            "SELECT pipeline_name FROM events WHERE execution_id = ?", ("exec-003",)
        ).fetchone()
        # 嵌套结构: pipeline_name 直接是祖父目录名 (不需要从扁平目录名解析)
        assert row["pipeline_name"] == "Get_Email_New"
    finally:
        conn.close()
