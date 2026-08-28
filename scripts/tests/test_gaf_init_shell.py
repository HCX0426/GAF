"""test_gaf_init_shell.py — Tests for gaf_init.sh bash script (M2.A-7)

Covers 6 cases verifying gaf_init.sh's structural properties:
1. test_script_exists_and_executable — gaf_init.sh exists, is a file, has bash shebang
2. test_set_e_and_utf8                — script uses `set -e` and forces UTF-8 (N92 fix)
3. test_conda_validation_step         — script checks for conda gaf env
4. test_sync_steps                    — script invokes sync_ai_memory + sync_skills
5. test_session_active_step           — script invokes check_session_active --create
6. test_l1_hardload_and_entry_hint    — script checks failure-modes N## count (L1) + AI entry hint

We test the script's static structure (grep) rather than executing it
because gaf_init.sh makes real changes to the repo (creates session, runs
sync tools, etc.). Each assertion is a substring check on the file content.

Run with:
    python -m unittest GAF/scripts/tests/test_gaf_init_shell.py -v
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import pytest

# Make the parent scripts/ directory importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGafInitShell(unittest.TestCase):
    """6-test suite for gaf_init.sh structure."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.script_path = SCRIPTS_DIR / "gaf_init.sh"
        cls.assertTrue(
            cls.script_path.exists(),
            f"gaf_init.sh not found at {cls.script_path}",
        )
        cls.content = cls.script_path.read_text(encoding="utf-8", errors="replace")
        cls.lines = cls.content.splitlines()

    # ---- 1. script exists + executable + shebang ----------------------

    def test_script_exists_and_executable(self) -> None:
        """gaf_init.sh exists, is a file, and starts with a bash shebang."""
        self.assertTrue(self.script_path.exists(), f"{self.script_path} missing")
        self.assertTrue(self.script_path.is_file(), f"{self.script_path} not a file")
        # First line must be a shebang pointing to bash
        first_line = self.lines[0] if self.lines else ""
        self.assertTrue(
            first_line.startswith("#!"),
            f"first line is not a shebang: {first_line!r}",
        )
        self.assertIn(
            "bash", first_line,
            f"shebang does not mention bash: {first_line!r}",
        )

    # ---- 2. set -e + UTF-8 ---------------------------------------------

    def test_set_e_and_utf8(self) -> None:
        """Script uses `set -e` and forces UTF-8 (N92 fix)."""
        self.assertIn(
            "set -e", self.content,
            "gaf_init.sh must use `set -e` for fail-fast behaviour",
        )
        # N92 fix: PYTHONIOENCODING=utf-8
        self.assertIn(
            "PYTHONIOENCODING=utf-8", self.content,
            "gaf_init.sh must set PYTHONIOENCODING=utf-8 (N92 CJK fix)",
        )
        # LC_ALL should also be set to a UTF-8 locale
        self.assertIn(
            "LC_ALL", self.content,
            "gaf_init.sh should set LC_ALL to a UTF-8 locale",
        )

    # ---- 3. conda validation -------------------------------------------

    def test_conda_validation_step(self) -> None:
        """Script validates the conda gaf environment before proceeding."""
        # Should check $CONDA_DEFAULT_ENV
        self.assertIn(
            "CONDA_DEFAULT_ENV", self.content,
            "gaf_init.sh must check CONDA_DEFAULT_ENV",
        )
        # Should mention "gaf" env name
        self.assertIn(
            '"gaf"', self.content,
            "gaf_init.sh must reference the 'gaf' env name",
        )
        # Should attempt to activate
        self.assertIn(
            "activate", self.content,
            "gaf_init.sh should attempt to activate the conda env",
        )

    # ---- 4. sync steps -------------------------------------------------

    def test_sync_steps(self) -> None:
        """Script invokes both sync_ai_memory.py and sync_skills.py."""
        self.assertIn(
            "sync_ai_memory.py", self.content,
            "gaf_init.sh must call sync_ai_memory.py",
        )
        self.assertIn(
            "sync_skills.py", self.content,
            "gaf_init.sh must call sync_skills.py",
        )
        # N93 fix: auto-run sync_skills --check (no manual step)
        self.assertIn(
            "sync_skills", self.content,
            "gaf_init.sh must call sync_skills",
        )
        # Verify the script calls --check at least once
        self.assertIn(
            "--check", self.content,
            "gaf_init.sh must use --check mode for sync verification",
        )

    # ---- 5. session active step ---------------------------------------

    def test_session_active_step(self) -> None:
        """Script invokes check_session_active.py --create."""
        self.assertIn(
            "check_session_active.py", self.content,
            "gaf_init.sh must call check_session_active.py",
        )
        self.assertIn(
            "--create", self.content,
            "gaf_init.sh must pass --create to create a fresh session",
        )

    # ---- 6. L1 hard-load + AI entry hint ------------------------------

    def test_l1_hardload_and_entry_hint(self) -> None:
        """Script enforces L1 hard-load of failure-modes.md and prints AI entry hint."""
        # M0.M L1 hard-load: check failure-modes.md has ≥ 5 N## entries
        self.assertIn(
            "failure-modes.md", self.content,
            "gaf_init.sh must reference failure-modes.md (L1 hard-load target)",
        )
        # The grep pattern for N## entries
        self.assertIn(
            "N[0-9]+", self.content,
            "gaf_init.sh must grep for N## failure-mode entries (L1 hard-load)",
        )
        # The 5-entry threshold
        self.assertIn(
            "5", self.content,
            "gaf_init.sh must enforce the ≥5 N## entries threshold",
        )
        # AI entry hint: should mention gaf-orchestrator
        self.assertIn(
            "gaf-orchestrator", self.content,
            "gaf_init.sh must reference gaf-orchestrator (AI entry point)",
        )
        # v8.3.1: hint about decision tree sync
        self.assertIn(
            "sync_skills", self.content,
            "gaf_init.sh should mention sync_skills / 4 副本同步",
        )


if __name__ == "__main__":
    unittest.main()
