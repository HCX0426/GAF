"""test_match_lessons_by_diff.py — M3 (2026-08-15) diff→lesson 触发式检索测试.

Covers:
1. _parse_front_matter: 标量值 + 列表值 + 缺 front matter
2. load_lessons: 只加载含 diff_keywords 的 lesson, 忽略 README
3. score_lessons: diff_keywords 命中 +3, related_files 命中 +2, 排序
4. main(): 无改动 → 0; 指定文件无匹配 → 0
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

from scripts.lessons import match_lessons_by_diff as m  # noqa: E402

pytestmark = pytest.mark.unit


def test_parse_front_matter_scalar_and_list():
    text = """---
date: 2026-08-15
topic: [workflow]
diff_keywords: [sql-injection, cursor-execute]
related_files:
  - backend/tasks/backup_views.py
  - backend/tasks/tests/test_backup_restore.py
---
body
"""
    data = m._parse_front_matter(text)
    assert data["date"] == "2026-08-15"
    assert data["diff_keywords"] == ["sql-injection", "cursor-execute"]
    assert data["related_files"] == [
        "backend/tasks/backup_views.py",
        "backend/tasks/tests/test_backup_restore.py",
    ]


def test_parse_front_matter_no_fm():
    assert m._parse_front_matter("# no front matter\n") == {}


def test_load_lessons_filters(tmp_path):
    (tmp_path / "README.md").write_text("index", encoding="utf-8")
    (tmp_path / "with-kw.md").write_text(
        "---\ndiff_keywords: [abc]\nrelated_files:\n  - backend/x.py\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "no-kw.md").write_text("---\ncreated_by: AI\n---\n", encoding="utf-8")
    lessons = m.load_lessons(tmp_path)
    assert [n["path"] for n in lessons] == ["with-kw.md"]
    assert lessons[0]["diff_keywords"] == ["abc"]


def test_load_lessons_reads_archived_subdir(tmp_path):
    (tmp_path / "archived-early").mkdir()
    (tmp_path / "archived-early" / "N168.md").write_text(
        "---\ndiff_keywords: [sql-injection]\n---\n", encoding="utf-8"
    )
    lessons = m.load_lessons(tmp_path)
    assert [n["path"] for n in lessons] == ["archived-early/N168.md"]


def _lesson(path: str, kws: list[str], files: list[str]) -> dict:
    return {
        "path": path,
        "diff_keywords": [k.lower() for k in kws],
        "related_files": [f.lower() for f in files],
    }


def test_score_keyword_hit():
    lessons = [_lesson("N168.md", ["sql-injection"], ["backend/tasks/backup_views.py"])]
    scored = m.score_lessons(
        lessons,
        ["backend/tasks/backup_views.py"],
        {"sql", "injection"},
        ["# sql-injection: avoid f-string in cursor.execute"],
    )
    assert len(scored) == 1
    assert scored[0]["score"] == 5  # 3 (kw 命中新增行原文) + 2 (related file)


def test_score_path_and_content_weights():
    lessons = [
        _lesson("A.md", ["kw"], []),
        _lesson("B.md", [], ["backend/tasks/x.py"]),
    ]
    scored = m.score_lessons(lessons, ["backend/tasks/x.py"], {"kw", "only"}, [])
    assert scored[0]["path"] == "A.md"
    assert scored[0]["score"] == 3
    assert scored[1]["path"] == "B.md"
    assert scored[1]["score"] == 2


def test_score_no_match_empty():
    lessons = [_lesson("A.md", ["zzz"], ["nope.py"])]
    assert m.score_lessons(lessons, ["other/x.py"], {"other"}, []) == []


def test_score_case_insensitive():
    lessons = [_lesson("A.md", ["SQL-Injection"], [])]
    scored = m.score_lessons(lessons, ["backend/x.py"], {"sql-injection"}, [])
    assert len(scored) == 1


def test_main_no_changed_files(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(m, "LESSONS_DIR", tmp_path)
    monkeypatch.setattr(m, "_git", lambda *a, **kw: "")
    assert m.main([]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
