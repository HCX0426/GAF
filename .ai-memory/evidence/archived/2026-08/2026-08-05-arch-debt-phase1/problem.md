# Problem: 架构债务累积 — Service 层缺失 + Agent 引擎边界模糊

## 现象
1. **视图层过胖**: `tasks/views.py`、`scheduler/views.py`、`agents/views.py` 中混入大量业务逻辑（设备探测、调度计算、任务派发），视图函数 200+ 行常见。
2. **Agent 引擎入口不统一**: `engine.py` 同时承担 Pipeline 执行 + 引擎生命周期管理，且 `TaskExecutor` 缺失，agent 端通过 `handle_pipeline_execute` 和 `handle_task_assign` 两个入口处理任务。
3. **测试耦合**: 视图层测试必须 mock 整个业务逻辑链，无法单独测试 service 方法。

## 影响范围
- backend: tasks, scheduler, agents 三个 app
- agent: engine 模块
- 全量测试 2775+ 个