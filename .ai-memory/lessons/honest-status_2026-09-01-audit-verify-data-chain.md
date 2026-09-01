---
topic: honest-status
date: 2026-09-01
created_by: AI
symptom: [audit, meta_audit, 审计, 检查, 功能验证, 数据链路, 键名不匹配, 硬编码默认]
solution: "功能型模块审计必做逐功能数据链路核对: ① 模型/数据来源 (grep 硬编码默认 gpt-4o-mini / request.data.get('model' / .first()) ② 前后端契约键名逐一比对 (如 by_model vs model_distribution) ③ 后端能力≠前端交互 (字段存在≠UI已实现) ④ 浏览器实测每个交互输入→输出。静态结构审计会漏功能正确性问题。详见 ai-operating-handbook Part 2 审计检查清单。"
diff_keywords: [ask-question, usage-stats, llm-config, by_model, model_distribution, estimate-cost, available-models, AskView, default_model]
related_files:
  - .ai-memory/meta/ai-operating-handbook.md
  - backend/gaf_ai/qa_views.py
  - backend/gaf_ai/views.py
  - backend/gaf_ai/llm_service.py
  - frontend/src/pages/AI/AiConfigPage.tsx
  - frontend/src/pages/AI/AIUsageDashboard.tsx
  - frontend/src/pages/AI/QAPanel.tsx
  - frontend/src/api/ai.ts
---

# 功能型模块审计必须逐功能核对数据链路（静态结构审计会漏功能 bug）

## Symptom

审计 AI 等**功能型模块**（配置/用量/问答/助手）时，只做了**静态结构审计**
（页面存在、是否完成、调用了哪些 API、页面间是否冗余），漏掉了 4 类功能正确性问题：

1. **硬编码默认模型**：`AskView` 用 `request.data.get('model', 'gpt-4o-mini')` 兜底，
   前端不传 model 就永远用 gpt-4o-mini，用户配的 DeepSeek/Qwen 用不上（"智能问答不能选配置好的模型"）。
2. **前后端字段契约不匹配**：后端 `usage-stats` 返回 `by_model`，前端 `AIUsageDashboard` 读
   `model_distribution` —— 键名不一致导致"模型使用分布"永远空（浏览器一眼可见，静态核对也能抓）。
3. **字段存在 ≠ 交互实现**：后端 `LLMConfig.available_models`（多模型 JSONField）早已存在且序列化器
   透出，但前端 AiConfigPage 只管理单个 default_model —— 后端能力与前端交互脱节。
4. **prompt 上下文缺失导致功能不可靠**：AI 助手 `generate-pipeline-stream` 只有一段 system + 一句话
   描述，无节点模板/技能/历史上下文，直出 Pipeline 不可靠；`optimize_pipeline` 不基于执行失败数据盲猜。

## Root cause

- 审计视角重"**结构/完成度/冗余**"，轻"**功能数据链路**"（数据从哪来 → 用什么模型 → 怎么算 → 前端怎么读）。
- 依赖静态阅读 + search 子代理的"页面盘点"（行数/API/重叠），未逐功能走通输入→输出。
- 未尽早用浏览器**实测每个交互**——很多功能 bug 在 UI 里一眼可见（模型下拉空、分布空）。

## Fix / Prevention（审计清单强化）

对功能型模块审计，除结构层外必做**逐功能数据链路核对**：

1. **模型/数据来源**：每个功能的模型或数据来自哪？激活 provider？DB 单例？还是硬编码默认值？
   → grep `'gpt-4o-mini'` / `request.data.get('model'` / `.first()` 等硬编码兜底。
2. **前后端契约逐一比对**：后端返回键 vs 前端读取键（`by_model` vs `model_distribution`）；
   接口类型定义 vs 实际消费。
3. **浏览器实测每个交互**：输入 → 观察输出（模型下拉是否反映配置、分布是否为空、tooltip 是否有数据）。
4. **后端能力 vs 前端交互脱节**：字段/接口存在 ≠ UI 已实现（`available_models` 存在但前端未用）。

## 沉淀位置说明

- **暂不进 N##**：Active N## 已超限（74 > 70，N181 紧急评估中）+ project_rules §4.12 新增门槛
  （未来 30 天 ≥3 次才入）。本条作为 lessons + handbook 流程强化沉淀。
- 与 N126（文档诚实标记）/ N167（评估清单）相关但更具体：**审计深度**。
