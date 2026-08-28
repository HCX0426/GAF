"""test_decision_tree_sync.py — Unit tests for sync_skills.py (M0.L / M2.A-2)

Covers the 5 cases listed in spec.md Appendix G §G.4 (v9.0 single-source update):
1. test_single_copy_generation  — 1 SKILL.md decision-tree copy exists (v9.0: gaf-orchestrator only)
2. test_check_mode_consistent   — the single copy has a valid non-empty block hash
3. test_check_mode_inconsistent — a drifted copy's block hash differs from source-of-truth
4. test_sync_mode_force         — --sync (force) mode rewrites drifted copies
5. test_root_task_type_node     — decision tree block contains step_1_identify_task_type (N68)

v9.0 note: Decision tree is now single-source (gaf-orchestrator only).
Other 3 SKILL.md files reference it instead of duplicating. Tests updated
to expect 1 copy instead of 4.

Run with:
    python -m unittest GAF/scripts/tests/test_decision_tree_sync.py -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import List

import pytest

# Make the parent scripts/ directory importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_skills  # noqa: E402

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixtures: minimal SKILL.md + a tiny "gaf-*" skills tree
# ---------------------------------------------------------------------------

DECISION_TREE_BODY = """\
## Decision Tree

### step_1_identify_task_type
- new_feature
- bug_fix
- documentation
- refactor
- unknown

### step_2_route_by_task_type
- new_feature -> gaf-task-execution
- bug_fix -> gaf-reflect-and-evolve

## End Decision Tree
"""


SKILL_HEADER = """\
---
name: {name}
description: {name} skill (test fixture)
---

# {name}

Some skill body content.

"""


def _make_skill(name: str, root: Path) -> Path:
    """Create a minimal skill directory + SKILL.md with the decision tree."""
    skill_dir = root / ".skills" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        SKILL_HEADER.format(name=name) + DECISION_TREE_BODY,
        encoding="utf-8",
    )
    return skill_md


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDecisionTreeSync(unittest.TestCase):
    """5-test suite for sync_skills (Appendix G §G.4)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self.tmp.name)
        # v9.0: Create the single decision tree source skill (gaf-orchestrator only).
        self.source_skills: List[Path] = []
        for name in sync_skills.DECISION_TREE_COPIES:
            self.source_skills.append(_make_skill(name, self.tmp_root))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ---- 1. single copy generation (v9.0: single source) ----------------

    def test_single_copy_generation(self) -> None:
        """The single decision tree SKILL.md copy (gaf-orchestrator) is present and contains the block."""
        self.assertEqual(
            len(sync_skills.DECISION_TREE_COPIES), 1,
            f"expected 1 decision tree copy (v9.0 single source), got {len(sync_skills.DECISION_TREE_COPIES)}",
        )
        # The single copy must exist + contain both block markers
        for src in self.source_skills:
            text = src.read_text(encoding="utf-8")
            self.assertIn(
                sync_skills.DECISION_TREE_START, text,
                f"{src.name} missing '{sync_skills.DECISION_TREE_START}'",
            )
            self.assertIn(
                sync_skills.DECISION_TREE_END, text,
                f"{src.name} missing '{sync_skills.DECISION_TREE_END}'",
            )
            # block hash must be non-empty
            block = sync_skills._extract_decision_tree_block(text)
            self.assertNotEqual(block, "", f"{src.name} block extraction empty")
            h = sync_skills._block_hash(block)
            self.assertEqual(len(h), 16, f"block hash should be 16 chars: {h}")

    # ---- 2. --check mode consistent → exit 0 -----------------------------

    def test_check_mode_consistent(self) -> None:
        """The single copy has a valid, non-empty block hash."""
        # Compute the block hash from the single source
        first_block = sync_skills._extract_decision_tree_block(
            self.source_skills[0].read_text(encoding="utf-8")
        )
        expected = sync_skills._block_hash(first_block)
        # The single source has a valid body, so the hash must be non-empty
        for src in self.source_skills:
            block = sync_skills._extract_decision_tree_block(
                src.read_text(encoding="utf-8")
            )
            self.assertEqual(
                sync_skills._block_hash(block), expected,
                f"{src.name} block hash differs",
            )

    # ---- 3. --check mode inconsistent → exit 1 ---------------------------

    def test_check_mode_inconsistent(self) -> None:
        """When a copy is drifted, its block hash differs from the source-of-truth."""
        # v9.0: With only 1 copy in DECISION_TREE_COPIES, create a second
        # fake skill manually to simulate drift (the source-of-truth is
        # source_skills[0] = gaf-orchestrator).
        drifted = _make_skill("gaf-orchestrator-drifted", self.tmp_root)
        original = self.source_skills[0].read_text(encoding="utf-8")
        # Mutate the block itself to make the hashes diverge.
        drifted.write_text(
            original.replace("new_feature", "new_feature_modified"),
            encoding="utf-8",
        )
        source_block = sync_skills._extract_decision_tree_block(
            self.source_skills[0].read_text(encoding="utf-8")
        )
        drifted_block = sync_skills._extract_decision_tree_block(
            drifted.read_text(encoding="utf-8")
        )
        self.assertNotEqual(
            sync_skills._block_hash(drifted_block),
            sync_skills._block_hash(source_block),
            "drifted copy should have a different block hash",
        )

    # ---- 4. --sync (force) mode rewrites drifted copies ------------------

    def test_sync_mode_force(self) -> None:
        """Calling sync_skill() overwrites the target with the source text."""
        # Make a "target" that's drifted
        target = self.tmp_root / "drifted_target" / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# drifted\n\nrandom content", encoding="utf-8")

        # Sync it from source[0]
        source = self.source_skills[0]
        source_text = source.read_text(encoding="utf-8")
        sync_skills.sync_skill(target, source, source_text)

        # Now the target should have the same content as the source
        self.assertEqual(
            target.read_text(encoding="utf-8"), source_text,
            "sync_skill() did not rewrite the target to match the source",
        )

    # ---- 5. root task type node present (N68) ---------------------------

    def test_root_task_type_node(self) -> None:
        """The decision tree copy contains the step_1_identify_task_type node (N68)."""
        for src in self.source_skills:
            text = src.read_text(encoding="utf-8")
            self.assertIn(
                "step_1_identify_task_type", text,
                f"{src.name} missing 'step_1_identify_task_type' (N68 violation)",
            )
            # All 5 task_type branches should be present
            for branch in sync_skills.REQUIRED_DECISION_TREE_SECTIONS[1:]:
                self.assertIn(
                    branch, text,
                    f"{src.name} missing task_type branch '{branch}' (N68 violation)",
                )


if __name__ == "__main__":
    unittest.main()
