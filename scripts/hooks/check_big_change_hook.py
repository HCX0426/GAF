"""check_big_change_hook.py — TD-321 pre-commit hook: 强制 B2 大修改 evidence.

When staged changes constitute a "big change" (per check_big_change.py 4-dimension
check), this hook requires a valid B2 evidence file (.cache/b2_acknowledged.json)
to prove that AI has run N151 5-step flow before committing.

The hook is a no-op (exit 0) when:
- Staged changes are NOT a big change (is_big=false), OR
- B2 evidence file exists, is fresh (< 30 min), and marks is_big=true

Otherwise the commit is blocked with a remediation hint.

Usage
-----
    python scripts/hooks/check_big_change_hook.py            # auto-detect staged
    python scripts/hooks/check_big_change_hook.py --no-fail  # warn only
    python scripts/hooks/check_big_change_hook.py --force    # always check

Exit codes
----------
    0 - not a big change, OR B2 evidence valid
    1 - big change detected but no valid B2 evidence (blocks commit unless --no-fail)
    2 - configuration / argument error

TD-321 (spec-83, 2026-07-21): N151 5-step 流程依赖 AI 自觉; 此 hook 把 B2 治本机制
从"AI 自决"升级为"pre-commit 强制", 防止 AI 跳过 B2 直接 commit 大修改.
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
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

# Import check_big_change (in scripts/, not scripts/hooks/)
from check_big_change import (  # noqa: E402
    check_big_change_staged,
    is_b2_evidence_valid,
    read_b2_evidence,
)

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="TD-321 pre-commit hook: 强制 B2 大修改 evidence",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run the check even when not in a pre-commit context",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Warn-only mode: print warning but do not exit 1",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF repo root (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    _ = repo_root  # future-proof; check_big_change uses REPO_ROOT internally

    # Step 1: evaluate staged changes
    result = check_big_change_staged()

    if not result["is_big"]:
        # Small change — no B2 evidence required
        return 0

    # Step 2: big change detected — require valid B2 evidence
    reasons_str = "; ".join(result["reasons"]) if result["reasons"] else "(no reasons)"
    print(
        f"🔍 B2 大修改检测到: {reasons_str}",
        file=sys.stderr,
    )

    evidence = read_b2_evidence()
    is_valid, fail_reason = is_b2_evidence_valid(evidence)

    if is_valid:
        print("✅ B2 evidence 有效 (.cache/b2_acknowledged.json, is_big=true, fresh)", file=sys.stderr)
        return 0

    # Step 3: invalid evidence — block commit (unless --no-fail)
    print(f"❌ B2 evidence 无效: {fail_reason}", file=sys.stderr)
    print("", file=sys.stderr)
    print("💡 大修改 commit 需先跑 N151 5 步流程 + B2 evidence:", file=sys.stderr)
    print("   1. 跑 N151 5 步流程 (架构盘点 → 识别反模式 → A/B/C 备选 → 拒绝双套/最小化 → AI 自决边界)", file=sys.stderr)
    print("   2. python scripts/check_big_change.py --staged --json  # 查看 staged 改动判定", file=sys.stderr)
    print("   3. python scripts/check_big_change.py --staged --acknowledge  # 写 evidence 文件", file=sys.stderr)
    print("   4. (evidence TTL 30 min, 过期需重跑)", file=sys.stderr)
    print("", file=sys.stderr)
    print("   绕过 (仅紧急情况, 会记录到 bypass log):", file=sys.stderr)
    print("   git commit --no-verify  # 跳过 hook (N110 治标, 不推荐)", file=sys.stderr)

    if args.no_fail:
        print("⚠️ --no-fail 模式: 仅警告, 不阻塞 commit", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
