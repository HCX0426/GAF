"""gaf_governance_batch.py - Run all GAF governance checks in one pre-commit hook.

Why this exists
---------------
pre-commit with ``language: python`` creates a managed virtualenv per hook
and adds ~5-6s venv activation overhead on every invocation. With 11
governance hooks registered in ``.pre-commit-config.yaml``, that's ~60s of
pure framework overhead on every ``git commit`` (observed: 71s total).

This batch script collapses 24 governance checks into a single
pre-commit hook invocation, reducing total commit time from ~71s to ~5s
while preserving per-check status reporting. The 7 pre-commit Python hooks
that used to be separate `language: python` entries (auto-archive,
spec-id-collision, evidence-completeness, B2 evidence, spec-context,
tier-alignment, code-rules) were folded in under TD-377 (2026-08-23) to
remove ~7 redundant interpreter cold-starts per commit.

How it works (v2 — import-based, N171 optimization)
----------------------------------------------------
Originally this script used ``subprocess.run`` to launch each check as a
separate Python process, costing ~0.3s per subprocess startup × 10 = 3s
overhead. Under N171 (script performance measurement discipline), this
was flagged as exceeding the < 1s ideal baseline for batch scripts.

v2 switches to in-process imports: each check script's ``main()``
function is invoked directly via ``importlib``. This eliminates 10 × 0.3s
subprocess startup overhead. Expected: 3.08s → ~1.5s.

What it runs — two tiers (TD-377 option B split, 2026-08-23)
------------------------------------------------------------
  COMMIT hot-path = all CHECKS except 6 heavy pure-verify modules
  (sync_skills, check_deps_sync, sync_docs_index, scan_scripts_vs_readme,
  promote_lessons, sync_spec_index) -> 17 checks, ~1.3-2s warm. PRE-PUSH
  cold-path = those 6 modules (7 entries; promote_lessons x2) -> 7 checks,
  ~1.4s. Tree-modifying regen (sync_ai_memory, auto_archive_specs) stays on
  COMMIT. Authoritative ordered list is the CHECKS tuple below.
    1. check_session_active.py --check       (session active guard)
    2. sync_ai_memory.py                      (regenerates auto-files)
    3. check_3step_evidence.py                (evidence trail validator)
    4. check_lessons_updated.py               (lesson front-matter validator)
    5. check_spec_consistency.py              (TD-170 [B] specs)
    6. sync_skills.py --check                 (5 skills + 1 rule distribution)
    7. promote_lessons.py --dry-run           (lesson promotion proposals)
    8. sync_docs_index.py --check             (docs/ index drift guard)
    9. check_path_consistency.py              (inline path drift guard)
   10. check_yn_matrices_index.py             (Y/N matrix index drift guard)
   11. sync_spec_index.py --check             (spec index drift guard)
   12. check_doc_code_sync.py                 (TD-325 code-doc causal binding)
   13. check_doc_path_drift.py                 (doc path drift guard)
   -- Folded from separate pre-commit hooks under TD-377 (2026-08-23):
   14. auto_archive_specs.py                   (archive completed specs)
   15. check_spec_id_collision.py              (prevent new spec_id conflicts)
   16. check_evidence_completeness.py          (N126 3-file triplet)
   17. check_big_change_hook.py                (TD-321 B2 evidence)
   18. check_spec_context.py                   (TD-342 spec-context carrier)
   19. check_tier_alignment.py                 (v9.2 tier feedback)
   20. check_code_rules.py                     (M1 AST static check)

What it does NOT run (must stay separate)
------------------------------------------
    - check_git_status_after_hook.py (N105 MM state guard)
      Must run LAST after all hooks have had a chance to modify the working
      tree. Registered as a separate ``gaf-git-status-check`` hook that
      runs after this batch.

Exit codes
----------
    0 - all checks passed (or warnings only)
    1 - at least one check failed
    2 - configuration error (script not found, etc.)

Usage
-----
    # Registered in .pre-commit-config.yaml as:
    - id: gaf-governance-batch
      name: GAF governance batch (24 checks, single venv)
      entry: python scripts/hooks/gaf_governance_batch.py
      language: python
      pass_filenames: false
      always_run: true
      stages: [pre-commit]

    # Manual run for debugging:
    python scripts/hooks/gaf_governance_batch.py
    python scripts/hooks/gaf_governance_batch.py --no-fail   # warn only
    python scripts/hooks/gaf_governance_batch.py --root <p> # different repo
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import fnmatch
import importlib
import io
import sys
import time
from collections.abc import Callable
from pathlib import Path

# (module_path, function_name, args, display_name)
# module_path is relative to scripts/ dir (e.g. "bootstrap.check_session_active")
# Order matters: sync_ai_memory runs early so downstream checks see fresh state.
CHECKS: list[tuple[str, str, list[str], str]] = [
    ("bootstrap.check_session_active", "main", ["--check"], "session active"),
    ("bootstrap.sync_ai_memory", "main", [], "sync_ai_memory"),
    ("hooks.check_3step_evidence", "main", [], "3-step evidence"),
    ("hooks.check_lessons_updated", "main", [], "lessons front-matter"),
    ("hooks.check_spec_consistency", "main", [], "TD-170 [B] specs"),
    ("bootstrap.sync_skills", "main", ["--check"], "5 skills + 1 rule"),
    ("lessons.promote_lessons", "main", ["--dry-run"], "promote lessons"),
    ("lessons.promote_lessons", "main", ["--check-cap"], "active N## cap (v9.2)"),
    ("bootstrap.sync_docs_index", "main", ["--check"], "docs/ index"),
    ("hooks.check_path_consistency", "main", [], "path consistency"),
    ("hooks.check_yn_matrices_index", "main", [], "Y/N matrices index"),
    ("governance.sync_spec_index", "main", ["--check"], "spec index drift"),
    ("hooks.check_doc_code_sync", "main", [], "doc-code sync"),
    ("hooks.check_doc_path_drift", "main", [], "doc-path-drift"),
    ("hooks.check_claimed_rules", "check_unclosed_review", [], "M2 review-closure"),
    ("hooks.check_deps_sync", "main", [], "deps-sync"),
    ("bootstrap.scan_scripts_vs_readme", "main", ["--check"], "scripts-readme"),
    # --- TD-377 (2026-08-23): fold the 7 separate pre-commit Python hooks
    #     into this single batch process. Previously each was a distinct
    #     `language: python` pre-commit entry, spawning its own interpreter
    #     (~0.3-0.5s cold start each). Consolidating here eliminates that
    #     redundant process-spawn overhead. gaf-git-status-check (N105) stays
    #     a separate LAST hook because it must run after all tree-modifying
    #     hooks. auto-archive runs early-ish (after sync_ai_memory) to keep
    #     active/ clean before downstream validators.
    ("bootstrap.auto_archive_specs", "main", [], "auto-archive specs"),
    ("hooks.check_spec_id_collision", "main", [], "spec-id collision"),
    ("hooks.check_evidence_completeness", "main", [], "evidence completeness"),
    ("hooks.check_big_change_hook", "main", [], "B2 evidence"),
    ("hooks.check_spec_context", "main", [], "spec-context carrier"),
    ("hooks.check_tier_alignment", "main", [], "tier alignment"),
    ("hooks.check_code_rules", "main", [], "code rules (M1)"),
]


def _ensure_scripts_on_path(root: Path) -> None:
    """Add scripts/ dir to sys.path so check modules can be imported."""
    scripts_dir = root / "scripts"
    scripts_str = str(scripts_dir)
    if scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)


def _check_matches(
    check: tuple[str, str, list[str], str], patterns: list[str]
) -> bool:
    """True if a check's module_path or display matches any fnmatch pattern."""
    module_path, _func, _check_args, display = check
    return any(
        fnmatch.fnmatch(module_path, p) or fnmatch.fnmatch(display, p)
        for p in patterns
    )


def _load_check(module_path: str, func_name: str) -> Callable:
    """Import the check module and return its main() function.

    Uses importlib with full module reload to avoid stale state when
    the batch script is invoked multiple times in the same Python
    session (e.g. during development).
    """
    # Force reimport in case module was loaded before (dev loop)
    if module_path in sys.modules:
        module = importlib.reload(sys.modules[module_path])
    else:
        module = importlib.import_module(module_path)
    return getattr(module, func_name)


def _run_check_in_process(
    func: Callable,
    args: list[str],
    display: str,
) -> tuple[bool, float, str]:
    """Run a check's main() in-process, capturing stdout/stderr.

    Supports both signatures:
        main(argv: list[str] | None = None) -> int   # preferred
        main() -> int                                 # legacy, uses sys.argv

    For legacy signatures, we monkey-patch sys.argv temporarily.
    """
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    start = time.monotonic()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            # Try the modern signature first (argv parameter)
            try:
                code = func(args)
            except TypeError:
                # Legacy signature: main() reads sys.argv
                old_argv = sys.argv
                sys.argv = [display] + args
                try:
                    code = func()
                finally:
                    sys.argv = old_argv
    except SystemExit as e:
        # A folded hook that still calls sys.exit() (e.g. outside __main__
        # guard) must not terminate the whole batch. Treat exit 0 as pass.
        elapsed = time.monotonic() - start
        code = e.code if isinstance(e.code, int) else 1
        passed = code == 0
        return passed, elapsed, f"SystemExit({code})"
    except Exception as e:
        elapsed = time.monotonic() - start
        return False, elapsed, f"EXCEPTION: {type(e).__name__}: {e}"
    elapsed = time.monotonic() - start
    passed = code == 0
    out_lines = [ln for ln in buf_out.getvalue().splitlines() if ln.strip()][-5:]
    err_lines = [ln for ln in buf_err.getvalue().splitlines() if ln.strip()][-3:]
    tail = "\n".join(out_lines + (["---stderr---"] + err_lines if err_lines else []))
    return passed, elapsed, tail


def _append_performance_baseline(
    repo_root: Path,
    batch_pass: int,
    batch_total: int,
    elapsed_s: float,
    failures: list[str],
) -> None:
    """Append a row to docs/reference/performance-baseline.md (Wave 3 — N171/N173).

    spec-2026-07-26-ai-governance-execution-rate-fix Wave 3: governance-batch
    完成时自动 append (timestamp + pass/total + elapsed + notes). 失败时也
    append (notes 字段标 "FAILED: <failures>").

    Idempotent: if the file does not exist, no-op (sync_docs_index will create
    it on next run; for first-time setup, see docs/reference/performance-baseline.md
    template in spec §5 Wave 3).
    """
    baseline_path = repo_root / "docs" / "reference" / "performance-baseline.md"
    if not baseline_path.is_file():
        # File missing — skip auto-append (avoid creating partial file)
        return

    timestamp = datetime.datetime.now(datetime.UTC).astimezone().isoformat(timespec="seconds")
    notes = f"FAILED: {', '.join(failures)}" if failures else "all pass"
    # Escape pipes in notes to avoid breaking the markdown table
    notes_escaped = notes.replace("|", "\\|")

    new_row = f"| {timestamp} | {batch_pass} | {batch_total} | {elapsed_s:.2f} | {notes_escaped} |\n"

    # Find the "## governance-batch 耗时记录" section and append after the last table row.
    # Strategy: read file, find the section header, find the table header + separator,
    # then insert the new row after the last data row (before the next blank line or section).
    try:
        content = baseline_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return

    section_marker = "## governance-batch 耗时记录"
    section_idx = content.find(section_marker)
    if section_idx == -1:
        # Section missing — skip (don't silently create partial structure)
        return

    # Find the table header line (| timestamp | batch_pass | ...)
    table_header_marker = "| timestamp | batch_pass |"
    header_idx = content.find(table_header_marker, section_idx)
    if header_idx == -1:
        return

    # Find the separator line (|---|---|...) after the header
    sep_idx = content.find("|---", header_idx)
    if sep_idx == -1:
        return

    # Find the end of the separator line
    sep_end_idx = content.find("\n", sep_idx)
    if sep_end_idx == -1:
        return

    # Find the next blank line or section header after the separator — that's the
    # boundary of the table.
    rest = content[sep_end_idx + 1:]
    lines = rest.splitlines(keepends=True)
    insert_offset = sep_end_idx + 1
    last_data_end = insert_offset
    for ln in lines:
        stripped = ln.strip()
        if not stripped or stripped.startswith("#"):
            # Blank line or next section header — table ends here
            break
        if not ln.lstrip().startswith("|"):
            break
        last_data_end = insert_offset + len(ln)
        insert_offset = last_data_end

    new_content = content[:last_data_end] + new_row + content[last_data_end:]
    try:
        baseline_path.write_text(new_content, encoding="utf-8")
    except OSError:
        pass
    else:
        # N190 root-cause fix: re-stage the file after writing so the
        # pre-commit framework doesn't see "files were modified by this
        # hook" and block the commit. Without this, governance-batch's
        # legitimate write to performance-baseline.md creates a MM
        # state that pre-commit treats as a hook failure (even though
        # N105 hook itself now whitelists this path).
        # Best-effort: if `git add` fails (e.g. not in a git repo, or
        # file is gitignored), silently skip — the write itself still
        # succeeded.
        import subprocess

        with contextlib.suppress(OSError, ValueError):
            # ValueError: baseline_path not under repo_root (shouldn't happen)
            # OSError: git binary not on PATH (extremely rare)
            subprocess.run(
                ["git", "add", "--", str(baseline_path.relative_to(repo_root))],
                cwd=str(repo_root),
                check=False,
                capture_output=True,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="GAF governance batch checker (24 checks in one hook)")
    parser.add_argument("--root", default=".", help="repo root (default: cwd)")
    parser.add_argument("--no-fail", action="store_true", help="warn only, always exit 0")
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="fnmatch patterns (module_path or display) of checks to SKIP",
    )
    parser.add_argument(
        "--select",
        nargs="*",
        default=[],
        help="if given, run ONLY checks whose module_path/display matches any pattern",
    )
    parser.add_argument(
        "--warn",
        nargs="*",
        default=[],
        help="fnmatch patterns of checks downgraded to warn: a failed check reports WARN but "
        "does not block (exit 0). Gate-4 钩子分级 (2026-08-26): 形式合规类检查降级不阻塞, "
        "真防护类保持 hard.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / ".git").exists() and not (root / ".pre-commit-config.yaml").exists():
        print(f"[governance-batch] ERROR: {root} is not a git repo root", file=sys.stderr)
        return 2

    _ensure_scripts_on_path(root)

    # Apply --select / --skip filters (TD-377 option B: split hot/cold paths)
    checks = CHECKS
    if args.select:
        checks = [c for c in checks if _check_matches(c, args.select)]
    if args.skip:
        checks = [c for c in checks if not _check_matches(c, args.skip)]

    print(f"[governance-batch] Running {len(checks)} checks in-process (v2 import-based, N171 optimized)")
    print(f"[governance-batch] repo: {root}")
    print()

    failures: list[str] = []
    warns: list[str] = []
    total_start = time.monotonic()
    for module_path, func_name, check_args, display in checks:
        check = (module_path, func_name, check_args, display)
        try:
            func = _load_check(module_path, func_name)
        except (ImportError, AttributeError) as e:
            print(f"  [SKIP] {display:30} module load failed: {e}")
            failures.append(f"{display} (module load failed)")
            continue
        passed, elapsed, tail = _run_check_in_process(func, check_args, display)
        is_warn = _check_matches(check, args.warn)
        if passed:
            status = "PASS"
        elif is_warn:
            status = "WARN"
            warns.append(display)
        else:
            status = "FAIL"
            failures.append(display)
        print(f"  [{status}] {display:30} {elapsed:5.2f}s  {module_path}")
        if not passed and tail:
            for ln in tail.splitlines():
                print(f"          | {ln}")

    total_elapsed = time.monotonic() - total_start
    print()
    print(
        f"[governance-batch] {len(checks) - len(failures)}/{len(checks)} passed "
        f"(+{len(warns)} warn) in {total_elapsed:.2f}s"
    )

    # Wave 3 (spec-2026-07-26-ai-governance-execution-rate-fix): auto-append
    # performance data to docs/reference/performance-baseline.md. Best-effort,
    # never blocks commit (file missing or write error → silent skip).
    _append_performance_baseline(
        repo_root=root,
        batch_pass=len(checks) - len(failures),
        batch_total=len(checks),
        elapsed_s=total_elapsed,
        failures=failures,
    )

    if failures:
        print(f"[governance-batch] FAILED: {', '.join(failures)}", file=sys.stderr)
        return 0 if args.no_fail else 1

    print("[governance-batch] All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
