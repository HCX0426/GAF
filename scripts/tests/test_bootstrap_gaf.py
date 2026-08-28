"""test_bootstrap_gaf.py — Tests for gaf_init.sh 4-step bootstrap (M2.A-6)

Covers 4 cases (consolidated from Appendix G §G.8 + user todo "4 跳初始化 + 4 资源"):
1. test_conda_env_check      — conda gaf env is required and detected
2. test_ai_memory_bootstrap  — sync_ai_memory populates .ai-memory/ top-level files
3. test_skills_bootstrap     — sync_skills generates 4 decision-tree SKILL.md copies
4. test_session_bootstrap    — check_session_active --create writes .gaf_session_active

Run with:
    python -m unittest GAF/scripts/tests/test_bootstrap_gaf.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

# Make the parent scripts/ directory importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_python_script(args: list[str], *, cwd: Path, env: dict) -> tuple[int, str, str]:
    """Run a Python script with given args; return (rc, stdout, stderr)."""
    proc = subprocess.run(
        ["python", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return (proc.returncode, proc.stdout, proc.stderr)


def _build_env() -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBootstrapGaf(unittest.TestCase):
    """4-test suite for gaf_init.sh 4-step bootstrap."""

    def setUp(self) -> None:
        # We test against the real GAF repo at REPO_ROOT
        self.repo_root = SCRIPTS_DIR.parent
        self.env = _build_env()
        # A tmp dir for the session test (which writes a session file)
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ---- 1. conda env check ---------------------------------------------

    def test_conda_env_check(self) -> None:
        """Step 1: gaf_init.sh requires conda gaf env; we verify by running a
        python interpreter via `conda run -n gaf`."""
        # Use the real `conda run -n gaf python -c ...` to verify the env works
        proc = subprocess.run(
            ["conda", "run", "-n", "gaf", "python", "-c", "import sys; print(sys.executable)"],
            cwd=str(self.repo_root),
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"conda gaf env not functional: stderr={proc.stderr!r}",
        )
        # The python path should mention gaf env (e.g. .../envs/gaf/...)
        self.assertIn(
            "gaf", proc.stdout.lower(),
            f"python executable path should include 'gaf': {proc.stdout!r}",
        )

    # ---- 2. .ai-memory bootstrap ---------------------------------------

    def test_ai_memory_bootstrap(self) -> None:
        """Step 2: sync_ai_memory should populate .ai-memory/ with top-level files."""
        ai_memory = self.repo_root / ".ai-memory"
        lessons = ai_memory / "lessons"
        # v9.7 (2026-07-26 TD-341): 4 个用户可读 ref 文件迁出到 docs/reference/, ref/ 仅留 3 个 AI 内部文件
        # spec-38 Phase 4: 4 个 auto-generated KB 在 meta/auto-kb/
        expected = {
            "ref/session-context.md", "ref/spec-index.md",
            "ref/doc-health-report-schema.md",
            "meta/auto-kb/api-endpoints.md", "meta/auto-kb/agent-protocol.md",
            "meta/auto-kb/pipeline-nodes.md", "meta/auto-kb/error-codes.md",
        }
        present = set()
        for relpath in expected:
            if (ai_memory / relpath).is_file():
                present.add(relpath)
        missing = expected - present
        self.assertEqual(
            missing, set(),
            f"missing .ai-memory files: {missing}",
        )
        # Also: at least 5 lessons exist
        lesson_files = [p for p in lessons.iterdir() if p.is_file() and p.suffix == ".md"]
        self.assertGreater(
            len(lesson_files), 5,
            f"expected > 5 lessons, got {len(lesson_files)}",
        )

    # ---- 3. skills bootstrap --------------------------------------------

    def test_skills_bootstrap(self) -> None:
        """Step 3: sync_skills should produce 4 decision-tree SKILL.md copies."""
        skills_dir = self.repo_root / ".skills" / "skills"
        expected = {
            "gaf-orchestrator", "gaf-knowledge-base",
            "gaf-task-execution", "gaf-reflect-and-evolve",
        }
        present = {p.name for p in skills_dir.iterdir() if p.is_dir()}
        missing = expected - present
        self.assertEqual(
            missing, set(),
            f"missing skill dirs: {missing}",
        )
        # Each copy must have SKILL.md
        for skill in expected:
            skill_md = skills_dir / skill / "SKILL.md"
            self.assertTrue(
                skill_md.exists(),
                f"{skill_md} does not exist",
            )
            text = skill_md.read_text(encoding="utf-8")
            self.assertIn("## Decision Tree", text, f"{skill} missing decision tree")

    # ---- 4. session active bootstrap ------------------------------------

    def test_session_bootstrap(self) -> None:
        """Step 4: check_session_active --create should write .trash/.gaf_session_active."""
        # Build a fake "repo root" mirroring the real scripts/ layout:
        #   fake_repo/scripts/_encoding_safe.py  (library module, top-level)
        #   fake_repo/scripts/bootstrap/check_session_active.py  (moved in reorg)
        # The sys.path bootstrap in check_session_active.py adds parents[1]
        # (fake_repo/scripts/) to sys.path, so import _encoding_safe resolves.
        fake_repo = self.tmp_path / "fake_repo"
        fake_scripts = fake_repo / "scripts"
        fake_bootstrap = fake_scripts / "bootstrap"
        fake_bootstrap.mkdir(parents=True, exist_ok=True)
        shutil.copy(
            str(SCRIPTS_DIR / "bootstrap" / "check_session_active.py"),
            str(fake_bootstrap / "check_session_active.py"),
        )
        shutil.copy(
            str(SCRIPTS_DIR / "_encoding_safe.py"),
            str(fake_scripts / "_encoding_safe.py"),
        )

        # Run --create from fake_repo
        proc = subprocess.run(
            ["python", "scripts/bootstrap/check_session_active.py", "--create"],
            cwd=str(fake_repo),
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"check_session_active --create failed: stderr={proc.stderr!r}",
        )
        session_file = fake_repo / ".trash" / ".gaf_session_active"
        self.assertTrue(
            session_file.exists(),
            f"{session_file} not created",
        )
        payload = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertIn("binding_hash", payload, "session file missing binding_hash")
        self.assertIn("expires_at", payload, "session file missing expires_at")


if __name__ == "__main__":
    unittest.main()
