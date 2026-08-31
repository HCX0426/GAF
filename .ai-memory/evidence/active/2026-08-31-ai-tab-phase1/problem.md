---
maintainer: manual
source: GAF/backend/settings
load_when: [evidence, ai-tab-phase1]
priority: high
symptom: [LLMConfig, llm-provider, multi-provider, available_models]
solution: Phase 1 多服务商 LLM 配置 — 见 solution.md
related_files:
  - backend/settings/models.py
  - backend/settings/views.py
  - backend/settings/migrations/0008_add_llm_config_available_models.py
  - frontend/src/pages/AI/AiConfigPage.tsx
  - frontend/src/api/ai.ts
created_by: AI
last_updated: 2026-08-31
---
## Problem

AI 页签原为"8 页平铺"，LLM 配置仅单条 `LLMConfig`，无法多服务商并存、无法逐 provider 连通测试、无法管理 provider 下模型列表。

触发：需要在 AiConfigPage 同时配置多个 LLM 服务商（OpenAI/DeepSeek/Qwen/Ollama）互不覆盖，并各自测试连通性。

影响范围：`backend/settings`（模型/序列化/视图）+ `frontend/src/pages/AI/AiConfigPage.tsx` + `frontend/src/api/ai.ts`。
