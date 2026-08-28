"""counter-sync domain (s38 split from sync_ai_memory.py, TD-365).

Frontmatter counter fields synced from actual counts:
- lessons/README.md `lessons_count` (TD-159)
- yn-matrices.md `auto_updated` (TD-164)
- project_rules.md archived count annotation (TD-171)
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path


def _sync_lessons_readme_count(root: Path, *, dry_run: bool = False) -> bool:
    """TD-159 — sync lessons/README.md frontmatter `lessons_count` field.

    Counts active lessons (`lessons/*.md` excluding README.md itself) and
    updates README.md frontmatter field `lessons_count`. Adds the field if
    missing. Returns True if file was modified.
    """
    readme_path = root / ".ai-memory" / "lessons" / "README.md"
    if not readme_path.is_file():
        return False
    lessons_dir = root / ".ai-memory" / "lessons"
    count = sum(1 for f in lessons_dir.glob("*.md") if f.name != "README.md")
    text = readme_path.read_text(encoding="utf-8")
    # Match frontmatter block
    fm_match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not fm_match:
        return False
    fm = fm_match.group(1)
    # Check whether the field already exists (any value).
    field_exists = re.search(r"^lessons_count:", fm, re.MULTILINE) is not None
    if field_exists:
        # Replace existing line (idempotent: no-op when value already correct).
        new_fm = re.sub(
            r"^lessons_count:.*$",
            f"lessons_count: {count}",
            fm,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        # Field missing — append after `priority:` line (last required field).
        new_fm = re.sub(
            r"(^priority:.*$)",
            rf"\1\nlessons_count: {count}",
            fm,
            count=1,
            flags=re.MULTILINE,
        )
    if new_fm == fm:
        return False
    new_text = text.replace(fm, new_fm, 1)
    if new_text == text:
        return False
    if not dry_run:
        readme_path.write_text(new_text, encoding="utf-8")
    return True


def _sync_yn_matrices_auto_updated(root: Path, *, dry_run: bool = False) -> bool:
    """TD-164 — sync yn-matrices.md frontmatter `auto_updated` field to today.

    Returns True if file was modified.
    """
    ynm_path = root / ".ai-memory" / "meta" / "yn-matrices.md"
    if not ynm_path.is_file():
        return False
    today = _dt.date.today().isoformat()
    text = ynm_path.read_text(encoding="utf-8")
    fm_match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not fm_match:
        return False
    fm = fm_match.group(1)
    new_fm = re.sub(
        r"^auto_updated:.*$",
        f"auto_updated: {today}",
        fm,
        count=1,
        flags=re.MULTILINE,
    )
    if new_fm == fm:
        return False
    new_text = text.replace(fm, new_fm, 1)
    if new_text == text:
        return False
    if not dry_run:
        ynm_path.write_text(new_text, encoding="utf-8")
    return True


def _sync_archived_count_in_rules(root: Path, *, dry_run: bool = False) -> bool:
    """TD-171 — sync project_rules.md §6.4 "约 N 条" archived count.

    Counts N## entries in `.ai-memory/meta/archived-lessons.md` table rows
    (lines matching `^| N` pattern — covers both dormant + archived tables)
    and updates project_rules.md §6.4 "约 N 条" annotation. Returns True
    if file was modified.
    """
    archived_path = root / ".ai-memory" / "meta" / "archived-lessons.md"
    rules_path = root / ".skills" / "rules" / "project_rules.md"
    if not archived_path.is_file() or not rules_path.is_file():
        return False
    archived_text = archived_path.read_text(encoding="utf-8")
    # Count N## table rows (each `| N...` row is one archived/dormant entry)
    count = len(re.findall(r"^\|\s+N[\dA-Za-z\-]+\s+\|", archived_text, re.MULTILINE))
    rules_text = rules_path.read_text(encoding="utf-8")
    # Match "约 N 条" pattern in §6.4 archived-lessons.md annotation
    new_text = re.sub(
        r"(archived-lessons\.md` \(已闭环 OR 罕见触发, 约 )\d+( 条\))",
        rf"\g<1>{count}\g<2>",
        rules_text,
        count=1,
    )
    if new_text == rules_text:
        return False
    if not dry_run:
        rules_path.write_text(new_text, encoding="utf-8")
    return True


def _sync_rules_counters(root: Path, *, dry_run: bool = False) -> bool:
    """TD-392 — sync lessons/README.md frontmatter active_n_count /
    retired_n_count / next_n_id counters.

    - active_n_count: N## table rows in failure-modes.md between
      "## Active N## 索引表" and "### Archived-Early N## 索引".
    - retired_n_count: N## table rows in failure-modes.md between
      "## Retired N## 索引" and "## Dormant N## 索引".
    - next_n_id: max(n_id in lessons/<*.md> frontmatter) + 1.

    Idempotent: returns False when all counters already correct. This closes
    TD-392 (之前 active/next 仅靠手动维护导致撞号/虚高).
    """
    readme_path = root / ".ai-memory" / "lessons" / "README.md"
    fm_path = root / ".ai-memory" / "meta" / "failure-modes.md"
    if not readme_path.is_file() or not fm_path.is_file():
        return False

    row_re = re.compile(r"^\|\s*N\d+(?:\s*/\s*N\d+)*\s*\|")
    active = retired = 0
    section = None
    for ln in fm_path.read_text(encoding="utf-8").splitlines():
        if ln.startswith("## Active N## 索引表"):
            section = "active"
            continue
        if ln.startswith("## Retired N## 索引"):
            section = "retired"
            continue
        if ln.startswith("## Dormant N## 索引") or ln.startswith("### "):
            if section in ("active", "retired"):
                section = None
            continue
        if section == "active" and row_re.match(ln):
            active += 1
        elif section == "retired" and row_re.match(ln):
            retired += 1

    lessons_dir = root / ".ai-memory" / "lessons"
    max_n = 0
    for f in lessons_dir.glob("*.md"):
        if f.name == "README.md":
            continue
        text = f.read_text(encoding="utf-8")
        fm_m = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
        body = fm_m.group(1) if fm_m else text[:400]
        m = re.search(r"^n_id:\s*N?(\d+)", body, re.MULTILINE)
        if m:
            max_n = max(max_n, int(m.group(1)))
    next_id = max_n + 1

    updates = {
        "active_n_count": str(active),
        "retired_n_count": str(retired),
        "next_n_id": str(next_id),
    }
    text = readme_path.read_text(encoding="utf-8")
    fm_match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not fm_match:
        return False
    fm = fm_match.group(1)
    new_fm = fm
    for field, val in updates.items():
        if re.search(rf"^{field}:", new_fm, re.MULTILINE):
            new_fm = re.sub(
                rf"^{field}:.*$",
                f"{field}: {val}",
                new_fm,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            new_fm = re.sub(
                r"(^priority:.*$)",
                rf"\1\n{field}: {val}",
                new_fm,
                count=1,
                flags=re.MULTILINE,
            )
    if new_fm == fm:
        return False
    new_text = text.replace(fm, new_fm, 1)
    if new_text == text:
        return False
    if not dry_run:
        readme_path.write_text(new_text, encoding="utf-8")
    return True
