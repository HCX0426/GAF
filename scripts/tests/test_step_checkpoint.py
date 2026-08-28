"""test_step_checkpoint.py — Unit tests for scripts/step_checkpoint.py (B1 治本机制).

Covers the 5 core paths required by TD-317:
1. test_mark_checkpoint_writes_file      — mark 命令正确写入 checkpoint 文件
2. test_next_step_returns_next           — next 命令返回正确的下一步
3. test_list_active_filters_done         — list 命令列出活跃任务 (过滤 done)
4. test_mark_done_sets_status            — done 命令标记任务完成
5. test_checkpoint_persistence_roundtrip — checkpoint 文件持久化 + 读取
6. test_next_step_after_last_returns_none — 走到最后一步后返回 None
7. test_read_checkpoint_missing_returns_none — 不存在的 task_id 返回 None
8. test_checkpoint_path_sanitizes_separators — task_id 含 / 或 \\ 时路径被清理

Run with: pytest scripts/tests/test_step_checkpoint.py -v
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Make scripts/ importable without installing as a package.
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

import step_checkpoint  # noqa: E402


@pytest.fixture()
def temp_session_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect step_checkpoint.SESSION_DIR to a temp dir for isolation."""
    session = tmp_path / "session"
    session.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(step_checkpoint, "SESSION_DIR", session)
    return session


# ---------------------------------------------------------------------------
# 1. mark command writes checkpoint file
# ---------------------------------------------------------------------------


def test_mark_checkpoint_writes_file(temp_session_dir: Path) -> None:
    """write_checkpoint should create a JSON file with all fields populated."""
    path = step_checkpoint.write_checkpoint("spec-81-P3", "new_feature", "step_3_load_kb")
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["task_id"] == "spec-81-P3"
    assert data["task_type"] == "new_feature"
    assert data["last_step"] == "step_3_load_kb"
    assert data["status"] == "in_progress"
    assert "timestamp" in data and data["timestamp"]


# ---------------------------------------------------------------------------
# 2. next step returns correct next step
# ---------------------------------------------------------------------------


def test_next_step_returns_next(temp_session_dir: Path) -> None:
    """next_step should return the step after the last completed step."""
    step_checkpoint.write_checkpoint("task-A", "bug_fix", "step_4_diagnose")
    ns = step_checkpoint.next_step("task-A")
    # STEP_ORDER["bug_fix"] = [..., step_4_diagnose, step_5_fix_and_reflect, ...]
    assert ns == "step_5_fix_and_reflect"


def test_next_step_after_last_returns_none(temp_session_dir: Path) -> None:
    """When last_step is the final step, next_step returns None."""
    last_step = step_checkpoint.STEP_ORDER["new_feature"][-1]
    step_checkpoint.write_checkpoint("task-B", "new_feature", last_step)
    assert step_checkpoint.next_step("task-B") is None


# ---------------------------------------------------------------------------
# 3. list_active filters out done tasks
# ---------------------------------------------------------------------------


def test_list_active_filters_done(temp_session_dir: Path) -> None:
    """list_active should only return tasks whose status != 'done'."""
    step_checkpoint.write_checkpoint("task-active-1", "new_feature", "step_1")
    step_checkpoint.write_checkpoint("task-active-2", "refactor", "step_2_read_context")
    step_checkpoint.write_checkpoint("task-done-1", "documentation", "step_4_write",
                                     status="done")
    active = step_checkpoint.list_active()
    ids = {cp["task_id"] for cp in active}
    assert ids == {"task-active-1", "task-active-2"}
    assert "task-done-1" not in ids


# ---------------------------------------------------------------------------
# 4. done command marks task done
# ---------------------------------------------------------------------------


def test_mark_done_sets_status(temp_session_dir: Path) -> None:
    """mark_done should rewrite the checkpoint with status='done'."""
    step_checkpoint.write_checkpoint("task-C", "refactor", "step_5_execute")
    assert step_checkpoint.mark_done("task-C") is True
    cp = step_checkpoint.read_checkpoint("task-C")
    assert cp is not None
    assert cp["status"] == "done"
    # task_type and last_step must be preserved.
    assert cp["task_type"] == "refactor"
    assert cp["last_step"] == "step_5_execute"


def test_mark_done_missing_returns_false(temp_session_dir: Path) -> None:
    """mark_done on a non-existent task_id returns False."""
    assert step_checkpoint.mark_done("nonexistent-task") is False


# ---------------------------------------------------------------------------
# 5. checkpoint persistence (write → read roundtrip)
# ---------------------------------------------------------------------------


def test_checkpoint_persistence_roundtrip(temp_session_dir: Path) -> None:
    """read_checkpoint should return exactly the fields written."""
    step_checkpoint.write_checkpoint("persist-1", "documentation", "step_4_write")
    # Simulate "fresh process" by reading back from disk.
    cp = step_checkpoint.read_checkpoint("persist-1")
    assert cp is not None
    assert cp["task_id"] == "persist-1"
    assert cp["task_type"] == "documentation"
    assert cp["last_step"] == "step_4_write"
    # File path must match checkpoint_path() convention.
    expected_path = step_checkpoint.checkpoint_path("persist-1")
    assert expected_path.exists()


# ---------------------------------------------------------------------------
# Bonus: edge cases
# ---------------------------------------------------------------------------


def test_read_checkpoint_missing_returns_none(temp_session_dir: Path) -> None:
    """read_checkpoint returns None when the file does not exist."""
    assert step_checkpoint.read_checkpoint("no-such-task") is None


def test_checkpoint_path_sanitizes_separators() -> None:
    r"""task_id containing / or \ should be sanitized in the file name."""
    path = step_checkpoint.checkpoint_path("spec/sub\\task")
    # Separator characters were replaced with underscore.
    assert path.name == "spec_sub_task.json"
