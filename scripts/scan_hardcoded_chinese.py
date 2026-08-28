#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_hardcoded_chinese.py — Phase 2 / TD-335 #3: 扫描前端硬编码中文字符串

Purpose:
    Walk frontend/src, count Chinese-character occurrences per file, and
    classify each occurrence into one of three buckets:

    A. i18n eligible    : 中文字符串出现在 JSX/TS 运行时上下文，需要
                           抽取到 i18n 资源文件 (frontend/src/i18n/locales/*.ts)
    B. Business palette  : 字段名/枚举值/测试 fixture 中的中文 (合法保留,
                           例如 account_type="手机"). 不强制迁移.
    C. Test / docs only  : 测试 fixture / 注释中的中文 (优先级最低)

    The script is intentionally read-only: it never modifies source.
    Output goes to stdout + a JSON report for CI / AI consumption.

Usage:
    python scripts/scan_hardcoded_chinese.py             # frontend/src 默认路径
    python scripts/scan_hardcoded_chinese.py --dir frontend/src --json

Exit codes:
    0 = scan complete (even if findings exist)
    1 = scan failed (missing dependency / bad dir)

Hard constraints:
    N192: 必须区分"可迁移的 UI 文案"与"合法业务字段", 不能一刀切.
    N193: 发现的 i18n 欠账必须纳入当前 spec, 不能作为"遗留建议".
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 匹配规则
# ---------------------------------------------------------------------------

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")

# 判定"UI 文案"的启发式: 字符串附近有 JSX / hook / event handler 上下文
# 而非简单的 key/value/注释。
_STRING_LITERAL_RE = re.compile(
    r"""['"`]([^'"`\n]*[\u4e00-\u9fff][^'"`\n]*)['"`]"""
)

# 已知 i18n key 引用: t('...') / $t('...') / useI18n()
_I18N_CALL_RE = re.compile(r"\b(?:t|useI18n)\s*\(")

# 合法业务调色板: 字段名 / 枚举值 / 注释
_BUSINESS_PALETTE_HINTS = [
    # i18n 资源文件本身
    r"i18n[\\/]locales[\\/]",
    # 注释
    r"^\s*//",
    r"^\s*/\*",
    # 常见业务字段 (account_type / task_status 等)
    r"(?:type|status|role|source|mode|label|category)\s*[:=]\s*['\"]",
]


@dataclass
class Finding:
    file: str
    line: int
    text: str
    bucket: str  # A / B / C
    reason: str = ""


@dataclass
class Report:
    files_scanned: int = 0
    total_chinese_chars: int = 0
    bucket_counts: Counter = field(default_factory=Counter)
    findings: list[Finding] = field(default_factory=list)


def classify_line(line: str, file_path: Path) -> tuple[str, str]:
    """Classify a single line of Chinese text into bucket A/B/C."""
    # C: 测试 / 文档
    if file_path.parent.name == "__tests__" or file_path.name.endswith(".test.tsx") or file_path.name.endswith(".test.ts"):
        return "C", "test file"

    # B: 合法业务调色板 / i18n 资源文件
    for hint in _BUSINESS_PALETTE_HINTS:
        if re.search(hint, str(file_path).replace("\\", "/")):
            return "B", f"matched pattern: {hint}"

    # A: UI 文案候选 — 中文字符串在运行时上下文
    if _STRING_LITERAL_RE.search(line):
        # 如果同行已经用 t('...') 包裹, 说明已 i18n 化, 归 B
        if _I18N_CALL_RE.search(line):
            return "B", "i18n call already"
        return "A", "string literal in runtime code"

    # 默认: 注释或其他, 归 B (保留)
    return "B", "non-literal context (comment / identifier)"


def scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        print(f"! skip {path}: {exc}", file=sys.stderr)
        return findings

    for lineno, line in enumerate(text.splitlines(), start=1):
        if not _CHINESE_RE.search(line):
            continue
        bucket, reason = classify_line(line, path)
        # A 类 (i18n 候选) 记录每条; B/C 类汇总
        finding = Finding(
            file=str(path).replace("\\", "/"),
            line=lineno,
            text=line.strip()[:120],
            bucket=bucket,
            reason=reason,
        )
        findings.append(finding)
    return findings


def scan_directory(root: Path) -> Report:
    report = Report()
    for pattern in ("*.ts", "*.tsx"):
        for file_path in root.rglob(pattern):
            # 跳过 node_modules / .git / __tests__ 仅在分类时标记
            rel = str(file_path).replace("\\", "/")
            if "node_modules" in rel or "/.git/" in rel:
                continue
            report.files_scanned += 1
            file_findings = scan_file(file_path)
            report.findings.extend(file_findings)
            report.bucket_counts.update(f.bucket for f in file_findings)

    return report


def print_summary(report: Report) -> None:
    total = sum(report.bucket_counts.values())
    print(f"\n=== Hardcoded Chinese Scan Summary ===")
    print(f"Files scanned : {report.files_scanned}")
    print(f"Total matches : {total}")
    print(f"  A (i18n eligible UI text) : {report.bucket_counts.get('A', 0)}")
    print(f"  B (business palette / ok)  : {report.bucket_counts.get('B', 0)}")
    print(f"  C (test / doc / low pri)  : {report.bucket_counts.get('C', 0)}")
    print()
    print("-- Top A candidates (first 25) --")
    a_findings = [f for f in report.findings if f.bucket == "A"]
    for f in a_findings[:25]:
        print(f"{f.file}:{f.line}  {f.text[:80]}")
    if len(a_findings) > 25:
        print(f"... and {len(a_findings) - 25} more (see --json report)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="frontend/src", help="root dir to scan (default: frontend/src)")
    parser.add_argument("--json", action="store_true", help="also write JSON report to stdout")
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    if not root.exists():
        print(f"ERROR: directory not found: {root}", file=sys.stderr)
        return 1

    report = scan_directory(root)
    print_summary(report)

    if args.json:
        payload = {
            "files_scanned": report.files_scanned,
            "bucket_counts": dict(report.bucket_counts),
            "findings": [asdict(f) for f in report.findings if f.bucket == "A"],
        }
        print("\n=== JSON_REPORT_BEGIN ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("=== JSON_REPORT_END ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
