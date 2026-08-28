# s42: L3-1 扫描 [A] 类修复 — pipeline 节点枚举三方契约 + 今日摘要 404

> 状态: ✅ 已归档 (commit -) | spec_id: 2026-08-19-s42-l3-scan-a-fixes
> 来源: L3-1 全量扫描（2026-08-19，触发条件①: 距上次 ≥ 2 spec）
> 创建: 2026-08-19 | 基线: N173 中修改 < 15min
> 归档: docs/specs/archived/2026-08/
> 实现产物: schema.py 46 种枚举 + test_pipeline_node_contract.py + DailySummaryCarousel.tsx 修复 + TD-366/367/368 登记

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit | 验收 evidence |
|------|------|---------|--------|--------------|
| P1 schema 枚举补全 + 契约测试 | ✅ | 2026-08-19 | - | 4 passed contract + 257 passed backend |
| P2 DailySummaryCarousel fetch 修复 | ✅ | 2026-08-19 | - | vite build ok, grep 无裸 fetch |
| P3 验证 + 归档 | ✅ | 2026-08-19 | - | ruff clean + evidence 三件套 |

## 背景

L3-1 扫描（9 维度，2 subagent）发现 2 个 [A] 类（P0/P1 且 < 500 行）：

1. **backend pipeline schema 节点类型枚举过期**（数据层⑦）：`backend/pipeline/schema.py` `ALL_NODE_TYPES` 仅 20 种（+4 legacy），缺 19 种前端编辑器（38 种）与 agent 注册表（42 种）均已支持的节点。含 `wheel`/`start_app`/`roi_resolver` 的 pipeline 经 API 保存会被 `jsonschema.validate` 拒绝（serializers.py:42）→ 前端能画、agent 能跑、后端存不了。
2. **今日摘要轮播永远空白**（界面层④）：`frontend/src/pages/Ops/Executions/analytics/DailySummaryCarousel.tsx:65` 硬编码 `fetch('/api/unattended/progress/')`——(a) 绕过 baseURL=/api/v2 的 axios client（N197 违反）；(b) 路径本身 404（真实路由 `/api/v2/scheduler/unattended/progress/`，vite proxy 无 rewrite）→ 被 `catch { setItems([]) }` 静默吞掉。

## 任务清单

### P1: schema 枚举补全 + 跨层契约测试

**事实基线**（本次扫描确认）：
- agent 注册名 42 种（`@register_node` 全量）: click, swipe, key_press, text_input, long_press, direct_hit, template_match, template_match_any, ocr, color_detect, feature_match, wait, branch, loop, random_delay, notify, device_control, monitor, sub_pipeline, goto, swipe_until, start_app, stop_app, and_match, or_match, custom_match, jump_back, wait_freezes, next, stop, anchor, multi_swipe, multi_scroll, multi_touch, wheel, neural_network, nn_classifier, nn_regressor, roi_resolver, sort_select, python_call, log_message
- 前端 `PipelineNodeType` 38 种 ⊆ agent 42（前端无 template_match_any/swipe_until/python_call/log_message）
- legacy 4 种（login_account/switch_account/switch_resource/captcha_detect）：**非死类型**——validators.py:112-115 字段映射 + estimator.py:25-28 耗时估算 + check_code_rules/check_schema_unification 白名单仍在消费 → **保留 + 标注 deprecated**（BD2-AUTO 兼容）

**任务**：
- [ ] 1. `backend/pipeline/schema.py` `ALL_NODE_TYPES` 补 19 种前端/agent 已有节点 + python_call/log_message（agent 注册但后端缺）→ 46 种；legacy 4 种保留并加注释标注 deprecated
- [ ] 2. 新增跨层契约测试 `scripts/tests/test_pipeline_node_contract.py`（文本扫描，不 import）：
  - `set(agent 注册名) ⊆ set(backend ALL_NODE_TYPES)`
  - `set(frontend PipelineNodeType) ⊆ set(backend)`
  - `set(backend) - set(agent) == legacy 4 种`
  - agent 注册名从 `agent/src/engine/nodes/*.py` 正则 `@register_node("...")` 提取（含多行形式）
  - 前端从 `frontend/src/types/models/pipeline.ts` `PipelineNodeType` union 提取
  - 后端从 `backend/pipeline/schema.py` `ALL_NODE_TYPES` 列表提取
- [ ] 3. 确认 `backend/pipeline/tests/` 无枚举内容断言（test_converter.py 仅注释引用）→ 无需改；跑 backend pipeline 测试回归

### P2: DailySummaryCarousel fetch 修复

- [ ] 4. `DailySummaryCarousel.tsx`：`fetch('/api/unattended/progress/', { headers: buildAuthHeaders() })` → `client.get('/scheduler/unattended/progress/')`（`import client from '@/api/client'`，interceptor 自动带 token，无需 buildAuthHeaders；移除该 import 若不再使用）
- [ ] 5. 顺带检查同文件是否还有其他裸 fetch（N197 归一化）

### P3: 验证 + 归档

- [ ] 6. 验证：scripts 新契约测试 + backend pipeline 测试 + ruff + `npx vite build`（TS 检查）
- [ ] 7. 写 evidence 三件套 + spec-context（B2 需评估）+ N202 若适用
- [ ] 8. 归档 spec → `docs/specs/archived/2026-08/`

## 已知限制

- 无（legacy 4 种保留为兼容，不删）

## Deviation Log

- （无）