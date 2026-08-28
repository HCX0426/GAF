---
id: n119-m2b-command-hang
date: 2026-06-17
priority: high
symptom: User reports "conda run -n gaf python scripts hang waiting for manual stop;
  git log --oneline -20 also requires manual stop; many git commands hang"
root_cause: "Two root causes for command hang on Windows PowerShell 5 + TraeAI terminal:\n\
  1. git pager (less/winpty) auto-engages on `git log` / `git diff` / `git show` and\
  \ waits\n   for user to press 'q' to quit, because TraeAI's terminal is detected\
  \ as interactive.\n2. `RunCommand` tool default `blocking=true` makes AI wait for\
  \ command to finish; for\n   long-running python scripts the user sees a hung terminal\
  \ and has to manually stop\n   the command so AI can continue.\n"
trigger: '- Any `git log` / `git diff` / `git show` without `--no-pager` (PowerShell
  5 always hits pager)
  - Any `conda run -n gaf python long_script.py` with default `blocking=true`
  - Any pytest/pip/npm/migrate command without explicit `blocking=false` + `wait_ms_before_async`
  '
solution: "AI MUST follow N119 command patterns:\n1. **git commands** — always prefix\
  \ with `git --no-pager` (or set `GIT_PAGER=cat` env):\n   `git --no-pager log --oneline\
  \ -20` / `git --no-pager diff` / `git --no-pager show HEAD`\n2. **Long commands**\
  \ — always use `blocking=false` + explicit `wait_ms_before_async` per档位表:\n   -\
  \ 快 (5s): `git status` / `ls` / `cat` / `ruff check` 单文件\n   - 中 (15s): `pytest`\
  \ 单文件 / `migrate` / `sync_ai_memory --query`\n   - 慢 (30s): `pytest` 单模块 / `sync_ai_memory\
  \ --index` / `npm install` 小包\n   - 超慢 (60s): `pip install` 大包 / `npm install` 大包\
  \ / `migrate` 含 data migration\n   - 极端 (120s): DB 导入 / 完整测试套件 / sync 整个仓库\n3. **Polling**\
  \ — use `CheckCommandStatus` to poll; if > expected, `StopCommand` kill\n4. **conda\
  \ run** — always include `-n gaf` for environment isolation\n5. **PYTHONIOENCODING=utf-8**\
  \ — set before any Python command to avoid PowerShell 5 GBK error\n6. **git commit**\
  \ — always use `-m \"...\"` (PowerShell 5 does not auto-close vim)\n"
diff_keywords: ["user", "reports", "conda", "run", "gaf", "python", "scripts", "hang", "waiting", "for", "manual", "stop"]
related_files:
- .trae/rules/project_rules.md
- .trae/skills/gaf-reflect-and-evolve/SKILL.md
- .ai-memory/meta/failure-modes.md
created_by: AI
level: L1
n_id: N119
topic: testing
---



# N119 — 命令卡死让用户手动结束 (Command Hang Forces User Manual Stop)

> **来源**: M2.B 实战 (2026-06-17) — 用户原话 "conda run -n gaf python 执行py文件总会让我自己结束你才能继续，git log --oneline -20 这个咋让我手动，git命令很多也要我手动停止才能继续"
> **闭环**: `.trae/skills/gaf-reflect-and-evolve/SKILL.md` + `project_rules.md §5.9` + `failure-modes.md N119` + `architecture-mistakes.md` + 本 lesson (5 层分发)

## 两大根因 (命令卡死, AI 必查)

| # | 卡死原因 | 触发命令 | 解决方案 |
|:-:|----------|----------|----------|
| **1** | **git pager** (less/winpty) 等待用户按 q | `git log` / `git diff` / `git show` / `git stash list` | 全部加 `--no-pager` 或 `GIT_PAGER=cat` |
| **2** | **python 输出缓冲 + 交互等待** | `conda run -n gaf python script.py` | `blocking=false` + 显式 `wait_ms_before_async` + `CheckCommandStatus` 轮询 |

## 4 原则 (命令模式硬规则, 必读)

1. **git 命令默认加 `--no-pager`** — 不依赖全局 `core.pager` 配置
2. **长命令用 `blocking=false`** — pytest / pip / npm / migrate / sync / 自定义 Python 脚本
3. **`wait_ms_before_async` 显式设档位** — 5 / 15 / 30 / 60 / 120 秒, 不允许用默认 0
4. **轮询 + 主动 StopCommand** — `CheckCommandStatus` 查输出, 超预期 `StopCommand` 杀

## wait_ms_before_async 档位表

| 档位 | 等待时间 | 适用命令 | 轮询节奏 |
|:----:|:--------:|----------|----------|
| **快** | `5000` (5s) | `git status` / `ls` / `cat` / `ruff check` 单文件 | `CheckCommandStatus` 阻塞 5s |
| **中** | `15000` (15s) | `pytest` 单文件 / `migrate` / `sync_ai_memory --query` / `git --no-pager log` | 阻塞 15s |
| **慢** | `30000` (30s) | `pytest` 单模块 / pytest 全套 / `sync_ai_memory --index` / `npm install` 小包 | 阻塞 30s |
| **超慢** | `60000` (60s) | `pip install` 大包 / `npm install` 大包 / `migrate` 含 data migration | 阻塞 60s |
| **极端** | `120000` (2min) | DB 导入 / 完整测试套件 / sync 整个仓库 | 阻塞 2min, 拿不到 `StopCommand` 杀 |

## 正确模式 vs 反模式

| 项 | 反模式 (N119 根因) | 正确模式 (N119 修复) |
|---|-------------------|---------------------|
| git log | `git log --oneline -20` (走 pager 卡死) | `git --no-pager log --oneline -20` |
| git diff | `git diff` (走 pager 卡死) | `git --no-pager diff` |
| git show | `git show HEAD` (走 pager 卡死) | `git --no-pager show HEAD` |
| python 脚本 | `conda run -n gaf python long_script.py` 默认 `blocking=true` | `conda run -n gaf python long_script.py` + `blocking=false` + `wait_ms_before_async=30000` |
| pytest 全套 | `pytest tests/` 默认 `blocking=true` 等 5-15min | `pytest tests/` + `blocking=false` + `wait_ms_before_async=60000` + `CheckCommandStatus` 轮 |
| pip install | `pip install torch` 等 10min+ | `pip install torch` + `blocking=false` + `wait_ms_before_async=120000` + 轮询 |

## AI 必做 (N119 硬规则)

- ✅ git 命令默认 `--no-pager`: `git log` / `git diff` / `git show` / `git stash list` / `git blame` 一律前缀
- ✅ 长命令 `blocking=false`: pytest / pip / npm / sync / 自定义 python 脚本
- ✅ `wait_ms_before_async` 显式设: 按上表选档位, 不允许用默认 0
- ✅ 轮询用 `CheckCommandStatus`: 不阻塞 5min+ 等命令, 拿到输出立即 `StopCommand` 杀后台进程
- ✅ conda run 必加 `-n gaf`: 环境隔离, 避免 base 环境跑错依赖
- ✅ PYTHONIOENCODING=utf-8: 跑 Python 命令前必设, 防 PowerShell 5 GBK 编码错
- ❌ NEVER 跑 `git log` / `git diff` 不加 `--no-pager` (PowerShell 5 必卡 pager)
- ❌ NEVER 用 `blocking=true` 等超过 2min 的命令 (用户会卡)
- ❌ NEVER 用 `wait_ms_before_async=0` 默认值 (拿不到输出就傻等, N111 反模式)
- ❌ NEVER 用 `git commit` 跑编辑 (PowerShell 5 不会自动关 vim, 必加 `-m "..."`)
- ❌ NEVER 跑 conda 命令不带 `-n gaf` (会落到 base 环境, 依赖错)

## 反模式家族

N82 (审计) + N100 (文件损坏) + N101 (状态不诚实) + N105 (hook 透传) + N106 (路径漂移) + N110 (lint 阻塞) + N111 (超时) + N114 (hook 误用) + N116 (并发缺位) + N117 (决策树治理) + N118 (测试环境) + N91 (hook 失败) + **N119 (本条 命令卡死)** — 同根因 (工具调用治理缺位)

## 5 层分发状态 (N95 闭环)

- [x] 层① .ai-memory/lessons/N119-m2b-command-hang.md (本文件)
- [x] 层② .ai-memory/lessons/architecture-mistakes.md (binary-safe append)
- [x] 层③ .ai-memory/meta/failure-modes.md N119 (binary-safe append)
- [x] 层④ .trae/skills/gaf-reflect-and-evolve/SKILL.md (补 §1 触发场景 "pre-commit hook 失败" 旁加 "命令卡死")
- [x] 层⑤ .trae/rules/project_rules.md §5.9 (本条 88 行新规则)
- [ ] 层⑥ docs/specs/legacy-trae/build-gaf-knowledge-system/{spec,tasks}.md (本轮 commit 后补)
