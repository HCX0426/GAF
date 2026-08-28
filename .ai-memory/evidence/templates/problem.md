---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, problem-step, evidence-problem]
solution: Problem 模板 — 描述症状/触发条件/影响范围;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/solution.md
  - .ai-memory/evidence/templates/verification.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-06-16
---
## Problem（症状 / 触发条件）

<!-- 用 1-3 句话描述你遇到了什么问题。AI 看到这部分应该能秒懂：
     1. 现象（报错信息 / 行为偏差）
     2. 触发条件（什么操作 / 什么环境）
     3. 影响范围（哪些模块 / 哪些用户）

     模板被 gaf-3step-evidence pre-commit hook 校验：
     - TODO / [fill in] / xxx / lorem ipsum 等占位符必须替换
     - 至少 1 个运行命令 / 文件路径 / API 端点
-->
