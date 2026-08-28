"""test_sync_changelog.py — Tests for the M1.H decision-tree changelog.

These tests cover the five contract promises of
`sync_skills.append_changelog_entry` and the related helpers:

1. **Header bootstrap** — when the changelog file is missing, the
   first call writes a full frontmatter + table header + first entry.
2. **Idempotency** — calling `append_changelog_entry` twice with the
   same SKILL.md content appends only once (the second call is a no-op).
3. **Hash change detection** — modifying the SKILL.md between calls
   appends a new row with the new hash and the previous row's hash
   in the `old_hash` column.
4. **Last-hash extraction** — `_read_changelog_last_hash` returns the
   right-most hash from the most recent data row.
5. **Note escaping** — `_build_changelog_entry` escapes pipe characters
   in the note so the table layout stays valid.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from sync_skills import (  # noqa: E402
    _build_changelog_entry,
    _extract_decision_tree_block_hash,
    _read_changelog_last_hash,
    append_changelog_entry,
)

pytestmark = pytest.mark.unit

SAMPLE_SKILL = """---
name: gaf-orchestrator
version: 8.4
---
# gaf-orchestrator

## Decision Tree

```yaml
new_feature:
  step_1: "read context"
bug_fix:
  step_1: "search lessons"
```

## End Decision Tree

## After

postamble that is not part of the decision tree block.
"""


MODIFIED_SKILL = """---
name: gaf-orchestrator
version: 8.4
---
# gaf-orchestrator

## Decision Tree

```yaml
new_feature:
  step_1: "read context"
  step_2: "new step (M1.H)"
bug_fix:
  step_1: "search lessons"
```

## End Decision Tree

## After

postamble.
"""


class ChangelogBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.skill_path = self.tmp_path / "SKILL.md"
        self.skill_path.write_text(SAMPLE_SKILL, encoding="utf-8")
        self.changelog_path = self.tmp_path / "decision-tree-changelog.md"

    def test_header_bootstrap_creates_file_with_first_entry(self):
        """Missing changelog → bootstrap frontmatter + table + first row."""
        self.assertFalse(self.changelog_path.exists())

        appended, old_hash, new_hash = append_changelog_entry(
            self.changelog_path, self.skill_path, note="M1.H init",
        )
        self.assertTrue(appended)
        self.assertEqual(old_hash, "")
        self.assertEqual(new_hash, _extract_decision_tree_block_hash(self.skill_path))

        content = self.changelog_path.read_text(encoding="utf-8")
        self.assertIn("---", content)
        self.assertIn("maintainer: auto", content)
        self.assertIn("| # | date | old_hash | new_hash | note | author |", content)
        self.assertIn("| 1 | ", content)
        self.assertIn("M1.H init", content)
        self.assertIn("| (initial) |", content)

    def test_idempotent_when_block_unchanged(self):
        """Same SKILL.md twice → second call is a no-op."""
        append_changelog_entry(self.changelog_path, self.skill_path, note="init")
        appended, old_hash, new_hash = append_changelog_entry(
            self.changelog_path, self.skill_path, note="again",
        )
        self.assertFalse(appended)
        self.assertEqual(old_hash, new_hash)

        content = self.changelog_path.read_text(encoding="utf-8")
        # Only one data row should exist.
        self.assertEqual(content.count("| 1 |"), 1)
        self.assertNotIn("again", content)

    def test_hash_change_appends_new_row_with_previous_hash(self):
        """Modified SKILL.md → new row with old_hash pointing to the last row."""
        append_changelog_entry(self.changelog_path, self.skill_path, note="v1")
        original_hash = _extract_decision_tree_block_hash(self.skill_path)

        self.skill_path.write_text(MODIFIED_SKILL, encoding="utf-8")
        appended, old_hash, new_hash = append_changelog_entry(
            self.changelog_path, self.skill_path, note="M1.H step_2 added",
        )
        self.assertTrue(appended)
        self.assertEqual(old_hash, original_hash)
        self.assertNotEqual(new_hash, original_hash)

        content = self.changelog_path.read_text(encoding="utf-8")
        self.assertIn("| 2 | ", content)
        self.assertIn(original_hash, content)
        self.assertIn(new_hash, content)
        self.assertIn("M1.H step_2 added", content)


class ChangelogHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.skill_path = self.tmp_path / "SKILL.md"
        self.skill_path.write_text(SAMPLE_SKILL, encoding="utf-8")
        self.changelog_path = self.tmp_path / "decision-tree-changelog.md"

    def test_read_last_hash_returns_rightmost_hash(self):
        """_read_changelog_last_hash returns the most recent new_hash."""
        append_changelog_entry(self.changelog_path, self.skill_path, note="v1")
        self.skill_path.write_text(MODIFIED_SKILL, encoding="utf-8")
        append_changelog_entry(self.changelog_path, self.skill_path, note="v2")

        last = _read_changelog_last_hash(self.changelog_path)
        self.assertEqual(last, _extract_decision_tree_block_hash(self.skill_path))
        self.assertNotEqual(last, "")

    def test_note_escapes_pipe_characters(self):
        """_build_changelog_entry escapes '|' in the note to keep the table valid."""
        row = _build_changelog_entry(
            entry_no=1, today="2026-06-16",
            old_hash="", new_hash="abcd1234efgh5678",
            note="block | with | pipes",
        )
        # 7 unescaped '|' separators (6 columns + trailing), plus 2 escaped
        # pipes in the note (each is rendered as the two-char sequence '\|'
        # which still contains one '|' character).
        self.assertEqual(row.count("|"), 7 + 2)
        self.assertIn("block \\| with \\| pipes", row)


class DecisionTreeBlockHashTests(unittest.TestCase):
    def test_block_hash_changes_when_block_changes(self):
        """Block hash is sensitive to changes inside the decision tree block."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            skill_path = tmp_path / "SKILL.md"
            skill_path.write_text(SAMPLE_SKILL, encoding="utf-8")
            h1 = _extract_decision_tree_block_hash(skill_path)
            skill_path.write_text(MODIFIED_SKILL, encoding="utf-8")
            h2 = _extract_decision_tree_block_hash(skill_path)
            self.assertNotEqual(h1, h2)
            self.assertEqual(len(h1), 16)
            self.assertEqual(len(h2), 16)


if __name__ == "__main__":
    unittest.main()
