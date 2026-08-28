---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-21-diagnosis-trigger-governance/
load_when: [evidence, 3-step-evidence, N204, diagnosis-trigger, superpowers-uninstall, lesson-frontmatter]
priority: high
symptom: [kb:evidence, 3-step-evidence, N204, task-failure-auto-diagnosis, superpowers-zh, lesson-fm-broken]
solution: Problem — 任务失败不自动诊断 (N204) + superpowers-zh 僵尸 L0 + 批量 lesson frontmatter 被格式重排破坏 (TD-378 回填遗漏 9 文件)
related_files:
  - .ai-memory/evidence/templates/problem.md
  - .skills/rules/env-hardrules.md
  - .ai-memory/lessons/N204-task-failure-auto-diagnosis.md
  - .ai-memory/meta/failure-modes.md
created_by: AI
last_updated: 2026-08-21
---
## Problem（症状 / 触发条件）

1. 现象: (a) 用户反馈"任务失败时 AI 不会自动调用诊断技能" — pipeline-task-diagnosis 仅在 gaf-orchestrator bug_fix 条件分支被引用, 规则层无 L0 硬约束, AI 可合法跳过诊断; (b) superpowers-zh.md 声明 alwaysApply 但从未被注入 (僵尸 L0); (c) 一次批量格式化把 16 个 lesson frontmatter 破坏 (行间插空行 + `topic: <key>---` 拼行尾), 9 个 archived-early lesson 缺 diff_keywords (TD-378 回填遗漏)
2. 触发条件: 对话出现失败关键词/日志含 NODE_TIMEOUT 等错误码; pre-commit 跑 check_lessons_updated 发现 frontmatter 解析失败
3. 影响范围: 全 AI 任务诊断路径 (N204); 规则加载信噪比 (superpowers-zh); lessons 检索/校验 (M3 diff_keywords + frontmatter 解析)
