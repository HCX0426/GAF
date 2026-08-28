#!/bin/bash
# gaf-commit.sh — v8.3.1 commit wrapper for the GAF knowledge system.
#
# Wraps `git commit` to:
#   1. Verify that a session is active (24h TTL, cross-platform binding).
#   2. Require `GAF_BYPASS_REASON` whenever `--no-verify` is passed.
#      v8.3.1 removed the "colleague signoff + 3/day cap" model (N82)
#      in favour of "self-sign bypass + audit log + 7-day review".
#   3. Append every commit (and every bypass) to `.gaf_audit.log`
#      so `bypass_weekly_review.py` can mine it.
#   4. Append a `COMMIT` line to `.pre-commit-hooks.log` so the
#      skip-rate monitor (check_skip_rate.py) has denominator data.
#
# Exit codes:
#   0 — git commit succeeded (or nothing to commit, propagated).
#   1 — session missing / bypass reason missing / git commit failed.
#   2 — misuse (no args, etc.).

set -e

# Resolve repo root regardless of where the user invokes us from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Resolve a usable Python interpreter (N188 conda gaf hard rule).
# Priority: $GAF_PYTHON env var > conda gaf env > PATH python.
# Avoids the Windows Store python stub (exit 9009) silently failing checks.
GAF_PYTHON_BIN="${GAF_PYTHON:-}"
if [[ -z "$GAF_PYTHON_BIN" ]]; then
    for candidate in \
        "$HOME/miniconda3/envs/gaf/bin/python" \
        "$HOME/miniconda3/envs/gaf/python.exe" \
        "/d/code/environment/conda/envs/gaf/python.exe" \
        "/c/Users/$USERNAME/miniconda3/envs/gaf/python.exe"; do
        if [[ -x "$candidate" ]]; then
            GAF_PYTHON_BIN="$candidate"
            break
        fi
    done
fi
if [[ -z "$GAF_PYTHON_BIN" ]]; then
    GAF_PYTHON_BIN="python"
fi

AUDIT_LOG="$REPO_ROOT/.gaf_audit.log"
HOOK_LOG="$REPO_ROOT/.pre-commit-hooks.log"
SESSION_FILE="$REPO_ROOT/.trash/.gaf_session_active"

# ---------------------------------------------------------------------------
# 0. Argument sanity
# ---------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
    echo "❌ gaf-commit.sh requires git commit args (use -- for separator)."
    echo "   example: gaf scripts/gaf-commit.sh -m 'fix: ...'"
    exit 2
fi

# ---------------------------------------------------------------------------
# 1. Session active check (N58 cross-platform binding)
# ---------------------------------------------------------------------------
if [[ ! -f "$SESSION_FILE" ]]; then
    echo "❌ .trash/.gaf_session_active missing: $SESSION_FILE"
    echo "   请先: bash scripts/gaf_init.sh"
    exit 1
fi

if ! "$GAF_PYTHON_BIN" scripts/bootstrap/check_session_active.py --check >/dev/null 2>&1; then
    echo "❌ session 验证失败"
    echo "   请重新: bash scripts/gaf_init.sh"
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Bypass interception (v8.3.1 / N82)
# ---------------------------------------------------------------------------
BYPASS_REASON="${GAF_BYPASS_REASON:-}"
WANTS_BYPASS=0
for arg in "$@"; do
    if [[ "$arg" == "--no-verify" ]]; then
        WANTS_BYPASS=1
        break
    fi
done

if [[ $WANTS_BYPASS -eq 1 ]]; then
    if [[ -z "$BYPASS_REASON" ]]; then
        echo "⚠️  --no-verify 需要说明原因（N82 修复）:"
        echo "   export GAF_BYPASS_REASON='<一句话原因>'"
        echo "   例: GAF_BYPASS_REASON='紧急修复：pre-commit gaf-sync 误报 sync timeout' \\"
        echo "       bash scripts/gaf-commit.sh --no-verify -m 'hotfix: ...'"
        echo ""
        echo "❌ commit 已拒绝（缺 reason）"
        exit 1
    fi

    GIT_USER="$(git config user.email 2>/dev/null || echo 'unknown')"
    TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    # Sanitise: keep reason on a single line, strip control chars.
    SAFE_REASON="$(printf '%s' "$BYPASS_REASON" | tr '\n' ' ' | tr -d '\r')"
    SAFE_ARGS="$(printf '%q ' "$@" | tr '\n' ' ')"

    mkdir -p "$(dirname "$AUDIT_LOG")"
    echo "BYPASS ts=$TS user=$GIT_USER reason=$SAFE_REASON args=$SAFE_ARGS" >> "$AUDIT_LOG"
    echo "⚠️  v8.3.1 允许 --no-verify（已写 audit log，7 天复盘会扫到）"
fi

# ---------------------------------------------------------------------------
# 3. Audit the actual commit attempt (denominator for skip-rate)
# ---------------------------------------------------------------------------
mkdir -p "$(dirname "$HOOK_LOG")"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SAFE_ARGS="$(printf '%q ' "$@" | tr '\n' ' ')"
echo "COMMIT ts=$TS args=$SAFE_ARGS" >> "$HOOK_LOG"

# ---------------------------------------------------------------------------
# 4. Hand off to git commit
# ---------------------------------------------------------------------------
# 🆕 v8.4 N105 修复: 检测到 --no-verify 时 echo 警告
# 根因: `exec git commit "$@"` 透传 --no-verify, 但 pre-commit framework 的
# hook 触发与 --no-verify 是分开的, gaf-sync 仍会跑并修改文件让 commit 失败。
# 修复: 警告用户已知 bug, 建议直接用 `git commit --no-verify`。
for arg in "$@"; do
    if [[ "$arg" == "--no-verify" ]]; then
        echo "⚠️  N105 已知透传 bug: gaf-commit.sh --no-verify 不会真跳过 hook,"
        echo "   gaf-sync hook 仍会跑并可能修改 auto-maintained 文件 (e.g. docs-index.md)."
        echo "   建议: 绕过 gaf-commit.sh, 直接用:"
        echo "     git commit --no-verify -m '...'"
        echo "   (此警告不阻断 commit, 仅提醒)"
        break
    fi
done

exec git commit "$@"
