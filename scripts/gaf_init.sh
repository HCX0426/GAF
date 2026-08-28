#!/bin/bash
# gaf_init.sh — v9.0 hard-constraint entry point (AI tasks must run before work)
# v9.0 restructure: fast/slow path split (gaf-workflow-v9-slim Task 1.8)
#   - --fast (default): only L1 hard-load + session active (< 1s)
#   - --full: pre-commit install + sync_ai_memory + sync_skills + L2 file existence
#   - No args = --fast
# v8.5 restructure: GAF is now workspace root, all paths are relative (no GAF/ prefix)
#   - Self-contained: auto-install pre-commit (no user pip install)
#   - Self-contained: auto-run pre-commit install
#   - Self-contained: auto-sync decision tree / lessons
#   - Self-contained: UTF-8 forced (N92 CJK garble fix)
#   - Self-contained: session auto-create
#   - v8.5: workspace parent sync removed (GAF IS workspace root now)

set -e

# Parse args: --fast (default) / --full
MODE="fast"
for arg in "$@"; do
    case "$arg" in
        --fast) MODE="fast" ;;
        --full) MODE="full" ;;
        --check-env) MODE="check-env" ;;
        *) echo "⚠️ Unknown arg: $arg (supported: --fast / --full / --check-env)";;
    esac
done
echo "🚀 gaf_init [$MODE] start (v9.0)"

# 0. Force UTF-8 stdout for all child Python processes (N92 / Windows CJK garble fix).
# PYTHONUTF8=1 enables Python UTF-8 Mode globally (equiv. `-X utf8`) — covers
# stdin/stdout/stderr + file IO defaults, not just stdout (aligned with
# TEST_SFCAPI_LANGUAGE three-line defense, 2026-08-15).
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export LC_ALL=C.UTF-8

# 1. conda verification (always)
if [[ "$CONDA_DEFAULT_ENV" != "gaf" ]]; then
    source activate gaf 2>/dev/null || {
        echo "❌ conda gaf env not found, run: conda activate gaf"
        exit 1
    }
fi

# 2. dependency check (always, fast)
python -c "import yaml, watchdog, click" 2>/dev/null || {
    echo "❌ Missing dependencies, run: conda run -n gaf pip install pyyaml watchdog click"
    exit 1
}

# 2.5 check-env mode: verify conda gaf + UTF-8 then exit (N188/N190 env probe, TD-370)
if [[ "$MODE" == "check-env" ]]; then
    echo "✅ [check-env] conda gaf env OK (python $(python -c 'import sys; print(sys.version.split()[0])' 2>/dev/null))"
    python -c "import sys; print('✅ [check-env] utf8_mode=%s stdout=%s' % (sys.flags.utf8_mode, sys.stdout.encoding))" 2>/dev/null || echo "⚠️ [check-env] utf8 probe failed (python missing?)"
    exit 0
fi

# ===== FULL-ONLY BLOCK START =====
if [[ "$MODE" == "full" ]]; then

    # 2.5. (N93 fix) Auto-install pre-commit if missing — avoid forcing user to run pip install.
    if ! command -v pre-commit >/dev/null 2>&1; then
        echo "🔧 [$MODE] pre-commit 未安装,自动安装中(避免让用户手动跑)..."
        pip install --quiet pre-commit || {
            echo "❌ pre-commit 安装失败,run: conda run -n gaf pip install pre-commit"
            exit 1
        }
        echo "✅ [$MODE] pre-commit 已自动安装"
    fi

    # 2.6. (N93 fix) Auto-run pre-commit install if hook not present — avoid forcing user to run.
    if [[ -d .git ]] && [[ ! -f .git/hooks/pre-commit ]]; then
        echo "🔧 [$MODE] pre-commit hook 未安装,自动执行 pre-commit install..."
        pre-commit install || {
            echo "❌ pre-commit install 失败,run: pre-commit install"
            exit 1
        }
        echo "✅ [$MODE] pre-commit hook 已自动安装"
    fi

    # 3. (N93 fix) Auto-run sync_ai_memory — AI 默默维护 KB,无需用户手跑.
    if [[ -f "scripts/bootstrap/sync_ai_memory.py" ]]; then
        echo "🔧 [$MODE] sync_ai_memory running..."
        python scripts/bootstrap/sync_ai_memory.py 2>&1 | head -20 || true
    fi

    # 3.5. (N93 fix) Auto-run sync_skills --check — 强制 gaf-orchestrator 决策树存在 (v9.0 单一权威源).
    if [[ -f "scripts/bootstrap/sync_skills.py" ]]; then
        echo "🔧 [$MODE] sync_skills --check running..."
        python scripts/bootstrap/sync_skills.py --check 2>&1 | head -10 || {
            echo "⚠️ [$MODE] sync_skills --check 失败,自动同步中..."
            python scripts/bootstrap/sync_skills.py 2>&1 | head -10
        }
    fi

    # 3.5.5. (L2 session-context) Auto-generate .ai-memory/ref/session-context.md —
    # compact project snapshot (env / apps / recent commits / active TD & roadmap)
    # that AI loads at the start of each session.
    if [[ -f "scripts/bootstrap/sync_session_context.py" ]]; then
        echo "🔧 [$MODE] sync_session_context running..."
        python scripts/bootstrap/sync_session_context.py 2>&1 | head -10 || true
    fi

    # 3.5.6. (C1 治本机制 2026-07-16) Auto-build .ai-memory/ semantic index for hybrid search.
    # Incremental update (mtime-based); skip if chromadb not installed.
    if [[ -f "scripts/bootstrap/build_memory_index.py" ]]; then
        echo "🔧 [$MODE] build_memory_index running (C1 hybrid search)..."
        python scripts/bootstrap/build_memory_index.py 2>&1 | head -10 || true
    fi

    # 3.6. (v8.5 restructure, 2026-07-17 updated) Verify 5 gaf-* skills + 1 rule distribution
REPO_SKILLS=$(ls ".skills/skills/gaf-orchestrator/SKILL.md" ".skills/skills/gaf-knowledge-base/SKILL.md" ".skills/skills/gaf-task-execution/SKILL.md" ".skills/skills/gaf-reflect-and-evolve/SKILL.md" ".skills/skills/gaf-lesson-router/SKILL.md" 2>/dev/null | wc -l)
REPO_RULES=$(ls ".skills/rules/project_rules.md" 2>/dev/null | wc -l)
    echo "🌳 [$MODE] 5 gaf-* skills + 1 rule 分发: workspace 根(GAF) ${REPO_SKILLS}/5 + ${REPO_RULES}/1"
    if [[ "$REPO_SKILLS" -ne 5 || "$REPO_RULES" -ne 1 ]]; then
        echo "⚠️ [$MODE] 副本不齐,自动修复中..."
        python scripts/bootstrap/sync_skills.py 2>&1 | head -15
    fi

    # 3.8. (N104 fix) docs-index stale check — 警告过期文档, 不阻塞启动
    if [[ -f "scripts/bootstrap/sync_docs_index.py" ]]; then
        if [[ ! -f ".ai-memory/meta/docs-index.md" ]]; then
            echo "🔧 [$MODE] docs-index 不存在, 自动生成中..."
            python scripts/bootstrap/sync_docs_index.py 2>&1 | head -3
        fi
        # 统计过期文档数 (只警告, 不阻塞)
        STALE_OUT=$(python scripts/bootstrap/sync_docs_index.py --check --stale-days 90 2>&1 || true)
        if echo "$STALE_OUT" | grep -q "stale doc"; then
            echo "⚠️  [$MODE] docs-index 检测到过期文档 (>90 天未更新):"
            echo "$STALE_OUT" | sed 's/^/   /'
        else
            echo "✅ [$MODE] docs-index OK"
        fi
    fi

    # 3.10. (spec-41) Doc health check — produce .cache/doc_health_report.json for AI consumption.
    # Read-only scan of docs/ + .ai-memory/ across 7 dimensions. <2s budget (N171).
    if [[ -f "scripts/governance/doc_health_check.py" ]]; then
        echo "🔧 [$MODE] doc_health_check running (spec-41, 7 dimensions)..."
        python scripts/governance/doc_health_check.py --no-fail 2>&1 | head -5 || true
    fi

    # [TD-387 2026-08-22] L2 文件清单校验已移至 always 段 (见下方 3.7.3),
    # 使默认 --fast 启动也确认 L2 在加载序列, 不再仅 --full 才校验.

fi
# ===== FULL-ONLY BLOCK END =====

# 3.7. (M0.M) L1 硬加载 failure-modes.md — AI 启动必读 (兜底, always run)
# 失败 exit 1, 不允许 fallback (硬约束, 区别于 soft guidance)
if [[ ! -f ".ai-memory/meta/failure-modes.md" ]]; then
    echo "❌ [$MODE] L1 硬加载失败: .ai-memory/meta/failure-modes.md 不存在"
    echo "   修复: 从 git history 恢复, 或跑 gaf_init.sh 在 GAF 根目录"
    exit 1
fi
# TD-371: 计数口径限定 Active 段 (## Active 到下一个 ## 之间), 避免全文件 grep 混入 Retired/Dormant/Archived
N_COUNT=$(awk '/^## Active/{f=1;next} /^## /&&f{f=0} f' .ai-memory/meta/failure-modes.md | grep -cE "^\| N[0-9]+" 2>/dev/null || echo 0)
if [[ "$N_COUNT" -lt 5 ]]; then
    echo "❌ [$MODE] L1 硬加载失败: failure-modes.md 不足 5 个 N## entry (实际 $N_COUNT)"
    echo "   修复: 检查 .ai-memory/meta/failure-modes.md 是否完整"
    exit 1
fi
echo "✅ [$MODE] L1 hard-load OK: failure-modes.md ($N_COUNT entries, 索引格式)"

# 3.7.3. (TD-387 2026-08-22) L2 文件清单校验 — 默认启动(--fast)也确认 L2 在加载序列
# L2 = ai-operating-handbook.md + tech-stack.md (v9.5). 缺失仅 WARN (L2 为 soft guidance,
# 区别于 L1 硬约束); 但输出明确标记, 供 AI 确认已加载, 避免"靠自觉跳过 L2"的形式化.
L2_FILES=(
    ".ai-memory/meta/ai-operating-handbook.md"
    "docs/reference/tech-stack.md"
)
L2_MISSING=0
for f in "${L2_FILES[@]}"; do
    if [[ ! -f "$f" ]]; then
        echo "⚠️ [$MODE] L2 file missing: $f"
        L2_MISSING=$((L2_MISSING + 1))
    fi
done
if [[ "$L2_MISSING" -eq 0 ]]; then
    echo "✅ [$MODE] L2 hard-load OK: ai-operating-handbook.md + tech-stack.md (v9.5)"
fi

# 3.7.2. (TD-324 spec-86, 2026-07-22) N181 紧急评估警告 — Active N## > 70 硬阈值
# 非阻塞, 仅 WARN (project_rules.md §4.12); 详细评估跑 n181_retirement_eval.py
N181_THRESHOLD=70
if [[ "$N_COUNT" -gt "$N181_THRESHOLD" ]]; then
    echo "⚠️ [$MODE] N181 紧急评估: Active N## $N_COUNT > $N181_THRESHOLD 硬阈值"
    echo "   (project_rules.md §4.12) — 跑 python scripts/governance/n181_retirement_eval.py 评估退役候选"
fi

# 3.7.1. (spec 2026-07-17-ai-meta-rules-eval-and-fix Phase 2) L2 量化校验 — ai-operating-handbook.md Part 2 红线模式 grep
# 失败行为: 警告 (非 exit 1, 因 L2 内容是 soft guidance, 与 L1 硬约束区分)
# 阈值 20 行 (当前 40+, 留 50% 安全余量)
L2_FILE=".ai-memory/meta/ai-operating-handbook.md"
if [[ -f "$L2_FILE" ]]; then
    L2_REDLINES=$(grep -cE '^- ❌.*→.*✅' "$L2_FILE" 2>/dev/null || echo 0)
    if [[ "$L2_REDLINES" -lt 20 ]]; then
        echo "⚠️ [$MODE] L2 量化校验警告: $L2_FILE 红线模式 $L2_REDLINES 行 (< 20 阈值)"
        echo "   修复: 检查 Part 2 行为红线段 (expected pattern: ^- ❌.*→.*✅)"
    else
        echo "✅ [$MODE] L2 hard-load OK: $L2_FILE ($L2_REDLINES red-lines, Part 2 行为红线模式)"
    fi
else
    echo "⚠️ [$MODE] L2 文件缺失: $L2_FILE"
fi

# P5 治本机制 (2026-07-16): failure-modes.md 正文 ≤ p5_max_lines 行 (frontmatter 字段, 默认 120, TD-167 单一权威源)
# 计算方式: 总行数 - frontmatter 行数 (frontmatter 以 --- 开始和结束)
FM_TOTAL=$(wc -l < .ai-memory/meta/failure-modes.md 2>/dev/null | tr -cd '0-9' || echo 0)
FM_FRONTMATTER=$(awk '/^---$/{c++; if(c==2) exit} END{print NR+0}' .ai-memory/meta/failure-modes.md 2>/dev/null | tr -cd '0-9' || echo 0)
FM_LINES=$(( ${FM_TOTAL:-0} - ${FM_FRONTMATTER:-0} ))
# Read p5_max_lines from frontmatter (single source of truth, TD-167)
FM_P5_MAX=$(awk '/^---$/{c++; next} c==1 && /^p5_max_lines:/ {gsub(/[^0-9]/, "", $2); print $2; exit}' .ai-memory/meta/failure-modes.md 2>/dev/null || echo "")
FM_P5_MAX=${FM_P5_MAX:-120}
if [[ "$FM_LINES" -gt "$FM_P5_MAX" ]]; then
    echo "⚠️ [$MODE] P5 警告: failure-modes.md 正文 $FM_LINES 行 (总 $FM_TOTAL - frontmatter $FM_FRONTMATTER) > $FM_P5_MAX 行硬上限"
    echo "   修复: python scripts/lessons/promote_lessons.py --enforce-limits --apply"
    echo "   (dry-run 预览: python scripts/lessons/promote_lessons.py --enforce-limits --dry-run)"
fi

# 5. AI entry uniqueness hint (always)
echo "🌳 [$MODE] AI 唯一入口：.skills/skills/gaf-orchestrator/SKILL.md（决策树根节点, .trae/ .opencode/ junction 指向 .skills/）"
echo "🌳 [$MODE] 单一权威源: 决策树只在 gaf-orchestrator, 其他 4 个 gaf-* SKILL.md 引用"
echo "🌳 [$MODE] docs/ 整个是给 AI 用的，AI 自动维护，无需人类 review"

# 6. session active (always, fast)
python scripts/bootstrap/check_session_active.py --create 2>&1 | head -5
echo "🔐 [$MODE] session active 已创建（24h TTL + 跨平台 binding）"

# 7. Final summary
echo ""
echo "============================================================"
if [[ "$MODE" == "fast" ]]; then
    echo "✅ gaf_init [$MODE] 完成,AI 可直接开始工作 (< 1s)"
    echo "   - L1 hard-load: OK (failure-modes.md $N_COUNT entries)"
    echo "   - session: active (24h)"
    echo "   - encoding: UTF-8 forced"
    echo "   - 跳过: pre-commit / sync_ai_memory / sync_skills / docs-index"
    echo "   - 如需完整流程: bash scripts/gaf_init.sh --full"
else
    echo "✅ gaf_init [$MODE] 完成,AI 可直接开始工作"
    echo "   - pre-commit: installed + hook installed"
    echo "   - KB sync: auto"
    echo "   - decision tree: 单一权威源校验通过"
    echo "   - L2 files: 2 files present (ai-operating-handbook.md + tech-stack.md, v9.5)"
    echo "   - session: active (24h)"
    echo "   - encoding: UTF-8 forced"
fi
echo "============================================================"
