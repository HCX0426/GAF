"""sync_docs_index.py — GAF docs/ 索引生成器 (v9.0).

Scans all Markdown files under GAF/docs/ and generates
`.ai-memory/meta/docs-index.md` based on their YAML frontmatter
(summary, applies_to, key_decisions, last_updated).

This is the bridge between human-readable design docs and the
AI's L2 hard-load knowledge. Without this index, AI doesn't know
what design docs exist or when they're relevant.

v9.0 新增（spec §9.1 脚本生成为主策略）:
- `module` 字段：从 docs/ 相对路径自动推导（如 `business.tasks` / `architecture.desktop`）
- `applies_to_code_paths` 字段：按内置 `_MODULE_CODE_PATHS` 映射表填充（spec §9.1 实测修正后）
- `maintainer` 字段：固定 `ai`（所有 docs/ 文档）
- `doc_last_updated` 字段：从 `git log -1 --format=%ci -- <file>` 获取，mtime 兜底
- 源文档 frontmatter 不动，新增字段全部由脚本生成到 docs-index.md

Usage:
    python sync_docs_index.py                 # generate index
    python sync_docs_index.py --check         # CI mode: fail if outdated
    python sync_docs_index.py --check --strict  # also fail on missing frontmatter
    python sync_docs_index.py --stale-days 90 # override stale threshold (default 90)
    python sync_docs_index.py --root <path>   # operate on a different repo

Exit codes:
    0 — OK (or no docs found)
    1 — Stale or missing frontmatter (in --check mode)
    2 — Configuration error

Frontmatter contract (see api-contract.md style):

    ---
    summary: 一句话说明 (≤ 80 字)
    applies_to: [tag1, tag2, ...]
    key_decisions:
      - 决策1
      - 决策2
    last_updated: 2026-06-15
    ---

    Required fields: summary, applies_to, last_updated
    Optional fields: key_decisions

    脚本自动生成字段（不需要源文档写）: module, applies_to_code_paths, maintainer, doc_last_updated
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
import json
import re
import sys
from pathlib import Path

import _encoding_safe  # noqa: F401  (must be first; reconfigures stdout to UTF-8)
from frontmatter import parse_front_matter

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT_DEFAULT / "docs"
INDEX_OUTPUT = REPO_ROOT_DEFAULT / ".ai-memory" / "meta" / "docs-index.md"
SKILL_MD_PATH = REPO_ROOT_DEFAULT / ".skills" / "skills" / "gaf-knowledge-base" / "SKILL.md"

REQUIRED_FIELDS = ("summary", "applies_to", "last_updated")
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

# Pattern: "<N> 份" used 3 times in SKILL.md (TD-165 single source of truth)
# Match either `docs/` 42 份 or `GAF/docs/`（42 份，...  formats
_DOCS_COUNT_PATTERNS = (
    re.compile(r"(`docs/`\s*)(\d+)(\s*份)"),
    re.compile(r"(`GAF/docs/`\（)(\d+)(\s*份)"),
)


def _is_valid_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value))


def _parse_date(s: str) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _scan_docs(docs_dir: Path) -> list[tuple[Path, dict[str, object], bool]]:
    """Scan all .md under docs_dir.

    Returns list of (path, frontmatter, has_frontmatter).
    """
    if not docs_dir.exists():
        return []
    results: list[tuple[Path, dict[str, object], bool]] = []
    for f in sorted(docs_dir.rglob("*.md")):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, _, has_fm = parse_front_matter(text)
        results.append((f, fm, has_fm))
    return results


def _group_by_tag(
    entries: list[tuple[Path, dict[str, object]]]
) -> dict[str, list[tuple[Path, dict[str, object]]]]:
    """Group docs by first tag in `applies_to`.

    `applies_to` may be a list; we use the first element as the
    primary group, then "其他" for docs without applies_to.
    """
    groups: dict[str, list[tuple[Path, dict[str, object]]]] = {}
    for path, fm in entries:
        applies = fm.get("applies_to", [])
        tag = str(applies[0]) if isinstance(applies, list) and applies else "其他"
        groups.setdefault(tag, []).append((path, fm))
    return groups


def _relative_to_repo(path: Path, repo_root: Path) -> str:
    """Make path relative to repo root, using forward slashes."""
    try:
        return str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(path)


# === P0 新增：脚本生成为主策略字段推导 (spec §9.1) ===

# 模块 → 代码路径映射表（spec §9.1 实测修正后）
_MODULE_CODE_PATHS: dict[str, list[str]] = {
    # business 9 模块
    "business.workspace": [],
    "business.game-profile": [
        "backend/gamestate/**",
        "frontend/src/pages/GameProfiles/**",
    ],
    "business.tasks": [
        "backend/tasks/**",
        "frontend/src/pages/Tasks/**",
    ],
    "business.devices": [
        "backend/devices/**",
        "agent/src/devices/**",
    ],
    "business.resources": [
        "backend/resources/**",
        "frontend/src/pages/Resources/**",
    ],
    "business.accounts": [
        "backend/accounts/**",
    ],
    "business.ops": [
        "backend/monitors/**",
        "backend/notifications/**",
    ],
    "business.ai": [
        "backend/gaf_ai/**",
        "backend/skills/**",
    ],
    "business.system": [],
    # architecture 5 层 + 横切
    "architecture.frontend": [
        "frontend/src/**",
    ],
    "architecture.backend": [
        "backend/config/**",
        "backend/gaf_core/**",
    ],
    "architecture.agent": [
        "agent/src/**",
    ],
    "architecture.desktop": [
        "desktop/**",
    ],
    "architecture.cross-cutting": [
        "backend/protocol/**",
        "backend/tracing/**",
    ],
    # architecture 根文档（overview / optimal-solution / features-overview）
    "architecture": [],
}


def _derive_module_from_path(rel_path: str) -> str | None:
    """从 docs/ 相对路径推导 module 字段（spec §9.1）。

    推导规则:
    - docs/business/<sub>/<file>.md → business.<sub>
    - docs/business/<sub>/<sub2>/<file>.md → business.<sub>（取第一级子目录）
    - docs/architecture/<sub>/<file>.md → architecture.<sub>
    - docs/architecture/<sub>/<sub2>/<file>.md → architecture.<sub>（取第一级子目录）
    - docs/architecture/<file>.md → architecture（架构根文档，文件直接在 architecture/ 下）
    - 其他顶层目录（analysis/standards/tech-debt/archive/specs/plans/health）→ None（不生成 module）
    """
    if rel_path.startswith("docs/business/"):
        parts = rel_path.split("/")
        # parts[0]='docs', parts[1]='business', parts[2]='<sub>'
        # 文件直接在 business/<sub>/ 下：len==4 (docs/business/<sub>/<file>.md)
        # 文件在更深层：len>4，仍取 parts[2] 作为 sub
        if len(parts) >= 4:
            return f"business.{parts[2]}"
        return None  # docs/business/<file>.md 或 docs/business/（不应出现）
    if rel_path.startswith("docs/architecture/"):
        parts = rel_path.split("/")
        # parts[0]='docs', parts[1]='architecture', parts[2]='<sub>' or '<file>.md'
        # 文件直接在 architecture/ 下：len==3 (docs/architecture/<file>.md) → 架构根文档
        if len(parts) == 3:
            return "architecture"
        # 文件在 architecture/<sub>/ 下：len>=4 → architecture.<sub>
        if len(parts) >= 4:
            return f"architecture.{parts[2]}"
        return None
    return None


def _get_applies_to_code_paths(module: str | None) -> list[str]:
    """按模块查映射表返回 applies_to_code_paths（spec §9.1）。"""
    if not module:
        return []
    return _MODULE_CODE_PATHS.get(module, [])


def _get_doc_last_updated_from_git(path: Path, repo_root: Path) -> str | None:
    """从 git log 获取文档最近修改日期（spec §9.1）。

    返回 YYYY-MM-DD 格式；若 git log 无记录则返回 None（mtime 兜底在调用方处理）。
    """
    import subprocess
    rel = _relative_to_repo(path, repo_root)
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci", "--", rel],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # %ci 格式: 2026-07-25 10:30:00 +0800
            iso = result.stdout.strip().split(" ")[0]
            return iso
    except (subprocess.SubprocessError, OSError):
        pass
    return None


# === P0 新增结束 ===


def _format_index(
    entries: list[tuple[Path, dict[str, object]]],
    repo_root: Path,
    stale_days: int,
    missing_fm: list[Path],
) -> str:
    """Format the index Markdown body."""
    today = _dt.date.today()
    lines: list[str] = []
    lines.append("---")
    lines.append("maintainer: derived-manual")
    lines.append("source: docs/**/*.md (YAML frontmatter)")
    lines.append("load_when: [新功能, Bug修复, 重构]")
    lines.append("priority: high")
    lines.append("symptom: [docs-index, design-discovery, ai-navigation]")
    lines.append("solution: AI 任务开工 L2 硬加载,按 applies_to 决定是否查具体文档")
    lines.append("related_files:")
    lines.append("  - .ai-memory/meta/failure-modes.md")
    lines.append("  - .skills/skills/gaf-orchestrator/SKILL.md")
    lines.append("created_by: AI")
    lines.append(f"generated: {today.isoformat()}")
    lines.append("---")
    lines.append("")
    lines.append("# GAF docs/ 设计文档索引（auto-generated）")
    lines.append("")
    lines.append(
        "> **强制**：AI 任务开工 L2 hard load 必须读本文件。\n"
        "> 按 `applies_to` 决定是否需要查具体设计文档原文。\n"
        "> 索引由 `python scripts/bootstrap/sync_docs_index.py` 自动生成。\n"
        "> 文件 frontmatter 改动后必须重跑脚本更新本索引。"
    )
    lines.append("")
    lines.append(f"**生成时间**：{today.isoformat()}  ")
    lines.append(f"**文档总数**：{len(entries)}  ")
    lines.append(f"**过期阈值**：{stale_days} 天")
    lines.append("")

    # Stats
    stale: list[tuple[Path, int]] = []
    for path, fm in entries:
        lu = fm.get("last_updated", "")
        if isinstance(lu, str):
            d = _parse_date(lu)
            if d:
                age = (today - d).days
                if age > stale_days:
                    stale.append((path, age))

    if stale:
        lines.append(f"## ⚠️ 过期文档（> {stale_days} 天未更新）")
        lines.append("")
        for path, age in sorted(stale, key=lambda x: -x[1]):
            rel = _relative_to_repo(path, repo_root)
            lines.append(f"- `{rel}` — {age} 天前")
        lines.append("")
    else:
        lines.append("## ✅ 全部文档新鲜（无过期）")
        lines.append("")

    if missing_fm:
        lines.append("## ❌ 缺少 frontmatter（必须修复）")
        lines.append("")
        for path in missing_fm:
            rel = _relative_to_repo(path, repo_root)
            lines.append(f"- `{rel}`")
        lines.append("")

    # Group by primary tag
    groups = _group_by_tag(entries)
    lines.append("## 文档列表（按 applies_to 分组）")
    lines.append("")
    for tag in sorted(groups.keys()):
        items = groups[tag]
        lines.append(f"### {tag}（{len(items)}）")
        lines.append("")
        for path, fm in items:
            rel = _relative_to_repo(path, repo_root)
            summary = fm.get("summary", "(无 summary)")
            lu = fm.get("last_updated", "?")
            decisions = fm.get("key_decisions", [])
            # P0 新增：脚本生成为主策略字段（spec §9.1）
            module = _derive_module_from_path(rel)
            code_paths = _get_applies_to_code_paths(module)
            doc_last_updated = _get_doc_last_updated_from_git(path, repo_root)
            if not doc_last_updated:
                # mtime 兜底
                doc_last_updated = _dt.date.fromtimestamp(
                    path.stat().st_mtime
                ).isoformat()
            line = f"- [{rel}]({rel}) — {summary}"
            if lu and lu != "?":
                line += f" _(updated {lu})_"
            lines.append(line)
            # 输出 P0 新增字段
            if module:
                lines.append(f"  - `module`: `{module}`")
            if code_paths:
                paths_str = ", ".join(f"`{p}`" for p in code_paths)
                lines.append(f"  - `applies_to_code_paths`: {paths_str}")
            elif module:
                lines.append(f"  - `applies_to_code_paths`: `[]` (待新文档填入)")
            lines.append(f"  - `maintainer`: `ai`")
            lines.append(f"  - `doc_last_updated`: `{doc_last_updated}`")
            if isinstance(decisions, list) and decisions:
                for d in decisions[:3]:  # show top 3
                    lines.append(f"  - {d}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 维护说明")
    lines.append("")
    lines.append("- 修改任何 docs/ 文件 → 更新其 `last_updated` + 重跑本脚本")
    lines.append("- 新建 docs/ 文件 → 加 frontmatter + 重跑本脚本")
    lines.append("- pre-commit hook: docs/ 改动 → 强制本索引更新")
    lines.append("- gaf_init.sh L1: 警告过期文档 (>90 天)")
    lines.append("")
    return "\n".join(lines)


def _sync_skill_md_docs_count(repo_root: Path, docs_count: int, *, dry_run: bool = False) -> bool:
    """TD-165 — sync `docs/` count in gaf-knowledge-base/SKILL.md.

    Replaces all hardcoded "<N> 份" patterns (3 occurrences) with the actual
    docs count from docs-index.md. Returns True if SKILL.md was modified.
    """
    skill_path = repo_root / ".skills" / "skills" / "gaf-knowledge-base" / "SKILL.md"
    if not skill_path.is_file():
        return False
    text = skill_path.read_text(encoding="utf-8")
    new_text = text
    for pattern in _DOCS_COUNT_PATTERNS:
        new_text = pattern.sub(rf"\g<1>{docs_count}\g<3>", new_text)
    if new_text == text:
        return False
    if not dry_run:
        skill_path.write_text(new_text, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# TD-332/TD-344 (spec-2026-07-26-governance-batch-perf-cache Wave 4):
# mtime-based incremental cache for --check mode.
#
# sync_docs_index --check scans docs/**/*.md (7.36s on GAF repo) to compute
# stale_count + missing_fm. If no .md file changed since the last successful
# check AND the date is the same (stale check depends on today's date), the
# output is guaranteed identical → replay cached output and exit code.
# ---------------------------------------------------------------------------

DOCS_CACHE_FILE_NAME = ".docs-index-cache.json"


def _docs_cache_path(repo_root: Path) -> Path:
    """Return path to .ai-memory/.docs-index-cache.json."""
    return repo_root / ".ai-memory" / DOCS_CACHE_FILE_NAME


def _build_docs_manifest(docs_dir: Path) -> dict[str, int]:
    """Build {relative_path: st_mtime_ns} for all .md files under docs/.

    Excludes ``docs/reference/performance-baseline.md`` (auto-generated by
    governance-batch on every commit, TD-347). Including it would invalidate
    the docs-index cache on every governance-batch run, forcing a 2.8s full
    scan each time. The file is auto-appended and does not affect docs-index
    stale checks.
    """
    manifest: dict[str, int] = {}
    if not docs_dir.exists():
        return manifest
    for path in sorted(docs_dir.rglob("*.md")):
        # TD-347: 排除 performance-baseline.md (auto-generated, 触发 cache 永久失效)
        if path.name == "performance-baseline.md" and path.parent.name == "reference":
            continue
        if path.is_file():
            try:
                rel = str(path.relative_to(docs_dir)).replace("\\", "/")
                manifest[rel] = path.stat().st_mtime_ns
            except OSError:
                continue
    return manifest


def _load_docs_cache(repo_root: Path) -> dict | None:
    """Load docs-index cache. Returns None if missing/corrupt."""
    path = _docs_cache_path(repo_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _write_docs_cache(
    repo_root: Path,
    manifest: dict[str, int],
    last_run_date: str,
    last_exit_code: int,
    last_output: str,
) -> None:
    """Write docs-index cache after a successful --check run."""
    path = _docs_cache_path(repo_root)
    cache = {
        "manifest": manifest,
        "last_run_date": last_run_date,
        "last_exit_code": last_exit_code,
        "last_output": last_output,
        "version": 1,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _check_docs_cache_valid(
    repo_root: Path,
    docs_dir: Path,
    current_date: str,
) -> tuple[bool, str, int]:
    """Check if docs-index cache is valid.

    Returns (cache_hit, cached_output, cached_exit_code).
    Cache is valid only if:
    - cache file exists
    - manifest matches (no .md file changed)
    - last_run_date == current_date (stale check depends on today's date)
    """
    cache = _load_docs_cache(repo_root)
    if cache is None:
        return False, "", 0
    cached_manifest = cache.get("manifest")
    if not isinstance(cached_manifest, dict):
        return False, "", 0
    cached_date = cache.get("last_run_date")
    if not isinstance(cached_date, str) or cached_date != current_date:
        return False, "", 0
    current_manifest = _build_docs_manifest(docs_dir)
    if cached_manifest != current_manifest:
        return False, "", 0
    cached_output = cache.get("last_output", "")
    cached_exit_code = cache.get("last_exit_code", 0)
    if not isinstance(cached_output, str) or not isinstance(cached_exit_code, int):
        return False, "", 0
    return True, cached_output, cached_exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF docs/ 索引生成器 (v9.0)"
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="Path to the GAF repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=90,
        help="Days threshold for stale docs (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI mode: report issues but don't write index",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="In --check mode, also fail on missing frontmatter",
    )
    parser.add_argument(
        "--output",
        default=str(INDEX_OUTPUT),
        help="Index output path (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    docs_dir = repo_root / "docs"
    output = Path(args.output).resolve()

    if not docs_dir.exists():
        print(f"❌ docs/ dir missing: {docs_dir}")
        return 2

    # TD-332/TD-344 Wave 4: mtime-based cache for --check mode.
    # If docs/**/*.md unchanged since last successful check AND same date,
    # replay cached output + exit code (skips 7.36s full scan).
    if args.check and not args.strict:
        today_str = _dt.date.today().isoformat()
        cache_hit, cached_output, cached_exit_code = _check_docs_cache_valid(
            repo_root, docs_dir, today_str
        )
        if cache_hit:
            if cached_output:
                print(cached_output)
            return cached_exit_code

    scanned = _scan_docs(docs_dir)
    if not scanned:
        print(f"ℹ️  no markdown found under {docs_dir}")
        return 0

    entries: list[tuple[Path, dict[str, object]]] = []
    missing_fm: list[Path] = []
    for path, fm, has_fm in scanned:
        if not has_fm:
            missing_fm.append(path)
            continue
        # Validate required fields
        bad = [f for f in REQUIRED_FIELDS if f not in fm or fm[f] in ("", [])]
        if bad:
            print(f"⚠️  {path.name}: missing fields {bad}")
            missing_fm.append(path)
            continue
        if "last_updated" in fm and not _is_valid_date(fm["last_updated"]):
            print(f"⚠️  {path.name}: invalid last_updated {fm['last_updated']!r}")
            missing_fm.append(path)
            continue
        entries.append((path, fm))

    body = _format_index(entries, repo_root, args.stale_days, missing_fm)

    today = _dt.date.today()
    stale_count = sum(
        1 for _, fm in entries
        if isinstance(fm.get("last_updated"), str)
        and (today - (_parse_date(fm["last_updated"]) or today)).days > args.stale_days
    )

    if args.check:
        ok = True
        check_messages: list[str] = []
        if stale_count > 0:
            msg = f"❌ {stale_count} stale doc(s) (> {args.stale_days} days)"
            print(msg)
            check_messages.append(msg)
            ok = False
        if args.strict and missing_fm:
            msg = f"❌ {len(missing_fm)} doc(s) missing/invalid frontmatter"
            print(msg)
            check_messages.append(msg)
            ok = False
        if ok:
            msg = f"✅ docs-index check passed ({len(entries)} docs, {stale_count} stale)"
            print(msg)
            check_messages.append(msg)
            # TD-332/TD-344 Wave 4: write cache after successful non-strict check.
            # Only cache non-strict mode (strict mode also checks missing_fm which
            # is already captured in the cache validity via manifest).
            if not args.strict:
                manifest = _build_docs_manifest(docs_dir)
                _write_docs_cache(
                    repo_root,
                    manifest,
                    today.isoformat(),
                    0,
                    "\n".join(check_messages),
                )
            return 0
        # Cache FAIL result too (so subsequent runs also hit cache if files unchanged)
        if not args.strict:
            manifest = _build_docs_manifest(docs_dir)
            _write_docs_cache(
                repo_root,
                manifest,
                today.isoformat(),
                1,
                "\n".join(check_messages),
            )
        return 1

    # Write index
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")
    # TD-165 — sync docs count to gaf-knowledge-base/SKILL.md
    skill_synced = _sync_skill_md_docs_count(repo_root, len(entries))
    print(
        f"✅ docs-index generated: {output}\n"
        f"   {len(entries)} docs indexed, {stale_count} stale, "
        f"{len(missing_fm)} missing frontmatter"
        + (f", SKILL.md docs count synced" if skill_synced else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
