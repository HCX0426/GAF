"""spec_dependency_graph.py — TD-326 spec-89: spec 流程可视化依赖图.

扫描 ``docs/specs/legacy-trae/*.md`` 提取 spec 之间依赖关系,
生成 mermaid 依赖图到 ``docs/specs/dependency-graph.md`` (spec-2026-07-26-trae-specs-plans-merge 迁移自旧 trae-specs 目录).

依赖来源:
    1. **显式依赖**: frontmatter ``depends_on: [spec-NN]`` 字段 (当前大部分为空)
    2. **隐式依赖**: spec 正文 "spec-XX 完成后" / "前置 spec-XX" / "依赖 spec-XX"
       / "based on spec-XX" / "spec-XX 引入/创建/建立" 等模式

输出:
    - mermaid ``graph TD`` 依赖图 (仅画有依赖关系的 spec, 孤立 spec 单独列出)
    - 同号多版本合并为单节点 (spec-36a/b → spec-36)
    - 同号多版本清单 (WARN, 复用 sync_spec_index.py 检测逻辑)

三种运行模式:
    python scripts/governance/spec_dependency_graph.py           # 生成 / 更新
    python scripts/governance/spec_dependency_graph.py --check   # 仅报告, 不写文件
    python scripts/governance/spec_dependency_graph.py --dry-run # 打印 mermaid 到 stdout
    python scripts/governance/spec_dependency_graph.py --root <path>

设计参考: ``sync_spec_index.py`` + ``n181_retirement_eval.py`` (argparse + Path +
_encoding_safe Windows UTF-8 fix).

Exit codes
----------
    0 - 成功
    2 - 配置/参数错误 (目录不存在等)
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

import argparse  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from collections import defaultdict  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Dict, List, Optional, Set, Tuple  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
SPECS_DIR_DEFAULT = REPO_ROOT_DEFAULT / "docs" / "specs" / "legacy-trae"
OUTPUT_FILE_DEFAULT = REPO_ROOT_DEFAULT / "docs" / "specs" / "dependency-graph.md"

# Frontmatter ``---`` block.
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
SPEC_ID_RE = re.compile(r"^spec_id:\s*(\S+)\s*$", re.MULTILINE)
TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)
COMMIT_RE = re.compile(r"^commit:\s*(\S+)\s*$", re.MULTILINE)
CREATED_RE = re.compile(r"^created:\s*(\S+)\s*$", re.MULTILINE)
# depends_on: [spec-NN, spec-MM]  or  depends_on: []  or  depends_on:\n  - spec-NN
DEPENDS_ON_INLINE_RE = re.compile(r"^depends_on:\s*\[([^\]]*)\]", re.MULTILINE)
DEPENDS_ON_MULTILINE_ITEM_RE = re.compile(r"^\s*-\s*(spec-\S+)", re.MULTILINE)
BLOCKS_INLINE_RE = re.compile(r"^blocks:\s*\[([^\]]*)\]", re.MULTILINE)

# Fallback: extract spec-NN from filename like "2026-07-21-spec83-td321-...md".
FILENAME_SPEC_RE = re.compile(r"-spec(\d+[a-z]?)-", re.IGNORECASE)

# Implicit dependency patterns in body text (after frontmatter).
# Group 1 = spec-NN. Strong signals: "spec-XX 完成后" / "前置 spec-XX".
# Medium signals: "spec-XX 修复/实施/完成" (description of prior spec work).
IMPLICIT_DEP_PATTERNS = [
    # spec-XX 完成后 / spec-XX 之后 / spec-XX 引入 / spec-XX 创建 / spec-XX 建立 / spec-XX 奠定
    re.compile(r"spec-(\d+[a-z]?)\s*(?:完成后|之后|引入|创建|建立|奠定)", re.IGNORECASE),
    # spec-XX 修复 / spec-XX 实施 / spec-XX 完成 (中等信号, 描述前置 spec 工作)
    re.compile(r"spec-(\d+[a-z]?)\s*(?:修复了|实施了|完成了|修复过)", re.IGNORECASE),
    # 前置 spec-XX / 依赖 spec-XX / based on spec-XX / builds on spec-XX
    re.compile(r"(?:前置|依赖|based\s+on|builds\s+on)\s*spec-(\d+[a-z]?)", re.IGNORECASE),
]

# Match any spec-NN reference (for self-reference exclusion).
SPEC_REF_RE = re.compile(r"spec-(\d+[a-z]?)", re.IGNORECASE)


def parse_spec_frontmatter(text: str) -> Dict[str, object]:
    """Parse frontmatter (``---`` block) returning dict of fields.

    Returns empty dict if no frontmatter. Extracts spec_id / title / commit /
    created / depends_on (list) / blocks (list).
    """
    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        return {}
    fm_text = fm_match.group(1)
    result: Dict[str, object] = {}
    m = SPEC_ID_RE.search(fm_text)
    if m:
        result["spec_id"] = m.group(1)
    m = TITLE_RE.search(fm_text)
    if m:
        result["title"] = m.group(1)
    m = COMMIT_RE.search(fm_text)
    if m:
        result["commit"] = m.group(1)
    m = CREATED_RE.search(fm_text)
    if m:
        result["created"] = m.group(1)

    # depends_on: [spec-NN, spec-MM] inline list
    # or depends_on:\n  - spec-NN\n  - spec-MM (multiline)
    deps: List[str] = []
    m = DEPENDS_ON_INLINE_RE.search(fm_text)
    if m:
        inline = m.group(1).strip()
        if inline:
            # SPEC_REF_RE group 1 is digits only; construct full "spec-NN"
            deps = [f"spec-{mm.group(1)}" for mm in SPEC_REF_RE.finditer(inline)]
    else:
        # multiline: depends_on:\n  - spec-NN\n  - spec-MM
        deps = list(DEPENDS_ON_MULTILINE_ITEM_RE.findall(fm_text))
    result["depends_on"] = [d.lower() for d in deps]

    # blocks: [spec-NN] (we parse but don't use for graph direction)
    blocks: List[str] = []
    m = BLOCKS_INLINE_RE.search(fm_text)
    if m:
        inline = m.group(1).strip()
        if inline:
            blocks = [f"spec-{mm.group(1)}" for mm in SPEC_REF_RE.finditer(inline)]
    result["blocks"] = [b.lower() for b in blocks]

    return result


def extract_spec_id_from_filename(filename: str) -> Optional[str]:
    """Fallback: extract ``spec-NN`` from filename like
    ``2026-07-21-spec83-td321-...md`` → ``spec-83``.
    """
    m = FILENAME_SPEC_RE.search(filename)
    if not m:
        return None
    num = m.group(1).lower()
    return f"spec-{num}"


def extract_explicit_deps(frontmatter: Dict[str, object]) -> List[str]:
    """Extract explicit dependencies from frontmatter ``depends_on`` field.

    Returns list of ``spec-NN`` (lowercase). Empty if no depends_on or empty list.
    """
    deps = frontmatter.get("depends_on", [])
    if not isinstance(deps, list):
        return []
    return [d.lower() for d in deps if isinstance(d, str) and d.strip()]


def extract_implicit_deps(body_text: str, self_spec_id: Optional[str]) -> List[str]:
    """Extract implicit dependencies from spec body text.

    Scans for patterns like "spec-XX 完成后" / "前置 spec-XX" / "依赖 spec-XX".
    Excludes self-references (``self_spec_id``).

    Returns de-duplicated list of ``spec-NN`` (lowercase), preserving first-seen order.
    """
    found: List[str] = []
    seen: Set[str] = set()
    for pattern in IMPLICIT_DEP_PATTERNS:
        for m in pattern.finditer(body_text):
            sid = f"spec-{m.group(1).lower()}"
            if self_spec_id and sid == self_spec_id.lower():
                continue  # exclude self-reference
            if sid not in seen:
                seen.add(sid)
                found.append(sid)
    return found


def build_dependency_map(specs_dir: Path) -> Dict[str, Dict[str, object]]:
    """Scan all spec .md files, build dependency map.

    Returns ``{spec_id: {title, commit, created, filename, deps: Set[str], blocks: List[str]}}``.
    ``deps`` is the union of explicit (frontmatter depends_on) and implicit (body
    text pattern) dependencies, with self-reference excluded.

    Same-id multi-version specs are merged: their deps union is taken, title from
    the latest (alphabetically last filename) is used.
    """
    if not specs_dir.is_dir():
        return {}
    dep_map: Dict[str, Dict[str, object]] = {}
    for md_file in sorted(specs_dir.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm = parse_spec_frontmatter(text)
        spec_id = fm.get("spec_id")
        if not spec_id:
            spec_id = extract_spec_id_from_filename(md_file.name)
        if not spec_id:
            continue  # unable to determine spec_id, skip
        spec_id = spec_id.lower()

        # Body = text after frontmatter
        body = text
        fm_match = FRONTMATTER_RE.match(text)
        if fm_match:
            body = text[fm_match.end():]

        explicit = extract_explicit_deps(fm)
        implicit = extract_implicit_deps(body, spec_id)
        deps: Set[str] = set(explicit) | set(implicit)
        deps.discard(spec_id)  # exclude self-reference

        blocks = fm.get("blocks", [])
        if not isinstance(blocks, list):
            blocks = []

        # Merge same-id multi-version: union deps, take latest title/commit/created
        if spec_id in dep_map:
            existing = dep_map[spec_id]
            existing_deps = existing.get("deps", set())
            if not isinstance(existing_deps, set):
                existing_deps = set(existing_deps)
            existing_deps.update(deps)
            existing["deps"] = existing_deps
            existing_blocks = existing.get("blocks", [])
            if not isinstance(existing_blocks, list):
                existing_blocks = []
            for b in blocks:
                if b not in existing_blocks:
                    existing_blocks.append(b)
            existing["blocks"] = existing_blocks
            # Keep latest (alphabetically last filename) title/commit/created
            existing["title"] = fm.get("title", existing.get("title", ""))
            existing["commit"] = fm.get("commit", existing.get("commit", ""))
            existing["created"] = fm.get("created", existing.get("created", ""))
            existing["filename"] = md_file.name
        else:
            dep_map[spec_id] = {
                "title": fm.get("title", ""),
                "commit": fm.get("commit", ""),
                "created": fm.get("created", ""),
                "filename": md_file.name,
                "deps": deps,
                "blocks": blocks,
            }
    return dep_map


def detect_collisions(dep_map: Dict[str, Dict[str, object]]) -> Dict[str, List[str]]:
    """Detect same-id multi-version collisions by checking spec files count vs
    unique spec_ids. Returns dict of spec_id → list of filenames (only groups
    with > 1 file).

    Note: ``build_dependency_map`` already merges same-id specs, so this function
    re-scans the specs_dir to count files per spec_id.
    """
    return {}  # placeholder; collisions reported via sync_spec_index.py


def find_orphans(dep_map: Dict[str, Dict[str, object]]) -> List[str]:
    """Find orphan specs (no deps and not depended on by any other spec).

    Returns sorted list of spec_ids.
    """
    # Build reverse dep set (specs that are depended on by others)
    depended_on: Set[str] = set()
    for info in dep_map.values():
        deps = info.get("deps", set())
        if not isinstance(deps, set):
            deps = set(deps)
        depended_on.update(deps)

    orphans = [
        sid for sid, info in dep_map.items()
        if not info.get("deps") and sid not in depended_on
    ]
    return sorted(orphans, key=_spec_sort_key)


def _spec_sort_key(sid: str) -> Tuple[int, str]:
    """Sort key for spec_id: numeric prefix then full id. ``spec-83`` → (83, "spec-83")."""
    m = re.match(r"spec-(\d+)", sid)
    num = int(m.group(1)) if m else 0
    return (num, sid)


def render_mermaid(dep_map: Dict[str, Dict[str, object]]) -> str:
    """Render mermaid ``graph TD`` dependency graph.

    Only specs with deps or depended-on specs are included (orphans excluded to
    keep graph readable). Edges: ``spec-NN --> spec-MM`` means NN depends on MM
    (MM should be done first).

    Node label: ``spec-NN[spec-NN<br/>title-truncated]``.
    """
    # Determine which specs to include (non-orphan)
    depended_on: Set[str] = set()
    for info in dep_map.values():
        deps = info.get("deps", set())
        if not isinstance(deps, set):
            deps = set(deps)
        depended_on.update(deps)
    included = {
        sid for sid, info in dep_map.items()
        if info.get("deps") or sid in depended_on
    }

    lines: List[str] = ["```mermaid", "graph TD"]
    # Nodes (sorted by spec_id)
    for sid in sorted(included, key=_spec_sort_key):
        info = dep_map[sid]
        title = info.get("title", "")
        if not isinstance(title, str):
            title = str(title)
        # Truncate title for readability, escape quotes
        title_short = title[:50].replace('"', "'")
        # mermaid node id: replace - with _ (mermaid id can't have -)
        node_id = sid.replace("-", "_")
        lines.append(f'    {node_id}["{sid}<br/>{title_short}"]')

    # Edges (sorted by source then target)
    edges: List[Tuple[str, str]] = []
    for sid in sorted(included, key=_spec_sort_key):
        info = dep_map[sid]
        deps = info.get("deps", set())
        if not isinstance(deps, set):
            deps = set(deps)
        for dep in deps:
            if dep in dep_map:  # only edge if dep exists in our map
                edges.append((sid, dep))
    for src, tgt in sorted(edges, key=lambda e: (_spec_sort_key(e[0]), _spec_sort_key(e[1]))):
        src_id = src.replace("-", "_")
        tgt_id = tgt.replace("-", "_")
        lines.append(f"    {src_id} --> {tgt_id}")

    lines.append("```")
    return "\n".join(lines)


def render_markdown(
    dep_map: Dict[str, Dict[str, object]],
    mermaid: str,
    orphans: List[str],
    output_file: Path,
) -> str:
    """Render full markdown content for ``docs/specs/dependency-graph.md``."""
    total_specs = len(dep_map)
    # Count edges (deps that exist in map)
    edge_count = 0
    for info in dep_map.values():
        deps = info.get("deps", set())
        if not isinstance(deps, set):
            deps = set(deps)
        edge_count += sum(1 for d in deps if d in dep_map)
    orphan_count = len(orphans)
    coverage_pct = ((total_specs - orphan_count) / total_specs * 100) if total_specs else 0

    lines: List[str] = []
    lines.append("---")
    lines.append("date: 2026-07-22")
    lines.append("source: docs/specs/legacy-trae/*.md")
    lines.append("generated_by: scripts/governance/spec_dependency_graph.py")
    lines.append("td: TD-326")
    lines.append("spec: spec-89")
    lines.append("---")
    lines.append("")
    lines.append("# Spec 依赖关系图 (auto-generated by spec_dependency_graph.py)")
    lines.append("")
    lines.append(f"> 总计 **{total_specs}** 个 spec | **{edge_count}** 条依赖边 | "
                 f"**{orphan_count}** 个孤立 spec | 覆盖率 **{coverage_pct:.1f}%**")
    lines.append(f"> 最后生成: 由 `scripts/governance/spec_dependency_graph.py` 自动生成 (TD-326 spec-89).")
    lines.append(f"> 依赖来源: frontmatter `depends_on` 字段 + 正文 `spec-XX 完成后/之后/引入/创建/建立` + `前置/依赖 spec-XX` 模式提取.")
    lines.append("")
    lines.append("## 依赖图 (mermaid)")
    lines.append("")
    lines.append(mermaid)
    lines.append("")
    lines.append("## 孤立 spec 清单 (无依赖关系)")
    lines.append("")
    if orphans:
        lines.append(f"> {orphan_count} 个 spec 无显式/隐式依赖关系, 未画入上图.")
        lines.append("")
        for sid in orphans:
            info = dep_map[sid]
            title = info.get("title", "")
            if not isinstance(title, str):
                title = str(title)
            lines.append(f"- `{sid}` — {title}")
    else:
        lines.append("✅ 无孤立 spec.")
    lines.append("")
    lines.append("## 同号多版本 (历史遗留, TD-322 wontfix)")
    lines.append("")
    lines.append("> 同号多版本 (spec-36/38/39/41/42/43/44/45 各 2 个) 已在依赖图中合并为单节点.")
    lines.append("> 详细清单见 `.ai-memory/ref/spec-index.md` ⚠️ 同号多版本冲突段.")
    lines.append("> 引用时建议用文件全名消歧, 或参考 commit hash 区分.")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="TD-326 spec-89: spec 流程可视化依赖图",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check (report stats, do not write output file)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print mermaid to stdout, do not write files",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    specs_dir = repo_root / "docs" / "specs" / "legacy-trae"
    output_file = repo_root / "docs" / "specs" / "dependency-graph.md"

    if not specs_dir.is_dir():
        print(f"ERROR: specs dir not found: {specs_dir}", file=sys.stderr)
        return 2

    dep_map = build_dependency_map(specs_dir)
    if not dep_map:
        print(f"ERROR: no spec files found in {specs_dir}", file=sys.stderr)
        return 2

    orphans = find_orphans(dep_map)
    mermaid = render_mermaid(dep_map)

    total_specs = len(dep_map)
    edge_count = sum(
        sum(1 for d in info.get("deps", set()) if d in dep_map)
        for info in dep_map.values()
    )
    orphan_count = len(orphans)
    coverage_pct = ((total_specs - orphan_count) / total_specs * 100) if total_specs else 0

    print(f"[spec_dependency_graph] scanned {total_specs} spec files in {specs_dir}")
    print(f"[spec_dependency_graph] edges: {edge_count} | orphans: {orphan_count} | "
          f"coverage: {coverage_pct:.1f}%")

    if args.dry_run:
        print("[spec_dependency_graph] --dry-run: mermaid output:")
        print(mermaid)
        return 0

    if args.check:
        print("[spec_dependency_graph] --check mode: report only (exit 0)")
        return 0

    content = render_markdown(dep_map, mermaid, orphans, output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(content, encoding="utf-8")
    print(f"[spec_dependency_graph] ✅ wrote {output_file} ({len(content)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
