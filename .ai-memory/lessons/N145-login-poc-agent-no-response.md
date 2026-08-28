---
source: GAF/.ai-memory/lessons/N145-login-poc-agent-no-response.md
load_when: [pipeline.execute timeout, agent heartbeat ok but execution pending, channel layer message not delivered, WebSocket handler stuck, task.result not received, TaskExecution status stuck pending]
priority: high
symptom: [kb:lesson:n145, pipeline-execute-pending, agent-heartbeat-but-no-execution, execution-stuck-pending, task-result-not-received, consumer-only-ack-no-db-update]
solution: N145 L1 已修复 — backend _handle_task_result 之前只发 ACK 不更新 TaskExecution,导致 execution 永远 pending。修复:加 database_sync_to_async 包裹的 _db_update_execution_result,设置 status/completed_at/duration/error_message/started_at。验证:WebSocket 直测 execution 34 pending→failed,backend log 确认 "任务结果" + "TaskExecution 已更新"。完整根因链 3 个独立问题:(1) BD2 窗口最小化→PrintWindow 截不到图 (主因,已临时解决);(2) backend consumer 不更新 DB (次因,本 L1 修复);(3) 模板匹配置信度 0.0894<0.8 (三因,登记 TD)。Agent task.result 发送问题 (多 agent consumer 实例 / send_message 异常静默吞掉) 登记为独立 TD。
diff_keywords: ["consumers", "handler", "connection", "views", "models", "pipeline.execute", "timeout", "agent", "heartbeat", "but", "execution", "pending"]
related_files:
  - backend/protocol/consumers.py
  - agent/src/client/handler.py
  - agent/src/client/connection.py
  - backend/tasks/views.py
  - backend/tasks/models.py
created_by: AI
date: 2026-07-05
generated: 2026-07-05
level: L1
n_id: N145
topic: agent-protocol
---


# N145: R37-P2 C2 — login PoC agent 未响应 + execution 永远 pending (L1 已修复)

> **触发**: "语法 + 1 任务 PoC 验证" (用户要求 JSON 语法验证 + login PoC 跑通作 PoC)
> **时间**: 2026-07-05 | **commit**: `-` (C2 PoC), L1 修复 commit (本提交)
> **影响**: R37-P2 C2 login PoC timeout,execution 一直 pending
> **状态**: ✅ L1 已修复 + 已验证 (backend consumer 端); ⚠️ Agent task.result 发送问题登记为独立 TD

## 1. 问题 (Problem)

R37-P2 C2.2 login PoC 端到端验证失败:

- Pipeline 创建成功 (id=5)
- execute API 调用成功 (execution_id=25/29/30/31/32/33/34, status=202)
- agent heartbeat 正常
- 但 execution status 一直 pending → timeout

调用链:
```
POST /api/v2/tasks/pipelines/{id}/execute/ (device_id=17)
  → PipelineViewSet.execute
  → channel layer send "pipeline.execute"
  → agent WebSocket receive
  → handler.handle_pipeline_execute
  → spawn daemon thread → orchestrator.execute_pipeline(graph_data)
  → (agent) send task.result
  → (backend) _handle_task_result  ← ❌ 只发 ACK,不更新 TaskExecution
```

## 2. 根因 (Root Cause) — 3 个独立问题

### 2.1 主因: BD2 窗口最小化 (已临时解决)

BD2 窗口最小化 (iconic=True, client rect 0x0) → PrintWindow 截不到图 → pipeline failed。
前会话已恢复窗口 (取消最小化),截图成功。

### 2.2 次因: backend consumer 不更新 DB (本 L1 修复) ✅

`backend/protocol/consumers.py::_handle_task_result` 之前只发 ACK,不更新 TaskExecution 状态:

```python
# 修复前 (只发 ACK):
async def _handle_task_result(self, frame):
    payload = frame.get("payload", {})
    execution_id = payload.get("execution_id", "")
    # ... 只记日志 + 发 ACK,不更新 DB
    ack = serialize_frame(msg_type=MessageType.EVENT_ACK, ...)
    await self.send(text_data=ack)
```

导致 execution 永远 pending,即使 agent 正确发送了 task.result。

### 2.3 三因: 模板匹配置信度低 (登记 TD)

模板匹配 confidence=0.0894 (或 0.0811) 远低于阈值 0.8 (pipeline 数据问题,模板图与实际截图不匹配)。与 L1 修复无关,登记为 TD。

### 2.4 附带发现: Agent task.result 发送问题 (登记 TD)

端到端测试时发现:agent 执行了 pipeline 并 log "Pipeline 执行失败",但 backend 没收到 task.result (只有 task.progress)。
可能原因:
1. 多 agent consumer 实例 (backend agent manager 重启 agent 时没杀旧进程,导致 2-3 个 agent 同时连接)
2. agent `send_message` 异常被 `run_coroutine_threadsafe` 的 Future 静默吞掉 (无 `add_done_callback` 记录异常)
3. WebSocket 断开但 agent 未检测到 (主循环未 await 时 ConnectionClosed 不触发)

这是独立的 agent 端问题,不属于 N145 L1 (backend 端) 修复范围。登记为 TD。

## 3. 修复 (Fix) — L1

修改 `backend/protocol/consumers.py`:

### 3.1 imports (line 9, line 26)

```python
from datetime import timedelta  # line 9 (新增)
from tasks.models import TaskExecution  # line 26 (新增)
```

### 3.2 `_handle_task_result` (line 373-413) — 收到 task.result 后更新 DB

```python
async def _handle_task_result(self, frame):
    payload = frame.get("payload", {})
    execution_id = payload.get("execution_id", "")
    success = bool(payload.get("success", False))
    elapsed_time = payload.get("elapsed_time", 0)
    error_msg = payload.get("error_msg", "")
    result_data = payload.get("data", {}) or {}

    logger.info("任务结果: agent_id=%s, execution_id=%s, success=%s, elapsed=%ss, trace_id=%s",
                self.agent_id, execution_id, success, elapsed_time, frame["trace_id"])

    # Update TaskExecution record (N145 L1 fix)
    if execution_id:
        await self._db_update_execution_result(
            execution_id=execution_id, success=success,
            elapsed_time=elapsed_time, error_msg=error_msg,
            result_data=result_data,
        )

    ack = serialize_frame(msg_type=MessageType.EVENT_ACK, ...)
    await self.send(text_data=ack)
```

### 3.3 `_db_update_execution_result` (line 415-460) — `@database_sync_to_async` 包裹的 sync ORM

```python
@database_sync_to_async
def _db_update_execution_result(self, *, execution_id, success, elapsed_time, error_msg, result_data):
    try:
        execution = TaskExecution.objects.get(pk=execution_id)
    except (TaskExecution.DoesNotExist, ValueError, TypeError):
        logger.warning("task.result: execution_id=%s 不存在或无效, 跳过状态更新", execution_id)
        return

    now = django_timezone.now()
    execution.status = TaskExecution.Status.SUCCESS if success else TaskExecution.Status.FAILED
    execution.completed_at = now
    try:
        seconds = float(elapsed_time) if elapsed_time else 0.0
    except (TypeError, ValueError):
        seconds = 0.0
    execution.duration = timedelta(seconds=seconds)

    if success:
        execution.result_data = result_data
        execution.error_message = ""
    else:
        execution.error_message = error_msg or "未知错误"

    if not execution.started_at:
        execution.started_at = now - timedelta(seconds=seconds)

    execution.save()
    logger.info("TaskExecution 已更新: id=%s, status=%s, duration=%ss", execution_id, execution.status, seconds)
```

## 4. 验证 (Verification) — L1

### 4.1 直接 DB 测试 (`临时验证脚本 (已删除)`)

execution 30 pending → failed,所有字段正确:
- status: pending → failed ✅
- completed_at: None → 2026-07-05 14:18:16 UTC ✅
- started_at: None → 2026-07-05 14:18:16 UTC ✅
- duration: None → 0:00:00.125000 ✅
- error_message: "" → "节点 click_start_game 执行失败: 模板匹配置信度 0.0894 低于阈值 0.8" ✅

### 4.2 WebSocket 端到端测试 (`临时验证脚本 (已删除)`)

用 websockets 库直连 backend,模拟 agent 发送 task.result:
- execution 34 pending → failed ✅
- backend log: `任务结果: agent_id=DESKTOP-SEOMBNL-local, execution_id=34, success=False, elapsed=0.125s` ✅
- backend log: `TaskExecution 已更新: id=34, status=failed, duration=0.125s` ✅
- backend 返回 event.ack ✅

### 4.3 Agent 端 task.result 发送问题 (未解决,登记 TD)

agent 执行 pipeline 并 log "Pipeline 执行失败",但 backend 没收到 task.result (只有 task.progress)。
这是独立的 agent 端问题,不影响 backend L1 修复的正确性 (已通过 4.2 WebSocket 直测验证)。

## 5. 教训 (Lesson)

- **consumer 处理上行消息必须更新 DB**: 不能只发 ACK,否则状态永远卡住
- **`database_sync_to_async` 是 async consumer 调用 sync ORM 的标准模式**: 已有 `_db_update_heartbeat` 等方法使用
- **端到端验证受阻时,用 WebSocket 直测隔离问题**: 当 agent 端有问题时,用 websockets 库直连 backend 测试,可隔离 backend 修复的正确性
- **多 agent consumer 实例问题**: backend agent manager 重启 agent 时没杀旧进程,导致多个 agent 同时连接,group_send 投递给所有 consumer (登记 TD)
- **`run_coroutine_threadsafe` 异常静默吞掉**: agent `_send_to_server` 用此调度发送,异常被 Future 吞掉,需加 `add_done_callback` 记录异常 (登记 TD)

## 6. 后续 (Follow-up)

### 6.1 已完成 (L1)

- ✅ backend `_handle_task_result` 加 DB 更新
- ✅ 直接 DB 测试通过
- ✅ WebSocket 端到端测试通过
- ✅ 5 层分发

### 6.2 登记 TD (后续 Phase)

- **TD-1**: 模板匹配 confidence 低 (0.0894 < 0.8) — pipeline 数据问题,模板图需更新
- **TD-2**: Agent task.result 发送问题 — `send_message` 异常静默吞掉,需加 `add_done_callback`
- **TD-3**: Backend agent manager 重启 agent 时没杀旧进程 — 导致多 agent consumer 实例
- **TD-4**: BD2 窗口最小化检测 + 自动恢复 — 主因,已临时解决,根治方案在 R37-P2 C6
