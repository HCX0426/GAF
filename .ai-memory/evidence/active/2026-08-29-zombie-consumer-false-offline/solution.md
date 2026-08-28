---
maintainer: manual
source: GAF
load_when: [evidence]
priority: high
symptom: [zombie-consumer, agent-false-offline, stale-websocket]
solution: Agent 加 active_channel 字段做最新连接仲裁; 诊断口诀"status 与 last_heartbeat 矛盾 + 心跳超时秒数巨大递增 = 僵尸连接, 重启后端"
created_by: AI
last_updated: 2026-08-28
---
## Solution（解决步骤）

1. 诊断口诀：Agent.status 与 last_heartbeat 矛盾（offline + 心跳新鲜）+ daphne 日志"心跳超时 15xxx s"秒数递增 = 僵尸 consumer 覆盖，重启后端进程树即可清除
2. 治本方向（建议 TD）：Agent 模型加 `active_channel` 字段，heartbeat/offline 写入前校验 channel 指纹，仅接受最新 channel 的写入
3. 连接级周期任务（_heartbeat_checker）需能识别自身过期（channel 版本比对），避免僵尸任务无限写共享状态