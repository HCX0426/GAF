---
maintainer: manual
source: BD2 get_email pipeline 测试
load_when: [agent-startup, pid-lock, singleton, 重复进程, WS 路由失效]
priority: high
symptom: [kb:agent-singleton, pid-lock, duplicate-agent, ws-routing-failure, N186, TD-339]
solution: agent 独立进程 __main__.py 加 acquire_singleton_lock PID 文件锁; 区分 agent 自身 vs backend agent_runtime.py
diff_keywords: ["main", "__main__", "agent", "runtime", "agent_runtime", "overview", "deployment", "design", "deployment-design", "agent-startup", "pid-lock", "singleton"]
related_files:
  - worker/src/__main__.py
  - backend/workers/worker_runtime.py
  - docs/architecture/overview.md
  - docs/architecture/desktop/deployment-design.md
created_by: AI
topic: platform-env
last_updated: 2026-07-23
---


# N186 — Agent 独立进程单例锁缺失 (TD-339)

## Problem（症状 / 触发条件）

BD2 get_email pipeline 测试中出现 4 个 agent 进程同时运行, 导致:

1. WS session 路由失效 — backend `group_send("agent_{id}")` 发到 agent_id 维度, 但 WS session 是 UUID 维度, 多 agent 同时连同一 agent_id 时消息路由错乱
2. screenshot 流风暴 — 多 agent 并发截图, device 被多次抢占
3. heartbeat 抖动 — 多 agent 心跳互相覆盖 Agent.status, 在 ONLINE/IDLE/OFFLINE 间抖动
4. executions 卡 pending — pipeline dispatch 成功 (status=sent) 但 agent 从未接收, execution 一直 pending

触发条件: 手动多次 `python -m src` 启动 agent (我作为 AI 在测试时连续启动 4 次, 违反 N155 行为规则).

影响范围: 所有手动启动 agent 的场景 (开发调试 / 外部脚本调用 / CI 环境).

## Solution（解决步骤）

1. `worker/src/__main__.py` 加 `acquire_singleton_lock()` / `release_singleton_lock()` 函数, 写 PID 文件 `%TEMP%\gaf_agent_lock\standalone.pid`
2. `main()` 入口在 `asyncio.run(run_agent(...))` 前调 `acquire_singleton_lock()`, 检测到存活 PID 则 `sys.exit(1)`
3. `finally` 块调 `release_singleton_lock()` 确保异常退出也释放锁
4. 加 `--skip-singleton-check` CLI 参数 (仅限调试场景)
5. `_is_pid_alive()` 用 psutil (优先) 或 Windows OpenProcess / POSIX os.kill(pid, 0) 回退

关键边界界定 (重要):
- **backend 端 `agent_runtime.py`** (TD-217 闭环): 保护 backend 自启 agent 子进程, 用 `manager.lock` + `agent.pid` + `_kill_stale_agent_processes()` + DB 心跳双检测 + 指数退避重启
- **agent 自身 `__main__.py`** (TD-339, 本 lesson): 保护手动启动场景, 用 `standalone.pid` PID 文件锁
- 两者**互补不重叠**: backend 端机制只在 backend 自启时生效, 手动 `python -m src` 完全绕过 backend, 由 agent 自身兜底

## Verification（验证）

```bash
# 1. 启动第一个 agent (成功)
cd d:\code\GAF\agent
D:\code\environment\venvs\gaf-agent\Scripts\python.exe -m src --agent-token <TOKEN>
# 预期: 日志 "Acquired agent singleton lock (PID <PID>)."

# 2. 另开终端启动第二个 agent (应 exit 1)
cd d:\code\GAF\agent
D:\code\environment\venvs\gaf-agent\Scripts\python.exe -m src --agent-token <TOKEN>
# 预期: 日志 "Agent singleton lock held by PID <PID1>... 退出." + exit code 1

# 3. 停止第一个 agent, 重启应成功 (stale lock reclaim)
# 预期: 日志 "Reclaiming stale agent lock (PID <PID1> not alive)."

# 4. --skip-singleton-check 绕过 (调试场景)
D:\code\environment\venvs\gaf-agent\Scripts\python.exe -m src --agent-token <TOKEN> --skip-singleton-check
# 预期: 不检查锁, 直接启动 (仅限调试)
```

预期: 第二个 agent exit code 1, 第一个 agent 正常运行; stale lock 自动 reclaim; `--skip-singleton-check` 可绕过.

## 反思

**与 N154/N155 的关系**: N154/N155 黑屏家族覆盖 backend 自启 agent 场景的代码防护 (`_kill_stale_agent_processes()` + `GAF_AUTO_START_AGENT=0` 默认). N186 补齐 agent 自身独立进程的单例锁, 是同一问题家族的 agent 端补丁.

**为何 N154/N155 没覆盖**: N154/N155 设计时假设 agent 只由 backend 启动 (生产场景). 开发场景手动启动是 N155 行为规则约束 (AI 启动前检查), 但行为规则无法防住所有情况 (用户手动 / 外部脚本 / CI). N186 用代码层 PID 锁兜底.

**编号冲突教训**: 登记本 TD 时最初用 TD-333/TD-334, 与 fixed.md 已闭环的 TD-333 (device_type_hint) / TD-334 (截图 handler) 编号冲突. 违反 §6.4 "编号一旦分配永不复用" 精神. 修正为 TD-339/TD-340. 教训: TD 编号分配前必 grep `{active,fixed,wontfix}.md` 验证 (已沉淀到 project_rules §4.8).
