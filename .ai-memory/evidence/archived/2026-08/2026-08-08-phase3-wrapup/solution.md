# 解决方案

## 实施方式

1. **TD-350**: 新增 `node_registry.py` 实现节点元数据注册，包含 JSON Schema 校验
2. **TD-351**: TaskExecution 模型新增 `is_archived`/`archived_at` 字段，实现软删除归档
3. **TD-352**: 新增 `scripts/gaf_daemon.py` Python 守护进程替代 PowerShell 管理
4. **TD-353**: PipelineEngine 引入 `_step_cancel_event` 实现步骤级协式中断
5. **TD-354**: 新增 `ChainManager(BaseEngine)` 包装 StateMachine，注册到 TaskExecutor

## 关键决策

- 引擎统一采用 TaskExecutor 分发模式，保持 `BaseEngine` 接口契约
- 进程守护采用 Python 实现而非继续扩展 PowerShell，提高跨平台兼容性
- 归档采用软删除（is_archived flag）而非物理删除，保留数据可恢复性