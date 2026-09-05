---
date: 2026-09-05
symptom: [worker-health-busy, daemon-restart-mid-task, agent-disconnected, execution-interrupted]
solution: 服务健康判定必须把"执行中(busy)"视为健康状态 — busy+心跳新鲜=正常干活; 假死由心跳陈旧(fresh)兜底, 不能按 status 白名单误杀忙碌进程
related_files:
  - scripts/services/health.py
  - scripts/gaf_daemon.py
  - scripts/tests/test_health_services.py
created_by: AI
priority: high
n_id: N221
diff_keywords: ["WORKER_HEALTHY_STATUSES", "check_worker", "健康感知重启", "daemon", "busy"]
---

# daemon 健康监控把执行中(busy)的 agent 判为不健康 → 重启中断执行

## 症状（2026-09-05 e2e 验证 7 个执行入口发现）

Pipeline 执行（exec 372）报 `Agent 断开连接，任务中断`；worker 日志显示收到 dispatch 后 3 秒进程重启。daemon 日志定位：
`[worker] 进程存活但健康检查失败 (status=busy hb_age=1.5225s) → 触发健康感知重启`。

## 根因

`scripts/services/health.py` 里 `WORKER_HEALTHY_STATUSES = {"idle", "online"}` **漏了 `busy`**。agent 一旦开始执行任务（status=busy，心跳完全正常 1.5s），daemon 每 15s 的健康检查就把它判为不健康 → 重启 → WS 断开 → 当前执行被中断。**任何执行时长跨过健康检查点的任务都会被打断**，是所有执行入口共同的隐性中断源。exec 371（游戏档案派发）逃过是因为执行仅 7s 未撞上检查点，纯属时序侥幸。

## 解决方案（已实现，commit 2ed1531）

1. `WORKER_HEALTHY_STATUSES = {"idle", "online", "busy"}` — busy 是 agent 正常干活状态
2. 假死兜底保留 `fresh`（last_heartbeat < 30s）：busy + 心跳陈旧 → 仍判不健康触发重启（僵尸 busy 不会漏）
3. 补单测 3 例：busy+fresh→healthy / busy+stale→unhealthy / idle+fresh→healthy
4. 顺手修同文件既有缺陷：`_native_log_paths` 缺 `agent` 分支（注释声称支持但代码没有，agent 原生日志=worker/system/worker.log）→ 修实现 + 修正虚构路径的测试

## 泛化原则

**"忙碌"不是"不健康"**。服务健康监控按 status 白名单判定时，必须把"正在工作/执行中"的状态显式纳入健康集合，否则看门狗会在任务进行中把服务杀掉。健康判定的核心信号是**心跳新鲜度**（是否假死），而不是"是否空闲"；空闲≠健康（可能假死），忙碌≠不健康（可能正常执行）。
