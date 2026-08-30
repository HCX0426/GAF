---
summary: chain 模式接入 StructuredLogger 的架构决策与多维度分析（已废弃）
status: deprecated
superseded_by: spec-2026-07-27-execution-path-unification
applies_to: ['agent', 'architecture']
key_decisions:
  - 方案 C：在 TaskOrchestrator 复用 StructuredLogger（与 PipelineEngine 对称接入）
  - chain step.name→node_id / step.action→node_type 字段映射
  - AutoResult 新增 structured_log_path 字段（向后兼容默认空串）
last_updated: 2026-07-27
---

# chain 模式接入 StructuredLogger 架构决策

> **⚠️ DEPRECATED (2026-07-27)**: 本文档描述的"chain 接入 StructuredLogger"是临时方案，
> 已被 [spec-2026-07-27-execution-path-unification](../../specs/archived/2026-07/2026-07-27-execution-path-unification.md)
> 取代。归一化后 chain 路径整体废弃，所有任务走 PipelineEngine，StructuredLogger 接入
> 复用 PipelineEngine 已有的日志路径。本文档保留作为决策历史参考。
>
> 版本：1.0 | 日期：2026-07-27 | 关联 spec：`spec-2026-07-25-logging-pipeline-hardening`（历史 spec 文档未留存）

## 1. 背景与盲区

GAF 任务执行有两条主路径：

| 模式 | 入口 | 执行器 | 结构化日志 |
|---|---|---|---|
| **pipeline** | `orchestrator.execute_pipeline` | `PipelineEngine.execute()` | ✅ 已接入（spec 阶段 3.1） |
| **chain** | `orchestrator.execute_task` → `_execute_chain` | `TaskOrchestrator._execute_step` | ❌ 缺失 |

### 1.1 数据流断点

```
backend → WS task.execute → handler.execute_task
  → orchestrator.execute_task
  → _execute_chain → _execute_step → _run_action
  → AutoResult（无 structured_log_path 字段）
  → handler 用 getattr(result, "structured_log_path", "") 读到空串
  → task.result WS 消息 structured_log_path=""
  → backend consumer 提取到空串 → snapshot 不写入
  → AI 工具读不到 JSONL，无法诊断 chain 模式任务
```

### 1.2 影响范围

- **BD2 登录任务**（chain 模式为主流任务形式）无结构化日志
- AI 诊断工具对 chain 任务"失明"
- `execution_snapshot.structured_log_path` 字段对 chain 任务永远为空

---

## 2. 多维度架构分析

> 评估维度权重：**架构维度（最大）> 数据流一致性 > 可维护性 > 可扩展性 > 测试维度**

### 2.1 候选方案

| 方案 | 接入位置 | 核心思路 |
|---|---|---|
| **A** | orchestrator 把 chain steps 转 pipeline_json，委托 PipelineEngine | 单一执行引擎，最大复用 |
| **B** | 抽取 `ExecutionLogger` 接口层，chain/pipeline 各自实现 | 抽象隔离，理想对称 |
| **C** | TaskOrchestrator 直接复用 `StructuredLogger`（与 PipelineEngine 对称接入） | 工具类复用，无新抽象 |

### 2.2 维度评估矩阵

| 维度 | 方案 A | 方案 B | 方案 C |
|---|---|---|---|
| **架构** | ❌ chain step 三段式（pre_verify/action/post_verify）与 pipeline 节点图语义不同，强行转换引入 schema 复杂度，违反"语义边界"原则 | ⚠️ `StructuredLogger` 本身已是抽象层，再包一层 `ExecutionLogger` 属于过度抽象，违反 YAGNI | ✅ `StructuredLogger` 是按 execution_id 注册的模块级单例（`_INSTANCES`），接口与 PipelineEngine 解耦，TaskOrchestrator 作为第二个用户对称接入，不是"复制" |
| **数据流一致性** | ❌ 转换层可能丢失 chain 特有字段（continue_on_error / fallback / retry_config） | ✅ 两端走同一接口 | ✅ 与 pipeline 路径完全对称：handler `getattr(result, "structured_log_path", "")` → backend `_handle_task_result` 提取 → `update_task_execution_result` 写 snapshot |
| **可维护性** | ❌ 转换层是新的故障点，需独立测试 | ⚠️ 新接口需要双份维护（chain impl + pipeline impl） | ✅ 接入方式与 PipelineEngine 完全对称，未来维护者一眼看懂；不引入新的执行路径 |
| **可扩展性** | ⚠️ chain 新增字段需同步转换层 | ✅ 抽象层允许两路径独立演化 | ✅ `log_node_event` 已支持 extra 字段，chain 特有信息（pre_verify 失败原因、retry 历次错误）可通过 extra 透传 |
| **测试** | ❌ 转换层需要双倍测试用例（chain schema + pipeline schema） | ⚠️ mock 一层接口，测试成本中等 | ✅ 复用 PipelineEngine 的测试范式（mock StructuredLogger，断言 log_node_event 调用参数） |
| **实施成本** | 高（~300 LOC 转换 + 测试） | 中（~150 LOC 抽象 + 双实现） | 低（~80 LOC 接入 + 测试） |

### 2.3 架构维度论证（权重最大）

**架构层面的核心判断**：

1. **`StructuredLogger` 的设计本质是工具类，不是 PipelineEngine 私有**：
   - 模块级 `_INSTANCES` 注册表（structured_logger.py:60-61）支持多调用方共享
   - `get_logger(execution_id, debug_dir)` 接口不依赖 PipelineEngine 任何类型
   - `log_node_event` 的 16 个参数都是通用语义（event/node_id/node_type/step_index/success/...），不是 pipeline 专属

2. **chain step 与 pipeline node 的字段天然映射**：
   - `step.name` → `node_id`
   - `step.action` → `node_type`
   - `step_index`（循环计数器）→ `step_index`
   - `result.success` → `success`
   - `result.elapsed_time` → `elapsed_ms`
   - `step.params` → `node_config`（供 `extract_result_fields` 提取点击坐标等）
   - 不需要新抽象层来"翻译"字段

3. **方案 A 的根本错误**：把"动作序列"和"状态图"两种执行语义强行合并。chain 模式的 `pre_verify/action/post_verify` 三段式是线性执行的，pipeline 的 node 之间是图遍历的。转换层会引入：
   - pre_verify 如何映射成 node？（虚节点？跳过？）
   - retry_config / fallback 在 pipeline 里没有对应概念
   - 这些语义差异会让转换层成为永久的"特殊情况处理"代码

4. **方案 B 的根本错误**：误把"接口对称"等同于"架构清洁"。`StructuredLogger` 已经是抽象层，再抽一层 `ExecutionLogger` 等于：
   - 新接口只有两个实现（chain impl + pipeline impl）
   - 新接口的方法签名几乎与 `StructuredLogger` 一一对应
   - 这不是抽象，是包装

### 2.4 决策

**选定方案 C**：在 `TaskOrchestrator` 复用 `StructuredLogger`，与 `PipelineEngine` 对称接入。

---

## 3. 实施要点

### 3.1 字段映射规范

| chain step 字段 | log_node_event 参数 | 备注 |
|---|---|---|
| `step.get("name", f"step_{idx}")` | `node_id` | 缺省用 `step_{idx}` |
| `step.get("action", "")` | `node_type` | click/swipe/key_press/text_input/screenshot/wait |
| `idx`（循环计数器） | `step_index` | 0-based |
| `result.success` | `success` | |
| `result.elapsed_time * 1000` | `elapsed_ms` | |
| `result.retry_count` | `retry_count` | |
| `result.error_msg` | `error_msg` | |
| `result.error_code` | `error_code` | chain 模式通常为空 |
| `step.get("params", {})` | 传给 `extract_result_fields(node_type, result.data, step["params"])` | 复用现有提取逻辑 |
| `result.data` | 传给 `extract_result_fields` | 提取点击坐标/OCR 文本等 |
| `step.get("comment", "")` | `comment` | 可选 |
| `step.get("rationale", "")` | `rationale` | 可选 |

### 3.2 事件类型

| 事件 | 触发时机 | event 字段 |
|---|---|---|
| 步骤执行完成 | `_execute_step` 返回后 | `chain.step.complete` |
| 步骤重试中 | `_handle_retry` 每次重试后 | `chain.step.retry` |
| 前置验证失败 | `_execute_step` 中 pre_verify 失败 | `chain.step.pre_verify_failed` |
| 后置验证失败 | `_execute_step` 中 post_verify 失败 | `chain.step.post_verify_failed` |

> **注**：使用 `chain.*` 前缀以与 pipeline 的 `node.execute.*` 区分，便于 AI 工具按执行模式筛选 JSONL。

### 3.3 AutoResult 字段扩展

`AutoResult` 新增 `structured_log_path: str = ""` 字段：
- 默认空串，向后兼容
- `_execute_chain` 返回前设置 `result.structured_log_path = self._last_structured_log_path`
- handler.py 现有 `getattr(result, "structured_log_path", "")` 自动生效，无需修改

### 3.4 orchestrator 字段扩展

`TaskOrchestrator.__init__` 新增：
- `_structured_logger: StructuredLogger | None = None`
- `_execution_id: str = ""`
- `_last_structured_log_path: str = ""`

`execute_task` 入口（`_task_exec_lock` 内部）初始化：
- `self._execution_id = new_execution_id()`
- `self._structured_logger = get_structured_logger(self._execution_id, debug_dir=self._config.debug_dir)`
- `self._last_structured_log_path = self._structured_logger.file_path`

`_execute_step` 末尾调用 `log_node_event`（best-effort，失败不阻塞任务）。

任务结束（成功/失败/取消）后调用 `self._structured_logger.close()`，避免后续误写入。

### 3.5 debug_dir 来源

复用 `AgentConfig.debug_dir`（与 `execute_pipeline` 同一来源），保证 chain 与 pipeline 的 JSONL 落在同一目录树 `<debug_dir>/structured/<execution_id>.jsonl`。

---

## 4. 验收标准

1. ✅ chain 模式任务执行后，`<debug_dir>/structured/<execution_id>.jsonl` 文件存在
2. ✅ JSONL 每行包含 `event=chain.step.complete` 等事件，字段齐全（node_id/node_type/step_index/success/elapsed_ms）
3. ✅ handler 收到的 task.result 消息 `structured_log_path` 非空
4. ✅ backend `execution_snapshot.structured_log_path` 字段非空
5. ✅ AI 工具能通过该路径读取 JSONL 并诊断
6. ✅ chain 模式与 pipeline 模式的 JSONL schema 字段一致（仅 event 前缀不同）

---

## 5. 反模式记录（避免后续走弯路）

| 反模式 | 错误原因 | 正确做法 |
|---|---|---|
| 把 chain 转成 pipeline 走 PipelineEngine | 语义不同强行合并 | 两条路径独立执行，共享日志工具类 |
| 新建 ExecutionLogger 抽象层 | 过度设计 | 直接复用 StructuredLogger |
| 在 handler.py 层接入日志 | 违反关注点分离（协议层不该承担日志细节） | 在 orchestrator 业务层接入 |
| 给 chain 单独写一套 log 接口 | 双份维护 | 复用 `log_node_event` + `extract_result_fields` |

---

## 6. 关联文档

- logging-pipeline-hardening spec（历史 spec 文档未留存） — pipeline 模式 StructuredLogger 接入设计
- [structured_logger.py](../../../worker/src/utils/structured_logger.py) — 工具类实现
- [pipeline_engine.py](../../../worker/src/engine/pipeline_engine.py) — pipeline 模式接入参考（L413-422 初始化、L545-617 记录事件）
- [orchestrator.py](../../../worker/src/core/orchestrator.py) — chain 模式接入目标
