---
date: 2026-06-16
symptom: [ai-decision-blocked, plan-known-still-asks, user-fatigue, n109, workflow-friction, over-ask-permission]
solution: '改 project_rules.md §3.5 大幅缩小授权范围: 仅跨大阶段合并/重写 history/删 branch/stash drop 仍需授权; 计划内任务 (P1/P2 已在 pending-roadmap.md 列出) AI 全自决: 选任务/拆子任务/创建文件/修改代码/写教训/commit'
diff_keywords: ["project", "rules", "project_rules", "architecture", "mistakes", "architecture-mistakes", "failure", "modes", "failure-modes", "skill", "n108", "commit"]
related_files:
  - .trae/rules/project_rules.md
  - .ai-memory/summaries/architecture-mistakes.md
  - .ai-memory/meta/failure-modes.md
  - .trae/skills/gaf-orchestrator/SKILL.md
  - .ai-memory/_archive/lessons-retired/N108-commit-rule-relaxation.md
created_by: AI
priority: high
l2_candidate: true
level: L1
n_id: N109
topic: ai-autonomy
---

# N109: 计划内任务仍反复问用户决定 → AI 推进慢 (2026-06-16)

> **根因**: N108 放开了 AI 自 commit, 但用户还要在每个分叉点 (选哪个 P2/谁先做) 决定, AI 没真正自决
> **触发条件**: M1.A 闭环后 AI 问"下一步: M1.B? R24? P-038?", 用户反馈 "以后这种已经有计划的任务，不用问我决定，让ai决定，规则要改下"
> **影响**: AI 推进需用户决策, 用户疲劳, AI 没真正成"自推进" Agent

## 1. 现象 (Symptom)

M1.A 闭环总结后 (commit -), AI 给出 4 个候选 (M1.B/R24/P-038/新需求), 问用户"要继续哪个?"。用户反馈:

> "以后这种已经有计划的任务，不用问我决定，让ai决定，规则要改下"

之前 N108 放开了"自 commit", 但 AI 仍把"计划选择权"留在用户手里 — 这其实是另一种"甩命令" (N93 变种): AI 不知道该推进哪个, 就甩给用户选。

## 2. 根因 (Root Cause) (4 维)

1. **N108 不完整**: 放开"自 commit" 但没放开"自选计划", N108 是 commit 层面, N109 是决策层面
2. **过度防御延伸**: N108 之前规则"全部要用户授权" 延伸到"全部要用户决定", N109 需进一步分两层 (commit 自决 vs 决策自决)
3. **AI 没"已计划任务" 概念**: 不知道 pending-roadmap.md 列出的 P1/P2 任务就是"已计划", 不需要再问
4. **缺"自决边界" 规则**: AI 不知道哪些决策可自决, 哪些需授权 — 需明文边界

同根因家族:
- **N93**: AI 甩命令给用户 (甩决策) → N109 是其延伸
- **N108**: commit 层面放开 → N109 决策层面放开
- **N108 同根因** (N93 过度限制双胞胎) → N109 同根因

## 3. 修复 (Solution) — project_rules.md §3.5 重构

### 3.1 §3.5 重构 (本轮)

**改前** (N108):
- §3.5 仍需用户授权: 跨大阶段合并 / 重写 history / 删 branch/tag / stash drop

**改后** (N109):
- §3.5 仍需用户授权 (范围大幅缩小): 仅剩 3 类
  - **跨工作区/跨机器的操作** (push 远程 / git pull --rebase 跨分支)
  - **重写 history** (`rebase -i` / `commit --amend` 已 push / `filter-branch`)
  - **不可逆数据删除** (`git branch -D` / `git tag -d` / `git stash drop` / API DELETE)
- §3.6 AI 自决范围 (新增): 计划内任务全自决
  - **选任务**: pending-roadmap.md P1/P2 任一任务, AI 按 ROI/依赖/优先级自选
  - **拆子任务**: 1 大任务拆 N 子任务, AI 自决
  - **写代码/建文件/改配置**: 按 spec/code-rules 实现
  - **写教训**: 5 层分发 (N95)
  - **commit + 验证**: 按 §3.4 流程

### 3.2 "已计划任务" 定义 (AI 必读)

满足任一条件即算"已计划":
- pending-roadmap.md 列出有 ID (P-###/A#/C#/M#/U#)
- spec.md 列出有 §N.M 编号
- tasks.md / checklist.md 列出有 checkbox `- [ ]`
- completed-features.md 列出有 ❌ 未实现 (即"做过的反例, 防止重写")
- 用户最近 3 轮对话明确说要做某事 (短时记忆)

### 3.3 自决硬约束 (避免 AI 跑偏)

- ✅ **必须有依据**: AI 选 X 不选 Y 必须有理由 (ROI/依赖/优先级), 写到 plan/pending-roadmap.md 二.5
- ✅ **必须 5 层分发**: 写完教训按 N95 闭环 (5 层缺一不可)
- ✅ **必须 commit 验证**: 按 §3.4 7 步流程, 不省略 `git log --oneline -1`
- ✅ **必须循环反思**: §4.6 每段验证后跑, 至少 2 轮
- ❌ **禁止自创任务**: pending-roadmap.md 没有的任务, 需用户确认 (避免 scope creep)
- ❌ **禁止跳过验证**: 本地 lint/test/sync 跑通才 commit

### 3.4 AI 推进流程 (7 步)

```
[AI 自推进计划内任务流程]
  1. 读 pending-roadmap.md 选下个任务 (按 ROI/依赖/优先级)
  2. 读 spec.md §N.M / tasks.md 看清范围
  3. 拆子任务 (用 TodoWrite 跟踪)
  4. 实施 (写代码/建文件/跑 sync 工具)
  5. 本地验证 (lint/test/sync) + 循环反思 (≥ 2 轮)
  6. commit (按 §3.4 流程, 不用问用户)
  7. 推进下一段 (回到 1)
```

## 4. 验证 (Verification)

- [x] `project_rules.md §3.5` 缩小到 3 类
- [x] `project_rules.md §3.6` 新增 AI 自决范围
- [x] `architecture-mistakes.md #37` 新增 (本轮)
- [x] `failure-modes.md N109` 新增 (本轮)
- [x] `.ai-memory/lessons/N109-decision-relaxation.md` (本文件) 新增
- [x] `.trae/skills/gaf-orchestrator/SKILL.md` 反思清单更新 (N109 加入)
- [x] `pending-roadmap.md` N109 状态标记
- [x] 5 层分发闭环 (N95)

## 5. 5 层分发 (N95 闭环)

| 层 | 路径 | 状态 |
|---|------|:---:|
| ① .ai-memory/ 教训层 | `.ai-memory/lessons/N109-decision-relaxation.md` (**本文件**) | ✅ |
| ② docs/ 架构教训层 | `.ai-memory/summaries/architecture-mistakes.md #37` (**本轮新增**) | ✅ |
| ③ spec/ 计划文档层 | `pending-roadmap.md` N109 状态 | ✅ |
| ④ SKILL.md 工作流层 | `.trae/skills/gaf-orchestrator/SKILL.md` 反思清单加入 N109 | ✅ |
| ⑤ project_rules.md 用户规则层 | `§3.5/§3.6` 重构 (**本轮修改**) | ✅ |

## 6. 反思 (Reflection)

**4 问**:
1. **本轮要做什么?** 改 §3.5 缩小授权范围 + §3.6 新增自决范围 + 5 层分发 N109
2. **现有代码哪里直接复用?** N108 范本 (5 层分发 + 4 维根因 + 7 步流程) 几乎可整段复制
3. **潜在风险/依赖?** AI 可能 scope creep (自创任务) / 跳过验证 / 不分发, 需硬约束 §3.3
4. **验收标准?** AI 后续选任务不需问, 5 层分发全 Y, 至少跑 1 段验证

**学习**:
- **N108 → N109 是 2 步走**: N108 解决"能不能 commit", N109 解决"该不该 commit 哪个", 2 步都不可省
- **"已计划" 必须明文定义**: AI 不知道什么是"已计划", 需 §3.2 列举 5 类判定条件
- **自决 ≠ 任意**: 必须有依据 (写到 plan) + 验证 + 5 层分发, 避免 AI 跑偏
- **N93+N108+N109 是三胞胎**: "甩命令" (N93) + "过度限制 commit" (N108) + "过度限制决策" (N109), 同一根因
- **"用户解放" 是渐进过程**: N108 解放 commit 节奏, N109 解放决策节奏, 下一步 N### 可能解放 spec 改动

## 7. 相关文件

- `.trae/rules/project_rules.md` (§3.5/§3.6 重构)
- `.ai-memory/summaries/architecture-mistakes.md` (#37 新增)
- `.ai-memory/meta/failure-modes.md` (N109 新增)
- `.trae/skills/gaf-orchestrator/SKILL.md` (反思清单加 N109)
- `docs/archive/pending-roadmap.md` (N109 状态)
- `.ai-memory/_archive/lessons-retired/N108-commit-rule-relaxation.md` (上游 N108, 已退役)

## 家族成员复发时间线（v9.0 合并 — 2026-07-07）

> **来源**: gaf-workflow-v9-slim Task 2.1 — 同根因家族合并
> **主条目**: 本文件 (N109 — decision relaxation)
> **家族根因**: AI 决策过度限制，需渐进解放 commit/决策/节奏/入口；同根因延伸 4 个教训

| 日期 | 编号 | 事件 | 已合并自 |
|------|------|------|---------|
| 2026-06-16 | N108 | commit rule relaxation — AI 可自执行 `git add` + `git commit` (按 §3.4 流程) | `2026-06-16-n108-commit-rule-relaxation.md` (保留独立，因上游 N108 是 commit 节奏) |
| 2026-06-16 | N109 | decision relaxation — 计划内任务 AI 自决选/拆/写/commit | (本主条目) |
| 2026-06-16 | N113 | auto-continue flow — 完成后不停下问用户，立即推进下一段 | `2026-06-16-n113-auto-continue-flow.md` (已删除) |
| 2026-06-16 | N115 | no-ask-start — 不问"是否开始"，完成立即推下一段 | `2026-06-16-n115-no-ask-start.md` (已删除) |
| 2026-06-21 | N127 | i18n + 反思节奏 + 部署推后 (混合主题，3 个独立子主题) | `2026-06-21-n127-i18n-pattern-and-reflection-rhythm.md` (已删除) |

**N127 拆分主题** (内容合并到本主条目 + project_rules.md):
- **i18n 接入**: 前端 i18n 必须按 4 语言 (zh-CN/en-US/ja-JP/ko-KR) 全覆盖，见 `project_rules.md §9`
- **反思节奏**: 每段 commit 后必跑反思清单 (N134 v9.0 已改为分级触发)
- **部署推后**: 优先简单开发任务，部署优化/运维脚本推后 (见 `pending-roadmap.md`)

**家族共性预防**:
- 计划内任务 AI 完全自治: 选/拆/写/commit/推进 (N109+N113+N115+N127)
- 3 类仍需用户授权: 跨工作区/远程操作 / 重写 history / 不可逆数据删除
- 完成后报告 ≤ 5 行 (commit hash + 分级分发 + ROADMAP + 下一段)，不停不等不问
- 反思节奏: 中/大修改每段 commit 后必跑反思，小修改豁免 (v9.0 §4.6 分级触发)
