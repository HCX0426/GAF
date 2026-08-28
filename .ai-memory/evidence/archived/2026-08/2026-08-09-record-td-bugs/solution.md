---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, solution-step, evidence-solution]
solution: Solution 模板 — 列步骤 + 涉及文件 + 命令;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/problem.md
  - .ai-memory/evidence/templates/verification.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-08-09
---
## Solution（解决步骤）

1. 在 docs/tech-debt/active.md 登记 TD-355~TD-362，含问题描述/影响/修复方案/关联文件
2. 更新 docs/tech-debt/README.md 总览表计数 (active 3→11, total 265→273)
3. 提交登记 commit，后续按优先级从 P2 开始逐个开 spec 修复