"""test_check_doc_code_sync.py — TD-325 spec-87 tests.

Tests the code-doc causal binding pre-commit hook:
1. 普通 commit (非触发文件) → PASS
2. urls.py 变更 + api-contract.md 未同步 → HARD FAIL
3. urls.py + api-contract.md 同步 staged → PASS
4. urls.py + api-contract.md 最近 1h 内 commit → PASS
5. models.py 字段变更 → HARD FAIL
6. 新增 backend app (apps.py added) → WARN
7. 模块重命名 (R status) → HARD FAIL
8. [skip-doc-sync] commit message → 跳过硬阻断 + 写 skip record
9. urls.py 只改注释 → PASS (内容快扫不命中)
10. --no-fail 模式 → HARD FAIL 降级为 WARN
"""
from __future__ import annotations

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

from hooks import check_doc_code_sync
from hooks.doc_sync_rules import RULES, DocSyncRule, match_rules

pytestmark = pytest.mark.unit


# ---------- rule table sanity tests ----------


def test_rules_count_and_ids():
    """规则表有 7 条规则, ID 为 R1..R7."""
    assert len(RULES) == 7
    ids = [r.id for r in RULES]
    assert ids == ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]


def test_match_rules_urls_py():
    """backend/accounts/urls.py (M) 命中 R1."""
    hits = match_rules("backend/accounts/urls.py", "M")
    assert any(r.id == "R1" for r in hits)


def test_match_rules_models_py():
    """backend/accounts/models.py (M) 命中 R2."""
    hits = match_rules("backend/accounts/models.py", "M")
    assert any(r.id == "R2" for r in hits)


def test_match_rules_new_app_apps_py():
    """backend/newapp/apps.py (A) 命中 R3."""
    hits = match_rules("backend/newapp/apps.py", "A")
    assert any(r.id == "R3" for r in hits)


def test_match_rules_rename_any_file():
    """任意文件 rename (R100) 命中 R4."""
    hits = match_rules("backend/accounts/services.py", "R100")
    assert any(r.id == "R4" for r in hits)


def test_match_rules_frontend_api_ts():
    """frontend/src/api/devices.ts (M) 命中 R5."""
    hits = match_rules("frontend/src/api/devices.ts", "M")
    assert any(r.id == "R5" for r in hits)


def test_match_rules_new_spec_md():
    """docs/specs/legacy-trae/new-spec.md (A) 命中 R6."""
    hits = match_rules("docs/specs/legacy-trae/2026-07-22-spec88-test.md", "A")
    assert any(r.id == "R6" for r in hits)


def test_match_rules_settings_py():
    """backend/config/settings/base.py (M) 命中 R7."""
    hits = match_rules("backend/config/settings/base.py", "M")
    assert any(r.id == "R7" for r in hits)


def test_match_rules_non_trigger_file():
    """backend/accounts/views.py (M) 不命中任何规则."""
    hits = match_rules("backend/accounts/views.py", "M")
    assert hits == []


# ---------- hook main() tests ----------


def _mock_staged(files: list[tuple[str, str]]):
    """Mock _get_staged_files to return given [(status, filepath), ...]."""
    return mock.patch.object(check_doc_code_sync, "_get_staged_files", return_value=files)


def _mock_content_scan(hit: bool):
    """Mock _scan_diff_content to always return hit (True) or miss (False)."""
    return mock.patch.object(check_doc_code_sync, "_scan_diff_content", return_value=hit)


def _mock_verify_doc(synced: bool):
    """Mock _verify_doc_synced to always return synced (True/False)."""
    return mock.patch.object(check_doc_code_sync, "_verify_doc_synced", return_value=synced)


def _mock_skip_token(active: bool):
    """Mock _check_skip_token to return active state."""
    return mock.patch.object(check_doc_code_sync, "_check_skip_token", return_value=active)


def test_typical_commit_no_trigger():
    """普通 .py 变更 (非触发文件) → PASS exit 0."""
    with _mock_staged([("M", "backend/accounts/views.py"), ("M", "README.md")]):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 0


def test_urls_py_change_no_doc_sync():
    """urls.py 变更 + 内容命中 + api-contract.md 未同步 → HARD FAIL exit 1."""
    with _mock_staged([("M", "backend/accounts/urls.py")]), \
         _mock_content_scan(True), \
         _mock_verify_doc(False), \
         _mock_skip_token(False):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 1


def test_urls_py_change_with_doc_staged():
    """urls.py + api-contract.md 同步 staged → PASS exit 0."""
    with _mock_staged([
        ("M", "backend/accounts/urls.py"),
        ("M", "docs/standards/api-contract.md"),
    ]), \
         _mock_content_scan(True), \
         _mock_verify_doc(True), \
         _mock_skip_token(False):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 0


def test_urls_py_change_with_doc_recent_commit():
    """api-contract.md 最近 1h 内 commit → PASS exit 0 (verify_doc 返回 True)."""
    with _mock_staged([("M", "backend/accounts/urls.py")]), \
         _mock_content_scan(True), \
         _mock_verify_doc(True), \
         _mock_skip_token(False):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 0


def test_models_py_change_hard_fail():
    """models.py 字段变更 (内容命中) + backend-conventions.md 未同步 → HARD FAIL."""
    with _mock_staged([("M", "backend/accounts/models.py")]), \
         _mock_content_scan(True), \
         _mock_verify_doc(False), \
         _mock_skip_token(False):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 1


def test_new_app_directory_warn():
    """新增 backend/newapp/apps.py (A 状态) → WARN exit 0 (不扫内容, 不验文档)."""
    with _mock_staged([("A", "backend/newapp/apps.py")]), \
         _mock_skip_token(False):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 0  # warn 不阻断


def test_module_rename_hard_fail():
    """模块重命名 (R 状态) → HARD FAIL exit 1 (R4, 无 required_docs)."""
    with _mock_staged([("R100", "backend/accounts/services.py")]), \
         _mock_skip_token(False):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 1


def test_skip_token_skips_hard_fail(tmp_path, monkeypatch):
    """commit message 含 [skip-doc-sync] → 硬阻断降级为 WARN + 写 skip record."""
    # Mock skip record path to temp
    fake_record = tmp_path / "doc_sync_skips.json"
    monkeypatch.setattr(check_doc_code_sync, "SKIP_RECORD_FILE", fake_record)

    with _mock_staged([("M", "backend/accounts/urls.py")]), \
         _mock_content_scan(True), \
         _mock_verify_doc(False), \
         _mock_skip_token(True):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 0  # skipped → exit 0
    # skip record written
    assert fake_record.is_file()
    data = json.loads(fake_record.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1
    assert "R1" in data[0]["rules"]
    assert "timestamp" in data[0]


def test_comment_only_change_passes():
    """urls.py 只改注释 (内容快扫不命中) → PASS exit 0."""
    with _mock_staged([("M", "backend/accounts/urls.py")]), \
         _mock_content_scan(False), \
         _mock_skip_token(False):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 0


def test_no_fail_mode_warns_only():
    """--no-fail 模式 → HARD FAIL 降级为 WARN, exit 0."""
    with _mock_staged([("M", "backend/accounts/urls.py")]), \
         _mock_content_scan(True), \
         _mock_verify_doc(False), \
         _mock_skip_token(False):
        exit_code = check_doc_code_sync.main(["--no-fail"])
    assert exit_code == 0


def test_no_staged_files_passes():
    """无 staged 文件 → PASS exit 0."""
    with _mock_staged([]):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 0


def test_frontend_api_ts_warn():
    """frontend/src/api/devices.ts 变更 (warn 规则) + 内容命中 + 文档未同步 → WARN exit 0."""
    with _mock_staged([("M", "frontend/src/api/devices.ts")]), \
         _mock_content_scan(True), \
         _mock_verify_doc(False), \
         _mock_skip_token(False):
        exit_code = check_doc_code_sync.main([])
    assert exit_code == 0  # warn 不阻断


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
