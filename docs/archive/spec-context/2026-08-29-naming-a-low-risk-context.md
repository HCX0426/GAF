# Spec-Context: 命名归一化 A 批 — 低危删除与文档归一 (2026-08-29)

## 用户决策原文
- 评估稿 `docs/analysis/concept-naming-normalization.md` 锁定命名归一化方案（七维 C=31，自决执行），执行顺序 §7.1：A→B→C→G→D/F。
- "写吧，然后开始" — 用户授权按 §7.1 顺序开始执行；P1 = A 批（删死代码 `graph.py` + 文档归一）。

## N151 5 步法评估
1. **架构盘点**: `worker/src/engine/graph.py` 为 DAG 并行执行模块，全仓生产 import=0（仅 `agent/tests/test_pipeline_graph.py` 引用），属未接线死代码；`TaskDispatcher` 为 concurrency-design.md 画框幽灵符号（无对应类）；`GafDaemon`/`gaf_daemon`/`gaf_services` 三渲染；`TraceSpan` 模型早已删除（残骸仅存于迁移文件/注释/归档文档，无功能影响）。
2. **识别反模式**: 文档指向不存在/未接线的代码（`graph.py` DAG 执行、`TaskDispatcher` 框）属"幽灵符号/死路径"反模式，误导读者。
3. **备选方案**: A) 删除死代码 + 去幽灵框（本 spec） B) 保留 graph.py 并接线 DAG 执行（超出范围，拒绝） C) 仅文档标注不删代码（留债，拒绝）。
4. **拒绝反模式**: 拒绝 B（DAG 并行执行非当前需求，且生产零引用，接线=过度实现）、C（留死代码债）；选 A。
5. **AI 自决边界**: 纯删除/文档归一，零 API/迁移/前端类型冲击；`TraceSpan` 残骸因在迁移文件（不可改）与注释中，按"不碰 migration"原则不改动（N167 反思确认）。

## N167 七维度评分
- **架构长远性**: 删除未接线死代码，降低误导，略改善可维护性 — 3
- **全局归一化**: 消除 `graph.py`/`TaskDispatcher` 幽灵符号，文档指向真实实现 — 4
- **新旧兼容**: 纯删死代码，零运行时兼容影响（生产零 import）— 5
- **现有业务完善**: 无功能新增，仅清理 — 4
- **性能资源优化**: 无影响 — 3
- **安全合规加固**: 无涉 — 2
- **长期维护成本**: 死代码清零，文档准确，维护成本降 — 4
- **总分**: 25（≥19 且领先次优 ≥5 → AI 自决）

## 关键实施决策
- **删 `worker/src/engine/graph.py` + `agent/tests/test_pipeline_graph.py`**（D1/OQ-1）：生产零引用，pytest agent/tests 626 passed（pipeline/engine 子集）+ 全量 collect 2048 无 import 错误。
- **concurrency-design.md:70** `TaskDispatcher` 框 → `dispatch_task`（`AgentSelector` 选 Worker），标注真实入口。
- **GafDaemon 三渲染**：文档已区分 `GafDaemon`(权威名)/`gaf_daemon.py`(实现)/`gaf_services.ps1`(Windows 兼容层)，无需改动即一致。
- **图执行文档归一**：overview §十 树移除 `graph.py` 行；optimal-solution #11 改指 `parser.py`(PipelineGraph) 并注 DAG 并行未接线；dispatch-flow #609 注 `ParallelExecutor` 原在 `worker/src/engine/graph.py`（OQ-1 已删）。
- **TraceSpan**：复核仅存于迁移文件/注释/归档文档，无功能影响，按"不碰 migration"原则不改动（已记入 spec P4 备注）。
- **环境坑**：PowerShell `git commit -m` 不填充 `COMMIT_EDITMSG`，`[skip-doc-sync]` 令牌读不到 → 用 `GAF_SKIP_DOC_SYNC=1` 环境变量跳过 doc-code-sync 硬阻断（R4 为删除死代码，引用均为描述删除本身/AI 模块 `graph.py`，属有意保留）。

## 已知限制（spec 记录，非本次实现）
- 无（纯删除/文档归一，零功能回归）。

## N173 用时字段
- start_ts: 2026-08-29T21:30:00+08:00
- end_ts: 2026-08-29T22:10:00+08:00
- duration_min: ~40
- within_baseline: false（大修改基线 < 60 min，但本 spec 实际为低危删除，diff >500 行仅因删 802 行测试文件，非真实工作量）
- root_cause_if_over: 删除 `test_pipeline_graph.py`（802 行）使 diff 机械超 500 行触发 B2 大修改判定；实际改动为零风险死代码清理 + 4 处文档归一，已 pytest 验证无回归。
