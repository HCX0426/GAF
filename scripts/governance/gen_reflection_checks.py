#!/usr/bin/env python3
"""GAF reflection check generator — creates _reflection_checks.json template."""

import argparse
import json
from datetime import datetime
from pathlib import Path

SEVEN_DIM_CHECKS = [
    "d1_overlap",
    "d2_bloat",
    "d3_count_drift",
    "d4_path_drift",
    "d5_frontmatter",
    "d6_staleness",
    "d7_index_consistency",
]

DUAL_DEBUG_CHECKS = ["A1", "A2", "A3", "A4", "A5"]

L3_SCAN_CHECKS = ["security", "performance", "compatibility"]

TASK_TYPES = ["bug_fix", "new_feature", "refactor", "documentation", "unknown"]


def derive_scope(diff_lines: int) -> str:
    if diff_lines < 50:
        return "small"
    if diff_lines <= 500:
        return "medium"
    return "big"


def select_checks(scope: str) -> dict:
    checks = {}
    if scope == "small":
        checks["dual_debug"] = list(DUAL_DEBUG_CHECKS)
    elif scope == "medium":
        checks["seven_dim"] = list(SEVEN_DIM_CHECKS)
        checks["dual_debug"] = list(DUAL_DEBUG_CHECKS)
    elif scope == "big":
        checks["seven_dim"] = list(SEVEN_DIM_CHECKS)
        checks["dual_debug"] = list(DUAL_DEBUG_CHECKS)
        checks["l3_scan"] = list(L3_SCAN_CHECKS)
    return checks


def build_template(task_type: str, diff_lines: int, scope: str) -> dict:
    checks = select_checks(scope)
    confirmation = {"timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
    for key in checks:
        confirmation[f"{key}_done"] = False

    return {
        "task_type": task_type,
        "diff_lines": diff_lines,
        "scope": scope,
        "selected_checks": checks,
        "ai_confirmation": confirmation,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate _reflection_checks.json template for GAF governance"
    )
    parser.add_argument(
        "--task-type",
        required=True,
        choices=TASK_TYPES,
        help="Type of the task",
    )
    parser.add_argument(
        "--diff-lines",
        required=True,
        type=int,
        help="Number of changed lines",
    )
    parser.add_argument(
        "--scope",
        choices=["small", "medium", "big"],
        default=None,
        help="Scope override (auto-derived from diff-lines if not given)",
    )

    args = parser.parse_args(argv)

    scope = args.scope or derive_scope(args.diff_lines)
    template = build_template(args.task_type, args.diff_lines, scope)

    output_path = Path.cwd() / "_reflection_checks.json"
    output_path.write_text(
        json.dumps(template, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Generated {output_path}  (scope={scope})")


if __name__ == "__main__":
    main()