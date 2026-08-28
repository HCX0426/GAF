---
maintainer: AI
source: GAF/.ai-memory/evidence/active/2026-08-22-env-hardrules-l0-split/problem.md
load_when: [evidence, 3-step-evidence]
priority: high
symptom: [kb:env-hardrules-l0-budget, TD-369, rules-split]
solution: env-hardrules L0 预算超 62KB 且只增不减，情境约束常驻每次注入
related_files:
  - .skills/rules/env-hardrules.md
  - .ai-memory/meta/env-hardrules-contextual.md
created_by: AI
last_updated: 2026-08-22
---
## Problem（症状 / 触发条件）

env-hardrules.md (L0 alwaysApply) 承载 N191-N204 情境约束，每次对话系统提示注入 34.5KB；叠加 project_rules.md 28.1KB = 62.6KB，违反 TD-369 ≤62KB 注入预算，且"只减不增"硬约束被违反（已退役 N194/N197/N198/N199 正文仍注入）。

触发条件：每次新对话 opencode 自动注入 .skills/rules/ 全部 .md。
影响范围：所有对话 token 预算 + 规则双份维护。
