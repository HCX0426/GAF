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

<!-- 必填可运行命令。gaf-3step-evidence hook 校验：
     - 必须有 `## Verification` 段
     - 段内至少 1 行匹配 $ / python / bash / pip / pytest / git 等命令前缀
     - 否则 --strict 模式下阻断 commit

     推荐格式：复现命令 + 预期输出 / 退出码
-->

$ <复现命令 1>
$ <复现命令 2>

预期：<退出码 / stdout 关键字 / 行为变化>
