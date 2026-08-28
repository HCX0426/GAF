"""check_spec_id_collision.py — TD-322 (spec-84 方案 B) pre-commit hook:
防止新增 spec 文件 spec_id 与已有冲突.

When a new ``docs/specs/legacy-trae/*.md`` file is staged for commit
(spec-2026-07-26-trae-specs-plans-merge 迁移自旧 trae-specs 目录),
this hook checks
whether its ``spec_id`` (frontmatter or filename-extracted) collides with an
existing spec_id. If collision detected, the commit is blocked with a hint to
use ``spec-NN-a/b`` suffix or the next free ``spec-NN``.

The hook is a no-op (exit 0) when:
- No docs/specs/legacy-trae/*.md file is staged, OR
- The staged spec's spec_id does not collide with existing ones

Historical collisions (spec-36/38/39/41/42/43/44/45, TD-322 wontfix) are
NOT blocked — only NEW collisions introduced by this commit are.

Usage
-----
    python scripts/hooks/check_spec_id_collision.py            # auto-detect staged
    python scripts/hooks/check_spec_id_collision.py --no-fail  # warn only
    python scripts/hooks/check_spec_id_collision.py --force    # always check

Exit codes
----------
    0 - no spec files staged, OR no new collision introduced
    1 - new spec_id collision detected (blocks commit unless --no-fail)
    2 - configuration / argument error

TD-322 (spec-84 方案 B, 2026-07-21): TD-322 wontfix — 历史同号多版本保留;
此 hook 防止新增 spec 冲突 (治本).
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
_GOVERNANCE_DIR = _SCRIPTS_DIR / "governance"
for _p in (_SCRIPTS_DIR, _GOVERNANCE_DIR):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

import argparse  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from sync_spec_index import (  # noqa: E402
    extract_spec_id_from_filename,
    parse_frontmatter,
)

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
SPECS_PREFIX = "docs/specs/legacy-trae/"

# TD-322 历史已知 wontfix 冲突 spec_id 列表 (spec-36/38/39/41/42/43/44/45)
# 这批 spec 在 v8.x 时期产生, 同号多版本 wontfix (不阻塞, 仅记录);
# hook 仅防止"新增"冲突, 这批历史冲突豁免.
HISTORICAL_WONTFIX_COLLISIONS: set[str] = {
    "spec-36", "spec-38", "spec-39", "spec-41",
    "spec-42", "spec-43", "spec-44", "spec-45",
}


def _staged_spec_files(repo_root: Path) -> list[Path]:
    """Return list of staged docs/specs/legacy-trae/*.md files (absolute paths).

    Uses ``git diff --cached --name-only`` so the hook only fires when a spec
    file is actually part of the commit. Returns empty list on git error
    (fail-open).
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    staged: list[Path] = []
    for line in result.stdout.splitlines():
        normalized = line.replace("\\", "/").lstrip("./")
        if not normalized.startswith(SPECS_PREFIX):
            continue
        if not normalized.endswith(".md"):
            continue
        staged.append(repo_root / normalized)
    return staged


def _extract_spec_id(md_path: Path) -> str | None:
    """Extract spec_id from frontmatter, fallback to filename."""
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = parse_frontmatter(text)
    if fm.get("spec_id"):
        return fm["spec_id"]
    return extract_spec_id_from_filename(md_path.name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="TD-322 (spec-84 方案 B) pre-commit hook: 防止新增 spec_id 冲突",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run the check even when no spec files are staged",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Warn-only mode: print warning but do not exit 1",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF repo root (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    specs_dir = repo_root / "docs" / "specs" / "legacy-trae"

    staged_specs = _staged_spec_files(repo_root)
    if not staged_specs and not args.force:
        return 0  # no spec files in this commit — skip

    if not specs_dir.is_dir():
        print(f"ERROR: specs dir not found: {specs_dir}", file=sys.stderr)
        return 2

    # Build existing spec_id → filenames map (excluding staged files for new-file check)
    # For modified existing specs, we want to compare against the on-disk state
    # minus the staged file itself (so a spec editing its own frontmatter doesn't
    # collide with itself).
    existing: dict[str, list[str]] = {}
    for md_file in sorted(specs_dir.glob("*.md")):
        sid = _extract_spec_id(md_file)
        if sid:
            existing.setdefault(sid, []).append(md_file.name)

    # For each staged spec, check if its spec_id collides with any OTHER file
    failures: list[str] = []
    for staged_path in staged_specs:
        staged_sid = _extract_spec_id(staged_path)
        if not staged_sid:
            continue  # unable to determine spec_id, skip
        # Skip historical wontfix collisions (TD-322 documented, not blocking)
        if staged_sid in HISTORICAL_WONTFIX_COLLISIONS:
            continue
        # Other files with same spec_id (excluding the staged file itself)
        others = [fn for fn in existing.get(staged_sid, []) if fn != staged_path.name]
        if others:
            failures.append(
                f"  - {staged_path.name} (spec_id={staged_sid}) collides with: {', '.join(others)}"
            )

    if not failures:
        return 0

    print("❌ spec_id 冲突检测到 (TD-322 spec-84 方案 B):", file=sys.stderr)
    for f in failures:
        print(f, file=sys.stderr)
    print("", file=sys.stderr)
    print("💡 修复方案:", file=sys.stderr)
    print("   - 用 spec-NN-a/b 后缀 (如 spec-83a, spec-83b)", file=sys.stderr)
    print("   - 或用下一个空闲 spec-NN (查 .ai-memory/ref/spec-index.md 找空闲号)", file=sys.stderr)
    print("   - 历史 spec-36/38/39/41/42/43/44/45 同号多版本 wontfix (TD-322), 新增冲突不允许", file=sys.stderr)
    print("", file=sys.stderr)
    print("   查看索引: python scripts/governance/sync_spec_index.py --check", file=sys.stderr)
    print("   生成索引: python scripts/governance/sync_spec_index.py", file=sys.stderr)

    if args.no_fail:
        print("⚠️ --no-fail 模式: 仅警告, 不阻塞 commit", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
