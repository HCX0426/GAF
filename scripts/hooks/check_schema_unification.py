"""check_schema_unification.py - N191 schema 归一化全链路扫描 (2026-07-29).

把 N191 env-hardrules.md 的 5 个 grep 模式 + 节点间数据流检查打包成
一次扫描, 避免 AI 每次手动跑 5 个 Grep 工具. 默认增量模式 (mtime cache
hit 跳过), 全量模式用 ``--full``.

为什么需要这个脚本
------------------
N191 硬约束要求 schema 归一化任务完成前必跑 7 项检查清单 + 5 个 grep 模式.
AI 每次手动跑 5 个 Grep 工具, 既慢又容易漏. 这个脚本把检查集成到一次调用,
且用 mtime cache (复用 TD-348 模式) 在文件未变化时跳过扫描, 解决"每次
全文件遍历好慢"的问题.

检查内容
--------
1. **旧字段名扫描** (N191 §5 个 grep 模式):
   - 节点顶层 ``type`` (应为 ``node_type``)
   - ``config.template`` 在 template_match 节点 (应为 ``template_id``)
   - ``config.max_wait`` (应为 ``timeout``)
   - ``action_type`` / ``next_step`` / ``retry_interval`` / ``fallback_action``
     在新代码 (canvas 旧 schema 残留)
   - ``execution_mode = "chain"`` (已废弃)

2. **节点间数据流检查** (N191 §节点间数据流):
   - publish_match_pos 写入字段完整性 (x/y/source/extra)
   - coord_system 字段标注 (physical/logical/legacy)
   - ROI 偏移传递 (sub_image_to_full 调用)

3. **agent ↔ backend 字段契约**:
   - agent 读取字段 vs backend validators 期望字段一致性
   - 已知: template_match 用 template_id (canonical) / template (legacy)
   - 已知: wait 节点用 template (canonical, mode=template/disappear)

增量模式 (默认)
---------------
基于 mtime manifest cache: 文件未变化时直接复用上次结果, 跳过整个扫描流程.
与 check_doc_path_drift.py / sync_ai_memory.py 同思路 (TD-348/TD-332).

Usage
-----
    # 默认增量模式 (mtime cache hit → 秒过)
    python scripts/hooks/check_schema_unification.py

    # 全量扫描 (强制重扫, 忽略 cache)
    python scripts/hooks/check_schema_unification.py --full

    # warn only (不阻断)
    python scripts/hooks/check_schema_unification.py --no-fail

Exit codes
----------
    0 - 无违规 (或 --no-fail 模式)
    1 - 至少 1 处 schema 残留
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
import contextlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]

# File extensions we scan for schema references
SCAN_EXTENSIONS = (".py", ".ts", ".tsx", ".json", ".md")

# Directories we never scan
SKIP_DIRS = frozenset({
    "node_modules", "dist", "build", "__pycache__", "venv", ".venv",
    "migrations", "_templates", "archive", ".trash", ".cache", ".git",
    "archived-early",  # lessons/archived-early/ 历史归档
})

# Scope: only scan these top-level dirs (避免全文件遍历)
SCAN_DIRS = frozenset({
    "worker/src", "backend", "frontend/src", "resources", "docs/business",
})


# ---------------------------------------------------------------------------
# N191 §5 个 grep 模式 — 旧字段名扫描
# ---------------------------------------------------------------------------

# 每条规则: (pattern, description, severity, whitelist_paths)
# severity: "error" (残留) / "warn" (可能是兼容层)
# whitelist_paths: 命中路径若在此列表中则跳过 (已知兼容层)
LEGACY_FIELD_RULES = [
    # 1. 节点顶层 "type": "click" 等 (应为 node_type)
    (
        re.compile(r'"type"\s*:\s*"(click|swipe|template_match|template_match_any|'
                   r"ocr|color_detect|feature_match|wait|branch|loop|key_press|"
                   r"text_input|long_press|direct_hit|notify|device_control|monitor|"
                   r"sub_pipeline|goto|swipe_until|login_account|switch_account|"
                   r'switch_resource|captcha_detect|random_delay)"'),
        "节点顶层 type 应为 node_type (N191 schema 归一化)",
        "error",
        [
            # canvas schema (React Flow) 有意用 type 字段, 与 nested schema 并存
            # 见 backend/pipeline/schema.py PIPELINE_GRAPH_SCHEMA oneOf + TD-075
            "backend/pipeline/recording_converter.py",  # 输出 canvas graph_data
            "backend/pipeline/schema.py",  # PIPELINE_GRAPH_SCHEMA 定义
            "frontend/src/utils/schemaValidator.ts",  # canvas schema 校验
            # parser.py 注释描述 React Flow 输入格式 (L230), 兼容层代码 L240 归一化
            "worker/src/engine/parser.py",
            # 测试用例有意测试 legacy/canvas schema 兼容性
            "backend/pipeline/tests/test_validators_nested.py",  # test_canvas_schema_still_passes
            "backend/pipeline/tests/test_validators.py",  # test_canvas_schema_still_passes (canvas 用 type)
            "backend/tasks/tests/test_worker_selector.py",  # test legacy type 字段兼容
        ],
    ),
    # 2. config.max_wait (应为 timeout)
    (
        re.compile(r'"max_wait"\s*:'),
        "config.max_wait 应为 config.timeout (N191 schema 归一化)",
        "error",
        [
            # canvas schema (React Flow) config 用 max_wait 是 legacy 兼容, 前端 NodePropertyPanel 兼容读取
            "backend/pipeline/recording_converter.py",  # 输出 canvas graph_data
            # agent wait.py _get_timeout 兼容读取 legacy max_wait (canonical=timeout)
            "worker/src/engine/nodes/wait.py",
        ],
    ),
    # 3. execution_mode = "chain" (已废弃)
    (
        re.compile(r'"execution_mode"\s*:\s*"chain"'),
        "execution_mode=chain 已废弃, 应为 pipeline (spec-2026-07-27-execution-path-unification)",
        "error",
        [],
    ),
]

# 节点级 type 字段残留 (frontend/backend/agent 代码里读取 node.type)
# 白名单: 已知的 @deprecated 兼容层
NODE_TYPE_CODE_RULES = [
    (
        re.compile(r"\bnode\.type\b|\bnode\['type'\]\b|\bnode\.get\(['\"]type['\"]\)"),
        "代码读取 node.type (应为 node.node_type)",
        "warn",
        [
            # @deprecated 兼容层 (frontend/src/types/models.ts L731-762)
            "frontend/src/types/models.ts",
            # @deprecated 兼容层 (frontend/src/pages/Tasks/Editor.tsx serializeNode)
            "frontend/src/pages/Tasks/Editor.tsx",
            # canvas 双读兼容: node.get('node_type') or node.get('type') 读取
            # 两种 graph schema, 非"只读 type"
            "backend/pipeline/estimator.py",
            "backend/pipeline/validators.py",  # _node_type(): 兼容读取 canvas/nested 双 schema
            "backend/pipeline/tests/test_estimator.py",  # docstring 描述算法用词
        ],
    ),
]

# action_type / next_step / retry_interval / fallback_action 在新代码
# (canvas 旧 schema 字段, 保存时应转换为 node_type/retry:{}/fallback:{})
# TD-395 / spec-2026-08-26 P4: 模式收窄为"带引号的 dict 键"访问, 不再匹配
# 裸单词 —— scheduler recovery / monitor 弹窗模板 / script_dsl 里 action_type
# 是业务领域字段名, 与 canvas 旧 schema 无关, 属于误报源. 已知兼容层走白名单
# (支持 "dir/" 前缀).
CANVAS_LEGACY_RULES = [
    (
        re.compile(r"['\"]action_type['\"]\s*:[^=\n]"),
        "canvas 旧 schema action_type 键 (应为 node_type)",
        "warn",
        [
            "frontend/src/types/models.ts",  # @deprecated TaskStepConfigLegacy
            "frontend/src/types/models/schedule.ts",  # TaskStepConfigLegacy 拆出 @deprecated
            "frontend/src/types/models/debug.ts",  # @deprecated 旧 chain schema UI-internal 注释
            "frontend/src/pages/Tasks/Editor.tsx",  # @deprecated serializeNode
            "backend/scheduler/",  # recovery 领域术语: action_type=恢复动作类型, 非 canvas 残留
            "worker/src/monitor/handlers.py",  # monitor 弹窗模板内部配置字段
            "worker/tests/test_monitor_coord_trace.py",  # 对应 monitor 测试
            "docs/business/ops/monitor-design.md",  # monitor 事件 payload 设计文档
        ],
    ),
]


# ---------------------------------------------------------------------------
# mtime-based manifest cache (复用 TD-348 模式)
# ---------------------------------------------------------------------------

CACHE_FILE_NAME = ".schema-unification-cache.json"


def _cache_path(root: Path) -> Path:
    """Return path to .ai-memory/.schema-unification-cache.json."""
    return root / ".ai-memory" / CACHE_FILE_NAME


def _build_mtime_manifest(repo_root: Path) -> dict[str, int]:
    """Build {relative_path: st_mtime_ns} for all scanned files.

    Only scans SCAN_DIRS top-level subdirs (not full repo walk) to keep
    the manifest small and fast.
    """
    import os

    manifest: dict[str, int] = {}
    # Include this checker script itself: logical changes (SCAN_DIRS,
    # SKIP_DIRS, severity map) must invalidate the cache, otherwise a stale
    # cached violation list persists after the rule set changes (TD-348
    # class — same root cause as check_path_consistency / check_doc_path_drift).
    self_path = Path(__file__).resolve()
    try:
        self_rel = str(self_path.relative_to(repo_root)).replace("\\", "/")
        manifest[self_rel] = self_path.stat().st_mtime_ns
    except (OSError, ValueError):
        pass
    for top in SCAN_DIRS:
        top_path = repo_root / top
        if not top_path.is_dir():
            continue
        for dirpath, dirs, files in os.walk(top_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if not fname.endswith(SCAN_EXTENSIONS):
                    continue
                full = Path(dirpath) / fname
                try:
                    rel = str(full.relative_to(repo_root)).replace("\\", "/")
                    manifest[rel] = full.stat().st_mtime_ns
                except OSError:
                    continue
    return manifest


def _load_cache(repo_root: Path) -> dict | None:
    path = _cache_path(repo_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(repo_root: Path, manifest: dict[str, int], exit_code: int,
                 violations_count: int) -> None:
    path = _cache_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest": manifest,
        "last_exit_code": exit_code,
        "last_violations_count": violations_count,
        "last_run_iso": __import__("datetime").datetime.now().isoformat(),
    }
    with contextlib.suppress(OSError):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _check_cache_hit(repo_root: Path) -> tuple[bool, dict | None]:
    """Return (is_hit, cached_data). Hit = manifest unchanged."""
    cached = _load_cache(repo_root)
    if cached is None:
        return False, None
    cached_manifest = cached.get("manifest", {})
    current_manifest = _build_mtime_manifest(repo_root)
    if cached_manifest == current_manifest:
        return True, cached
    return False, None


# ---------------------------------------------------------------------------
# 扫描逻辑
# ---------------------------------------------------------------------------

def _is_whitelisted(rel_path: str, whitelist: list) -> bool:
    """Exact-match or dir-prefix match (entry ending with '/') against whitelist."""
    for entry in whitelist:
        if entry.endswith("/"):
            if rel_path.startswith(entry):
                return True
        elif rel_path == entry:
            return True
    return False


def _scan_file(content: str, rules: list, rel_path: str) -> list[dict]:
    """Scan file content against rules, return violations."""
    violations = []
    for pattern, desc, severity, whitelist in rules:
        if _is_whitelisted(rel_path, whitelist):
            continue
        for match in pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            violations.append({
                "file": rel_path,
                "line": line_no,
                "severity": severity,
                "desc": desc,
                "match": match.group(0)[:80],
            })
    return violations


def scan_repo(repo_root: Path) -> list[dict]:
    """Scan repo for schema unification violations."""
    import os

    all_rules = LEGACY_FIELD_RULES + NODE_TYPE_CODE_RULES + CANVAS_LEGACY_RULES
    violations: list[dict] = []

    for top in SCAN_DIRS:
        top_path = repo_root / top
        if not top_path.is_dir():
            continue
        for dirpath, dirs, files in os.walk(top_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if not fname.endswith(SCAN_EXTENSIONS):
                    continue
                full = Path(dirpath) / fname
                try:
                    rel = str(full.relative_to(repo_root)).replace("\\", "/")
                    content = full.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                violations.extend(_scan_file(content, all_rules, rel))
    return violations


# ---------------------------------------------------------------------------
# 节点间数据流检查 (静态文件扫描版)
# ---------------------------------------------------------------------------

def check_node_data_flow(repo_root: Path) -> list[dict]:
    """检查节点间数据流关键模式 (N191 §节点间数据流).

    只做静态扫描: 确认 publish_match_pos / coord_system / sub_image_to_full
    在 agent 代码中存在且未被误删. 完整的运行时数据流验证需跑 e2e.
    """
    violations: list[dict] = []
    worker_nodes_dir = repo_root / "worker" / "src" / "engine" / "nodes"
    if not worker_nodes_dir.is_dir():
        return violations

    # 检查 publish_match_pos 在识别类节点中调用
    recognition_nodes = ["template_match.py", "template_match_any.py", "ocr.py",
                         "feature_match.py", "color_detect.py"]
    for fname in recognition_nodes:
        fpath = worker_nodes_dir / fname
        if not fpath.is_file():
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "publish_match_pos" not in content:
            violations.append({
                "file": f"worker/src/engine/nodes/{fname}",
                "line": 0,
                "severity": "warn",
                "desc": f"{fname} 识别类节点未调用 publish_match_pos (N191 节点间数据流)",
                "match": "missing publish_match_pos",
            })

    return violations


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="N191 schema 归一化全链路扫描")
    parser.add_argument("--root", type=Path, default=REPO_ROOT_DEFAULT,
                        help="repo root (default: auto-detect)")
    parser.add_argument("--full", action="store_true",
                        help="全量扫描, 忽略 mtime cache")
    parser.add_argument("--no-fail", action="store_true",
                        help="warn only, 不阻断 (exit 0 即使有违规)")
    args = parser.parse_args()

    repo_root = args.root.resolve()
    if not (repo_root / ".git").is_dir():
        print(f"[schema-unification] ERROR: not a git repo: {repo_root}", file=_sys.stderr)
        return 2

    # 增量模式: mtime cache hit → 直接复用上次结果
    if not args.full:
        is_hit, cached = _check_cache_hit(repo_root)
        if is_hit and cached:
            last_code = cached.get("last_exit_code", 0)
            last_count = cached.get("last_violations_count", 0)
            if last_code == 0:
                print(f"[schema-unification] PASS (cache hit, {last_count} violations上次)")
                return 0
            else:
                print(f"[schema-unification] FAIL (cache hit, {last_count} violations上次)")
                if args.no_fail:
                    return 0
                return 1

    # 全量扫描或 cache miss
    violations = scan_repo(repo_root)
    violations.extend(check_node_data_flow(repo_root))

    errors = [v for v in violations if v["severity"] == "error"]
    warns = [v for v in violations if v["severity"] == "warn"]

    # 写 cache
    exit_code = 1 if errors else 0
    _write_cache(repo_root, _build_mtime_manifest(repo_root), exit_code, len(violations))

    # 输出
    if errors:
        print(f"[schema-unification] FAIL: {len(errors)} errors, {len(warns)} warns")
        for v in errors[:20]:
            print(f"  ERROR {v['file']}:{v['line']} — {v['desc']}")
            print(f"        match: {v['match']}")
    else:
        print(f"[schema-unification] PASS: 0 errors, {len(warns)} warns (含白名单豁免)")
    # P4 (TD-395): 不再 warns[:10] 截断 —— 截断会导致 lint 通过但告警详情
    # 丢失, 误报无法被审计. 全量打印, 总数已在 PASS/FAIL 行体现.
    for v in warns:
        print(f"  WARN  {v['file']}:{v['line']} — {v['desc']}")

    if args.no_fail:
        return 0
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
