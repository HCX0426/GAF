---
date: 2026-08-21
topic: workflow
n_id: N204
symptom: [task-failure-no-auto-diagnosis, diagnosis-skill-not-loaded, pipeline-node-fail]
solution: "pipeline-task-diagnosis 仅在 gaf-orchestrator bug_fix 分支条件引用, 规则层无 L0 硬约束强制 AI 在任务失败时自动加载诊断。需 L0 硬约束: 对话出现失败关键词 / 日志含 pipeline 错误码时, 必须调用 Skill(name='pipeline-task-diagnosis'), 即使任务分类为 new_feature/refactor/documentation 也适用。"
diff_keywords: ["pipeline-task-diagnosis", "diagnosis", "node-fail", "NODE_TIMEOUT", "TEMPLATE_NOT_FOUND", "env-hardrules", "load_when"]
related_files:
  - .trae/rules/env-hardrules.md
  - .trae/skills/pipeline-task-diagnosis/SKILL.md
  - .trae/skills/gaf-orchestrator/SKILL.md
  - .trae/skills/gaf-reflect-and-evolve/SKILL.md
  - .trae/skills/gaf-knowledge-base/SKILL.md
created_by: AI
priority: high
---

# N204: 任务失败不自动诊断 — pipeline-task-diagnosis 触发断层

## 背景

用户反馈"任务失败时 AI 不会自动调用诊断技能"。深入评估 `.skills/` 全目录后发现根因：

1. **决策树条件引用**：`pipeline-task-diagnosis` 只在 `gaf-orchestrator` bug_fix 分支 step_4_diagnose 被条件引用（symptom 需命中"pipeline 节点/OCR/模板匹配/坐标"），不在任何 `load_skills` 列表顶层
2. **标准链路绕过**：bug_fix 标准链路只加载 `systematic-debugging`（通用方法论），不含 GAF 专属的 `pipeline-task-diagnosis`
3. **规则层无强制**：`env-hardrules.md` 无"任务失败必须诊断"的 L0 硬约束
4. **"主动触发"是空中楼阁**：SKILL.md 内部声明的"对话出现失败关键词→主动加载"只有已加载该 SKILL 才能看到，而加载它又依赖上述链路 → 鸡生蛋问题

## 修复（2026-08-21）

1. `.trae/skills/pipeline-task-diagnosis/SKILL.md` 增加 `load_when` front-matter（bug_fix + 失败关键词 + 错误码）
2. `gaf-orchestrator` bug_fix 分支 `load_skills` 顶层加入 `pipeline-task-diagnosis`
3. `env-hardrules.md` 新增「诊断触发硬约束 (N204)」L0 段：失败关键词/错误码必须加载诊断，跳过需记录理由
4. `gaf-reflect-and-evolve §6.3` 明确与 pipeline-task-diagnosis 的边界（职责划分表）
5. `gaf-knowledge-base §5` bug_fix.diagnose 加入 `pipeline-task-diagnosis`
6. `.skills/README.md` 分类统计表补上 pipeline-task-diagnosis 条目（Testing & Quality 3→4，合计 17→18）
7. 卸载 `superpowers-zh.md`（僵尸 L0：声明 alwaysApply 但实际从未被注入；边界声明已迁移到 README.md 边界规则）

## 预防

- 对话中出现失败关键词 / 日志含 pipeline 错误码 → 先加载诊断，排除配置/数据流/弹窗问题，再谈修复
- 新增 GAF 特定方法论 skill 时，必须同时接入：决策树 load_skills / 规则层硬约束 / README 索引 / gaf-* 边界声明
