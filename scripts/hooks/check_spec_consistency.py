"""check_spec_consistency.py — TD-170 [B]-class spec validator.

历史: 原 v8.3.1 spec/tasks/checklist 三件套交叉校验器, 目标目录
旧 trae-specs/build-gaf-knowledge-system/ 已删除 (spec 完成后清理),
原 spec.md / tasks.md / checklist.md 一致性检查 (heading 对齐 /
checked-item 反查 / Phase 对齐 / version banner drift) 全部废弃。

当前仅保留 TD-170 [B]-class 检查: 扫描 `docs/specs/legacy-trae/*.md`
中带 [B] 标记但缺少 TD-### ID 的场景 (TD-170: must list TD-### IDs, not just count)
(spec-2026-07-26-trae-specs-plans-merge 迁移自旧 trae-specs 目录)。

Usage:
    python check_spec_consistency.py
    python check_spec_consistency.py --root <repo>
    python check_spec_consistency.py --no-fail

Exit codes:
    0 — OK ([B] issues are warnings ⚠️, do not block commit; original semantics preserved)
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]

# TD-170 — [B] class tech-debt registration must include TD-### IDs (not just count)
# Match "[B]" mentions and nearby TD-### or B### references (within 200 chars)
# Accept either TD-### (tech-debt ID) or B### (spec-internal ID like B1/B2/B3)
_B_CLASS_RE = re.compile(r"\[B\]")
_TD_ID_RE = re.compile(r"\b(?:TD-|B)\d+\b")


def check_td170_b_class_specs(specs_dir: Path) -> tuple[int, list[str]]:
    """TD-170 — scan docs/specs/legacy-trae/*.md for [B] mentions without TD-### IDs.

    For each [B] mention, look within ±200 chars for a TD-### reference.
    If none found, the spec records only a count without identifying TDs.

    Returns (exit_code, messages):
        - (0, messages) always — [B] issues are warnings (⚠️), not errors,
          preserving original semantics where they do not block commit.
    """
    if not specs_dir.exists():
        return 0, [f"ℹ️ specs dir not found, skipping: {specs_dir}"]
    issues: list[str] = []
    for spec_file in sorted(specs_dir.glob("*.md")):
        text = spec_file.read_text(encoding="utf-8")
        for m in _B_CLASS_RE.finditer(text):
            # Window: 200 chars before + 200 chars after the [B] match
            start = max(0, m.start() - 200)
            end = min(len(text), m.end() + 200)
            window = text[start:end]
            if not _TD_ID_RE.search(window):
                issues.append(
                    f"⚠️  {spec_file.name}: [B] mention without TD-### ID "
                    f"(TD-170: must list TD-### IDs, not just count). "
                    f"Context: ...{window[max(0, m.start()-start-40):m.end()-start+40]}..."
                )
    if issues:
        return 0, issues
    return 0, [f"✅ TD-170 [B]-class specs OK ({specs_dir})"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF TD-170 [B]-class spec validator",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="Path to the GAF repo root (default: %(default)s). "
             "Specs dir is then <root>/docs/specs/legacy-trae/.",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Print report but never exit non-zero.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    specs_dir = root / "docs" / "specs" / "legacy-trae"
    code, messages = check_td170_b_class_specs(specs_dir)
    for m in messages:
        print(m)
    if args.no_fail:
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
