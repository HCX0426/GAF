---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, verification-step, evidence-verification]
solution: Verification 模板 — 跑过的命令 + 实际输出 + 截图;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/problem.md
  - .ai-memory/evidence/templates/solution.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-08-09
---
## Verification（验证）

$ grep "TD-355\|TD-356\|TD-357\|TD-358\|TD-359\|TD-360\|TD-361\|TD-362" docs/tech-debt/active.md

预期：8 个 TD 条目均存在，含完整的问题描述和修复方案

$ grep "active.*11\|total.*273" docs/tech-debt/README.md

预期：README.md 总览表显示 active=11, total=273