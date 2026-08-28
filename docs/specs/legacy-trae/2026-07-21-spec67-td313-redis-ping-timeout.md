---
spec_id: spec-67
title: TD-313 test_task_result_returns_ack Redis ping 同步阻塞 4s 超时 (修复 redis_utils.get_redis_client 加 socket_timeout=0.2)
status: ✅ done
created: 2026-07-21
owner: AI
priority: P2
related_tech_debt: [TD-313]
n167_score: B 治本 (实施) - 单方案修复, 无需 N167 评分
---

# spec-67: TD-313 修复 — redis_utils.py 加 socket_timeout

## 背景

spec-65 Phase 7 验证 `-n auto` 时发现 `test_task_result_returns_ack` TimeoutError, 单核也失败 → 登记 TD-313.

spec-67 Phase 1 定位根因:
- 测试日志: `18:07:25,322 task.result 处理` → `18:07:29,534 Redis unavailable` (4 秒后!)
- 根因: `redis.Redis(host, port).ping()` 同步阻塞 ~4s 才返回 ECONNREFUSED (Redis 默认 socket_connect_timeout 长)
- 链路: `_handle_task_result` → `_release_resources_for_execution` → `_release_concurrency_slot` → `get_default_controller()` → `RedisConcurrencyController.__init__` → `get_redis_client()` → `ping()` 阻塞 4s
- 超过 `WebsocketCommunicator.receive_from()` 默认 1s timeout → TimeoutError

## Phase 1: 定位根因 (✅)

- [x] 1.1 跑单核 test 拿完整日志, 发现 `task.result` → `Redis unavailable` 间隔 4s
- [x] 1.2 链路分析: _release_resources_for_execution → get_redis_client().ping() 同步阻塞
- [x] 1.3 修复方案: `get_redis_client()` 加 `socket_timeout=0.5` + `socket_connect_timeout=0.5`

## Phase 2: 修 redis_utils.py (✅)

- [x] 2.1 get_redis_client() 加 socket_timeout=0.2 + socket_connect_timeout=0.2 (从 0.5 调低以适配 receive_from 1s timeout)
- [x] 2.2 注释说明: 防 Redis 未跑时 ping() 阻塞 4s 触发测试 TimeoutError (TD-313)

## Phase 3: 验证 单核 + -n auto 测试通过 (✅)

- [x] 3.1 单核 `pytest test_task_result_returns_ack -p no:xdist -v` → `1 passed in 26.25s` ✅ (之前 `1 failed in 17.71s`)
- [x] 3.2 全套 `-n auto` `pytest backend/ -n auto -q` → `1955 passed, 3 warnings in 140.79s` ✅ (之前 `1954 passed, 1 failed`, +1 test 不再失败)

## Phase 4: N177 中修改全套回归 (-n auto) (✅)

- [x] 4.1 全套 `pytest backend/ -n auto -q` → 140.79s < 600s (中修改基线) ✅

## Phase 5: TD-313 迁移 fixed.md + active.md 计数 + commit + 反思 (✅)

- [x] 5.1 active.md TD-313 段落 (🔧 → ✅ FIXED)
- [x] 5.2 fixed.md 追加 TD-313 ✅ FIXED 段落
- [x] 5.3 active.md 顶部计数 7 → 6
- [x] 5.4 git commit
- [x] 5.5 反思段

## 反思 (中修改 ~30 行, 跑 5 项反思)

### ① 4 问反思

1. **改了什么**: `backend/tasks/redis_utils.py` `get_redis_client()` 加 `socket_timeout=0.2` + `socket_connect_timeout=0.2` (URL + host:port 两条路径都加) + TD-313 fix 注释
2. **为什么改**: `redis.Redis(host, port).ping()` 默认 socket_connect_timeout 长, Redis 未跑时阻塞 ~4s, 超过 `WebsocketCommunicator.receive_from()` 默认 1s timeout → `test_task_result_returns_ack` TimeoutError; TD-313 根因
3. **怎么验证**: 单核 `1 passed in 26.25s` (之前 `1 failed`) + 全套 `-n auto` `1955 passed in 140.79s` (之前 `1954 passed, 1 failed`); 日志从 `Error 10061` → `Timeout connecting to server`
4. **影响范围**: `tasks/redis_utils.py` 单文件修改; 副作用: 全套时间 117s → 141s (+24s, 每个 worker 首次 ping 多 0.2s), 可接受 (远低于 600s, `_REDIS_PROBED` cache 后不再触发)

### ② 状态标记

- ✅ spec-67 done (TD-313 修复)
- ✅ N177 中修改全套回归 141s < 600s 通过
- ✅ TD-313 迁移 fixed.md
- ✅ active.md 7 → 6 活跃 TD

### ③ A/B/C 改进

- A: socket_timeout=0.2 是合理值 (Local Redis 健康 0.2s 足够, 远程 Redis 可用 REDIS_URL override)
- B: 可选 — 加环境变量 `REDIS_SOCKET_TIMEOUT` 让生产远程 Redis 调整 (当前 over-engineering, 不加)
- C: 选 A (当前修复足够, 留待生产远程 Redis 部署时再加 env var)

### ④ 根因分析

- **直接根因**: `redis.Redis(...).ping()` 默认 socket_connect_timeout 长 (Linux 默认 TCP SYN+ACK 重试 ~4s)
- **深层根因**: `get_redis_client()` 设计未考虑测试场景 (InMemoryChannelLayer 已替代 Redis, 但 `RedisConcurrencyController.__init__` 仍调 `get_redis_client()`); 此为 TD-259 #29 cross-app import 隔离的副作用
- **教训**: 同步 IO 调用必须有显式 timeout (socket_timeout / requests timeout / httpx timeout), 不能依赖默认值

### ⑤ 上下文管理

- 本次 spec-67 上下文使用合理: Phase 1 根因定位 (Read + Grep 链路分析) + Phase 2 单文件 Edit + Phase 3 验证 + Phase 5 文档治理; 未触发 N160 上下文饱和
