---
spec: 2026-08-08-td349-service-layer-test-coverage
title: TD-349 Service 层测试覆盖补全 Spec
status: active
created: 2026-08-08
estimated_effort: 0.5 day
risk: low
---

# TD-349 Service 层测试覆盖补全 Spec

## 1. 背景与动机

### 实际状态核查

TD-349 登记时基于早期架构审查的推测，认为 Service 层仍有 2 条路径未提取。**实际代码核查后，Service 层提取已在 Phase 1 完成**：

| 维度 | 预期状态 | 实际状态 |
| :--- | :--- | :--- |
| `SchedulerService` | 不存在 | ✅ 已存在，4 个方法，`scheduler/views.py` 全部委托 |
| `DeviceService` | 不存在 | ✅ 已存在，健康检查 + 状态更新 + ADB 路径，`agents/views.py` 全部委托 |
| `TaskService` | 存在 | ✅ 已存在，`dispatch()` / `cancel()` 方法 |
| 测试覆盖 | 无 | ✅ 11 个测试在 `backend/tasks/tests/test_service.py` |

### 仍需补全的缺口

| Service 方法 | 是否有测试 | 文件 |
| :--- | :--- | :--- |
| `SchedulerService.get_execution_plan()` | ✅ 2 个测试 | `test_service.py:107-134` |
| `SchedulerService.validate_time_window()` | ✅ 2 个测试 | `test_service.py:136-184` |
| **`SchedulerService.get_today_schedule()`** | ❌ 无测试 | — |
| **`SchedulerService.list_executions()`** | ❌ 无测试 | — |
| `DeviceService.check_single_device_health()` | ✅ 2 个测试 | `test_service.py:191-228` |
| `DeviceService.update_device_status()` | ✅ 2 个测试 | `test_service.py:230-253` |
| **`DeviceService.check_all_devices_health()`** | ❌ 无测试 | — |

## 2. 问题定义

3 个 Service 方法缺乏单元测试覆盖，尽管不影响现有功能，但存在回归风险：

- `SchedulerService.get_today_schedule()` — 被 `today_schedule_view` 调用，负责生成今日无人值守日程
- `SchedulerService.list_executions()` — 被 `executions_view` 调用，负责分页查询执行历史
- `DeviceService.check_all_devices_health()` — 被 `health_check` action 调用，负责遍历所有设备执行健康检查

## 3. 目标

为上述 3 个方法各补 ≥2 个单元测试，覆盖正常路径和边界条件，使 Service 层测试覆盖率达到 100%。

## 4. 实施计划

### Task 1: 补 `SchedulerService.get_today_schedule()` 测试

**现有代码**（[scheduler_service.py L59-L95](file:///d:/code/GAF/backend/scheduler/services/scheduler_service.py#L59)）：

```python
@staticmethod
def get_today_schedule() -> dict:
    today = timezone.now().date()
    plans = generate_execution_plan(days=1)
    today_items = []
    for plan in plans:
        item = {
            "id": hash(...) % 1000000,
            "device_id": plan.get("device_id"),
            # ...
            "status": "pending",
            "progress": 0,
            "error_message": None,
        }
        today_items.append(item)
    return {
        "date": today.isoformat(),
        "total": len(today_items),
        "completed": 0,
        "failed": 0,
        "items": today_items,
    }
```

**测试用例**（追加到 `test_service.py::TestSchedulerService`）：

1. `test_get_today_schedule_returns_correct_structure` — mock `generate_execution_plan` 返回 2 个计划，验证返回结构包含 `date`、`total`、`items` 等字段
2. `test_get_today_schedule_empty_plan` — mock `generate_execution_plan` 返回空列表，验证 `total=0`、`items=[]`

### Task 2: 补 `SchedulerService.list_executions()` 测试

**现有代码**（[scheduler_service.py L97-L164](file:///d:/code/GAF/backend/scheduler/services/scheduler_service.py#L97)）：

```python
@staticmethod
def list_executions(page=1, page_size=20) -> dict:
    from tasks.models import TaskExecution
    status_map = { ... }
    qs = TaskExecution.objects.select_related("task").prefetch_related("task__schedules").order_by("-created_at")
    total = qs.count()
    offset = (page - 1) * page_size
    items = qs[offset:offset + page_size]
    results = [...]
    return {"count": total, "page": page, "page_size": page_size, "results": results}
```

**测试用例**（追加到 `test_service.py::TestSchedulerService`）：

1. `test_list_executions_default_page` — mock `TaskExecution.objects` 返回 2 条记录，验证返回结构含 `count`、`page`、`results`
2. `test_list_executions_empty` — mock `TaskExecution.objects` 返回空，验证 `count=0`、`results=[]`

### Task 3: 补 `DeviceService.check_all_devices_health()` 测试

**现有代码**（[device_service.py L269-L282](file:///d:/code/GAF/backend/agents/services/device_service.py#L269)）：

```python
def check_all_devices_health(self) -> list[dict]:
    results: list[dict] = []
    devices = Device.objects.select_related("agent").all()
    for device in devices:
        result = self.check_single_device_health(device)
        results.append(result)
    return results
```

**测试用例**（追加到 `test_service.py::TestDeviceService`）：

1. `test_check_all_devices_health_returns_list` — mock `Device.objects.all` 返回 2 个 device，mock `check_single_device_health` 返回预设结果，验证返回列表长度 = 2
2. `test_check_all_devices_health_empty` — mock `Device.objects.all` 返回空 QuerySet，验证返回空列表

## 5. 测试与验收方案

### 运行方式

```powershell
D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/tasks/tests/test_service.py -p no:django -o addopts="" -v
```

### 验收标准

- `TestSchedulerService` 现有 4 个 + 新增 4 个 = **8 个测试全部通过**
- `TestDeviceService` 现有 4 个 + 新增 2 个 = **6 个测试全部通过**
- 3 个新增方法各覆盖 ≥2 个测试用例（正常路径 + 边界条件）
- 测试不依赖真实数据库（使用 `unittest.mock.patch`）

## 6. 风险与缓解

| 风险 | 缓解措施 |
| :--- | :--- |
| `list_executions` 依赖 `TaskExecution.objects` 复杂查询链 | mock `select_related` / `prefetch_related` 链式调用 |
| `check_all_devices_health` 依赖 `check_single_device_health` | mock 内部方法，只测遍历逻辑 |
| pytest-django 插件加载慢 | 加 `-p no:django -o addopts=""` 禁用 |