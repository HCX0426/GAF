# s45 Problem — 录制截图占位

## 症状
RecordingStepper.tsx 截图区域显示占位文字"截图需通过后端 URL 访问"。

## 根因链（L3-1 扫描 s42 确认）
1. agent 录制模式（`python -m src --record`）截图写 agent 本地 `./recordings/screenshots/<name>/`，`recording_data.events[].screenshot_path` 是 agent 本地路径，前端无法访问
2. `RecordingAPIClient`（agent/src/core/recording_api.py）是死代码——无调用方、无鉴权 header
3. backend 无录制截图存储/serve 端点
4. 前端 RecordingPanel 是 demo 假数据（随机 click，注释明示 "Demo"）

## 影响
录制回放（RecordingStepper）无法展示真实截图；agent CLI 录制的数据无法进入 backend 闭环。

## 用户决策
方案 2：接真截图——对接 backend，截图落盘 + 前端展示。