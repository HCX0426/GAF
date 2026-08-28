---
id: N132
date: 2026-06-24
title: DRF PrimaryKeyRelatedField 返回实例 + JSONField filterset + set-state-in-effect
priority: medium
cross_refs:
- skills/views.py (publish action)
- skills/tests/test_skill_market.py
- SkillMarket/index.tsx (useEffect)
- frontend/src/api/misc.ts (unattended POST trailing slash)
- frontend/src/stores/useUnattendedStore.ts (snake_case→camelCase mapping)
- frontend/src/api/__tests__/api-paths.test.ts (POST slash guard)
tags:
- drf
- react-hooks
- django-filter
- skill-market
- api-contract
symptom:
- drf
- react
- primary-key-related-field
- jsonfield
- filterset
- skill-market
- set-state-in-effect
- append-slash
- trailing-slash
- snake-case
- camal-case
- contract-mismatch
solution: DRF PrimaryKeyRelatedField returns model instance in validated_data (not
  PK); JSONField cannot be in filterset_fields; DRF ViewSet get_queryset should vary
  by action; React setState in effect needs async guard/cancelled flag; Django
  APPEND_SLASH POST missing trailing slash raises 500 (GET masked by 301) — frontend
  write calls must carry the exact backend path; never `as XxxType[]` cast a
  snake_case API response onto camelCase types — map explicitly.
diff_keywords: ["views", "drf", "misc", "useUnattendedStore", "api-paths"]
related_files:
- backend/skills/views.py
- backend/skills/tests/test_skill_market.py
- frontend/src/pages/AI/SkillMarket.tsx
- frontend/src/api/misc.ts
- frontend/src/stores/useUnattendedStore.ts
- frontend/src/api/__tests__/api-paths.test.ts
created_by: AI
level: L1
n_id: N132
topic: doc-governance
---




# N131: DRF + React 常见陷阱 (Skill 市场实现)

## 问题 1: PrimaryKeyRelatedField 返回实例不是 ID

**症状**: `TypeError: int() argument must be a string... not 'SkillDefinition'`

**根因**: `SkillMarketItemCreateSerializer` 的 `skill` 字段是 PrimaryKeyRelatedField，`serializer.validated_data['skill']` 返回的是 **SkillDefinition 实例**，不是 ID。后续 `SkillDefinition.objects.get(pk=skill_id)` 传入实例报错。

**修复**: 直接用 `skill = serializer.validated_data['skill']`，删除额外的 DB 查询。

**教训**: DRF PrimaryKeyRelatedField 在 `validated_data` 中返回模型实例，不是 PK 值。不要再写 `Model.objects.get(pk=validated_data['field'])`。

## 问题 2: JSONField 不能放 filterset_fields

**症状**: `AssertionError: AutoFilterSet resolved field 'tags' with 'exact' lookup to an unrecognized field type JSONField`

**根因**: django-filter 无法自动为 JSONField 生成过滤器。

**修复**: 从 `filterset_fields` 移除 JSONField 字段，或添加 `filter_overrides`。

**教训**: `filterset_fields` 只能包含 django-filter 支持的字段类型（CharField/IntegerField/BooleanField/DateTimeField 等），JSONField/ArrayField 需自定义过滤器。

## 问题 3: get_queryset 需按 action 区分状态过滤

**症状**: `test_import_pending_item_fails` 期望 400，实际 404

**根因**: `get_queryset()` 默认只返回 APPROVED 状态，pending item 查不到返回 404。但 import/review action 需要先获取对象再检查状态返回 400。

**修复**: `get_queryset()` 对 `import_item`/`review` action 返回所有状态，视图内检查状态返回 400。

**教训**: DRF ViewSet 的 `get_queryset()` 可以根据 `self.action` 区分不同 action 的 queryset。自定义 action 需要状态校验时，不要在 queryset 层过滤，在视图内校验。

## 问题 4: react-hooks/set-state-in-effect

**症状**: ESLint 错误 `Calling setState synchronously within an effect can trigger cascading renders`

**根因**: `useEffect` 中调用包含 `setLoading(true)` 的外部函数，被视为同步 setState。

**修复**: 用 `cancelled` flag 模式内联异步逻辑：
```tsx
useEffect(() => {
  let cancelled = false;
  const load = async () => {
    setLoading(true);
    try { /* ... */ if (!cancelled) setData(...); }
    finally { if (!cancelled) setLoading(false); }
  };
  load();
  return () => { cancelled = true; };
}, [deps]);
```

**教训**: React 18+ 的 `react-hooks/set-state-in-effect` 规则要求 effect 中的 setState 必须在异步回调或 cleanup 保护下，避免级联渲染。

## 问题 5: POST 路径缺尾斜杠 → APPEND_SLASH 下 500（GET 被 301 掩盖）

**症状**: 无人值守「启动/停止/暂停/恢复」通过 UI 全部报错，而 preflight(GET) 正常。

**根因**: 前端调 `client.post('/scheduler/unattended/start')`（无尾斜杠），后端路由是 `unattended/start/`。Django `APPEND_SLASH=True`（config 未显式设置）对 GET 会 301 重定向（前端静默跟随，正常）；但对 **POST 直接抛 RuntimeError → 500**（AppendSlash 无法保留 POST body）。同批 4 个端点全踩。

**修复**: 前端写请求统一带尾斜杠（`/scheduler/unattended/start/`）；`api-paths.test.ts` 增加 POST 端点尾斜杠断言护栏。

**教训 5a**: 只要后端没有显式 `APPEND_SLASH=False`，前端**所有写请求(post/put/patch/delete)的路径必须与后端路由完全一致含尾斜杠**。GET 的 301 重定向会掩盖路径不一致，所以"GET 能通"不能证明路径正确。新增前端端点时同步补 api-paths 断言。

## 问题 6: 后端 snake_case 响应被前端 camelCase 类型 as 强转 → 静默数据全空

**症状**: 状态矩阵每台设备都显示「离线」、账户列空白、进度"暂无数据"；控制台无报错。

**根因**: 后端 `/scheduler/unattended/status|queue|progress` 返回 snake_case（`device_id`/`device_name`/`account_name`…），前端 `MatrixRow`/`QueueItem`/`ProgressData` 类型是 camelCase，store 用 `data.matrix as MatrixRow[]` 直接强转。TS 强转不检查运行时形状，所有字段变成 undefined → UI 渲染空值/默认值，无法自动发现。

**修复**: `useUnattendedStore` 增加 `matrixRowToState`/`queueItemToState`/`progressToState` 显式字段映射；测试 fixture 改用真实后端 snake_case 形状。

**教训 6a**: `as XxxType[]` 强转是**运行时契约盲区**——TS 只信类型注释，不信实际数据。消费后端 API 响应时，要么字段命名与后端完全一致（如 DeviceGroup 与 serializer 逐字段相等），要么显式 map 转换并让它被真实响应形状的单测覆盖。定长检查：搜索 `data.* as XxxType[]`，对照后端 serializer 字段逐项核对。

## 问题 7: Django ORM 的 `__lt/__gt` 不匹配 NULL → 心跳超时检测漏掉"从未心跳"记录

**症状**: 工作台显示 2 个 Agent，实际只有 1 个真实 agent（本机）。第二个是 legacy/manual 记录，`status=ONLINE` 但 `last_heartbeat=None`。

**根因**: `tasks/heartbeat.py::check_agent_heartbeats` 用 `last_heartbeat__lt=cutoff` 找超时 agent。SQL 中 `NULL < timestamp` 结果是 NULL（未知），Django filter 不选中——**从未心跳的记录永远不会被判定超时**，永远 ONLINE = 幻影 agent。

**修复**: 联合判定 `Q(last_heartbeat__isnull=True) | Q(last_heartbeat__lt=cutoff)`；None 心跳按最大超时处理。

**教训 7a**: 所有"按时间戳找过期/陈旧"的 ORM 过滤都要考虑 NULL：
- Django `__lt/__gt/__lte/__gte` 对 NULL 字段一律不匹配（NULL-safe 语义）
- 时间戳可能为 NULL 的列（`last_heartbeat`、`completed_at`、`started_at`）必须显式补 `filter(Q(x__isnull=True) | Q(x__lt=...))` 或 `Coalesce`
- 排查这类问题快路径：全库 grep `__lt=` / `__gt=` 配合可空时间字段
