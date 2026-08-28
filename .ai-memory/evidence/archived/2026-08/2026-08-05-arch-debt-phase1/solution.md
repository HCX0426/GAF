# Solution: Phase 1 — Service 层 + Agent 引擎重构

## 方案
1. **Service 层模式**: 为 tasks/scheduler/agents 三个 app 创建 `services/` 包，将业务逻辑从 views 迁移到 service 类中。
2. **Agent 引擎重构**: `engine.py` → `pipeline_engine.py`（专注 Pipeline 执行）+ `executor.py`（`TaskExecutor` 统一入口）。
3. **视图层瘦身**: views 只负责 HTTP 协议处理（参数校验、序列化、响应），业务逻辑委托给 service。

## 关键决策
- Service 类用简单构造函数，不引入 DI 框架（保持轻量）
- `TaskExecutor` 用 registry 模式注册 engine，支持未来扩展
- 向后兼容：旧模块路径通过 `__init__.py` re-export 保持兼容