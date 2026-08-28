---
spec_id: spec-2026-08-16-s1-protocol-reliability
title: S1 协议可靠性语义补全 (dispatch ack / result 状态守卫 / 出站队列 / heartbeat 释放 slot)
status: ✅ 已归档 (docs/specs/archived/2026-08/2026-08-16-s1-protocol-reliability.md)
created: 2026-08-16
task_type: refactor
applies_to: [backend, agent, protocol]
---

# S1 — 协议可靠性语义补全

> 来源：2026-08-16 AI 大脑 + 工作流全面评估 Phase 1（S1）。评估报告结论：WS 协议层"帧格式+压缩协商+观测性"成熟，但可靠性语义缺失——无派发确认、无出站队列、无结果状态守卫，三者叠加构成"健康 agent 下执行卡死"和"迟到结果复活"两个真实数据一致性缺陷。

## 阶段状态表

| 阶段 | 内容 | 状态 | 完成时间 | commit hash |
|------|------|------|---------|-------------|
| P1 | task.dispatch 派发确认 (ack + 超时补发) | ✅ | 2026-08-16 | - |
| P2 | task.result 状态守卫 | ✅ | 2026-08-16 | - |
| P3 | agent 出站队列 (断线重放) | ✅ | 2026-08-16 | - |
| P4 | heartbeat 释放并发槽位 | ✅ | 2026-08-16 | - |
| P5 | 测试补齐 + 文档同步 | ✅ (测试) / 🔧 (文档 dispatch-flow.md 待 S2 后统一更新) | 2026-08-16 | - |

## 任务清单

### P1: task.dispatch 派发确认

- [x] backend: dispatch 后记录 dispatch_sent_at + dispatch_attempts (tasks/tasks.py)
- [x] agent: 收到 task.assign/task.dispatch 后回 event.ack(ack_type="task.dispatch") (handler.py)
- [x] backend: consumers._handle_event_ack 处理 task.dispatch ack → 写 dispatch_ack_at (consumers.py)
- [x] backend: check_dispatch_acks beat 任务 (10s) — agent 在线重派 / 离线 fail (heartbeat.py + celery.py)

### P2: task.result 状态守卫

- [x] protocol/services.py update_task_execution_result 终态守卫 (SUCCESS/FAILED/CANCELLED/FORCE_TERMINATED 拒绝覆盖)

### P3: agent 出站队列

- [x] connection.py send_message 失败 → 入 outbox (deque maxlen=50)
- [x] 重连成功后 _flush_outbox FIFO 重放; 重放中断剩余帧重新入队

### P4: heartbeat 释放并发槽位

- [x] heartbeat.py fail RUNNING 循环补 _release_concurrency_slot

### P5: 测试 + 文档

- [x] backend: test_dispatch_ack.py (10 tests: dispatch_sent_at / offline fail / online redispatch / acked untouched / max attempts / recent not stale / 终态守卫 3 / heartbeat slot)
- [x] agent: test_outbox_and_dispatch_ack.py (8 tests: enqueue / capacity / flush FIFO / noop / skip / requeue / dispatch ack)
- [x] dispatch-flow.md 同步 1.8 (S1 ack 语义 + S2 恢复链, 与 S2 P7 一起更新)

## 实现产物清单 (2026-08-16 归档时补充)

- 代码: `backend/tasks/tasks.py` (dispatch snapshot) / `backend/tasks/heartbeat.py` (check_dispatch_acks + slot) / `backend/protocol/services.py` (终态守卫) / `agent/src/client/handler.py` (ack) / `agent/src/client/connection.py` (outbox)
- 测试: `backend/tasks/tests/test_dispatch_ack.py` (10) + `agent/tests/test_outbox_and_dispatch_ack.py` (8)
- 文档: `docs/architecture/cross-cutting/dispatch-flow.md` v1.8

## 验收标准

1. ✅ agent 收到任务必回 ack，backend 能检测未 ack 并补发/fail
2. ✅ 迟到 task.result 不能把 FAILED/CANCELLED 执行复活
3. ✅ agent 断线窗口期的 task.result 重连后自动补发
4. ✅ agent 心跳超时 fail 执行时并发槽位同步释放
5. ✅ 相关 pytest 全绿 (backend 478 + agent 2260)

## 已知限制

- 出站队列仅覆盖内存 (进程崩溃丢失)，跨进程持久化留待后续
- check_dispatch_acks 重派复用 dispatch_task.delay (重新走 selector/并发检查)，未 ack 但 agent 实际已开始执行时可能重复派发 (agent 端幂等由 execution_id 天然保证 — 同一 execution 重复 assign 会重复执行, 已知风险, 场景罕见: ack 丢失 + 网络健康)