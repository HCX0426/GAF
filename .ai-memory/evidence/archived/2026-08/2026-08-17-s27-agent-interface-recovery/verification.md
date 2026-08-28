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
last_updated: 2026-06-16
---
## Verification（验证）

$ D:\code\environment\conda\envs\gaf\python.exe -m pytest agent/tests/ -p no:django -o addopts=""
$ D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/scheduler/tests/ -q

预期：agent 2281 passed / 3 skipped；backend scheduler 47 passed（e2e 137 deselected）；新增 test_s27_recovery_wiring.py 21 passed；test_recovery_link_wiring.py 16 passed；yaml 被 Manager 加载 states=2 transitions=1 safe=['main_menu']
