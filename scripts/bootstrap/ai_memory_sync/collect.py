"""collect domain (s38 split from sync_ai_memory.py, TD-365).

Fuzzy-match collection across 4 sources: lessons/ + failure-modes.md N## index
+ yn-matrices/_*.md + summaries/*.md. Parsed front matter helpers live in
sync_ai_memory (main file) and are reached via `_main` (runtime attribute
lookup keeps test-side `sync_ai_memory.yaml` patching effective).
"""

from __future__ import annotations

import re

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path
from pathlib import Path as _Path
from typing import Dict, List

_SCRIPTS_DIR = _Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

if "sync_ai_memory" in _sys.modules:
    # sys.path hack context (scripts/tests): top-level module already loaded.
    import sync_ai_memory as _main
else:
    try:
        from scripts.bootstrap import sync_ai_memory as _main
    except ImportError:  # pragma: no cover - unreachable in package context
        import sync_ai_memory as _main

from symptom_synonyms import expand_query  # noqa: E402


def collect_lessons(root: Path) -> List[Dict[str, object]]:
    """Walk root/.ai-memory/lessons/ and parse every file's front matter.

    `root` may be either the GAF repo root (e.g. `D:/.../GAF`) or the
    `.ai-memory/` directory itself — both are accepted for caller
    convenience, since `--root` is documented at the repo level while
    some library callers may pass the AI memory directory directly.

    Returns a list of dicts: {path, data, body, had_front_matter}.
    Files with missing or invalid front matter are included with empty
    data so the caller can decide how to surface them.
    """
    candidates: List[Path] = []
    if root.name == ".ai-memory":
        candidates.append(root / "lessons")
    else:
        candidates.append(root / ".ai-memory" / "lessons")
        candidates.append(root / "lessons")
    for lessons_dir in candidates:
        if lessons_dir.exists():
            break
    else:
        return []
    lessons: List[Dict[str, object]] = []
    for path in sorted(lessons_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        try:
            data, body, had_fm = _main.parse_front_matter(text)
        except _main.FrontMatterError:
            data, body, had_fm = {}, text, False
        lessons.append(
            {
                "path": path,
                "data": data,
                "body": body,
                "had_front_matter": had_fm,
            }
        )
    return lessons


def _symptom_tokens(data: Dict[str, object]) -> List[str]:
    """Flatten a front matter's `symptom` field into a list of strings."""
    symptom = data.get("symptom", [])
    if isinstance(symptom, str):
        return [symptom]
    if isinstance(symptom, list):
        return [str(s) for s in symptom]
    return []


def query_lessons(
    query: str,
    root: Path,
) -> List[Dict[str, object]]:
    """Fuzzy-match a user query against lesson symptom fields.

    Returns a list of matches sorted by descending score (number of
    expanded keywords that hit the lesson's symptom list). Each match
    is a dict with: path, score, matched_keywords, symptom.
    """
    keywords = expand_query(query)
    if not keywords:
        return []
    keywords_lower = {k.lower() for k in keywords}
    matches: List[Dict[str, object]] = []
    for lesson in collect_lessons(root):
        tokens = _symptom_tokens(lesson["data"])
        if not tokens and not lesson["had_front_matter"]:
            continue
        hit = []
        for token in tokens:
            if token.lower() in keywords_lower:
                hit.append(token)
            else:
                # Partial match: token contains a keyword or vice versa.
                for kw in keywords_lower:
                    if kw in token.lower() or token.lower() in kw:
                        hit.append(token)
                        break
        if hit:
            matches.append(
                {
                    "path": lesson["path"],
                    "score": len(set(hit)),
                    "matched_keywords": sorted(set(hit)),
                    "symptom": tokens,
                    "source": "lessons",
                }
            )
    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches


# B3 治本机制 (2026-07-16): 扩展 L3 检索覆盖到 4 目录.
# 旧机制: 仅扫 lessons/, failure-modes/yn-matrices/summaries 是检索盲区.
# 新机制: 4 目录全扫 + N## 编号同义词扩展, 覆盖率 25% → 100%.
# 不引入 embedding: 避免新增依赖 + 索引文件维护成本.
EXTENDED_SCAN_PATHS: List[Path] = []  # populated lazily per-root


def _scan_failure_modes_index(root: Path) -> List[Dict[str, object]]:
    """Scan failure-modes.md N## index rows as queryable records."""
    # Handle both repo root and .ai-memory dir as `root` (same logic as collect_lessons).
    if root.name == ".ai-memory":
        fm_path = root / "meta" / "failure-modes.md"
    else:
        fm_path = root / ".ai-memory" / "meta" / "failure-modes.md"
    if not fm_path.exists():
        return []
    text = fm_path.read_text(encoding="utf-8")
    records: List[Dict[str, object]] = []
    for line in text.splitlines():
        # Match: | N91 | description | lessons/file | ... |
        m = re.match(r"^\|\s*(N\d+)\s*\|([^|]+)\|([^|]*)\|", line)
        if not m:
            continue
        n_id = m.group(1).strip()
        desc = m.group(2).strip()
        lesson_ref = m.group(3).strip()
        # Tokens: N## id + description words + lesson ref
        tokens = [n_id] + [w for w in re.split(r"[\s,，/]+", desc) if w] + [w for w in re.split(r"[\s,，/]+", lesson_ref) if w]
        records.append(
            {
                "path": fm_path,
                "tokens": tokens,
                "n_id": n_id,
                "desc": desc,
                "source": "failure-modes",
            }
        )
    return records


def _scan_yn_matrices(root: Path) -> List[Dict[str, object]]:
    """Scan yn-matrices/_*.md files as queryable records.

    Wave 2 (2026-07-26, spec-2026-07-26-ai-governance-execution-rate-fix):
    同时扫描 archived-yn-matrices/ 子目录, source 字段标 "archived-yn-matrices".
    归档 sub-file 仍可作为 queryable record (历史 Y/N 矩阵的检索证据).
    """
    if root.name == ".ai-memory":
        yn_dir = root / "meta" / "yn-matrices"
    else:
        yn_dir = root / ".ai-memory" / "meta" / "yn-matrices"
    records: List[Dict[str, object]] = []

    def _scan_dir(dir_path: Path, source_label: str) -> None:
        if not dir_path.exists():
            return
        for sub in sorted(dir_path.glob("_*.md")):
            text = sub.read_text(encoding="utf-8")
            # Extract N## references + section headings as tokens
            n_refs = re.findall(r"\bN\d+\b", text)
            headings = re.findall(r"^#+\s*(.+)$", text, re.MULTILINE)
            tokens = list(set(n_refs + headings))
            records.append(
                {
                    "path": sub,
                    "tokens": tokens,
                    "source": source_label,
                }
            )

    _scan_dir(yn_dir, "yn-matrices")
    _scan_dir(yn_dir / "archived-yn-matrices" if yn_dir.exists() else None, "archived-yn-matrices")
    return records


def _scan_summaries(root: Path) -> List[Dict[str, object]]:
    """Scan summaries/*.md files as queryable records."""
    if root.name == ".ai-memory":
        sm_dir = root / "summaries"
    else:
        sm_dir = root / ".ai-memory" / "summaries"
    if not sm_dir.exists():
        return []
    records: List[Dict[str, object]] = []
    for path in sorted(sm_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            data, body, _ = _main.parse_front_matter(text)
        except Exception:
            data, body, _ = {}, text, False
        tokens = _symptom_tokens(data)
        # Also add headings + N## refs from body
        n_refs = re.findall(r"\bN\d+\b", body)
        headings = re.findall(r"^#+\s*(.+)$", body, re.MULTILINE)
        tokens = list(set(tokens + n_refs + headings))
        if tokens:
            records.append(
                {
                    "path": path,
                    "tokens": tokens,
                    "source": "summaries",
                }
            )
    return records


def query_all_sources(
    query: str,
    root: Path,
) -> List[Dict[str, object]]:
    """B3 治本机制: fuzzy-match query against 4 sources.

    Sources: lessons/ (via query_lessons) + failure-modes.md N## index +
    yn-matrices/_*.md + summaries/*.md.

    Each match dict includes `source` field: lessons / failure-modes / yn-matrices / summaries.
    """
    # 1. lessons/ (existing logic, already includes source=lessons)
    matches = query_lessons(query, root)

    keywords = expand_query(query)
    if not keywords:
        return matches
    keywords_lower = {k.lower() for k in keywords}

    # 2. failure-modes.md N## index
    for rec in _scan_failure_modes_index(root):
        tokens = rec["tokens"]
        hit = []
        for token in tokens:
            token_lower = token.lower()
            if token_lower in keywords_lower:
                hit.append(token)
            else:
                for kw in keywords_lower:
                    if kw in token_lower or token_lower in kw:
                        hit.append(token)
                        break
        if hit:
            matches.append(
                {
                    "path": rec["path"],
                    "score": len(set(hit)),
                    "matched_keywords": sorted(set(hit)),
                    "symptom": [rec["n_id"], rec["desc"]],
                    "source": rec["source"],
                }
            )

    # 3. yn-matrices/_*.md
    for rec in _scan_yn_matrices(root):
        tokens = rec["tokens"]
        hit = []
        for token in tokens:
            token_lower = token.lower()
            if token_lower in keywords_lower:
                hit.append(token)
            else:
                for kw in keywords_lower:
                    if kw in token_lower or token_lower in kw:
                        hit.append(token)
                        break
        if hit:
            matches.append(
                {
                    "path": rec["path"],
                    "score": len(set(hit)),
                    "matched_keywords": sorted(set(hit)),
                    "symptom": tokens[:5],  # first 5 tokens for brevity
                    "source": rec["source"],
                }
            )

    # 4. summaries/*.md
    for rec in _scan_summaries(root):
        tokens = rec["tokens"]
        hit = []
        for token in tokens:
            token_lower = token.lower()
            if token_lower in keywords_lower:
                hit.append(token)
            else:
                for kw in keywords_lower:
                    if kw in token_lower or token_lower in kw:
                        hit.append(token)
                        break
        if hit:
            matches.append(
                {
                    "path": rec["path"],
                    "score": len(set(hit)),
                    "matched_keywords": sorted(set(hit)),
                    "symptom": tokens[:5],
                    "source": rec["source"],
                }
            )

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches
