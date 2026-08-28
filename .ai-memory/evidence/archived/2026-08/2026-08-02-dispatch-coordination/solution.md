# Solution: Full Dispatch Coordination + URL Normalization + Perf Monitor

## 代码变更
1. **Pending 自动恢复**: `backend/tasks/tasks.py` 新增 `retry_pending_executions` 周期性任务，扫描 PENDING 超 5 分钟的执行重试
2. **进程唯一性**: `scripts/gaf_services.ps1` 根据命令行匹配杀旧进程，启动后验证无重复
3. **pipeline_name_p0 修复**: 将变量从 `execute_pipeline` 作为参数传递到 `_execute_pipeline_inner`
4. **handler.py 异常捕获**: 在 `handle_message` 外层 try/except，发送失败状态
5. **URL 归一化**: agent 端从 `GAF_API_PREFIX` 读取，前端从 `VITE_API_PREFIX` 读取，后端路由用 `APP_ROUTES` 映射，WS 路径用 `WS_AGENT_PATH`
6. **性能计量**: agent/backend 双端 `PerformanceMonitor` + `Timer` + `PerfMiddleware` + API 端点
7. **资源包重构**: BrownDust-II → "BrownDust II"，default → "GAF Default"，删除废弃包

## 文档变更
1. 新增 `docs/architecture/cross-cutting/dispatch-flow.md`
2. 更新 `docs/architecture/overview.md` 补充单Agent多窗口架构
3. 更新 `docs/reference/data-flow.md`、`docs/business/troubleshooting.md`
4. 更新 `.trae/rules/env-hardrules.md` 新增调度协调 + URL 归一化硬约束