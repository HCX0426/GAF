---
spec: 2026-08-31-ai-tab-agent-learning-spec
phase: Phase 1
start_ts: 2026-08-31T12:15:00+08:00
end_ts: 2026-08-31T13:10:00+08:00
duration_min: 55
within_baseline: true
---

# 2026-08-31 AI 页签改造 — Phase 1 多服务商 LLM 配置（spec-context 承载体）

> B2 大修改承载体（TD-342 / N151 / N167 / N173）。
> spec: `docs/specs/active/2026-08-31-ai-tab-agent-learning-spec.md`；关联 TD-423。

## 1. 用户决策原文（对话片段）

- "API Key 管理这个页签应该移动到AI的页签，然后你评估下AI这个页签里的界面是不是有点乱，需要重新设计这个独立agent架构和UI？你不能找下目前开源的ide是怎么实现多服务商的api key的加载吗，先评估"
- "同步TD那里先？，要是我这个ai页签开发完，我能符合目前招聘要的技术条件吗，这块我也准备学习的，还是新开的spec先？"
- "开始吧，我会在最后完后开始学习"（批准执行 Phase 1，学习留待功能完成后）
- 用户意图：AI 页签 = 学习载体 + JD 对标，非纯功能迭代；多服务商配置对齐 VS Code BYOK / Continue.dev 实践

## 2. N151 5 步法评估过程

1. **文档审视**：读 `optimal-solution` / `features-overview` / `overview` + `llm-integration-design.md` §2.3/§8（4-level fallback chain preferred→backup→local→offline）。
2. **架构盘点**：`settings.LLMConfig` 为单行模型 → 只能配一个 provider，切换即覆盖 key；`llm_service._get_llm_config` 用 `objects.first()`；`AiConfigPage` 为单配置表单；AI 侧边栏 8 页平铺。
3. **识别反模式**：① 单行覆盖 → 无法多服务商并存；② `first()` 选中最新创建行，不一定是激活行；③ AI 侧边栏无信息架构分组。
4. **备选方案**：
   - **A**：新增 `LLMProvider` 模型（provider→models 两级，含迁移播种）— 架构更"标准"但引入新实体 + 迁移 + 双表共存
   - **B**：复用 `LLMConfig` 多行 + `is_active` 唯一激活（`set_active` action 做排他降级）— 改动最小，复用现有字段/端点/序列化
   - **C**：环境变量驱动多 provider — 无法支撑 Web UI 图形化管理，弃
   - **结论：采用 B**（LLMConfig 本就支持多行，`is_active` 字段已存在，只是缺"唯一激活"约束与 UI 编排）。
5. **风险与回退**：`set_active` 为增量 action，无破坏性迁移，可平滑回退；`_get_llm_config` 语义变化有 6 条后端测试锁定。

## 3. N167 七维度评分（方案 B）

| 维度 | 评分 | 说明 |
|------|:---:|------|
| 1 架构长远性 | 8 | 复用 LLMConfig 多行能力，不引入新模型/迁移 |
| 2 全局归一化 | 8 | 复用现有字段/端点/序列化/UI 范式，无并行概念 |
| 3 跨切面 | 7 | 涉及 settings/gaf_ai/frontend，改动集中可控 |
| 4 可逆性 | 8 | set_active 增量 action，无破坏性迁移 |
| 5 未来扩展 | 7 | Phase 2/3（LangGraph/MCP/RAG）可平滑演进 |
| 6 复杂度 | 8 | 后端 1 action + 1 查询语义 + 前端 1 页重构 |
| 7 长期维护 | 8 | 无重复逻辑，测试覆盖激活唯一性 |
| **总分** | **54** | ≥19 且领先，自决 |

## 4. 关键实施决策

- 不新建 `LLMProvider` 模型；复用 `LLMConfig` + `is_active` 排他激活（收敛 TD-423 范围）。
- `LLMConfigViewSet.set_active` action（POST `{id}/set-active/`）：先 `exclude(pk).update(is_active=False)` 降级其余行，再提升目标行——单查询保证唯一激活。
- `llm_service._get_llm_config` 改为 `filter(is_active=True).order_by('-updated_at').first()`，无激活行返回 `None`（配合既有 fallback）。
- `llm_router.py` 保持通用 4-level router 不变；构建 client 时使用激活 provider 的配置（由 `_get_llm_config` 供给）。
- 前端 `AiConfigPage` 重构为 Provider 卡片列表：卡片 = provider + base_url + 状态 Tag + 编辑/设为激活/删除（激活项禁删）+ 顶部"添加 Provider"弹窗；顶部 Alert 区支持对激活 provider 一键"测试连接"（latency + 响应预览）。
- API 前端层：`ai.ts` 补 `deleteLlmProviderConfig` / `setActiveLlmProvider`，list 接口解包 DRF 分页信封。
- AI 侧边栏 4 分组：对话(assistant/qa) / 分析(anomaly/log-analysis) / Skill(editor/market) / 配置运维(config/usage)；i18n 四语言补齐。
- 测试：后端 `test_llm_provider.py` 6 条（并存/排他激活/激活优先/无激活 None/key 加密往返/key 不回传）；前端 `AiConfigPage.test.tsx` 5 条 + `ai.test.ts` 30 条。

## 5. N173 用时字段

- start_ts: `2026-08-31T12:15:00+08:00`
- end_ts: `2026-08-31T13:10:00+08:00`
- duration_min: 55
- within_baseline: true（大修改基线 <60 min）
- root_cause_if_over: （不适用）
