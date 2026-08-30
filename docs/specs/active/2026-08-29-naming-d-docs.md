---
spec: 2026-08-29-naming-d-docs
title: 命名归一化 D 批：纯文档收口（overview/features/子文档修正 + 概念速查 + 三健康面 + 三层节点）
status: active
created: 2026-08-29
estimated_effort: 1 day
risk: low
depends_on: []
source: docs/analysis/concept-naming-normalization.md §4(D4/D7/D12/D14/D20-D24/X1)/§5(7,8,10,11,12)/§9(OQ-7,OQ-8)/§1
---

# 命名归一化 D 批：纯文档收口

## 1. 背景与动机 (Background)

D 批为**纯文档**修正（零代码/零 API/零迁移），收口评估稿 §4 的文档差异与 §9 的 OQ-7/OQ-8 澄清（评估稿 §7 D 批）。含 overview/features 概念纠偏、子文档内部矛盾修正、概念速查、三块健康面语义澄清、三层节点区分。

## 2. 核心问题 (Problem)

| 项 | 现状 | 目标 |
|----|------|------|
| `RotationRule` 标签 / 缺失 `by_last_executed` | overview/features 两文档各列 3 类型 | 术语 `GameAccountRotation`；补 4 选含 `by_last_executed`（D7） |
| `Tag` 双 app 暗示 | overview §9.1 tasks/resources 各列裸 `Tag` | 单一 `resources.Tag`（D12） |
| 子文档矛盾 | ScreenshotCache TTL 50/100(D21)；SQLite/Postgres(D22)；pre-commit 计数(D24)；debug-logging(D20) | 修正 |
| `get_unified_logical_rect` vs `publish_match_pos` | 记为"名不一致" | 文档说明异物（D23②） |
| 概念速查缺失 | 循环≠监控 等边界不清 | 新增速查（OQ-7） |
| 三健康面混淆 | Header "系统运行状态" 语义不明 | 明确三块 + Header 标签"系统综合状态"（OQ-8，纯文案） |
| 三层节点 | TaskChainNode/PipelineNode/Pipeline 过载 | 文档显式区分（可选 `PipelineNode`→`AgentNode` 标 NOT DONE） |

## 3. 目标 (Goals)

1. overview/features 概念纠偏（RotationRule/Tab/轮换策略 4 选）。
2. 子文档内部矛盾修正（D20–D24/X1）。
3. 新增"概念速查"澄清循环≠监控等边界（OQ-7）。
4. 明确三块健康面；Header UI 标签"系统运行状态"→"系统综合状态"（纯文案，零 API）。
5. 文档显式区分三层节点；`get_unified_logical_rect`/`publish_match_pos` 异物说明。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | overview/features 纠正（D4/D7/D12） | ✅ |
| P2 | 子文档矛盾修正（D20–D24/X1） | ⏳ |
| P3 | 概念速查 + 三健康面（OQ-7/OQ-8） | ✅ |
| P4 | 三层节点 + D23② 说明 | ✅ |
| P5 | Worker / Agent(AI) 术语区分章（OQ-10） | ✅ |

#### Task P1.1: overview/features

- `RotationRule`→`GameAccountRotation`；补 4 选 `sequential`/`random`/`by_stamina`/`by_last_executed`（D7）。
- `Tag`：撤销 tasks/resources 双 Tag 暗示，标注单一 `resources.Tag`（D12）。
- 补 9 个 features-only 概念到 overview §9（D13）；`AnomalyPattern` 注前端-only（决策 11）。

#### Task P2.1: 子文档

- `concurrency-design.md`(D21 ScreenshotCache TTL 统一)、`deployment-design.md`(D22 SQLite/Postgres)、`pre-commit-stages.md`(D24 计数)、`debug-logging-structure.md`(D20 矛盾)、`coordinate-transform-pipeline.md`(D23②)。

#### Task P3.1: 概念速查 + 健康面

- 新增"概念速查"：循环任务≠监控任务（F1/OQ-7）；监控=monitors+MonitorManager+pipeline 监控节点。
- 明确三块健康面：`system_status_view`(overall) / `InfraHealthPanel`(`/accounts/init/health/`) / `ServicesPage`；前端 `HeaderStatusIndicator.tsx` 标签"系统运行状态"→"系统综合状态"（OQ-8，纯 UI 文案）。

#### Task P4.1: 三层节点

- 文档显式区分：backend `Pipeline`(JSON) / backend `TaskChainNode`(持久化链节点) / agent `PipelineNode`(运行时节点)；可选 `PipelineNode`→`AgentNode` 改名**标 NOT DONE**（不同层非同物，见 §1）。
- `get_unified_logical_rect`(坐标转换方法) vs `step=publish_match_pos`(trace step 值) 异物说明（D23②）。

#### Task P5.1: Worker / Agent(AI) 术语区分（OQ-10）

- overview/features 显式区分三概念：**Device**(被控 PC/模拟器) / **Worker**(自动化执行节点/进程，原 "Agent") / **Agent**(未来 AI 智能体，`backend/gaf_ai` LangGraph agent，会话 `AgentSession` 保留)。
- 全文将"执行节点/进程"语义的 "Agent" 统一改 "Worker"（具体符号改名见批 G）；"AI 智能体"语义的 "Agent" 保留。

## 5. 测试与验收

- 文档构建/链接检查通过；grep `RotationRule`/`TaskDispatcher` 文档残留清零。
- 前端：手动确认 Header 显示"系统综合状态"（仅文案）。
- 评估稿标记 D 批完成。

## 6. 回滚

- 纯文档，git revert 即可。
