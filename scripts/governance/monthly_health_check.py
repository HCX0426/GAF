"""monthly_health_check.py - Spec-45: monthly project hygiene checks.

4 checks (C1/H1/I1/N1 from docs/health/procedure.md):
    C1: active TD count (active.md) — warning >5, critical >10
    H1: git status hygiene — sensitive files + uncommitted count
    I1: large files — single file > threshold lines
    N1: empty dirs/files — post-refactor leftovers

Output: .cache/monthly_health_report.json (Issue/ReportSummary schema reused
from spec-41 report_schema for report format consistency).

NOT integrated into gaf_init.sh (monthly check != per-session check).
Run manually: python scripts/governance/monthly_health_check.py

Performance budget: < 2s (N171).
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
import time
from pathlib import Path

# Bootstrap: make scripts/ importable
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first after bootstrap; reconfigures stdout to UTF-8)

from datetime import datetime  # noqa: E402

import yaml  # noqa: E402

from governance.report_schema import DocHealthReport, Issue, ReportSummary  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS_FILE = Path(__file__).parent / "thresholds.yaml"


# ---- C1: active TD count ----

def check_c1_active_td(repo_root: Path, thresholds: dict) -> list[Issue]:
    """C1: active TD count (active.md).

    Thresholds (health/procedure.md C1):
        > warning_threshold (default 5)  -> P2
        > critical_threshold (default 10) -> P1
    """
    cfg = thresholds or {}
    warn = cfg.get("warning_threshold", 5)
    crit = cfg.get("critical_threshold", 10)

    active_md = repo_root / "docs/archive/active-tech-debt.md"
    if not active_md.exists():
        return [Issue(
            dimension="c1_active_td", severity="P2",
            evidence="active-tech-debt.md not found",
            suggested_fix="create docs/archive/active-tech-debt.md",
            root_cause_hint="tech-debt tracking not initialized",
        )]

    text = active_md.read_text(encoding="utf-8")
    # Count table rows containing 🔧 or 🚧 markers (active TD entries)
    active_count = sum(
        1 for line in text.splitlines()
        if ("🔧" in line or "🚧" in line) and "|" in line
    )

    if active_count > crit:
        return [Issue(
            dimension="c1_active_td", severity="P1",
            evidence=f"{active_count} active TDs (>{crit} critical threshold)",
            suggested_fix=f"immediate cleanup — promote or close >= {active_count - crit} TDs",
            root_cause_hint="TD accumulation without cleanup",
        )]
    if active_count > warn:
        return [Issue(
            dimension="c1_active_td", severity="P2",
            evidence=f"{active_count} active TDs (>{warn} warning threshold)",
            suggested_fix="review active.md and promote/close lower-priority TDs",
            root_cause_hint="gradual TD accumulation",
        )]
    return []


# ---- H1: git status hygiene ----

def check_h1_git_status(repo_root: Path, thresholds: dict) -> list[Issue]:
    """H1: Git worktree hygiene.

    Checks:
        1. Sensitive files (.env, *.key, *.pem, *credentials*, *.pfx) in git
        2. Uncommitted changes count (> warning threshold -> P2)
    """
    cfg = thresholds or {}
    uncommitted_warn = cfg.get("uncommitted_warning", 20)
    sensitive_patterns = cfg.get(
        "sensitive_patterns",
        [".env", "*.key", "*.pem", "*credentials*", "*.pfx"],
    )

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo_root,
            capture_output=True, text=True, encoding="utf-8",
        )
    except (FileNotFoundError, OSError) as exc:
        return [Issue(
            dimension="h1_git_status", severity="P0",
            evidence=f"git not available: {exc!r}",
            suggested_fix="install git or check PATH",
            root_cause_hint="git executable missing",
        )]

    if result.returncode != 0:
        return [Issue(
            dimension="h1_git_status", severity="P0",
            evidence=f"git status failed: {result.stderr.strip()}",
            suggested_fix="check git repo state",
            root_cause_hint="git repo corruption",
        )]

    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    uncommitted = len(lines)

    issues: list[Issue] = []

    # Check for sensitive files (in either staged or untracked status)
    sensitive_found = []
    for ln in lines:
        # git status --porcelain format: XY <path>  (X/Y in " M?!" etc.)
        # Path starts at column 3; rename format: "ORIG -> NEW"
        path_part = ln[3:].strip()
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]
        fname = Path(path_part).name
        for pat in sensitive_patterns:
            if fnmatch.fnmatch(fname, pat):
                sensitive_found.append(path_part)
                break

    if sensitive_found:
        issues.append(Issue(
            dimension="h1_git_status", severity="P0",
            evidence=f"Sensitive files in git: {sensitive_found}",
            suggested_fix="add to .gitignore + git rm --cached <file>",
            root_cause_hint=".gitignore missing sensitive patterns",
        ))

    if uncommitted > uncommitted_warn:
        issues.append(Issue(
            dimension="h1_git_status", severity="P2",
            evidence=f"{uncommitted} uncommitted changes (>{uncommitted_warn})",
            suggested_fix="commit or stash pending work",
            root_cause_hint="large pending state",
        ))

    return issues


# ---- I1: large files ----

_CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}


def check_i1_large_files(repo_root: Path, thresholds: dict) -> list[Issue]:
    """I1: large single files (> threshold lines).

    Thresholds (health/procedure.md I1):
        default_lines: 1000
        per_dir overrides (backend=2000, frontend/src=1500, etc.)

    Skips:
        - Auto-generated files (*.generated.ts) — large by design, tracked in tsconfig
        - __pycache__ / node_modules / .venv / venv / debug dirs
        - agent/debug/ (runtime debug output, not source)
        - exclude_files (fnmatch patterns, matched against repo-relative posix path)
          — deliberately kept-large files (e.g. test_agent.py/test_scheduler.py merged
          by design, TD-365 exclusion a3e65c08)
    """
    cfg = thresholds or {}
    default_threshold = cfg.get("default_lines", 1000)
    per_dir = cfg.get("per_dir", {})
    exclude_files = cfg.get("exclude_files", [])
    skip_dir_parts = {"__pycache__", "node_modules", ".venv", "venv", "debug"}
    scan_dirs = ["backend", "frontend/src", "agent/src", "scripts"]

    issues: list[Issue] = []
    for scan_dir in scan_dirs:
        full_dir = repo_root / scan_dir
        if not full_dir.exists():
            continue
        threshold = per_dir.get(scan_dir, default_threshold)
        for f in full_dir.rglob("*"):
            if not f.is_file() or f.suffix not in _CODE_SUFFIXES:
                continue
            # Skip generated/debug/cache dirs
            if any(part in skip_dir_parts for part in f.parts):
                continue
            # Skip auto-generated files (api.generated.ts, etc.)
            if ".generated." in f.name or f.name.endswith(".gen.ts"):
                continue
            try:
                # str.count("\n") is ~5-10x faster than sum(1 for _ in fh)
                # because it's a C-level character scan.
                text = f.read_text(encoding="utf-8", errors="ignore")
                line_count = text.count("\n")
                # Trailing line without newline counts as a line
                if text and not text.endswith("\n"):
                    line_count += 1
            except OSError:
                continue
            if line_count > threshold:
                rel = f.relative_to(repo_root).as_posix()
                if exclude_files and any(
                    fnmatch.fnmatch(rel, pat) for pat in exclude_files
                ):
                    continue
                issues.append(Issue(
                    dimension="i1_large_files", severity="P2",
                    file=rel, line=line_count,
                    evidence=f"{rel}: {line_count} lines (> {threshold})",
                    suggested_fix="refactor / split module",
                    root_cause_hint="gradual file growth without refactor",
                ))
    return issues


# ---- N1: empty dirs/files ----

def check_n1_empty_dirs(repo_root: Path, thresholds: dict) -> list[Issue]:
    """N1: empty directories and empty files (post-refactor leftovers).

    Skips:
        - .git, .cache, node_modules, __pycache__, .venv, venv dirs
        - .trash (already-garbage-collected staging area)
        - MagicMock/ (test mock side-effect dirs, not real code)
        - agent/debug/ (runtime debug output, not source)
        - .gitkeep / .keep / __init__.py (intentional empty files)
        - .lock files (intentional empty lock files)
        - Dirs containing only .gitkeep (intentional placeholders)
    """
    cfg = thresholds or {}
    skip_dirs = set(cfg.get(
        "skip_dirs",
        [".git", ".cache", "node_modules", "__pycache__", ".venv", "venv",
         ".trash", "MagicMock", "debug"],
    ))
    skip_empty_files = set(cfg.get(
        "skip_empty_files", [".gitkeep", ".keep", "__init__.py"],
    ))
    # File name patterns (substring match) for intentional empty files
    skip_empty_patterns = (".lock",)

    issues: list[Issue] = []
    for p in repo_root.rglob("*"):
        # Skip if any path component is in skip_dirs
        if any(part in skip_dirs for part in p.parts):
            continue
        if p.is_dir():
            try:
                children = list(p.iterdir())
            except (PermissionError, OSError):
                continue
            # Dir with only .gitkeep → intentional placeholder, skip
            real_children = [c for c in children if c.name not in skip_empty_files]
            if not real_children and children:
                continue  # only .gitkeep/.keep/__init__.py
            if not children:
                rel = p.relative_to(repo_root).as_posix()
                issues.append(Issue(
                    dimension="n1_empty", severity="P2",
                    file=rel,
                    evidence=f"empty directory: {rel}",
                    suggested_fix="remove dir or add .gitkeep",
                    root_cause_hint="post-refactor leftover",
                ))
        elif p.is_file():
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size != 0:
                continue
            # Skip intentional empty files
            if p.name in skip_empty_files:
                continue
            if any(pat in p.name for pat in skip_empty_patterns):
                continue
            rel = p.relative_to(repo_root).as_posix()
            issues.append(Issue(
                dimension="n1_empty", severity="P2",
                file=rel,
                evidence=f"empty file: {rel}",
                suggested_fix="remove or populate file",
                root_cause_hint="post-refactor leftover",
            ))
    return issues


# ---- Orchestration ----

_CHECKS = [
    ("c1_active_td", check_c1_active_td),
    ("h1_git_status", check_h1_git_status),
    ("i1_large_files", check_i1_large_files),
    ("n1_empty", check_n1_empty_dirs),
]


def run_all_checks(repo_root: Path, thresholds: dict) -> list[Issue]:
    """Run all 4 monthly checks and collect issues.

    Each check receives its own sub-config (``thresholds[check_name]``)
    rather than the full YAML. If a key is missing, an empty dict is passed.
    """
    issues: list[Issue] = []
    for check_name, check_fn in _CHECKS:
        cfg = thresholds.get(check_name, {}) if isinstance(thresholds, dict) else {}
        try:
            check_issues = check_fn(repo_root, cfg)
            issues.extend(check_issues)
        except Exception as exc:
            issues.append(Issue(
                dimension=check_name,
                severity="P0",
                evidence=f"check crashed: {exc!r}",
                suggested_fix=f"inspect {check_name} function",
                root_cause_hint="module bug or threshold misconfiguration",
            ))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Spec-45 monthly health checker")
    parser.add_argument("--output", type=Path, default=None,
                        help="output JSON path; defaults to <root>/.cache/monthly_health_report.json")
    parser.add_argument("--no-fail", action="store_true", help="warn-only mode (always exit 0)")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()

    output = args.output or args.root / ".cache" / "monthly_health_report.json"

    thresholds = yaml.safe_load(THRESHOLDS_FILE.read_text(encoding="utf-8"))
    monthly_cfg = thresholds.get("monthly_checks", {}) if isinstance(thresholds, dict) else {}

    start = time.perf_counter()
    issues = run_all_checks(args.root, monthly_cfg)
    duration = time.perf_counter() - start

    # Get git sha
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=args.root, text=True, encoding="utf-8"
        ).strip()
    except Exception:
        sha = "unknown"

    report = DocHealthReport(
        generated_at=datetime.now().astimezone().isoformat(),
        repo_root=str(args.root),
        git_sha=sha,
        duration_seconds=round(duration, 3),
        summary=ReportSummary.from_issues(issues),
        issues=issues,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.to_json(), encoding="utf-8")
    print(f"✅ monthly_health_check: {len(issues)} issues ({report.summary.by_severity}) in {duration:.2f}s")
    print(f"   Report: {output}")

    if args.no_fail:
        return 0
    has_p0 = report.summary.by_severity.get("P0", 0) > 0
    return 1 if has_p0 else 0


if __name__ == "__main__":
    sys.exit(main())
