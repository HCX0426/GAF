"""skill_sync.timestamps — --update-timestamps command (s39 split, TD-365 6/9)."""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from . import constants as _constants  # module-attr access so tests can monkeypatch (N202 18)
from .io_utils import (
    _read_text,
    _write_text,
    parse_frontmatter_updated,
    update_frontmatter_updated,
)

# =============================================================================
# 🆕 TD-323 (spec-85, 2026-07-21): --update-timestamps command
# =============================================================================

def cmd_update_timestamps(args: argparse.Namespace) -> int:
    """🆕 TD-323: sync SKILL.md frontmatter ``updated`` field with today's date.

    For each skill in ``TIMESTAMP_SKILLS``:
    1. Get the current ``updated:`` field from frontmatter.
    2. If it differs from today (or field is missing) → update frontmatter.
    3. If it already equals today → skip.

    s32 fix: write **today** instead of the git log date. The old behaviour
    (writing ``git log -1`` date) was a self-referential loop: after syncing,
    the user commits, the commit advances the git log date past the value we
    wrote, and the next --check reports stale again — forever. Writing today
    converges because the sync commit itself carries today's date.

    Returns 0 on success (even if some skills were skipped due to missing files
    or git errors — those are reported as warnings, not failures).
    """
    root = Path(args.root).resolve()
    skills_dir = root / ".skills" / "skills"
    today = datetime.date.today().isoformat()

    updated_count = 0
    skipped_count = 0
    unchanged_count = 0

    for skill in _constants.TIMESTAMP_SKILLS:
        skill_md = skills_dir / skill / "SKILL.md"
        if not skill_md.exists():
            print(f"⚠️  {skill}/SKILL.md 不存在, 跳过")
            skipped_count += 1
            continue
        text = _read_text(skill_md)
        if not text:
            print(f"⚠️  {skill}/SKILL.md 读取失败, 跳过")
            skipped_count += 1
            continue
        current_updated = parse_frontmatter_updated(text)
        if current_updated == today:
            print(f"✅ {skill}: updated={today} (已一致)")
            unchanged_count += 1
            continue
        new_text = update_frontmatter_updated(text, today)
        if new_text == text:
            print(f"⚠️  {skill}: frontmatter 缺失或无法插入 updated 字段, 跳过 (需手动补)")
            skipped_count += 1
            continue
        _write_text(skill_md, new_text)
        print(f"🔄 {skill}: updated {current_updated or '(missing)'} → {today} (today)")
        updated_count += 1

    total = len(_constants.TIMESTAMP_SKILLS)
    print()
    print(
        f"✅ 时间戳同步完成: {updated_count} 更新 / {unchanged_count} 已一致 / "
        f"{skipped_count} 跳过 / {total} 总计"
    )
    if updated_count > 0:
        print()
        print("📝 提示: 更新后的 SKILL.md 需要 commit 才能让 git log 反映今天 (s32):")
        print("   git add .skills/skills/*/SKILL.md && git commit -m '...'")
    return 0

