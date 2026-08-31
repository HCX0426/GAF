---
maintainer: manual
source: GAF/backend/settings
load_when: [evidence, ai-tab-phase1]
priority: high
symptom: [LLMConfig, llm-provider, multi-provider, available_models]
solution: Phase 1 多服务商 LLM 配置 验证
related_files:
  - backend/settings/models.py
  - backend/settings/views.py
  - backend/settings/migrations/0008_add_llm_config_available_models.py
  - frontend/src/pages/AI/AiConfigPage.tsx
  - frontend/src/api/ai.ts
created_by: AI
last_updated: 2026-08-31
---
## Verification

$ python -m pytest backend/settings/tests/ -q
预期: 20 passed（含 test_llm_provider.py 8 项：CRUD/激活唯一性/key 加密往返/available_models 往返/test 端点 400 路径/多 provider 并存）

$ cd frontend && npx vitest run src/pages/AI/__tests__/AiConfigPage.test.tsx
预期: 7 passed（含逐 provider"测试"按钮调用 testLlmProvider(id)）

$ cd frontend && npx tsc --noEmit
预期: 0 errors

$ python -m ruff check backend/settings/
预期: All checks passed
