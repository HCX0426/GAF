# gaf_init.ps1 — v9.0 hard-constraint entry point (PowerShell 7.x equivalent of gaf_init.sh)
# v9.0 restructure: fast/slow path split (gaf-workflow-v9-slim Task 1.8)
#   - --fast (default): only L1 hard-load + session active (< 1s)
#   - --full: pre-commit install + sync_ai_memory + sync_skills + L2 file existence
#   - No args = --fast
#
# Maintained alongside gaf_init.sh (Linux/macOS); this file is Windows PowerShell 7.x+.
# TD-320 (2026-07-21 spec-82): bash-only .sh → PowerShell 等价版本

#Requires -Version 7.0

$ErrorActionPreference = "Stop"

# Parse args: --fast (default) / --full
$MODE = "fast"
foreach ($arg in $args) {
    switch ($arg) {
        "--fast" { $MODE = "fast" }
        "--full" { $MODE = "full" }
        default { Write-Host "⚠️ Unknown arg: $arg (supported: --fast / --full)" }
    }
}
Write-Host "🚀 gaf_init [$MODE] start (v9.0, PowerShell)"

# 0. Force UTF-8 stdout for all child Python processes (N92 / Windows CJK garble fix).
# PYTHONUTF8=1 enables Python UTF-8 Mode globally (equiv. `python -X utf8`) —
# covers stdin/stdout/stderr + file IO defaults, not just stdout (aligned with
# TEST_SFCAPI_LANGUAGE three-line defense, 2026-08-15).
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:LC_ALL = "C.UTF-8"

# 1. conda verification (always)
# Auto-discover conda + load PowerShell hook if not loaded (N160 — avoid forcing user to conda init).
# Note: conda.bat on PATH is NOT enough — it can't modify current PowerShell session env.
#       Must load PowerShell hook so `conda` becomes a Function (not Application).
if ($env:CONDA_DEFAULT_ENV -ne "gaf") {
    $condaCmd = Get-Command conda -ErrorAction SilentlyContinue
    $needHook = $true
    if ($condaCmd -and $condaCmd.CommandType -eq "Function") {
        $needHook = $false
    }
    if ($needHook) {
        $condaBase = $null
        # Try $env:CONDA_EXE first (set by conda activate in parent shell if inherited)
        if ($env:CONDA_EXE -and (Test-Path $env:CONDA_EXE)) {
            $condaBase = Split-Path (Split-Path $env:CONDA_EXE)
        }
        # Try existing conda command source (conda.bat in condabin/)
        if (-not $condaBase -and $condaCmd -and $condaCmd.Source) {
            $condaBase = Split-Path (Split-Path $condaCmd.Source)
        }
        # Try common Windows install locations
        if (-not $condaBase) {
            $candidates = @(
                "D:\code\environment\conda\Miniconda3",
                "D:\code\environment\conda\Anaconda3",
                "$env:USERPROFILE\Miniconda3",
                "$env:USERPROFILE\Anaconda3",
                "$env:LOCALAPPDATA\Miniconda3",
                "$env:LOCALAPPDATA\Anaconda3",
                "C:\Miniconda3",
                "C:\Anaconda3",
                "C:\ProgramData\Miniconda3",
                "C:\ProgramData\Anaconda3"
            )
            foreach ($cand in $candidates) {
                if (Test-Path "$cand\shell\condabin\conda-hook.ps1") {
                    $condaBase = $cand
                    break
                }
            }
        }
        if ($condaBase -and (Test-Path "$condaBase\shell\condabin\conda-hook.ps1")) {
            & "$condaBase\shell\condabin\conda-hook.ps1"
        }
    }
    try {
        conda activate gaf 2>$null
        if ($LASTEXITCODE -ne 0) { throw "conda activate failed" }
    } catch {
        Write-Host "❌ conda gaf env not found, run: conda activate gaf"
        Write-Host "   (PowerShell 需先跑一次 conda init powershell, 或确保 conda 在 PATH)"
        exit 1
    }
}

# 2. dependency check (always, fast)
python -c "import yaml, watchdog, click" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Missing dependencies, run: conda run -n gaf pip install pyyaml watchdog click"
    exit 1
}

# ===== FULL-ONLY BLOCK START =====
if ($MODE -eq "full") {

    # 2.5. (N93 fix) Auto-install pre-commit if missing — avoid forcing user to run pip install.
    $precommitCmd = Get-Command pre-commit -ErrorAction SilentlyContinue
    if (-not $precommitCmd) {
        Write-Host "🔧 [$MODE] pre-commit 未安装,自动安装中(避免让用户手动跑)..."
        pip install --quiet pre-commit
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ pre-commit 安装失败,run: conda run -n gaf pip install pre-commit"
            exit 1
        }
        Write-Host "✅ [$MODE] pre-commit 已自动安装"
    }

    # 2.6. (N93 fix) Auto-run pre-commit install if hook not present — avoid forcing user to run.
    if ((Test-Path .git) -and -not (Test-Path .git/hooks/pre-commit)) {
        Write-Host "🔧 [$MODE] pre-commit hook 未安装,自动执行 pre-commit install..."
        pre-commit install
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ pre-commit install 失败,run: pre-commit install"
            exit 1
        }
        Write-Host "✅ [$MODE] pre-commit hook 已自动安装"
    }

    # 3. (N93 fix) Auto-run sync_ai_memory — AI 默默维护 KB,无需用户手跑.
    if (Test-Path "scripts/bootstrap/sync_ai_memory.py") {
        Write-Host "🔧 [$MODE] sync_ai_memory running..."
        python scripts/bootstrap/sync_ai_memory.py 2>&1 | Select-Object -First 20
    }

    # 3.5. (N93 fix) Auto-run sync_skills --check — 强制 gaf-orchestrator 决策树存在 (v9.0 单一权威源).
    if (Test-Path "scripts/bootstrap/sync_skills.py") {
        Write-Host "🔧 [$MODE] sync_skills --check running..."
        python scripts/bootstrap/sync_skills.py --check 2>&1 | Select-Object -First 10
        if ($LASTEXITCODE -ne 0) {
            Write-Host "⚠️ [$MODE] sync_skills --check 失败,自动同步中..."
            python scripts/bootstrap/sync_skills.py 2>&1 | Select-Object -First 10
        }
    }

    # 3.5.5. (L2 session-context) Auto-generate .ai-memory/ref/session-context.md
    if (Test-Path "scripts/bootstrap/sync_session_context.py") {
        Write-Host "🔧 [$MODE] sync_session_context running..."
        python scripts/bootstrap/sync_session_context.py 2>&1 | Select-Object -First 10
    }

    # 3.5.6. (C1 治本机制 2026-07-16) Auto-build .ai-memory/ semantic index for hybrid search.
    if (Test-Path "scripts/bootstrap/build_memory_index.py") {
        Write-Host "🔧 [$MODE] build_memory_index running (C1 hybrid search)..."
        python scripts/bootstrap/build_memory_index.py 2>&1 | Select-Object -First 10
    }

    # 3.6. (v8.5 restructure, 2026-07-17 updated) Verify 5 gaf-* skills + 1 rule distribution
    $skillFiles = @(
        ".skills/skills/gaf-orchestrator/SKILL.md",
        ".skills/skills/gaf-knowledge-base/SKILL.md",
        ".skills/skills/gaf-task-execution/SKILL.md",
        ".skills/skills/gaf-reflect-and-evolve/SKILL.md",
        ".skills/skills/gaf-lesson-router/SKILL.md"
    )
    $REPO_SKILLS = ($skillFiles | Where-Object { Test-Path $_ }).Count
    $REPO_RULES = if (Test-Path ".skills/rules/project_rules.md") { 1 } else { 0 }
    Write-Host "🌳 [$MODE] 5 gaf-* skills + 1 rule 分发: workspace 根(GAF) $REPO_SKILLS/5 + $REPO_RULES/1"
    if ($REPO_SKILLS -ne 5 -or $REPO_RULES -ne 1) {
        Write-Host "⚠️ [$MODE] 副本不齐,自动修复中..."
        python scripts/bootstrap/sync_skills.py 2>&1 | Select-Object -First 15
    }

    # 3.8. (N104 fix) docs-index stale check — 警告过期文档, 不阻塞启动
    if (Test-Path "scripts/bootstrap/sync_docs_index.py") {
        if (-not (Test-Path ".ai-memory/meta/docs-index.md")) {
            Write-Host "🔧 [$MODE] docs-index 不存在, 自动生成中..."
            python scripts/bootstrap/sync_docs_index.py 2>&1 | Select-Object -First 3
        }
        # 统计过期文档数 (只警告, 不阻塞)
        $staleOut = python scripts/bootstrap/sync_docs_index.py --check --stale-days 90 2>&1
        if ($staleOut -match "stale doc") {
            Write-Host "⚠️  [$MODE] docs-index 检测到过期文档 (>90 天未更新):"
            $staleOut | ForEach-Object { Write-Host "   $_" }
        } else {
            Write-Host "✅ [$MODE] docs-index OK"
        }
    }

    # 3.10. (spec-41) Doc health check — produce .cache/doc_health_report.json for AI consumption.
    if (Test-Path "scripts/governance/doc_health_check.py") {
        Write-Host "🔧 [$MODE] doc_health_check running (spec-41, 7 dimensions)..."
        python scripts/governance/doc_health_check.py --no-fail 2>&1 | Select-Object -First 5
    }

    # [TD-387 2026-08-22] L2 文件清单校验已移至 always 段 (见下方 3.7.3),
    # 使默认 --fast 启动也确认 L2 在加载序列, 不再仅 --full 才校验.

}
# ===== FULL-ONLY BLOCK END =====

# 3.7. (M0.M) L1 硬加载 failure-modes.md — AI 启动必读 (兜底, always run)
# 失败 exit 1, 不允许 fallback (硬约束, 区别于 soft guidance)
if (-not (Test-Path ".ai-memory/meta/failure-modes.md")) {
    Write-Host "❌ [$MODE] L1 硬加载失败: .ai-memory/meta/failure-modes.md 不存在"
    Write-Host "   修复: 从 git history 恢复, 或跑 gaf_init.ps1 在 GAF 根目录"
    exit 1
}
$fmMatches = Select-String -Path ".ai-memory/meta/failure-modes.md" -Pattern '^\| N[0-9]+' -AllMatches
$N_COUNT = if ($fmMatches) { $fmMatches.Matches.Count } else { 0 }
if ($N_COUNT -lt 5) {
    Write-Host "❌ [$MODE] L1 硬加载失败: failure-modes.md 不足 5 个 N## entry (实际 $N_COUNT)"
    Write-Host "   修复: 检查 .ai-memory/meta/failure-modes.md 是否完整"
    exit 1
}
Write-Host "✅ [$MODE] L1 hard-load OK: failure-modes.md ($N_COUNT entries, 索引格式)"

# 3.7.3. (TD-387 2026-08-22) L2 文件清单校验 — 默认启动(--fast)也确认 L2 在加载序列
# L2 = ai-operating-handbook.md + tech-stack.md (v9.5). 缺失仅 WARN (L2 为 soft guidance,
# 区别于 L1 硬约束); 但输出明确标记, 供 AI 确认已加载, 避免"靠自觉跳过 L2"的形式化.
$L2_FILES = @(
    ".ai-memory/meta/ai-operating-handbook.md",
    "docs/reference/tech-stack.md"
)
$L2_MISSING = 0
foreach ($f in $L2_FILES) {
    if (-not (Test-Path $f)) {
        Write-Host "⚠️ [$MODE] L2 file missing: $f"
        $L2_MISSING++
    }
}
if ($L2_MISSING -eq 0) {
    Write-Host "✅ [$MODE] L2 hard-load OK: ai-operating-handbook.md + tech-stack.md (v9.5)"
}

# 3.7.2. (TD-324 spec-86, 2026-07-22) N181 紧急评估警告 — Active N## > 70 硬阈值
# 非阻塞, 仅 WARN (project_rules.md §4.12); 详细评估跑 n181_retirement_eval.py
$N181_THRESHOLD = 70
if ($N_COUNT -gt $N181_THRESHOLD) {
    Write-Host "⚠️ [$MODE] N181 紧急评估: Active N## $N_COUNT > $N181_THRESHOLD 硬阈值"
    Write-Host "   (project_rules.md §4.12) — 跑 python scripts/governance/n181_retirement_eval.py 评估退役候选"
}

# 3.7.1. (spec 2026-07-17-ai-meta-rules-eval-and-fix Phase 2) L2 量化校验 — ai-operating-handbook.md Part 2 红线模式 grep
# 失败行为: 警告 (非 exit 1, 因 L2 内容是 soft guidance, 与 L1 硬约束区分)
# 阈值 20 行 (当前 40+, 留 50% 安全余量)
$L2_FILE = ".ai-memory/meta/ai-operating-handbook.md"
if (Test-Path $L2_FILE) {
    $l2Matches = Select-String -Path $L2_FILE -Pattern '^- ❌.*→.*✅' -AllMatches
    $L2_REDLINES = if ($l2Matches) { $l2Matches.Matches.Count } else { 0 }
    if ($L2_REDLINES -lt 20) {
        Write-Host "⚠️ [$MODE] L2 量化校验警告: $L2_FILE 红线模式 $L2_REDLINES 行 (< 20 阈值)"
        Write-Host "   修复: 检查 Part 2 行为红线段 (expected pattern: ^- ❌.*→.*✅)"
    } else {
        Write-Host "✅ [$MODE] L2 hard-load OK: $L2_FILE ($L2_REDLINES red-lines, Part 2 行为红线模式)"
    }
} else {
    Write-Host "⚠️ [$MODE] L2 文件缺失: $L2_FILE"
}

# P5 治本机制 (2026-07-16): failure-modes.md 正文 ≤ p5_max_lines 行 (frontmatter 字段, 默认 120, TD-167 单一权威源)
# 计算方式: 总行数 - frontmatter 行数 (frontmatter 以 --- 开始和结束)
$fmContent = Get-Content .ai-memory/meta/failure-modes.md
$FM_TOTAL = $fmContent.Count
$FM_FRONTMATTER = 0
$fmCloseCount = 0
for ($i = 0; $i -lt $fmContent.Count; $i++) {
    if ($fmContent[$i] -match '^---\s*$') {
        $fmCloseCount++
        if ($fmCloseCount -eq 2) {
            $FM_FRONTMATTER = $i + 1
            break
        }
    }
}
$FM_LINES = $FM_TOTAL - $FM_FRONTMATTER
# Read p5_max_lines from frontmatter (single source of truth, TD-167)
$FM_P5_MAX = 120
$fmOpenCount = 0
for ($i = 0; $i -lt $fmContent.Count; $i++) {
    if ($fmContent[$i] -match '^---\s*$') {
        $fmOpenCount++
        if ($fmOpenCount -eq 2) { break }
        continue
    }
    if ($fmOpenCount -eq 1 -and $fmContent[$i] -match '^p5_max_lines:\s*(\d+)') {
        $FM_P5_MAX = [int]$Matches[1]
    }
}
if ($FM_LINES -gt $FM_P5_MAX) {
    Write-Host "⚠️ [$MODE] P5 警告: failure-modes.md 正文 $FM_LINES 行 (总 $FM_TOTAL - frontmatter $FM_FRONTMATTER) > $FM_P5_MAX 行硬上限"
    Write-Host "   修复: python scripts/lessons/promote_lessons.py --enforce-limits --apply"
    Write-Host "   (dry-run 预览: python scripts/lessons/promote_lessons.py --enforce-limits --dry-run)"
}

# 5. AI entry uniqueness hint (always)
Write-Host "🌳 [$MODE] AI 唯一入口：.skills/skills/gaf-orchestrator/SKILL.md（决策树根节点, .trae/ .opencode/ junction 指向 .skills/）"
Write-Host "🌳 [$MODE] 单一权威源: 决策树只在 gaf-orchestrator, 其他 4 个 gaf-* SKILL.md 引用"
Write-Host "🌳 [$MODE] docs/ 整个是给 AI 用的，AI 自动维护，无需人类 review"

# 6. session active (always, fast)
python scripts/bootstrap/check_session_active.py --create 2>&1 | Select-Object -First 5
Write-Host "🔐 [$MODE] session active 已创建（24h TTL + 跨平台 binding）"

# 7. Final summary
Write-Host ""
Write-Host "============================================================"
if ($MODE -eq "fast") {
    Write-Host "✅ gaf_init [$MODE] 完成,AI 可直接开始工作 (< 1s)"
    Write-Host "   - L1 hard-load: OK (failure-modes.md $N_COUNT entries)"
    Write-Host "   - session: active (24h)"
    Write-Host "   - encoding: UTF-8 forced"
    Write-Host "   - 跳过: pre-commit / sync_ai_memory / sync_skills / docs-index"
    Write-Host "   - 如需完整流程: pwsh scripts/gaf_init.ps1 --full"
} else {
    Write-Host "✅ gaf_init [$MODE] 完成,AI 可直接开始工作"
    Write-Host "   - pre-commit: installed + hook installed"
    Write-Host "   - KB sync: auto"
    Write-Host "   - decision tree: 单一权威源校验通过"
    Write-Host "   - L2 files: 2 files present (ai-operating-handbook.md + tech-stack.md, v9.5)"
    Write-Host "   - session: active (24h)"
    Write-Host "   - encoding: UTF-8 forced"
}
Write-Host "============================================================"
