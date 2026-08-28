"""test_e2e_run_all.py — pytest wrapper around scripts/e2e/run_all.py.

M2.B deliverable: re-export each e2e scenario as a unittest TestCase so
pytest picks them up. We also add a few negative tests that exercise the
N91 hook-failure → fix-command mapping by deliberately passing bad
arguments to ``run_all.py`` and asserting the runner's exit code.

This is intentionally a thin wrapper: the scenarios themselves are the
``@register``-decorated functions inside ``run_all.py``. We invoke them
directly here rather than re-implementing the logic.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

# Ensure UTF-8 output (N92 CJK garble fix on Windows cp936/cp437).
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("LC_ALL", "C.UTF-8")

# Add repo root to sys.path so ``from scripts.e2e.run_all import ...`` works.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# scripts/ needs to be on sys.path for sync_lock + _encoding_safe imports
# inside the collaboration scenario.
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import pytest

from scripts.e2e.run_all import SCENARIOS, run_all  # noqa: E402

pytestmark = pytest.mark.e2e

REPO = _REPO_ROOT


class E2EScenarioTests(unittest.TestCase):
    """Each scenario should run individually and report OK."""

    def test_cold_start(self) -> None:
        ok, detail = SCENARIOS["cold_start"](REPO)
        self.assertTrue(ok, msg=detail)

    def test_new_feature(self) -> None:
        ok, detail = SCENARIOS["new_feature"](REPO)
        self.assertTrue(ok, msg=detail)

    def test_bug_fix(self) -> None:
        ok, detail = SCENARIOS["bug_fix"](REPO)
        self.assertTrue(ok, msg=detail)

    def test_documentation(self) -> None:
        ok, detail = SCENARIOS["documentation"](REPO)
        self.assertTrue(ok, msg=detail)

    def test_refactor(self) -> None:
        ok, detail = SCENARIOS["refactor"](REPO)
        self.assertTrue(ok, msg=detail)

    def test_cross_repo(self) -> None:
        ok, detail = SCENARIOS["cross_repo"](REPO)
        self.assertTrue(ok, msg=detail)

    def test_collaboration(self) -> None:
        ok, detail = SCENARIOS["collaboration"](REPO)
        self.assertTrue(ok, msg=detail)


class E2ERunnerTests(unittest.TestCase):
    """Test the run_all() harness itself."""

    def test_run_all_returns_zero_on_full_success(self) -> None:
        # Playwright scenarios (browser_login, devices_control_mode,
        # ai_qa_chat) launch a browser subprocess which pytest's
        # SelectorEventLoop cannot create on Windows
        # (NotImplementedError from _make_subprocess_transport). They
        # are covered end-to-end by test_cli_strict_all_passes, which
        # runs run_all.py as a fresh subprocess with the default
        # ProactorEventLoop. Here we exercise the run_all() harness
        # in-process with the non-Playwright scenarios only.
        non_playwright = [
            n for n in SCENARIOS
            if n not in {"browser_login", "devices_control_mode", "ai_qa_chat"}
        ]
        code = run_all(REPO, only=non_playwright, strict=True)
        self.assertEqual(code, 0)

    def test_run_all_subselection(self) -> None:
        # Running just one scenario should not fail.
        code = run_all(REPO, only=["cold_start"], strict=True)
        self.assertEqual(code, 0)

    def test_unknown_scenario_is_skipped(self) -> None:
        # ``run_all`` should not crash on an unknown name; it just logs SKIP.
        code = run_all(REPO, only=["__nonexistent__"], strict=False)
        self.assertEqual(code, 0)


class E2ECLITests(unittest.TestCase):
    """End-to-end CLI smoke tests: invoke run_all.py as a subprocess."""

    def test_cli_list(self) -> None:
        """``python scripts/e2e/run_all.py --list`` lists all 10 scenarios."""
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "e2e" / "run_all.py"), "--list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "LC_ALL": "C.UTF-8"},
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        names = proc.stdout.strip().splitlines()
        # 7 original scenarios + 3 Playwright scenarios added later
        # (browser_login, devices_control_mode, ai_qa_chat).
        self.assertEqual(len(names), 10)
        for expected in ("cold_start", "new_feature", "bug_fix",
                          "documentation", "refactor", "cross_repo",
                          "browser_login", "devices_control_mode",
                          "ai_qa_chat", "collaboration"):
            self.assertIn(expected, names)

    def test_cli_strict_all_passes(self) -> None:
        """``--strict`` exits 0 when all 10 scenarios pass."""
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "e2e" / "run_all.py"), "--strict"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "LC_ALL": "C.UTF-8"},
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
        self.assertIn("10/10 passed", proc.stdout)

    def test_cli_subselection(self) -> None:
        """``run_all.py cold_start`` runs a single scenario."""
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "e2e" / "run_all.py"),
             "new_feature", "bug_fix"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "LC_ALL": "C.UTF-8"},
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
        self.assertIn("2/2 passed", proc.stdout)

    def test_failure_log_written_on_failure(self) -> None:
        """If a scenario fails, .trash/.e2e-failures.log must be appended.

        We force a failure by monkey-patching one scenario to always
        return ``(False, 'forced')`` and assert the log file gains a
        ``FAIL  forced`` line. Clean up afterwards so the real log is
        preserved.
        """
        log_path = REPO / ".trash" / ".e2e-failures.log"
        before = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        # Temporarily override the cold_start scenario.
        from scripts.e2e import run_all as run_all_mod

        original = run_all_mod.SCENARIOS["cold_start"]
        run_all_mod.SCENARIOS["cold_start"] = lambda repo: (False, "forced")
        why_before = ""
        why_path = REPO / ".ai-memory" / "ops" / "why-skipped.md"
        if why_path.exists():
            why_before = why_path.read_text(encoding="utf-8", errors="replace")
        try:
            code = run_all_mod.run_all(REPO, only=["cold_start"], strict=False)
        finally:
            run_all_mod.SCENARIOS["cold_start"] = original
        self.assertEqual(code, 0)  # strict=False → exit 0 even on failure
        after = log_path.read_text(encoding="utf-8", errors="replace")
        # Restore the files to their pre-test state so the real run stays clean.
        log_path.write_text(before, encoding="utf-8")
        why_path.write_text(why_before, encoding="utf-8")
        self.assertNotEqual(before, after, msg="failure log not appended")
        self.assertIn("FAIL  cold_start: forced", after)


class N91HookMappingTests(unittest.TestCase):
    """N91 verification: the hook-failure mapping is complete.

    v9.0 slim-down moved the N91 hook-failure mapping table out of
    ``gaf-reflect-and-evolve/SKILL.md §4`` into
    ``.ai-memory/meta/yn-matrices/_workflow.md §7``. Wave 2
    (2026-07-26) later split the matrices by topic and archived the
    N91 hook-ID mapping table to
    ``archived-yn-matrices/_workflow-reflection.md``, replacing §7 with
    the N150 (root-cause fix + pre-existing-error) matrices. We verify
    the current layout: N91 is still indexed in ``failure-modes.md``,
    the hook names appear in the live governance config, and the lesson
    file still exists.
    """

    def test_hooks_in_workflow_table(self) -> None:
        workflow = (
            REPO / ".ai-memory" / "meta" / "yn-matrices" / "_workflow-commit.md"
        ).read_text(encoding="utf-8", errors="replace")
        # v9.0 N171 consolidation: 14 fine-grained governance hooks →
        # 5 batch hooks (gaf-governance-batch + gaf-git-status-check +
        # gaf-post-commit-batch + gaf-skip-rate + gaf-audit-scripts),
        # plus 4 manual-stage lint hooks retained.
        hooks = (
            "gaf-governance-batch", "gaf-git-status-check",
            "gaf-post-commit-batch", "gaf-skip-rate", "gaf-audit-scripts",
            "eslint", "prettier", "ruff", "mypy",
        )
        # The N150 §7 matrices reference the N91 hook-ID mapping table
        # (which is archived), so verify the hook names against the live
        # pre-commit config instead of a stale matrix file.
        precommit_cfg = (REPO / ".pre-commit-config.yaml").read_text(
            encoding="utf-8", errors="replace",
        )
        for h in hooks:
            self.assertIn(
                h, precommit_cfg, msg=f"hook {h!r} missing from .pre-commit-config.yaml"
            )
        # And the workflow matrix still documents the hook-failure handling.
        self.assertIn("N150", workflow)

    def test_n91_referenced_in_failure_modes(self) -> None:
        # v9.1 slim-down: N## index moved from project_rules.md §5.8 to
        # failure-modes.md (single source of truth).
        failure_modes = (REPO / ".ai-memory" / "meta" / "failure-modes.md").read_text(
            encoding="utf-8", errors="replace",
        )
        self.assertIn("N91", failure_modes)
        # The N91 hook-ID mapping table is archived under
        # archived-yn-matrices/_workflow-reflection.md.
        archived = (
            REPO / ".ai-memory" / "meta" / "yn-matrices" / "archived-yn-matrices" /
            "_workflow-reflection.md"
        )
        self.assertTrue(archived.exists(), msg=f"missing archived N91 mapping {archived}")
        archived_text = archived.read_text(encoding="utf-8", errors="replace")
        self.assertIn("Hook ID 映射表", archived_text)

    def test_n91_lesson_present(self) -> None:
        lesson = REPO / ".ai-memory" / "lessons" / "N91-m2b-hook-failure.md"
        self.assertTrue(lesson.exists(), msg=f"missing {lesson}")
        text = lesson.read_text(encoding="utf-8", errors="replace")
        self.assertIn("M2.B 闭环", text)
        self.assertIn("14 hook", text)


if __name__ == "__main__":
    unittest.main()
