#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_hardcoded_patterns.py — GAF governance: 硬编码反模式扫描器

Purpose:
    When AI starts a task, this script scans the current git diff for known
    hardcoded anti-patterns (like /api/v2, action_type, etc.) and tells the
    AI which N## rules to proactively load.

    This implements the "症状 → 知识点映射硬触发" from the GAF governance spec.

Features:
    --diff-only  (default: true) — scan only staged/unstaged changes
    --all                        — scan entire repo (for initial setup)

Usage:
    python scripts/governance/scan_hardcoded_patterns.py --diff-only
    python scripts/governance/scan_hardcoded_patterns.py --all

Exit codes:
    0 = scan complete (WARNING only, never blocks commit)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 硬编码反模式 → N## 规则映射表
# 每条规则: pattern (regex), n_id, description, last_hit, hit_count
# ---------------------------------------------------------------------------

SCAN_PATTERNS: list[dict[str, Any]] = [
    {
        "pattern": r"/api/v2",
        "n_id": "N197",
        "description": "URL 归一化",
        "last_hit": "2026-08-06T13:41:38.142254+00:00",
        "hit_count": 1,
    },
    {
        "pattern": r"action_type|next_step|retry_interval|fallback_action",
        "n_id": "N191",
        "description": "Schema 统一",
        "last_hit": "2026-08-06T13:41:38.142254+00:00",
        "hit_count": 1,
    },
    {
        "pattern": r"conda run -n gaf|python manage\.py runserver|python -m pytest",
        "n_id": "N188",
        "description": "Conda 环境",
        "last_hit": "2026-08-06T13:41:38.142254+00:00",
        "hit_count": 1,
    },
    {
        "pattern": r"<<EOF|<<'EOF'|\|\||&&",
        "n_id": "N190",
        "description": "PowerShell shell",
        "last_hit": "2026-08-06T13:41:38.142254+00:00",
        "hit_count": 1,
    },
    {
        "pattern": r"time\.sleep\(|sleep\(\d+\)",
        "n_id": "N196",
        "description": "测试数据",
        "last_hit": "2026-08-06T13:41:38.142254+00:00",
        "hit_count": 1,
    },
    {
        "pattern": r"grep|head\s|tail\s|sed\s|awk\s",
        "n_id": "N190",
        "description": "Windows 上的 Unix 命令",
        "last_hit": "2026-08-06T13:41:38.142254+00:00",
        "hit_count": 1,
    },
]


def _get_diff_text() -> str:
    """获取当前 git diff（staged + unstaged）文本。"""
    parts: list[str] = []

    try:
        unstaged = subprocess.run(
            ["git", "diff", "--no-color"],
            capture_output=True,
            text=True, encoding="utf-8",
            timeout=30,
        )
        if unstaged.stdout:
            parts.append(unstaged.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    try:
        staged = subprocess.run(
            ["git", "diff", "--cached", "--no-color"],
            capture_output=True,
            text=True, encoding="utf-8",
            timeout=30,
        )
        if staged.stdout:
            parts.append(staged.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return "\n".join(parts)


def _get_all_text(repo_root: Path) -> str:
    """扫描整个仓库，返回所有文件文本拼接。"""
    parts: list[str] = []
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist", "build"}

    for file_path in repo_root.rglob("*"):
        if not file_path.is_file():
            continue
        rel_parts = file_path.relative_to(repo_root).parts
        if any(p in skip_dirs for p in rel_parts):
            continue
        if file_path.suffix.lower() in {
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
            ".woff", ".woff2", ".ttf", ".eot",
            ".pyc", ".pyo", ".so", ".dll", ".exe",
            ".pdf", ".zip", ".tar", ".gz", ".lock",
        }:
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
            parts.append(text)
        except (UnicodeDecodeError, OSError):
            continue

    return "\n".join(parts)


def scan_text(text: str) -> list[dict[str, Any]]:
    """扫描文本，返回所有命中记录。"""
    hits: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for rule in SCAN_PATTERNS:
        pattern = rule["pattern"]
        regex = re.compile(pattern)
        matched = False

        for match in regex.finditer(text):
            matched = True
            match_text = match.group(0)
            hits.append({
                "match": match_text,
                "n_id": rule["n_id"],
                "description": rule["description"],
            })
            print(f"[HIT] Found hardcoded \"{match_text}\" → 加载 {rule['n_id']} ({rule['description']})")

        if matched:
            rule["last_hit"] = now
            rule["hit_count"] += 1

    return hits


def _print_summary(hits: list[dict[str, Any]]) -> None:
    """打印扫描摘要。"""
    if not hits:
        print("[OK] 无硬编码模式命中")
        return

    n_ids = sorted(set(h["n_id"] for h in hits))
    unique_hits = len(set(h["match"] for h in hits))
    total_hits = len(hits)

    print()
    print("=== Hardcoded Pattern Scan Summary ===")
    print(f"Total hits  : {total_hits}")
    print(f"Unique      : {unique_hits}")
    print(f"Rules to load: {', '.join(n_ids)}")

    for n_id in n_ids:
        related = [h for h in hits if h["n_id"] == n_id]
        descs = sorted(set(h["description"] for h in related))
        print(f"  {n_id} ({', '.join(descs)}): {len(related)} hit(s)")


def _persist_pattern_stats() -> None:
    """将扫描命中统计写回源文件。"""
    import ast

    file_path = Path(__file__).resolve()
    content = file_path.read_text(encoding="utf-8")

    lines = content.split("\n")
    new_lines = []
    in_list = False
    bracket_depth = 0
    idx = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        if "SCAN_PATTERNS:" in stripped or "SCAN_PATTERNS = [" in stripped:
            in_list = True
            new_lines.append(line)
            continue
        if in_list and stripped == "]":
            in_list = False
            new_lines.append(line)
            continue

        if not in_list:
            new_lines.append(line)
            continue

        new_line = line

        for p in SCAN_PATTERNS:
            if p["hit_count"] > 0:
                old_hit = f'"hit_count": 1'
                new_hit = f'"hit_count": {p["hit_count"]}'
                if old_hit in new_line and p["hit_count"] > 0:
                    new_line = new_line.replace(old_hit, new_hit)

                old_last = '"last_hit": "2026-08-06T13:41:38.142254+00:00"'
                new_last = f'"last_hit": "{p["last_hit"]}"'
                if old_last in new_line and p["last_hit"] is not None:
                    new_line = new_line.replace(old_last, new_last)

        new_lines.append(new_line)

    new_content = "\n".join(new_lines)
    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--diff-only",
        action="store_true",
        default=True,
        help="Scan only staged/unstaged changes (default: true)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Scan entire repo (for initial setup)",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        default=False,
        help="Don't write hit_count/last_hit back to file",
    )
    args = parser.parse_args(argv)

    if args.all:
        repo_root = Path.cwd()
        print(f"[SCAN] Scanning entire repo: {repo_root}")
        text = _get_all_text(repo_root)
    else:
        print("[SCAN] Scanning git diff only (staged + unstaged)")
        text = _get_diff_text()

    if not text.strip():
        print("[OK] 无硬编码模式命中 (diff 为空)")
        return 0

    hits = scan_text(text)
    _print_summary(hits)

    if not args.no_persist and any(p["hit_count"] > 0 for p in SCAN_PATTERNS):
        _persist_pattern_stats()
        print("[OK] 扫描统计已写回 scan_hardcoded_patterns.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())