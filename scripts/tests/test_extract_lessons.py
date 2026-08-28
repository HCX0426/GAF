"""test_extract_lessons.py — Unit tests for extract_lessons.py (M0.D / M2.A)

Covers the 4 cases listed in spec.md Appendix G §G.2:
1. test_4_data_sources       — 4 data sources (code-rules / library-conflicts / bug-tracker / git-log) parse without error
2. test_front_matter_generation — generated lessons contain all 5 required front matter fields
3. test_query_index          — lessons index is searchable via --query (fuzzy match)
4. test_draft_non_empty      — draft section character count is ≥ 20 (N85 fix)

Run with:
    pytest GAF/scripts/tests/test_extract_lessons.py -v
or:
    python -m unittest GAF/scripts/tests/test_extract_lessons.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List

import pytest

# Make the parent scripts/ directory importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import extract_lessons  # noqa: E402

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixtures: small synthetic data sources
# ---------------------------------------------------------------------------

SAMPLE_CODE_RULES = """\
---
date: '2026-01-01'
symptom: [code-rules]
---

# Code Rules

## 1. SearchReplace Safety

SearchReplace on CJK files corrupts UTF-8 multibyte characters.
Always verify after editing with `git diff` and use Write tool as fallback.

## 2. PowerShell Limits

PowerShell 5 does not support `&&` operator. Use `;` for statement
chaining, or call commands separately.
"""

SAMPLE_LIBRARY_CONFLICTS = """\
# Library Conflicts

| # | Deprecated API | Correct API | Severity |
|:-:|---------------|-------------|----------|
| 1 | `Modal.destroyOnClose` | `Modal.destroyOnHidden` | Runtime crash |
| 2 | `Space.direction` | `Space.orientation` | Warning |
| 3 | `Input.Group` | `Space.Compact` | Warning |
"""

SAMPLE_BUG_TRACKER = """\
# Bug Tracker

| Bug ID | 标题 | 级别 | 修复于 |
|:------:|------|:----:|:------:|
| BUG-001 | API_TIMEOUT 未定义导致白屏 | P0 | Phase 4 |
| BUG-002 | Vite 缓存导致旧代码错误持续 | P1 | Phase 4 |
"""


def _write_fake_repo(root: Path) -> Path:
    """Build a fake repo with the 3 file sources + a .git directory for git-log."""
    ai_memory = root / ".ai-memory"
    lessons = ai_memory / "lessons"
    summaries = ai_memory / "summaries"
    ops = ai_memory / "ops"
    lessons.mkdir(parents=True)
    summaries.mkdir(parents=True)
    ops.mkdir(parents=True)

    (summaries / "code-rules.md").write_text(SAMPLE_CODE_RULES, encoding="utf-8")
    (summaries / "library-conflicts.md").write_text(SAMPLE_LIBRARY_CONFLICTS, encoding="utf-8")
    (ops / "bug-tracker.md").write_text(SAMPLE_BUG_TRACKER, encoding="utf-8")

    # Fake a git repo so parse_git_log can run.
    import subprocess
    subprocess.check_call(["git", "init", "-q", str(root)], shell=False)
    subprocess.check_call(
        ["git", "-C", str(root), "config", "user.email", "test@test"],
        shell=False,
    )
    subprocess.check_call(
        ["git", "-C", str(root), "config", "user.name", "test"],
        shell=False,
    )
    subprocess.check_call(["git", "-C", str(root), "add", "-A"], shell=False)
    subprocess.check_call(
        ["git", "-C", str(root), "commit", "-m", "initial: bootstrap", "-q"],
        shell=False,
    )
    subprocess.check_call(
        ["git", "-C", str(root), "commit", "--allow-empty", "-m", "feat: add lesson extractor", "-q"],
        shell=False,
    )
    return root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExtractLessons(unittest.TestCase):
    """4-test suite for extract_lessons (Appendix G §G.2)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.fake_root = _write_fake_repo(self.tmp_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ---- 1. 4 data sources ------------------------------------------------

    def test_4_data_sources(self) -> None:
        """All 4 data sources parse without error and return ≥ 1 item each."""
        by_source = extract_lessons.build_all(self.fake_root)
        # 3 file-based sources must return lists
        for source in ("code-rules", "library-conflicts", "bug-tracker"):
            self.assertIn(source, by_source, f"missing source: {source}")
            self.assertIsInstance(by_source[source], list, f"{source} not a list")
            self.assertGreater(
                len(by_source[source]), 0,
                f"{source} returned 0 items (expected ≥ 1)",
            )
        # git-log returns a list (may be empty if git is unavailable, but
        # our setUp seeded commits, so we expect 2).
        self.assertIn("git-log", by_source)
        self.assertIsInstance(by_source["git-log"], list)
        self.assertGreaterEqual(
            len(by_source["git-log"]), 1,
            "git-log returned 0 items (expected ≥ 1, setUp added 2 commits)",
        )
        # Verify source tag on at least one item from each parser
        for source in ("code-rules", "library-conflicts", "bug-tracker", "git-log"):
            for item in by_source[source]:
                self.assertEqual(item["source"], source)

    # ---- 2. front matter generation --------------------------------------

    def test_front_matter_generation(self) -> None:
        """Generated lesson drafts contain all 5 required front matter fields."""
        by_source = extract_lessons.build_all(self.fake_root)
        for source, items in by_source.items():
            self.assertGreater(len(items), 0, f"{source} returned 0 items")
            for item in items:
                draft = extract_lessons.build_lesson_draft(item)
                # Front matter must be present
                self.assertTrue(
                    draft.startswith("---\n"),
                    f"{source}: draft missing opening `---`",
                )
                # All 5 required fields must appear
                is_valid, missing = extract_lessons._check_front_matter(draft)
                self.assertTrue(
                    is_valid,
                    f"{source}: front matter missing fields {missing}",
                )
                # Also sanity-check the maintainer is `auto` and created_by is `AI`
                self.assertIn("maintainer: auto", draft)
                self.assertIn("created_by: AI", draft)

    # ---- 3. query index ---------------------------------------------------

    def test_query_index(self) -> None:
        """The lessons index is searchable via `--query` (fuzzy match)."""
        by_source = extract_lessons.build_all(self.fake_root)
        # Write index to the tmp INDEX_PATH
        index = extract_lessons.build_index(by_source)
        self.assertGreater(len(index), 0, "index is empty")
        # Every entry must have file / symptom / solution / source
        for entry in index:
            for field in ("file", "symptom", "solution", "source"):
                self.assertIn(field, entry, f"index entry missing field: {field}")

        # Query: 'bug' should match bug-tracker entries
        bug_hits = extract_lessons.query_index("bug", index=index)
        self.assertGreater(len(bug_hits), 0, "query 'bug' returned 0 hits")
        for hit in bug_hits:
            self.assertEqual(hit["source"], "bug-tracker")

        # Query: 'api' should match library-conflicts (api-related deprecated APIs)
        api_hits = extract_lessons.query_index("api", index=index)
        self.assertGreater(len(api_hits), 0, "query 'api' returned 0 hits")

        # Query: 'popup' should return 0 hits (not in any of the 3 sample sources)
        popup_hits = extract_lessons.query_index("popup", index=index)
        self.assertEqual(len(popup_hits), 0, "query 'popup' unexpectedly matched")

        # Empty query returns the full index
        all_hits = extract_lessons.query_index("", index=index)
        self.assertEqual(len(all_hits), len(index))

    # ---- 4. draft non-empty (N85 fix) -------------------------------------

    def test_draft_non_empty(self) -> None:
        """The `## 症状` draft section must be ≥ 20 characters (N85 fix)."""
        by_source = extract_lessons.build_all(self.fake_root)
        for source, items in by_source.items():
            self.assertGreater(len(items), 0, f"{source} returned 0 items")
            for item in items:
                draft = extract_lessons.build_lesson_draft(item)
                # Find the `## 症状` section
                marker = "## 症状"
                idx = draft.find(marker)
                self.assertNotEqual(
                    idx, -1,
                    f"{source}: draft missing `## 症状` section",
                )
                tail = draft[idx + len(marker):]
                # Section ends at the next `## ` heading or EOF
                next_heading = tail.find("\n## ")
                section = tail if next_heading == -1 else tail[:next_heading]
                section = section.strip()
                self.assertGreaterEqual(
                    len(section), 20,
                    f"{source}: draft `## 症状` section is < 20 chars "
                    f"(N85 fix violated): {section!r}",
                )


if __name__ == "__main__":
    unittest.main()
