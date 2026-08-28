"""append_lesson_block.py — idempotent markdown block appender.

Consolidates the many one-off ``_append_n*.py`` helpers into a single
parameterized tool. It appends a block of text to a target markdown file
only when a marker string is not already present.

Usage
-----
    python scripts/lessons/append_lesson_block.py \\
        --target .ai-memory/meta/failure-modes.md \\
        --marker "### N117:" \\
        --block path/to/n117_failure_block.md

    python scripts/lessons/append_lesson_block.py \\
        --target .ai-memory/summaries/architecture-mistakes.md \\
        --marker "# 46 M1H" \\
        --block path/to/n117_arch_block.md \\
        --dry-run

Exit codes
----------
    0 - block already present (no-op) or appended successfully
    1 - target or block file missing
    2 - configuration / argument error
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: F401  (must be first; reconfigures stdout to UTF-8)

import argparse
import sys
from pathlib import Path

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]


def resolve_target(root: Path, target: str) -> Path:
    """Resolve target path relative to repo root when not absolute."""
    path = Path(target)
    if path.is_absolute():
        return path
    return root / path


def append_block(
    target: Path,
    marker: str,
    block: str,
    *,
    dry_run: bool = False,
) -> int:
    """Append ``block`` to ``target`` if ``marker`` is not already present.

    Returns 0 on success or idempotent no-op, 1 on missing files.
    """
    if not target.exists():
        print(f"ERROR: target not found: {target}", file=sys.stderr)
        return 1

    raw = target.read_bytes()
    marker_bytes = marker.encode("utf-8")
    if marker_bytes in raw:
        print(f"marker already present in {target.name} (no-op)")
        return 0

    # Ensure the existing file ends with at least one blank line.
    if not raw.endswith(b"\n"):
        raw += b"\n"
    if not raw.endswith(b"\n\n"):
        raw += b"\n"

    raw += block.encode("utf-8")

    if dry_run:
        print(f"[dry-run] would append {len(block)} bytes to {target}")
        return 0

    target.write_bytes(raw)
    print(f"appended block to {target.name} ({len(block)} bytes)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Idempotent markdown block appender for GAF lessons"
    )
    parser.add_argument("--target", required=True, help="Target markdown file")
    parser.add_argument("--marker", required=True, help="Idempotency marker string")
    parser.add_argument("--block", required=True, help="File containing the block to append")
    parser.add_argument("--root", default=str(REPO_ROOT_DEFAULT), help="Repository root")
    parser.add_argument("--dry-run", action="store_true", help="Report but do not write")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    target = resolve_target(root, args.target)
    block_path = Path(args.block)
    if not block_path.is_absolute():
        block_path = root / block_path

    if not block_path.exists():
        print(f"ERROR: block file not found: {block_path}", file=sys.stderr)
        return 1

    block_text = block_path.read_text(encoding="utf-8")
    return append_block(target, args.marker, block_text, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
