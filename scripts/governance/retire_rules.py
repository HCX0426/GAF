#!/usr/bin/env python3

from pathlib import Path
import re
import datetime
import argparse
import os
import sys

FAILURE_MODES_PATH = Path(".ai-memory/meta/failure-modes.md")
REPO_ROOT = Path(__file__).resolve().parents[2]

RETIRE_DORMANT_DAYS = 90

ACTIVE_TABLE_RE = re.compile(
    r'^\|\s*(N\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|$'
)
DORMANT_TABLE_RE = re.compile(
    r'^\|\s*(N[\d/]+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$'
)
RETIRED_TABLE_RE = re.compile(
    r'^\|\s*(N\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$'
)

N_ID_RE = re.compile(r'N(\d+)')

STOPWORDS = {
    '的', '了', '在', '是', '和', '与', '或', '不', '也', '都', '就', '要',
    '必', '须', '应', '该', '可', '能', '会', '将', '把', '被', '让', '使',
    '对', '向', '从', '到', '为', '以', '及', '等', '中', '内', '外', '上',
    '下', '前', '后', '间', '时', '里', '上', '但', '而', '且', '或', '如',
    '禁', '禁止', '需', '需要', '应该', '必须', '不得', '不准', '务必',
    '避免', '防止', '不要', '不能', '确保', '保证', '正确', '错误',
    '用', '使用', '通过', '进行', '执行', '完成', '实现', '处理',
    '检查', '验证', '确认', '评估', '分析', '识别',
}

KEYWORD_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)')


def parse_active_entries(text):
    """Parse all Active N## entries from the failure-modes table."""
    entries = []
    in_active_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('## Active N##'):
            in_active_section = True
            continue
        if stripped.startswith('## ') and in_active_section:
            break
        if not in_active_section:
            continue
        m = ACTIVE_TABLE_RE.match(stripped)
        if m:
            n_id = m.group(1)
            topic = m.group(2).strip()
            constraint = m.group(3).strip()
            lesson_link = m.group(4).strip()
            trigger_count = int(m.group(5))
            last_triggered = m.group(6).strip()
            entries.append({
                'n_id': n_id,
                'n_num': int(n_id[1:]),
                'topic': topic,
                'constraint': constraint,
                'lesson_link': lesson_link,
                'trigger_count': trigger_count,
                'last_triggered': last_triggered,
            })
    return entries


def parse_dormant_entries(text):
    """Parse Dormant N## entries."""
    entries = []
    in_dormant_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('## Dormant N##'):
            in_dormant_section = True
            continue
        if stripped.startswith('## ') and in_dormant_section:
            break
        if not in_dormant_section:
            continue
        m = DORMANT_TABLE_RE.match(stripped)
        if m:
            n_ids = m.group(1)
            topic = m.group(2).strip()
            family = m.group(3).strip()
            yn_matrix = m.group(4).strip()
            entries.append({
                'n_ids': n_ids,
                'topic': topic,
                'family': family,
                'yn_matrix': yn_matrix,
            })
    return entries


def parse_retired_entries(text):
    """Parse Retired N## entries."""
    entries = []
    in_retired_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('## Retired N##'):
            in_retired_section = True
            continue
        if stripped.startswith('## ') and in_retired_section:
            break
        if not in_retired_section:
            continue
        m = RETIRED_TABLE_RE.match(stripped)
        if m:
            n_id = m.group(1)
            topic = m.group(2).strip()
            deposition_location = m.group(3).strip()
            reason = m.group(4).strip()
            entries.append({
                'n_id': n_id,
                'topic': topic,
                'deposition_location': deposition_location,
                'reason': reason,
            })
    return entries


def check_trigger_a(entry):
    """trigger_count=0 — never triggered."""
    return entry['trigger_count'] == 0


def check_trigger_b(entry, now):
    """last_triggered > 90 days ago."""
    lt = entry['last_triggered']
    if lt == '-' or not lt:
        return False
    try:
        last_date = datetime.date.fromisoformat(lt)
        return (now - last_date).days > RETIRE_DORMANT_DAYS
    except ValueError:
        return False


def check_trigger_c(entry, all_entries):
    """Rule already covered by a newer N##."""
    n_num = entry['n_num']
    topic = entry['topic']
    constraint = entry['constraint']

    n_ref_pattern = re.compile(r'N(\d+)')
    current_nums_in_entry = set(int(x) for x in n_ref_pattern.findall(topic + ' ' + constraint))
    current_nums_in_entry.add(n_num)

    for other in all_entries:
        if other['n_num'] <= n_num:
            continue

        other_nums = set(int(x) for x in n_ref_pattern.findall(other['topic'] + ' ' + other['constraint']))

        if n_num in other_nums:
            return True, other['n_id']

        other_topic = other['topic']
        topic_words = [w for w in topic.split() if len(w) >= 2]
        other_topic_words = [w for w in other_topic.split() if len(w) >= 2]
        common = set(topic_words) & set(other_topic_words)

        if len(common) >= 2:
            return True, other['n_id']

    return False, None


def extract_keywords(constraint_text):
    """Extract searchable code-level keywords from constraint text."""
    keywords = set()

    for match in KEYWORD_RE.finditer(constraint_text):
        kw = match.group(1).lower()
        if len(kw) >= 3 and kw not in STOPWORDS:
            if any(c.isalpha() for c in kw):
                keywords.add(kw)

    return list(keywords)[:5]


def check_trigger_d(entry, codebase_root):
    """Code pattern no longer exists — grep for distinctive code patterns, 0 hits."""
    constraint = entry['constraint']
    keywords = extract_keywords(constraint)

    if not keywords:
        return False, 0

    code_suffixes = {
        '.py', '.ts', '.tsx', '.js', '.jsx', '.ps1', '.sh', '.bash',
        '.cs', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.php',
        '.rb', '.sql', '.html', '.css', '.scss', '.vue', '.jsx',
        '.tsx', '.md', '.yaml', '.yml', '.json', '.xml', '.cfg', '.ini',
    }

    exclude_dirs = {
        '.git', '__pycache__', 'node_modules', '.venv', 'venv',
        'env', '.env', 'dist', 'build', '.cache', 'snapshots',
        '__MACOSX', '.idea', '.vscode',
    }

    hits = 0
    files_checked = 0
    max_files = 500

    base_root = str(codebase_root)

    for root, dirs, files in os.walk(base_root):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for fname in files:
            fpath = os.path.join(root, fname)
            _, ext = os.path.splitext(fname)
            if ext not in code_suffixes:
                continue
            try:
                fsize = os.path.getsize(fpath)
                if fsize > 2 * 1024 * 1024:
                    continue
            except OSError:
                continue

            files_checked += 1
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content_lower = f.read().lower()
                    for kw in keywords:
                        kw_lower = kw.lower()
                        if len(kw_lower) < 3:
                            continue
                        if kw_lower in content_lower:
                            hits += 1
                            break
            except (OSError, UnicodeDecodeError):
                continue

            if files_checked >= max_files:
                break
        if files_checked >= max_files:
            break

    no_hits = (hits == 0) and (files_checked >= 30)
    return no_hits, hits


def evaluate_retirement(entry, all_active_entries, now, codebase_root):
    """Evaluate all 4 retirement triggers for an entry."""
    reasons = []

    if check_trigger_a(entry):
        reasons.append(('a', f"trigger_count=0 (never triggered)"))

    if check_trigger_b(entry, now):
        age = (now - datetime.date.fromisoformat(entry['last_triggered'])).days
        reasons.append(('b', f"last_triggered={entry['last_triggered']} ({age}d > {RETIRE_DORMANT_DAYS}d)"))

    covered, covered_by = check_trigger_c(entry, all_active_entries)
    if covered:
        reasons.append(('c', f"covered by newer {covered_by}"))

    no_pattern, hits = check_trigger_d(entry, codebase_root)
    if no_pattern:
        reasons.append(('d', f"code pattern not found in codebase (0/{hits} hits)"))

    return reasons


def move_to_dormant(text, n_id, entry_data):
    """Move an eligible entry from Active to Dormant section."""
    lines = text.splitlines()

    active_start = None
    active_end = None
    dormant_start = None
    dormant_end = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('## Active N##'):
            active_start = i
        elif stripped.startswith('## ') and active_start is not None and active_end is None:
            active_end = i
        if stripped.startswith('## Dormant N##'):
            dormant_start = i
        elif stripped.startswith('## ') and dormant_start is not None and dormant_end is None:
            dormant_end = i

    if active_end is None:
        active_end = len(lines)
    if dormant_end is None:
        dormant_end = len(lines)

    target_line_idx = None
    for i in range(active_start or 0, active_end):
        if f'| {n_id} |' in lines[i]:
            target_line_idx = i
            break

    if target_line_idx is None:
        return text

    target_line = lines.pop(target_line_idx)

    family_nums = N_ID_RE.findall(n_id)
    if family_nums:
        family_id = f"N{family_nums[0]}"
    else:
        family_id = n_id

    dormant_entry = f"| {n_id} | {entry_data['topic']} | {family_id} (retired) | _(moved from Active {n_id})_ |"

    insert_pos = dormant_start or len(lines)
    for i in range(dormant_start or 0, dormant_end or len(lines)):
        if '| N' in lines[i]:
            insert_pos = i
            break
    else:
        insert_pos = dormant_start or len(lines)

    lines.insert(insert_pos, dormant_entry)

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Evaluate N## rules for retirement eligibility"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report without modifying (default)",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Move eligible entries to Dormant section",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=RETIRE_DORMANT_DAYS,
        help=f"Days threshold for trigger (b) (default: {RETIRE_DORMANT_DAYS})",
    )
    parser.add_argument(
        "--codebase",
        type=str,
        default=str(REPO_ROOT),
        help="Codebase root directory for pattern grep",
    )
    args = parser.parse_args(argv)

    if not FAILURE_MODES_PATH.exists():
        print("[OK] failure-modes: file not found (skipping)")
        return 0

    text = FAILURE_MODES_PATH.read_text(encoding="utf-8")
    now = datetime.datetime.now().date()

    active_entries = parse_active_entries(text)
    dormant_entries = parse_dormant_entries(text)
    retired_entries = parse_retired_entries(text)

    print(f"=== N## Rule Retirement Evaluation ===")
    print(f"Active:   {len(active_entries)} entries")
    print(f"Dormant:  {len(dormant_entries)} entries")
    print(f"Retired:  {len(retired_entries)} entries")
    print()

    eligible = []
    not_eligible = []

    for entry in active_entries:
        reasons = evaluate_retirement(
            entry, active_entries, now, Path(args.codebase)
        )
        if reasons:
            eligible.append((entry, reasons))
        else:
            not_eligible.append(entry['n_id'])

    if eligible:
        print(f"Eligible for retirement: {len(eligible)} N##")
        print()
        for entry, reasons in eligible:
            n_id = entry['n_id']
            reason_str = "; ".join(f"({code}) {desc}" for code, desc in reasons)
            print(f"  {n_id}: {entry['topic'][:60]}")
            print(f"    Triggers: {reason_str}")
            print(f"    trigger_count={entry['trigger_count']}, last_triggered={entry['last_triggered']}")
            print()

        if args.execute:
            for entry, reasons in eligible:
                text = move_to_dormant(text, entry['n_id'], entry)
            FAILURE_MODES_PATH.write_text(text, encoding="utf-8")
            print(f"[EXECUTE] Moved {len(eligible)} N## to Dormant section")
        else:
            print(f"[DRY-RUN] Would move {len(eligible)} N## to Dormant section")
            print(f"  Run with --execute to actually modify the file")
    else:
        print("No N## eligible for retirement.")

    print(f"\nNot eligible: {len(not_eligible)} N## ({', '.join(not_eligible[:10])}{'...' if len(not_eligible) > 10 else ''})")
    print(f"\nSummary: {len(eligible)} eligible / {len(active_entries)} total active")

    return 0


if __name__ == "__main__":
    sys.exit(main())