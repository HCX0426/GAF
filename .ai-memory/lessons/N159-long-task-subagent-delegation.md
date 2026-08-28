---
date: 2026-07-13
symptom: [workflow, subagent, efficiency, context-bloat, parallel-delegation]
solution: 长任务（≥5 子任务）应主动评估独立性并分拆给 subagent 并行执行，主上下文只做依赖链 + 最终验证 + commit。判定标准：子任务数 ≥3 且互相独立 → 并行；单子任务涉及 ≥2 文件协调 → 委托；大量 Read 调查 → search subagent；有依赖 → 主做依赖链。
diff_keywords: ["project", "rules", "project_rules", "skill", "yn", "matrices", "yn-matrices", "workflow", "subagent", "efficiency", "context-bloat", "parallel-delegation"]
related_files:
  - .trae/rules/project_rules.md
  - .trae/skills/dispatching-parallel-agents/SKILL.md
  - .ai-memory/meta/yn-matrices.md
created_by: AI
priority: high
n_id: N159
topic: agent-impl
level: L1
cross_refs: [N109, N113, N127]
l2_candidate: true
---


# N159 — 长任务应主动分拆给 subagent

> **级别**: L1 可复用经验（Y/N 检查清单 + 影响 AI 全局行为）
> **分类**: AI 行为约束 — 任务执行节奏（N109 自治边界）
> **来源**: 2026-07-13 用户反馈"执行任务过长时，应该多分子任务给subagent的（得记录下？）"
> **状态**: ✅ FIXED（本教训 + §3.6 N109 家族引用）

## 触发原话

> "执行任务过长时，应该多分子任务给subagent的（得记录下？）"

## 症状

AI 接到大任务（如"全部修复 P0+P1+P2 共 9 项 + 月度检查 16 项"）时，倾向于在主上下文中串行执行所有子任务，导致：
1. 主上下文膨胀（多个文件的 Read/Edit 结果堆积）
2. 后期改动效率下降（上下文越长，推理质量越低）
3. 用户等待时间长（无法并行）

## 根因

- AI 默认"自己做完"，没有主动评估"哪些子任务可以独立分给 subagent"
- 规则文档 §3.6 (N109) 说"计划内任务 AI 完全自治"，但没有指导"何时应该委托给 subagent"
- superpowers-zh 的 `dispatching-parallel-agents` skill 存在但 AI 不会主动调用

## 修复方案

### 判定标准：何时应该分拆给 subagent

| 条件 | 行动 |
|------|------|
| 子任务数 ≥ 3 且互相独立 | 用 subagent 并行 |
| 单个子任务涉及 ≥ 2 个文件的协调修改 | 用 subagent（保护主上下文） |
| 任务预估涉及大量 Read（如审计、调查） | 用 search subagent |
| 子任务有依赖关系 | 主上下文做依赖链，独立部分委托 |

### 执行流程

1. **任务拆分**：用 TodoWrite 列出所有子任务
2. **独立性评估**：标记每个子任务的依赖关系
3. **并行委托**：无依赖的子任务用 `Task` 工具并行委托给 subagent
4. **主上下文只做**：依赖链 + 最终验证 + commit

### 典型场景

- **认证修复（9 项）**：前端核心（tokenStore+client+auth+useAuthStore）有依赖链 → 主上下文做；后端配置（base.py+celery.py）独立 → subagent 做
- **月度检查（16 项）**：纯文档 → subagent 做
- **代码审计**：多个文件独立扫描 → 多个 search subagent 并行

## 验证标准

- ✅ 大任务（≥ 5 子任务）开始前，AI 评估哪些可以委托给 subagent
- ✅ 主上下文的 TodoWrite 标注每个子任务是"主做"还是"subagent 做"
- ❌ 禁止在主上下文中串行执行 ≥ 5 个独立子任务

## 分发

- [x] lessons: 本文件
- [ ] yn-matrices: §2 ai-autonomy（待补充）
- [ ] project_rules §6.4: 索引行（待补充）
