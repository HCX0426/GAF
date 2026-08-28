"""doc_health_check.py - Spec-41 static-layer doc health checker (7 dimensions).

Runs 7 read-only dimension checks against docs/ + .ai-memory/, produces
.cache/doc_health_report.json for AI consumption at session start.

Performance budget: < 2s (N171).

Usage:
    python scripts/governance/doc_health_check.py
    python scripts/governance/doc_health_check.py --output .cache/doc_health_report.json
    python scripts/governance/doc_health_check.py --no-fail  # warn-only
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Bootstrap: make scripts/ importable
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first after bootstrap; reconfigures stdout to UTF-8)

import subprocess  # noqa: E402
from datetime import datetime  # noqa: E402

import yaml  # noqa: E402

from governance.report_schema import DocHealthReport, Issue, ReportSummary  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS_FILE = Path(__file__).parent / "thresholds.yaml"
CONSUMED_FILE = REPO_ROOT / ".cache" / "doc_health_consumed.json"


def run_all_dimensions(repo_root: Path, thresholds: dict) -> list[Issue]:
    """Run all 7 dimensions and collect issues.

    Each dimension module receives its own sub-config (``thresholds[dim_name]``)
    rather than the full YAML. If a dimension key is missing from thresholds,
    an empty dict is passed (dimension uses its own defaults).
    """
    issues: list[Issue] = []
    from governance.check_dimensions import (
        d1_overlap, d2_bloat, d3_count_drift, d4_path_drift,
        d5_frontmatter, d6_staleness, d7_index_consistency,
        d8_yaml_frontmatter,
    )
    for module in (d1_overlap, d2_bloat, d3_count_drift, d4_path_drift,
                   d5_frontmatter, d6_staleness, d7_index_consistency,
                   d8_yaml_frontmatter):
        dim_name = module.__name__.split(".")[-1]
        # Pass sub-config; missing key → empty dict (dimension uses defaults)
        dim_config = thresholds.get(dim_name, {}) if isinstance(thresholds, dict) else {}
        try:
            dim_issues = module.check(repo_root, dim_config)
            issues.extend(dim_issues)
        except Exception as exc:
            issues.append(Issue(
                dimension=dim_name,
                severity="P0",
                evidence=f"check crashed: {exc!r}",
                suggested_fix="inspect the dimension module",
                root_cause_hint="module bug or threshold misconfiguration",
            ))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Spec-41 doc health checker")
    parser.add_argument("--output", type=Path, default=None,
                        help="output JSON path; defaults to <root>/.cache/doc_health_report.json")
    parser.add_argument("--no-fail", action="store_true", help="warn-only mode (always exit 0)")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()

    output = args.output or args.root / ".cache" / "doc_health_report.json"

    thresholds = yaml.safe_load(THRESHOLDS_FILE.read_text(encoding="utf-8"))

    start = time.perf_counter()
    issues = run_all_dimensions(args.root, thresholds)
    duration = time.perf_counter() - start

    # Spec-42 Phase 1: load consumed.json and mark Issue.consumed for issues
    # that were patched in prior sessions (and not failing). This lets the
    # AI flywheel skip already-patched issues at session start.
    # Loaded after run_all_dimensions so a corrupted consumed.json cannot
    # crash the static-layer check (graceful degradation: empty dict).
    from governance.doc_health_consumed import ConsumedTracker
    tracker = ConsumedTracker(args.root / ".cache" / "doc_health_consumed.json")
    consumed = tracker.load()
    consumed_patched = 0
    for issue in issues:
        entry = consumed.get(issue.id)
        if entry is not None and not entry.get("patch_failed", False):
            issue.consumed = True
            consumed_patched += 1

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
    print(f"✅ doc_health_check: {len(issues)} issues ({report.summary.by_severity}) in {duration:.2f}s")
    print(f"   Report: {output}")
    if consumed_patched:
        print(f"   Consumed (skipped by flywheel): {consumed_patched}")

    if args.no_fail:
        return 0
    has_p0 = report.summary.by_severity.get("P0", 0) > 0
    return 1 if has_p0 else 0


if __name__ == "__main__":
    sys.exit(main())
