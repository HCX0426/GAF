"""check_big_change.py — B2 治本机制: N151 触发条件客观化

Quantitative 4-dimension check for "big change" to trigger N151 5-step flow:
1. diff line count (> 500 → big)
2. cross-app count (backend/<app>/ changed ≥ 2 apps → big)
3. DB migration files (new migrations/*.py → big)
4. API contract files (urls.py / serializers.py / types/models.ts → big)

Usage:
    python scripts/check_big_change.py              # default: HEAD vs HEAD~1
    python scripts/check_big_change.py --base HEAD~2 --head HEAD
    python scripts/check_big_change.py --json
    python scripts/check_big_change.py --staged     # check staged changes (for pre-commit hook)
    python scripts/check_big_change.py --acknowledge  # write .cache/b2_acknowledged.json (mark B2 run)

Output: JSON {is_big, reasons, dimensions, suggested_flow}

治本机制 (B2, 2026-07-16):
- 旧机制: "架构变更/跨模块" 靠 AI 自决, 灰区大
- 新机制: 脚本量化 4 维度, 客观触发 N151 5 步流程, 无灰区

TD-321 (2026-07-21 spec-83): pre-commit hook 强制
- 加 --staged 模式: 检查 staged 改动 (git diff --cached)
- 加 --acknowledge 模式: 写 .cache/b2_acknowledged.json (含 timestamp + is_big + dimensions)
- pre-commit hook 检查: 若 staged is_big=true, 要求有效的 b2_acknowledged.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# N105 hook infra fix (2026-08-16): GBK console crashes on emoji output
# (UnicodeEncodeError in pre-commit). Force UTF-8 so the hook is locale-safe.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]

# Thresholds (per N151 lesson §4)
DIFF_LINE_THRESHOLD = 500
CROSS_APP_THRESHOLD = 2

# B2 evidence file (TD-321): written by --acknowledge, read by pre-commit hook.
B2_EVIDENCE_FILE = REPO_ROOT / ".cache" / "b2_acknowledged.json"
B2_EVIDENCE_TTL_SECONDS = 30 * 60  # 30 min — evidence must be fresh at commit time

# File patterns that indicate API contract change
API_CONTRACT_PATTERNS = [
    r"backend/.*/urls\.py$",
    r"backend/.*/serializers\.py$",
    r"backend/.*/migrations/\d+_.*\.py$",  # exclude migrations (handled separately)
    r"frontend/src/types/models\.ts$",
    r"frontend/src/api/.*\.ts$",
    r"docs/standards/api-contract\.md$",
]
API_CONTRACT_RE = re.compile("|".join(API_CONTRACT_PATTERNS))

# Migration file pattern (dimension 3, separate from API contract)
MIGRATION_RE = re.compile(r"backend/.*/migrations/\d+_.*\.py$")

# Backend app pattern: backend/<app>/
BACKEND_APP_RE = re.compile(r"^backend/([^/]+)/")


def run_git_diff_names(base: str, head: str) -> List[str]:
    """Return list of changed file paths (one per line)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base}..{head}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"❌ git diff failed: {e}", file=sys.stderr)
        return []


def run_git_diff_stat(base: str, head: str) -> int:
    """Return total diff line count (insertions + deletions)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--shortstat", f"{base}..{head}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        # Output like: " 12 files changed, 300 insertions(+), 50 deletions(-)"
        m = re.search(r"(\d+) insertion", result.stdout)
        ins = int(m.group(1)) if m else 0
        m = re.search(r"(\d+) deletion", result.stdout)
        dele = int(m.group(1)) if m else 0
        return ins + dele
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0


def run_git_staged_names() -> List[str]:
    """Return list of staged file paths (git diff --cached --name-only)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"❌ git diff --cached failed: {e}", file=sys.stderr)
        return []


def run_git_staged_stat() -> int:
    """Return total staged diff line count (insertions + deletions)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--shortstat"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        m = re.search(r"(\d+) insertion", result.stdout)
        ins = int(m.group(1)) if m else 0
        m = re.search(r"(\d+) deletion", result.stdout)
        dele = int(m.group(1)) if m else 0
        return ins + dele
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0


def count_cross_apps(changed_files: List[str]) -> Tuple[int, List[str]]:
    """Count distinct backend/<app>/ directories changed."""
    apps: set = set()
    for f in changed_files:
        m = BACKEND_APP_RE.match(f)
        if m:
            apps.add(m.group(1))
    return len(apps), sorted(apps)


def has_migration_files(changed_files: List[str]) -> Tuple[bool, List[str]]:
    """Check if any new migration files are in the diff."""
    migrations = [f for f in changed_files if MIGRATION_RE.match(f)]
    return bool(migrations), migrations


def has_api_contract_changes(changed_files: List[str]) -> Tuple[bool, List[str]]:
    """Check if any API contract files changed (excluding migrations)."""
    api_files = [
        f for f in changed_files
        if API_CONTRACT_RE.match(f) and not MIGRATION_RE.match(f)
    ]
    return bool(api_files), api_files


def check_big_change(base: str, head: str) -> Dict[str, Any]:
    """Run 4-dimension big-change check.

    Returns dict with:
        is_big: bool — True if any dimension triggers
        reasons: List[str] — human-readable reasons
        dimensions: Dict — raw dimension data
        suggested_flow: str — "N151 5-step" or "normal"
    """
    changed_files = run_git_diff_names(base, head)
    diff_lines = run_git_diff_stat(base, head)

    return _evaluate_big_change(changed_files, diff_lines)


def check_big_change_staged() -> Dict[str, Any]:
    """Run 4-dimension big-change check on STAGED changes (for pre-commit hook)."""
    changed_files = run_git_staged_names()
    diff_lines = run_git_staged_stat()

    return _evaluate_big_change(changed_files, diff_lines)


def _evaluate_big_change(changed_files: List[str], diff_lines: int) -> Dict[str, Any]:
    """Shared evaluation logic for both HEAD-vs-base and staged modes."""
    # Dimension 1: diff line count
    dim1_big = diff_lines > DIFF_LINE_THRESHOLD

    # Dimension 2: cross-app count
    cross_app_count, apps = count_cross_apps(changed_files)
    dim2_big = cross_app_count >= CROSS_APP_THRESHOLD

    # Dimension 3: DB migration files
    has_migrations, migration_files = has_migration_files(changed_files)
    dim3_big = has_migrations

    # Dimension 4: API contract changes
    has_api, api_files = has_api_contract_changes(changed_files)
    dim4_big = has_api

    is_big = dim1_big or dim2_big or dim3_big or dim4_big

    reasons: List[str] = []
    if dim1_big:
        reasons.append(f"diff {diff_lines} 行 > {DIFF_LINE_THRESHOLD} 阈值")
    if dim2_big:
        reasons.append(f"跨 {cross_app_count} backend app (≥ {CROSS_APP_THRESHOLD}): {', '.join(apps)}")
    if dim3_big:
        reasons.append(f"DB 迁移文件 {len(migration_files)} 个: {', '.join(migration_files[:3])}")
    if dim4_big:
        reasons.append(f"API 契约文件 {len(api_files)} 个: {', '.join(api_files[:3])}")

    return {
        "is_big": is_big,
        "reasons": reasons,
        "dimensions": {
            "diff_lines": diff_lines,
            "cross_app_count": cross_app_count,
            "cross_apps": apps,
            "migration_files": migration_files,
            "api_contract_files": api_files,
            "total_changed_files": len(changed_files),
        },
        "suggested_flow": "N151 5-step (架构盘点 → 识别反模式 → A/B/C 备选 → 拒绝双套/最小化 → AI 自决边界)" if is_big else "normal",
    }


def write_b2_evidence(result: Dict[str, Any]) -> Path:
    """Write B2 evidence file (TD-321). Called by --acknowledge mode.

    Evidence schema (JSON):
        timestamp: ISO 8601 string (UTC)
        is_big: bool
        dimensions: Dict — raw dimension data
        reasons: List[str]
    """
    B2_EVIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "is_big": result["is_big"],
        "dimensions": result["dimensions"],
        "reasons": result["reasons"],
    }
    B2_EVIDENCE_FILE.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return B2_EVIDENCE_FILE


def read_b2_evidence() -> Optional[Dict[str, Any]]:
    """Read B2 evidence file. Returns None if missing or invalid."""
    if not B2_EVIDENCE_FILE.is_file():
        return None
    try:
        return json.loads(B2_EVIDENCE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def is_b2_evidence_valid(evidence: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """Check whether B2 evidence is valid (exists + fresh + is_big=true).

    Returns (is_valid, reason). reason is empty string when valid.
    """
    if evidence is None:
        return False, "B2 evidence 文件不存在 (.cache/b2_acknowledged.json)"
    ts_str = evidence.get("timestamp")
    if not ts_str:
        return False, "B2 evidence 缺少 timestamp 字段"
    try:
        ts = _dt.datetime.fromisoformat(ts_str)
    except ValueError:
        return False, f"B2 evidence timestamp 格式无效: {ts_str}"
    age = (_dt.datetime.now(_dt.timezone.utc) - ts).total_seconds()
    if age > B2_EVIDENCE_TTL_SECONDS:
        mins = int(age // 60)
        return False, f"B2 evidence 已过期 ({mins} min 前, TTL {B2_EVIDENCE_TTL_SECONDS // 60} min)"
    if not evidence.get("is_big"):
        return False, "B2 evidence 标记 is_big=false, 但 staged 改动判定为 is_big=true (不一致)"
    return True, ""


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="B2 治本机制: N151 触发条件客观化")
    parser.add_argument("--base", default="HEAD~1", help="git diff base (default: HEAD~1)")
    parser.add_argument("--head", default="HEAD", help="git diff head (default: HEAD)")
    parser.add_argument("--json", action="store_true", help="Output as JSON (default: human-readable)")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check STAGED changes (git diff --cached) instead of HEAD vs HEAD~1. For pre-commit hook.",
    )
    parser.add_argument(
        "--acknowledge",
        action="store_true",
        help="Write .cache/b2_acknowledged.json with current check result (mark B2 as run). "
             "Use after running N151 5-step flow, before commit.",
    )
    args = parser.parse_args(argv)

    # Choose mode: --staged vs default (HEAD vs HEAD~1)
    if args.staged:
        result = check_big_change_staged()
        mode_label = "staged"
    else:
        result = check_big_change(args.base, args.head)
        mode_label = f"{args.base}..{args.head}"

    # --acknowledge: write evidence file and exit
    if args.acknowledge:
        path = write_b2_evidence(result)
        print(f"✅ B2 evidence written: {path}")
        print(f"   is_big: {result['is_big']}")
        if result["reasons"]:
            print(f"   reasons: {'; '.join(result['reasons'])}")
        return 0

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"# B2 大修改判定 ({mode_label})")
        print()
        print(f"## is_big: {'true ✅' if result['is_big'] else 'false'}")
        print(f"## 建议流程: {result['suggested_flow']}")
        print()
        if result["reasons"]:
            print("## 触发原因:")
            for r in result["reasons"]:
                print(f"  - {r}")
        else:
            print("## 触发原因: (无)")
        print()
        d = result["dimensions"]
        print("## 4 维度数据:")
        print(f"  - diff 行数: {d['diff_lines']} (阈值 > {DIFF_LINE_THRESHOLD})")
        print(f"  - 跨 app 数: {d['cross_app_count']} (阈值 ≥ {CROSS_APP_THRESHOLD}) {d['cross_apps']}")
        print(f"  - DB 迁移文件: {len(d['migration_files'])} 个")
        print(f"  - API 契约文件: {len(d['api_contract_files'])} 个")
        print(f"  - 总改动文件: {d['total_changed_files']} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
