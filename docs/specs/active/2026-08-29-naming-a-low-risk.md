---
spec: 2026-08-29-naming-a-low-risk
title: 命名归一化 A 批：低危删除与文档归一（graph.py / TaskDispatcher / GafDaemon / TraceSpan 残骸）
status: active
created: 2026-08-29
estimated_effort: 0.5 day
risk: low
depends_on: []
source: docs/analysis/concept-naming-normalization.md §1/§5(9,10,13,OQ-1)/§7
---

# 命名归一化 A 批：低危删除与文档归一

## 1. 背景与动机 (Background)

A 批为**零 API 契约 / 零 DB 迁移 / 零前端类型**冲击的改动（评估稿 §7 A 批）：删除死代码 `graph.py`、移除文档幽灵符号 `TaskDispatcher`、守护进程命名归一 `GafDaemon`、清理已删模型 `TraceSpan` 的代码残骸。可安全先行，为后续高危批降低干扰。

## 2. 核心问题 (Problem)

| 项 | 现状 | 目标 | 依据 |
|----|------|------|------|
| `agent/src/engine/graph.py` | DAG 执行+工具，仅测试 import，**生产零引用** | 删除文件 + 测试 | D1/OQ-1 |
| `TaskDispatcher` 文档框 | concurrency-design.md:70 画框，无对应类 | 去框 → `dispatch_task` | D18/X1 |
| `GafDaemon`/`gaf_daemon`/`gaf_services` | 三渲染 | `GafDaemon` 权威名；`.py` 实现；`.ps1` 兼容层 | D19 |
| `TraceSpan` 代码残骸 | 模型已删，43 处残留引用（注释/import） | 清理残骸 | D14 |

## 3. 目标 (Goals)

1. 删除 `graph.py` 及其测试，文档改指 `PipelineGraph`(`parser.py`)。
2. concurrency-design.md 移除 `TaskDispatcher` 框，标注真实入口 `dispatch_task` + `AgentSelector`。
3. 文档统一守护进程命名（`GafDaemon` 权威）。
4. 清理 `TraceSpan` 死引用。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 删 graph.py + 测试 | ⏳ |
| P2 | concurrency-design 去 TaskDispatcher 框 | ⏳ |
| P3 | GafDaemon 文档归一 | ⏳ |
| P4 | TraceSpan 残骸清理 | ⏳ |

#### Task P1.1: 删 graph.py

- `agent/src/engine/graph.py` + 对应测试（`agent/tests/...graph*`）删除。
- grep 确认无生产 import（评估稿：外部生产 import=0）；若有测试 import，一并迁移/删除。
- `docs/architecture/` 中"DAG 执行"表述改指 `PipelineGraph`(`parser.py`)。

#### Task P2.1: 去 TaskDispatcher 框

- `docs/architecture/concurrency-design.md` 移除 "TaskDispatcher" 画框；标注实际为 `dispatch_task`(模块函数) + `AgentSelector`。

#### Task P3.1: GafDaemon 文档归一

- overview/features 统一 `GafDaemon` 为权威名；`gaf_daemon.py` 为实现；`gaf_services.ps1` 标 "Windows 启停兼容层"。

#### Task P4.1: TraceSpan 残骸

- 全仓 grep `TraceSpan`（43 处，评估稿 §7）清理注释/死 import，无功能影响。

## 5. 测试与验收

- `conda run -n gaf python -m pytest agent/tests -q` 通过（graph 相关已移）。
- 文档链接/构建检查通过；grep `TaskDispatcher`/`TraceSpan` 残留按需清零（TraceSpan 代码残骸清零）。
- 评估稿标记 A 批完成。

## 6. 回滚

- 纯删除/文档级，git revert 本 spec commit 即可。
