"""check_code_rules.py — GAF 代码铁律 AST 静态检测 (M1, 2026-08-15).

把 failure-modes / env-hardrules 中可 AST 化的代码铁律做成机器可检测的
pre-commit 门禁, 终结"规则靠 AI 自觉"的状态 (借鉴 TEST_SFCAPI static_check).

规则注册表 (CODE_RULES, 数据驱动 — 加规则只需加一行)
-----------------------------------------------------
    R001  静默吞错 (裸/空 except)          N182/N183 节点观测性      error
    R002  测试中 time.sleep                N196 测试数据硬约束        warn
    R003  硬编码 /api/v2 路径拼接          N197 URL 拼接归一化        warn
    R004  cursor.execute 字符串拼接 SQL    N168 SQL 注入修复          error
    R005  节点 schema 旧字段残留           N191 schema 归一化         warn

阻断策略
--------
- error 级命中 → exit 1 (阻断 commit); 逃生门 = 既有 ``--no-verify`` +
  ``GAF_BYPASS_REASON`` 审计 (gaf-commit.sh), 禁止默认使用.
- warn 级命中 → 仅打印 (exit 0).

增量 vs 全量
------------
默认按 ``git diff --cached`` 的**新增行**检测: 只卡新代码, 不翻历史债
(2026-08-15 实测 backend/agent 有 84 个文件的存量空 except, 全量阻断会
锁死所有改动). ``--all`` 全文件扫描用于定期审计 (仿 check_schema_unification).

Usage
-----
    # pre-commit 调用 (pass_filenames: true, 只收 staged py)
    python scripts/hooks/check_code_rules.py <file1> <file2> ...

    # 手动: 扫描全部 staged py (backend|agent)
    python scripts/hooks/check_code_rules.py

    # 全量审计 (忽略 diff, 扫整个文件)
    python scripts/hooks/check_code_rules.py --all

    # 只警告不阻断
    python scripts/hooks/check_code_rules.py --no-fail

Exit codes
----------
    0 - 无 error 级违规 (或 --no-fail)
    1 - 至少 1 处 error 级违规
    2 - 配置错误 (非 git 仓库等)
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
import ast  # noqa: E402
import fnmatch  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]

# Hook 只收 backend|agent 的 .py (见 .pre-commit-config.yaml files 过滤)
CODE_DIRS = ("backend", "agent")


@dataclass(frozen=True)
class Violation:
    """单条违规记录."""

    file: str
    line: int
    rule_id: str
    severity: str  # "error" | "warn"
    message: str
    hint: str


@dataclass(frozen=True)
class CodeRule:
    """单条代码铁律规则 (数据驱动注册表).

    check(tree, content, rel_path) -> list[Violation]; 返回空 = 通过.
    """

    id: str
    ref: str
    severity: str
    description: str
    path_includes: tuple[str, ...] = ()
    path_excludes: tuple[str, ...] = ()
    check: object = field(default=None, compare=False)


# ---------------------------------------------------------------------------
# 规则实现
# ---------------------------------------------------------------------------


def _check_silent_except(tree: ast.AST, content: str, rel: str) -> list[Violation]:
    """R001: 裸 except / 空 except 体 (N182/N183 节点观测性)."""
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            out.append(Violation(
                rel, node.lineno, "R001", "error",
                "裸 except (未指定异常类型)",
                "N182/N183: 禁止静默吞错; 至少 `except Exception as e:` 并记录错误日志/上下文追溯",
            ))
        elif len(node.body) == 1 and isinstance(
            node.body[0], (ast.Pass, ast.Continue, ast.Break)
        ):
            out.append(Violation(
                rel, node.lineno, "R001", "error",
                "空 except 体 (仅 pass/continue/break)",
                "N182/N183: 禁止静默吞错; 记录错误日志 (节点观测性硬约束) 或显式抛出",
            ))
    return out


def _check_cursor_execute_concat(tree: ast.AST, content: str, rel: str) -> list[Violation]:
    """R004: cursor.execute 用 f-string / 字符串拼接拼 SQL (N168)."""
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "execute" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.JoinedStr):
            out.append(Violation(
                rel, node.lineno, "R004", "error",
                "cursor.execute 使用 f-string 拼接 SQL",
                "N168: 一律参数化查询 (:VAR 绑定变量), 字符串拼接有 SQL 注入风险",
            ))
        elif (
            isinstance(first, ast.BinOp)
            and isinstance(first.op, (ast.Add, ast.Mod))
            and isinstance(first.left, ast.Constant)
            and isinstance(first.left.value, str)
        ):
            out.append(Violation(
                rel, node.lineno, "R004", "error",
                "cursor.execute 使用字符串拼接 SQL",
                "N168: 一律参数化查询 (:VAR 绑定变量), 字符串拼接有 SQL 注入风险",
            ))
    return out


def _check_test_sleep(tree: ast.AST, content: str, rel: str) -> list[Violation]:
    """R002: 测试中 time.sleep (N196 测试数据硬约束)."""
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_sleep = False
        if isinstance(func, ast.Name) and func.id == "sleep":
            is_sleep = True  # from time import sleep
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "sleep"
            and isinstance(func.value, ast.Name)
            and func.value.id == "time"
        ):
            is_sleep = True
        if is_sleep:
            out.append(Violation(
                rel, node.lineno, "R002", "warn",
                "测试中使用 time.sleep",
                "N196: 禁 sleep 硬等; 用条件等待/polling (N160 条件等待模式) 替代",
            ))
    return out


def _check_hardcoded_api_v2(tree: ast.AST, content: str, rel: str) -> list[Violation]:
    """R003: 硬编码 /api/v2 路径 (N197 URL 拼接归一化)."""
    out: list[Violation] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "/api/v2" in node.value
            and node.value.strip()
        ):
            out.append(Violation(
                rel, node.lineno, "R003", "warn",
                "硬编码 /api/v2 路径字符串",
                "N197: URL 拼接归一化; 用规范常量/配置, 禁止硬编码前缀",
            ))
    return out


# N191 5 个 grep 模式 (与 check_schema_unification.py 保持一致, 防止双份漂移)
_SCHEMA_TYPE_RE = re.compile(
    r'"type"\s*:\s*"(click|swipe|template_match|template_match_any|'
    r"ocr|color_detect|feature_match|wait|branch|loop|key_press|"
    r"text_input|long_press|direct_hit|notify|device_control|monitor|"
    r"sub_pipeline|goto|swipe_until|login_account|switch_account|"
    r'switch_resource|captcha_detect|random_delay)"'
)
_SCHEMA_MAX_WAIT_RE = re.compile(r'"max_wait"\s*:')
_SCHEMA_EXECUTION_MODE_RE = re.compile(r'"execution_mode"\s*:\s*"chain"')
_SCHEMA_NODE_TYPE_RE = re.compile(
    r"\bnode\.type\b|\bnode\['type'\]\b|\bnode\.get\(['\"]type['\"]\)"
)
_SCHEMA_ACTION_TYPE_RE = re.compile(r"\baction_type\b")

_SCHEMA_WHITELIST = frozenset({
    # canvas schema (React Flow) 有意用 type 字段
    "backend/pipeline/recording_converter.py",
    "backend/pipeline/schema.py",
    "frontend/src/utils/schemaValidator.ts",
    "agent/src/engine/parser.py",
    "backend/pipeline/tests/test_validators_nested.py",
    "backend/tasks/tests/test_agent_selector.py",
    # config.max_wait legacy 兼容层
    "agent/src/engine/nodes/wait.py",
    # node.type @deprecated 兼容层
    "frontend/src/types/models.ts",
    "frontend/src/pages/Tasks/Editor.tsx",
})

_SCHEMA_RULES: tuple[tuple[re.Pattern, str], ...] = (
    (_SCHEMA_TYPE_RE, "节点顶层 type 应为 node_type (N191 schema 归一化)"),
    (_SCHEMA_MAX_WAIT_RE, "config.max_wait 应为 config.timeout (N191 schema 归一化)"),
    (_SCHEMA_EXECUTION_MODE_RE, "execution_mode=chain 已废弃, 应为 pipeline (N191)"),
    (_SCHEMA_NODE_TYPE_RE, "代码读取 node.type (应为 node.node_type, N191)"),
    (_SCHEMA_ACTION_TYPE_RE, "canvas 旧 schema action_type (应为 node_type, N191)"),
)


def _check_schema_residue(tree: ast.AST, content: str, rel: str) -> list[Violation]:
    """R005: N191 节点 schema 旧字段残留 (正则, 白名单同 check_schema_unification)."""
    out: list[Violation] = []
    if rel in _SCHEMA_WHITELIST:
        return out
    for pattern, desc in _SCHEMA_RULES:
        for match in pattern.finditer(content):
            line_no = content[: match.start()].count("\n") + 1
            out.append(Violation(
                rel, line_no, "R005", "warn", desc,
                "N191: schema 归一化; 确认非 legacy 兼容层后改用 canonical 字段",
            ))
    return out


# ---------------------------------------------------------------------------
# 注册表 (顺序即输出顺序)
# ---------------------------------------------------------------------------

CODE_RULES: list[CodeRule] = [
    CodeRule(
        id="R001", ref="N182/N183", severity="error",
        description="静默吞错 (裸/空 except)",
        path_includes=("agent/src/**", "backend/**"),
        path_excludes=("**/migrations/**",),
        check=_check_silent_except,
    ),
    CodeRule(
        id="R002", ref="N196", severity="warn",
        description="测试中 time.sleep",
        path_includes=("**/tests/**", "**/test_*.py", "**/*_test.py"),
        check=_check_test_sleep,
    ),
    CodeRule(
        id="R003", ref="N197", severity="warn",
        description="硬编码 /api/v2 路径",
        path_includes=("agent/src/**",),
        check=_check_hardcoded_api_v2,
    ),
    CodeRule(
        id="R004", ref="N168", severity="error",
        description="cursor.execute 字符串拼接 SQL",
        path_includes=("backend/**",),
        path_excludes=("**/migrations/**",),
        check=_check_cursor_execute_concat,
    ),
    CodeRule(
        id="R005", ref="N191", severity="warn",
        description="节点 schema 旧字段残留",
        path_includes=("agent/src/**", "backend/**"),
        check=_check_schema_residue,
    ),
]


# ---------------------------------------------------------------------------
# diff 新增行提取 (增量门禁)
# ---------------------------------------------------------------------------


def _added_line_ranges(root: Path, rel_path: str) -> list[tuple[int, int]] | None:
    """返回 git 暂存区中新增行的行号区间; None = 未跟踪文件 (整文件视为新增)."""
    probe = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", rel_path],
        capture_output=True,
    )
    if probe.returncode != 0:
        return None
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--unified=0", "--", rel_path],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    ranges: list[tuple[int, int]] = []
    for line in diff.stdout.splitlines():
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if not m:
            continue
        start = int(m.group(1))
        count = int(m.group(2) or "1")
        if count > 0:
            ranges.append((start, start + count - 1))
    return ranges


def _added_ranges_map(root: Path) -> dict[str, list[tuple[int, int]]] | None:
    """一次 ``git diff --cached --unified=0`` 解析全部 .py 的新增行区间.

    {rel_path: [(start, end), ...]}; 文件不在 map 中 = 无新增行 (跳过).
    None = git 不可用 (非真实仓库, 如测试的 fake repo), 调用方 fallback
    整文件视为新增 (与 _added_line_ranges 的 None 语义一致).
    N171 优化: 旧实现每文件 2 次 git 子进程, 全量 --all-files 128s →
    本实现 1 次子进程.
    """
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--unified=0", "--", "*.py"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if diff.returncode != 0:
        return None
    ranges: dict[str, list[tuple[int, int]]] = {}
    cur: str | None = None
    for line in diff.stdout.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
            ranges.setdefault(cur, [])
        elif cur is not None and line.startswith("@@"):
            m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2) or "1")
                if count > 0:
                    ranges[cur].append((start, start + count - 1))
    return ranges


def _in_added_ranges(line: int, ranges: list[tuple[int, int]] | None) -> bool:
    """None (未跟踪) → 整文件视为新增, 全部命中."""
    if ranges is None:
        return True
    return any(start <= line <= end for start, end in ranges)


# ---------------------------------------------------------------------------
# 扫描逻辑
# ---------------------------------------------------------------------------


def _rule_matches(rule: CodeRule, rel_path: str, apply_filter: bool) -> bool:
    # apply_filter=False: 仓库外文件 (仅测试/临时场景) 不做路径过滤
    if not apply_filter:
        return True
    if rule.path_includes and not any(fnmatch.fnmatch(rel_path, pat) for pat in rule.path_includes):
        return False
    return not (
        rule.path_excludes and any(fnmatch.fnmatch(rel_path, pat) for pat in rule.path_excludes)
    )


def _scan_file(
    path: Path,
    root: Path,
    all_lines: bool,
    ranges_map: dict[str, list[tuple[int, int]]] | None = None,
) -> list[Violation]:
    try:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as e:
        print(f"[code-rules] SKIP {path.name}: {e}")
        return []
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        print(f"[code-rules] WARN {path}: SyntaxError ({e.msg} L{e.lineno}) — 跳过")
        return []

    try:
        rel = str(path.resolve().relative_to(root)).replace("\\", "/")
        rel_is_fallback = False
    except ValueError:
        rel = path.name
        rel_is_fallback = True

    if all_lines:
        added: list[tuple[int, int]] | None = None
    elif ranges_map is None:
        # git 不可用 (fake repo) → 逐文件探测, 与旧行为一致
        added = _added_line_ranges(root, rel)
    else:
        # 批量 map: 文件不在 map 中 = 无新增行 (跳过), None 仅 map 缺失时
        added = ranges_map.get(rel, [])
    violations: list[Violation] = []
    for rule in CODE_RULES:
        if not _rule_matches(rule, rel, apply_filter=not rel_is_fallback):
            continue
        for v in rule.check(tree, content, rel):  # type: ignore[misc]
            if _in_added_ranges(v.line, added):
                violations.append(v)
    return violations


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

_GIT_DIFF_PATTERNS = (".py",)


def _staged_py_files(root: Path) -> list[Path]:
    """git diff --cached --name-only --diff-filter=ACM, 过滤 backend|agent py."""
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    files: list[Path] = []
    for line in diff.stdout.splitlines():
        line = line.strip()
        if not line or not line.endswith(_GIT_DIFF_PATTERNS):
            continue
        if not line.startswith(CODE_DIRS):
            continue
        p = root / line
        if p.is_file():
            files.append(p)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GAF 代码铁律 AST 静态检测")
    parser.add_argument("files", nargs="*", help="要检查的 .py 文件 (pre-commit 传入 staged 文件)")
    parser.add_argument("--root", type=Path, default=REPO_ROOT_DEFAULT, help="repo root")
    parser.add_argument("--no-fail", action="store_true", help="只警告不阻断 (exit 0)")
    parser.add_argument("--all", action="store_true", help="全文件扫描, 忽略 diff 新增行过滤")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not (root / ".git").is_dir():
        print(f"[code-rules] ERROR: not a git repo: {root}", file=_sys.stderr)
        return 2

    files: list[Path] = []
    for f in args.files:
        p = Path(f)
        files.append(p if p.is_absolute() else root / p)
    if not files:
        files = _staged_py_files(root)

    if not files:
        print("[code-rules] PASS: no .py files to check")
        return 0

    # N171: 单次 git diff 解析全部文件的新增行区间 (旧实现每文件 2 次子进程)
    ranges_map = None if args.all else _added_ranges_map(root)

    violations: list[Violation] = []
    for f in files:
        violations.extend(_scan_file(f, root, all_lines=args.all, ranges_map=ranges_map))

    errors = [v for v in violations if v.severity == "error"]
    warns = [v for v in violations if v.severity == "warn"]

    for v in violations:
        level = "ERROR" if v.severity == "error" else "WARN"
        print(f"  [{level}] {v.rule_id} {v.file}:{v.line} — {v.message}")
        print(f"        hint: {v.hint}")

    if errors:
        print(f"[code-rules] FAIL: {len(errors)} error(s), {len(warns)} warn(s)")
    else:
        print(f"[code-rules] PASS: 0 errors, {len(warns)} warn(s)")

    if args.no_fail:
        return 0
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
