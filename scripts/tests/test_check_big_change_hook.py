"""test_check_big_change_hook.py — TD-321 spec-83 tests.

Tests the B2 pre-commit hook logic:
1. Small change (is_big=false) → hook passes (exit 0)
2. Big change without evidence → hook fails (exit 1)
3. Big change with fresh + is_big=true evidence → hook passes
4. Big change with expired evidence → hook fails
5. Big change without evidence + --no-fail → hook warns only (exit 0)
6. Big change with is_big=false evidence (mismatch) → hook fails
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path
from unittest import mock

# Bootstrap scripts/ import
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import pytest

# Import check_big_change (for evidence write helpers)
from check_big_change import B2_EVIDENCE_FILE, B2_EVIDENCE_TTL_SECONDS, write_b2_evidence
from hooks import check_big_change_hook

pytestmark = pytest.mark.unit


def _make_result(is_big: bool, **overrides) -> dict:
    """Build a fake check_big_change result dict for testing."""
    base = {
        "is_big": is_big,
        "reasons": ["test reason"] if is_big else [],
        "dimensions": {
            "diff_lines": 600 if is_big else 10,
            "cross_app_count": 0,
            "cross_apps": [],
            "migration_files": [],
            "api_contract_files": [],
            "total_changed_files": 1,
        },
        "suggested_flow": "N151 5-step" if is_big else "normal",
    }
    base.update(overrides)
    return base


def _write_evidence(tmp_path: Path, is_big: bool, age_seconds: int = 0) -> Path:
    """Write a fake B2 evidence file with controlled timestamp.

    Patch check_big_change_hook.read_b2_evidence to read from this path.
    """
    ts = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=age_seconds)
    evidence = {
        "timestamp": ts.isoformat(),
        "is_big": is_big,
        "dimensions": {"diff_lines": 600},
        "reasons": ["test"],
    }
    # Patch B2_EVIDENCE_FILE path via mock
    target = B2_EVIDENCE_FILE
    # Bypass actual file write — use mock for read_b2_evidence
    return target


# Tests

def test_small_change_passes(tmp_path):
    """Small change (is_big=false) → hook passes (exit 0)."""
    fake_result = _make_result(is_big=False)
    with mock.patch.object(check_big_change_hook, "check_big_change_staged", return_value=fake_result):
        exit_code = check_big_change_hook.main([])
    assert exit_code == 0


def test_big_change_without_evidence_fails():
    """Big change + no evidence file → hook fails (exit 1)."""
    fake_result = _make_result(is_big=True)
    with mock.patch.object(check_big_change_hook, "check_big_change_staged", return_value=fake_result), \
         mock.patch.object(check_big_change_hook, "read_b2_evidence", return_value=None):
        exit_code = check_big_change_hook.main([])
    assert exit_code == 1


def test_big_change_with_fresh_evidence_passes():
    """Big change + fresh (1 min ago) + is_big=true evidence → hook passes."""
    fake_result = _make_result(is_big=True)
    fake_evidence = {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "is_big": True,
        "dimensions": {"diff_lines": 600},
        "reasons": ["test"],
    }
    with mock.patch.object(check_big_change_hook, "check_big_change_staged", return_value=fake_result), \
         mock.patch.object(check_big_change_hook, "read_b2_evidence", return_value=fake_evidence):
        exit_code = check_big_change_hook.main([])
    assert exit_code == 0


def test_big_change_with_expired_evidence_fails():
    """Big change + expired (> 30 min) evidence → hook fails."""
    fake_result = _make_result(is_big=True)
    expired_ts = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=B2_EVIDENCE_TTL_SECONDS + 60)
    fake_evidence = {
        "timestamp": expired_ts.isoformat(),
        "is_big": True,
        "dimensions": {"diff_lines": 600},
        "reasons": ["test"],
    }
    with mock.patch.object(check_big_change_hook, "check_big_change_staged", return_value=fake_result), \
         mock.patch.object(check_big_change_hook, "read_b2_evidence", return_value=fake_evidence):
        exit_code = check_big_change_hook.main([])
    assert exit_code == 1


def test_big_change_with_no_fail_mode_warns_only():
    """Big change + no evidence + --no-fail → warns but passes (exit 0)."""
    fake_result = _make_result(is_big=True)
    with mock.patch.object(check_big_change_hook, "check_big_change_staged", return_value=fake_result), \
         mock.patch.object(check_big_change_hook, "read_b2_evidence", return_value=None):
        exit_code = check_big_change_hook.main(["--no-fail"])
    assert exit_code == 0


def test_big_change_with_mismatched_evidence_fails():
    """Big change + evidence says is_big=false → hook fails (mismatch)."""
    fake_result = _make_result(is_big=True)
    fake_evidence = {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "is_big": False,  # mismatch — evidence says small, but staged is big
        "dimensions": {"diff_lines": 10},
        "reasons": [],
    }
    with mock.patch.object(check_big_change_hook, "check_big_change_staged", return_value=fake_result), \
         mock.patch.object(check_big_change_hook, "read_b2_evidence", return_value=fake_evidence):
        exit_code = check_big_change_hook.main([])
    assert exit_code == 1


def test_b2_evidence_ttl_constant():
    """B2_EVIDENCE_TTL_SECONDS = 30 * 60 (30 min, as documented)."""
    assert B2_EVIDENCE_TTL_SECONDS == 30 * 60
    assert B2_EVIDENCE_TTL_SECONDS == 1800


def test_write_b2_evidence_creates_file(tmp_path, monkeypatch):
    """write_b2_evidence writes valid JSON with required fields."""
    # Patch B2_EVIDENCE_FILE to a temp path
    fake_path = tmp_path / "b2_acknowledged.json"
    monkeypatch.setattr("check_big_change.B2_EVIDENCE_FILE", fake_path)

    result = _make_result(is_big=True)
    path = write_b2_evidence(result)

    assert path == fake_path
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "timestamp" in data
    assert data["is_big"] is True
    assert data["dimensions"]["diff_lines"] == 600
    assert data["reasons"] == ["test reason"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
