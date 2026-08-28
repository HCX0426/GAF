---
date: 2026-06-16
symptom: [n111, command-timeout, blocking-run, no-output, no-error, terminal-stuck, ai-not-killing, ai-wait-forever, fallback-strategy, task-goal-continuity]
solution: '6 步超时应对: 5 段判别 → CheckCommandStatus → 0 输出 StopCommand → 报原因 → 异步 → 换方式继续 (拆分/异步/子agent/降级/换工具/根因修复). 主动结束 ≠ 失败 = 自决能力; 杀命令后必换方式继续, 不放弃任务目标'
diff_keywords: ["project", "rules", "project_rules", "architecture", "mistakes", "architecture-mistakes", "failure", "modes", "failure-modes", "ai", "autonomy", "_ai-autonomy"]
related_files:
  - .trae/rules/project_rules.md
  - .ai-memory/summaries/architecture-mistakes.md
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/meta/yn-matrices/archived-yn-matrices/_ai-autonomy.md
  - .trae/skills/gaf-orchestrator/SKILL.md
  - .ai-memory/lessons/N105-commit-bypass-rollback.md
  - .ai-memory/lessons/N109-decision-relaxation.md
created_by: AI
priority: high
l2_candidate: true
level: L1
n_id: N111
topic: ai-autonomy
---

# N111: AI 跑命令超时仍死等 → 用户被卡死 (2026-06-16)

> **根因**: AI 跑 `pytest` / `migrate` / `npm install` 等长时命令, 默认 `blocking=true` + `wait_ms_before_async=0`, 跑超 15 分钟无输出 AI 不知主动杀, 用户也只能干等
> **触发条件**: AI 跑长时命令 (sync 工具 / 测试套件 / 数据库 migrate / pip install) → 输出 0 行 / 不知进度 → 用户反馈 "ai运行终端命令时，要是时间超过预期时间要会主动结束那次的命令看报错"
> **影响**: 单次命令可卡 30+ 分钟, AI 整个 session 停滞, 用户没法介入, 错失中止时机

## 1. 现象 (Symptom)

AI 跑 `python scripts/bootstrap/sync_ai_memory.py --index` (扫 17 lessons 跑 ~1min OK), 但有时跑 `conda run -n gaf python -m pytest backend/...` 全套测试 (200+ 测试) 跑 5-15 分钟, 期间无 stdout 输出, AI 傻等。用户看到"AI 半天没反应" 实际 AI 在等命令, 命令在跑测试, 但用户不知道为什么, 也没办法 abort。

更深层: 跑 `pip install -r requirements.txt` 装大包 (PyTorch ~1.5GB) 可 5-20min, 同样 0 输出。

## 2. 根因 (Root Cause) (4 维)

1. **缺"超时主动结束" 规则层**: project_rules.md §5.2 只有"shell 命令限制" (多行 -c 禁用), 没有"超时主动结束" 规则
2. **AI 等待 vs 主动判别层**: AI 默认 `blocking=true` 一直等, 没"超过预期时间主动看状态" 概念
3. **缺预期时间基线层**: AI 不知道"pytest 全套应该 1-2min" vs "pip install 应该 5-10min", 没基线就没法判别超时
4. **N93 反模式变种层**: AI 等命令"等太久 = 甩命令给用户" 另一面, AI 不主动报状态 = 甩沉默给用户

## 3. 修复 (Solution) — 5 段超时判别 + 主动 StopCommand

### 3.1 5 段超时判别 (AI 必查)

| 时间段 | 命令类型 | AI 行为 |
|:------:|---------|---------|
| **0-30s** | 短命令 (ls / cat / git status / ruff check) | 正常 blocking, 必看到输出 |
| **30s-2min** | 中命令 (pytest 单文件 / sync_ai_memory --index / lint) | blocking OK, 但应见输出 |
| **2-5min** | 中长命令 (pytest 单模块 / migrate / 单文件 rebuild) | **有输出 → OK; 0 输出 → CheckCommandStatus 查; 仍 0 输出 → StopCommand 杀** |
| **5-15min** | 长命令 (pytest 全套 / npm install 中包) | **有输出 → 继续等; 0 输出 → CheckCommandStatus 查, 必要时 StopCommand** |
| **>15min** | 超长命令 (pip install 大包 / npm install 大包 / DB 导入) | **有输出 → 继续等; 0 输出 → 必须 StopCommand, 改用 blocking=false + 异步看** |

### 3.2 主动结束 ≠ 失败 = 自决能力

```
[AI 跑命令超时自决流程 (6 步, 2026-07-15 升级)]
  1. 命令跑 > 预期时间 (按 5 段判别)
  2. CheckCommandStatus 查最新输出 (不带 wait_ms, 直接看)
  3. 判断:
     ├─ 有输出 + 进度 → 继续等 (blocking=true)
     ├─ 有输出 + 报错 → 杀 + 根因分析 (§3.5 策略 6)
     ├─ 0 输出 + 超预期 → StopCommand 杀 + 改 blocking=false 异步看
     └─ 0 输出 + 已 5min+ → 必须 StopCommand + 报 "命令疑似卡死, 已结束, 请确认"
  4. 杀命令后报原因 (N101 状态诚实)
  5. 长命令改异步 (blocking=false + wait_ms_before_async=10000)
  6. 换替代方案继续 (§3.5 策略表, 不放弃任务目标) ← 2026-07-15 新增
```

### 3.5 换方式策略表 (2026-07-15 新增 — 用户反馈 "超时换方式执行")

> **来源**: 用户反馈 2026-07-15 — "一旦超时就判断是否要结束命令，用别的方式来执行"
> **核心原则**: 杀命令 ≠ 放弃任务目标。必须选一种替代方案继续。

| 策略 | 适用场景 | 操作 | 示例 |
|:----:|---------|------|------|
| **拆分** | 长命令跑全量 (pytest 全套 / npm build) | 拆成 per-app / per-module 分段跑, 缩小范围定位卡点 | `pytest 全套` 卡 → `pytest gaf_core` + `pytest agents` 分段 |
| **异步** | 命令本身需长跑 (dev server / celery) | `blocking=false` + `wait_ms_before_async=10000`, 后台跑 + 定期 CheckCommandStatus | `runserver` → 异步 + 每 2min 查状态 |
| **子 agent** | 命令输出过大 / 需独立调试 | `Task` 工具分发, 保护主 context window | 全量 ruff 输出 5000 行 → Task 子 agent 处理 |
| **降级** | 全量跑不通但急需验证 | 跑关键子集 + 标注"降级验证, 全量待补" | E2E 10 个卡 → 跑 3 个关键 + 标注 |
| **换工具** | RunCommand 卡死 / 输出截断 | Write 临时 .py/.ps1 脚本 → RunCommand 跑脚本 (绕过 inline 限制) | `conda run -c "多行"` 不支持 → Write .py + run |
| **根因修复** | 命令报错 (非卡死) | 先根因分析 (§2.0), 能当场修则修, 不能则登记 tech-debt (§4.8) | `git add backend/core` 失败 → 查 git mv 已执行 |

### 3.3 反模式 (避免)

- ❌ **NEVER** 命令跑超 2min 0 输出仍傻等 (违反本规则 §3.1)
- ❌ **NEVER** 跑 `pytest 全套` / `pip install 大包` 不设预期时间 (违反 §3.1 基线)
- ❌ **NEVER** 等命令到 session timeout (Trae 默认 5min 强制 kill, AI 应主动提前)
- ❌ **NEVER** 主动结束命令后不报原因 (违反 N101 状态诚实)
- ❌ **NEVER** 用 `wait_ms_before_async=0` 默认 (应按命令类型设)
- ❌ **NEVER** 杀命令后直接放弃任务目标 (必须换方式继续, §3.5) ← 2026-07-15 新增

### 3.4 命令类型预期基线 (AI 必记)

| 命令 | 预期时间 | 异常信号 |
|------|:------:|---------|
| `ls` / `cat` / `git status` | <5s | 卡 10s+ = 文件锁 |
| `ruff check` 单文件 | <5s | 卡 10s+ = 死循环 |
| `pytest` 单文件 | 5-30s | 卡 2min+ = 导入死循环 |
| `pytest` 全套 | 1-5min | 卡 10min+ = 数据库锁 / fixture 死循环 |
| `migrate` | 5-30s | 卡 2min+ = 锁等待 |
| `sync_ai_memory --index` | 5-30s | 卡 2min+ = git 死锁 |
| `pip install` 小包 | 10-60s | 卡 5min+ = 网络死 |
| `pip install` 大包 (torch) | 5-15min | 卡 20min+ = 网络死/编译错 |
| `npm install` | 1-5min | 卡 10min+ = registry 死 |
| `sync_skills` / `sync_docs_index` | 10-60s | 卡 2min+ = 文件系统挂 |

## 4. 验证 (Verification)

- [x] `project_rules.md §5.2.2` 新增 (本轮)
- [x] `architecture-mistakes.md #39` 新增 (本轮)
- [x] `failure-modes.md N111` 新增 (本轮)
- [x] `bypass-patterns.md §3` 加 N111 主动结束模式 (本轮)
- [x] `.trae/skills/gaf-orchestrator/SKILL.md` 反思清单加 ⑩ 终端超时判别 (本轮)
- [x] `pending-roadmap.md` N111 状态 (本轮)
- [x] `.ai-memory/lessons/N111-command-timeout.md` (本文件) 新增

## 5. 5 层分发 (N95 闭环)

| 层 | 路径 | 状态 |
|---|------|:---:|
| ① .ai-memory/ 教训层 | `.ai-memory/lessons/N111-command-timeout.md` (**本文件**) | ✅ |
| ② docs/ 架构教训层 | `.ai-memory/summaries/architecture-mistakes.md #39` (**本轮新增**) | ✅ |
| ③ spec/ 计划文档层 | `pending-roadmap.md` N111 状态 | ✅ |
| ④ SKILL.md 工作流层 | `.trae/skills/gaf-orchestrator/SKILL.md` 反思清单加 ⑩ | ✅ |
| ⑤ project_rules.md 用户规则层 | `§5.2.2` 新增 (**本轮**) | ✅ |
| ⑥ bypass-patterns.md 模式层 | `§3` 加 N111 主动结束模式 | ✅ |

## 6. 反思 (Reflection)

**4 问**:
1. **本轮要做什么?** 加 N111 规则 (命令超时主动结束), 5 层分发, 防 AI 傻等
2. **现有代码哪里直接复用?** §3.4 命令类型预期基线 (AI 已积累的经验, 显式化)
3. **潜在风险/依赖?** 误杀 (实际命令在跑, AI 看 0 输出以为卡死) — 解: CheckCommandStatus 二次确认
4. **验收标准?** AI 跑命令 >2min 0 输出必须主动查; >5min 0 输出必须 StopCommand

**学习**:
- **N93+N108+N109+N110+N111 同根因家族**: "甩命令/沉默" 各种变种
  - N93: AI 甩命令给用户 (甩执行)
  - N108: 过度限制 commit (甩 commit 决策)
  - N109: 过度限制选计划 (甩 plan 决策)
  - N110: hook 误触项目历史 (甩错位置)
  - **N111: AI 傻等命令 (甩沉默)** ← 本条
- **"主动结束 ≠ 失败" 是 AI 成熟的标志**: 知道何时杀命令, 何时改异步, 何时报原因
- **预期时间基线是 AI 决策基础**: 不知道"pytest 1-2min" 就不知道"5min 0 输出 = 卡死"
- **N95 6 层分发 (本轮新加 ⑥ bypass-patterns)**: bypass-patterns 是教训→行动的桥梁, N111 加进 §3 让 AI 实战可查

## 7. 相关文件

- `.ai-memory/lessons/N111-command-timeout.md` (本文件)
- `.trae/rules/project_rules.md` (§5.2.2 新增)
- `.ai-memory/summaries/architecture-mistakes.md` (#39 新增)
- `.ai-memory/meta/failure-modes.md` (N111 新增)
- `.ai-memory/meta/failure-modes.md` (§3 加 N111 主动结束模式)
- `.trae/skills/gaf-orchestrator/SKILL.md` (§3.2 ⑩ 反思清单)
- `docs/archive/pending-roadmap.md` (N111 状态)
- `.ai-memory/lessons/N105-commit-bypass-rollback.md` (上游)
- `.ai-memory/lessons/N109-decision-relaxation.md` (上游)
