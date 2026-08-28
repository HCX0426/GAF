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
last_updated: 2026-06-16
---
## Solution（解决步骤）

<!-- 1-5 个原子步骤，每步 ≤ 1 行。每步都要可执行，不要写"考虑 / 评估 / 评估一下"。
     模板校验：
     - 至少 1 步包含具体命令 / 文件路径 / API 端点
     - 不允许纯叙述
-->
1. <具体步骤 1，含命令或路径>
2. <具体步骤 2>
3. <具体步骤 3>
