"""check_evidence_completeness.py — Evidence completeness validator.

Enforces the N126 honest-marking contract: each evidence directory under
``.ai-memory/evidence/active/`` must contain the 3-file triplet
``problem.md`` / ``solution.md`` / ``verification.md``. Incomplete
evidence directories are blocked from commit.

Validation rules:
  - Each evidence dir must contain all 3 files.
  - Missing file → ERROR + exit 1.
  - Empty file (0 bytes) → ERROR + exit 1.
  - File < 50 bytes → WARNING (does not block).
  - Allowlist (``.ai-memory/evidence/.incomplete-allowlist``) skips
    specified dirs (legacy transition, one dir name per line).

Usage:
    python check_evidence_completeness.py             # scan active/
    python check_evidence_completeness.py --path <p>  # scan custom dir
    python check_evidence_completeness.py --no-strict # warn only
    python check_evidence_completeness.py --verbose    # list files per dir
    python check_evidence_completeness.py --allow-incomplete <dir>...

Exit codes:
    0 — All evidence complete (or warnings only with --no-strict)
    1 — One or more evidence directories incomplete
    2 — Configuration error (active/ dir missing)
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

import argparse  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT_DEFAULT = REPO_ROOT_DEFAULT / ".ai-memory" / "evidence"
ACTIVE_DIR_DEFAULT = EVIDENCE_ROOT_DEFAULT / "active"
ALLOWLIST_PATH_DEFAULT = EVIDENCE_ROOT_DEFAULT / ".incomplete-allowlist"

REQUIRED_FILES = (
    "problem.md",
    "solution.md",
    "verification.md",
)

# Files below this size are flagged as suspiciously short (warning only).
MIN_CONTENT_BYTES = 50


def _load_allowlist(path: Path) -> set[str]:
    """Return allowlist dir names (one per line). Empty set if file missing.

    Lines starting with ``#`` and blank lines are ignored. Whitespace
    around dir names is stripped.
    """
    if not path.is_file():
        return set()
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        names.add(stripped)
    return names


def _append_to_allowlist(path: Path, names: list[str]) -> None:
    """Append ``names`` to the allowlist file (idempotent, deduped).

    Creates the file (and parent dir) if missing. Existing entries are
    preserved; only new names are appended.
    """
    existing = _load_allowlist(path)
    new_names = [n for n in names if n and n not in existing]
    if not new_names:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve existing content; append a trailing newline if missing.
    prefix = ""
    if path.is_file():
        old = path.read_text(encoding="utf-8")
        if old and not old.endswith("\n"):
            prefix = "\n"
    with path.open("a", encoding="utf-8") as fh:
        for name in new_names:
            fh.write(f"{prefix}{name}\n")
            prefix = ""


def _iter_evidence_dirs(root: Path) -> list[Path]:
    """Return sorted subdirectories of ``root`` (non-recursive).

    Hidden dirs (starting with ``.`` or ``_``) and non-dir entries are
    skipped.
    """
    if not root.is_dir():
        return []
    dirs: list[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name.startswith("_"):
            continue
        dirs.append(child)
    return dirs


def _check_dir(dir_path: Path, *, verbose: bool) -> dict[str, list[str]]:
    """Validate one evidence directory.

    Returns a dict with keys ``errors`` and ``warnings`` (lists of
    human-readable messages). Empty lists mean the dir is complete.
    """
    errors: list[str] = []
    warnings: list[str] = []
    for name in REQUIRED_FILES:
        target = dir_path / name
        if not target.is_file():
            errors.append(f"  ❌ missing: {name}")
            continue
        size = target.stat().st_size
        if size == 0:
            errors.append(f"  ❌ empty (0 bytes): {name}")
        elif size < MIN_CONTENT_BYTES:
            warnings.append(
                f"  ⚠️  small ({size} bytes < {MIN_CONTENT_BYTES}): {name}"
            )
        if verbose:
            print(f"    {name}: {size} bytes")
    return {"errors": errors, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF evidence completeness validator (N126)",
    )
    parser.add_argument(
        "--path",
        default=str(ACTIVE_DIR_DEFAULT),
        help=(
            "Evidence directory to scan (default: %(default)s). "
            "Only direct subdirectories are checked."
        ),
    )
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exit 1 on incomplete evidence (default: on; use --no-strict to warn only).",
    )
    parser.add_argument(
        "--allow-incomplete",
        nargs="+",
        default=[],
        metavar="DIR_NAME",
        help=(
            "Append dir name(s) to the allowlist file and skip them this run. "
            "Use for legacy incomplete evidence during transition."
        ),
    )
    parser.add_argument(
        "--allowlist",
        default=str(ALLOWLIST_PATH_DEFAULT),
        help="Path to allowlist file (default: %(default)s).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print file list and sizes for each scanned directory.",
    )
    args = parser.parse_args(argv)

    allowlist_path = Path(args.allowlist).resolve()
    # If user passed --allow-incomplete, persist names before scanning.
    if args.allow_incomplete:
        _append_to_allowlist(allowlist_path, args.allow_incomplete)

    scan_root = Path(args.path).resolve()
    if not scan_root.is_dir():
        print(f"❌ scan path is not a directory: {scan_root}")
        return 2

    allowlist = _load_allowlist(allowlist_path)

    dirs = _iter_evidence_dirs(scan_root)
    if not dirs:
        print(f"ℹ️  no evidence subdirectories under {scan_root}")
        print(f"   allowlist: {allowlist_path} ({len(allowlist)} entries)")
        return 0

    complete = 0
    incomplete_dirs: list[str] = []
    skipped_dirs: list[str] = []
    all_warnings: list[str] = []

    print(f" scanning: {scan_root}")
    print(f" allowlist: {allowlist_path} ({len(allowlist)} entries)")
    print(f" scanned {len(dirs)} evidence directory(ies)")
    print("-" * 60)

    for d in dirs:
        if d.name in allowlist:
            skipped_dirs.append(d.name)
            print(f" SKIP  {d.name} (allowlisted)")
            continue
        if args.verbose:
            print(f" DIR   {d.name}")
        result = _check_dir(d, verbose=args.verbose)
        if result["errors"]:
            incomplete_dirs.append(d.name)
            print(f" FAIL  {d.name}")
            for msg in result["errors"]:
                print(msg)
            for msg in result["warnings"]:
                print(msg)
                all_warnings.append(f"{d.name}: {msg}")
        elif result["warnings"]:
            complete += 1
            print(f" WARN  {d.name}")
            for msg in result["warnings"]:
                print(msg)
                all_warnings.append(f"{d.name}: {msg}")
        else:
            complete += 1
            print(f" OK    {d.name}")

    print("-" * 60)
    print(f" scanned: {len(dirs)}  complete: {complete}  "
          f"incomplete: {len(incomplete_dirs)}  skipped: {len(skipped_dirs)}")
    if incomplete_dirs:
        print(" incomplete list:")
        for name in incomplete_dirs:
            print(f"   - {name}")
    if all_warnings:
        print(f" warnings: {len(all_warnings)} (small files, non-blocking)")

    if incomplete_dirs and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
