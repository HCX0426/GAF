"""check_doc_path_drift.py - 文档路径漂移检测 (spec §7.3, P2 阶段).

在 ``git commit`` 时扫描全仓库文件, 检测是否包含 docs/.ai-memory 重构
(spec 2026-07-25-docs-ai-memory-restructure) 后已废弃的旧路径引用.
任一命中 → exit 1 阻断 commit (除非 ``--no-fail`` 或文件在白名单中).

设计原则 (spec §7)
------------------
- 旧路径零兼容: 不保留、不软链、不重定向
- pre-commit hook 永久约束, 防止 AI/人类误回退
- 白名单豁免: 历史记录 (.git/) + 上下文承载体 (docs/archive/spec-context/)
  + 早期归档 (.ai-memory/lessons/archived-early/) + evidence 归档目录

FORBIDDEN_PATTERNS 分类
-----------------------
1. P0 旧路径 (docs/general/ + docs/superpowers/ + docs/governance/ + docs/specs/dependency-graph.md)
2. P1 旧路径 (evidence/<date>-<task>/ 直接 + lessons/<...>-n<N>-<slug>.md 旧命名)
3. P2 旧路径 (.ai-memory/ 根目录 7 个文件, 已迁到 ref/)

TD-348 mtime cache (2026-07-26)
-------------------------------
全仓 os.walk + 逐文件 read_text 在文件未变化时是纯浪费. 引入 mtime-based
manifest cache: cache hit 时跳过整个扫描流程, 直接复用上次结果 (exit code +
简化输出). 与 sync_ai_memory.py / sync_docs_index.py 同思路 (TD-332/TD-344).

Usage
-----
    # 注册在 gaf_governance_batch.py CHECKS 第 13 项:
    ("hooks.check_doc_path_drift", "main", [], "doc-path-drift"),

    # 手动运行:
    python scripts/hooks/check_doc_path_drift.py
    python scripts/hooks/check_doc_path_drift.py --no-fail   # warn only
    python scripts/hooks/check_doc_path_drift.py --root <p>  # 不同 repo

Exit codes
----------
    0 - 无违规 (或 --no-fail 模式)
    1 - 至少 1 处旧路径引用
    2 - 配置错误 (非 git repo 等)
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
import json  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]

# File extensions we scan for path references
SCAN_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".yaml", ".yml", ".sh", ".ps1", ".json")

# Directories we never scan (3rd-party, build artefacts, history)
SKIP_DIRS = frozenset(
    {
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        "venv",
        ".venv",
        "migrations",
        "_templates",
        "archive",
        ".trash",
        ".cache",
        ".trae",  # v9.4: junction → .skills/, 避免双重扫描
        ".opencode",  # v9.4: junction → .skills/, 避免双重扫描
    }
)


# ---------------------------------------------------------------------------
# TD-348: mtime-based manifest cache (复用 sync_ai_memory.py 模式)
# ---------------------------------------------------------------------------

CACHE_FILE_NAME = ".doc-path-drift-cache.json"


def _cache_path(root: Path) -> Path:
    """Return path to .ai-memory/.doc-path-drift-cache.json."""
    return root / ".ai-memory" / CACHE_FILE_NAME


def _build_mtime_manifest(repo_root: Path) -> dict[str, int]:
    """Build {relative_path: st_mtime_ns} for all scanned files.

    Walks the repo with the same SKIP_DIRS / SCAN_EXTENSIONS filter as the
    main scan, recording mtime for each candidate. If this manifest is
    unchanged since the last successful scan, the violations result is
    guaranteed identical (no file content changed).

    Excludes all .ai-memory/.-*-cache.json files (TD-348, similar to TD-347):
    SCAN_EXTENSIONS includes .json, so cache files would be included in
    the manifest. Each cache write changes its mtime, which would invalidate
    the cache on the next run (N+1 loop). Skipping them breaks the cycle.
    """
    import os

    manifest: dict[str, int] = {}
    # All cache/state files under .ai-memory/ that are auto-written by governance hooks.
    # Excluding them prevents cache-write → mtime-change → cache-miss loops.
    CACHE_FILE_BASENAMES = frozenset({
        CACHE_FILE_NAME,  # .doc-path-drift-cache.json (self)
        ".sync-cache.json",  # sync_ai_memory cache (TD-332/TD-344)
        ".docs-index-cache.json",  # sync_docs_index cache (TD-332/TD-344/TD-347)
        ".path-consistency-cache.json",  # check_path_consistency cache (TD-348)
        "sync-state.json",  # sync_ai_memory runtime state (.gitignored, auto-written every run)
    })
    # Include this checker script itself: logical changes (SKIP_DIRS,
    # whitelist, severity map) must invalidate the cache, otherwise a stale
    # cached violation list persists after the rule set changes (e.g. a
    # renamed/moved file kept reporting its old path on cache hit, since a
    # move preserves mtime and the manifest saw no change).
    self_path = Path(__file__).resolve()
    try:
        self_rel = str(self_path.relative_to(repo_root)).replace("\\", "/")
        manifest[self_rel] = self_path.stat().st_mtime_ns
    except (OSError, ValueError):
        pass
    # Files auto-written by governance-batch itself (not user edits).
    # Excluding prevents N+1 cache miss: batch end → auto-write → next batch cache miss.
    # performance-baseline.md is a timestamp log; its content doesn't affect hook results.
    AUTO_WRITTEN_PATHS = frozenset({
        "docs/reference/performance-baseline.md",  # _append_performance_baseline in gaf_governance_batch.py
    })
    for dirpath, dirs, files in os.walk(repo_root):
        # Prune SKIP_DIRS in-place (same as walk_repo)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != ".git"]
        for fname in files:
            if not fname.endswith(SCAN_EXTENSIONS):
                continue
            # 排除所有 cache 文件 (TD-348, 类似 TD-347 的 performance-baseline.md 排除)
            if fname in CACHE_FILE_BASENAMES:
                continue
            full = Path(dirpath) / fname
            try:
                rel = str(full.relative_to(repo_root)).replace("\\", "/")
                if rel in AUTO_WRITTEN_PATHS:
                    continue
                manifest[rel] = full.stat().st_mtime_ns
            except OSError:
                continue
    return manifest


def _load_cache(repo_root: Path) -> dict | None:
    """Load cache JSON. Returns None if missing or corrupt."""
    path = _cache_path(repo_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(
    repo_root: Path,
    manifest: dict[str, int],
    last_exit_code: int,
    per_file_violations: dict[str, list[tuple[int, str, str, str]]],
    last_skipped_whitelist: int,
) -> None:
    """Write cache JSON with per-file violation results (TD-390 incremental).

    ``per_file_violations`` maps rel_path → its list of hits
    (line, matched, phase, msg). This lets a later cache-miss (caused by a
    small change) reuse the known results of unchanged files and only
    re-`read_text` the files whose mtime changed, instead of re-scanning
    the whole repo.
    """
    path = _cache_path(repo_root)
    violation_count = sum(len(hits) for hits in per_file_violations.values())
    cache = {
        "manifest": manifest,
        "last_exit_code": last_exit_code,
        "last_violation_count": violation_count,
        "last_skipped_whitelist": last_skipped_whitelist,
        "per_file_violations": per_file_violations,
        "version": 2,
    }
    try:
        path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # Non-fatal: cache write failure should not break the hook.
        pass


def _check_cache_valid(repo_root: Path) -> tuple[bool, int, int, int]:
    """Check if cache is valid (all mtimes match last successful scan).

    Returns (cache_hit, cached_exit_code, cached_violation_count,
    cached_skipped_whitelist). Cache hit means safe to skip full scan.
    """
    cache = _load_cache(repo_root)
    if cache is None:
        return False, 0, 0, 0
    cached_manifest = cache.get("manifest")
    if not isinstance(cached_manifest, dict):
        return False, 0, 0, 0
    cached_exit_code = cache.get("last_exit_code", 0)
    cached_violation_count = cache.get("last_violation_count", 0)
    cached_skipped_whitelist = cache.get("last_skipped_whitelist", 0)
    if not isinstance(cached_exit_code, int):
        return False, 0, 0, 0
    if not isinstance(cached_violation_count, int):
        return False, 0, 0, 0
    if not isinstance(cached_skipped_whitelist, int):
        return False, 0, 0, 0
    current_manifest = _build_mtime_manifest(repo_root)
    # Stale-violation guard: a rename/move of a referenced path that lives
    # outside the scan scope (e.g. ``.ai-memory``) preserves mtime, so the
    # manifest above would not catch it and the cache would keep reporting
    # the old path forever. When the last scan had violations, re-verify the
    # offending files still exist and still match — cheap (only those files,
    # not a full walk). Any missing/unmatched file invalidates the cache.
    if cached_violation_count > 0 and cached_manifest == current_manifest:
        pv = cache.get("per_file_violations")
        if isinstance(pv, dict):
            for vrel, hits in pv.items():
                vpath = repo_root / vrel
                # hits come from JSON, so they are lists of lists; scan_file
                # returns tuples. Normalise to lists for a stable comparison.
                actual = [list(h) for h in scan_file(vpath)]
                expected = [list(h) for h in hits]
                if not vpath.is_file() or actual != expected:
                    return False, cached_exit_code, cached_violation_count, cached_skipped_whitelist
    if cached_manifest != current_manifest:
        return False, cached_exit_code, cached_violation_count, cached_skipped_whitelist
    return True, cached_exit_code, cached_violation_count, cached_skipped_whitelist

# spec §7.3 — 禁止的旧路径模式 (任一命中即报错)
FORBIDDEN_PATTERNS: list[tuple[str, str, str]] = [
    # P0 旧路径 — docs/general/ + docs/superpowers/ + docs/governance/ 已删除
    (r"docs/general/", "P0", "docs/general/ 已删除 (P0 重构), 迁移到 docs/business/ + docs/architecture/"),
    (r"docs/superpowers/", "P0", "docs/superpowers/ 已删除 (P0 重构), 迁移到 docs/specs/ + docs/plans/"),
    (r"docs/governance/", "P0", "docs/governance/ 已删除 (P0 重构), 迁移到 docs/business/ops/"),
    # docs/specs/dependency-graph.md 是自动生成, 但路径仍是合法的, 不在禁止列表
    # P1 旧路径 — evidence/<date>-<task>/ 直接在 evidence/ 根目录
    # 负向先行断言排除合法子目录 (active/archived/templates/README.md)
    (
        r"\.ai-memory/evidence/(?!active/|archived/|templates/|README\.md)[^/]+/",
        "P1",
        "evidence/<date>-<task>/ 必须在 evidence/active/ 或 evidence/archived/ 下 (P1 重构)",
    ),
    # P1 旧路径 — lessons 旧命名 <topic>_<date>-n<N>-<slug>.md
    # 排除 archived-early/ 子目录
    (
        r"\.ai-memory/lessons/(?!archived-early/)[^/]+\d{4}-\d{2}-\d{2}-n\d+",
        "P1",
        "lessons 文件名应为 N<N>-<slug>.md (P1 改名), 旧格式 <topic>_<date>-n<N>-<slug>.md 已废弃",
    ),
    # P2 旧路径 — .ai-memory/ 根目录 7 个文件已迁到 ref/
    (r"\.ai-memory/tech-stack\.md", "P2", "tech-stack.md 已迁移到 .ai-memory/ref/ (P2 重构)"),
    (r"\.ai-memory/version-compat\.md", "P2", "version-compat.md 已迁移到 .ai-memory/ref/ (P2 重构)"),
    (r"\.ai-memory/data-flow\.md", "P2", "data-flow.md 已迁移到 .ai-memory/ref/ (P2 重构)"),
    (r"\.ai-memory/cli-cheatsheet\.md", "P2", "cli-cheatsheet.md 已迁移到 .ai-memory/ref/ (P2 重构)"),
    (r"\.ai-memory/session-context\.md", "P2", "session-context.md 已迁移到 .ai-memory/ref/ (P2 重构)"),
    (r"\.ai-memory/spec-index\.md", "P2", "spec-index.md 已迁移到 .ai-memory/ref/ (P2 重构)"),
    (r"\.ai-memory/doc-health-report-schema\.md", "P2", "doc-health-report-schema.md 已迁移到 .ai-memory/ref/ (P2 重构)"),
    # P3 旧路径 — .trae/specs/ + .trae/plans/ 已迁到 docs/specs/legacy-trae/ + docs/plans/legacy-trae/
    # (spec-2026-07-26-trae-specs-plans-merge)
    # 历史文档 (fixed.md / completed-features.md / wontfix.md 等) 引用 .trae/specs|plans 路径
    # 通过 WHITELIST_FRAGMENTS 中具体文件白名单豁免
    (r"\.trae/specs/", "P3", ".trae/specs/ 已迁移到 docs/specs/legacy-trae/ (spec-2026-07-26-trae-specs-plans-merge)"),
    (r"\.trae/plans/", "P3", ".trae/plans/ 已迁移到 docs/plans/legacy-trae/ (spec-2026-07-26-trae-specs-plans-merge)"),
]

# spec §7.4 — 白名单豁免 (路径包含这些片段则跳过检查)
WHITELIST_FRAGMENTS = [
    ".git/",  # 历史记录不可改
    "docs/archive/spec-context/",  # 上下文承载体目录, 记录设计原文
    ".ai-memory/lessons/archived-early/",  # 早期归档文件 + 无 N 编号文件
    ".ai-memory/evidence/archived/",  # 归档 evidence (历史)
    ".ai-memory/evidence/active/",  # 活跃 evidence (新结构)
    ".ai-memory/evidence/templates/",  # evidence 模板
    "docs/plans/2026-07-25-docs-ai-memory-restructure.md",  # 本计划文档自身 (描述旧路径)
    "docs/specs/active/2026-07-25-docs-ai-memory-restructure.md",  # 本 spec 文档自身
    "docs/specs/active/2026-07-26-trae-specs-plans-merge.md",  # 本 spec 文档自身 (描述 .trae/specs|plans 旧路径)
    # 历史文档 (记录旧路径合理, 不改):
    "docs/specs/legacy-trae/",  # 原 .trae/specs/, spec-2026-07-26-trae-specs-plans-merge 迁移; 历史 spec 文档, 含旧路径是合理记录
    "docs/plans/legacy-trae/",  # 原 .trae/plans/, spec-2026-07-26-trae-specs-plans-merge 迁移; 历史 plan 文档, 含旧路径是合理记录
    "docs/specs/archived/",  # 历史 spec 文档归档
    "docs/plans/archived/",  # 历史 plan 文档归档
    "docs/tech-debt/fixed.md",  # 历史已修 TD 记录, 含旧路径是合理记录
    "docs/tech-debt/fixed-archive-",  # 历史归档 TD (按年度, fixed-archive-YYYY.md), 含旧路径合理
    "docs/tech-debt/wontfix.md",  # 历史 WONTFIX TD 记录
    "docs/completed-features.md",  # 历史已完成功能记录
    "docs/health/procedure.md",  # 月度健康检查流程指南
    "docs/specs/README.md",  # specs README 含路径说明
    "docs/specs/dependency-graph.md",  # 自动生成的依赖图, source 字段含旧路径
    "docs/specs/archived/2026-07/2026-07-25-docs-ai-memory-restructure.md",  # 历史 spec 描述旧路径
    "docs/plans/archived/2026-07/2026-07-25-docs-ai-memory-restructure.md",  # 历史 plan 描述旧路径
    ".ai-memory/ref/spec-index.md",  # spec 索引, source 字段含旧路径
    ".ai-memory/ref/doc-health-report-schema.md",  # 引用旧 spec 路径
    ".ai-memory/meta/docs-index.md",  # 历史索引描述
    ".ai-memory/meta/spec-evolution.md",  # spec 演进历史 (路径映射表)
    ".ai-memory/meta/yn-matrices/_workflow-spec.md",  # yn-matrix grep 命令历史
    ".ai-memory/evidence/archived/",  # 归档 evidence 含旧路径作为历史记录
    "backend/agents/models.py",  # 代码注释引用历史 spec 路径
    "docs/architecture/cross-cutting/pre-commit-stages.md",  # hook 文档引用旧路径
    ".ai-memory/meta/archived-lessons.md",  # 历史归档索引
    ".ai-memory/evidence/archived/",  # 归档 evidence 含旧路径作为历史记录
    # 测试 fixture (含旧路径作为测试数据, 不应改):
    "scripts/tests/test_doc_health_check.py",  # doc-health 测试 fixture (s40 拆分前; 保留历史)
    "scripts/tests/test_doc_health_common.py",  # s40 split (TD-365 7/9)
    "scripts/tests/test_doc_health_d1_overlap.py",  # s40 split
    "scripts/tests/test_doc_health_d2_bloat.py",  # s40 split
    "scripts/tests/test_doc_health_d3_count.py",  # s40 split
    "scripts/tests/test_doc_health_d4_path.py",  # s40 split
    "scripts/tests/test_doc_health_d5_frontmatter.py",  # s40 split
    "scripts/tests/test_doc_health_d6_staleness.py",  # s40 split
    "scripts/tests/test_doc_health_d7_index.py",  # s40 split
    "scripts/tests/test_doc_health_d8_yaml.py",  # s40 split
    "scripts/tests/test_doc_health_integration.py",  # s40 split
    "scripts/tests/test_check_doc_path_drift.py",  # 本 hook 的测试文件
    "scripts/tests/test_path_hooks_cache.py",  # TD-348 mtime cache 测试, 含旧路径样例
    "scripts/e2e/fixtures/",  # e2e fixture, 含旧路径作为测试数据
    # Hook 自身 (定义 FORBIDDEN_PATTERNS 字符串, 不能不写旧路径):
    "scripts/hooks/check_doc_path_drift.py",
    # docstring/注释中的旧路径示例 (作为说明, 非真实路径):
    "scripts/hooks/check_3step_evidence.py",  # docstring 含 <date>-<task> 格式说明
    "scripts/hooks/post_commit_reflection_check.py",  # docstring 说明
    # governance 检查器代码 (含 `", "` 路径列表分隔符, 非真实路径引用):
    "scripts/governance/check_dimensions/d1_overlap.py",
    "scripts/governance/check_dimensions/d5_frontmatter.py",
    "scripts/governance/check_dimensions/d6_staleness.py",
]

# 编译正则一次
FORBIDDEN_REGEXES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(p), phase, msg) for p, phase, msg in FORBIDDEN_PATTERNS
]


def _is_whitelisted(filepath: str) -> bool:
    """Return True if filepath matches any whitelist fragment."""
    for frag in WHITELIST_FRAGMENTS:
        if frag in filepath:
            return True
    return False


def scan_file(path: Path) -> list[tuple[int, str, str, str]]:
    """Return [(line_no, matched_text, phase, message), ...] for forbidden path hits."""
    hits: list[tuple[int, str, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits

    for idx, line in enumerate(text.splitlines(), start=1):
        # 跳过纯注释行 (避免误报注释里的旧路径说明)
        # 但仍检查代码字符串, 因为路径引用主要在字符串中
        for regex, phase, msg in FORBIDDEN_REGEXES:
            for match in regex.finditer(line):
                hits.append((idx, match.group(0), phase, msg))
    return hits


def walk_repo(repo_root: Path) -> list[Path]:
    """Yield candidate files under repo_root matching SCAN_EXTENSIONS."""
    import os

    candidates: list[Path] = []
    for dirpath, dirs, files in os.walk(repo_root):
        # Prune SKIP_DIRS in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != ".git"]
        for fname in files:
            if not fname.endswith(SCAN_EXTENSIONS):
                continue
            candidates.append(Path(dirpath) / fname)
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="GAF doc path drift checker (spec §7.3, P2)")
    parser.add_argument("--root", default=str(REPO_ROOT_DEFAULT), help="Repository root to scan")
    parser.add_argument("--no-fail", action="store_true", help="Warn-only mode (do not exit 1 on errors)")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    if not (repo_root / ".git").exists():
        print(f"ERROR: {repo_root} is not a git repo", file=sys.stderr)
        return 2

    # TD-348: mtime cache hit → skip full scan, return last result
    cache_hit, cached_exit_code, cached_violation_count, cached_skipped_whitelist = _check_cache_valid(
        repo_root
    )
    if cache_hit:
        print(
            f"[doc-path-drift] cache hit: {cached_violation_count} violation(s), "
            f"{cached_skipped_whitelist} file(s) skipped (whitelist) [from last scan]"
        )
        return cached_exit_code

    current_manifest = _build_mtime_manifest(repo_root)
    prior_cache = _load_cache(repo_root)
    prior_manifest = prior_cache.get("manifest") if prior_cache else None
    prior_pv = prior_cache.get("per_file_violations") if prior_cache else None
    # TD-390 incremental: on a miss (e.g. one file changed), re-scan ONLY the
    # files whose mtime changed (or are new), reusing the cached per-file
    # results for everything else. Keeps "whole-repo" correctness (any untouched
    # old path is still reported from cache) while cutting scan I/O from all
    # files to just the changed ones.
    if isinstance(prior_pv, dict) and prior_manifest != current_manifest:
        changed = [
            rel for rel in current_manifest
            if prior_manifest.get(rel) != current_manifest[rel]
        ]
        changed += [rel for rel in prior_manifest if rel not in current_manifest]
        changed = sorted(set(changed))
        # Only these need re-reading; the rest are reused verbatim from cache.
        candidates = [(repo_root / rel, rel) for rel in changed]
        seen_cache = True
        cached_pv: dict[str, list[tuple[int, str, str, str]]] | None = prior_pv
    else:
        candidates = [(p, str(p.relative_to(repo_root)).replace("\\", "/")) for p in walk_repo(repo_root)]
        seen_cache = False
        cached_pv = None

    print(f"[doc-path-drift] {'incremental' if seen_cache else 'full'} scan: "
          f"{'changed' if seen_cache else len(candidates)} files under {repo_root}")

    # Start from cached per-file results (unchanged files), then overwrite the
    # entries for changed/new files, and drop entries for deleted files.
    violations: list[tuple[Path, int, str, str, str]] = []
    per_file_violations: dict[str, list[tuple[int, str, str, str]]] = {}
    skipped_whitelist = 0

    # Seed with cached results for files still present (and only for the ones
    # we are not about to re-scan). This is the reuse that avoids 1000+ reads.
    if cached_pv is not None:
        changed_lookup = {rel for _, rel in candidates}
        for rel, hits in cached_pv.items():
            if (repo_root / rel).is_file() and rel not in changed_lookup:
                per_file_violations[rel] = hits

    for full, rel in candidates:
        if _is_whitelisted(rel):
            skipped_whitelist += 1
            per_file_violations.pop(rel, None)
            continue
        hits = scan_file(full)
        per_file_violations[rel] = hits

    # If this was a full scan (no cache), count whitelist skips over every file.
    if not seen_cache:
        skipped_whitelist = sum(
            1 for full, rel in candidates if _is_whitelisted(rel)
        )

    for rel, hits in per_file_violations.items():
        for line_no, matched, phase, msg in hits:
            violations.append((repo_root / rel, line_no, matched, phase, msg))

    # 输出违规
    for path, line_no, matched, phase, msg in violations:
        rel = path.relative_to(repo_root)
        print(f"  [{phase}] {rel}:{line_no}  '{matched}'")
        print(f"          → {msg}")

    print(f"---\n[doc-path-drift] {len(violations)} violation(s), {skipped_whitelist} file(s) skipped (whitelist)")

    if violations and not args.no_fail:
        exit_code = 1
    else:
        exit_code = 0

    # TD-348/TD-390: refresh cache after a scan so the next run can reuse it.
    _write_cache(
        repo_root,
        current_manifest,
        exit_code,
        per_file_violations,
        skipped_whitelist,
    )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
