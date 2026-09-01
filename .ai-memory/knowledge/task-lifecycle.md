---
maintainer: derived-manual
source: backend/tasks/models.py, backend/scheduler/engine.py, worker/src/core/orchestrator.py
load_when:
- 新功能 (任务相关)
- Bug修复 (任务执行异常)
- AI 任务开工
priority: high
symptom:
- kb:task:lifecycle
- task-state-machine
- 任务状态
- task-lifecycle
solution: 8 个状态机 + 5 种转换路径 + 4 个 AI 易错点 (含 N76 跳过 ready, N81 误转 completed)
related_files:
- backend/tasks/models.py
- backend/scheduler/engine.py
- worker/src/core/orchestrator.py
- .ai-memory/meta/auto-kb/pipeline-nodes.md
- .ai-memory/meta/auto-kb/error-codes.md
created_by: AI
generated: 2026-06-16
auto_updated: 2026-06-16
last_manual_edit: 2026-07-20
---
# Task Lifecycle (任务生命周期) - AI 速查

> **适用场景**: AI 写任务相关代码 / 调试任务卡住 / 排查任务状态错乱
> **核心模型**: `Task` (Django model) + `TaskExecution` (执行实例) + `TaskSchedule` (定时)

## 1. 状态机（8 个状态）

```
        ┌────────┐
        │ DRAFT  │ (草稿, 未提交)
        └────┬───┘
             │ submit
             ▼
        ┌────────┐
        │ READY  │ (待执行, 已入队)
        └────┬───┘
             │ schedule
             ▼
        ┌────────┐
        │ RUNNING│ (执行中)
        └────┬───┘
        ┌────┴────┬──────────┬────────┐
        │         │          │        │
        ▼         ▼          ▼        ▼
   ┌─────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │ PAUSED  │ │SUCCESS │ │ FAILED │ │TIMEOUT │
   └────┬────┘ └────────┘ └────────┘ └────────┘
        │ resume
        ▼
   (回到 RUNNING)
```

| 状态 | 含义 | 转换触发 |
|------|------|----------|
| `DRAFT` | 草稿, Pipeline 未填完整 | 用户编辑 |
| `READY` | 待执行, 已入队 (scheduler) | `task.services.submit_task()` |
| `RUNNING` | 执行中, Agent 占用 | `scheduler.engine.dispatch()` |
| `PAUSED` | 暂停, 等待用户恢复 | `task.services.pause_task()` |
| `SUCCESS` | 成功完成 | `TaskExecution.result == SUCCESS` |
| `FAILED` | 失败, 可重试 | `TaskExecution.result == FAILED && retry_count < max` |
| `TIMEOUT` | 超时 (> max_runtime_seconds) | scheduler watchdog |
| `CANCELLED` | 用户取消 | `task.services.cancel_task()` |

## 2. 关键转换路径（5 条主路径）

### 2.1 正常路径 (success)

```
DRAFT → submit → READY → schedule → RUNNING → SUCCESS
  ↑                                       │
  └────────────── retry (N≤3) ────────────┘
```

### 2.2 失败重试 (failure_with_retry)

```
RUNNING → FAILED → retry_check → READY → RUNNING (重试)
                  → retry_count >= max → FAILED (终态)
```

### 2.3 暂停恢复 (pause_resume)

```
RUNNING → pause_request → PAUSED → resume_request → RUNNING
```

### 2.4 超时 (timeout)

```
RUNNING → max_runtime_elapsed → TIMEOUT → notify_admin
```

### 2.5 取消 (cancel)

```
{READY, RUNNING, PAUSED} → cancel_request → CANCELLED (终态)
```

## 3. AI 易错点 (4 条历史教训)

### 3.1 ❌ 跳过 READY 直接 RUNNING (N76)

**错误**: `task.services.submit_task()` 后直接设 `status=RUNNING`, 跳过 `READY` 入队
**后果**: scheduler 不知任务存在, 永远不会 dispatch, 任务永远卡住
**正确**: `submit_task()` 设 `READY`, scheduler watchdog 拉到 `RUNNING`

### 3.2 ❌ 误把 FAILED 转 COMPLETED (N81)

**错误**: retry 逻辑里 `if retry_count >= max: status = COMPLETED`
**后果**: 实际失败的任务被标 SUCCESS, 用户看不到错误, 飞轮 "读侧" 看到假数据
**正确**: 终态用 `FAILED`, `SUCCESS` 只在 result == SUCCESS 时设

### 3.3 ❌ PAUSED 不持久化 (N84)

**错误**: PAUSED 状态只存内存, Agent 重启后丢失
**后果**: Agent 重启后任务回到 RUNNING, 实际窗口已关闭
**正确**: PAUSED 必须落 DB (`Task.status` 字段), Agent 重启时查询并继续 PAUSED

### 3.4 ❌ TIMEOUT 后不通知 (N88)

**错误**: `TIMEOUT` 状态仅设状态, 不发通知
**后果**: 管理员不知道任务超时, 资源 (设备占用) 一直锁住
**正确**: TIMEOUT 转换时调用 `notifications.tasks.send_timeout_alert()`

## 4. 速查表 (Cheatsheet)

| 场景 | 正确 API | 错误 API |
|------|----------|----------|
| 提交任务 | `task.services.submit_task(task_id)` | `task.status = RUNNING` (直接改) |
| 暂停任务 | `task.services.pause_task(task_id)` | `task.status = PAUSED` (直接改) |
| 恢复任务 | `task.services.resume_task(task_id)` | `task.status = RUNNING` (直接改) |
| 取消任务 | `task.services.cancel_task(task_id)` | `task.delete()` (删除而非取消) |
| 标记成功 | `task.services.complete_task(task_id, result)` | `task.status = SUCCESS` (直接改) |
| 标记失败 | `task.services.fail_task(task_id, error)` | `task.status = FAILED` (直接改) |

## 5. 数据库表 (Django models)

```python
# backend/tasks/models.py
class Task(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('READY', 'Ready'),
        ('RUNNING', 'Running'),
        ('PAUSED', 'Paused'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
        ('TIMEOUT', 'Timeout'),
        ('CANCELLED', 'Cancelled'),
    ]
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='DRAFT')
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    max_runtime_seconds = models.IntegerField(default=3600)  # 1 小时
```

## 6. 反思 (Reflection)

- **4 问**: 任务状态错乱 → 看 `Task.status` 字段 + `TaskExecution` 历史
- **常见错误**: 跳过状态机直接改 status 字段 → 必须用 `services/` 层 API
- **陷阱**: PAUSED 不持久化 / TIMEOUT 不通知 → 都有 lessons
- **相关**: pipeline-nodes.md (执行节点) / error-codes.md (错误码) / orchestrator (Agent 侧)
