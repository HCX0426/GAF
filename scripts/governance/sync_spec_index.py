"""sync_spec_index.py — TD-322 (spec-84 方案 B): spec_id 索引生成 + 同号多版本检测.

扫描 ``docs/specs/legacy-trae/*.md`` 的 frontmatter ``spec_id:`` 字段 (fallback 从文件名
(spec-2026-07-26-trae-specs-plans-merge 迁移自旧 trae-specs 目录)
提取 ``spec-NN``), 生成 ``.ai-memory/ref/spec-index.md`` 索引表 (spec_id | 文件名 |
标题 | commit | 日期), 并检测同号多版本冲突 (WARN 不阻塞).

设计目的 (TD-322 wontfix mitigation):
    - 历史同号多版本 (spec-36/38/39/41/42/43/44/45 各 2 个) 保留不动
    - 索引脚本提供 spec-NN → 文件全名消歧查询
    - 配合 ``check_spec_id_collision.py`` pre-commit hook 防止新增冲突

两种运行模式:
    python scripts/governance/sync_spec_index.py           # 同步索引 (默认)
    python scripts/governance/sync_spec_index.py --check   # 只检查, 同号多版本 WARN (exit 0)
    python scripts/governance/sync_spec_index.py --dry-run # 只报告不写文件

Exit codes
----------
    0 - 成功 (同步完成, 或 --check 模式下计数一致/有 WARN 也 exit 0)
    2 - 配置/参数错误 (目录不存在等)

设计参考: ``scripts/governance/sync_tech_debt_counts.py`` (argparse + Path +
_encoding_safe Windows UTF-8 fix).
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
from typing import Dict, List, Optional, Tuple  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
SPECS_DIR_DEFAULT = REPO_ROOT_DEFAULT / "docs" / "specs" / "legacy-trae"
INDEX_FILE_DEFAULT = REPO_ROOT_DEFAULT / ".ai-memory" / "ref" / "spec-index.md"

# Front matter ``spec_id: spec-NN`` (or ``spec-NNa/b``).
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
SPEC_ID_RE = re.compile(r"^spec_id:\s*(\S+)\s*$", re.MULTILINE)
TITLE_RE = re.compile(r"^title:\s*(.+?)\s*$", re.MULTILINE)
COMMIT_RE = re.compile(r"^commit:\s*(\S+)\s*$", re.MULTILINE)
CREATED_RE = re.compile(r"^created:\s*(\S+)\s*$", re.MULTILINE)

# Fallback: extract spec-NN from filename like "2026-07-21-spec83-td321-...md".
FILENAME_SPEC_RE = re.compile(r"-spec(\d+[a-z]?)-", re.IGNORECASE)


def parse_frontmatter(text: str) -> Dict[str, str]:
    """Parse frontmatter (``---`` block) returning dict of fields.

    Returns empty dict if no frontmatter. Only extracts spec_id / title /
    commit / created (the fields we care about).
    """
    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        return {}
    fm_text = fm_match.group(1)
    result: Dict[str, str] = {}
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
    return result


def extract_spec_id_from_filename(filename: str) -> Optional[str]:
    """Fallback: extract ``spec-NN`` from filename like
    ``2026-07-21-spec83-td321-...md`` → ``spec-83``.
    """
    m = FILENAME_SPEC_RE.search(filename)
    if not m:
        return None
    num = m.group(1).lower()
    # Normalize: "83" → "83", "59f" → "59f"
    return f"spec-{num}"


def scan_specs(specs_dir: Path) -> List[Dict[str, str]]:
    """Scan all .md files in specs_dir, return list of spec info dicts.

    Each dict has keys: spec_id / filename / title / commit / created / source
    where source is "frontmatter" or "filename".
    """
    if not specs_dir.is_dir():
        return []
    results: List[Dict[str, str]] = []
    for md_file in sorted(specs_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        spec_id = fm.get("spec_id")
        source = "frontmatter"
        if not spec_id:
            spec_id = extract_spec_id_from_filename(md_file.name)
            source = "filename"
        if not spec_id:
            continue  # unable to determine spec_id, skip
        results.append({
            "spec_id": spec_id,
            "filename": md_file.name,
            "title": fm.get("title", ""),
            "commit": fm.get("commit", ""),
            "created": fm.get("created", ""),
            "source": source,
        })
    return results


def detect_collisions(specs: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    """Group specs by spec_id, return dict of spec_id → list of specs (only
    groups with > 1 entry, i.e. collisions).
    """
    by_id: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for s in specs:
        by_id[s["spec_id"]].append(s)
    return {sid: lst for sid, lst in by_id.items() if len(lst) > 1}


def render_index(specs: List[Dict[str, str]]) -> str:
    """Render the spec-index.md content as a markdown table."""
    lines: List[str] = []
    lines.append("# Spec Index (auto-generated by sync_spec_index.py)")
    lines.append("")
    lines.append(f"> 总计 {len(specs)} 个 spec 文件. 同号多版本会标注 ⚠️.")
    lines.append(f"> 最后生成: 由 `sync_spec_index.py` 自动同步.")
    lines.append("")
    lines.append("| spec_id | 文件名 | 标题 | commit | 创建日期 | 来源 |")
    lines.append("|:---:|---|---|:---:|:---:|:---:|")
    # Sort by spec_id (numeric prefix aware) then filename
    def _key(s: Dict[str, str]) -> Tuple[str, str]:
        sid = s["spec_id"]
        # Extract numeric part for sort: "spec-83" → 83, "spec-59f" → 59
        m = re.match(r"spec-(\d+)", sid)
        num = int(m.group(1)) if m else 0
        return (f"{num:04d}", s["filename"])
    for s in sorted(specs, key=_key):
        sid = s["spec_id"]
        marker = ""
        # Check if this spec_id has collisions
        # (we don't have direct access here; caller can mark)
        commit = s["commit"] if s["commit"] else "-"
        created = s["created"] if s["created"] else "-"
        title = s["title"][:60] if s["title"] else "-"
        source = s["source"]
        lines.append(f"| {sid}{marker} | {s['filename']} | {title} | {commit} | {created} | {source} |")
    return "\n".join(lines) + "\n"


def render_collisions_section(collisions: Dict[str, List[Dict[str, str]]]) -> str:
    """Render a markdown section listing collisions (WARN)."""
    if not collisions:
        return ""
    lines: List[str] = []
    lines.append("")
    lines.append("## ⚠️ 同号多版本冲突 (历史遗留, TD-322 wontfix)")
    lines.append("")
    lines.append(f"> 检测到 {len(collisions)} 组同号多版本 (共 {sum(len(v) for v in collisions.values())} 文件).")
    lines.append("> 引用时建议用文件全名消歧, 或参考 commit hash 区分.")
    lines.append("")
    for sid, lst in sorted(collisions.items()):
        lines.append(f"### {sid} ({len(lst)} 文件)")
        lines.append("")
        lines.append("| 文件名 | commit | 创建日期 |")
        lines.append("|---|:---:|:---:|")
        for s in lst:
            commit = s["commit"] if s["commit"] else "-"
            created = s["created"] if s["created"] else "-"
            lines.append(f"| {s['filename']} | {commit} | {created} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="TD-322 (spec-84 方案 B): spec_id 索引生成 + 同号多版本检测",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check (report collisions as WARN, do not write index file)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be written, but do not write files",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    specs_dir = repo_root / "docs" / "specs" / "legacy-trae"
    index_file = repo_root / ".ai-memory" / "ref" / "spec-index.md"

    if not specs_dir.is_dir():
        print(f"ERROR: specs dir not found: {specs_dir}", file=sys.stderr)
        return 2

    specs = scan_specs(specs_dir)
    if not specs:
        print(f"ERROR: no spec files found in {specs_dir}", file=sys.stderr)
        return 2

    collisions = detect_collisions(specs)

    print(f"[sync_spec_index] scanned {len(specs)} spec files in {specs_dir}")
    if collisions:
        total_collisions = sum(len(v) for v in collisions.values())
        print(f"[sync_spec_index] ⚠️ {len(collisions)} 同号多版本组 ({total_collisions} 文件):")
        for sid, lst in sorted(collisions.items()):
            print(f"  - {sid}: {len(lst)} 文件")
            for s in lst:
                print(f"      · {s['filename']}")
    else:
        print(f"[sync_spec_index] ✅ 无同号多版本冲突")

    if args.check:
        # --check: WARN only, always exit 0 (collisions are advisory, not blocking)
        print("[sync_spec_index] --check mode: WARN only (exit 0)")
        return 0

    # Generate index content
    content = render_index(specs)
    if collisions:
        content += render_collisions_section(collisions)

    if args.dry_run:
        print("[sync_spec_index] --dry-run: would write index file:")
        print(f"  target: {index_file}")
        print(f"  size: {len(content)} bytes, {content.count(chr(10))} lines")
        return 0

    # Write index file
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(content, encoding="utf-8")
    print(f"[sync_spec_index] ✅ wrote {index_file} ({len(content)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
