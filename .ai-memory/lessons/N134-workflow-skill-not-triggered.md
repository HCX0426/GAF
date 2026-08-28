---
id: N134
date: 2026-06-28
l2_candidate: true
symptom: 'User pointed out that throughout a 30+ commit audit-fix conversation, gaf-orchestrator
  §3.2 ① 4 问反思 (line 215) and gaf-lesson-router §3 End-of-Task Collection were never
  executed. User asked: ''is it that the workflow skills don''t integrate these skills
  together?'''
category: workflow
cause: Execution deviation, not design flaw. gaf-orchestrator SKILL.md §3.2 mandates
  'every Round reflection must fill ①-⑧', and Load Timing Matrix lists task_complete
  → must-load rhythm-autonomy/bypass-review/distribution (i.e. lesson-router). Skills
  ARE integrated by design. AI treated each batch as 'in-progress' rather than 'task_complete',
  skipping reflection and lesson collection.
solution: '1. Round 3 reflection executed per §3.2 ①-⑤ + ㉑-㉔ (see audit doc §十六 Round
  3).
  2. Lesson file created per gaf-lesson-router §3 End-of-Task Collection checklist
  (this file).
  3. 5-layer distribution executed (① this file ② architecture-mistakes ③ spec ④ SKILL.md
  unchanged ⑤ project_rules.md hard constraint added).
  4. Re-check all fixed items via Grep + Glob + manage.py check + tsc — all verified.
  '
priority: high
diff_keywords: ["user", "pointed", "out", "that", "throughout", "commit", "audit-fix", "conversation", "gaf-orchestrator"]
related_files:
- .trae/skills/gaf-orchestrator/SKILL.md
- .trae/skills/gaf-lesson-router/SKILL.md
- .trae/rules/project_rules.md
cross_refs:
- N109
- N113
- N115
- N127
- N132
created_by: AI
level: L1
n_id: N134
topic: workflow
---




# N134 — Workflow skills not triggered despite being integrated

## What happened

During a multi-session audit-fix conversation (30+ commits fixing 134 issues across P0/P1/P2/P3 batches), the user pointed out:

> "整个对话都没有 gaf-orchestrator/SKILL.md#L215 gaf-lesson-router/SKILL.md，还是工作流skill里没把这些skill联合起来？"
> (Throughout the entire conversation, neither gaf-orchestrator/SKILL.md#L215 [4 问反思] nor gaf-lesson-router/SKILL.md were used. Or is it that the workflow skills don't integrate these skills together?)

Investigation confirmed:
- gaf-orchestrator SKILL.md §3.2 ① (line 215) mandates "每次 Round 反思必填 ①-⑧ 项" (every Round reflection must fill items ①-⑧)
- gaf-lesson-router §3 provides "End-of-Task Collection" checklist (6 steps)
- Load Timing Matrix lists task_complete → must-load rhythm-autonomy/bypass-review/distribution
- **Skills ARE integrated by design** — the issue is AI execution deviation

## Root cause

1. **AI treated each batch as "in-progress"**: Because the audit fix was a continuous multi-batch effort, AI classified each batch commit as an intermediate step rather than a "task_complete" event. This skipped the lesson-router collect branch.

2. **Reflection checklist not hard-executed**: Although §3.2 ① 4 问反思 is in SKILL.md, AI prioritized "完成后立即推进下一段" (N127 推进自决) over reflection, skipping the reflection step after each commit.

3. **No enforcement mechanism**: The skills rely on AI self-discipline to invoke them. There is no programmatic hook that forces reflection after commit.

## Fix

1. **Round 3 reflection executed** per §3.2 ①-⑤ + ㉑-㉔ (documented in audit doc §十六 Round 3)
2. **Re-check all fixed items** via Grep + Glob + manage.py check + tsc — 15 verification checks, all ✅
3. **Lesson file created** (this file) per gaf-lesson-router §3 checklist
4. **5-layer distribution**:
   - ① lessons: this file
   - ② architecture-mistakes: summary added to architecture-mistakes.md
   - ③ spec: clause added to spec.md
   - ④ SKILL.md: gaf-orchestrator §3.2 + gaf-lesson-router §3 already have constraints, no change needed
   - ⑤ project_rules.md: hard constraint added to §6.5

## Prevention

- **每段 commit 后必跑 §3.2 ① 4 问反思** (even if treated as "in-progress")
- **task_complete 判定标准放宽**: 单批 commit 完成 = 触发 lesson-router collect 检查 (not just end of entire task)
- **用户反馈"未执行某 skill"时**: 立即按该 skill 流程补执行，不辩解
- **反思优先于推进**: N127 推进自决 ≠ 跳过反思; 反思是推进的前提，不是可选步骤

## Verification

- Round 3 reflection: ✅ documented in audit doc §十六
- Re-check table: ✅ 15 items all verified
- django check: ✅ 0 issues
- tsc: ✅ 0 errors
- 5-layer distribution: ✅ all 5 layers updated

## 家族成员复发时间线（v9.0 合并 — 2026-07-07）

> **来源**: gaf-workflow-v9-slim Task 2.1 — 同根因家族合并
> **主条目**: 本文件 (N134 — workflow skills not triggered)
> **家族根因**: 反思流程未硬触发，AI 优先推进跳过反思/lesson 收集

| 日期 | 编号 | 事件 | 已合并自 |
|------|------|------|---------|
| 2026-06-28 | N134 | 30+ commit audit-fix 对话全程未触发 §3.2 ① 4 问反思 + lesson-router collect | (本主条目) |
| 2026-07-05 | N134-recurrence | WebSocket 修复后先 commit 后才调 lesson-router collect，违反 §3 "End-of-Task Collection" pre-commit gate | `2026-07-05-n134-recurrence-reflection-before-commit.md` (已删除) |

**家族共性预防**:
- 每段 commit 后必跑 §3.2 ① 4 问反思 (即使视为 "in-progress")
- lesson-router collect 必须在 `git commit` **之前** 调用，不是 post-commit cleanup
- N127 推进自决 ≠ 跳过反思; 反思是推进的前提
