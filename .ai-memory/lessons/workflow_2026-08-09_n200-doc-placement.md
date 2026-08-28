---
date: 2026-08-09
topic: workflow
n_id: N200
symptom: [spec-placement, doc-governance, skill-vs-spec-boundary]
solution: 创建 spec 文档前未检查文档分层规则，错误放入 Skill 目录
diff_keywords: ["project", "rules", "project_rules", "spec-placement", "doc-governance", "skill-vs-spec-boundary"]
related_files:
  - .trae/rules/project_rules.md
created_by: AI
priority: high
---


# N200: Spec 文档错误放入 Skill 目录

## 问题描述

AI 在创建 `pipeline-task-diagnosis` 的 spec 文档时，错误地将 `spec.md` 放入了 `.trae/skills/pipeline-task-diagnosis/` 目录。

**错误路径**：
```
.trae/skills/pipeline-task-diagnosis/
  ├── SKILL.md      ✅ 正确
  └── spec.md       ❌ 错误：spec 不应在 Skill 目录
```

**正确路径**：
```
docs/specs/active/
  └── 2026-08-09-pipeline-task-diagnosis-spec.md  ✅ 正确
```

## 根因分析

1. **规则加载不完整**：创建文档前未主动查阅 `project_rules.md` §2.1 文档分层规则
2. **Skill 目录的"惯性"**：看到 Skill 目录有多个文件，就默认 spec 也应放入
3. **缺少前置检查**：创建新文档前没有检查"应该放哪"这一步

## 违反的规则

```
project_rules.md §2.1 文档分层规则
├── AI skills: .trae/skills/ (只放 SKILL.md)
├── AI 工作产物: docs/specs/active/ (spec/plan)
└── 项目级: docs/ (用户可读文档)
```

## 解决方案

### 新增规则（project_rules.md §2.1.1）

创建任何新文档前，必须按以下清单判定归属：

```text
□ 1. 文档类型判定:
   - Skill 定义 (SKILL.md) → .trae/skills/<skill>/
   - Spec/Plan (设计规范/实施计划) → docs/specs/active/
   - 架构评估 → .trae/architecture/
   - 用户可读文档 (分析/设计/规范) → docs/ 对应子目录

□ 2. 禁止放入 Skill 目录的内容:
   - ❌ spec.md / plan.md / design.md (这些是 AI 工作产物)
   - ❌ 教程/说明文档 (除非是 SKILL.md 的必要补充)
   - ✅ 只允许 SKILL.md (Skill 定义本身)

□ 3. 自问验证:
   - "这个文档是 Skill 定义本身吗？" → 是 → .trae/skills/
   - "这个文档是 AI 的执行产物吗？" → 是 → docs/specs/active/
```

### Spec 归档流程

- 活跃 spec → `docs/specs/active/`
- 完成并验证 → `docs/specs/archived/YYYY-MM/`
- 历史遗留 → `docs/specs/legacy-trae/`

## 预防措施

1. **创建文档前必须检查归属**：按 §2.1.1 清单判定
2. **Skill 目录只放 SKILL.md**：其他任何文档都是错误
3. **主动加载规则**：创建文档前先读 `project_rules.md` §2.1

## 教训

- AI 在新会话中容易忘记规则，需要在关键操作前主动加载
- Skill 目录的职责是"Skill 定义"，不是"Skill 相关文档集合"
- Spec 是 AI 的工作产物，应放在 `docs/specs/active/` 而非 Skill 目录