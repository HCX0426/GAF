---
maintainer: manual
source: GAF
load_when: [evidence]
priority: high
symptom: [zombie-consumer, agent-false-offline, stale-websocket]
solution: 僵尸 consumer 的 _heartbeat_checker 永不取消 → 每 10s set_agent_offline 覆盖新连接的心跳 idle; 重启后端即清
created_by: AI
last_updated: 2026-08-28
---
## Problem（症状 / 触发条件）

用户反馈："右上角 系统运行状态 — 未启动，不是有 agent 吗"。现象：
- 右上角状态灯显示 idle（未启动），但 agent 明明存在且心跳正常
- Agent.status 与 Agent.last_heartbeat 矛盾（offline + 心跳新鲜 ~10s）
- daphne 日志每 10s 一条 "Agent 心跳超时 15161s 标记为离线"（秒数递增）
- AgentSession.status 始终 online

## Solution（解决步骤）

1. 连查 DB Agent.status（间隔 2s×12 次）→ 观察到 idle↔offline 每 10s 抖动
2. grep daphne 日志 → "心跳超时 15xxx s" 秒数恒定递增 → 僵尸 consumer 的 _heartbeat_checker 仍在跑
3. 定位根因：agent 重启后旧 WS 连接未触发 disconnect()，其循环任务覆盖新连接写入
4. 修复：`D:\code\environment\conda\envs\gaf\python.exe d:\code\GAF\scripts\gaf_daemon.py restart` 重启后端进程树清僵尸
5. 验证：agent 稳定 idle（35s 无跳变）→ overall=running → 浏览器实测绿色灯"运行中"

## Verification（验证）

$ git log backend/protocol/consumers.py backend/protocol/services.py -5 --oneline

$ D:\code\environment\conda\envs\gaf\python.exe scripts/bootstrap/sync_ai_memory.py --query "zombie consumer agent false offline"

$ Get-NetTCPConnection -LocalPort 8000 -State Listen

预期：find N216 lesson; :8000 LISTENING; Agent.status=idle 稳定 30s+