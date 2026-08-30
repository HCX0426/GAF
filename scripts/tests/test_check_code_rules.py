"""test_check_code_rules.py — M1 (2026-08-15) code-rule AST hook tests.

Covers:
1. R001 bare except → exit 1 (error)
2. R001 empty except (pass-only) → exit 1
3. R001 proper except (with logging) → exit 0
4. R002 time.sleep in tests → warn only (exit 0)
5. R003 hardcoded /api/v2 → warn only (exit 0)
6. R004 cursor.execute(f"...") → exit 1
7. R004 cursor.execute(":VAR" param) → exit 0
8. R005 schema residue (max_wait) → warn only (exit 0)
9. --no-fail suppresses failure
10. SyntaxError file → skipped, exit 0
11. no files → exit 0
12. path filters: unrelated.py (outside backend|agent) not scanned
"""
from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap scripts/ import
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import pytest  # noqa: E402
from hooks import check_code_rules  # noqa: E402

pytestmark = pytest.mark.unit

CLEAN_EXCEPT = '''\
def safe_read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError as e:
        print(f"read failed: {e}")
        return ""
'''

BARE_EXCEPT = '''\
def bad_read(path):
    try:
        with open(path) as f:
            return f.read()
    except:
        return ""
'''

EMPTY_EXCEPT = '''\
def bad_read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        pass
'''

SLEEP_TEST = '''\
import time

def wait_some():
    time.sleep(3)
'''

API_V2 = '''\
def build_url():
    return "/api/v2" + "/tasks"
'''

FSTRING_SQL = '''\
def query(cursor, part_no):
    cursor.execute(f"SELECT * FROM part WHERE part_no={part_no}")
'''

PARAM_SQL = '''\
def query(cursor, part_no):
    cursor.execute("SELECT * FROM part WHERE part_no=:VAR", [part_no])
'''

MAX_WAIT_RESIDUE = '''\
def node_config():
    return {"type": "click", "config": {"max_wait": 5}}
'''


def _repo(tmp_path: Path) -> Path:
    """Create a fake git repo dir (minimal .git marker) for root-relative paths."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    return repo


def _write(repo: Path, rel: str, content: str) -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _run(repo: Path, f: Path, *extra: str) -> int:
    return check_code_rules.main([str(f), "--root", str(repo), *extra])


def test_r001_bare_except_fails(tmp_path):
    repo = _repo(tmp_path)
    f = _write(repo, "backend/bare.py", BARE_EXCEPT)
    assert _run(repo, f) == 1


def test_r001_empty_except_fails(tmp_path):
    repo = _repo(tmp_path)
    f = _write(repo, "backend/empty.py", EMPTY_EXCEPT)
    assert _run(repo, f) == 1


def test_r001_proper_except_passes(tmp_path):
    repo = _repo(tmp_path)
    f = _write(repo, "backend/clean.py", CLEAN_EXCEPT)
    assert _run(repo, f) == 0


def test_r002_sleep_is_warn_only(tmp_path):
    repo = _repo(tmp_path)
    f = _write(repo, "backend/tests/test_wait.py", SLEEP_TEST)
    assert _run(repo, f) == 0


def test_r003_api_v2_is_warn_only(tmp_path):
    repo = _repo(tmp_path)
    f = _write(repo, "worker/src/api.py", API_V2)
    assert _run(repo, f) == 0


def test_r004_fstring_sql_fails(tmp_path):
    repo = _repo(tmp_path)
    f = _write(repo, "backend/sql.py", FSTRING_SQL)
    assert _run(repo, f) == 1


def test_r004_param_sql_passes(tmp_path):
    repo = _repo(tmp_path)
    f = _write(repo, "backend/sql_ok.py", PARAM_SQL)
    assert _run(repo, f) == 0


def test_r005_schema_residue_is_warn_only(tmp_path):
    repo = _repo(tmp_path)
    f = _write(repo, "worker/src/schema.py", MAX_WAIT_RESIDUE)
    assert _run(repo, f) == 0


def test_no_fail_suppresses_failure(tmp_path):
    repo = _repo(tmp_path)
    f = _write(repo, "backend/bare2.py", BARE_EXCEPT)
    assert _run(repo, f, "--no-fail") == 0


def test_syntax_error_file_skipped(tmp_path):
    repo = _repo(tmp_path)
    f = _write(repo, "backend/broken.py", "def broken(:\n")
    assert _run(repo, f) == 0


def test_no_files_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert check_code_rules.main([]) == 0


def test_rule_path_filters(tmp_path):
    """R001 path_includes excludes files outside backend/agent."""
    repo = _repo(tmp_path)
    f = _write(repo, "unrelated.py", BARE_EXCEPT)
    assert _run(repo, f) == 0


def test_added_line_ranges_parsing(monkeypatch):
    """_added_line_ranges parses unified=0 hunk headers."""
    class _R:
        returncode = 0

        def __init__(self, text):
            self.stdout = text

    monkeypatch.setattr(
        check_code_rules.subprocess, "run",
        lambda *a, **kw: _R("@@ -10,3 +10,2 @@\n@@ -20 +20,1 @@\n"),
    )
    ranges = check_code_rules._added_line_ranges(REPO_ROOT, "backend/x/y.py")
    assert ranges == [(10, 11), (20, 20)]


def test_added_ranges_map_parsing(monkeypatch):
    """_added_ranges_map parses multi-file unified=0 diff in one call."""
    class _R:
        returncode = 0

        def __init__(self, text):
            self.stdout = text

    diff_text = (
        "diff --git a/backend/a.py b/backend/a.py\n"
        "--- a/backend/a.py\n"
        "+++ b/backend/a.py\n"
        "@@ -1 +1,2 @@\n"
        "diff --git a/backend/b.py b/backend/b.py\n"
        "--- a/backend/b.py\n"
        "+++ b/backend/b.py\n"
        "@@ -10,3 +10,2 @@\n"
    )
    monkeypatch.setattr(
        check_code_rules.subprocess, "run",
        lambda *a, **kw: _R(diff_text),
    )
    ranges = check_code_rules._added_ranges_map(REPO_ROOT)
    assert ranges == {"backend/a.py": [(1, 2)], "backend/b.py": [(10, 11)]}


def test_added_ranges_map_git_failure_returns_none(monkeypatch):
    """git 不可用 (fake repo) → None, main fallback 逐文件探测."""
    class _R:
        returncode = 128
        stdout = ""

    monkeypatch.setattr(
        check_code_rules.subprocess, "run",
        lambda *a, **kw: _R(),
    )
    assert check_code_rules._added_ranges_map(REPO_ROOT) is None


def test_staged_py_files_filters_correctly(monkeypatch):
    """_staged_py_files 只收 backend|agent 的 .py (端到端 endswith 回归)."""
    class _R:
        returncode = 0

        def __init__(self, text):
            self.stdout = text

    fake_out = (
        "backend/tasks/serializers.py\n"
        "backend/config/settings/base.py\n"
        "backend/accounts/migrations/0001_initial.py\n"
        "scripts/hooks/other.py\n"
        "frontend/App.tsx\n"
    )
    monkeypatch.setattr(
        check_code_rules.subprocess, "run",
        lambda *a, **kw: _R(fake_out),
    )
    files = check_code_rules._staged_py_files(REPO_ROOT)
    rels = [str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in files]
    assert rels == [
        "backend/tasks/serializers.py",
        "backend/config/settings/base.py",
        "backend/accounts/migrations/0001_initial.py",
    ]


def test_main_uses_batch_map(monkeypatch, tmp_path):
    """批量 map 生效: 文件不在 map (无新增行) → 不拦截; 在 map → 拦截."""
    repo = _repo(tmp_path)
    f = _write(repo, "backend/bare3.py", BARE_EXCEPT)
    # 模拟 git 不可用 (fake repo), 但 map 由测试注入为空 → 无新增行 → exit 0
    monkeypatch.setattr(check_code_rules, "_added_ranges_map", lambda root: {})
    assert _run(repo, f) == 0
    # 文件在 map 中 (新增行覆盖 except) → exit 1
    monkeypatch.setattr(
        check_code_rules, "_added_ranges_map", lambda root: {"backend/bare3.py": [(1, 5)]}
    )
    assert _run(repo, f) == 1


def test_in_added_ranges_none_means_whole_file():
    assert check_code_rules._in_added_ranges(5, None) is True


def test_in_added_ranges_hit_and_miss():
    ranges = [(10, 20), (30, 40)]
    assert check_code_rules._in_added_ranges(15, ranges) is True
    assert check_code_rules._in_added_ranges(25, ranges) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
