# TD-351: TaskExecution 大表归档策略

> **关联 TD**: TD-351 (TaskExecution 大表无归档策略，长期运行拖慢查询)
> **来源**: `docs/tech-debt/active.md` TD-351
> **状态**: 🔧 待修 → 🚧 进行中
> **优先级**: P2
> **登记时间**: 2026-08-08

---

## 1. 问题描述

### 1.1 现状

`TaskExecution` 表持续追加，无定时归档机制。该表存储每次任务执行的完整记录，包含 `log`（大文本）、`result_data`（JSON）、`execution_snapshot`（JSON）等重字段。

### 1.2 具体问题

| 问题 | 描述 | 影响 |
|------|------|------|
| **无归档机制** | 所有执行记录永久保留在 `tasks_taskexecution` 表 | 数月后累积数万行，拖慢查询 |
| **重字段膨胀** | `log` 大文本 + `result_data`/`execution_snapshot` JSON 占用大量空间 | 全表扫描 I/O 增加 |
| **select_for_update 慢** | `dispatch_task` 中 `select_for_update` 扫描全表 | PENDING 状态的旧记录也被扫描 |
| **列表 API 慢** | `TaskExecutionViewSet` 默认返回所有记录 | 前端加载历史记录变慢 |
| **备份恢复慢** | 大表延长备份窗口和恢复时间 | 运维成本增加 |

### 1.3 根因

`TaskExecution` 模型设计时未考虑生命周期管理，无 `is_archived` 字段，无定期清扫任务。

---

## 2. 修复方案

### 2.1 架构概览

采用**原地归档**（in-place archiving）而非新建归档表，避免数据迁移和跨表查询：

```
修改:
  backend/tasks/models.py        ← 加 is_archived + archived_at 字段
  backend/tasks/migrations/      ← 新增 migration 0055
  backend/tasks/tasks.py         ← 新增 archive_old_executions 任务
  backend/tasks/execution_views.py ← 默认排除归档记录，加 archived 查询参数
  backend/config/celery.py       ← beat_schedule 注册周级归档任务
  backend/tasks/tests/           ← 新增测试
```

### 2.2 模型变更

在 `TaskExecution` 中新增 2 个字段：

```python
is_archived = models.BooleanField(
    default=False,
    db_index=True,
    verbose_name='已归档',
    help_text='标记该执行为已归档状态，默认查询会过滤',
)
archived_at = models.DateTimeField(
    null=True,
    blank=True,
    verbose_name='归档时间',
    help_text='记录被归档的时间戳',
)
```

### 2.3 归档策略

- **触发**: Celery Beat 每周日凌晨 4:00 执行
- **条件**: `completed_at < 30 天前` AND `status` 为终态 (SUCCESS/FAILED/CANCELLED/FORCE_TERMINATED) AND `is_archived=False`
- **操作**:
  1. 设置 `is_archived=True`, `archived_at=timezone.now()`
  2. 清理 `log` 字段（大文本，日志已写入文件系统）
  3. 保留 `result_data` 和 `execution_snapshot`（便于历史查询）
- **幂等性**: 重复执行不会重复归档（WHERE `is_archived=False`）

### 2.4 API 变更

**默认行为**: `TaskExecutionViewSet` 的 `get_queryset()` 默认排除 `is_archived=True` 的记录

**查询参数**: 支持 `?include_archived=true` 参数，返回所有记录（含归档）：
```python
def get_queryset(self):
    qs = TaskExecution.objects.all().order_by("-created_at")
    include_archived = self.request.query_params.get("include_archived", "false").lower() == "true"
    if not include_archived:
        qs = qs.filter(is_archived=False)
    # Non-admin users see only their own executions
    if self.request.user.role != "admin":
        qs = qs.filter(triggered_by=self.request.user)
    return qs
```

### 2.5 Celery Beat 注册

在 `backend/config/celery.py` 中注册：

```python
'archive-old-executions': {
    'task': 'tasks.tasks.archive_old_executions',
    'schedule': crontab(hour=4, minute=0, day_of_week=0),  # 每周日凌晨 4:00
},
```

---

## 3. 任务清单

### Task 1: 模型变更 + 迁移

- [ ] 1.1 在 `TaskExecution` 模型中新增 `is_archived` + `archived_at` 字段
- [ ] 1.2 生成 migration 0055
- [ ] 1.3 验证：迁移后现有数据不受影响，新记录默认 `is_archived=False`

### Task 2: 归档任务

- [ ] 2.1 在 `backend/tasks/tasks.py` 中实现 `archive_old_executions` Celery 任务
- [ ] 2.2 任务逻辑：筛选终态 + `completed_at < 30天前` + `is_archived=False`
- [ ] 2.3 归档操作：设置 is_archived=True, archived_at=now(), 清理 log 字段
- [ ] 2.4 返回归档统计（归档数、清理字段数、耗时）
- [ ] 2.5 在 `beat_schedule` 中注册（每周日凌晨 4:00）

### Task 3: API 默认过滤

- [ ] 3.1 修改 `TaskExecutionViewSet.get_queryset()` 默认排除 `is_archived=True`
- [ ] 3.2 支持 `?include_archived=true` 查询参数
- [ ] 3.3 验证：列表 API 默认不返回归档记录；传参后返回全部

### Task 4: 测试

- [ ] 4.1 测试归档任务：正常归档、跳过未完成记录、跳过已归档记录、幂等性
- [ ] 4.2 测试 API 过滤：默认排除、include_archived 参数
- [ ] 4.3 测试迁移：字段添加后不破坏现有数据

---

## 4. 验证标准

| # | 验证项 | 期望 | 验证方式 |
|---|--------|------|----------|
| 1 | 迁移后 `TaskExecution` 含 `is_archived` + `archived_at` | 字段存在，默认 False | 代码审查 |
| 2 | `archive_old_executions` 归档 30 天前的终态记录 | 归档数 > 0，`is_archived=True` | pytest |
| 3 | 未完成记录不被归档 | PENDING/RUNNING 记录保持 `is_archived=False` | pytest |
| 4 | 已归档记录不被重复归档 | 幂等性：第二次调用归档数为 0 | pytest |
| 5 | 列表 API 默认不返回归档记录 | response 中无 `is_archived=True` 的记录 | pytest |
| 6 | `?include_archived=true` 返回全部记录 | 含归档记录 | pytest |
| 7 | 归档后 `log` 字段被清空 | `archive.log == ""` | pytest |
| 8 | 归档不阻塞 `dispatch_task` | 归档任务使用独立 transaction | 代码审查 |

---

## 5. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/tasks/models.py` | 修改 | 加 is_archived + archived_at 字段 |
| `backend/tasks/migrations/0055_*.py` | 新增 | 迁移文件 |
| `backend/tasks/tasks.py` | 修改 | 加 archive_old_executions 任务 |
| `backend/tasks/execution_views.py` | 修改 | 默认过滤归档记录，支持 include_archived |
| `backend/config/celery.py` | 修改 | 注册 archive-old-executions beat |
| `backend/tasks/tests/test_archive_executions.py` | 新增 | 归档策略测试 |

---

## 6. 测试计划

### 测试文件: `backend/tasks/tests/test_archive_executions.py`

| # | 测试名 | 验证点 |
|---|--------|--------|
| 1 | `test_archives_old_completed` | 30 天前的 SUCCESS 记录被归档 |
| 2 | `test_skips_recent_completed` | 1 天前的 SUCCESS 记录不被归档 |
| 3 | `test_skips_pending` | PENDING 记录不被归档 |
| 4 | `test_skips_running` | RUNNING 记录不被归档 |
| 5 | `test_idempotent` | 第二次调用归档数为 0 |
| 6 | `test_clears_log` | 归档后 log 字段被清空 |
| 7 | `test_api_excludes_archived_by_default` | 列表 API 默认不返回归档记录 |
| 8 | `test_api_include_archived` | `?include_archived=true` 返回全部 |

```bash
# 运行测试
D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/tasks/tests/test_archive_executions.py -v --no-header

# 回归测试（仅 backend）
D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/tasks/ -v --no-header --durations=10
```

---

## 7. 与现有 cleanup_old_archives 的关系

现有 `gaf_core.tasks.cleanup_old_archives` 处理文件级清理（tar.gz 归档包、debug 目录），本 TD-351 处理 DB 级归档（TaskExecution 记录标记）。两者互补不冲突：

- `cleanup_old_archives`: 每天凌晨 3:30 清理 30 天前的文件归档
- `archive_old_executions`: 每周日凌晨 4:00 归档 30 天前的 DB 记录

---

## 8. 已知限制

- 归档采用软标记（`is_archived=True`）而非物理删除，保留历史数据可查
- 归档后 `log` 字段被清空，但日志文件仍保留在文件系统（由 `cleanup_old_archives` 管理）
- 首次归档可能处理大量历史记录，建议在低峰期执行