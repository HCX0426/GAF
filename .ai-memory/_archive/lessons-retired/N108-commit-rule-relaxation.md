---
date: 2026-06-16
symptom: [commit-rule-over-restriction, ai-pace-blocked, over-defensive-policy, n108, workflow-friction, permission-fatigue]
solution: '重构 project_rules.md §3 为 5 个子段: §3.1 禁止 (destructive 永远禁止) / §3.2 允许 (AI 自执行) / §3.3 硬约束 (分段粒度+验证+格式) / §3.4 流程 (7 步标准) / §3.5 仍需授权 (跨大阶段/rebase/branch -D)'
related_files:
  - .trae/rules/project_rules.md
  - .ai-memory/summaries/architecture-mistakes.md
  - .ai-memory/meta/failure-modes.md
  - .trae/skills/gaf-orchestrator/SKILL.md
created_by: AI
priority: high
level: L1
n_id: N108
topic: workflow
---
# N108: commit 规则过严 → AI 工作节奏被打断 (2026-06-16)

> **根因**: 旧 `project_rules.md §3` 仅 4 行, 简单粗暴"AI 不可执行 `git commit` 除非用户明确要求", 每 1 子任务停下等授权
> **触发条件**: 用户反馈 "commit 规则改下，允许 ai 自己合并提交"
> **影响**: AI 工作节奏被频繁授权打断, 用户体验差, 反而降低安全性 (用户疲劳 → 授权变松散)

## 1. 现象 (Symptom)

M1.A 后续 [B] 类 (N106 强化) 闭环时, AI 完成 5 个文件 (N107 工具 + lesson + pre-commit hook + architecture-mistakes #35 + failure-modes N107), 跑通验证 (0 error 0 warning) 后问用户 "是否授权 commit (5 个文件)?"。用户反馈:

> "commit的规则改下，允许ai自己合并提交"

之前 project_rules.md §3 仅 4 行, 没有区分 destructive vs normal 操作, 也没有"分段粒度" 的硬约束。

## 2. 根因 (Root Cause) (3 维)

1. **过度防御**: 早期项目怕 AI 误推 / 误删 / 误 reset, 简单粗暴"全部要用户授权"
2. **缺分层规则**: 没有区分"destructive 操作" (reset/revert/force push/branch -D) vs "正常 commit/add"
3. **缺自执行 commit 硬约束**: 即使放开 AI 自 commit, 也要有"分段粒度 + 验证 + 格式" 等约束

同根因家族 (N93+N95+N105+N107+N108):
- **N93**: AI 把本该自己跑的命令甩给用户 (甩命令) → N108 反向: AI 想 commit 也要等用户 (过度限制)
- **N95**: 5 层分发 → N108 5 层分发 (rule/lesson/architecture/skill/spec)
- **N105**: gaf-commit.sh --no-verify 透传 bug → N108 仍可自执行 `git commit --no-verify` (已知 bug 绕开)
- **N107**: hook 自动化兜底 → N108 "AI 自 commit" 安全基础
- **N108**: "AI 被过度限制" 是 N93 双胞胎

## 3. 修复 (Solution) — project_rules.md §3 重构

### 3.1 5 个子段 (本轮已实装)

**§3.1 禁止操作** (destructive 永远禁止):
- `git reset` / `git revert` / `git checkout` (回退用途) 仍仅用户可执行
- `git push --force` / `--force-with-lease` 需用户显式授权
- `commit --amend` 已 push 不可 amend
- AI 不可 push 到远程 (避免误推 main)

**§3.2 允许操作** (AI 可自执行):
- `git add <file>` + `git commit -m "..."` 按 §4.4 分段粒度, **无需逐次用户授权**
- `git commit --no-verify` 仍可自执行 (N105 透传 bug 已知)
- 只读命令 (status/log/diff/show/blame) + 分支操作 (stash/checkout -b)

**§3.3 自执行 commit 硬约束**:
- 按分段粒度 (1 个子任务 / 2-3 个相关子任务)
- commit 前本地验证 (lint/test/sync)
- commit message 格式: `<type>(<scope>): <subject>` (type ∈ feat/fix/refactor/docs/test/chore/perf/build/ci)
- 禁止空 commit + 禁止敏感文件 commit
- commit 后必须 `git log --oneline -1` 验证 (防 N82+N105 审计错觉)

**§3.4 分段提交流程** (7 步标准):
1. 完成 1 个子任务 / 2-3 个相关子任务
2. 本地验证 (lint/test/sync) 跑通
3. git status 看变更范围, git diff 检查内容
4. git add <specific_files> (不用 -A 或 .)
5. git commit -m "type(scope): subject" (不用 --no-verify, 除非 hook 已知误触)
6. git log --oneline -1 验证 commit 成功
7. 进入下一段 (回到 1)

**§3.5 仍需用户授权**:
- 跨大阶段合并 (Phase / 里程碑)
- 重写 history (`rebase -i` / `commit --amend` 已 push)
- 删除 branch/tag (`git branch -D` / `git tag -d`)
- `stash drop` / `clean -f` (可能丢未保存工作)

## 4. 验证 (Verification)

- [x] `project_rules.md §3` 已重构为 5 个子段
- [x] `architecture-mistakes.md #36` 新增
- [x] `failure-modes.md N108` 新增
- [x] `.ai-memory/lessons/N108-commit-rule-relaxation.md` (本文件) 新增
- [x] 5 层分发闭环: ① lessons ② architecture-mistakes ③ spec (轻量) ④ SKILL ⑤ project_rules
- [x] AI 后续工作直接按 §3.4 流程自 commit

## 5. 5 层分发 (N95 闭环)

| 层 | 路径 | 状态 |
|---|------|:---:|
| ① .ai-memory/ 教训层 | `.ai-memory/lessons/N108-commit-rule-relaxation.md` (**本文件**) | ✅ |
| ② docs/ 架构教训层 | `.ai-memory/summaries/architecture-mistakes.md #36` (**本轮新增**) | ✅ |
| ③ spec/tasks/checklist 计划文档层 | (本次为规则修订, 非任务实现, 跳过) | N/A |
| ④ SKILL.md 工作流层 | (.trae/skills/gaf-orchestrator/SKILL.md §3.2 反思清单已含 git 流程, 不需改) | ✅ |
| ⑤ project_rules.md 用户规则层 | `§3` 重构为 5 个子段 (**本轮修改**) | ✅ |

**附加 ⑥**: AI 后续工作流自执行 (本轮起效) ✅

## 6. 反思 (Reflection)

**4 问**:
1. **本轮要做什么?** 重构 project_rules.md §3, 允许 AI 自 commit, 5 层分发 N108
2. **现有代码哪里直接复用?** N107 5 层分发模板、architecture-mistakes.md 格式
3. **潜在风险/依赖?** 5 个子段 (禁止/允许/硬约束/流程/仍需授权) 必须平衡效率与安全
4. **验收标准?** 5 层分发全 Y + AI 后续自 commit 不再问授权

**学习**:
- **"全部禁止" → "分层规则"**: 安全约束不能一刀切, 必须区分 destructive vs normal
- **AI 节奏 vs 用户授权**: 每 1 子任务停下等授权 = 节奏打断, 改"按分段粒度自执行" 平衡效率与安全
- **N95 + N82 + N105 闭环后才敢放开**: hook 自动化 + 5 层分发 + 审计机制都就位后, "AI 自 commit" 才安全
- **同根因家族 (N93+N95+N105+N107+N108)**: "AI 不知道要主动做某事" + "AI 被过度限制" 是双胞胎, 都需硬约束
- **"用户授权" 重新定义**: 从"每次 commit" 降为"跨大阶段合并 / 重写 history", 用户解放生产力

## 7. 相关文件

- `.trae/rules/project_rules.md` (§3 重构)
- `.ai-memory/summaries/architecture-mistakes.md` (#36 新增)
- `.ai-memory/meta/failure-modes.md` (N108 新增)
- `.trae/skills/gaf-orchestrator/SKILL.md` (§3.2 反思清单已含 git 流程)
- `scripts/hooks/check_path_consistency.py` (N107, 顺带)
- `.pre-commit-config.yaml` (gaf-path-consistency-check hook, 顺带)
