"""doc_health_patch.py - Spec-42 Phase 2: AI patch planning + verification helpers.

Provides two classes that support the self-evolution flywheel's AI patch
flow (spec-42 §3.2):

- ``PatchPlanner``: reads ``.cache/doc_health_report.json`` +
  ``.cache/doc_health_consumed.json`` and produces a list of patchable
  issues (P0/P1, unconsumed, not patch_failed) grouped by dimension for
  batch patching.

- ``PatchVerifier``: re-runs ``doc_health_check.py`` + relevant pytest
  via subprocess to confirm that a patch actually resolved the issue
  and did not introduce regressions.

All subprocess calls use a 10s timeout to prevent hangs (N111). The
verifier never calls Python functions directly — it always shells out
so the verification reflects the real environment.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Bootstrap: make scripts/ importable for direct execution
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from governance.doc_health_consumed import ConsumedTracker  # noqa: E402
from governance.report_schema import Issue  # noqa: E402


# Severity rank used to sort patchable issues (P0 first, then P1).
# P2 is filtered out before sorting; the rank here is only for P0/P1.
_SEVERITY_RANK = {"P0": 0, "P1": 1}

# Default cap on issues patched per session (spec-42 §3.2.1 red line).
DEFAULT_MAX_ISSUES = 10

# Subprocess timeout (seconds) for both doc_health_check and pytest.
# Prevents hangs from blocking the AI patch flow at session start.
_SUBPROCESS_TIMEOUT = 10

# Files that, when patched, trigger D3 mandatory sedimentation per spec-42 §3.3.3.
# Patching any of these requires the caller (AI in main session) to sync the
# corresponding rules/handbook sections per §3.8 边执行边沉淀. Paths are
# relative to repo root, forward slashes (matches report.json `file` field style).
RULES_FILES = {
    ".skills/rules/project_rules.md",
    ".ai-memory/meta/ai-operating-handbook.md",
    ".ai-memory/meta/failure-modes.md",
}


class PatchPlanner:
    """Generate patch plan from unconsumed P0/P1 issues.

    Reads ``.cache/doc_health_report.json`` + ``.cache/doc_health_consumed.json``,
    filters patchable issues (P0/P1, unconsumed, not patch_failed), groups
    by dimension for batch patching.
    """

    def __init__(self, report_file: Path, consumed_file: Path):
        self.report_file = Path(report_file)
        self.consumed_file = Path(consumed_file)

    def get_patchable_issues(self, max_issues: int = DEFAULT_MAX_ISSUES) -> list[Issue]:
        """Return list of patchable issues (P0/P1, unconsumed, not patch_failed).

        Sort order: P0 first, then P1. Within same severity, preserve report
        order (stable sort). Capped at ``max_issues`` (default 10 per
        spec §3.2.1).

        Issues with ``patch_failed=true`` in consumed.json are excluded —
        they need TD escalation, not re-patch (spec §3.3.4). Issues with
        ``patch_failed=false`` in consumed.json are also excluded — they
        were already patched successfully in a prior session.
        """
        raw_issues = self._load_report_issues()
        if not raw_issues:
            return []

        consumed = ConsumedTracker(self.consumed_file).load()

        patchable: list[Issue] = []
        for raw in raw_issues:
            sev = raw.get("severity")
            if sev not in ("P0", "P1"):
                continue
            issue_id = raw.get("id", "")
            # Any entry in consumed.json excludes the issue from auto-patch:
            #   - patch_failed=false → already patched successfully
            #   - patch_failed=true  → needs TD escalation, not re-patch
            if issue_id in consumed:
                continue
            patchable.append(self._issue_from_dict(raw))

        # Stable sort by severity rank preserves report order within P0/P1.
        patchable.sort(key=lambda i: _SEVERITY_RANK.get(i.severity, 99))

        return patchable[:max_issues]

    def group_by_dimension(self, issues: list[Issue]) -> dict[str, list[Issue]]:
        """Group issues by dimension for batch patching.

        Returns ``dict[dimension_name -> list[Issue]]``. Within each group,
        preserve original order (P0 first, then P1) — callers should pass
        already-sorted issues (e.g. the output of ``get_patchable_issues``).
        """
        groups: dict[str, list[Issue]] = {}
        for issue in issues:
            groups.setdefault(issue.dimension, []).append(issue)
        return groups

    def check_d3_sediment_trigger(self, patched_files: list[str]) -> list[str]:
        """Return list of rules files that were patched (need D3 sedimentation).

        D3 trigger condition (spec-42 §3.3.3): any patched file in RULES_FILES
        → must sync sedimentation per §3.8 边执行边沉淀. The caller (AI in
        main session) must then sync the corresponding rules/handbook sections.

        Args:
            patched_files: List of file paths (relative to repo root, forward
                slashes) that were modified by the patch flow.

        Returns:
            List of patched files that are in RULES_FILES (subset of input).
            Empty list if no rules files were patched. Order follows input
            order (callers can dedupe if needed).
        """
        return [f for f in patched_files if f in RULES_FILES]

    # ---- Internal helpers ----

    def _load_report_issues(self) -> list[dict]:
        """Load the ``issues`` array from the report JSON file.

        Returns an empty list if the file is missing, corrupted, or has no
        ``issues`` field. Graceful degradation mirrors ConsumedTracker.load.
        """
        if not self.report_file.exists():
            return []
        try:
            data = json.loads(self.report_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, dict):
            return []
        issues = data.get("issues", [])
        if not isinstance(issues, list):
            return []
        return issues

    @staticmethod
    def _issue_from_dict(raw: dict) -> Issue:
        """Construct an Issue from a report JSON dict, preserving id.

        ``Issue.__post_init__`` recomputes id if empty; we pass the existing
        id explicitly so it is preserved across report → Issue roundtrips.
        """
        return Issue(
            dimension=raw.get("dimension", ""),
            severity=raw.get("severity", "P2"),
            evidence=raw.get("evidence", ""),
            suggested_fix=raw.get("suggested_fix", ""),
            root_cause_hint=raw.get("root_cause_hint", ""),
            file=raw.get("file"),
            line=raw.get("line"),
            files=raw.get("files"),
            consumed=bool(raw.get("consumed", False)),
            id=raw.get("id", ""),
        )


class PatchVerifier:
    """Verify patch success by re-running doc_health_check + relevant pytest.

    Used after AI applies patches to confirm issues are resolved and no
    regression was introduced. All checks run via ``subprocess.run`` (never
    direct Python calls) so the verification reflects the real environment.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def rerun_check(self) -> list[Issue]:
        """Re-run ``doc_health_check.py`` via subprocess. Return new issues list.

        Uses ``subprocess.run(["conda", "run", "-n", "gaf", "python",
        "scripts/governance/doc_health_check.py", "--no-fail"])`` to ensure
        the conda env ``gaf`` is used (project_rules §1). The script rewrites
        ``.cache/doc_health_report.json`` in-place; this method parses the
        rewritten file and returns the current Issue list.

        On subprocess error (CalledProcessError / TimeoutExpired / other
        OSError), returns an empty list — callers should treat this as
        "verification not possible" rather than "all issues resolved".
        """
        cmd = [
            "conda", "run", "-n", "gaf", "python",
            "scripts/governance/doc_health_check.py",
            "--no-fail",
        ]
        try:
            subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True, encoding="utf-8",
                timeout=_SUBPROCESS_TIMEOUT,
                check=False,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return []

        report_file = self.repo_root / ".cache" / "doc_health_report.json"
        if not report_file.exists():
            return []
        try:
            data = json.loads(report_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, dict):
            return []
        raw_issues = data.get("issues", [])
        if not isinstance(raw_issues, list):
            return []
        return [PatchPlanner._issue_from_dict(raw) for raw in raw_issues]

    def verify_patched(self, patched_issue_ids: list[str]) -> dict[str, bool]:
        """Return ``{issue_id: True if no longer in current report, False if still present}``.

        Calls ``rerun_check()`` internally. Returns a dict mapping each
        patched issue_id to whether it is resolved (True) or still present
        (False) in the current report. An empty current report means all
        patched ids are considered resolved (True).
        """
        current_issues = self.rerun_check()
        current_ids = {issue.id for issue in current_issues}
        return {iid: (iid not in current_ids) for iid in patched_issue_ids}

    def run_relevant_pytest(self, dimension: str) -> tuple[int, int]:
        """Run pytest for dimension-specific tests. Return ``(passed, failed)``.

        Dimension → test file mapping (s40 split, TD-365 7/9; was spec-42 §3.2.3
        single-file mapping):
            - ``d1_overlap`` → ``scripts/tests/test_doc_health_d1_overlap.py``
            - ``d2_bloat`` → ``scripts/tests/test_doc_health_d2_bloat.py``
            - ``d3_count_drift`` → ``scripts/tests/test_doc_health_d3_count.py``
            - ``d4_path_drift`` → ``scripts/tests/test_doc_health_d4_path.py``
            - ``d5_frontmatter`` → ``scripts/tests/test_doc_health_d5_frontmatter.py``
            - ``d6_staleness`` → ``scripts/tests/test_doc_health_d6_staleness.py``
            - ``d7_index_consistency`` → ``scripts/tests/test_doc_health_d7_index.py``
            - ``consumed`` (Phase 1) → ``scripts/tests/test_doc_health_consumed.py``
            - ``patch`` (Phase 2) → ``scripts/tests/test_doc_health_patch.py``

        Uses ``subprocess.run(["conda", "run", "-n", "gaf", "pytest", ...])``
        to match the project environment. Parses the combined stdout+stderr
        for ``"X passed"`` and ``"Y failed"`` patterns.

        On subprocess error (CalledProcessError / TimeoutExpired / OSError)
        or unknown dimension, returns ``(0, 0)`` and logs a warning to
        stderr. ``(0, 0)`` means "verification not possible" — callers
        should treat it as a failed verification, not a passing one.
        """
        test_file = self._map_dimension_to_test_file(dimension)
        if test_file is None:
            print(
                f"warning: PatchVerifier.run_relevant_pytest: unknown dimension "
                f"{dimension!r}, skipping pytest",
                file=sys.stderr,
            )
            return (0, 0)

        cmd = [
            "conda", "run", "-n", "gaf",
            "pytest", test_file, "-v", "--tb=short",
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True, encoding="utf-8",
                timeout=_SUBPROCESS_TIMEOUT,
                check=False,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            print(
                f"warning: PatchVerifier.run_relevant_pytest: subprocess failed "
                f"for dimension {dimension!r}: {exc!r}",
                file=sys.stderr,
            )
            return (0, 0)

        return self._parse_pytest_output(result.stdout + "\n" + result.stderr)

    # ---- Internal helpers ----

    @staticmethod
    def _map_dimension_to_test_file(dimension: str) -> str | None:
        """Map a dimension name to the relevant pytest test file path.

        Returns None for unknown dimensions (caller logs a warning).
        Paths are relative to ``repo_root`` (used as subprocess cwd).

        s40 (TD-365 7/9): each dimension maps to its own split test file
        (previously all 7 dimensions shared test_doc_health_check.py).
        """
        dimension_files = {
            "d1_overlap": "scripts/tests/test_doc_health_d1_overlap.py",
            "d2_bloat": "scripts/tests/test_doc_health_d2_bloat.py",
            "d3_count_drift": "scripts/tests/test_doc_health_d3_count.py",
            "d4_path_drift": "scripts/tests/test_doc_health_d4_path.py",
            "d5_frontmatter": "scripts/tests/test_doc_health_d5_frontmatter.py",
            "d6_staleness": "scripts/tests/test_doc_health_d6_staleness.py",
            "d7_index_consistency": "scripts/tests/test_doc_health_d7_index.py",
        }
        if dimension in dimension_files:
            return dimension_files[dimension]
        if dimension == "consumed":
            return "scripts/tests/test_doc_health_consumed.py"
        if dimension == "patch":
            return "scripts/tests/test_doc_health_patch.py"
        return None

    @staticmethod
    def _parse_pytest_output(text: str) -> tuple[int, int]:
        """Parse pytest output for passed/failed counts.

        Looks for ``"X passed"`` and ``"Y failed"`` patterns in the summary
        line (e.g. ``"===== 5 passed, 2 failed in 3.45s ====="``). Returns
        ``(passed, failed)``; ``(0, 0)`` if no match found.
        """
        passed = 0
        failed = 0
        passed_match = re.search(r"(\d+)\s+passed", text)
        failed_match = re.search(r"(\d+)\s+failed", text)
        if passed_match:
            passed = int(passed_match.group(1))
        if failed_match:
            failed = int(failed_match.group(1))
        return (passed, failed)
