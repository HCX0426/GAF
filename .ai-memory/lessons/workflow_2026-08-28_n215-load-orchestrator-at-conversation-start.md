---
date: 2026-08-28
symptom: [skip-orchestrator-load, missing-decision-tree, no-task-type-judgement, conversation-start-discipline]
solution: 每次对话起始必须先加载 gaf-orchestrator 判定 task_type（2026-08-27 用户决策强制）；再按分支 L2/L3 加载 skill + KB，否则入口纪律缺失会连带收尾（沉淀/反思）纪律一起丢
related_files:
  - .trae/skills/gaf-orchestrator/SKILL.md
  - .skills/rules/project_rules.md
created_by: AI
priority: high
n_id: N215
diff_keywords: ["orchestrator", "decision-tree", "task_type", "Skill(name='gaf-orchestrator')", "对话起始"]
---

# 对话起始未加载 gaf-orchestrator：任务入口纪律缺失

## 症状（2026-08-28 整轮 E2E/文档/沉淀对话）

本轮对话从"E2E 持久化"到"spec 归档"到"教训沉淀"跨越多次任务，但**从头到尾没有在起始调用 `Skill(name='gaf-orchestrator')`** 判定 task_type，直接进入执行。用户连续两次追问暴露：①完成任务不自动做沉淀判断；②每次对话没加载工作流。——两个缺口同源：**入口没走决策树，整套流程（判定→加载→闭环→沉淀）就没被触发**。

## 根因

规则与 skill 都有强制条款（orchestrator "对话起始强制判定 2026-08-27 用户决策：每次对话先加载本 skill 判定 task_type"；project_rules §0 "任务开始前必须先调用 gaf-orchestrator"），但它们是"AI 自执行约束"——没有 hook 强制（无法在 pre-commit 检查"这个对话加载过 orchestrator 没"）。依赖 AI 自觉时，一旦开始干活就容易跳过"门槛仪式"直接钻任务，且跳过入口后连收尾（collect/反思）一起省了。

## 解决方案（执行约定）

1. **每次对话第一条任务消息**：先 `Skill(name='gaf-orchestrator')` → 读决策树根节点判定 task_type（new_feature/bug_fix/documentation/refactor/unknown/meta_audit）→ 按分支加载对应 skill + KB → 再动手。
2. 纯问答/检查也过一遍判定（通常落 meta_audit/unknown），用户明确"闲聊"才口头标注跳过理由。
3. 收尾配套：最后一个 commit 后跑 `gaf-lesson-router collect` 自检"这轮有没有下次会再犯的坑"（N206：沉淀自决不问）；读 M3 hook 匹配建议而非只看 Passed。
4. 若本轮任务本身耗时长，中途也可标一次"当前仍处于 XXX 分支"以保持流程可追溯。

## 泛化原则

GAF 的流程纪律是"链条式"的：入口（orchestrator 判定）是第一节，缺了它后面的 L2/L3/闭环/沉淀全链断。凡是"AI 自执行"的入口步骤，不要因为"我知道该干嘛"就跳过——加载 skill 本身也是让 KB/教训进入上下文的必要动作。