#!/usr/bin/env python3

from pathlib import Path
import re
import datetime
import argparse
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
CHEATSHEET_PATH = REPO_ROOT / ".ai-memory" / "ai-cheatsheet.md"
FAILURE_MODES_PATH = REPO_ROOT / ".ai-memory" / "meta" / "failure-modes.md"
LESSONS_DIR = REPO_ROOT / ".ai-memory" / "lessons"
ARCHIVED_LESSONS_DIR = LESSONS_DIR / "archived-early"
SESSION_TRACES_DIR = REPO_ROOT / ".ai-memory" / "session-traces"
SCAN_PATTERNS_PATH = REPO_ROOT / "scripts" / "governance" / "scan_hardcoded_patterns.py"
GOVERNANCE_DIR = REPO_ROOT / ".ai-memory" / "governance"
REPORT_FILE = GOVERNANCE_DIR / "lifecycle-report.md"

CHEATSHEET_DORMANCY_DAYS = 30
N_DORMANT_DAYS = 90

META_RE = re.compile(
    r'<!--\s*meta:\s*\{last_used:\s*"([^"]+)",\s*trigger_count:\s*(\d+),\s*expire_days:\s*(\d+)\}\s*-->'
)
ENTRY_RE = re.compile(r'^\s*[-*]\s+')
DORMANT_RE = re.compile(r'<!--\s*DORMANT:\s*(\d{4}-\d{2}-\d{2})\s*-->')

ACTIVE_TABLE_RE = re.compile(
    r'^\|\s*(N\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|$'
)

SCAN_PATTERN_RE = re.compile(
    r'\{\s*"pattern":\s*r?"([^"]+)",\s*"n_id":\s*"([^"]+)",\s*"description":\s*"([^"]*)",\s*"last_hit":\s*([^,]+),\s*"hit_count":\s*(\d+)\s*\}'
)


def analyze_cheatsheet():
    """Analyze cheatsheet entries for active/dormant status."""
    if not CHEATSHEET_PATH.exists():
        return {'total': 0, 'active': 0, 'dormant': 0, 'details': []}

    text = CHEATSHEET_PATH.read_text(encoding="utf-8")
    now = datetime.datetime.now().date()

    total = 0
    active = 0
    dormant = 0
    details = []

    for line in text.splitlines():
        if not ENTRY_RE.match(line):
            continue

        total += 1
        m = META_RE.search(line)
        if not m:
            continue

        last_used_str = m.group(1)
        try:
            last_used = datetime.date.fromisoformat(last_used_str)
        except ValueError:
            continue

        age = (now - last_used).days
        is_dormant = bool(DORMANT_RE.search(line)) or age > CHEATSHEET_DORMANCY_DAYS

        if is_dormant:
            dormant += 1
        else:
            active += 1

        title = line.strip().lstrip("-* ").strip()[:60]
        details.append({
            'title': title,
            'age_days': age,
            'dormant': is_dormant,
        })

    return {
        'total': total,
        'active': active,
        'dormant': dormant,
        'details': details[:5],
    }


def analyze_n_rules():
    """Analyze N## rules from failure-modes.md."""
    if not FAILURE_MODES_PATH.exists():
        return {'active': 0, 'dormant': 0, 'retired': 0, 'total': 0}

    text = FAILURE_MODES_PATH.read_text(encoding="utf-8")
    now = datetime.datetime.now().date()

    active = 0
    dormant = 0
    retired = 0
    active_details = []

    in_active = False
    in_dormant = False
    in_retired = False

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith('## Active N##'):
            in_active = True
            in_dormant = False
            in_retired = False
            continue
        if stripped.startswith('## Dormant N##'):
            in_active = False
            in_dormant = True
            in_retired = False
            continue
        if stripped.startswith('## Retired N##'):
            in_active = False
            in_dormant = False
            in_retired = True
            continue
        if stripped.startswith('## ') or stripped.startswith('### '):
            if in_active or in_dormant or in_retired:
                in_active = False
                in_dormant = False
                in_retired = False

        if in_active:
            m = ACTIVE_TABLE_RE.match(stripped)
            if m:
                n_id = m.group(1)
                topic = m.group(2).strip()
                tc = int(m.group(5))
                lt = m.group(6).strip()
                active += 1

                is_inactive = False
                if tc == 0:
                    is_inactive = True
                elif lt != '-':
                    try:
                        lt_date = datetime.date.fromisoformat(lt)
                        if (now - lt_date).days > N_DORMANT_DAYS:
                            is_inactive = True
                    except ValueError:
                        pass

                active_details.append({
                    'n_id': n_id,
                    'topic': topic[:50],
                    'inactive': is_inactive,
                })
                continue
            
            # Try 5-column format (trigger_count embedded)
            m5 = re.match(r'^\|\s*(N\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$', stripped)
            if m5:
                n_id = m5.group(1)
                topic = m5.group(2).strip()
                tc_col = m5.group(3)
                tc_m = re.search(r'trigger_count=(\d+)', tc_col)
                tc = int(tc_m.group(1)) if tc_m else 0
                lt = m5.group(5).strip()
                active += 1

                is_inactive = False
                if tc == 0:
                    is_inactive = True
                elif lt != '-':
                    try:
                        lt_date = datetime.date.fromisoformat(lt)
                        if (now - lt_date).days > N_DORMANT_DAYS:
                            is_inactive = True
                    except ValueError:
                        pass

                active_details.append({
                    'n_id': n_id,
                    'topic': topic[:50],
                    'inactive': is_inactive,
                })

        if in_dormant:
            if stripped.startswith('| N'):
                dormant += 1

        if in_retired:
            if stripped.startswith('| N'):
                retired += 1

    return {
        'active': active,
        'dormant': dormant,
        'retired': retired,
        'total': active + dormant + retired,
        'active_inactive': sum(1 for d in active_details if d['inactive']),
        'active_triggered': sum(1 for d in active_details if not d['inactive']),
        'active_details': active_details[:5],
    }


def analyze_lessons():
    """Analyze lesson files for active/archived status."""
    active = 0
    archived = 0
    total = 0
    active_triggered = 0

    # Read failure-modes once for all lookups
    fm_text = FAILURE_MODES_PATH.read_text(encoding="utf-8") if FAILURE_MODES_PATH.exists() else ""
    
    # Build trigger_count lookup from Active N## section
    tc_lookup = {}
    in_active = False
    for line in fm_text.splitlines():
        s = line.strip()
        if s.startswith('## Active N##'):
            in_active = True
            continue
        if s.startswith('## ') and in_active:
            in_active = False
        if in_active:
            # Try 6-column format first
            m6 = ACTIVE_TABLE_RE.match(s)
            if m6:
                tc_lookup[m6.group(1)] = int(m6.group(5))
                continue
            # Try 5-column format (trigger_count embedded in col 3)
            m5 = re.match(r'^\|\s*(N\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$', s)
            if m5:
                tc_col = m5.group(3)
                tc_m = re.search(r'trigger_count=(\d+)', tc_col)
                if tc_m:
                    tc_lookup[m5.group(1)] = int(tc_m.group(1))

    if LESSONS_DIR.exists():
        for f in LESSONS_DIR.glob("*.md"):
            if f.is_file() and f.name not in ("README.md",):
                active += 1
                total += 1
                stem = f.stem
                m = re.match(r'(N\d+)', stem)
                if m:
                    n_id = m.group(1)
                    tc = tc_lookup.get(n_id, 0)
                    if tc > 0:
                        active_triggered += 1

    if ARCHIVED_LESSONS_DIR.exists():
        for f in ARCHIVED_LESSONS_DIR.glob("*.md"):
            if f.is_file() and f.name not in ("README.md",):
                archived += 1
                total += 1

    return {
        'active': active,
        'archived': archived,
        'total': total,
        'active_triggered': active_triggered,
    }


def analyze_session_traces():
    """Analyze session-traces directory."""
    if not SESSION_TRACES_DIR.exists():
        return {'count': 0, 'retained': 0, 'compressed': 0, 'deleted': 0, 'retention': 'N/A'}

    json_files = sorted(
        [f for f in SESSION_TRACES_DIR.iterdir() if f.is_file() and f.suffix == '.json'],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    total = len(json_files)
    retained = min(total, 20)
    compressed = max(0, min(total - 20, 80))
    old_deleted = max(0, total - 100)

    return {
        'count': total,
        'retained': retained,
        'compressed': compressed,
        'deleted': old_deleted,
        'retention': 'healthy' if total <= 100 else 'needs cleanup',
    }


def analyze_scan_patterns():
    """Analyze scan patterns from scan_hardcoded_patterns.py."""
    if not SCAN_PATTERNS_PATH.exists():
        return {'total': 0, 'active': 0, 'dormant': 0}

    content = SCAN_PATTERNS_PATH.read_text(encoding="utf-8")
    now = datetime.datetime.now()

    patterns = []
    in_list = False
    bracket_depth = 0
    current_pattern = None
    current_n_id = None
    current_desc = None
    current_last_hit = None
    current_hit_count = None
    collecting = False

    for line in content.splitlines():
        stripped = line.strip()
        if 'SCAN_PATTERNS:' in stripped or 'SCAN_PATTERNS = [' in stripped:
            in_list = True
            continue
        if in_list and stripped == ']':
            break

        if not in_list:
            continue

        if '"pattern":' in stripped:
            if collecting and current_pattern is not None:
                patterns.append({
                    'pattern': current_pattern,
                    'n_id': current_n_id,
                    'description': current_desc,
                    'last_hit': current_last_hit,
                    'hit_count': current_hit_count,
                })
            collecting = True
            current_pattern = None
            current_n_id = None
            current_desc = None
            current_last_hit = None
            current_hit_count = None

            m = re.search(r'"pattern":\s*r?"([^"]+)"', stripped)
            if m:
                current_pattern = m.group(1)

        if collecting:
            m_n = re.search(r'"n_id":\s*"([^"]+)"', stripped)
            if m_n:
                current_n_id = m_n.group(1)

            m_d = re.search(r'"description":\s*"([^"]*)"', stripped)
            if m_d:
                current_desc = m_d.group(1)

            m_lh = re.search(r'"last_hit":\s*([^,}\]]+)', stripped)
            if m_lh:
                val = m_lh.group(1).strip()
                if val == 'None':
                    current_last_hit = None
                else:
                    current_last_hit = val

            m_hc = re.search(r'"hit_count":\s*(\d+)', stripped)
            if m_hc:
                current_hit_count = int(m_hc.group(1))

    if collecting and current_pattern is not None:
        patterns.append({
            'pattern': current_pattern,
            'n_id': current_n_id,
            'description': current_desc,
            'last_hit': current_last_hit,
            'hit_count': current_hit_count,
        })

    total = len(patterns)
    active = 0
    dormant = 0

    for p in patterns:
        if p['hit_count'] == 0 and p['last_hit'] is None:
            dormant += 1
        else:
            active += 1

    return {
        'total': total,
        'active': active,
        'dormant': dormant,
        'patterns': patterns,
    }


def compute_health_score(cheatsheet, n_rules, lessons, traces, scan_patterns):
    """Compute overall health score A/B/C/D.

    Scoring:
    - Active entities with trigger_count > 0: 1.0 (fully active)
    - Active entities with trigger_count = 0: 0.0 (zombie, created but never used)
    - Dormant/Archived: excluded from denominator (intentionally preserved, not a loss)
    - Retired: excluded (intentional end-state)
    
    Score = active_with_triggers / (active_with_triggers + active_zombies) * 100
    This measures the quality of active governance, not the quantity of preserved items.
    """
    scores = []

    if cheatsheet['total'] > 0:
        cs_active = cheatsheet['active']
        cs_dormant = cheatsheet.get('dormant', 0)
        # Only score active items; dormant excluded (intentional)
        cs_score = cs_active / (cs_active + cs_dormant) * 100 if (cs_active + cs_dormant) > 0 else 0
        scores.append(cs_score)

    if n_rules['active'] + n_rules['dormant'] > 0:
        # Active items that have been triggered are healthy
        nr_active_healthy = n_rules.get('active_triggered', n_rules['active'])
        nr_active_zombie = n_rules['active'] - nr_active_healthy
        nr_total_scored = nr_active_healthy + nr_active_zombie
        nr_score = nr_active_healthy / nr_total_scored * 100 if nr_total_scored > 0 else 100
        scores.append(nr_score)

    if lessons['total'] > 0:
        ls_active = lessons['active']
        ls_archived = lessons.get('archived', 0)
        # Active lessons: those with trigger_count > 0 are healthy
        ls_active_healthy = lessons.get('active_triggered', ls_active)
        ls_active_zombie = ls_active - ls_active_healthy
        ls_total_scored = ls_active_healthy + ls_active_zombie
        ls_score = ls_active_healthy / ls_total_scored * 100 if ls_total_scored > 0 else 100
        scores.append(ls_score)

    if scan_patterns['total'] > 0:
        sp_score = scan_patterns['active'] / scan_patterns['total'] * 100
        scores.append(sp_score)

    if not scores:
        return 'A', 100.0

    avg = sum(scores) / len(scores)

    if avg > 80:
        grade = 'A'
    elif avg > 60:
        grade = 'B'
    elif avg > 40:
        grade = 'C'
    else:
        grade = 'D'

    return grade, round(avg, 1)


def generate_report(cheatsheet, n_rules, lessons, traces, scan_patterns, grade, score):
    """Generate markdown lifecycle report."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# GAF Governance Lifecycle Report",
        "",
        f"_Generated: {now}_",
        "",
        f"## Health Score: **{grade}** ({score}%)",
        "",
        "| Entity | Active | Dormant | Other | Total | Active Rate |",
        "|--------|--------|---------|-------|-------|-------------|",
    ]

    cs_total = cheatsheet['total'] or 1
    cs_rate = f"{cheatsheet['active'] / cs_total * 100:.0f}%"
    lines.append(
        f"| Cheatsheet entries | {cheatsheet['active']} | {cheatsheet['dormant']} | - | {cheatsheet['total']} | {cs_rate} |"
    )

    nr_total = n_rules['total'] or 1
    nr_active_rate = f"{n_rules['active'] / nr_total * 100:.0f}%"
    lines.append(
        f"| N## rules | {n_rules['active']} | {n_rules['dormant']} | {n_rules['retired']} (retired) | {n_rules['total']} | {nr_active_rate} |"
    )

    ls_total = lessons['total'] or 1
    ls_rate = f"{lessons['active'] / ls_total * 100:.0f}%"
    lines.append(
        f"| Lessons | {lessons['active']} | {lessons['archived']} (archived) | - | {lessons['total']} | {ls_rate} |"
    )

    sp_total = scan_patterns['total'] or 1
    sp_rate = f"{scan_patterns['active'] / sp_total * 100:.0f}%"
    lines.append(
        f"| Scan patterns | {scan_patterns['active']} | {scan_patterns['dormant']} | - | {scan_patterns['total']} | {sp_rate} |"
    )

    lines.append(
        f"| Session traces | {traces['retained']} (retained) | {traces['compressed']} (compressed) | {traces['deleted']} (deleted) | {traces['count']} | {traces['retention']} |"
    )

    lines.append("")
    lines.append("## Cheatsheet Details")
    lines.append("")
    if cheatsheet['details']:
        lines.append("| Entry | Age (days) | Status |")
        lines.append("|-------|-----------|--------|")
        for d in cheatsheet['details']:
            status = "DORMANT" if d['dormant'] else "active"
            lines.append(f"| {d['title']} | {d['age_days']} | {status} |")
        lines.append(f"| ... ({cheatsheet['total'] - len(cheatsheet['details'])} more) | | |")
    else:
        lines.append("_No cheatsheet entries with metadata_")

    lines.append("")
    lines.append("## N## Rules Details")
    lines.append("")
    if n_rules['active_details']:
        lines.append("| N## | Topic | Status |")
        lines.append("|-----|-------|--------|")
        for d in n_rules['active_details']:
            status = "INACTIVE (triggers retirement)" if d['inactive'] else "active"
            lines.append(f"| {d['n_id']} | {d['topic']} | {status} |")
        remaining = n_rules['active'] - len(n_rules['active_details'])
        if remaining > 0:
            lines.append(f"| ... ({remaining} more active) | | |")
    else:
        lines.append("_No active N## rules found_")

    lines.append("")
    lines.append("## Session Traces")
    lines.append("")
    lines.append(f"- Total trace files: {traces['count']}")
    lines.append(f"- Retained (newest 20): {traces['retained']}")
    lines.append(f"- Compressed (20-100): {traces['compressed']}")
    lines.append(f"- Deleted (>100): {traces['deleted']}")
    lines.append(f"- Retention status: {traces['retention']}")

    lines.append("")
    lines.append("## Scan Patterns")
    lines.append("")
    if scan_patterns['patterns']:
        lines.append("| Pattern | N## | Description | Hit Count | Status |")
        lines.append("|---------|-----|-------------|-----------|--------|")
        for p in scan_patterns['patterns']:
            status = "DORMANT" if p['hit_count'] == 0 else "active"
            lines.append(
                f"| `{p['pattern'][:30]}` | {p['n_id'] or '-'} | {p['description'] or '-'} | {p['hit_count']} | {status} |"
            )
    else:
        lines.append("_No scan patterns found_")

    lines.append("")
    lines.append("## Recommendations")
    lines.append("")

    recommendations = []

    if cheatsheet['dormant'] > 0:
        recommendations.append(
            f"- **Cheatsheet**: {cheatsheet['dormant']} dormant entries (>30 days unused). "
            f"Run `python scripts/governance/cleanup_cheatsheet.py --execute` to mark them."
        )

    if n_rules.get('active_inactive', 0) > 0:
        recommendations.append(
            f"- **N## Rules**: {n_rules['active_inactive']} active N## have trigger_count=0 or last_triggered>90d. "
            f"Run `python scripts/governance/retire_rules.py --execute` to evaluate retirement."
        )

    if scan_patterns['dormant'] > 0:
        recommendations.append(
            f"- **Scan Patterns**: {scan_patterns['dormant']} scan patterns have never matched. "
            f"Consider removing or updating them."
        )

    if not recommendations:
        recommendations.append("- All governance entities are healthy. No action required.")

    lines.extend(recommendations)
    lines.append("")

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate lifecycle health report for all governance entities"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(REPORT_FILE),
        help="Output path for the markdown report",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        default=False,
        help="Also print report to stdout",
    )
    args = parser.parse_args(argv)

    print("Analyzing governance entities...")

    cheatsheet = analyze_cheatsheet()
    print(f"  Cheatsheet: {cheatsheet['total']} entries ({cheatsheet['active']} active, {cheatsheet['dormant']} dormant)")

    n_rules = analyze_n_rules()
    print(f"  N## Rules: {n_rules['active']} active, {n_rules['dormant']} dormant, {n_rules['retired']} retired")

    lessons = analyze_lessons()
    print(f"  Lessons: {lessons['active']} active, {lessons['archived']} archived")

    traces = analyze_session_traces()
    print(f"  Session Traces: {traces['count']} files ({traces['retention']})")

    scan_patterns = analyze_scan_patterns()
    print(f"  Scan Patterns: {scan_patterns['total']} patterns ({scan_patterns['active']} active, {scan_patterns['dormant']} dormant)")

    grade, score = compute_health_score(cheatsheet, n_rules, lessons, traces, scan_patterns)
    print(f"\nHealth Score: {grade} ({score}%)")

    report = generate_report(cheatsheet, n_rules, lessons, traces, scan_patterns, grade, score)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {output_path}")

    if args.stdout:
        print("\n" + "=" * 60)
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())