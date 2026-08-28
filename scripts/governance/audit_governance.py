#!/usr/bin/env python3

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent.parent

CLEANUP_CHEATSHEET = SCRIPTS_DIR / "cleanup_cheatsheet.py"
RETIRE_RULES = SCRIPTS_DIR / "retire_rules.py"
LIFECYCLE_REPORT = SCRIPTS_DIR / "lifecycle_report.py"

AUDIT_DIR = REPO_ROOT / ".ai-memory" / "governance"
AUDIT_REPORT = AUDIT_DIR / "audit-summary.md"


def run_script(script_path, args=None, cwd=None):
    """Run a governance script and return stdout, stderr, exit code."""
    if not script_path.exists():
        return "", f"Script not found: {script_path}", 1

    if args is None:
        args = []

    cmd = [sys.executable, str(script_path)] + args
    if cwd is None:
        cwd = str(REPO_ROOT)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout, proc.stderr, proc.returncode


def run_cleanup_cheatsheet(exec_mode=False, days=None):
    """Run cleanup_cheatsheet.py."""
    args = []
    if exec_mode:
        args.append("--execute")
    else:
        args.append("--dry-run")
    if days is not None:
        args.extend(["--days", str(days)])
    stdout, stderr, rc = run_script(CLEANUP_CHEATSHEET, args)
    return {
        'script': 'cleanup_cheatsheet',
        'stdout': stdout,
        'stderr': stderr,
        'exit_code': rc,
        'mode': 'execute' if exec_mode else 'dry-run',
    }


def run_retire_rules(exec_mode=False, days=None):
    """Run retire_rules.py."""
    args = []
    if exec_mode:
        args.append("--execute")
    else:
        args.append("--dry-run")
    if days is not None:
        args.extend(["--days", str(days)])
    stdout, stderr, rc = run_script(RETIRE_RULES, args)
    return {
        'script': 'retire_rules',
        'stdout': stdout,
        'stderr': stderr,
        'exit_code': rc,
        'mode': 'execute' if exec_mode else 'dry-run',
    }


def run_lifecycle_report(write=True):
    """Run lifecycle_report.py."""
    args = []
    if write:
        args.append("--stdout")
    stdout, stderr, rc = run_script(LIFECYCLE_REPORT, args)
    return {
        'script': 'lifecycle_report',
        'stdout': stdout,
        'stderr': stderr,
        'exit_code': rc,
    }


def generate_audit_summary(results, exec_mode):
    """Generate unified audit summary from all script results."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# GAF Governance Audit Summary",
        "",
        f"_Generated: {now}_",
        f"_Mode: {'EXECUTE (changes applied)' if exec_mode else 'DRY-RUN (no changes)'}_",
        "",
        "## Audit Overview",
        "",
    ]

    for r in results:
        status = "✅ PASS" if r['exit_code'] == 0 else f"⚠️ EXIT {r['exit_code']}"
        if r.get('mode'):
            lines.append(f"- **{r['script']}** [{r['mode']}]: {status}")
        else:
            lines.append(f"- **{r['script']}**: {status}")

    lines.append("")

    for r in results:
        lines.append(f"## {r['script'].replace('_', ' ').title()}")
        lines.append("")
        if r['stdout']:
            stdout_lines = r['stdout'].strip().split('\n')
            for sl in stdout_lines[:30]:
                lines.append(f"  {sl}")
            if len(stdout_lines) > 30:
                lines.append(f"  ... ({len(stdout_lines) - 30} more lines)")
        if r['exit_code'] != 0 and r['stderr']:
            lines.append("")
            lines.append("  **Errors:**")
            for el in r['stderr'].strip().split('\n')[:10]:
                lines.append(f"    {el}")
        lines.append("")

    lines.append("## Next Steps")
    lines.append("")

    recommendations = []

    cheatsheet_result = None
    retire_result = None
    for r in results:
        if r['script'] == 'cleanup_cheatsheet':
            cheatsheet_result = r
        elif r['script'] == 'retire_rules':
            retire_result = r

    if cheatsheet_result and 'dormant' in cheatsheet_result['stdout'].lower():
        recommendations.append(
            "- Run `python scripts/governance/cleanup_cheatsheet.py --execute` "
            "to mark dormant entries in cheatsheet"
        )

    if retire_result and 'eligible' in retire_result['stdout'].lower():
        recommendations.append(
            "- Run `python scripts/governance/retire_rules.py --execute` "
            "to move eligible N## rules to Dormant section"
        )

    if not recommendations:
        recommendations.append("- No immediate actions recommended.")
        recommendations.append("- Schedule periodic audit: `python scripts/governance/audit_governance.py`")

    lines.extend(recommendations)
    lines.append("")

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Integrated governance audit — runs all lifecycle scripts"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run all scripts in dry-run mode (default)",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Run cleanup scripts in execute mode (will modify files)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Dormancy threshold days for cheatsheet (default: 30)",
    )
    parser.add_argument(
        "--retire-days",
        type=int,
        default=90,
        help="Days threshold for retirement trigger (b) (default: 90)",
    )
    parser.add_argument(
        "--no-lifecycle",
        action="store_true",
        default=False,
        help="Skip lifecycle_report.py",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(AUDIT_REPORT),
        help="Output path for audit summary",
    )
    args = parser.parse_args(argv)

    exec_mode = args.execute

    print("=" * 60)
    print("GAF Governance Audit")
    print(f"Mode: {'EXECUTE' if exec_mode else 'DRY-RUN'}")
    print("=" * 60)
    print()

    results = []

    print("[1/3] Running cleanup_cheatsheet.py...")
    r = run_cleanup_cheatsheet(exec_mode=exec_mode, days=args.days)
    results.append(r)
    print(r['stdout'])
    if r['exit_code'] != 0:
        print(f"  ⚠️  Exit code: {r['exit_code']}")
    print()

    print("[2/3] Running retire_rules.py...")
    r = run_retire_rules(exec_mode=exec_mode, days=args.retire_days)
    results.append(r)
    print(r['stdout'])
    if r['exit_code'] != 0:
        print(f"  ⚠️  Exit code: {r['exit_code']}")
    print()

    if not args.no_lifecycle:
        print("[3/3] Running lifecycle_report.py...")
        r = run_lifecycle_report(write=True)
        results.append(r)
        if r['stdout']:
            print(r['stdout'][:500])
            if len(r['stdout']) > 500:
                print("  ... (truncated)")
        if r['exit_code'] != 0:
            print(f"  ⚠️  Exit code: {r['exit_code']}")
        print()
    else:
        print("[3/3] Skipped lifecycle_report.py (--no-lifecycle)")
        print()

    print("=" * 60)
    print("Generating audit summary...")

    summary = generate_audit_summary(results, exec_mode)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary, encoding="utf-8")

    print(f"Audit summary written to: {output_path}")
    print()

    pass_count = sum(1 for r in results if r['exit_code'] == 0)
    fail_count = len(results) - pass_count

    print(f"Results: {pass_count}/{len(results)} scripts passed")
    if fail_count > 0:
        print(f"⚠️  {fail_count} script(s) had non-zero exit codes")
    else:
        print("✅ All scripts completed successfully")

    if not exec_mode:
        print()
        print("💡 Run with --execute to apply changes:")
        print("   python scripts/governance/audit_governance.py --execute")

    return 0


if __name__ == "__main__":
    sys.exit(main())
