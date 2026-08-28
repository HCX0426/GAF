# s43 verification — 验证矩阵

## 验证矩阵

| # | 验证项 | 结果 | evidence |
|---|--------|------|----------|
| 1 | backend WS 路由回归 | ✅ **268 passed**（protocol/tests + agents test_device_api） | `pytest backend/protocol/tests/ backend/agents/tests/test_device_api.py -q` |
| 2 | 前端 TS 检查 | ✅ vite build 成功 | `npx vite build`（frontend/） |
| 3 | WS 硬编码残留 | ✅ 仅默认值 + 历史注释（非运行时） | grep `ws/devices` frontend/src + backend |
| 4 | 死组件 0 引用 | ✅ 删除后 grep 无残留 | grep TimeWindowConfig/NodePreviewModal 等 |
| 5 | 文档路径验证 | ✅ 修正后路径 glob 全部存在 | device_bridge/handlers/verify.py + agent/src/engine/graph.py + core/chain_manager.py |
| 6 | TD 迁移 | ✅ TD-366/367/368 → fixed（本节） | active-tech-debt.md 清空 |

## 时间

- N173: start ~02:10 / end ~02:45 / duration ~35min — 中修改基线 15min 超时。
  归因：3 个 TD 批量（代码 + 8 文件删除 + 10 处文档）+ 验证两轮；实际单 TD 均 < 10min。记录观察项（批量 spec 基线应放宽）。