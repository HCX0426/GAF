---
summary: TD-390 — LLM 生成 Pipeline 运行时守门（静态校验 + 风险评分）
applies_to: ['backend']
applies_to_code_paths:
  - backend/gaf_ai/pipeline_guard.py
  - backend/gaf_ai/views.py
last_updated: 2026-08-23
---

# TD-390: LLM 生成 Pipeline 运行时守门

> 来源: 2026-08-22 AI 开发通病对照分析（原登记 TD-387，因与 fixed-tech-debt.md 已提交的 TD-387(L2 加载) 重号，2026-08-23 重编号为 TD-390）。
> 优先级: P2（原 P2）。
> 范围: 仅生成侧守门（静态校验 + 风险评分 + 高风险标记）。执行侧超时熔断/回退属 PipelineEngine 范畴，超出本 spec，登记 follow-up。

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit | 验收 evidence |
|------|------|----------|--------|---------------|
| P1 后端守卫模块 `pipeline_guard.validate_and_score` | ✅ 完成 | 2026-08-23 | - | 结构/循环/坐标/风险评分单测通过 |
| P2 接入 `generate_pipeline` + `generate_pipeline_stream` 响应 | ✅ 完成 | 2026-08-23 | - | 响应含 `validation` 字段 |
| P3 测试 + lint + 提交 | ✅ 完成 | 2026-08-23 | - | pytest 18 passed + ruff 通过 |

## 背景

`gaf_ai/views.py` 的 `generate_pipeline` 把 LLM 文本用 `json.loads` 解析后**仅检查 `'nodes'` 是否存在**即把 `graph_data` 返回给前端供执行。LLM 幻觉若产出：
- 坐标越界 / 负数坐标的操作节点（点错位置）
- 循环节点（无限执行卡死）
- 不可达孤立节点
- 高危 node_type（shell/adb/restart/install 等系统级副作用）

这些当前零校验，执行时直接暴露。TD-390 在"生成物落地前"加一层静态守门 + 风险评分，让前端对高风险生成物弹确认。

## 修复方案

### 后端 `backend/gaf_ai/pipeline_guard.py`（新增）
`validate_and_score(graph_data) -> dict`：
- **结构校验**: nodes 为列表且非空；每个节点有唯一 id + node_type；edges 的 source/target 引用存在的节点。
- **循环检测**: 基于邻接表拓扑可达性判环（循环 = 可能无限执行，error）。
- **可达性**: 从首节点 DFS，标记不可达孤立节点（warning）。
- **坐标边界**: 节点 params 含 x/y/left/top/width/height 且超 `[0, 4096]` → warning。
- **风险评分**: 按 node_type 分级累加 —— HIGH(系统副作用, +3) / MEDIUM(UI 交互含坐标, +1) / SAFE(观测分析, 0)；未知类型 warning（按安全但建议人工确认）。
- **返回**: `{valid, errors, warnings, risk_score, risk_level(low/medium/high), high_risk_nodes, cycle_detected, unreachable_nodes}`。

### 接入 `views.py`
- `generate_pipeline`: 解析出 `graph_data` 后调用 `validate_and_score`，响应增加 `validation` 字段。
- `generate_pipeline_stream`: `event_stream` 的 `done` 事件附带 `validation`。

> 新增 `validation` 字段向后兼容（前端可忽略）；不改动前端类型，不触碰 API 契约文件，不触发 B2。

## 验证标准
- `pytest backend/gaf_ai/tests/test_pipeline_guard.py` 覆盖：合法管线 / 循环 / 越界坐标 / 高危节点 / 孤立节点 / 非标准结构。
- `test_views.py` 断言 `generate_pipeline` 响应含 `validation` 且高风险管线 `risk_level=='high'`。
- `ruff` 通过；本 spec 不改动前端，无需 tsc。
