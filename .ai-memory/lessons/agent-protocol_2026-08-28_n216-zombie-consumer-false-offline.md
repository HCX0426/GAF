---
date: 2026-08-28
symptom: [zombie-consumer, agent-false-offline, stale-websocket, heartbeat-overwrite, status-flapping]
solution: Agent 状态 idle↔offline 抖动且日志显示"心跳超时 15161s"而 DB last_heartbeat 新鲜 = 僵尸 consumer 的 _heartbeat_checker 仍未取消, 每 10s set_agent_offline 覆盖新连接写入; 应立即重启后端进程树清僵尸, 治本需按 channel 身份仲裁最新连接
related_files:
  - backend/protocol/consumers.py
  - backend/protocol/services.py
  - backend/workers/agent_runtime.py
  - agent/src/client/connection.py
created_by: AI
priority: high
n_id: N216
level: L1
topic: agent-protocol
diff_keywords: ["_heartbeat_checker", "set_agent_offline", "update_agent_heartbeat", "_last_heartbeat", "HEARTBEAT_OFFLINE_SECONDS"]
---
# Agent 假离线：僵尸 consumer 覆盖心跳状态

## 症状（2026-08-28 用户反馈"有 agent 但状态灯显示未启动"）

1. 右上角状态灯显示 idle，用户质疑"不是有 agent 吗"。
2. `GET /api/v2/monitors/status/` 返回 `devicesTotal=1, overall=idle`——因为 Agent.status 是 offline。
3. 但 Agent 心跳在更新（`update_agent_heartbeat` 每 10s 执行，last_heartbeat 新鲜 ~10s）。
4. Agent.status 在 idle ↔ offline 间**每 ~10s 抖动**（连查 12 次观察到 idle 只持续 2s，其余 8s 都是 offline）。
5. daphne 日志每 10s 一条：`Agent 心跳超时 15161s，标记为离线`（超时秒数恒定递增 10s）。
6. AgentSession.status 始终 online（session 是新的，agent 表被旧连接覆盖）。

## 根因

**两个 AgentWebSocket consumer 实例并存，互相覆盖同一 agent_id 的 DB 状态：**

1. **僵尸 consumer**（旧连接）：agent 19:21 重启时旧 TCP 连接未触发服务端 `disconnect()`（客户端异常退出无 close 帧），其
   `_heartbeat_checker` 无限循环任务（每 10s 检查 `time.time() - self._last_heartbeat > HEARTBEAT_OFFLINE_SECONDS`）
   从未被取消，`self._last_heartbeat` 永远停在旧值 → 每 10s 判定"心跳超时 15161s" → 调
   `_db_set_agent_offline(agent_id)` 把 Agent.status 置 offline。
2. **新连接**（live）：每 10s 收到 agent.heartbeat 帧 → `update_agent_heartbeat` 把 Agent.status 置 idle。
3. **无唯一性仲裁**：`set_agent_offline` / `update_agent_heartbeat` 都只按 agent_id 无差别 UPDATE，不知道
   哪个 channel 是 agent 的"现任连接"。两点互相覆盖 → 状态抖动。
4. **后端长期不重启**：daphne 17:34 启动后一直运行，僵尸 consumer 挂在内存（Channels 内存 layer），
   不清除 → 症状持续 4 小时+（15161s）。

## 排查路径（下次直接照抄）

1. 先看 DB：`Agent.status` 与 `Agent.last_heartbeat` 矛盾（offline + 心跳新鲜）→ 有人外部覆盖。
2. 连查 2 次 status（隔 2s）：idle/offline 跳变 → 双写竞争实锤。
3. grep daphne 日志：`Agent 心跳超时 15\d+s`（秒数恒增）→ 僵尸 consumer 的 checker 仍在跑。
4. 重启后端进程树（`python scripts/gaf_daemon.py restart`）→ 清僵尸 → 状态稳定 idle。
5. 治本方向（未实施）：为 Agent 记录"当前持有 channel"，set_agent_offline 前校验来源；或
    heartbeat 更新时带 channel 指纹，仅接受最新 channel 写入。

## 泛化原则

- WS 连接断开 ≠ disconnect() 必然触发。客户端异常退出/断网/重连时，服务端可能长期保留
  死连接的周期性后台任务。
- 任何"每 N 秒循环 + 写共享状态"的连接级任务，必须能识别自己是否已过期（channel 版本/最后活跃比对）。
- agent 心跳类状态若存在"DB 值 vs 会话内变量"两种来源，必然出现竞争，需单一来源。

## 防错机制

- 诊断口诀：**"status 与 last_heartbeat 矛盾 + 心跳超时秒数巨大且递增 = 僵尸连接，重启后端"**。
- **治本已落地 (spec 2026-08-29 P4)**：Agent 表加 `active_channel` 字段（migration 0018），
  `connect()` CAS 接管，`update_agent_heartbeat` / `set_agent_offline` 带 channel 守卫
  （非现任 channel 写入 0 行），`_heartbeat_checker` 每轮自查 active_channel 过期即自愈退出。
  后续出现 agent 状态异常时，优先检查 active_channel 是否被正确接管/清理。