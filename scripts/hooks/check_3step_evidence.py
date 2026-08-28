"""check_3step_evidence.py — v8.3.1 3-step evidence validator.

Each AI commit should be backed by the 3-step evidence trail defined
in Appendix B (problem / solution / verification). This hook enforces
that:

  1. At least one evidence directory for the current day exists
     (named ``<date>-<task>`` under ``.ai-memory/evidence/``).
  2. All three template files are present (or have been replaced by
     real content) for the most recent AI session.
  3. Each file's "## Verification" section actually contains a runnable
     command (so AI can't fake it with lorem ipsum).

Directory layout (3-layer, since the v8.4 simplification):

    .ai-memory/evidence/<date>-<task>/<file>.md

Usage:
    python check_3step_evidence.py             # validate today's dirs
    python check_3step_evidence.py --strict    # fail when any template
                                                # is still a placeholder
    python check_3step_evidence.py --root <p>  # operate on a different
                                                # repo
    python check_3step_evidence.py --no-fail   # print report only

Exit codes:
    0 — OK (or warnings only when --no-fail)
    1 — Missing files or unfilled placeholders
    2 — Configuration error (no .ai-memory dir, etc.)
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse  # noqa: E402
import datetime as _dt  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
AI_MEMORY = REPO_ROOT_DEFAULT / ".ai-memory"
EVIDENCE_DIR = AI_MEMORY / "evidence"
TEMPLATES_DIR = EVIDENCE_DIR / "templates"

REQUIRED_TEMPLATES = (
    "problem.md",
    "solution.md",
    "verification.md",
)

# Phrases that should NEVER appear in a "filled-in" evidence file.
# AI commonly writes these as placeholders and forgets to replace.
PLACEHOLDER_PATTERNS = (
    re.compile(r"TODO", re.IGNORECASE),
    re.compile(r"\[fill in\]", re.IGNORECASE),
    re.compile(r"\bxxx\b", re.IGNORECASE),
    re.compile(r"lorem ipsum", re.IGNORECASE),
)

# A line is "runnable" if it starts with $, python, bash, cmd, ps1, or
# any `pip`/`conda`/`git` invocation. We accept markdown links to
# commands too. This catches pure prose like "I verified it works".
RUNNABLE_HINT = re.compile(
    r"(?m)^[\s>]*(\$|python|bash|sh|cmd|powershell|ps1|pip|conda|git|npm|"
    r"pytest|ruff|mypy|pre-commit)",
)


def _today_dirs(root: Path) -> list[Path]:
    """Return today's evidence directories matching ``<date>-<task>``.

    P1 restructure (spec §6.2) moved evidence dirs to ``active/`` subdir.
    This function checks both the new ``active/`` location and the legacy
    root location for backward compatibility.

    Returns all dirs whose name starts with today's date followed by ``-``.
    """
    today_str = _dt.date.today().isoformat()
    prefix = f"{today_str}-"
    evidence_root = root / ".ai-memory" / "evidence"
    if not evidence_root.exists():
        return []
    matches: list[Path] = []
    # P1+: evidence/active/<date>-<task>/ (新结构, 单一权威源)
    active_dir = evidence_root / "active"
    if active_dir.is_dir():
        for d in active_dir.iterdir():
            if d.is_dir() and d.name.startswith(prefix):
                matches.append(d)
    # Legacy: evidence/<date>-<task>/ (向后兼容, 旧仓库迁移期)
    for d in evidence_root.iterdir():
        if d.is_dir() and d.name.startswith(prefix):
            matches.append(d)
    return sorted(set(matches))


def _iter_evidence_dirs(root: Path) -> list[Path]:
    """Return evidence dirs sorted newest-first.

    P1 restructure (spec §6.2) moved evidence dirs to ``active/`` and
    ``archived/YYYY-MM/`` subdirs. This function scans:
    - ``evidence/active/`` (P1+ 单一权威源)
    - ``evidence/archived/YYYY-MM/`` (P1+ 归档)
    - ``evidence/`` root (legacy, 向后兼容)

    `templates/` (renamed from `_templates/` in TD-158) and any hidden
    directories are excluded. The templates dir legitimately contains
    placeholder text (it IS the template) and must not be scanned as
    historical evidence.
    """
    evidence_root = root / ".ai-memory" / "evidence"
    if not evidence_root.exists():
        return []
    dirs: list[Path] = []
    # P1+: evidence/active/<date>-<task>/
    active_dir = evidence_root / "active"
    if active_dir.is_dir():
        for child in sorted(active_dir.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            if child.name.startswith("_") or child.name.startswith("."):
                continue
            dirs.append(child)
    # P1+: evidence/archived/YYYY-MM/<date>-<task>/
    archived_dir = evidence_root / "archived"
    if archived_dir.is_dir():
        for month_dir in sorted(archived_dir.iterdir(), reverse=True):
            if not month_dir.is_dir():
                continue
            for child in sorted(month_dir.iterdir(), reverse=True):
                if not child.is_dir():
                    continue
                if child.name.startswith("_") or child.name.startswith("."):
                    continue
                dirs.append(child)
    # Legacy: evidence/<date>-<task>/ (向后兼容)
    for child in sorted(evidence_root.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        # TD-158: templates dir renamed from `_templates/` to `templates/`.
        # Skip both old and new names, plus any hidden dir.
        # P1: 也跳过 active/ 和 archived/ 子目录 (已在上面处理)
        if child.name in ("templates", "_templates", "active", "archived"):
            continue
        if child.name.startswith("_") or child.name.startswith("."):
            continue
        dirs.append(child)
    return dirs


def _has_placeholder(text: str) -> list[str]:
    """Return the placeholder phrases found in `text`."""
    hits: list[str] = []
    for pat in PLACEHOLDER_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


def _is_verification_runnable(text: str) -> bool:
    """Decide whether the verification section is a real command, not prose.

    We look for the "## Verification" heading and check whether any
    runnable line follows it before the next heading or EOF.
    """
    match = re.search(r"^##\s*Verification.*$", text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return False
    tail = text[match.end():]
    next_heading = re.search(r"^##\s+", tail, re.MULTILINE)
    section = tail if next_heading is None else tail[: next_heading.start()]
    return bool(RUNNABLE_HINT.search(section))


def check_repo(root: Path, *, strict: bool) -> tuple[int, list[str]]:
    """Run the 3-step evidence check against `root`.

    Returns (exit_code, messages). The exit code is 0 on success,
    1 when something needs fixing, 2 on configuration errors.
    """
    if not (root / ".ai-memory").exists():
        return 2, [f"❌ {root / '.ai-memory'} does not exist; run bootstrap first."]

    issues: list[str] = []
    info: list[str] = []

    # 1. templates dir — informational, not blocking
    if TEMPLATES_DIR.exists():
        for name in REQUIRED_TEMPLATES:
            if not (TEMPLATES_DIR / name).exists():
                issues.append(f"❌ template missing: {TEMPLATES_DIR / name}")
    else:
        info.append(f"ℹ️  templates dir missing (acceptable if evidence inlined): {TEMPLATES_DIR}")

    # 2. today's dirs (3-layer: <date>-<task>)
    today_dirs = _today_dirs(root)
    today_str = _dt.date.today().isoformat()
    if not today_dirs:
        issues.append(
            f"❌ no evidence dir for today ({today_str}) found under {EVIDENCE_DIR}\n"
            f"   fix: mkdir -p {EVIDENCE_DIR}/{today_str}-<task-name> "
            f"&& cp {TEMPLATES_DIR}/{{problem,solution,verification}}.md "
            f"{EVIDENCE_DIR}/{today_str}-<task-name>/"
        )
    else:
        for today in today_dirs:
            for name in REQUIRED_TEMPLATES:
                target = today / name
                if not target.exists():
                    # Allow inlined body: a `_session_*.md` could replace the
                    # template files when all 3 sections are present in one
                    # document. We still warn.
                    info.append(
                        f"ℹ️  {target.name} missing in {today.name} "
                        f"(will be inlined in _session_*.md?)"
                    )
                    continue
                text = target.read_text(encoding="utf-8")
                placeholders = _has_placeholder(text)
                if placeholders:
                    # At commit time (when this hook runs), evidence must be
                    # fully filled in. Placeholders in today's evidence are
                    # errors, not warnings — the commit should be blocked
                    # until the evidence is complete.
                    issues.append(
                        f"❌ {target}: placeholders still present: {placeholders}"
                    )
                if name == "verification.md" and not _is_verification_runnable(text):
                    if strict:
                        issues.append(
                            f"❌ {target}: '## Verification' has no runnable command"
                        )
                    else:
                        info.append(
                            f"⚠️  {target}: '## Verification' has no runnable command"
                        )

    # 3. historical scan: any older dir that still has unfilled placeholders
    today_set = set(today_dirs)
    for d in _iter_evidence_dirs(root):
        if d in today_set:
            continue
        for name in REQUIRED_TEMPLATES:
            f = d / name
            if not f.exists():
                continue
            text = f.read_text(encoding="utf-8")
            if _has_placeholder(text):
                issues.append(
                    f"❌ {f}: historical evidence still has placeholders"
                )

    if issues:
        return 1, issues + info
    if today_dirs:
        return 0, info or [
            f"✅ 3-step evidence OK ({len(today_dirs)} dir(s) for today)"
        ]
    return 0, info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF 3-step evidence validator (v8.3.1)",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="Path to the GAF repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when ## Verification has no runnable command.",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Print report but never exit non-zero.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    code, messages = check_repo(root, strict=args.strict)
    for m in messages:
        print(m)
    if args.no_fail:
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
