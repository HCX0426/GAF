# s43 solution — 三个 TD 修复

## TD-366: WS 路径 env 化（N197 模式扩展）

- backend/config/app_info.py: `WS_DEVICES_PATH = os.getenv("GAF_WS_DEVICES_PATH", "ws/devices/")`
- backend/agents/routing.py: `re_path(rf'^{WS_DEVICES_PATH}(?P<device_id>[^/]+)/adb-logs/$')`
- frontend/src/config/app.ts: `WS_DEVICES_PATH = import.meta.env.VITE_WS_DEVICES_PATH || '/ws/devices/'`
- frontend/.env: `VITE_WS_DEVICES_PATH=/ws/devices/`
- AdbLogViewerPage.tsx: url 拼 `${WS_DEVICES_PATH}${id}/adb-logs/`
- 改 env 一处 → 全链路生效（自问验证: 改路径需改 1 处 ✓）

## TD-367: 死代码删除

- git rm 8 组件（TimeWindowConfig/SwitchIntervalConfig/ExecutionPlanPreview/DeviceWarmupEditor/ConcurrencyMatrixPanel/AutoStopConditions/AccountRotationEditor/NodePreviewModal）
- 删除前 grep 验证 0 引用（N174 修复方案验证）

## TD-368: 文档漂移修正（10 处）

1. optimal-solution.md:349 → device_bridge/handlers/verify.py
2. optimal-solution.md:145 graph.py → ✅ 存在
3. overview.md:537 删 devices/worker_pool.py 行
4. overview.md:558 chain.py → chain_manager.py
5. features-overview.md:50 心跳 15s/30s → 10s/30s
6. features-overview.md:280 6 app → 4 app（去 tracing/metrics）
7. features-overview.md:307 tracing/spans → gaf_core/tracing (trace_id)
8. features-overview.md:351 metrics/sla → monitors/sla
9. features-overview.md:474 去 i18n/（并入 gaf_core）
10. features-overview.md:564-566 i18n//tracing//metrics/ → gaf_core.i18n / gaf_core.tracing / monitors

## 关键决策

- 设备 WS 用**前缀段 env**（ws/devices/）而非全路径模板：动态 deviceId 是路径变量，前缀段归一化即达 N197 目标
- tracing 文档描述更新为实际实现（gaf_core/tracing trace_id ContextVar，无 TraceSpan 三层）