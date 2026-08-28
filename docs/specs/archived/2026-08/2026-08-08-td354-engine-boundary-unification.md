# TD-354: Agent 三段引擎边界统一 (ChainManager + TaskExecutor 集成)

> **关联 TD**: TD-354 (Phase 1 Task 1.2: 梳理 Agent 三段引擎边界)
> **来源**: `docs/specs/active/2026-08-08-architechure-debt-refactor.md` Phase 1 Task 1.2
> **状态**: 🔧 待修 → 🚧 进行中 → ✅ 完成
> **优先级**: P1
> **登记时间**: 2026-08-08
> **完成时间**: TBD

---

## 1. 问题描述

### 1.1 现状

Agent 执行引擎有三条路径：
- **PipelineEngine**: 线性步骤执行（Click → Input → Screenshot）
- **StateMachine**: 状态机任务执行（根据界面状态决策下一步）
- **TaskExecutor**: 已创建统一入口，但仅注册了 `PipelineEngineAdapter`，**未注册 ChainManager**

当前 `TaskExecutor` 仅支持 `"pipeline"` 类型，`TaskOrchestrator` 仍直接创建 `PipelineEngine` 实例（L897），未使用 `TaskExecutor`。

### 1.2 具体问题

| 问题 | 描述 | 影响 |
|------|------|------|
| **缺少 ChainManager** | StateMachine 执行路径无 `BaseEngine` 包装 | 无法通过 TaskExecutor 统一分发 |
| **TaskExecutor 未集成到 Orchestrator** | Orchestrator 直接 `PipelineEngine()` 而非通过 executor | 三段引擎边界不清晰 |
| **StateMachine 入口不统一** | state_machine 走 `_execute_state_machine_dispatch` 分支 | 新增引擎需修改 orchestrator 核心逻辑 |

### 1.3 根因

`executor.py` Phase 1 仅实现了 `PipelineEngineAdapter`，`ChainManager` 未实现，`TaskOrchestrator` 未迁移到 `TaskExecutor`。

---

## 2. 修复方案

### 2.1 架构概览

```
agent/src/engine/
    ├── executor.py          ← 修改: 注册 ChainManager
    ├── chain_manager.py     ← 新增: StateMachine 的 BaseEngine 包装
    └── pipeline_engine.py   ← 不变

agent/src/core/
    └── orchestrator.py      ← 修改: state_machine 分发走 TaskExecutor
```

### 2.2 ChainManager 实现

新建 `agent/src/engine/chain_manager.py`，实现 `BaseEngine` 接口，包装 `StateMachine` 执行：

```python
class ChainManager(BaseEngine):
    """Chain 执行引擎 — 包装 StateMachine 执行路径。

    StateMachine 是 Python callable 模块 hook，不能 JSON 序列化，
    通过 `task_definition["module"]` 指定模块路径。
    """

    def run(self, task_definition: dict, **kwargs) -> AutoResult:
        """执行 StateMachine 任务。

        Args:
            task_definition: 含 ``module`` 字段的 dict。
            **kwargs: 支持:
                - device_manager: DeviceManager 实例
                - image_processor: ImageProcessor 实例
                - device_id: 可选设备 ID

        Returns:
            AutoResult 执行结果
        """
        ...
```

核心逻辑从 `TaskOrchestrator._execute_state_machine_dispatch()` 迁移，保持相同的行为契约。

### 2.3 TaskExecutor 注册

在 `TaskExecutor.__init__` 中注册 `ChainManager`：

```python
self._engines: dict[str, BaseEngine] = {
    "pipeline": PipelineEngineAdapter(),
    "chain": ChainManager(),  # 新增
}
```

### 2.4 TaskOrchestrator 集成

在 `TaskOrchestrator.execute_pipeline()` 中，state_machine 分支（检测 `module` 字段）改用 `TaskExecutor` 分发：

```python
# 修改前: 直接调用 _execute_state_machine_dispatch
if isinstance(pipeline_json, dict) and pipeline_json.get("module"):
    return self._execute_state_machine_dispatch(pipeline_json, device_id=device_id)

# 修改后: 通过 TaskExecutor 分发
if isinstance(pipeline_json, dict) and pipeline_json.get("module"):
    executor = TaskExecutor()
    return executor.execute("chain", pipeline_json, ...)
```

---

## 3. 任务清单

### Task 1: 创建 ChainManager

- [ ] 1.1 新建 `agent/src/engine/chain_manager.py`
- [ ] 1.2 实现 `ChainManager(BaseEngine)` 类
- [ ] 1.3 核心逻辑：import module → build_state_machine → machine.run()
- [ ] 1.4 设备切换逻辑（set_active_device + finally 恢复）

### Task 2: 注册到 TaskExecutor

- [ ] 2.1 在 `TaskExecutor.__init__` 中注册 `ChainManager`
- [ ] 2.2 更新 `engine/__init__.py` 导出

### Task 3: 重构 TaskOrchestrator

- [ ] 3.1 state_machine 分支改用 `TaskExecutor.execute("chain", ...)`
- [ ] 3.2 保留 `_execute_state_machine_dispatch` 向后兼容（测试依赖）

### Task 4: 测试

- [ ] 4.1 编写 `ChainManager` 单元测试
- [ ] 4.2 验证 `TaskExecutor` 可分发 "chain" 类型
- [ ] 4.3 回归测试：state_machine 执行路径不变

---

## 4. 验证标准

| # | 验证项 | 期望 | 验证方式 |
|---|--------|------|----------|
| 1 | `TaskExecutor.engines` 包含 "chain" | `"chain" in executor.engines` | pytest |
| 2 | `TaskExecutor.execute("chain", ...)` 返回正确结果 | 成功返回 AutoResult | pytest |
| 3 | 任务含 `module` 字段时走 ChainManager | 不报错，执行结果正确 | pytest |
| 4 | 任务不含 `module` 字段时仍走 PipelineEngine | 行为不变 | pytest |
| 5 | 设备切换逻辑正确 (set_active_device) | 设备切换后恢复 | pytest |
| 6 | 向后兼容：`_execute_state_machine_dispatch` 仍可用 | 直接调用不报错 | pytest |

---

## 5. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `agent/src/engine/chain_manager.py` | 新增 | ChainManager 实现 |
| `agent/src/engine/executor.py` | 修改 | 注册 ChainManager |
| `agent/src/engine/__init__.py` | 修改 | 导出 ChainManager |
| `agent/src/core/orchestrator.py` | 修改 | 使用 TaskExecutor 分发 state_machine |
| `agent/tests/engine/test_chain_manager.py` | 新增 | ChainManager 测试 |

---

## 6. 测试计划

### 6.1 新增测试

**`agent/tests/engine/test_chain_manager.py`**:

| # | 测试名 | 验证点 |
|---|--------|--------|
| 1 | `test_chain_manager_is_baseengine` | ChainManager 是 BaseEngine 子类 |
| 2 | `test_chain_manager_run_missing_module` | 缺 module 字段返回 fail |
| 3 | `test_chain_manager_run_module_import_error` | 模块导入失败返回 fail |
| 4 | `test_chain_manager_run_missing_builder` | 模块无 build_state_machine 返回 fail |
| 5 | `test_chain_manager_run_builder_error` | builder 抛出异常返回 fail |
| 6 | `test_chain_manager_run_success` | 正常执行返回 success |
| 7 | `test_chain_manager_run_device_switch` | 设备切换逻辑正确 |
| 8 | `test_task_executor_registers_chain` | TaskExecutor 含 chain 引擎 |
| 9 | `test_task_executor_dispatch_chain` | TaskExecutor 分发 chain 成功 |