---
maintainer: manual
source: GAF/backend/settings
load_when: [evidence, ai-tab-phase1]
priority: high
symptom: [LLMConfig, llm-provider, multi-provider, available_models]
solution: Phase 1 多服务商 LLM 配置 解决步骤
related_files:
  - backend/settings/models.py
  - backend/settings/views.py
  - backend/settings/migrations/0008_add_llm_config_available_models.py
  - frontend/src/pages/AI/AiConfigPage.tsx
  - frontend/src/api/ai.ts
created_by: AI
last_updated: 2026-08-31
---
## Solution

1. `backend/settings/models.py`: 在既有多行 `LLMConfig` 上新增 `available_models = models.JSONField(default=list)`（复用现有多 row + set_active 唯一激活模式，拒绝新建双套 Provider 表 — N151）。
2. `backend/settings/views.py`: `LLMConfigViewSet` 新增 `test_connection` action（POST `/settings/llm-config/{id}/test/`），用该 provider 的 api_key/base_url/model 发最小 chat 请求，返回成功 + latency 或 502 失败。
3. `backend/settings/serializers.py`: `LLMConfigSerializer` 暴露 `available_models` 字段。
4. `backend/settings/migrations/0008_add_llm_config_available_models.py`: 新增 `available_models` 字段迁移。
5. `frontend/src/api/ai.ts`: `LlmProviderConfig` 加 `available_models` + 新增 `testLlmProvider(id)` 调用 `/settings/llm-config/{id}/test/`。
6. `frontend/src/pages/AI/AiConfigPage.tsx`: Provider 卡片加"测试"按钮（逐 provider 调 testLlmProvider）+ 卡片展示模型 Tag 列表 + 编辑弹窗加"模型列表"TextArea（换行转数组）。
7. `frontend/src/i18n/locales/ailab.ts`: 4 语言新增测试/模型列表 key。
8. `frontend/src/pages/AI/__tests__/AiConfigPage.test.tsx` + `backend/settings/tests/test_llm_provider.py`: 新增测试覆盖 test 端点与 available_models 往返。
