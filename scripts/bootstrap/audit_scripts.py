#!/usr/bin/env python
"""Quarterly scripts/ audit — detect stale scripts (90 days untouched + no README reference).

Purpose:
    Quarterly audit of scripts/ directory to detect:
    1. Scripts not modified in 90+ days
    2. Scripts not referenced in scripts/README.md
    3. Scripts with missing frontmatter (for .py files)

Usage:
    python scripts/bootstrap/audit_scripts.py              # full audit
    python scripts/bootstrap/audit_scripts.py --stale-days 180  # custom threshold
    python scripts/bootstrap/audit_scripts.py --check       # pre-commit mode (exit 1 if stale)

Exit codes:
    0: No stale scripts (or --check mode with < 3 stale)
    1: Stale scripts detected (>= 3 in --check mode)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

STALE_DAYS_DEFAULT = 90


def find_scripts(root: Path) -> list[Path]:
    """Find all script files in scripts/ (recursive)."""
    scripts_dir = root / "scripts"
    if not scripts_dir.exists():
        return []
    extensions = {".py", ".sh", ".ps1", ".ts", ".js"}
    return sorted(
        p for p in scripts_dir.rglob("*")
        if p.is_file() and p.suffix in extensions
    )


def read_readme_refs(root: Path) -> set[str]:
    """Read scripts/README.md and extract referenced script names."""
    readme = root / "scripts" / "README.md"
    if not readme.exists():
        return set()
    text = readme.read_text(encoding="utf-8")
    # Match script filenames mentioned in README
    import re
    refs = set(re.findall(r"[\w\-/]+\.(?:py|sh|ps1|ts|js)", text))
    return refs


def get_mtime_days(path: Path) -> int:
    """Get days since last modification."""
    mtime = path.stat().st_mtime
    now = datetime.now(tz=timezone.utc).timestamp()
    return int((now - mtime) / 86400)


def check_frontmatter(path: Path) -> list[str]:
    """Check if a .py script has frontmatter docstring (first line)."""
    if path.suffix != ".py":
        return []
    try:
        first_line = path.read_text(encoding="utf-8").split("\n", 1)[0]
    except (OSError, UnicodeDecodeError):
        return ["unreadable"]
    if not first_line.startswith(('"""', "'''", "#!")):
        return ["missing docstring"]
    return []


def audit(root: Path, stale_days: int) -> list[dict]:
    """Run full audit, return list of findings."""
    scripts = find_scripts(root)
    readme_refs = read_readme_refs(root)
    findings = []

    for script in scripts:
        rel = script.relative_to(root)
        rel_str = str(rel).replace("\\", "/")
        days_old = get_mtime_days(script)
        in_readme = script.name in readme_refs or rel_str in readme_refs
        fm_issues = check_frontmatter(script)

        issues = []
        if days_old > stale_days:
            issues.append(f"stale ({days_old}d)")
        if not in_readme and "site-packages" not in rel_str and "node_modules" not in rel_str:
            issues.append("not in README")
        issues.extend(fm_issues)

        if issues:
            findings.append({
                "path": rel_str,
                "days_old": days_old,
                "in_readme": in_readme,
                "issues": issues,
            })

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Quarterly scripts/ audit — detect stale scripts"
    )
    parser.add_argument("--stale-days", type=int, default=STALE_DAYS_DEFAULT,
                        help=f"Stale threshold in days (default: {STALE_DAYS_DEFAULT})")
    parser.add_argument("--check", action="store_true",
                        help="Pre-commit mode: exit 1 if >= 3 stale scripts")
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="Repository root (default: cwd)")
    args = parser.parse_args(argv)

    findings = audit(args.root, args.stale_days)

    if not findings:
        print(f"✅ scripts/ audit passed (0 stale scripts, threshold={args.stale_days}d)")
        return 0

    print(f"⚠️  scripts/ audit: {len(findings)} scripts with issues:")
    for f in findings:
        issues_str = ", ".join(f["issues"])
        print(f"  {f['path']} ({f['days_old']}d, README={'Y' if f['in_readme'] else 'N'}): {issues_str}")

    if args.check and len(findings) >= 3:
        print(f"\n❌ {len(findings)} scripts with issues (>= 3 threshold). Consider cleanup.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
