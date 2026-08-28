---
summary: GAF 任务取消与清理设计
applies_to: ['backend', 'design']
key_decisions:
  - 概述
  - Phase 6.1-6.4 实现完成：SafePointChecker + CleanupManager + MonitorManager.force_stop_all + force-terminate 端点
last_updated: 2026-07-05
---

# GAF 任务取消与清理设计

> 版本：1.2 | 日期：2026-07-05 | 修订：Phase 6.1-6.4 实现完成，状态矩阵更新

## 0. 现实状态（2026-07-05 审计，Phase 6.1-6.4 后更新）

> ✅ **Phase 6.1-6.4 实现完成**：`SafePointChecker`、`CleanupManager`、`MonitorManager.force_stop_all()`、`force-terminate` REST 端点已全部实现。`ResourceLock.release_all_for_task` 仍待补（推后到 ResourceLock 接入 dispatch_task 后）。

| 项 | 文档声称 | 现实代码 | 状态 |
|----|----------|----------|------|
| 取消信号传播 | Server → WebSocket → Agent | `TaskViewSet.cancel` (`backend/tasks/views.py:146-182`) + Agent `MessageHandler.handle_task_cancel` (`agent/src/client/handler.py:322`) | ✅ 一致 |
| `TaskExecutionViewSet.force_terminate` 端点 | POST `/api/v2/tasks/task-executions/{id}/force-terminate/` | `backend/tasks/views.py:340-407`（Phase 6.4）；跳过宽限期，直接标记 `force_terminated` + 发送 WS `task.force_terminate` ——⚠️ 2026-08-28 实查: force_terminate action 已随重构移除（execution_views.py 仅剩 steps/replay/cancel/pause/resume/skip/retry-from-step/node-trace）；强制终止仅经 Celery check_cancel_timeout 超时路径 | ✅ Phase 6.4 完成 |
| `MonitorManager.force_stop_all` | 强制停止所有监控线程 | `agent/src/monitor/manager.py:215-278`（Phase 6.3）；1 秒 join 超时 + 清空规则 + 返回线程是否退出 | ✅ Phase 6.3 完成 |
| `SafePointChecker` 类 | 链式管理器集成取消检查 | `agent/src/core/safe_point.py`（Phase 6.1）；`SafePointChecker` + `TaskCancelledError`；4 个方法：`check()` / `wait_for_safe_point()` / `raise_if_cancelled()` / `reset()` | ✅ Phase 6.1 完成 |
| `CleanupManager` 类 | 资源清理管理器 | `agent/src/core/cleanup.py`（Phase 6.2）；优先级排序清理栈；4 个优先级常量；`register()` / `cleanup()` / `clear()` API | ✅ Phase 6.2 完成 |
| `force_terminate` Celery 任务 | 调用 `MonitorManager.force_stop_all(agent_id)` | `backend/tasks/services/monitor_service.py` 的 `check_cancel_timeout` Celery 任务实现等价功能（10s 超时 → `force_terminated`）；未直接调用 agent 方法，而是依赖 WS 信号 | 🟡 实现等价但路径不同 |
| `ResourceLock.release_all_for_task` | 强制释放设备锁 | **方法不存在**；`ResourceLock` 本身也未接入 `dispatch_task`（见 `resource_lock.py:1-9` docstring） | 🟡 推后（ResourceLock 接入 dispatch_task 后再补） |

### 0.1 实际取消机制（Phase 6.1-6.4 后）

Agent 端 `PipelineEngine` 通过 `cancel_event` 实现取消：
1. Server 发送 `task.cancel` WebSocket 消息
2. Agent `MessageHandler.handle_task_cancel` 调用 `TaskOrchestrator.cancel_task()`
3. `PipelineEngine.execute` 循环检查 `_cancel_event.is_set()`（多处安全点：line 261/275/317/366）
4. 命中安全点（节点边界）时退出循环
5. Agent 回传 `task.cancelled`

**强制终止路径**（Phase 6.4）：
1. Server 端 `TaskExecutionViewSet.force_terminate` 端点接收 POST 请求
2. 立即标记 DB 状态为 `force_terminated`（跳过 10 秒宽限期）
3. 发送 WS `task.force_terminate` 给 agent
4. Agent 收到后调用 `MonitorManager.force_stop_all()`（1 秒超时）+ `CleanupManager.cleanup()` + `pipeline_engine.cancel()`
5. 注：agent 端 WS handler 待接入（当前 `MessageHandler` 只处理 `task.cancel`，未处理 `task.force_terminate`）

**自动超时升级路径**：
- `check_cancel_timeout` Celery 任务（`backend/tasks/services/monitor_service.py`）扫描 `CANCELLED` 状态超过 10 秒的执行，标记为 `force_terminated`
- ⚠️ 当前未注册到 `CELERY_BEAT_SCHEDULE`（P1-3 待办）

---

## 1. 概述

GAF 需要支持任务的优雅取消和资源清理。本设计定义取消信号传播机制、安全点检查、资源清理流程、超时强制终止和取消原因记录方案。

> ✅ **Phase 6.1-6.4 实现完成**：`SafePointChecker`、`CleanupManager`、`MonitorManager.force_stop_all()`、`force-terminate` REST 端点已全部实现。下文保留设计稿作为架构参考，现实实现见 §0。

---

## 2. 取消信号传播（Server → Agent）

### 2.1 传播架构

```
Client (用户点击取消)
    │
    ▼
Server REST API: POST /api/v2/tasks/task-executions/{id}/cancel/
    │
    ▼
TaskService.cancel_execution()
    │
    ├──► 更新数据库状态: running → cancelling
    │
    ├──► WebSocket: task.cancel → Agent
    │         │
    │         ▼
    │    TaskOrchestrator.receive_cancel()
    │         │
    │         ▼
    │    设置 cancel_event
    │         │
    │         ▼
    │    等待安全点 → 执行清理 → 确认取消
    │
    └──► 超时监控 (10秒)
              │
              ▼
         强制终止
```

### 2.2 取消信号定义

```python
from dataclasses import dataclass
from enum import Enum

class CancelReason(str, Enum):
    """取消原因"""
    USER_REQUEST = "user_request"           # 用户主动取消
    TIMEOUT = "timeout"                     # 任务超时
    AGENT_DISCONNECTED = "agent_disconnected"  # Agent 断连
    SYSTEM_SHUTDOWN = "system_shutdown"     # 系统关闭
    DEPENDENCY_FAILED = "dependency_failed" # 依赖任务失败
    RESOURCE_UNAVAILABLE = "resource_unavailable"  # 资源不可用

@dataclass
class CancelSignal:
    """取消信号"""
    task_id: str
    execution_id: str
    reason: CancelReason
    message: str
    timestamp: float
    force: bool = False          # 是否强制终止
    grace_period: float = 10.0   # 宽限期（秒）
```

### 2.3 Server 端取消流程

```python
class TaskService:
    """任务服务"""

    def cancel_execution(self, execution_id: str, reason: CancelReason, message: str = "") -> None:
        """取消任务执行"""
        execution = TaskExecution.objects.get(id=execution_id)

        if execution.status not in ("pending", "running"):
            raise InvalidStateError(f"Cannot cancel execution in state: {execution.status}")

        execution.status = "cancelling"
        execution.cancel_reason = f"{reason.value}: {message}"
        execution.save()

        cancel_signal = CancelSignal(
            task_id=str(execution.task_id),
            execution_id=str(execution_id),
            reason=reason,
            message=message,
            timestamp=time.time(),
        )

        self._send_cancel_to_agent(execution, cancel_signal)
        self._start_force_terminate_timer(execution_id, cancel_signal.grace_period)

    def _send_cancel_to_agent(self, execution: TaskExecution, signal: CancelSignal) -> None:
        """通过 WebSocket 发送取消信号给 Agent"""
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"agent_{execution.agent_id}",
            {
                "type": "task_cancel",
                "task_id": signal.task_id,
                "execution_id": signal.execution_id,
                "reason": signal.reason.value,
                "message": signal.message,
                "force": signal.force,
                "grace_period": signal.grace_period,
            },
        )

    def _start_force_terminate_timer(self, execution_id: str, grace_period: float) -> None:
        """启动强制终止定时器"""
        force_terminate.apply_async(
            args=[execution_id],
            countdown=grace_period,
        )
```

---

## 3. 安全点检查

### 3.1 安全点定义

安全点是任务执行过程中可以安全暂停的位置，确保取消操作不会导致数据不一致或设备状态异常。

| 安全点类型 | 说明 | 示例 |
|-----------|------|------|
| 步骤边界 | 步骤之间 | 步骤 A 完成，步骤 B 未开始 |
| 等待点 | 等待操作期间 | wait / wait_for_template |
| 重试间隔 | 重试等待期间 | 步骤重试的间隔时间 |
| 循环边界 | 循环迭代之间 | loop 的每次迭代开始前 |
| 状态转移 | 状态机转移期间 | 状态转移评估阶段 |

### 3.2 安全点检查实现

```python
class SafePointChecker:
    """安全点检查器"""

    def __init__(self, cancel_event: threading.Event):
        self._cancel_event = cancel_event

    def check(self) -> bool:
        """检查是否收到取消信号"""
        return self._cancel_event.is_set()

    def wait_for_safe_point(self, timeout: float = 5.0) -> bool:
        """等待安全点，返回是否收到取消信号"""
        return self._cancel_event.wait(timeout=timeout)

    def raise_if_cancelled(self) -> None:
        """如果已取消则抛出异常"""
        if self._cancel_event.is_set():
            raise TaskCancelledError("Task cancelled by user")
```

### 3.3 在 ChainManager 中集成

```python
class ChainManager:
    """链式管理器，集成取消检查"""

    def __init__(self, orchestrator: "TaskOrchestrator"):
        self._orchestrator = orchestrator
        self._cancel_event = threading.Event()
        self._safe_point = SafePointChecker(self._cancel_event)

    def execute(self, context: "TaskContext") -> "ChainResult":
        """执行链式任务"""
        step_index = 0
        while step_index < len(self._steps):
            self._safe_point.raise_if_cancelled()

            step = self._steps[step_index]
            result = self._execute_step(step, context)

            if not result.success:
                step_index = self._handle_failure(step, result, step_index)
            else:
                step_index += 1

            self._safe_point.raise_if_cancelled()

        return ChainResult(success=True)

    def cancel(self, reason: str = "") -> None:
        """取消任务"""
        self._cancel_event.set()
        self._cancel_reason = reason
```

### 3.4 在 StateMachine 中集成

```python
class StateMachineExecutor:
    """状态机执行器，集成取消检查"""

    def __init__(self, definition, orchestrator, event_bus):
        self._definition = definition
        self._orchestrator = orchestrator
        self._event_bus = event_bus
        self._cancel_event = threading.Event()
        self._safe_point = SafePointChecker(self._cancel_event)

    def execute(self, context: "ExecutionContext") -> "StateMachineResult":
        """执行状态机"""
        context.current_state = self._definition.initial_state

        while True:
            self._safe_point.raise_if_cancelled()

            termination = self._check_termination(context)
            if termination.terminated:
                return StateMachineResult(
                    success=termination.success,
                    final_state=context.current_state,
                    reason=termination.reason,
                )

            current_node = self._definition.states[context.current_state]
            self._execute_state_action(current_node, context)

            self._safe_point.raise_if_cancelled()

            transition = self._evaluate_transitions(current_node, context)
            if transition:
                self._execute_transition(transition, context)
                context.current_state = transition.to_state

            context.iteration_count += 1

    def cancel(self, reason: str = "") -> None:
        """取消状态机执行"""
        self._cancel_event.set()
```

---

## 4. 资源清理流程

### 4.1 清理清单

| 资源类型 | 清理操作 | 优先级 |
|----------|---------|--------|
| 设备锁 | 释放 | 高 |
| 临时文件 | 删除截图缓存 | 中 |
| 线程 | 停止 MonitorThread | 高 |
| WebSocket 连接 | 保持（不关闭） | 低 |
| 数据库事务 | 提交/回滚 | 高 |
| 内存缓存 | 清理步骤结果缓存 | 中 |

### 4.2 清理管理器

```python
class CleanupManager:
    """资源清理管理器"""

    def __init__(self):
        self._cleanup_stack: list[tuple[int, Callable]] = []

    def register(self, priority: int, cleanup_fn: Callable) -> None:
        """注册清理函数"""
        self._cleanup_stack.append((priority, cleanup_fn))

    def cleanup(self) -> list[str]:
        """执行所有清理操作，返回清理结果"""
        results = []
        sorted_cleanups = sorted(self._cleanup_stack, key=lambda x: x[0], reverse=True)

        for priority, cleanup_fn in sorted_cleanups:
            try:
                cleanup_fn()
                results.append(f"✓ {cleanup_fn.__name__}")
            except Exception as e:
                results.append(f"✗ {cleanup_fn.__name__}: {e}")

        self._cleanup_stack.clear()
        return results
```

### 4.3 任务执行中的清理注册

```python
class TaskOrchestrator:
    """任务编排器"""

    def execute_task(self, task_def: dict) -> str:
        """执行任务"""
        task_id = str(uuid.uuid4())
        cleanup = CleanupManager()

        try:
            device_lock = self._resource_lock.acquire(device_id, task_id)
            cleanup.register(10, lambda: self._resource_lock.release(device_id, task_id))

            monitor_thread = self._monitor_manager.start_monitor(device_id, rules)
            cleanup.register(5, lambda: self._monitor_manager.stop_monitor(device_id))

            temp_dir = self._create_temp_dir(task_id)
            cleanup.register(3, lambda: shutil.rmtree(temp_dir, ignore_errors=True))

            result = self._chain_manager.execute(context)

            return task_id
        except TaskCancelledError:
            cleanup.cleanup()
            raise
        except Exception:
            cleanup.cleanup()
            raise
        finally:
            cleanup.cleanup()
```

---

## 5. 超时强制终止（10秒）

### 5.1 强制终止流程

```
1. 取消信号发送后启动 10 秒定时器
2. Agent 在安全点响应取消 → 正常取消
3. 10 秒内未响应 → 强制终止
   a. 标记执行状态为 force_terminated
   b. 强制释放设备锁
   c. 停止所有监控线程
   d. 记录强制终止原因
```

### 5.2 强制终止实现

```python
from celery import shared_task

@shared_task
def force_terminate(execution_id: str) -> None:
    """强制终止任务执行（Celery 定时任务）"""
    try:
        execution = TaskExecution.objects.get(id=execution_id)
    except TaskExecution.DoesNotExist:
        return

    if execution.status in ("success", "failed", "cancelled"):
        return

    if execution.status == "cancelling":
        execution.status = "force_terminated"
        execution.error_message = "Force terminated: agent did not respond to cancel signal within grace period"
        execution.completed_at = timezone.now()
        execution.save()

        ResourceLock.release_all_for_task(execution_id)
        MonitorManager.force_stop_all(execution.agent_id)

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"agent_{execution.agent_id}",
            {
                "type": "task_force_terminate",
                "execution_id": execution_id,
            },
        )
```

### 5.3 Agent 端强制终止处理

```python
class TaskOrchestrator:
    """Agent 端任务编排器"""

    def on_force_terminate(self, execution_id: str) -> None:
        """处理强制终止信号"""
        if execution_id in self._active_tasks:
            context = self._active_tasks[execution_id]
            context.cancelled = True
            context.cancel_reason = "force_terminated"

            for thread in threading.enumerate():
                if isinstance(thread, MonitorThread):
                    thread.stop()

            self._cleanup_all_resources(execution_id)
```

---

## 6. 取消原因记录

### 6.1 记录格式

```python
@dataclass
class CancelRecord:
    """取消记录"""
    execution_id: str
    cancel_reason: CancelReason
    cancel_message: str
    cancelled_at: float
    cancelled_by: str | None       # 取消操作者
    agent_response_time: float | None  # Agent 响应时间
    cleanup_result: list[str]      # 清理结果
    force_terminated: bool         # 是否被强制终止
```

### 6.2 记录存储

取消记录存储在 `TaskExecution` 模型中：

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | CharField | cancelled / force_terminated |
| `cancel_reason` | CharField | 取消原因编码 |
| `error_message` | TextField | 详细取消信息 |
| `completed_at` | DateTimeField | 取消完成时间 |
| `result_data` | JSONField | 清理结果等附加数据 |

### 6.3 取消历史查询

```python
class CancelHistoryService:
    """取消历史服务"""

    def get_cancel_history(self, task_id: str) -> list[dict]:
        """获取任务的取消历史"""
        executions = TaskExecution.objects.filter(
            task_id=task_id,
            status__in=["cancelled", "force_terminated"],
        ).order_by("-created_at")

        return [
            {
                "execution_id": str(e.id),
                "status": e.status,
                "cancel_reason": e.cancel_reason,
                "error_message": e.error_message,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "duration": str(e.duration) if e.duration else None,
                "result_data": e.result_data,
            }
            for e in executions
        ]

    def get_cancel_statistics(self) -> dict:
        """获取取消统计"""
        total = TaskExecution.objects.filter(
            status__in=["cancelled", "force_terminated"]
        ).count()
        forced = TaskExecution.objects.filter(status="force_terminated").count()

        reason_counts = {}
        for reason in CancelReason:
            count = TaskExecution.objects.filter(
                cancel_reason__startswith=reason.value
            ).count()
            if count > 0:
                reason_counts[reason.value] = count

        return {
            "total_cancels": total,
            "force_terminates": forced,
            "force_terminate_rate": round(forced / max(total, 1) * 100, 1),
            "by_reason": reason_counts,
        }
```

---

## 7. 取消流程时序图

```
Client          Server              Agent
  │               │                   │
  │  POST cancel  │                   │
  │──────────────►│                   │
  │               │  status=cancelling │
  │               │  ───────┐         │
  │               │         │ DB      │
  │               │  ◄──────┘         │
  │               │                   │
  │               │  task.cancel      │
  │               │──────────────────►│
  │               │                   │  set cancel_event
  │               │                   │  ───────┐
  │               │                   │         │
  │               │                   │  ◄──────┘
  │               │                   │
  │               │  [等待安全点]      │
  │               │                   │
  │               │                   │  执行清理
  │               │                   │  ───────┐
  │               │                   │         │
  │               │                   │  ◄──────┘
  │               │                   │
  │               │  task.cancelled   │
  │               │◄──────────────────│
  │               │                   │
  │               │  status=cancelled │
  │               │  ───────┐         │
  │               │         │ DB      │
  │               │  ◄──────┘         │
  │               │                   │
  │  200 OK       │                   │
  │◄──────────────│                   │
  │               │                   │
```

如果 10 秒内 Agent 未响应：

```
Server                              Agent
  │                                   │
  │  [10秒超时]                        │
  │                                   │
  │  status=force_terminated          │
  │  ───────┐                         │
  │         │ DB                      │
  │  ◄──────┘                         │
  │                                   │
  │  task.force_terminate             │
  │──────────────────────────────────►│
  │                                   │  强制停止所有线程
  │                                   │  释放所有资源
```
