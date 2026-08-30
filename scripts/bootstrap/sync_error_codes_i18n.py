"""sync_error_codes_i18n.py — 后端 ErrorCode ↔ 前端 i18n error.codes.* 同步工具.

Task 5.2 (P4, 2026-07-29, N193 已知限制解决): 后端新增 ErrorCode 时前端不会自动同步,
本脚本扫描后端 ``backend/gaf_core/error_codes.py`` 与 agent ``worker/src/core/error_codes.py``
中定义的 ``ErrorCode`` (IntEnum) / ``NodeErrorCode`` (StrEnum) 成员, 与前端
``frontend/src/i18n/locales/common.ts`` 中的 ``error.codes.*`` key 对比, 报告
缺失 / 多余的 key, 并在 ``--update`` 模式下自动补全缺失的 key (用源码行内注释作为
zh-CN 默认文案, 其他 locale 用 ``<TODO: translate>`` 占位, 由人工后续翻译).

使用方式:
    # 默认: 扫描 + 报告差异 (CI / hook 友好, exit code 0=一致, 1=有差异)
    conda run -n gaf python scripts/bootstrap/sync_error_codes_i18n.py

    # 只检查, 不修改文件 (与默认等价, 显式 flag)
    conda run -n gaf python scripts/bootstrap/sync_error_codes_i18n.py --check

    # 自动补全缺失的 error.codes.* key (不删除已有 key, 避免误删翻译)
    conda run -n gaf python scripts/bootstrap/sync_error_codes_i18n.py --update

    # 输出 JSON 格式报告 (供 CI 消费)
    conda run -n gaf python scripts/bootstrap/sync_error_codes_i18n.py --json

设计原则:
- 只扫描源码, 不 import 后端模块 (避免 conda 环境依赖, 兼容 CI)
- AST + regex 提取枚举成员 + 行内注释 (注释作为 zh-CN 默认文案)
- 不破坏人工翻译: 已有的 error.codes.* key 一律保留, 只追加缺失项
- 4 locale 全覆盖: zh-CN / en-US / ja-JP / ko-KR
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
import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

REPO_ROOT = _Path(__file__).resolve().parents[2]
BACKEND_ERROR_CODES = REPO_ROOT / "backend" / "gaf_core" / "error_codes.py"
WORKER_ERROR_CODES = REPO_ROOT / "worker" / "src" / "core" / "error_codes.py"
FRONTEND_COMMON_TS = REPO_ROOT / "frontend" / "src" / "i18n" / "locales" / "common.ts"

LOCALES = ("zh-CN", "en-US", "ja-JP", "ko-KR")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class EnumMember:
    """枚举成员: name + value + 行内注释 (作为 zh-CN 默认文案)."""

    name: str
    value: str  # IntEnum 也存为字符串 (如 "1001"), 与前端 key 后缀一致
    comment: str = ""  # 源码行内注释, 已 strip "#" 和空白
    enum_class: str = ""  # "ErrorCode" 或 "NodeErrorCode"
    source_file: str = ""  # "backend" 或 "agent"


@dataclass
class SyncReport:
    """同步差异报告."""

    backend_members: List[EnumMember] = field(default_factory=list)
    agent_members: List[EnumMember] = field(default_factory=list)
    # 前端每个 locale 已有的 error.codes.* key 集合
    frontend_keys: Dict[str, set] = field(default_factory=lambda: {loc: set() for loc in LOCALES})
    # 期望的 key 集合 (从后端 + agent 枚举推导)
    expected_keys: set = field(default_factory=set)
    # 每个 locale 缺失的 key
    missing: Dict[str, List[str]] = field(default_factory=lambda: {loc: [] for loc in LOCALES})
    # 每个 locale 多余的 key (前端有但后端没有, 可能是废弃枚举)
    extra: Dict[str, List[str]] = field(default_factory=lambda: {loc: [] for loc in LOCALES})

    def has_diff(self) -> bool:
        return any(self.missing[loc] for loc in LOCALES) or any(self.extra[loc] for loc in LOCALES)


# ---------------------------------------------------------------------------
# 后端 / agent 枚举扫描
# ---------------------------------------------------------------------------


def _parse_enum_file(path: Path, source_label: str) -> List[EnumMember]:
    """用 AST + 行扫描解析 enum 文件, 提取 ErrorCode / NodeErrorCode 成员 + 行内注释.

    实现策略:
    1. AST 找到 ClassDef 节点 (ErrorCode / NodeErrorCode)
    2. 对每个 Assign 节点 (NAME = VALUE), 取行号
    3. 在源码行末尾找 # 注释 (容许中间空白)
    """
    if not path.exists():
        return []

    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines()
    members: List[EnumMember] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name not in ("ErrorCode", "NodeErrorCode"):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                continue
            name = stmt.targets[0].id
            # value 可能是 ast.Constant (IntEnum 数字 / StrEnum 字符串) 或 ast.Constant .value
            value_node = stmt.value
            if isinstance(value_node, ast.Constant):
                raw_value = value_node.value
            else:
                # 跳过复杂表达式 (如 NodeErrorCode 的 NAME = "NAME" 已是 Constant)
                continue
            value = str(raw_value)
            # 提取行内注释: 行末 # xxx
            line_idx = stmt.lineno - 1
            if 0 <= line_idx < len(lines):
                line = lines[line_idx]
                # 找到 # 不在字符串内的位置 — 简化: 用 split, 因 enum 赋值行不会含 "#" 字符串字面量
                # (NodeErrorCode 的值是 "NO_MATCH" 这种, 不含 #)
                if "#" in line:
                    comment_part = line.split("#", 1)[1].strip()
                else:
                    comment_part = ""
            else:
                comment_part = ""
            members.append(
                EnumMember(
                    name=name,
                    value=value,
                    comment=comment_part,
                    enum_class=node.name,
                    source_file=source_label,
                )
            )
    return members


def scan_backend_and_agent() -> Tuple[List[EnumMember], List[EnumMember]]:
    """扫描 backend + agent 两份 error_codes.py, 返回成员列表.

    Note: backend 与 agent 各自定义 NodeErrorCode (同名字段, 互为镜像), 取并集.
    ErrorCode (IntEnum) 仅 backend 定义.
    """
    backend = _parse_enum_file(BACKEND_ERROR_CODES, "backend")
    agent = _parse_enum_file(WORKER_ERROR_CODES, "agent")
    return backend, agent


# ---------------------------------------------------------------------------
# 前端 i18n 扫描
# ---------------------------------------------------------------------------


_FRONTEND_KEY_RE = re.compile(r"'(error\.codes\.[^']+)'\s*:\s*'([^']*)'")


def scan_frontend_i18n() -> Dict[str, set]:
    """扫描 frontend/src/i18n/locales/common.ts, 返回每个 locale 已有的 error.codes.* key 集合.

    common.ts 结构: 每个语言段是 'zh-CN': { ... 'error.codes.X': '...', ... } 形式.
    本函数用 regex 直接提取所有 'error.codes.X' 行, 再按 locale 段切分.
    """
    if not FRONTEND_COMMON_TS.exists():
        return {loc: set() for loc in LOCALES}

    src = FRONTEND_COMMON_TS.read_text(encoding="utf-8")
    # 切分 locale 段: 'zh-CN': { ... }, 'en-US': { ... }, ...
    # 简化: 逐 locale 找 'LOC': { 起始位置, 然后到下一个 'LOC': { 或文件结束
    result: Dict[str, set] = {loc: set() for loc in LOCALES}
    for loc in LOCALES:
        # 匹配 'LOC': { ... } — 用非贪婪 + 提前断言下一个 locale
        # 简单方案: 找 'LOC': { 起始, 然后截取到下一个 'zh-CN'/'en-US'/'ja-JP'/'ko-KR' 之前的 }
        pattern = re.compile(
            r"'" + re.escape(loc) + r"'\s*:\s*\{([\s\S]*?)\n\s*\},?\s*\n",
            re.MULTILINE,
        )
        match = pattern.search(src)
        if not match:
            continue
        block = match.group(1)
        for m in _FRONTEND_KEY_RE.finditer(block):
            result[loc].add(m.group(1))
    return result


# ---------------------------------------------------------------------------
# 同步逻辑
# ---------------------------------------------------------------------------


def build_expected_keys(backend: List[EnumMember], agent: List[EnumMember]) -> set:
    """从 backend + agent 枚举成员推导期望的 error.codes.* key 集合.

    规则:
    - ErrorCode (IntEnum): key 后缀是数字 value (如 error.codes.1001)
    - NodeErrorCode (StrEnum): key 后缀是 name (如 error.codes.NO_MATCH), 与 value 同值
    - backend 与 agent 的 NodeErrorCode 取并集 (理论上完全一致, 取并集兜底)
    """
    expected = set()
    for m in backend + agent:
        if m.enum_class == "ErrorCode":
            expected.add(f"error.codes.{m.value}")
        elif m.enum_class == "NodeErrorCode":
            expected.add(f"error.codes.{m.name}")
    return expected


def build_report() -> SyncReport:
    """扫描后端 + agent + 前端, 构建 SyncReport."""
    backend, agent = scan_backend_and_agent()
    frontend_keys = scan_frontend_i18n()
    expected = build_expected_keys(backend, agent)

    report = SyncReport(
        backend_members=backend,
        agent_members=agent,
        frontend_keys=frontend_keys,
        expected_keys=expected,
    )

    for loc in LOCALES:
        report.missing[loc] = sorted(expected - frontend_keys[loc])
        report.extra[loc] = sorted(frontend_keys[loc] - expected)
    return report


def _format_comment_as_zh(member: EnumMember) -> str:
    """把源码行内注释转成 zh-CN 默认文案.

    注释形如 "模板/特征匹配未找到" (已是中文), 直接返回;
    若注释为空, 返回 member.name 替换下划线为空格 (作为 fallback).
    """
    if member.comment:
        return member.comment
    return member.name.replace("_", " ")


def _format_name_as_en(member: EnumMember) -> str:
    """用 enum name 作为 en-US 占位文案 (Title Case + 空格)."""
    return member.name.replace("_", " ").title()


# ---------------------------------------------------------------------------
# --update 模式: 自动补全缺失 key
# ---------------------------------------------------------------------------


def _find_locale_block_range(src: str, loc: str) -> Optional[Tuple[int, int]]:
    """返回 common.ts 中 'LOC': { ... } 段在源码中的 [start, end) 字符 offset."""
    pattern = re.compile(
        r"(\s*)'" + re.escape(loc) + r"'\s*:\s*\{",
        re.MULTILINE,
    )
    m = pattern.search(src)
    if not m:
        return None
    start = m.end()  # 跳过 {
    # 从 start 往后找匹配的 } (不嵌套, 简单匹配到下一个独立行 })
    # common.ts 的 locale block 结束是 "\n  }," 或 "\n  }\n"
    end_pattern = re.compile(r"\n(\s*)\},?\s*\n")
    end_m = end_pattern.search(src, start)
    if not end_m:
        return None
    return start, end_m.start()


def _insert_keys_into_locale_block(
    src: str, loc: str, keys_to_add: List[Tuple[str, str]]
) -> str:
    """在 locale block 末尾 (} 之前) 插入 error.codes.X 行.

    keys_to_add: [(key, value), ...] 已按 key 排序.
    """
    rng = _find_locale_block_range(src, loc)
    if rng is None:
        return src  # 找不到段, 不改
    start, end = rng
    # 找到 block 内最后一个非空行结束位置 (在 end 之前)
    # 简化: 直接在 end 位置插入, 用 4 空格缩进
    block_content = src[start:end]
    # 找到 block 最后一个 "," — 若上一行已有逗号则直接追加, 否则需要补逗号
    # 简化策略: 把新行追加到 block_content 末尾, 每行格式为 "    'key': 'value',\n"
    # 检查 block_content 最后一个非空白字符是否为 ","
    stripped = block_content.rstrip()
    if not stripped.endswith(","):
        # 最后一行缺逗号, 补一个
        # 找到最后一个非空白行的位置
        last_newline = block_content.rfind("\n")
        if last_newline >= 0:
            # 在最后一个非空白行末尾补逗号
            # 实际: 找到 stripped 末尾在 block_content 中的位置
            # 简化: 直接替换 block_content 为 stripped + "," + 余下空白
            tail_whitespace = block_content[len(stripped):]
            block_content = stripped + "," + tail_whitespace
    # 构造新行
    new_lines = []
    for key, value in keys_to_add:
        # 转义 value 中的单引号
        escaped_value = value.replace("\\", "\\\\").replace("'", "\\'")
        new_lines.append(f"    '{key}': '{escaped_value}',\n")
    # 插入到 block_content 末尾 (在 tail_whitespace 之前)
    # 重新计算 stripped + tail
    stripped2 = block_content.rstrip()
    tail2 = block_content[len(stripped2):]
    new_block = stripped2 + "\n" + "".join(new_lines) + tail2.lstrip("\n")
    return src[:start] + new_block + src[end:]


def update_frontend_i18n(report: SyncReport) -> bool:
    """自动补全缺失的 error.codes.* key.

    策略:
    - zh-CN: 用源码行内注释作为默认文案
    - en-US: 用 enum name Title Case 作为占位文案
    - ja-JP / ko-KR: 用 "<TODO: translate> <name>" 占位
    - 已有 key 一律不修改 (保留人工翻译)
    - 不删除 extra key (避免误删)

    Returns: True 若文件被修改.
    """
    if not FRONTEND_COMMON_TS.exists():
        print(f"[ERROR] frontend i18n file not found: {FRONTEND_COMMON_TS}")
        return False

    src = FRONTEND_COMMON_TS.read_text(encoding="utf-8")
    original_src = src

    # 构建 name → EnumMember 索引 (后端优先, 因为后端有注释)
    name_to_member: Dict[str, EnumMember] = {}
    for m in report.backend_members + report.agent_members:
        if m.name not in name_to_member:
            name_to_member[m.name] = m
    # value (IntEnum 数字) → member (用于 ErrorCode 数字 key)
    value_to_member: Dict[str, EnumMember] = {}
    for m in report.backend_members:
        if m.enum_class == "ErrorCode":
            value_to_member[m.value] = m

    for loc in LOCALES:
        missing = report.missing[loc]
        if not missing:
            continue
        keys_to_add: List[Tuple[str, str]] = []
        for key in missing:
            # key 形如 "error.codes.1001" (ErrorCode) 或 "error.codes.NO_MATCH" (NodeErrorCode)
            suffix = key[len("error.codes."):]
            if suffix.isdigit():
                # ErrorCode 数字 key
                member = value_to_member.get(suffix)
                if member is None:
                    value = f"<TODO: ErrorCode {suffix}>"
                else:
                    if loc == "zh-CN":
                        value = _format_comment_as_zh(member)
                    elif loc == "en-US":
                        value = _format_name_as_en(member)
                    else:
                        value = f"<TODO: translate> {member.name}"
            else:
                # NodeErrorCode 字符串 key (name == value)
                member = name_to_member.get(suffix)
                if member is None:
                    value = f"<TODO: NodeErrorCode {suffix}>"
                else:
                    if loc == "zh-CN":
                        value = _format_comment_as_zh(member)
                    elif loc == "en-US":
                        value = _format_name_as_en(member)
                    else:
                        value = f"<TODO: translate> {member.name}"
            keys_to_add.append((key, value))
        # 按 key 排序, 让数字 key 在前, 字符串 key 在后
        keys_to_add.sort(key=lambda x: (not x[0][len("error.codes."):].isdigit(), x[0]))
        src = _insert_keys_into_locale_block(src, loc, keys_to_add)
        print(f"[UPDATE] {loc}: appended {len(keys_to_add)} missing error.codes.* keys")

    if src != original_src:
        FRONTEND_COMMON_TS.write_text(src, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------


def print_report(report: SyncReport) -> None:
    """打印人类可读的差异报告."""
    print("=" * 70)
    print("ErrorCode ↔ frontend i18n sync report")
    print("=" * 70)
    print(f"Backend members: {len(report.backend_members)} "
          f"(ErrorCode={sum(1 for m in report.backend_members if m.enum_class == 'ErrorCode')}, "
          f"NodeErrorCode={sum(1 for m in report.backend_members if m.enum_class == 'NodeErrorCode')})")
    print(f"Agent members:   {len(report.agent_members)} (NodeErrorCode mirror)")
    print(f"Expected keys:   {len(report.expected_keys)}")
    print()
    for loc in LOCALES:
        print(f"  [{loc}] frontend has {len(report.frontend_keys[loc])} error.codes.* keys")
        if report.missing[loc]:
            print(f"    MISSING ({len(report.missing[loc])}):")
            for key in report.missing[loc]:
                print(f"      - {key}")
        if report.extra[loc]:
            print(f"    EXTRA ({len(report.extra[loc])}): (前端有但后端无, 可能是废弃枚举)")
            for key in report.extra[loc]:
                print(f"      - {key}")
        if not report.missing[loc] and not report.extra[loc]:
            print("    ✅ in sync")
    print("=" * 70)


def print_json_report(report: SyncReport) -> None:
    """打印 JSON 格式报告 (CI 友好)."""
    payload = {
        "backend_members": [
            {"name": m.name, "value": m.value, "comment": m.comment, "class": m.enum_class}
            for m in report.backend_members
        ],
        "agent_members": [
            {"name": m.name, "value": m.value, "comment": m.comment, "class": m.enum_class}
            for m in report.agent_members
        ],
        "expected_keys": sorted(report.expected_keys),
        "frontend_keys": {loc: sorted(report.frontend_keys[loc]) for loc in LOCALES},
        "missing": {loc: report.missing[loc] for loc in LOCALES},
        "extra": {loc: report.extra[loc] for loc in LOCALES},
        "has_diff": report.has_diff(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync backend ErrorCode / NodeErrorCode with frontend i18n error.codes.* keys.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: only report diffs, do not modify files (default behavior).",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update mode: auto-append missing error.codes.* keys to frontend i18n file. "
             "zh-CN uses source comment; en-US uses enum name; ja-JP/ko-KR use <TODO> placeholder.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON report (for CI consumption).",
    )
    args = parser.parse_args()

    report = build_report()

    if args.json:
        print_json_report(report)
    else:
        print_report(report)

    if args.update:
        updated = update_frontend_i18n(report)
        if updated:
            print("[OK] frontend/src/i18n/locales/common.ts updated with missing keys.")
            # 重新扫描确认
            new_report = build_report()
            if not args.json:
                print()
                print("[After update]")
                print_report(new_report)
        else:
            print("[SKIP] no missing keys to append (or update failed).")

    # exit code: 0 = in sync, 1 = has diff
    return 1 if report.has_diff() else 0


if __name__ == "__main__":
    raise SystemExit(main())
