"""promote_lessons.py — M0.M 提升闭环 (lessons → 4 目标) + N## 生命周期自动化

Scan .ai-memory/lessons/ and suggest promotions to 4 target files
based on `priority:` + cross-reference count. M0.M 闭环 (2026-06-15).
P2 (2026-07-16): Added --archive / --enforce-limits subcommands for
N## lifecycle automation (治本机制 — 见 docs/specs/legacy-trae/2026-07-16-ai-thinking-chain-slim.md).

Usage:
    python scripts/lessons/promote_lessons.py --dry-run    # 提议但不动文件
    python scripts/lessons/promote_lessons.py --apply      # AI 确认后实际写入
    python scripts/lessons/promote_lessons.py --stats      # 只打印统计
    python scripts/lessons/promote_lessons.py --archive --dry-run     # 提议归档 dormant N##
    python scripts/lessons/promote_lessons.py --archive --apply       # 实际归档 dormant N##
    python scripts/lessons/promote_lessons.py --enforce-limits --dry-run   # 提议超限归档
    python scripts/lessons/promote_lessons.py --enforce-limits --apply     # 实际超限归档

Promotion rules (M0.M spec.md §14.7 条款 10):
    - priority=high   + ≥ 2 cross-refs → auto-suggest
    - priority=medium + ≥ 3 cross-refs → auto-suggest
    - priority=low    → no auto-suggest (AI may trigger manually)

4 promotion targets:
    1. .skills/rules/project_rules.md       (硬规则层)
    2. .skills/skills/gaf-orchestrator/SKILL.md  (反思清单 / 流程)
    3. .ai-memory/summaries/architecture-mistakes.md  (架构教训)
    4. .ai-memory/meta/failure-modes.md   (失败模式)

Archive rules (P2 治本机制):
    - failure-modes.md N## 行含 "(dormant" 或 "(已合并到" 标记 → 立即归档到 archived-lessons.md
    - 活跃 N## 在 failure-modes.md / yn-matrices / SKILL.md / rules.md / lessons/README.md
      出现次数 ≤ 1 + lessons/ 文件 front matter date 超过 6 个月 → 归档
    - 物理 lessons/ 文件保留（编号永不复用，可解档）

Audit log: .gaf_promote.log (one line per --apply)
"""

from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

import _encoding_safe  # noqa: F401  (must be first; reconfigures stdout to UTF-8)
from frontmatter import parse_front_matter

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
AI_MEMORY = REPO_ROOT_DEFAULT / ".ai-memory"
LESSONS_DIR = AI_MEMORY / "lessons"
PROMOTE_LOG = REPO_ROOT_DEFAULT / ".gaf_promote.log"

# Minimum cross-reference count per priority level for auto-suggest.
PROMOTE_THRESHOLDS: dict[str, int] = {
    "high": 2,
    "medium": 3,
    # "low" is intentionally absent — no auto-suggest.
}

# 4 promotion targets. `marker` is a substring used to detect
# existing promotion entries (avoid duplicates on re-runs).
PROMOTE_TARGETS: dict[str, dict[str, str]] = {
    "rules": {
        "path": ".skills/rules/project_rules.md",
        "marker": "## 5. (M0.M 提升自 .ai-memory/lessons/)",
        "kind_label": "硬规则",
    },
    "skill": {
        "path": ".skills/skills/gaf-orchestrator/SKILL.md",
        "marker": "### §3.4 (M0.M 提升自 lessons/)",
        "kind_label": "反思清单",
    },
    "docs": {
        "path": ".ai-memory/summaries/architecture-mistakes.md",
        "marker": "## (M0.M 提升自 lessons/)",
        "kind_label": "架构教训",
    },
    "failure_modes": {
        "path": ".ai-memory/meta/failure-modes.md",
        "marker": "### (M0.M 提升自 lessons/)",
        "kind_label": "失败模式",
    },
    # 🆕 P1b (2026-07-16): L2 candidate target — 高频教训沉淀到 L2 硬加载文件
    # 不自动写入 (分类需 AI 判断), 只提议. AI 手动沉淀后设 l2_candidate=true.
    "handbook": {
        "path": ".ai-memory/meta/ai-operating-handbook.md",
        "marker": "### (M0.M 提升自 lessons/)",
        "kind_label": "L2 行为红线",
    },
}

# 🆕 P1b (2026-07-16): L2 candidate detection threshold
# priority=high + cross_refs >= L2_CANDIDATE_REFS + l2_candidate != true → 提议沉淀到 handbook Part 2
L2_CANDIDATE_REFS = 3

# Where to count cross-references. Skills reference lessons either
# by filename or by symptom keyword. We scan all 4 GAF skills + the
# two long-form docs for any of these.
REFERENCE_SCAN_PATHS: list[str] = [
    ".skills/rules/project_rules.md",
    ".skills/skills/gaf-orchestrator/SKILL.md",
    ".skills/skills/gaf-task-execution/SKILL.md",
    ".skills/skills/gaf-reflect-and-evolve/SKILL.md",
    ".skills/skills/gaf-knowledge-base/SKILL.md",
    ".ai-memory/summaries/architecture-mistakes.md",
    ".ai-memory/summaries/code-rules.md",
    ".ai-memory/summaries/library-conflicts.md",
    ".ai-memory/meta/failure-modes.md",
]

# P2 治本机制: failure-modes.md 主索引文件 + archived-lessons.md + 硬上限
FAILURE_MODES_PATH = ".ai-memory/meta/failure-modes.md"
ARCHIVED_LESSONS_PATH = ".ai-memory/meta/archived-lessons.md"

# failure-modes.md 行数硬上限 (P5 治本硬约束, fallback 用)
# TD-312 已修 (2026-07-21 spec-61): enforce_failure_modes_limit 从 frontmatter p5_max_lines 动态读取, 本常量仅 fallback
FAILURE_MODES_MAX_LINES = 190  # fallback when frontmatter p5_max_lines 缺失/非法 (s28 2026-08-17 同步 170→190)
# 6 个月未引用 → 归档候选
DORMANT_MONTHS_THRESHOLD = 6
# 活跃 N## 在引用扫描路径中出现次数阈值 (≤ 此值 + 6 个月未引用 → 归档)
DORMANT_REFCOUNT_THRESHOLD = 1

# v9.2 Spec A (2026-08-22): Active 硬上限机械出清.
# 背景: 沉淀纪律强制写入引用导致 refcount 保护失效 (--archive/--enforce-limits
# 均为 0 候选), 只进不出. 改用索引行自带 trigger_count / last_triggered 列判据.
ACTIVE_N_CAP = 35          # Active 段硬上限, 超限触发机械出清
CAP_STALE_DAYS = 30        # last_triggered 早于此天数才可出清 (v9.2 调参: 观测多数 N## ~37d 内被重触发, 60d 在清理节奏下几不触发, 30d 才能捕获真·陈旧者)
CAP_TRIGGER_MAX = 5        # trigger_count ≤ 此值才可出清 (v9.2 调参: 低频阈值放宽到历史触发≤5)

# Regex to match N## index rows in failure-modes.md:
# | N91 | pre-commit hook 失败 | ... |
NINDEX_ROW_RE = re.compile(r"^\|\s*(N\d+)\s*\|(.*)\|$")
# Detection of dormant / merged markers in N## row.
DORMANT_MARKERS = ("(dormant", "(已合并到", "(M0 闭环", "(M0.A 闭环", "(v8.4 闭环", "(v8.5 闭环", "(v8.6 闭环", "(v9.0 闭环", "(v9.1 闭环")

def scan_lessons(root: Path) -> list[dict[str, object]]:
    """Walk root/.ai-memory/lessons/ and root/.ai-memory/summaries/ and collect {path, priority, symptoms, date}.

    Files without a parseable `priority:` field default to "low" (no auto-suggest).
    """
    candidates: list[Path] = []
    if root.name == ".ai-memory":
        candidates.append(root / "lessons")
        candidates.append(root / "summaries")
    else:
        candidates.append(root / ".ai-memory" / "lessons")
        candidates.append(root / ".ai-memory" / "summaries")
    lessons: list[dict[str, object]] = []
    for lessons_dir in candidates:
        if not lessons_dir.exists():
            continue
        for path in sorted(lessons_dir.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            fm = parse_front_matter(text)[0]
            priority = str(fm.get("priority", "low")).lower()
            if priority not in ("high", "medium", "low"):
                priority = "low"
            raw_symptoms = fm.get("symptom", [])
            if isinstance(raw_symptoms, list):
                symptom_list = [str(s).strip() for s in raw_symptoms if str(s).strip()]
            else:
                symptom_list = [
                    s.strip()
                    for s in str(raw_symptoms).strip("[]").split(",")
                    if s.strip()
                ]
            # 改进 2 (2026-07-16): detect family main entries to skip re-promotion.
            # New v9.1 family mains carry `merged_n_ids` front-matter; older family
            # mains (N105/N109/N126/N135) lack it but --apply idempotent check
            # still protects against duplicate writes.
            is_family_main = bool(fm.get("merged_n_ids")) or bool(
                re.search(r"-n\d+-n\d+-", path.name)
            )
            # 🆕 P1b (2026-07-16): l2_candidate frontmatter field
            # true = 已沉淀到 ai-operating-handbook.md Part 2 (L2 硬加载)
            # false/missing = 未沉淀, 高频时 promote_lessons 提议沉淀
            l2_candidate_raw = fm.get("l2_candidate", False)
            l2_candidate = str(l2_candidate_raw).lower() in ("true", "yes", "1")
            lessons.append(
                {
                    "path": path,
                    "name": path.name,
                    "priority": priority,
                    "symptoms": symptom_list,
                    "date": fm.get("date", "unknown"),
                    "is_family_main": is_family_main,
                    "l2_candidate": l2_candidate,
                    "n_id": fm.get("n_id", ""),
                }
            )
    return lessons


def count_references(lesson: dict[str, object], root: Path) -> int:
    """Count how many times this lesson's symptoms or filename appear in REFERENCE_SCAN_PATHS.

    Used as the "frequently referenced" signal for promotion.
    """
    haystack_keywords: list[str] = []
    name = str(lesson["name"])
    # Strip date prefix and .md suffix to match references like "n95-distribution-gap".
    base = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", name)
    base = base[:-3] if base.endswith(".md") else base
    if base:
        haystack_keywords.append(base)
    for symptom in lesson.get("symptoms", []):
        # Symptom strings like "n95:distribution:gap" or Chinese.
        for chunk in re.split(r"[:：,，]", str(symptom)):
            chunk = chunk.strip()
            if chunk and len(chunk) >= 3:
                haystack_keywords.append(chunk)

    total = 0
    for rel in REFERENCE_SCAN_PATHS:
        path = root / rel
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for kw in haystack_keywords:
            total += text.count(kw)
    return total


def suggest_promotion(lessons: list[dict[str, object]], root: Path) -> list[dict[str, object]]:
    """Filter lessons that meet the auto-suggest threshold.

    Returns lessons that have priority + ref count matching PROMOTE_THRESHOLDS,
    annotated with `ref_count` and the chosen `target_key`.

    🆕 P1b (2026-07-16): Also detects L2 candidate (priority=high + refs >= 3 +
    l2_candidate != true) → target_key="handbook". AI 手动沉淀后设 l2_candidate=true.
    """
    suggestions: list[dict[str, object]] = []
    for lesson in lessons:
        # 改进 2 (2026-07-16): skip family main entries — already merged,
        # re-promoting just adds noise (and --apply idempotent check would
        # skip the write anyway, but --dry-run was misleading).
        if lesson.get("is_family_main"):
            continue
        priority = str(lesson["priority"])
        threshold = PROMOTE_THRESHOLDS.get(priority)
        if threshold is None:
            continue
        ref_count = count_references(lesson, root)
        if ref_count < threshold:
            continue
        # 🆕 P1b (2026-07-16): L2 candidate detection — high + refs >= 3 + not yet沉淀
        if (priority == "high" and ref_count >= L2_CANDIDATE_REFS
                and not lesson.get("l2_candidate")):
            suggestions.append(
                {
                    **lesson,
                    "ref_count": ref_count,
                    "threshold": threshold,
                    "target_key": "handbook",
                    "l2_candidate_reason": (
                        f"priority=high + refs={ref_count} >= {L2_CANDIDATE_REFS} + "
                        f"l2_candidate=false → 建议沉淀到 ai-operating-handbook.md Part 2"
                    ),
                }
            )
            continue  # L2 candidate 优先, 不重复提议到其他目标
        # Target selection: high + heavily-cited → rules / docs;
        # medium → failure_modes.
        target_key = "docs" if priority == "high" else "failure_modes"
        if priority == "high" and ref_count >= 4:
            target_key = "rules"
        suggestions.append(
            {
                **lesson,
                "ref_count": ref_count,
                "threshold": threshold,
                "target_key": target_key,
            }
        )
    return suggestions


def render_suggestions(suggestions: list[dict[str, object]]) -> str:
    """Pretty-print a list of promotion suggestions."""
    if not suggestions:
        return "✅ 无提议 (所有 lessons 引用次数未达阈值)"
    lines = [f"📋 提议 {len(suggestions)} 条提升:"]
    for i, s in enumerate(suggestions, 1):
        target = PROMOTE_TARGETS[str(s["target_key"])]
        lines.append(f"  [{i}] {s['name']}")
        lines.append(
            f"      priority: {s['priority']}  refs: {s['ref_count']} (阈值 {s['threshold']})"
        )
        lines.append(f"      → 目标: {target['kind_label']} ({target['path']})")
        lines.append(f"      symptoms: {', '.join(s['symptoms']) or '(none)'}")
        # 🆕 P1b (2026-07-16): L2 candidate 提示
        if s.get("l2_candidate_reason"):
            lines.append(f"      ⚠️ L2 candidate: {s['l2_candidate_reason']}")
            lines.append(f"         AI 手动沉淀后设 frontmatter: l2_candidate: true")
    return "\n".join(lines)


def append_to_target(suggestion: dict[str, object], root: Path) -> str:
    """Append a one-paragraph entry to the target file under the M0.M marker.

    Idempotent: skips if lesson name already appears in the target.
    """
    target_key = str(suggestion["target_key"])
    target_meta = PROMOTE_TARGETS[target_key]
    target_path = root / target_meta["path"]
    if not target_path.exists():
        return f"⚠️ 目标文件不存在: {target_path}"
    text = target_path.read_text(encoding="utf-8")
    if str(suggestion["name"]) in text:
        return f"⏭️ 已存在, 跳过: {suggestion['name']}"
    marker = target_meta["marker"]
    addition = f"\n{marker}\n\n" if marker not in text else ""
    entry = (
        f"- **{suggestion['name']}** "
        f"(priority={suggestion['priority']}, refs={suggestion['ref_count']}, "
        f"date={suggestion['date']})\n"
        f"  - symptoms: {', '.join(suggestion['symptoms']) or '(none)'}\n"
    )
    new_text = text + addition + entry
    target_path.write_text(new_text, encoding="utf-8")
    return f"✅ 已写入 {target_meta['path']}"


def log_promote(applied: list[dict[str, object]], root: Path) -> None:
    """Append a single audit-log line summarising this --apply run."""
    PROMOTE_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    names = ",".join(str(s["name"]) for s in applied) or "(none)"
    line = f"PROMOTE ts={ts} count={len(applied)} names={names}\n"
    with PROMOTE_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)


# ============================================================================
# P2 治本机制: N## 生命周期自动化 (--archive / --enforce-limits)
# ============================================================================

def parse_failure_modes_index(root: Path) -> list[dict[str, object]]:
    """Parse failure-modes.md N## index table.

    Returns a list of dicts with keys:
        n_id (str): "N91"
        line (str): full original line
        n_num (int): 91
        row_content (str): content after N## column
        is_dormant (bool): True if row contains dormant / merged / closed marker
        lesson_path (str|None): lesson file path extracted from row (if any)
    """
    fm_path = root / FAILURE_MODES_PATH
    if not fm_path.exists():
        return []
    text = fm_path.read_text(encoding="utf-8")
    entries: list[dict[str, object]] = []
    for line in text.splitlines():
        m = NINDEX_ROW_RE.match(line)
        if not m:
            continue
        n_id = m.group(1)
        row_content = m.group(2)
        try:
            n_num = int(n_id[1:])
        except ValueError:
            continue
        is_dormant = any(marker in row_content for marker in DORMANT_MARKERS)
        # Extract lesson path from row (look for `lessons/...md` pattern)
        lesson_match = re.search(r"lessons/[^\s`)]+\.md", row_content)
        lesson_path = lesson_match.group(0) if lesson_match else None
        entries.append({
            "n_id": n_id,
            "n_num": n_num,
            "line": line,
            "row_content": row_content,
            "is_dormant": is_dormant,
            "lesson_path": lesson_path,
        })
    return entries


def count_n_id_references(n_id: str, root: Path) -> int:
    """Count occurrences of `n_id` (e.g. "N91") across reference scan paths
    AND yn-matrices/ sub-files AND lessons/README.md.

    Excludes the failure-modes.md index row itself (counted as 1 baseline).
    """
    scan_paths = list(REFERENCE_SCAN_PATHS) + [
        ".ai-memory/meta/yn-matrices.md",
        ".ai-memory/lessons/README.md",
        ".ai-memory/meta/archived-lessons.md",
    ]
    # Also include yn-matrices/ sub-files (active + archived)
    # Wave 2 (2026-07-26, spec-2026-07-26-ai-governance-execution-rate-fix):
    # archived-yn-matrices/ 仍含 N## 引用, 需一起扫描以保持引用计数准确.
    yn_dir = root / ".ai-memory" / "meta" / "yn-matrices"
    if yn_dir.exists():
        for sub in yn_dir.glob("_*.md"):
            scan_paths.append(str(sub.relative_to(root)))
        archived_yn_dir = yn_dir / "archived-yn-matrices"
        if archived_yn_dir.exists():
            for sub in archived_yn_dir.glob("_*.md"):
                scan_paths.append(str(sub.relative_to(root)))

    total = 0
    for rel in scan_paths:
        path = root / rel
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Count word-boundary matches to avoid N91 matching N911
        total += len(re.findall(rf"\b{re.escape(n_id)}\b", text))
    # Subtract 1 for the failure-modes.md index row itself
    fm_path = root / FAILURE_MODES_PATH
    if fm_path.exists():
        fm_text = fm_path.read_text(encoding="utf-8")
        fm_count = len(re.findall(rf"^\|\s*{re.escape(n_id)}\s*\|", fm_text, re.MULTILINE))
        total -= fm_count
    return max(total, 0)


def get_lesson_last_activity(n_id: str, root: Path) -> _dt.date | None:
    """Estimate last activity date for N## by scanning lessons/ front matter.

    Looks for lesson files whose name or content references this N##,
    returns the most recent `date` / `auto_updated` field found.
    Returns None if no lesson file found.
    """
    lessons_dir = root / ".ai-memory" / "lessons"
    if not lessons_dir.exists():
        return None
    n_num_str = n_id[1:]  # "91" from "N91"
    candidates: list[_dt.date] = []
    for path in lessons_dir.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Match by filename (e.g. ...-n91-...md) or content (N91 mention)
        if f"-n{n_num_str}-" not in path.name and n_id not in text:
            continue
        fm = parse_front_matter(text)[0]
        for field in ("auto_updated", "date", "generated", "created_by"):
            val = fm.get(field)
            if isinstance(val, str):
                try:
                    d = _dt.date.fromisoformat(val[:10])
                    candidates.append(d)
                except ValueError:
                    pass
    return max(candidates) if candidates else None


def find_dormant_n_entries(root: Path) -> list[dict[str, object]]:
    """Identify N## entries to archive (P2 治本机制).

    Archive candidates:
    1. Rows marked dormant / merged / closed (DORMANT_MARKERS) → archive immediately
    2. Active N## with refcount ≤ DORMANT_REFCOUNT_THRESHOLD AND last activity
       older than DORMANT_MONTHS_THRESHOLD months → archive

    Returns list of dicts with keys: n_id, line, reason, last_activity, refcount
    """
    entries = parse_failure_modes_index(root)
    cutoff_date = _dt.date.today() - _dt.timedelta(days=DORMANT_MONTHS_THRESHOLD * 30)
    candidates: list[dict[str, object]] = []
    for entry in entries:
        n_id = str(entry["n_id"])
        if entry["is_dormant"]:
            candidates.append({
                "n_id": n_id,
                "line": entry["line"],
                "reason": "dormant marker (已合并/闭环/dormant)",
                "last_activity": None,
                "refcount": 0,
            })
            continue
        # Active N##: check refcount + last activity
        refcount = count_n_id_references(n_id, root)
        last_activity = get_lesson_last_activity(n_id, root)
        if refcount > DORMANT_REFCOUNT_THRESHOLD:
            continue
        if last_activity is None:
            # No lesson file — only archive if extremely low refcount
            if refcount == 0:
                candidates.append({
                    "n_id": n_id,
                    "line": entry["line"],
                    "reason": f"no lesson file + refcount={refcount}",
                    "last_activity": None,
                    "refcount": refcount,
                })
            continue
        if last_activity < cutoff_date:
            candidates.append({
                "n_id": n_id,
                "line": entry["line"],
                "reason": f"refcount={refcount} + last_activity={last_activity.isoformat()} (< {cutoff_date.isoformat()})",
                "last_activity": last_activity,
                "refcount": refcount,
            })
    return candidates


def archive_n_entries(candidates: list[dict[str, object]], root: Path, apply: bool) -> list[str]:
    """Remove candidate rows from failure-modes.md and append to archived-lessons.md.

    All candidates are removed from failure-modes.md. Only candidates NOT already
    in archived-lessons.md are appended (idempotent append).

    Returns list of action log lines.
    """
    if not candidates:
        return ["✅ 无归档候选"]
    fm_path = root / FAILURE_MODES_PATH
    arch_path = root / ARCHIVED_LESSONS_PATH
    if not fm_path.exists() or not arch_path.exists():
        return [f"❌ 文件不存在: {fm_path} 或 {arch_path}"]
    fm_text = fm_path.read_text(encoding="utf-8")
    arch_text = arch_path.read_text(encoding="utf-8")
    actions: list[str] = []
    # All candidate lines must be removed from failure-modes.md
    candidate_lines = {str(c["line"]) for c in candidates}
    new_fm_lines = [
        line for line in fm_text.splitlines() if line not in candidate_lines
    ]
    new_fm_text = "\n".join(new_fm_lines)
    if not new_fm_text.endswith("\n"):
        new_fm_text += "\n"
    # Only append candidates NOT already in archived-lessons.md
    candidates_to_append: list[dict[str, object]] = []
    for cand in candidates:
        n_id = str(cand["n_id"])
        if re.search(rf"\b{re.escape(n_id)}\b", arch_text):
            actions.append(f"⏭️ 已在 archived-lessons.md: {n_id} (仅从 failure-modes.md 删除)")
            continue
        candidates_to_append.append(cand)
    # Build archive append block (only for new entries)
    new_arch_text = arch_text
    if candidates_to_append:
        ts = _dt.datetime.now().strftime("%Y-%m-%d")
        append_block = ["\n## P2 自动归档 (治本机制 — " + ts + ")\n"]
        append_block.append("| N## | 原索引行 | 归档原因 |")
        append_block.append("|:---:|---------|---------|")
        for cand in candidates_to_append:
            reason = str(cand["reason"]).replace("|", "\\|")
            line_escaped = str(cand["line"]).replace("|", "\\|")
            append_block.append(f"| {cand['n_id']} | {line_escaped} | {reason} |")
        append_block.append("")
        if not new_arch_text.endswith("\n"):
            new_arch_text += "\n"
        new_arch_text += "\n".join(append_block)
    if apply:
        fm_path.write_text(new_fm_text, encoding="utf-8")
        if candidates_to_append:
            arch_path.write_text(new_arch_text, encoding="utf-8")
        for cand in candidates:
            actions.append(f"✅ 归档 {cand['n_id']}: {cand['reason']}")
        # Log
        PROMOTE_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts_iso = _dt.datetime.now().isoformat(timespec="seconds")
        names = ",".join(str(c["n_id"]) for c in candidates)
        with PROMOTE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"ARCHIVE ts={ts_iso} count={len(candidates)} names={names}\n")
    else:
        for cand in candidates:
            actions.append(f"📋 待归档 {cand['n_id']}: {cand['reason']}")
    return actions


def parse_active_rows_with_stats(root: Path) -> list[dict[str, object]]:
    """Parse Active-section rows of failure-modes.md with trigger stats.

    Only scans the `## Active N##` section (stops at next `## ` header).
    Extracts trailing `| trigger_count | last_triggered |` columns.
    Rows without parseable stats get trigger_count=None / last_triggered=None
    and are never cap-eligible.
    """
    fm_path = root / FAILURE_MODES_PATH
    if not fm_path.exists():
        return []
    text = fm_path.read_text(encoding="utf-8")
    in_active = False
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            in_active = "Active N##" in line
            continue
        if not in_active or line.startswith("#"):
            continue
        m = NINDEX_ROW_RE.match(line)
        if not m:
            continue
        n_id = m.group(1)
        trigger_count: int | None = None
        last_triggered: _dt.date | None = None
        sm = re.search(r"\|\s*(\d+)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|?\s*$", line)
        if sm:
            trigger_count = int(sm.group(1))
            try:
                last_triggered = _dt.date.fromisoformat(sm.group(2))
            except ValueError:
                pass
        rows.append({
            "n_id": n_id,
            "line": line,
            "trigger_count": trigger_count,
            "last_triggered": last_triggered,
        })
    return rows


def find_cap_candidates(root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Identify stale Active N## rows eligible for mechanical clearing.

    Eligible = last_triggered < today - CAP_STALE_DAYS AND trigger_count ≤ CAP_TRIGGER_MAX.
    Protected = referenced by any L0 file (.skills/rules/*.md) — always-injected
    rules are definitionally active regardless of trigger stats.

    Returns (candidates_sorted_oldest_first, all_active_rows).
    """
    rows = parse_active_rows_with_stats(root)
    l0_text = ""
    for p in sorted((root / ".skills" / "rules").glob("*.md")):
        try:
            l0_text += p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    cutoff = _dt.date.today() - _dt.timedelta(days=CAP_STALE_DAYS)
    eligible: list[tuple[_dt.date, int, dict[str, object]]] = []
    for row in rows:
        n_id = str(row["n_id"])
        # L0 常驻保护: 被 rules 层引用的 N## 不出清
        if re.search(rf"\b{re.escape(n_id)}\b", l0_text):
            continue
        cnt = row["trigger_count"]
        last = row["last_triggered"]
        if cnt is None or last is None:
            continue
        if last < cutoff and cnt <= CAP_TRIGGER_MAX:
            eligible.append((last, cnt, row))
    eligible.sort(key=lambda t: (t[0], t[1]))
    candidates = [t[2] for t in eligible]
    return candidates, rows


def enforce_active_cap(root: Path, apply: bool) -> list[str]:
    """v9.2 Spec A: Active 段 > ACTIVE_N_CAP → 机械出清最陈旧条目到 archived-lessons.md.

    出清判据 (全部满足): last_triggered < 60 天前 + trigger_count ≤ 3 +
    未被 .skills/rules/*.md 引用. lessons 文件保留, 可随时解档恢复.
    """
    candidates, rows = find_cap_candidates(root)
    actions: list[str] = [
        f"📊 Active N## {len(rows)} 条 / 上限 {ACTIVE_N_CAP} 条"
    ]
    excess = len(rows) - ACTIVE_N_CAP
    if excess <= 0:
        actions.append(f"✅ Active {len(rows)} ≤ {ACTIVE_N_CAP}, 无需出清")
        return actions
    if not candidates:
        actions.append(
            f"⚠️ 超限 {excess} 条但无可出清候选 "
            f"(判据: last_triggered<{CAP_STALE_DAYS}天 + trigger≤{CAP_TRIGGER_MAX} + 非L0引用)"
        )
        return actions
    to_clear = candidates[:excess]
    actions.append(
        f"📋 待出清 {len(to_clear)} 条 (超限 {excess}):"
    )
    for cand in to_clear:
        cand["reason"] = (
            f"cap-clear: last={cand['last_triggered']} cnt={cand['trigger_count']}"
        )
        actions.append(
            f"  - {cand['n_id']}: last={cand['last_triggered']} cnt={cand['trigger_count']}"
        )
    actions.extend(archive_n_entries(to_clear, root, apply=apply))
    return actions


def check_active_cap(root: Path) -> int:
    """Passive commit-time guard (ratchet semantics).

    - Active ≤ ACTIVE_N_CAP → pass.
    - Active > cap AND mechanical candidates exist → exit 1 (blocks commit
      until `--enforce-cap --apply` clears them).
    - Active > cap but nothing eligible → pass with warning (data too young;
      converges toward cap over time as entries age past CAP_STALE_DAYS).
    """
    rows = parse_active_rows_with_stats(root)
    if len(rows) <= ACTIVE_N_CAP:
        print(f"✅ active-n-cap: {len(rows)} ≤ {ACTIVE_N_CAP}")
        return 0
    candidates, _ = find_cap_candidates(root)
    if not candidates:
        print(
            f"⚠️ active-n-cap: Active {len(rows)} > {ACTIVE_N_CAP} 但暂无可机械出清候选 "
            f"(判据过严或数据太新), 放行"
        )
        return 0
    print(
        f"❌ active-n-cap: Active {len(rows)} > {ACTIVE_N_CAP} 且存在 "
        f"{len(candidates)} 条可出清候选; 跑 "
        f"`python scripts/lessons/promote_lessons.py --enforce-cap --apply` 出清后重试"
    )
    return 1


def enforce_failure_modes_limit(root: Path, apply: bool) -> list[str]:
    """P5 治本硬约束: failure-modes.md body > p5_max_lines (frontmatter) → archive
    least-active N## until ≤ p5_max_lines.

    TD-312 修复 (2026-07-21 spec-61):
    - bug 2: line_count 改用 body (不含 frontmatter), 与 P5 约束 "不含 frontmatter" 语义一致
    - bug 1: max_lines 从 frontmatter p5_max_lines 读取, 不再硬编码常量 (常量保留为 fallback)

    Returns list of action log lines.
    """
    fm_path = root / FAILURE_MODES_PATH
    if not fm_path.exists():
        return [f"❌ 文件不存在: {fm_path}"]
    fm_text = fm_path.read_text(encoding="utf-8")
    # TD-312 fix: 用 parse_front_matter 分离 frontmatter 和 body
    data, body, had_fm = parse_front_matter(fm_text)
    body_line_count = len(body.splitlines())
    # TD-312 fix: max_lines 从 frontmatter p5_max_lines 读取, fallback 用常量
    try:
        max_lines = int(data.get("p5_max_lines", FAILURE_MODES_MAX_LINES))
    except (ValueError, TypeError):
        max_lines = FAILURE_MODES_MAX_LINES
    if body_line_count <= max_lines:
        return [f"✅ failure-modes.md body {body_line_count} ≤ {max_lines} 行 (p5_max_lines), 无需归档"]
    # Sort active N## by last_activity ascending (oldest first)
    entries = parse_failure_modes_index(root)
    active = [e for e in entries if not e["is_dormant"]]
    sortable: list[tuple[_dt.date | None, dict[str, object]]] = []
    far_future = _dt.date(9999, 12, 31)
    for entry in active:
        n_id = str(entry["n_id"])
        # P5 fix (2026-07-16): N## referenced by yn-matrices / SKILL.md / rules.md
        # is actively used, skip it entirely (do not archive).
        refcount = count_n_id_references(n_id, root)
        if refcount > 0:
            continue  # actively referenced, never archive
        last_activity = get_lesson_last_activity(n_id, root)
        sort_key = last_activity if last_activity is not None else far_future
        sortable.append((sort_key, entry))
    sortable.sort(key=lambda x: x[0])
    candidates: list[dict[str, object]] = []
    projected_lines = body_line_count
    for sort_key, entry in sortable:
        if projected_lines <= max_lines:
            break
        n_id = str(entry["n_id"])
        last_str = sort_key.isoformat() if sort_key != far_future else "unknown"
        candidates.append({
            "n_id": n_id,
            "line": entry["line"],
            "reason": f"enforce-limits: last_activity={last_str}",
            "last_activity": sort_key if sort_key != far_future else None,
            "refcount": 0,
        })
        projected_lines -= 1
    if not candidates:
        return [f"⚠️ failure-modes.md body {body_line_count} > {max_lines} (p5_max_lines) 但无可归档候选"]
    header = f"📊 failure-modes.md body {body_line_count} 行 > {max_lines} (p5_max_lines) 上限, 待归档 {len(candidates)} 条:"
    actions = [header]
    actions.extend(archive_n_entries(candidates, root, apply=apply))
    return actions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promote frequently-referenced .ai-memory/lessons/ to 4 target files (M0.M)."
    )
    parser.add_argument(
        "--root", default=str(REPO_ROOT_DEFAULT),
        help="Path to the GAF repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print suggestions only; do not modify any file (default mode).",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="AI-confirmed: actually append entries to target files + write audit log.",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print summary stats and exit (no suggestions).",
    )
    parser.add_argument(
        "--archive", action="store_true",
        help="P2 治本机制: archive dormant N## from failure-modes.md to archived-lessons.md.",
    )
    parser.add_argument(
        "--enforce-limits", action="store_true",
        help="P5 治本硬约束: failure-modes.md > 100 lines → archive least-active N##.",
    )
    parser.add_argument(
        "--enforce-cap", action="store_true",
        help="v9.2 Spec A: Active 段 > ACTIVE_N_CAP → 机械出清最陈旧条目.",
    )
    parser.add_argument(
        "--check-cap", action="store_true",
        help="v9.2 Spec A: passive guard — exit 1 if Active > ACTIVE_N_CAP (commit-time).",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()

    # v9.2 passive cap guard (no file mutation)
    if args.check_cap:
        return check_active_cap(root)

    # P2/P5/v9.2 archive mode (互斥 with default promote mode)
    if args.archive or args.enforce_limits or args.enforce_cap:
        if args.enforce_limits:
            actions = enforce_failure_modes_limit(root, apply=args.apply)
            actions.extend(enforce_active_cap(root, apply=args.apply))
        elif args.enforce_cap:
            actions = enforce_active_cap(root, apply=args.apply)
        else:
            candidates = find_dormant_n_entries(root)
            print(f"📊 归档候选 {len(candidates)} 条:")
            for cand in candidates:
                print(f"  - {cand['n_id']}: {cand['reason']}")
            print()
            actions = archive_n_entries(candidates, root, apply=args.apply)
        for line in actions:
            print(line)
        return 0

    lessons = scan_lessons(root)
    if not lessons:
        print(f"❌ 未找到任何 lessons: {root / '.ai-memory' / 'lessons'} (或 {root / '.ai-memory' / 'summaries'})", file=sys.stderr)
        return 1

    if args.stats:
        by_pri: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for lesson in lessons:
            by_pri[str(lesson["priority"])] += 1
        print(f"📊 lessons 总数: {len(lessons)}")
        for pri in ("high", "medium", "low"):
            print(f"   - priority={pri}: {by_pri[pri]}")
        return 0

    suggestions = suggest_promotion(lessons, root)
    print(render_suggestions(suggestions))

    if not args.apply:
        return 0
    if not suggestions:
        print("(无 apply 项)")
        return 0

    print("\n🔧 --apply 模式, 写入目标文件 + audit log ...")
    applied: list[dict[str, object]] = []
    for s in suggestions:
        result = append_to_target(s, root)
        print(f"  {result}")
        applied.append(s)
    log_promote(applied, root)
    print(f"\n📝 audit log: {PROMOTE_LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
