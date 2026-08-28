# Verification

## 验收结果
- [x] 执行卡在 PENDING 超过 5 分钟后自动重试（最大 5 次）
- [x] `gaf_services.ps1 start` 确保只有一个 Celery Worker + 一个 Celery Beat
- [x] `gaf_services.ps1 start` 末尾自动启动 monitor
- [x] 子 pipeline 执行不再因 `pipeline_name_p0` 作用域错误崩溃
- [x] `handler.py` 异常捕获后正确发送失败状态，任务不卡住
- [x] Agent 端 API 路径从 `GAF_API_PREFIX` 读取，无硬编码 `/api/v2/`
- [x] 前端 API 前缀从 `VITE_API_PREFIX` 读取，无硬编码
- [x] 后端路由使用 `APP_ROUTES` 映射拼接
- [x] WebSocket 路径使用 `WS_AGENT_PATH` 变量
- [x] 调试模式通过根目录 `.env` 的 `GAF_DEBUG` 统一控制
- [x] `tasks/tasks.py` 中无 `check_agent_heartbeats` 死代码
- [x] 新增 `docs/architecture/cross-cutting/dispatch-flow.md` 完整
- [x] `env-hardrules.md` 含调度协调硬约束 + URL 拼接归一化约束
- [x] agent/backend 双端 perf_monitor 实现，API 端点 `/api/v2/system/perf` 可用