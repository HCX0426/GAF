"""gaf_post_commit_batch.py - Run post-commit reflection checks in one hook.

Why this exists
---------------
pre-commit with ``language: python`` adds ~1s venv activation overhead per
hook. With 2 post-commit hooks registered, that's ~2s of pure framework
overhead on every ``git commit`` (observed: 2.37s total, 0.45s actual work).

This batch script collapses 2 post-commit checks into a single hook
invocation, reducing post-commit time from ~2.37s to ~1.2s.

Both checks are non-blocking (post-commit hooks run AFTER the commit is
created and cannot fail it). They only print WARNINGS to stderr to remind
the developer to run the reflection checklist (N134).

What it runs
------------
    1. post_commit_reflection_check.py  (N134 evidence + A/B/C classification)
    2. select_reflection_checks.py --diff HEAD~1  (P4 auto-select Y/N items)
    3. check_claimed_rules.py (M2 声称-激活率回执: commit message N## vs diff 证据)

Exit codes
----------
    Always 0 (post-commit hooks cannot fail a commit).

Usage
-----
    - id: gaf-post-commit-batch
      name: GAF post-commit batch (reflection + P4 checklist)
      entry: python scripts/hooks/gaf_post_commit_batch.py
      language: python
      pass_filenames: false
      always_run: true
      stages: [post-commit]
"""
from __future__ import annotations

import contextlib
import importlib
import io
import sys
import time
from collections.abc import Callable
from pathlib import Path

# (module_path, function_name, args, display_name)
CHECKS: list[tuple[str, str, list[str], str]] = [
    ("hooks.post_commit_reflection_check", "main", [], "N134 reflection"),
    ("select_reflection_checks", "main", ["--diff", "HEAD~1"], "P4 checklist"),
    ("hooks.check_claimed_rules", "main", [], "M2 claimed-rules"),
]


def _ensure_scripts_on_path(root: Path) -> None:
    """Add scripts/ and scripts/hooks/ to sys.path."""
    for p in [root / "scripts", root / "scripts" / "hooks"]:
        p_str = str(p)
        if p_str not in sys.path:
            sys.path.insert(0, p_str)


def _load_check(module_path: str, func_name: str) -> Callable:
    """Import the check module and return its main() function."""
    if module_path in sys.modules:
        module = importlib.reload(sys.modules[module_path])
    else:
        module = importlib.import_module(module_path)
    return getattr(module, func_name)


def _run_check_in_process(
    func: Callable,
    args: list[str],
    display: str,
) -> tuple[int, float, str]:
    """Run a check's main() in-process, capturing stdout/stderr.

    Returns (exit_code, elapsed_seconds, output_tail).
    """
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    start = time.monotonic()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            try:
                code = func(args)
            except TypeError:
                old_argv = sys.argv
                sys.argv = [display] + args
                try:
                    code = func()
                finally:
                    sys.argv = old_argv
    except Exception as e:
        elapsed = time.monotonic() - start
        return 1, elapsed, f"EXCEPTION: {type(e).__name__}: {e}"
    elapsed = time.monotonic() - start
    out_lines = [ln for ln in buf_out.getvalue().splitlines() if ln.strip()][-3:]
    err_lines = [ln for ln in buf_err.getvalue().splitlines() if ln.strip()][-3:]
    tail = "\n".join(out_lines + (["---stderr---"] + err_lines if err_lines else []))
    return code, elapsed, tail


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    _ensure_scripts_on_path(root)

    print("[post-commit-batch] Running 3 checks in-process (v2 import-based, N171 optimized)")
    print()

    total_start = time.monotonic()
    for module_path, func_name, check_args, display in CHECKS:
        try:
            func = _load_check(module_path, func_name)
        except (ImportError, AttributeError) as e:
            print(f"  [SKIP] {display:25} module load failed: {e}")
            continue
        code, elapsed, tail = _run_check_in_process(func, check_args, display)
        # post-commit hooks are advisory: print status but never fail
        status = "OK" if code == 0 else "WARN"
        print(f"  [{status}] {display:25} {elapsed:5.2f}s  {module_path}")
        if tail and code != 0:
            for ln in tail.splitlines():
                print(f"          | {ln}")

    total_elapsed = time.monotonic() - total_start
    print(f"[post-commit-batch] {len(CHECKS)} checks in {total_elapsed:.2f}s (advisory, always exit 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
