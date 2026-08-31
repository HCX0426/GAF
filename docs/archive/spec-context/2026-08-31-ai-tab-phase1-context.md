---
spec: 2026-08-31-ai-tab-agent-learning-spec
phase: Phase 1 多服务商 LLM 配置
created: 2026-08-31
---

# Spec Context — AI 页签改造 Phase 1（多服务商 LLM 配置）

## 用户决策

- 无额外用户决策（spec 已授权 Plan Phase 1 全栈实施，自决推进）。

## N151 架构评估

### 1. 架构盘点（4 维度）

- **数据**: 现 `settings_llm_config` 表非单例（多行可用），已有 `is_active` 唯一激活语义；`set_active` action 已实现排他激活。
- **依赖**: `LLMConfig` 被 `gaf_ai.llm_service._get_llm_config()`（filter is_active=True）与 agent `llm_adapter.py` / `graph.py` 消费；serializer/view/url 已就绪。
- **调用**: 前端 `AiConfigPage` ALREADY 通过 `/settings/llm-config/` 做多 provider CRUD + set-active；LLM 调用链走 `gaf_ai.llm_router` 4-level fallback（preferred 读 is_active 行）。
- **历史**: spec 原设计提 `LLMProvider` 新表 + `LLMConfig` 保留为激活指针。但盘点发现现网 `LLMConfig` 已天然支持多行 + 排他激活，无需要新建双表。

### 2. 识别反模式

- **❌ 双套并存**: spec 草稿「新增 `LLMProvider` 表 + `LLMConfig` 保留」= 两套 LLM 存储结构 → 拒绝。现有 `LLMConfig` 多行 + `is_active` 已完整表达 provider[apiKey/baseUrl] → Model[] 能力，仅需补 `available_models` 字段。
- **❌ 最小化修补**: 非-workaround，是复用既有架构的合理实现。

### 3. A/B/C 备选

- **A（采用）**: 在既有 `LLMConfig` 多行模型上增 `available_models` JSON 字段 + `test` action。① 无新建表、零数据迁移风险 ② 复用 set_active 排他激活与 llm_router 读取 ③ 长期可维护（单表表达 provider→models）④ 迁移成本=1 个 JSONField migration ⑤ 连带影响=serializer + 前端类型同步。
- **B**: 新建 `LLMProvider` 表，`LLMConfig` 降为指针。① 架构上分两表更"规范" ② 但引入双表同步/激活一致性复杂度 ③ 长期多一份维护面 ④ 迁移需 seed + 双写 ⑤ 破坏现有调用点（需改 llm_service 两处）。
- **C**: 仅扩展 `LLMConfig` 为 JSON 大字段存全部 provider。① 最简单 ② 但丢结构化查询/排他校验 ③ JSON 内嵌难审计 ④ 无迁移 ⑤ serializer 复杂。

### 4. 拒绝双套 / 最小化

- 拒绝 B（双套并存）；拒绝 C（JSON 大字段违背结构化）。
- 采纳 A — 复用既有 `LLMConfig` 多行模式，最小且完整。

### 5. AI 自决边界

- 方向判定：A（架构判定，非"最小改动"借口）。自决执行无需用户批准。

## N167 七维度评分（修改清单）

| 维度 | 评分 | 说明 |
|------|:---:|------|
| 1 架构长远性 | 9 | 复用多行 LLMConfig，字段可扩展 |
| 2 全局归一化 | 8 | 单一 LLM 配置表承载 provider→models |
| 3 逻辑正确性 | 9 | test 端点 + available_models 往返有测试 |
| 4 可测试性 | 9 | 后端 8 项 + 前端 7 项测试 |
| 5 性能 | 9 | JSON 字段 + 无额外查询 |
| 6 易用性 | 8 | 前端模型 Tag + TextArea 管理 |
| 7 长期维护成本 | 8 | 无多表同步负担 |

总分 60 / 7 维 ≥ 19 且领先达标 → AI 自决执行。

## 关键决策

- `available_models`（JSON list）而非 spec 原 `models` —— 避免与 `django.db.models` 模块名冲突，语义等价于 spec 的 `models`。
- 复用 `LLMConfig` 而非新建 `LLMProvider`（N151 拒绝双套）。

## 用时

- start_ts: 2026-08-31 17:51 | end_ts: 2026-08-31 18:xx | duration: ~40 min（对照中修改基线 < 15 min 超基线，主要耗在探索/迁移/前端 4 步配套）
