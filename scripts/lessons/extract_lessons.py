"""extract_lessons.py — v8.3.1 自动 lessons 提取器 (M0.D / M2.A 范围)

4 个数据源解析 + front matter 自动生成:
  1. code-rules.md       — summaries/code-rules.md (## section 列表)
  2. library-conflicts.md — summaries/library-conflicts.md (废弃 API 表格)
  3. bug-tracker.md       — ops/bug-tracker.md (BUG-### 表格)
  4. git log              — `git log --oneline` (commit messages)

每个数据源产生一个 "draft" 草稿 (.md 字符串), 含:
  - 完整 front matter (5 必填: maintainer / symptom / solution / related_files / created_by)
  - 草稿 section (≥ 20 字符, N85 修复: 防 AI 偷懒写空)

Usage:
    python extract_lessons.py                  # 跑所有 4 数据源
    python extract_lessons.py --source code-rules
    python extract_lessons.py --query popup    # 在索引中模糊搜
    python extract_lessons.py --dry-run        # 只解析, 不写
    python extract_lessons.py --root <path>    # 跨仓库

Lessons 索引: .ai-memory/lessons/_index.json
  - 4 字段: file / symptom / solution / source (4 数据源之一)
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: F401  (must be first; reconfigures stdout to UTF-8)

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
AI_MEMORY = REPO_ROOT_DEFAULT / ".ai-memory"
LESSONS_DIR = AI_MEMORY / "lessons"
SUMMARIES_DIR = AI_MEMORY / "summaries"
OPS_DIR = AI_MEMORY / "ops"
INDEX_PATH = LESSONS_DIR / "_index.json"

# 4 数据源 (固定顺序, 跟 spec.md §14 / Appendix G §G.2 一致)
SOURCES: Tuple[str, ...] = (
    "code-rules",
    "library-conflicts",
    "bug-tracker",
    "git-log",
)

SOURCE_PATHS: Dict[str, Path] = {
    "code-rules": SUMMARIES_DIR / "code-rules.md",
    "library-conflicts": SUMMARIES_DIR / "library-conflicts.md",
    "bug-tracker": OPS_DIR / "bug-tracker.md",
}

# Front matter 必填字段 (5 个, 跟 sync_ai_memory.py REQUIRED_FIELDS 一致)
REQUIRED_FIELDS: Tuple[str, ...] = (
    "maintainer",
    "symptom",
    "solution",
    "related_files",
    "created_by",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Convert a heading / commit message into a kebab-case slug for filenames.

    Examples:
        >>> _slugify("API_TIMEOUT 未定义导致白屏")
        'api-timeout'
        >>> _slugify("fix: scheduler select_related 500")
        'fix-scheduler-select-related-500'
    """
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", slug)
    slug = slug.strip("-")
    # Keep length sane — CJK chars take 3 bytes; cap at 50
    if len(slug) > 50:
        slug = slug[:50].rstrip("-")
    return slug or "lesson"


def _rel_path(path: Path) -> str:
    """Return path relative to repo root, falling back to absolute for fixture paths."""
    try:
        return str(path.relative_to(REPO_ROOT_DEFAULT))
    except ValueError:
        return str(path)


def _build_front_matter(
    *,
    symptom: List[str],
    solution: str,
    related_files: List[str],
    source: str,
) -> str:
    """Build a YAML front matter block from the 5 required fields.

    `date` is auto-filled with today's date; the caller can override by
    passing the resulting string to a custom writer.
    """
    today = _dt.date.today().isoformat()
    lines = ["---"]
    lines.append(f"date: {today}")
    lines.append("maintainer: auto")
    symptom_str = ", ".join(symptom)
    lines.append(f"symptom: [{symptom_str}]")
    # YAML escape: wrap in double quotes, escape backslashes and double quotes
    safe_solution = solution.replace("\\", "\\\\").replace('"', '\\"')
    lines.append(f'solution: "{safe_solution}"')
    lines.append("related_files:")
    for f in related_files:
        lines.append(f"  - {f}")
    lines.append("created_by: AI")
    lines.append(f"source: {source}")
    lines.append("---")
    return "\n".join(lines)


def _check_front_matter(front_matter: str) -> Tuple[bool, List[str]]:
    """Validate that all 5 REQUIRED_FIELDS are present in the front matter.

    Returns (is_valid, missing_field_list).
    """
    missing: List[str] = []
    for field in REQUIRED_FIELDS:
        # Match the field at line start, e.g. `symptom:` or `symptom :`
        if not re.search(rf"^{re.escape(field)}\s*:", front_matter, re.MULTILINE):
            missing.append(field)
    return (len(missing) == 0, missing)


# ---------------------------------------------------------------------------
# 4 data source parsers
# ---------------------------------------------------------------------------


def parse_code_rules(path: Path) -> List[Dict[str, object]]:
    """Parse code-rules.md — split by `## ` headings; one lesson per section.

    The section's body is used as the draft (first 30 lines, trimmed).
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    lessons: List[Dict[str, object]] = []
    # Split by `## ` heading (level 2); skip the H1 at the very top
    sections = re.split(r"^##\s+", text, flags=re.MULTILINE)
    # sections[0] = front matter + H1 intro; sections[1:] = each ## section
    for body in sections[1:]:
        # First line of body = heading text
        heading, _, rest = body.partition("\n")
        heading = heading.strip()
        if not heading:
            continue
        # Take the first non-empty, non-heading paragraph as the draft
        rest_lines = [
            line for line in rest.splitlines() if line.strip() and not line.startswith("#")
        ]
        draft = "\n".join(rest_lines[:5]).strip()
        if len(draft) < 20:
            # Section has no body — use the heading as a one-liner
            draft = heading
        lessons.append(
            {
                "source": "code-rules",
                "heading": heading,
                "draft": draft,
                "symptom": ["code-rules", _slugify(heading)[:30]],
                "solution": f"参考 code-rules.md §{heading} 规则",
                "related_files": [_rel_path(path)],
            }
        )
    return lessons


def parse_library_conflicts(path: Path) -> List[Dict[str, object]]:
    """Parse library-conflicts.md — one lesson per table row.

    Markdown table row format: `| # | Deprecated API | Correct API | ... |`
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    lessons: List[Dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if "---" in line:  # table separator
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        # Try to find deprecated → correct mapping in the first 3 columns
        deprecated = cells[1] if len(cells) > 1 else ""
        correct = cells[2] if len(cells) > 2 else ""
        if not deprecated or "Deprecated" in deprecated:
            # Header row, skip
            continue
        if "—" in deprecated or "—" in correct or not deprecated or not correct:
            continue
        lessons.append(
            {
                "source": "library-conflicts",
                "heading": f"{deprecated} → {correct}",
                "draft": f"`{deprecated}` 已废弃, 使用 `{correct}`",
                "symptom": ["library", "api-deprecated", _slugify(deprecated)[:30]],
                "solution": f"替换为 {correct}",
                "related_files": [_rel_path(path)],
            }
        )
    return lessons


def parse_bug_tracker(path: Path) -> List[Dict[str, object]]:
    """Parse bug-tracker.md — one lesson per BUG-NNN row."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    rel = _rel_path(path)
    lessons: List[Dict[str, object]] = []
    for line in text.splitlines():
        # Match BUG-### 格式
        m = re.match(r"\|\s*(BUG-\d+)\s*\|\s*([^|]+?)\s*\|", line)
        if not m:
            continue
        bug_id = m.group(1)
        title = m.group(2).strip()
        if not title or title == "Bug ID":
            continue
        lessons.append(
            {
                "source": "bug-tracker",
                "heading": f"{bug_id}: {title}",
                "draft": f"Bug {bug_id} — {title}; 详情见 bug-tracker.md",
                "symptom": ["bug", "已修复", bug_id.lower()],
                "solution": f"参考 {bug_id} 修复方式 (见 bug-tracker.md)",
                "related_files": [rel],
            }
        )
    return lessons


def parse_git_log(repo_root: Path, limit: int = 50) -> List[Dict[str, object]]:
    """Parse `git log --oneline -N` — one lesson per commit subject.

    Uses the commit hash and subject as the lesson slug.
    """
    try:
        out = subprocess.check_output(
            ["git", "log", "--oneline", f"-{limit}"],
            cwd=str(repo_root),
            stderr=subprocess.PIPE,
        ).decode("utf-8", errors="replace")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    lessons: List[Dict[str, object]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: `<hash> <subject>`
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        sha, subject = parts[0], parts[1].strip()
        # Conventional-commit-style: drop the type prefix for the heading
        clean = re.sub(r"^(feat|fix|docs|refactor|test|chore|perf|build|ci)\([^)]+\):\s*", "", subject)
        lessons.append(
            {
                "source": "git-log",
                "heading": subject,
                "draft": f"Commit `{sha[:8]}`: {subject}",
                "symptom": ["commit-history", sha[:8]],
                "solution": "参考 git log 历史",
                "related_files": [],
            }
        )
        _ = clean  # suppress unused warning
    return lessons


# ---------------------------------------------------------------------------
# Lesson assembly
# ---------------------------------------------------------------------------


def build_lesson_draft(item: Dict[str, object]) -> str:
    """Build a full lesson draft (front matter + body) from a parsed item.

    The body section must be ≥ 20 characters (N85 fix).
    """
    front_matter = _build_front_matter(
        symptom=list(item.get("symptom", [])),
        solution=str(item.get("solution", "")),
        related_files=list(item.get("related_files", [])),
        source=str(item.get("source", "")),
    )
    heading = str(item.get("heading", "Untitled"))
    draft = str(item.get("draft", ""))
    body = f"# {heading}\n\n## 症状\n\n{draft}\n\n## 根因\n\n参见源数据源 ({item.get('source')})。\n\n## 解决步骤\n\n参考相关文件与历史记录。\n"
    return f"{front_matter}\n\n{body}"


def build_all(repo_root: Path) -> Dict[str, List[Dict[str, object]]]:
    """Run all 4 parsers and return a {source: [items]} dict.

    Paths are derived from ``repo_root`` so callers can point at a real
    checkout or a fixture tree (keeps the 3 file sources consistent with
    ``parse_git_log`` which already runs in ``repo_root``).
    """
    ai_memory = repo_root / ".ai-memory"
    paths = {
        "code-rules": ai_memory / "summaries" / "code-rules.md",
        "library-conflicts": ai_memory / "summaries" / "library-conflicts.md",
        "bug-tracker": ai_memory / "ops" / "bug-tracker.md",
    }
    return {
        "code-rules": parse_code_rules(paths["code-rules"]),
        "library-conflicts": parse_library_conflicts(paths["library-conflicts"]),
        "bug-tracker": parse_bug_tracker(paths["bug-tracker"]),
        "git-log": parse_git_log(repo_root),
    }


def build_index(by_source: Dict[str, List[Dict[str, object]]]) -> List[Dict[str, object]]:
    """Build the lessons index used by `--query` and the sync tool.

    Each entry: {file, symptom, solution, source}.
    """
    index: List[Dict[str, object]] = []
    for source, items in by_source.items():
        for i, item in enumerate(items):
            slug = _slugify(str(item.get("heading", f"item-{i}")))
            filename = f"{source}-{slug}.md"
            index.append(
                {
                    "file": filename,
                    "symptom": list(item.get("symptom", [])),
                    "solution": str(item.get("solution", "")),
                    "source": source,
                }
            )
    return index


def write_index(by_source: Dict[str, List[Dict[str, object]]]) -> Path:
    """Write the lessons index to INDEX_PATH and return the path."""
    index = build_index(by_source)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return INDEX_PATH


def query_index(query: str, index: Optional[List[Dict[str, object]]] = None) -> List[Dict[str, object]]:
    """Fuzzy search the index for `query` (case-insensitive substring).

    `query` is matched against `symptom` and `solution` fields. If `index`
    is None, the on-disk `_index.json` is loaded.
    """
    if index is None:
        if not INDEX_PATH.exists():
            return []
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if not query:
        return index
    q = query.lower()
    hits = []
    for entry in index:
        symptoms = [str(s).lower() for s in entry.get("symptom", [])]
        solution = str(entry.get("solution", "")).lower()
        if any(q in s for s in symptoms) or q in solution:
            hits.append(entry)
    return hits


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF lessons 提取器 (4 数据源 + front matter 自动生成)"
    )
    parser.add_argument(
        "--source",
        choices=SOURCES,
        help="仅跑单个数据源 (默认: 全部 4 个)",
    )
    parser.add_argument(
        "--query",
        help="在 lessons 索引中模糊搜 (如 'popup' 或 'api:404')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析, 不写索引",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF 仓库根 (默认: %(default)s)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()

    if args.query:
        hits = query_index(args.query)
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0

    by_source = build_all(repo_root)
    if args.source:
        by_source = {args.source: by_source[args.source]}

    total = 0
    for source, items in by_source.items():
        print(f"  {source}: {len(items)} lessons")
        total += len(items)

    if not args.dry_run:
        idx_path = write_index(by_source)
        print(f"✅ Index written: {idx_path} ({total} lessons)")
    else:
        print(f"ℹ️  Dry-run: {total} lessons parsed, index not written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
