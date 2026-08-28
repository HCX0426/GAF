# s43 problem — TD-366/367/368 三个 [B] 类问题（L3-1 扫描登记）

## 触发

s42 L3-1 扫描登记 TD-366/367/368 → 按 §4.8 TD 处理顺序接修（P2 优先，批量）。

## TD-366: AdbLogViewer WS 路径硬编码（集成层⑨）

- AdbLogViewerPage.tsx:127 `ws/devices/${id}/adb-logs/` 硬编码 + backend agents/routing.py:11 硬编码正则
- N197 只覆盖协议级 WS（ws/protocol/agents/），设备级 WS 未 env 化
- 路由改名 → 前端静默断连

## TD-367: 8 个死组件（功能层⑤）

- frontend/src/components/Scheduler/ 7 个 + components/Pipeline/NodePreviewModal.tsx
- 0 处 import（grep 41 匹配全为定义文件自身 + 2 同名 interface/function）
- ~2000 行死代码，UnattendedControlPage 自实现渲染

## TD-368: 架构文档 3 处路径/数值过期（架构层③）

- optimal-solution.md:349 backend/agent/handlers/verify.py（实际 device_bridge/handlers/verify.py）+ :145 graph.py 状态错（实际存在）
- overview.md devices/worker_pool.py 不存在 + core/chain.py（实际 chain_manager.py）
- features-overview.md: 心跳 15s/30s（实际 10s/30s）+ tracing//metrics//i18n/ 3 个已移除 app 残留 + metrics/sla（实际 monitors/sla）