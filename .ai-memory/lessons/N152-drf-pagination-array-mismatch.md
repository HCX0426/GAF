---
id: N152
date: 2026-07-09
title: DRF global pagination vs frontend array expectation causes UI white-screen
priority: high
cross_refs:
- backend/scheduler/views.py
- frontend/src/api/scheduler.ts
- frontend/src/pages/Ops/Logs/SpecialtyLogTabs.tsx
- frontend/src/pages/Ops/Monitors/RecoveryLogTab.tsx
- backend/scheduler/tests/test_scheduler.py
tags:
- drf
- pagination
- frontend
- api-contract
- log-center
symptom:
- drf
- pagination
- rawData.some
- TypeError
- white-screen
- log-center
- array
solution: |
  When a DRF ViewSet relies on global DEFAULT_PAGINATION_CLASS but the frontend
  fetch helper and component expect a plain array, the paginated `{count, results}`
  object is passed to Ant Design Table and crashes with `TypeError: rawData.some is not a function`.
  Fix: explicitly set `pagination_class = None` on the ViewSet when the endpoint is
  meant to return an array, or update the frontend to consume `PaginatedResponse<T>`.
  The contract must be explicit and symmetric across backend/frontend/tests.
diff_keywords: ["views", "drf"]
related_files:
- backend/scheduler/views.py
- frontend/src/api/scheduler.ts
- frontend/src/pages/Ops/Logs/SpecialtyLogTabs.tsx
- frontend/src/pages/Ops/Monitors/RecoveryLogTab.tsx
- backend/scheduler/tests/test_scheduler.py
created_by: AI
level: L1
n_id: N152
topic: cross-layer-sync
---


# N152: DRF 全局分页与前端数组期望不匹配导致白屏

## 症状

- 用户点击侧边栏“日志中心”或“6 条日志”后页面白屏。
- 浏览器控制台报错：
  ```
  TypeError: rawData.some is not a function
  ```
- 触发位置：日志中心 > “恢复日志”标签页（`frontend/src/pages/Ops/Logs/SpecialtyLogTabs.tsx`）。

## 根因

1. `backend/config/settings/base.py` 配置了全局 DRF 分页：
   ```python
   REST_FRAMEWORK = {
       "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
       "PAGE_SIZE": 20,
   }
   ```
2. `backend/scheduler/views.py` 的 `RecoveryLogViewSet` 未显式设置 `pagination_class`，因此 list 接口返回：
   ```json
   {
     "count": 6,
     "next": null,
     "previous": null,
     "results": [...]
   }
   ```
3. 前端 `frontend/src/api/scheduler.ts` 中的 `fetchRecoveryLogs()` 声明返回 `Promise<RecoveryLogEntry[]>`。
4. `SpecialtyLogTabs.tsx` 的 `RecoveryLogTab` 直接把响应对象传给 Ant Design Table：
   ```tsx
   const res = await fetchRecoveryLogs();
   setData(res ?? []);
   ```
5. Ant Design Table 内部期望 `dataSource` 是数组，对对象调用 `.some()` 时抛出 `TypeError`，React 错误边界捕获后页面白屏。

## 修复

在 `RecoveryLogViewSet` 上显式禁用分页，使其与前端数组期望一致：

```python
class RecoveryLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RecoveryLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # ← 返回数组而非分页对象
```

备选方案（当需要分页时）：修改前端 `fetchRecoveryLogs()` 返回 `PaginatedResponse<RecoveryLogEntry>`，并在组件中取 `res.results ?? []`。

## 验证

- 后端测试：`pytest backend/scheduler/tests/test_recovery_log_api.py -v` → 10 passed。
- 浏览器验证：Playwright 点击日志中心全部 7 个标签页，无 `rawData.some` 错误。

## 教训

- **不要依赖隐式默认分页**：新增 DRF ViewSet 时，必须明确该接口返回分页对象还是数组。
- **前后端契约必须对称**：后端分页配置、API 返回类型、前端 TS 类型、组件取数方式四者要一致。
- **测试应覆盖真实形状**：如果测试同时兼容两种形状（list 和 paginated dict），说明契约不明确，应通过显式 `pagination_class` 确定一种。
