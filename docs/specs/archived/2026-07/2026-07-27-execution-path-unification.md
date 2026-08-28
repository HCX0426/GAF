---
spec_id: spec-2026-07-27-execution-path-unification
title: 执行路径归一化 — chain 并入 pipeline 引擎
status: completed
created: 2026-07-27
last_updated: 2026-07-27
completed: 2026-07-27
owner: AI
priority: P1
related_tds: []
related_lessons:
  - N190-n105-loop-and-powershell-heredoc-l0-gap
related_specs:
  - spec-2026-07-25-logging-pipeline-hardening
  - docs/architecture/agent/chain-mode-structured-logging.md（被本 spec 取代，标记 deprecated）
scope:
  - agent/src/core/orchestrator.py
  - agent/src/core/result.py
  - agent/src/engine/node.py
  - agent/src/engine/parser.py
  - agent/src/engine/engine.py
  - agent/src/client/handler.py
  - backend/tasks/models.py
  - backend/protocol/consumers.py
  - backend/pipeline/tasks.py
  - backend/tasks/serializers.py
  - backend/tasks/views.py
estimated_loc: 1200
---

# 执行路径归一化 — chain 并入 pipeline 引擎

> **背景**: GAF 当前有两条执行路径（chain / pipeline），共享全部资源但执行能力不对等。
> 详见 [docs/architecture/agent/chain-mode-structured-logging.md §2](../../architecture/agent/chain-mode-structured-logging.md) 的多维度分析。
> 本 spec 的目标是通过"pipeline 吸收 chain 优点 + chain schema 废弃"实现执行引擎归一化。

---

## 1. 现状与问题

### 1.1 两条路径的资源与能力对比

| 维度 | chain 路径 | pipeline 路径 |
|---|---|---|
| **入口** | `handler.handle_task_assign` → `orchestrator.execute_task` | `handler.handle_pipeline_execute` → `orchestrator.execute_pipeline` |
| **执行器** | `TaskOrchestrator._execute_chain` / `_execute_step` | `PipelineEngine.execute()` |
| **schema** | `{"steps": [{"action", "params", "pre_verify", "post_verify", "retry", "fallback", "continue_on_error"}]}` | `{"nodes": [{"id", "type", "config", "next"}], "edges": [...]}` |
| **控制流** | 仅顺序执行 | branch / goto / loop DAG |
| **节点类型** | 6 种原子动作 | 15+ 种（含 NN/ROI/multi_touch） |
| **状态隔离** | ❌ 共享实例属性，`_task_exec_lock` 全局串行 | ✅ per-call `PipelineContext`，真并行 |
| **超时防护** | ❌ 无 | ✅ `ThreadPoolExecutor` + `MAX_STEP_TIMEOUT=300s` |
| **死循环防护** | ❌ 无 | ✅ `max_iterations=10000` |
| **节点内控制流** | ✅ retry/fallback/pre_verify/post_verify/continue_on_error | ❌ 无 |
| **依赖注入** | ❌ 无 | ✅ verifier/wait_freezes/recovery/llm |

### 1.2 核心问题

1. **执行能力割裂**：chain 缺超时/并行/死循环防护；pipeline 缺节点内声明式控制流
2. **代码重复**：`_execute_step` / `_run_action` / `_handle_retry` / `_handle_fallback` 与 PipelineEngine 节点执行逻辑重复
3. **维护成本**：新增能力（如 StructuredLogger 接入）需在两处实现
4. **资源浪费**：chain 的 `_task_exec_lock` 全局串行抵消了 DeviceManager 多设备并发能力

### 1.3 用户决策约束

- **不保留老任务**：现有 chain 任务一次性迁移到 pipeline schema
- **不写编译器**：chain schema 直接废弃，不做 chain→pipeline 自动转换
- **任务执行不存 DB**：仅 Task（任务定义）+ TaskExecution（执行记录）持久化，编译产物不存
- **跳过 BD2 端到端回归测试**：老任务迁移后直接验证，不做双路径等价性测试

---

## 2. 设计目标

### 2.1 核心目标

- **G1 单一执行引擎**：`PipelineEngine` 成为唯一执行器，`_execute_chain` / `_execute_step` / `_run_action` / `_handle_retry` / `_handle_fallback` 全部删除
- **G2 pipeline 吸收 chain 优点**：PipelineNode 基类支持 `retry` / `fallback` / `pre_verify` / `post_verify` / `continue_on_error` 字段
- **G3 线性模式**：pipeline 支持无 edges 的线性执行（按 nodes 列表顺序）
- **G4 schema 归一**：Task.execution_mode 废弃 CHAIN，task_definition 统一为 pipeline JSON
- **G5 入口归一**：handler 合并 `handle_task_assign` 与 `handle_pipeline_execute`，统一走 `orchestrator.execute_pipeline`

### 2.2 非目标

- 不改 PipelineEngine 的 DAG 遍历算法
- 不改 `PipelineParser` 的核心解析逻辑（仅扩展字段）
- 不改 TaskExecution 表结构
- 不改前端任务编辑器（前端已支持 pipeline JSON 编辑）

---

## 3. 实施阶段

### 阶段 2：PipelineNode 字段扩展（吸收 chain 优点）

**目标**：让 pipeline 节点支持 chain step 的节点内控制流字段。

#### 3.2.1 PipelineNode 基类扩展

[agent/src/engine/node.py](../../../agent/src/engine/node.py) `PipelineNode` dataclass 新增字段：

```python
@dataclass
class PipelineNode:
    id: str
    name: str = ""
    node_type: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    next_node_id: str | None = None
    comment: str = ""
    rationale: str = ""
    # ↓ 新增（吸收 chain step 字段）
    pre_verify: dict[str, Any] | None = None
    post_verify: dict[str, Any] | None = None
    retry: dict[str, Any] | None = None
    fallback: dict[str, Any] | None = None
    continue_on_error: bool = False
```

#### 3.2.2 PipelineNode.from_dict / to_dict 同步

`from_dict` 读取新字段（缺省 None / False，向后兼容）；`to_dict` 序列化新字段。

#### 3.2.3 PipelineEngine 节点执行逻辑扩展

[agent/src/engine/engine.py](../../../agent/src/engine/engine.py) `_execute_node_step` 方法在节点 `execute()` 调用前后插入验证 / 重试 / 回退逻辑：

```python
def _execute_node_step(self, node, context, iteration):
    # 1. pre_verify（新增）
    if node.pre_verify:
        verify_result = self._verifier.verify(node.pre_verify) if self._verifier else fail_result(...)
        if verify_result.failed:
            return fail_result(error_msg=f"前置验证失败: {verify_result.error_msg}")

    # 2. 节点 execute（保留现有逻辑，含 ThreadPoolExecutor 超时）
    result = self._run_node_with_timeout(node, context)

    # 3. retry（新增，复用 chain 的 _handle_retry 算法）
    if result.failed and node.retry:
        result = self._handle_node_retry(node, result)

    # 4. fallback（新增，复用 chain 的 _handle_fallback 算法）
    if result.failed and node.fallback:
        result = self._handle_node_fallback(node)

    # 5. post_verify（新增，仅成功时执行）
    if result.success and node.post_verify:
        verify_result = self._verifier.verify(node.post_verify)
        if verify_result.failed:
            return fail_result(error_msg=f"后置验证失败: {verify_result.error_msg}")

    # 6. continue_on_error（新增，控制图遍历行为）
    # 若节点失败且 continue_on_error=True，engine 不终止 pipeline，继续 next_node
    # 默认 False：节点失败即终止（保留现有行为）

    return result
```

#### 3.2.4 retry / fallback 算法迁移

从 [orchestrator.py](../../../agent/src/core/orchestrator.py) `_handle_retry` / `_handle_fallback` 迁移到 `PipelineEngine`，逻辑保持一致：
- `retry`: max_retries / base_delay / backoff_factor（指数退避）
- `fallback`: 调用 fallback.action + fallback.params（fallback 在 pipeline 里是 inline dict，不引用其他节点）

#### 3.2.5 continue_on_error 在图遍历中的处理

[engine.py](../../../agent/src/engine/engine.py) 主循环 `_resolve_next_node` 后：
- 节点失败且 `continue_on_error=True` → 不 break，继续下一个节点
- 节点失败且 `continue_on_error=False`（默认）→ break pipeline（保留现有行为）

#### 3.2.6 StructuredLogger 事件扩展

`log_node_event` 新增事件类型（与 chain 路径对称）：
- `node.execute.pre_verify_failed`
- `node.execute.post_verify_failed`

（`node.execute.complete` 已存在，retry 事件并入 complete 的 `retry_count` 字段，不单独发事件）

#### 3.2.7 单元测试

- `test_pipeline_node_fields.py`：PipelineNode 新字段 from_dict / to_dict 往返
- `test_engine_node_control_flow.py`：pre_verify 失败 / retry 触发 / fallback 触发 / post_verify 失败 / continue_on_error 跳过失败节点

**验收**：所有现有 pipeline 测试通过 + 新增控制流测试通过。

---

### 阶段 3：pipeline 线性模式（Parser 扩展）

**目标**：pipeline JSON 无 edges 字段时，按 nodes 列表顺序自动生成 next 链。

#### 3.3.1 现状

[parser.py:152-161](../../../agent/src/engine/parser.py) 已有部分支持：无 edges 时从 `node.next_node_id` 推断边。但要求每个 node 显式声明 `next_node_id`，不友好。

#### 3.3.2 改进

`PipelineGraph.from_dict` 在无 edges 且无 `next_node_id` 时，按 `nodes` 列表顺序自动链接：

```python
# 在 from_dict 末尾，graph.edges 仍为空时
if not graph.edges and len(graph.nodes) > 1:
    node_ids = list(graph.nodes.keys())
    for i in range(len(node_ids) - 1):
        graph.edges.setdefault(node_ids[i], []).append(
            PipelineEdge(from_node=node_ids[i], to_node=node_ids[i+1])
        )
    # entry_node 默认第一个
    if not graph.entry_node:
        graph.entry_node = node_ids[0]
```

#### 3.3.3 用户侧效果

```json
// 线性 pipeline（无 edges）
{
  "nodes": [
    {"id": "click_login", "type": "click", "config": {"x": 100, "y": 200}, "post_verify": {...}},
    {"id": "wait_load", "type": "wait", "config": {"seconds": 2}},
    {"id": "click_enter", "type": "click", "config": {"x": 300, "y": 400}}
  ]
  // 无 edges → 自动按顺序链接
}
```

#### 3.3.4 单元测试

- `test_parser_linear_mode.py`：无 edges 时自动链接 / 单节点 / entry_node 默认 / 与显式 next_node_id 混用

**验收**：线性 pipeline JSON 能被 PipelineEngine 正确执行。

---

### 阶段 4：handler / orchestrator 入口归一

**目标**：合并 `handle_task_assign` 与 `handle_pipeline_execute`，所有任务走 `execute_pipeline`。

#### 3.4.1 handler 合并

[agent/src/client/handler.py](../../../agent/src/client/handler.py)：
- `handle_task_assign` 内部直接调用 `handle_pipeline_execute` 的核心逻辑（或直接 alias）
- 保留两个 WS 消息类型入口（`task.assign` / `task.dispatch` / `pipeline.execute`）以兼容 backend，但内部统一走 `orchestrator.execute_pipeline`
- 删除 `execution_mode` 分支判断

#### 3.4.2 orchestrator.execute_task 废弃

[orchestrator.py](../../../agent/src/core/orchestrator.py)：
- `execute_task` 标记 `@deprecated`，内部委托 `execute_pipeline`（task_definition 直接当 pipeline_json 传）
- 删除 `_execute_chain` / `_execute_task_inner` / `_execute_step` / `_run_action` / `_handle_retry` / `_handle_fallback` / `_log_chain_step_event` / `_close_structured_logger`
- 保留 `_run_verify`（PipelineEngine 复用）
- 保留 `_verifier` / `_structured_logger` 字段（PipelineEngine 已有自己的 logger，orchestrator 不再需要）

#### 3.4.3 backend 协议层

[backend/protocol/consumers.py](../../../backend/protocol/consumers.py)：
- `TASK_DISPATCH` payload 不再发送 `execution_mode` 字段（或发送但 agent 忽略）
- `task_definition` 字段统一为 pipeline JSON

[backend/pipeline/tasks.py](../../../backend/pipeline/tasks.py)：
- `dispatch_task` 不再读 `task.execution_mode`，统一按 pipeline 发送

#### 3.4.4 单元测试

- `test_handler_unified.py`：`task.assign` / `pipeline.execute` 两个入口都能正确触发 `execute_pipeline`
- `test_orchestrator_deprecated.py`：`execute_task` 标记 deprecated 后仍能工作（委托 execute_pipeline）

**验收**：BD2 登录任务通过 `task.assign` 入口走 `execute_pipeline` 执行成功。

---

### 阶段 5：Task 模型归一

**目标**：backend Task 表废弃 CHAIN execution_mode，task_definition 统一为 pipeline JSON。

#### 3.5.1 Task.ExecutionMode 简化

[backend/tasks/models.py](../../../backend/tasks/models.py)：
- `ExecutionMode` 删除 `CHAIN`，仅保留 `PIPELINE`（或整个 enum 废弃，execution_mode 字段删除）
- 默认值改为 `PIPELINE`

```python
class Task(models.Model):
    class ExecutionMode(models.TextChoices):
        PIPELINE = 'pipeline', 'Pipeline'
        STATE_MACHINE = 'state_machine', 'State Machine'
        # CHAIN 已废弃
```

#### 3.5.2 数据迁移

写一次性 Django migration / data migration：
- 把所有 `execution_mode='chain'` 的 Task 改为 `execution_mode='pipeline'`
- 把所有 `task_definition` 是 chain schema 的 Task 转成 pipeline schema

转换规则（一次性，迁移后删除）：
```python
def chain_to_pipeline(task_definition: dict) -> dict:
    steps = task_definition.get("steps", [])
    nodes = []
    for step in steps:
        node = {
            "id": step.get("name") or f"step_{i}",
            "type": step.get("action", ""),
            "config": step.get("params", {}),
            "comment": step.get("comment", ""),
            "rationale": step.get("rationale", ""),
        }
        if step.get("pre_verify"): node["pre_verify"] = step["pre_verify"]
        if step.get("post_verify"): node["post_verify"] = step["post_verify"]
        if step.get("retry"): node["retry"] = step["retry"]
        if step.get("fallback"): node["fallback"] = step["fallback"]
        if step.get("continue_on_error"): node["continue_on_error"] = True
        nodes.append(node)
    return {"nodes": nodes}  # 无 edges → 线性模式
```

#### 3.5.3 单元测试

- `test_migration_chain_to_pipeline.py`：迁移函数对各种 chain step 配置的转换正确性

**验收**：现有 chain 任务全部迁移为 pipeline schema，DB 中无 `execution_mode='chain'` 记录。

---

### 阶段 6：清理与文档

**目标**：删除死代码，更新文档。

#### 3.6.1 删除代码

- [orchestrator.py](../../../agent/src/core/orchestrator.py)：删除 `_execute_chain` / `_execute_task_inner` / `_execute_step` / `_run_action` / `_handle_retry` / `_handle_fallback` / `_log_chain_step_event` / `_close_structured_logger` / `_structured_logger` / `_execution_id` / `_last_structured_log_path` 字段
- [handler.py](../../../agent/src/client/handler.py)：删除 `execution_mode` 处理分支
- [backend/tasks/models.py](../../../backend/tasks/models.py)：删除 `ExecutionMode.CHAIN`
- 删除 chain 相关测试：`test_orchestrator.py` 中 chain 执行相关用例

#### 3.6.2 文档更新

- [docs/architecture/agent/chain-mode-structured-logging.md](../../architecture/agent/chain-mode-structured-logging.md)：顶部标注 `DEPRECATED — 被 spec-2026-07-27-execution-path-unification 取代`
- [docs/business/tasks/execution-reality.md](../../business/tasks/execution-reality.md)：更新执行路径描述为单一 pipeline 引擎
- [docs/architecture/agent/](../../architecture/agent/)：新增 `execution-engine-unification.md` 描述归一化后的架构

#### 3.6.3 单元测试

- 全量回归：`agent/tests/` + `backend/tests/` 通过
- 验收：无 chain 相关死代码，文档描述与代码一致

---

## 4. 风险与对策

| 风险 | 等级 | 对策 |
|---|---|---|
| pipeline 节点字段扩展影响现有 pipeline 任务 | 低 | 新字段全部可选 + 默认 None/False，老 pipeline JSON 零影响 |
| chain→pipeline 数据迁移边界 case | 中 | 迁移函数覆盖所有 chain step 字段；迁移前备份 DB |
| BD2 登录任务迁移后执行失败 | 中 | 用户已接受不写回归测试；迁移后人工触发一次 BD2 登录任务验证 |
| `_task_exec_lock` 串行语义丢失影响 chain 任务 | 低 | chain 任务迁移到 pipeline 后获得真并行能力，是改进非退化 |
| StructuredLogger 在 chain 路径的接入代码（阶段 1 已完成）被废弃 | 低 | 接入逻辑迁移到 PipelineEngine 已有日志路径，不丢失能力 |

---

## 5. 验收标准（整体）

1. ✅ `TaskOrchestrator` 不再包含 `_execute_chain` / `_execute_step` 等方法
2. ✅ `PipelineNode` 支持 `pre_verify` / `post_verify` / `retry` / `fallback` / `continue_on_error` 字段
3. ✅ pipeline JSON 无 edges 时按 nodes 顺序执行
4. ✅ `Task.execution_mode` 无 CHAIN 选项
5. ✅ DB 中所有 Task 的 `task_definition` 为 pipeline schema
6. ✅ `handler.handle_task_assign` 与 `handle_pipeline_execute` 内部统一走 `execute_pipeline`
7. ✅ BD2 登录任务（迁移后）能通过 `task.assign` 入口执行成功，生成 JSONL 日志，`execution_snapshot.structured_log_path` 非空
8. ✅ 全量单元测试通过

---

## 6. 关联文档

- [docs/architecture/agent/chain-mode-structured-logging.md](../../architecture/agent/chain-mode-structured-logging.md) — chain 接入 StructuredLogger 的临时方案（被本 spec 取代）
- [docs/specs/active/2026-07-25-logging-pipeline-hardening.md](2026-07-25-logging-pipeline-hardening.md) — pipeline 模式 StructuredLogger 接入设计
- [docs/business/tasks/execution-reality.md](../../business/tasks/execution-reality.md) — 执行路径现状描述
