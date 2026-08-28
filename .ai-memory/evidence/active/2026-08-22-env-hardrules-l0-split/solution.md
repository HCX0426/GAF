---
maintainer: AI
source: GAF/.ai-memory/evidence/active/2026-08-22-env-hardrules-l0-split/solution.md
load_when: [evidence, 3-step-evidence]
priority: high
symptom: [kb:env-hardrules-l0-budget]
solution: 拆 L0 常驻 + contextual 按需载体，orchestrator 触发加载
related_files:
  - .skills/rules/env-hardrules.md
  - .ai-memory/meta/env-hardrules-contextual.md
  - .opencode/skills/gaf-orchestrator/SKILL.md
created_by: AI
last_updated: 2026-08-22
---
## Solution（解决步骤）

1. 将 N191/N192/N193/N196/N204 活跃段 + N194/N197/N198/N199 退役段从 env-hardrules.md 迁出至 .ai-memory/meta/env-hardrules-contextual.md
2. env-hardrules.md 仅保留 N188/N190/N195 + 情境约束索引表（指向 contextual）
3. 在 gaf-orchestrator SKILL.md L2/L3 段加触发加载点：task_type ∈ {fix,new_feature,refactor,documentation} 或失败关键词时 Read contextual 对应段
4. 同步 failure-modes/handbook/skills/docs 中指向缺失 lesson 的断链至 contextual 权威载体
5. 补 B2 spec-context 载体 (docs/archive/spec-context/env-hardrules-l0-split-context.md) 含 N151 五步 + N167 七维度
