---
date: 2026-06-15
symptom:
- distribution:gap
- 分发缺位
- 5-layer-missing
- n95
- ai-learning-failure
solution: '5 层分发机制（5 layers: memory / docs / spec / skill / rules）'
diff_keywords: ["failure", "modes", "failure-modes", "distribution", "gap"]
related_files:
- .ai-memory/meta/failure-modes.md
- .trae/rules/project_rules.md
- scripts/bootstrap/sync_skills.py
created_by: AI
priority: high
level: L1
n_id: N95
topic: workflow
---



# AI 学习只分发到 1-2 层就停（5 层分发缺位）

## 症状

- AI 总结完新经验/新教训 → 默认只写 `.ai-memory/lessons/<date>-<symptom>.md` 一处就当完事
- 缺 ② .ai-memory/summaries/ 架构教训层
- 缺 ③ spec.md / tasks.md / checklist.md 计划文档层
- 缺 ④ SKILL.md 工作流/技能层
- 缺 ⑤ project_rules.md 用户规则层
- 用户反馈："ai 总结学习部分,会提升到文档,skill 和规则里才对吧"

## 根因（5 维）

1. **AI 不擅长"分发"**: 同一反模式三次（N93/N94/N95）都出在"分发"环节 — AI 不知道要分发到哪、分发到几层
2. **缺少"全栈"意识**: AI 写教训时只想到 `.ai-memory/` 一处,没想到 spec / skill / rules 也要同步
3. **缺分发 checklist**: 写完教训后 AI 没清单提醒"5 个层级都分发了吗?"
4. **没有强制机制**: pre-commit hook 只验证 commit 合规,不验证"教训分发完整度"
5. **规则不进仓库**: gaf-dev-workflow / project_rules.md 之前只在 workspace 根,团队成员拉新仓库看不到 → 分发链断了

## 解决步骤（M0.L 闭环）

1. **层 ① 教训层**: 创建本文件 `2026-06-15-n95-distribution-gap.md` (✅)
2. **层 ② 架构教训层**: `architecture-mistakes.md` 加 #27 AI Learning Distribution Gap (✅)
3. **层 ③ 计划文档层**: spec.md §14.6 + tasks.md M0.L + checklist.md 2.18-2.24 (✅)
4. **层 ④ SKILL.md 层**: gaf-dev-workflow §3.2 反思清单加 ⑤ 项 5 层分发 Y/N 矩阵 (✅)
5. **层 ⑤ 规则层**: gaf-dev-workflow + project_rules.md 入 GAF 仓库, sync_skills.py 分发 5+1 (✅)

## 验证

- `python GAF/scripts/bootstrap/sync_skills.py --check` 通过 (10 skill 副本 + 2 rule 副本一致)
- `gaf_init.sh` 验证清单: 仓库内 5/5 + 1/1, workspace 根 5/5 + 1/1
- 5 个 GAF skills + 1 个 rule 在 GAF 仓库和 workspace 根各一份

## 预防

- pre-commit hook: `sync_skills.py --check` 每次提交前必跑
- `gaf-dev-workflow` §3.2 反思清单: ⑥ 项 5 层分发 Y/N 矩阵必查
- `gaf_init.sh` 启动验证 5+1 分发,缺则自动修复
- 任何新规则/新 skill 必须先入 GAF 仓库,再分发

## 相关

- 失败模式: N93 (decision tree 漂移) / N94 (skill 漂移) / N95 (本条 5 层分发)
- 教训: #27 AI Learning Distribution Gap
- spec: v8.4 §14.6 5 层分发机制
- tasks: M0.L 5 层分发机制（N95 闭环）
