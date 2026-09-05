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
last_updated: 2026-09-05
---
## Verification（验证）

$ cd backend && python -m pytest workers plugins protocol -q
预期：`385 passed, 40 deselected`（退出码 0）

$ cd backend && python -m pytest resources tasks -q
预期：`230 passed`（退出码 0）

$ cd frontend && npx tsc -b --pretty false
预期：退出码 0（修复前退出码 2、6 个类型错误）

$ cd frontend && npx vitest run src/stores/__tests__/useAuthStore.test.ts src/api/__tests__/client.test.ts
预期：`13 passed`（退出码 0）

$ cd backend && python ../scripts/check_prod_settings.py
预期：安装 whitenoise 前 `FAIL: middleware 不可导入: whitenoise...`（退出 1）；安装后 `prod settings OK: 13 middleware, staticfiles backend = whitenoise.storage.CompressedManifestStaticFilesStorage`（退出 0）

$ python -m ruff check scripts/check_prod_settings.py backend/config/settings/prod.py
预期：`All checks passed!`
