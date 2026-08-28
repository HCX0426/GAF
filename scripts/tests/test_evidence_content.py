"""test_evidence_content.py — Unit tests for check_3step_evidence.py (M2.A-3)

Covers 5 cases (consolidated from Appendix G §G.5):
1. test_3_templates_complete        — 3 templates with all required headings → exit 0
2. test_missing_one_heading         — missing 1 heading → exit 1
3. test_all_templates_missing       — all 3 templates missing → lists all
4. test_placeholder_unfilled        — unfilled placeholders → exit 1 (strict by default)
5. test_strict_mode_rejects_placeholder — --strict mode: verification without runnable cmd → exit 1

Run with:
    python -m unittest GAF/scripts/tests/test_evidence_content.py -v
"""
from __future__ import annotations

import datetime as _dt
import json
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

import check_3step_evidence  # noqa: E402

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixtures: minimal .ai-memory/evidence tree
# ---------------------------------------------------------------------------


TEMPLATE_PROBLEM = """\
# Problem

## Symptom
Something broke.

## Trigger Conditions
1. Run `pytest`

## Root Cause
TODO [fill in] the actual cause here.

## Verification
Run `pytest` and see it pass.
"""

TEMPLATE_SOLUTION = """\
# Solution

## Fix
Patched the offending function.

## Verification
$ python -m pytest tests/test_foo.py
"""

TEMPLATE_VERIFICATION_OK = """\
# Verification

## Verification
$ python -m pytest tests/test_foo.py -v
"""

TEMPLATE_VERIFICATION_NO_RUNNABLE = """\
# Verification

## Verification
We verified it works by hand.
"""


def _write_evidence_dir(repo_root: Path, *, with_placeholders: bool = True) -> Path:
    """Create a fake repo with .ai-memory/evidence/templates/.

    Returns the repo_root.
    """
    templates = repo_root / ".ai-memory" / "evidence" / "templates"
    templates.mkdir(parents=True, exist_ok=True)

    problem_text = TEMPLATE_PROBLEM
    solution_text = TEMPLATE_SOLUTION
    verification_text = TEMPLATE_VERIFICATION_OK
    if not with_placeholders:
        # Strip placeholders from problem template
        problem_text = problem_text.replace("TODO [fill in] the actual cause here.", "A missing import.")
    (templates / "problem.md").write_text(problem_text, encoding="utf-8")
    (templates / "solution.md").write_text(solution_text, encoding="utf-8")
    (templates / "verification.md").write_text(verification_text, encoding="utf-8")

    # Also seed today's evidence dir
    today = repo_root / ".ai-memory" / "evidence" / f"{_dt.date.today().isoformat()}-test-task"
    today.mkdir(parents=True, exist_ok=True)
    (today / "problem.md").write_text(problem_text, encoding="utf-8")
    (today / "solution.md").write_text(solution_text, encoding="utf-8")
    (today / "verification.md").write_text(verification_text, encoding="utf-8")
    return repo_root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEvidenceContent(unittest.TestCase):
    """5-test suite for check_3step_evidence (consolidated from G.5)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self.tmp.name)
        # .ai-memory must exist for check_repo() to proceed
        (self.tmp_root / ".ai-memory").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ---- 1. 3 templates complete → exit 0 --------------------------------

    def test_3_templates_complete(self) -> None:
        """With 3 templates present and verification has a runnable cmd → exit 0."""
        _write_evidence_dir(self.tmp_root, with_placeholders=False)
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=True)
        self.assertEqual(
            code, 0,
            f"expected exit 0, got {code}. messages: {msgs}",
        )
        # At least one message should mention success
        self.assertTrue(
            any("OK" in m or "✅" in m for m in msgs),
            f"no success message in: {msgs}",
        )

    # ---- 2. missing 1 heading → exit 1 ----------------------------------

    def test_missing_one_heading(self) -> None:
        """Verification template missing the `## Verification` heading → exit 1 in strict."""
        _write_evidence_dir(self.tmp_root, with_placeholders=False)
        # Overwrite verification template with body lacking the heading
        today = self.tmp_root / ".ai-memory" / "evidence" / f"{_dt.date.today().isoformat()}-test-task"
        (today / "verification.md").write_text(
            "# Verification\n\nJust some prose without the required heading.\n",
            encoding="utf-8",
        )
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=True)
        self.assertEqual(
            code, 1,
            f"expected exit 1 (missing heading), got {code}. messages: {msgs}",
        )
        # Should mention runnable or heading
        joined = " ".join(msgs)
        self.assertTrue(
            "runnable" in joined.lower() or "verification" in joined.lower(),
            f"error message didn't mention the issue: {msgs}",
        )

    # ---- 3. all 3 templates missing → lists all -------------------------

    def test_all_templates_missing(self) -> None:
        """When the entire _templates dir is gone, info message says so (acceptable)."""
        # Don't seed _templates at all; just create .ai-memory/
        templates = self.tmp_root / ".ai-memory" / "evidence" / "_templates"
        if templates.exists():
            for f in templates.iterdir():
                f.unlink()
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        # Today's dir is also missing → should report exit 1
        self.assertEqual(
            code, 1,
            f"expected exit 1 (today's dir missing), got {code}. messages: {msgs}",
        )
        # Should list the missing today dir
        joined = " ".join(msgs)
        self.assertIn(
            _dt.date.today().isoformat(), joined,
            f"missing date in messages: {msgs}",
        )

    # ---- 4. placeholder unfilled → exit 1 --------------------------------

    def test_placeholder_unfilled(self) -> None:
        """A template with unfilled TODO/[fill in] placeholders → exit 1."""
        _write_evidence_dir(self.tmp_root, with_placeholders=True)
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=True)
        self.assertEqual(
            code, 1,
            f"expected exit 1 (placeholders), got {code}. messages: {msgs}",
        )
        joined = " ".join(msgs)
        self.assertIn(
            "placeholder", joined.lower(),
            f"messages should mention 'placeholder': {msgs}",
        )

    # ---- 5. strict mode rejects placeholder-free but non-runnable -------

    def test_strict_mode_rejects_placeholder(self) -> None:
        """In strict mode, a Verification section without a runnable cmd → exit 1."""
        # Seed evidence with the no-runnable verification
        templates = self.tmp_root / ".ai-memory" / "evidence" / "templates"
        templates.mkdir(parents=True, exist_ok=True)
        (templates / "problem.md").write_text(TEMPLATE_PROBLEM.replace("TODO [fill in] the actual cause here.", "A bug."), encoding="utf-8")
        (templates / "solution.md").write_text(TEMPLATE_SOLUTION, encoding="utf-8")
        (templates / "verification.md").write_text(TEMPLATE_VERIFICATION_NO_RUNNABLE, encoding="utf-8")
        today = self.tmp_root / ".ai-memory" / "evidence" / f"{_dt.date.today().isoformat()}-test-task"
        today.mkdir(parents=True, exist_ok=True)
        for name in ("problem.md", "solution.md", "verification.md"):
            (today / name).write_text((templates / name).read_text(encoding="utf-8"), encoding="utf-8")

        # Non-strict → exit 0 (warning only)
        code_loose, msgs_loose = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        # Strict → exit 1
        code_strict, msgs_strict = check_3step_evidence.check_repo(self.tmp_root, strict=True)
        self.assertEqual(
            code_strict, 1,
            f"strict mode should reject non-runnable verification, got {code_strict}. messages: {msgs_strict}",
        )
        joined = " ".join(msgs_strict)
        self.assertIn(
            "runnable", joined.lower(),
            f"strict message should mention 'runnable': {msgs_strict}",
        )


if __name__ == "__main__":
    unittest.main()
