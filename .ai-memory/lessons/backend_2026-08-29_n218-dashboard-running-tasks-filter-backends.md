---
date: 2026-08-29
symptom: [dashboard-running-tasks-wrong, status-filter-ignored, filter-backends-missing, monitor-metric-unverified, wrong-count-shown]
solution: DRF ViewSet 若缺 filter_backends/filterset_fields, query 参数被静默忽略且无报错 — 前端统计类卡片(运行任务/未读等)必须核对 API 实际行为(带与不带过滤参数各测一次), 并对呈现的数字做"合理性断言"(无任务时不运行任务≈0)
related_files:
  - backend/tasks/execution_views.py
  - frontend/src/pages/Dashboard/index.tsx
created_by: AI
priority: high
n_id: N218
diff_keywords: ["filter_backends", "filterset_fields", "status", "task-executions", "运行任务", "DjangoFilterBackend"]
---

# 工作台"运行任务"恒显全表数：ViewSet 缺 filter_backends 静默忽略 query 参数

## 症状（2026-08-29, 用户反馈"一个任务都没跑，工作台却显示运行任务 90 多个"）

用户明确没有运行任何任务，工作台"运行任务"卡片却显示 91。DB 实测 `TaskExecution` 全表 91 条（62 success / 26 failed / 3 cancelled / **running 0**）。前端 `fetchExecutions({ status: 'running' })` 请求 `/tasks/task-executions/?status=running`，**API 返回 count=91**——与不带参数完全一致。

## 根因

`TaskExecutionViewSet extends ReadOnlyModelViewSet`，但类上**没有任何 `filter_backends` / `filterset_fields`**。DRF 对 ViewSet 未配置过滤时，`?status=running` 这类 query 参数**被静默忽略**（不报错、不 400），返回全 queryset。前端统计卡片自以为"拿到了 running 数"，实际是全表行数。属于"监控/统计类数据源的呈现值长期未与真实 DB 对齐"（N218 教训：Dashboard 数字要定期抽查）。

## 解决方案

1. **修复**：为 `TaskExecutionViewSet` 补 `filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]` + `filterset_fields = ["status", "task", "device", "game_account", "triggered_by"]`。
   - ⚠️ 坑：filterset_fields 必须只含 **model 真实字段**。第一版误加 `execution_mode`（它是 Task 的字段，TaskExecution 没有）→ `TypeError: 'Meta.fields' must not contain non-model field names: execution_mode` 500。domain 字段不能直接进 filterset。
2. **验证**（commit 后实测）：`?status=running` count=0；`?status=failed` count=26；无参 count=91。工作台"运行任务"变 0。
3. **回归测试**：`test_execution_status_filter.py`（running/failed/无参三分支）。
4. **方法**：修复统计类 bug 时，「先在浏览器看用户可见数字 → 直连 DB 数真实值 → 对 API 带/不带参数各打一次 → 定位是展示层还是数据层」。本次排查即按此链 1 次定位。

## 泛化原则

- **DRF ViewSet 的过滤是"声明式"的**：没写 `filterset_fields` 就等于没有过滤，query 参数静默丢弃。后端单测和前端都不容易发现（因为"有响应、数字看起来合理"）。凡是前端"按条件取数"的调用，后端对应端点在**本次改动前**最好有"无过滤 vs 有过滤"的对照断言。
- 用户可见的统计数字（工作台卡片/仪表盘）应纳入周期性抽查（meta_audit 巡检时对呈现值对账 DB）。