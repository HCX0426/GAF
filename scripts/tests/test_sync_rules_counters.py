"""TD-392 — _sync_rules_counters 自动维护 active/retired/next_n_id 计数。"""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]  # repo root
sys.path.insert(0, str(_REPO / "scripts"))
sys.path.insert(0, str(_REPO / "scripts" / "bootstrap"))

from ai_memory_sync.counters import _sync_rules_counters  # noqa: E402


def _mk_fm(tmp: Path) -> None:
    p = tmp / ".ai-memory" / "meta" / "failure-modes.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(
            [
                "## Active N## 索引表",
                "| N100 | a |",
                "| N101 | b |",
                "### Archived-Early N## 索引",
                "## Retired N## 索引",
                "| N50 | c |",
                "## Dormant N## 索引",
                "| N5/N6 | d |",
            ]
        ),
        encoding="utf-8",
    )


def _mk_readme(tmp: Path, fm: str) -> None:
    p = tmp / ".ai-memory" / "lessons" / "README.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}---\n# L\n", encoding="utf-8")


def _mk_lesson(tmp: Path, name: str, nid: str) -> None:
    p = tmp / ".ai-memory" / "lessons" / name
    # n_id placed after a long symptom block (>400 chars) to exercise the
    # frontmatter-parse fix (前一版 read 前 400 字符会漏扫 N208 型 long frontmatter)
    p.write_text(f"---\nsymptom:\n- {'x' * 500}\nn_id: {nid}\n---\n# x\n", encoding="utf-8")


def test_counters_updates_fields(tmp_path: Path) -> None:
    _mk_fm(tmp_path)
    _mk_readme(tmp_path, "lessons_count: 0\nactive_n_count: 0\nretired_n_count: 0\nnext_n_id: 0\n")
    _mk_lesson(tmp_path, "N200-a.md", "N200")
    _mk_lesson(tmp_path, "N202-b.md", "N202")
    assert _sync_rules_counters(tmp_path, dry_run=False) is True
    t = (tmp_path / ".ai-memory" / "lessons" / "README.md").read_text(encoding="utf-8")
    assert "active_n_count: 2" in t
    assert "retired_n_count: 1" in t
    assert "next_n_id: 203" in t


def test_counters_idempotent(tmp_path: Path) -> None:
    _mk_fm(tmp_path)
    _mk_readme(tmp_path, "lessons_count: 0\nactive_n_count: 2\nretired_n_count: 1\nnext_n_id: 203\n")
    _mk_lesson(tmp_path, "N200-a.md", "N200")
    _mk_lesson(tmp_path, "N202-b.md", "N202")
    # 初始即正确 → 无改动
    assert _sync_rules_counters(tmp_path, dry_run=False) is False