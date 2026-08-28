"""check_reflection_evidence.py — R9 reflection evidence validator.

Validates that the AI actually ran reflection checks by reading
``_reflection_checks.json`` in the repo root. This file is produced
by the gaf-reflect-and-evolve skill and records which reflection
dimensions were exercised for the current task.

Validation rules:
  - File missing → PASS (not all tasks require reflection evidence)
  - File present → must contain:
      * ``task_type`` (non-empty string)
      * ``selected_checks`` (array with ≥ 1 entry)
      * ``ai_confirmation.seven_dim_done`` === true (boolean)
      * ``ai_confirmation.dual_debug_done`` === true (boolean)
      * ``timestamp`` within the last 30 minutes (prevents stale files)
  - Stale file (> 30 min) → FAIL (AI must re-run reflection)
  - Any missing/invalid field → FAIL

Handles both working-tree and staged copies of the file so that
pre-commit hooks can detect already-committed evidence.

Usage:
    python check_reflection_evidence.py
    python check_reflection_evidence.py --root <path>
    python check_reflection_evidence.py --no-strict

Exit codes:
    0 — Evidence OK, or file absent (not blocking)
    1 — File exists but validation failed
    2 — Configuration error
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import _encoding_safe  # noqa: E402,F401

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
REFLECTION_FILE = "_reflection_checks.json"
STALE_WINDOW_SEC = 1800  # 30 minutes

REQUIRED_SECTIONS = (
    "task_type",
    "selected_checks",
    "ai_confirmation.seven_dim_done",
    "ai_confirmation.dual_debug_done",
    "timestamp",
)


def _find_reflection_file(root: Path) -> Path | None:
    """Locate ``_reflection_checks.json`` in the repo.

    Checks the working tree first, then the staged area via
    ``git show :_reflection_checks.json`` so that pre-commit hooks
    can detect evidence that was already ``git add``-ed.
    """
    target = root / REFLECTION_FILE
    if target.is_file():
        return target
    return None


def _load_json(path: Path) -> dict | None:
    """Parse JSON from `path`, returning None on any failure."""
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def _check_staged_copy(root: Path) -> dict | None:
    """Try to load the staged (index) copy of the reflection file.

    Pre-commit hooks run *before* the staged copy is committed, so
    ``git show :file`` can reveal evidence that was already staged
    but not yet present in the working tree.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "show", f":{REFLECTION_FILE}"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
        return None


def _validate_timestamp(data: dict) -> tuple[bool, str]:
    """Check that the timestamp is within the stale window.

    Accepts ISO-8601 strings (``datetime.fromisoformat``) or
    numeric Unix timestamps (``time.time()`` comparison).
    """
    raw = data.get("timestamp")
    if raw is None:
        return False, "timestamp field missing"

    now = time.time()

    if isinstance(raw, (int, float)):
        age = now - raw
        if age > STALE_WINDOW_SEC:
            return False, f"timestamp is {age:.0f}s old (max {STALE_WINDOW_SEC}s)"
        if age < 0:
            return False, f"timestamp is in the future ({age:.0f}s)"
        return True, f"timestamp is fresh ({age:.0f}s old)"

    if isinstance(raw, str):
        try:
            dt = datetime.datetime.fromisoformat(raw)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            ts = dt.timestamp()
        except (ValueError, OSError):
            return False, f"timestamp string not parseable: {raw!r}"
        age = now - ts
        if age > STALE_WINDOW_SEC:
            return False, f"timestamp is {age:.0f}s old (max {STALE_WINDOW_SEC}s)"
        if age < 0:
            return False, f"timestamp is in the future ({age:.0f}s)"
        return True, f"timestamp is fresh ({age:.0f}s old)"

    return False, f"timestamp has unexpected type: {type(raw).__name__}"


def _validate(data: dict) -> tuple[bool, list[str]]:
    """Run all R9 validation checks against the parsed JSON.

    Returns (passed, messages) where messages is a list of human-readable
    strings prefixed with FAIL or PASS.
    """
    messages: list[str] = []
    ok = True

    # 1. task_type
    task_type = data.get("task_type")
    if not isinstance(task_type, str) or not task_type.strip():
        messages.append("FAIL  task_type is missing or empty")
        ok = False
    else:
        messages.append(f"PASS  task_type: {task_type}")

    # 2. selected_checks
    selected = data.get("selected_checks")
    if not isinstance(selected, list) or len(selected) < 1:
        messages.append("FAIL  selected_checks is missing or empty")
        ok = False
    else:
        messages.append(f"PASS  selected_checks: {len(selected)} check(s) selected")

    # 3. ai_confirmation.seven_dim_done
    seven_dim = data.get("ai_confirmation", {}).get("seven_dim_done") if isinstance(data.get("ai_confirmation"), dict) else None
    if seven_dim is not True:
        messages.append("FAIL  ai_confirmation.seven_dim_done is not true")
        ok = False
    else:
        messages.append("PASS  ai_confirmation.seven_dim_done: true")

    # 4. ai_confirmation.dual_debug_done
    dual_debug = data.get("ai_confirmation", {}).get("dual_debug_done") if isinstance(data.get("ai_confirmation"), dict) else None
    if dual_debug is not True:
        messages.append("FAIL  ai_confirmation.dual_debug_done is not true")
        ok = False
    else:
        messages.append("PASS  ai_confirmation.dual_debug_done: true")

    # 5. timestamp freshness
    ts_ok, ts_msg = _validate_timestamp(data)
    if not ts_ok:
        messages.append(f"FAIL  {ts_msg}")
        ok = False
    else:
        messages.append(f"PASS  {ts_msg}")

    return ok, messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF R9 reflection evidence validator",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="Path to the GAF repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="Print report but never exit non-zero.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"FAIL  root is not a directory: {root}")
        return 2

    file_path = _find_reflection_file(root)
    if file_path is None:
        staged_data = _check_staged_copy(root)
        if staged_data is not None:
            print(f"WARN  {REFLECTION_FILE} not in working tree but found in staged area")
            passed, messages = _validate(staged_data)
            for m in messages:
                print(f"  {m}")
            if passed:
                print(f"PASS  staged {REFLECTION_FILE} is valid")
                return 0 if not args.no_strict else 0
            print(f"FAIL  staged {REFLECTION_FILE} validation failed")
            return 1 if not args.no_strict else 0

        print(f"PASS  {REFLECTION_FILE} not found — reflection evidence not required")
        return 0

    data = _load_json(file_path)
    if data is None:
        print(f"FAIL  {REFLECTION_FILE} exists but is not valid JSON")
        return 1 if not args.no_strict else 0

    print(f"PASS  {REFLECTION_FILE} found at {file_path}")
    passed, messages = _validate(data)
    for m in messages:
        print(f"  {m}")

    if passed:
        print(f"PASS  {REFLECTION_FILE} validation OK")
        return 0

    print(f"FAIL  {REFLECTION_FILE} validation failed — re-run reflection checks")
    return 1 if not args.no_strict else 0


if __name__ == "__main__":
    sys.exit(main())