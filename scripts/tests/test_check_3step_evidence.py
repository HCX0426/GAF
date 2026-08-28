"""test_check_3step_evidence.py — Unit tests for check_3step_evidence.py (M2.A-8)

Covers 8 cases (extended from Appendix G §G.5 + user todo "3 步 evidence hook"):
1. test_repo_missing_ai_memory           — .ai-memory/ missing → exit 2
2. test_today_dir_missing                — today's evidence dir missing → exit 1
3. test_today_dir_exists_no_templates    — today dir exists but templates missing
4. test_template_problem_with_placeholder — problem template has TODO → exit 1
5. test_template_solution_complete       — solution template complete → exit 0
6. test_template_verification_runnable   — verification with $ cmd → exit 0
7. test_template_verification_strict_no_runnable — strict mode + no runnable → exit 1
8. test_historical_dir_with_placeholders  — older dir still has placeholders → exit 1
9. test_template_xxx_pattern             — `xxx` placeholder detected → exit 1
10. test_template_lorem_ipsum            — lorem ipsum placeholder detected → exit 1

Run with:
    python -m unittest GAF/scripts/tests/test_check_3step_evidence.py -v
"""
from __future__ import annotations

import datetime as _dt
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

# Make the parent scripts/ directory importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_3step_evidence  # noqa: E402

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _seed_repo(root: Path, *, problem: str, solution: str, verification: str) -> None:
    """Seed a fake .ai-memory/evidence/templates/ with the given template bodies."""
    templates = root / ".ai-memory" / "evidence" / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    (templates / "problem.md").write_text(problem, encoding="utf-8")
    (templates / "solution.md").write_text(solution, encoding="utf-8")
    (templates / "verification.md").write_text(verification, encoding="utf-8")

    today = root / ".ai-memory" / "evidence" / f"{_dt.date.today().isoformat()}-test-task"
    today.mkdir(parents=True, exist_ok=True)
    (today / "problem.md").write_text(problem, encoding="utf-8")
    (today / "solution.md").write_text(solution, encoding="utf-8")
    (today / "verification.md").write_text(verification, encoding="utf-8")


def _seed_today(root: Path, *, with_placeholders: bool = False) -> None:
    """Seed a 'good' today dir (no placeholders, runnable verification)."""
    problem = (
        "# Problem\n\n## Symptom\nX is broken.\n\n## Root Cause\n"
        + ("TODO [fill in] cause." if with_placeholders else "A real cause.")
    )
    solution = "# Solution\n\n## Fix\nPatched.\n\n## Verification\n$ pytest"
    verification = "# Verification\n\n## Verification\n$ pytest -v"
    _seed_repo(root, problem=problem, solution=solution, verification=verification)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheck3StepEvidence(unittest.TestCase):
    """10-test suite for check_3step_evidence.py (M2.A-8; 8 + 2 bonus)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ---- 1. .ai-memory missing → exit 2 --------------------------------

    def test_repo_missing_ai_memory(self) -> None:
        """When the .ai-memory/ directory does not exist → exit 2."""
        # Do NOT create .ai-memory
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        self.assertEqual(
            code, 2,
            f"expected exit 2 (config error), got {code}. messages: {msgs}",
        )
        joined = " ".join(msgs).lower()
        self.assertIn(
            "does not exist", joined,
            f"message should mention 'does not exist': {msgs}",
        )

    # ---- 2. today's evidence dir missing → exit 1 ----------------------

    def test_today_dir_missing(self) -> None:
        """When today's evidence dir is missing → exit 1."""
        (self.tmp_root / ".ai-memory").mkdir(parents=True, exist_ok=True)
        # Do NOT create today's evidence dir
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        self.assertEqual(
            code, 1,
            f"expected exit 1 (missing today dir), got {code}. messages: {msgs}",
        )
        joined = " ".join(msgs)
        self.assertIn(
            _dt.date.today().isoformat(), joined,
            f"missing date in messages: {msgs}",
        )

    # ---- 3. today dir exists, no template files → exit 0 (info) -------

    def test_today_dir_exists_no_templates(self) -> None:
        """When today's dir is created but no template files inside → no critical issue."""
        (self.tmp_root / ".ai-memory").mkdir(parents=True, exist_ok=True)
        today = self.tmp_root / ".ai-memory" / "evidence" / f"{_dt.date.today().isoformat()}-test-task"
        today.mkdir(parents=True, exist_ok=True)
        # No template files inside; check should report info, not exit 1
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        # No template files = no placeholder check, so exit 0
        self.assertEqual(
            code, 0,
            f"expected exit 0 (info only), got {code}. messages: {msgs}",
        )

    # ---- 4. problem template with TODO → exit 1 ------------------------

    def test_template_problem_with_placeholder(self) -> None:
        """When the problem template has a TODO placeholder → exit 1."""
        (self.tmp_root / ".ai-memory").mkdir(parents=True, exist_ok=True)
        _seed_today(self.tmp_root, with_placeholders=True)
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        self.assertEqual(
            code, 1,
            f"expected exit 1 (placeholder), got {code}. messages: {msgs}",
        )
        joined = " ".join(msgs).lower()
        self.assertIn(
            "placeholder", joined,
            f"messages should mention 'placeholder': {msgs}",
        )

    # ---- 5. solution template complete → exit 0 ------------------------

    def test_template_solution_complete(self) -> None:
        """When the solution template is complete (no placeholders, runnable) → exit 0."""
        (self.tmp_root / ".ai-memory").mkdir(parents=True, exist_ok=True)
        _seed_today(self.tmp_root, with_placeholders=False)
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        self.assertEqual(
            code, 0,
            f"expected exit 0 (clean), got {code}. messages: {msgs}",
        )

    # ---- 6. verification with runnable cmd → exit 0 --------------------

    def test_template_verification_runnable(self) -> None:
        """A verification template with a $ command line → exit 0 (runnable)."""
        (self.tmp_root / ".ai-memory").mkdir(parents=True, exist_ok=True)
        _seed_today(self.tmp_root, with_placeholders=False)
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        self.assertEqual(code, 0, f"expected 0, got {code}. messages: {msgs}")

    # ---- 7. strict mode + non-runnable verification → exit 1 ----------

    def test_template_verification_strict_no_runnable(self) -> None:
        """Strict mode with a Verification section containing only prose → exit 1."""
        (self.tmp_root / ".ai-memory").mkdir(parents=True, exist_ok=True)
        problem = "# Problem\n\n## Symptom\nX is broken.\n\n## Root Cause\nReal cause."
        solution = "# Solution\n\n## Fix\nPatched.\n\n## Verification\n$ pytest"
        verification = "# Verification\n\n## Verification\nWe just tested by hand."
        _seed_repo(self.tmp_root, problem=problem, solution=solution, verification=verification)
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=True)
        self.assertEqual(
            code, 1,
            f"strict should reject non-runnable, got {code}. messages: {msgs}",
        )
        joined = " ".join(msgs).lower()
        self.assertIn(
            "runnable", joined,
            f"strict message should mention 'runnable': {msgs}",
        )

    # ---- 8. historical dir with placeholders → exit 1 ------------------

    def test_historical_dir_with_placeholders(self) -> None:
        """An older evidence dir still containing placeholders → exit 1."""
        (self.tmp_root / ".ai-memory").mkdir(parents=True, exist_ok=True)
        # Today's dir is clean
        _seed_today(self.tmp_root, with_placeholders=False)
        # Yesterday's dir has unfilled placeholders
        yesterday = self.tmp_root / ".ai-memory" / "evidence" / "2025-01-01-old-task"
        yesterday.mkdir(parents=True, exist_ok=True)
        (yesterday / "problem.md").write_text(
            "# Old\n\n## Symptom\nY was broken.\n\n## Root Cause\nTODO [fill in]\n",
            encoding="utf-8",
        )
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        self.assertEqual(
            code, 1,
            f"expected exit 1 (historical placeholder), got {code}. messages: {msgs}",
        )
        joined = " ".join(msgs).lower()
        self.assertIn(
            "historical", joined,
            f"messages should mention 'historical': {msgs}",
        )

    # ---- 9. xxx placeholder pattern ------------------------------------

    def test_template_xxx_pattern(self) -> None:
        """`xxx` placeholder (case-insensitive) should be detected."""
        (self.tmp_root / ".ai-memory").mkdir(parents=True, exist_ok=True)
        problem = "# Problem\n\n## Symptom\nX broke.\n\n## Root Cause\nxxx — to be determined"
        solution = "# Solution\n\n## Fix\nPatched.\n\n## Verification\n$ pytest"
        verification = "# Verification\n\n## Verification\n$ pytest"
        _seed_repo(self.tmp_root, problem=problem, solution=solution, verification=verification)
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        self.assertEqual(
            code, 1,
            f"expected exit 1 (xxx placeholder), got {code}. messages: {msgs}",
        )

    # ---- 10. lorem ipsum placeholder pattern --------------------------

    def test_template_lorem_ipsum(self) -> None:
        """`lorem ipsum` placeholder should be detected."""
        (self.tmp_root / ".ai-memory").mkdir(parents=True, exist_ok=True)
        problem = "# Problem\n\n## Symptom\nX broke.\n\n## Root Cause\nlorem ipsum dolor sit amet"
        solution = "# Solution\n\n## Fix\nPatched.\n\n## Verification\n$ pytest"
        verification = "# Verification\n\n## Verification\n$ pytest"
        _seed_repo(self.tmp_root, problem=problem, solution=solution, verification=verification)
        code, msgs = check_3step_evidence.check_repo(self.tmp_root, strict=False)
        self.assertEqual(
            code, 1,
            f"expected exit 1 (lorem ipsum placeholder), got {code}. messages: {msgs}",
        )


if __name__ == "__main__":
    unittest.main()
