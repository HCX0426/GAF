#!/bin/bash
# start_gaf.sh — GAF 启动脚本 (spec §5 方案 A, P2 阶段新增 2026-07-26)
#
# 设计目标 (spec §5)
# ------------------
# 替代 Celery 定时任务, GAF 启动时显式调用一次 startup_checks (清理 + 遗忘机制),
# 然后启动 Django runserver。无系统级调度依赖 (无 cron / 无 Celery beat / 无任务计划程序)。
#
# L0 硬约束 (.skills/rules/env-hardrules.md)
# ----------------------------------------
# 所有 Python 命令必用 `conda run -n gaf python ...`, 不可直接 `python manage.py ...`
# conda 环境名固定为 `gaf`, Python 3.11.15
#
# Usage
# -----
#   bash scripts/start_gaf.sh             # 默认启动 (跑 startup_checks + Django)
#   bash scripts/start_gaf.sh --dry-run   # 只跑 startup_checks dry-run, 不启动 Django
#   bash scripts/start_gaf.sh --skip-checks  # 跳过 startup_checks, 仅启动 Django
#
# Exit codes
# ----------
#   0 - 正常退出 (Django 被 Ctrl+C 终止)
#   1 - startup_checks 失败 (非 dry-run 模式)
#   2 - 配置错误 (非 git repo / conda env 不存在)

set -e

# 解析参数
DRY_RUN=false
SKIP_CHECKS=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --skip-checks) SKIP_CHECKS=true ;;
        *) echo "⚠️ Unknown arg: $arg (supported: --dry-run / --skip-checks)";;
    esac
done

# Step 1: 校验 GAF 仓库根
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -d "$REPO_ROOT/.git" ]]; then
    echo "❌ [start_gaf] $REPO_ROOT is not a git repo"
    exit 2
fi
cd "$REPO_ROOT"

# Step 2: 校验 conda gaf 环境 (L0 硬约束)
if ! conda env list 2>/dev/null | grep -q "^gaf\s"; then
    echo "❌ [start_gaf] conda env 'gaf' not found. Run: conda create -n gaf python=3.11"
    exit 2
fi

echo "[start_gaf] repo: $REPO_ROOT"
echo "[start_gaf] conda env: gaf (Python 3.11.15)"
echo ""

# Step 3: 跑 startup_checks (spec §5.2)
if [[ "$SKIP_CHECKS" == "true" ]]; then
    echo "[start_gaf] ⏭️  Skipping startup_checks (--skip-checks)"
else
    echo "[start_gaf] Running startup checks (spec §5.2)..."
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[start_gaf] Dry-run mode: 只打印不实际修改, 不启动 Django"
        conda run -n gaf python manage.py run_startup_checks --dry-run
        exit 0
    else
        # 非 dry-run: 跑实际清理, 失败则退出
        if ! conda run -n gaf python manage.py run_startup_checks; then
            echo "❌ [start_gaf] startup_checks failed (exit $?)"
            exit 1
        fi
    fi
    echo ""
fi

# Step 4: 启动 Django runserver
echo "[start_gaf] Starting Django runserver..."
echo "[start_gaf] Press Ctrl+C to stop"
echo ""
exec conda run -n gaf python manage.py runserver
