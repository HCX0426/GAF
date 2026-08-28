---
spec_id: spec-2026-08-16-s2-recovery-link-wiring
title: S2 恢复链接线接线 (reassign 补派发 / device.command 转发 / 语义动作落地 / sleep 移出 signal / freeze beat / timeout)
status: ✅ 已归档 (docs/specs/archived/2026-08/2026-08-16-s2-recovery-link-wiring.md)
created: 2026-08-16
task_type: refactor
applies_to: [backend, scheduler, protocol]
---

# S2 — 恢复链接线接线

> 来源：2026-08-16 AI 大脑 + 工作流全面评估 Phase 1（S2）。评估结论：P-020-B 恢复引擎（ActionChain + 5 层 handle_*）结构完整，但**动作执行结果没有真正接线到执行链路**——reassign 不补派发、device.command 无 consumer 转发、语义动作返回假 success、signal 回调同步 sleep、freeze 检测无 beat、timeout_seconds 未实现。恢复动作"看起来执行了"，实际是死代码路径。
>
> **用户决策（2026-08-16 已确认）**：S2-2.7 agent 端界面恢复（yaml 状态机）单独排期，本 Phase 只接 backend 侧（2.1-2.6）。

## 阶段状态表

| 阶段 | 内容 | 状态 | 完成时间 | commit hash |
|------|------|------|---------|-------------|
| P1 | reassign 补派发 (dispatch_task 重新派发) | ✅ | 2026-08-16 | - |
| P2 | device.command backend 转发 (consumer 路由方法) | ✅ | 2026-08-16 | - |
| P3 | 语义动作落地 (retry 重置 step / 其余诚实降级) | ✅ | 2026-08-16 | - |
| P4 | sleep 移出 signal (on_commit 回调不阻塞) | ✅ | 2026-08-16 | - |
| P5 | detect_app_freeze 注册 beat | ✅ | 2026-08-16 | - |
| P6 | ActionSpec.timeout_seconds 实现 | ✅ | 2026-08-16 | - |
| P7 | 测试 + 文档同步 | ✅ | 2026-08-16 | - |

## 任务清单

### P1: reassign 补派发

- [x] `_action_reassign` 换 agent 后调用 `dispatch_task.delay(execution.id)` 重新派发（当前只改 agent + 重置 step，任务永远卡 PENDING）
- [x] reassign 仅在 execution 非终态时派发（防 FAILED/CANCELLED 执行被重新激活）

### P2: device.command backend 转发

- [x] consumer 添加 `device_command(event)` 方法（Channels 把 group_send `{'type': 'device.command'}` 路由到此处），serialize 成 WS 帧发给 agent
- [x] 缺失时 Channels 静默丢弃 → 恢复动作"成功"但 agent 永远收不到（同 pipeline_execute 失败模式）

### P3: 语义动作落地

- [x] `_action_semantic` 的 retry: 重置对应 ExecutionStep 为 PENDING（若其 task_result 非终态）→ 使下游 retry_pending_executions / 重新调度可恢复
- [x] skip/restart/switch_account: 无法在 backend 侧真正执行的，改为显式 error 返回（诚实降级，不返回假 success）；能在 backend 落地的落地（skip → 标记 step SKIPPED）
- [x] 涉及 ExecutionStep 的语义动作保持防递归（不改 signal 触发）

### P4: sleep 移出 signal

- [x] `handle_step_failure` 内 `time.sleep(min(wait_time, 60))` 移除（on_commit 回调同步 sleep 阻塞 worker/请求线程）
- [x] 保留指数退避语义：将 wait 改为 ChainStepResult 的延迟提示字段，由调用方（Celery task）决定是否 sleep

### P5: detect_app_freeze 注册 beat

- [x] `config/celery.py` beat_schedule 注册 `detect-app-freeze`（60s，`scheduler.tasks.detect_app_freeze`）
- [x] imports 增加 `scheduler.tasks`（或确认 autodiscover 已覆盖）

### P6: ActionSpec.timeout_seconds 实现

- [x] `_execute_single_action` 用 `time.monotonic` + 循环检查实现 per-attempt 超时（同步阻塞型动作如 ADB 命令调用无法中断，用信号/超时检查兜底）
- [x] 超时后返回 ChainStepResult(success=False, error="timeout after Ns")

### P7: 测试 + 文档

- [x] reassign 派发测试（换 agent 后 dispatch_task.delay 被调用；终态 execution 不派发）
- [x] consumer device_command 转发测试（group_send → agent 收到 WS 帧）
- [x] 语义动作 retry/skip 测试
- [x] sleep 移除测试（handle_step_failure 不再 sleep）
- [x] timeout 测试（max_retries 循环内超时返回失败结果）
- [x] dispatch-flow.md 同步（S1 ack 语义 + S2 恢复链一起更新）

## 实现产物清单 (2026-08-16 归档时补充)

- 代码: `backend/scheduler/recovery_engine.py` (reassign 补派发 / sleep 移出 signal / timeout) / `backend/protocol/services.py` (语义动作落地) / `backend/protocol/consumers.py` (device.command 转发) / `backend/config/celery.py` (detect-app-freeze + check-dispatch-acks + cleanup-stale-sessions 三条 beat)
- 测试: `backend/scheduler/tests/test_recovery_link_wiring.py` (新增) + `backend/protocol/tests/test_protocol.py` + `test_p048_device_command_result.py`
- 文档: `docs/architecture/cross-cutting/dispatch-flow.md` v1.8

## 验收标准

1. reassign 后任务不再卡 PENDING（dispatch_task 重新派发到新 agent）
2. device.command 帧能到达 agent（不再被 Channels 静默丢弃）
3. retry/skip 语义动作有真实 DB 效果；无法落地的动作显式报错而非假 success
4. signal on_commit 回调不阻塞（无 time.sleep）
5. detect_app_freeze 按 beat 周期运行
6. timeout_seconds 生效
7. 相关 pytest 全绿

## 已知限制

- agent 端界面恢复（yaml 状态机）单独排期（用户决策），本 spec 只做 backend 侧
- device.command 到达 agent 后，agent 端具体执行逻辑（重启模拟器/重连 ADB 等）依赖 2.7 排期