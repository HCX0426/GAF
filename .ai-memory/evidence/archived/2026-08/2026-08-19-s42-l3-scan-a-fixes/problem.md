# s42 problem — L3-1 扫描发现的 2 个 [A] 类问题

## 触发

L3-1 全量扫描（2026-08-19，距上次 ≥ 2 spec 触发条件①）— 2 subagent 并行扫 9 维度。

## 问题 1: pipeline 节点枚举三方契约断裂（数据层⑦）

- backend/pipeline/schema.py ALL_NODE_TYPES 仅 24 种（20 现役 + 4 legacy）
- 前端编辑器 38 种 + agent @register_node 42 种均已支持
- 缺 19 种：neural_network / and_match / or_match / custom_match / multi_swipe / multi_scroll / multi_touch / wheel / jump_back / wait_freezes / next / stop / anchor / sort_select / start_app / stop_app / nn_classifier / nn_regressor / roi_resolver
- 缺 agent 独有 2 种：python_call / log_message
- 后果：前端能画、agent 能跑的 pipeline（含 wheel/start_app/roi_resolver）经 API 保存被 jsonschema enum 校验拒绝（serializers.py:42）

## 问题 2: 今日摘要轮播永远空白（界面层④）

- DailySummaryCarousel.tsx:65 `fetch('/api/unattended/progress/')` 双重违规：
  (a) 绕过 baseURL=/api/v2 的 axios client（N197 违反）
  (b) 路径 404 — 真实路由 /api/v2/scheduler/unattended/progress/，vite proxy 无 rewrite
- catch { setItems([]) } 静默吞掉 → "今日摘要" Tab 永远空

## 影响范围

- backend/pipeline/schema.py + scripts/tests/test_pipeline_node_contract.py（新）+ frontend DailySummaryCarousel.tsx