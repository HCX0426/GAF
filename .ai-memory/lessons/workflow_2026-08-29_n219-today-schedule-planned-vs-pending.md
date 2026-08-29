---
date: 2026-08-29
symptom: [today-schedule-arrow-gap, planned-vs-pending-misleading, empty-account-double-arrow, dashboard-timeline-confusing]
solution: 计划型展示(今日日程=引擎推导的排期)的状态语义要与执行型状态区分 — 未触发的计划用 planned(计划中) 而非 pending(待执行), 避免用户误以为"任务在排队却不动"; 前端拼接 device→account→chain 时对空字段做条件渲染, 禁止无条件 `a → b → c`
related_files:
  - backend/scheduler/services/scheduler_service.py
  - frontend/src/components/Dashboard/TodaySchedule.tsx
  - backend/scheduler/serializers.py
  - frontend/src/components/Dashboard/ExecutionQueuePreview.tsx
  - backend/tasks/execution_views.py
  - backend/executions/views.py
  - backend/scheduler/unattended_views.py
  - backend/protocol/services.py
created_by: AI
priority: high
n_id: N219
diff_keywords: ["planned", "计划中", "today_schedule", "account_name", "getStatusConfig", "→"]
---

# 今日日程把"计划排期"显示成"待执行" + 空账户渲染出空段箭头

## 症状（2026-08-29, 用户追问"今日日程那没问题吗?"）

工作台"今日日程"显示 2 条:
- `Chrome-Browser → cycle-test-1 → cycle-baidu-chain` （正常）
- `LDPlayer → → cycle-chain` （**双箭头中间空白**）
两条都标 **"待执行"**, 但用户明确没启动任何任务 → "待执行"强烈误导为"任务在排队却不跑"。

## 根因

1. **计划≠执行**: `get_today_schedule` 调 `generate_execution_plan(days=1)`, 按 "Device + GameProfile.default_routine" 推导**今天该跑哪些链** — 这是排期(计划), 与真实执行(无人值守是否启动/执行记录)无关. 但后端把计划项状态写成 `["pending"]`("待执行"), 前端 Timeline 直接渲染, 用户看到"待执行"却无执行行为 → 判为系统 bug.
2. **空账号拼接**: `device.game_account` 未绑定时 `account_name=None`, 前端无条件渲染 `{device} → {account} → {chain}` → `LDPlayer → → cycle-chain`.

## 解决方案（N219）

1. **状态语义分离**: 计划项状态 `pending` → **`planned`("计划中")**; 前端 `ScheduleItemStatus` + `getStatusConfig` 增加 `planned` 分支(灰/日历 icon). "待执行"保留给真实已派发的执行(如执行队列), 计划排期不再与之混淆.
2. **空字段条件渲染**: 前端 `account_name` 有值才渲染 ` → account` 段; 后端 `account_name` 空时给 `""`（不再"未知账户"占位）.
3. **serializer 同步**: TodayScheduleItemSerializer 状态 ChoiceField 补 `planned`.
4. 回归测试: `test_today_schedule_planned_status_and_empty_account`（planned + 空账号断言）。
5. 2026-08-29 全仓同类扫除: ① 执行队列预览 (ExecutionQueuePreview) 同消费 today 接口, 补 `planned` 分支 + 空段守卫; ② 后端 `get_today_schedule` 的 `device_name`/`task_chain_name` 占位统一 `""`; ③ recovery-log 摘要/日报 items/failures/无人值守 queue 的 `未知设备/未知账户/未知任务/未知错误` 全部改空串 (无 UI 消费方, 诚实为空优于伪占位); ④ protocol 落库默认 `未知错误` → `""` + 测试同步。

## 验证

- 浏览器实测 dashboard: `LDPlayer → cycle-chain`(无空段) + 两条"计划中" + Chrome 条目完整 ✅
- scheduler tests 139 passed（含新用例）+ ruff 0 + tsc 0

## 泛化原则

- **状态值符合"事实语义"**: 展示层的状态标签必须与用户可观察到的"是否在发生"一致。引擎推导的排期用 `planned/计划中`, 派发后的执行才用 `pending/待执行`/`running/进行中`。用词模糊会直接制造"系统在跑但我没让它跑"的困惑。
- **拼接型文案必须防御空段**: 任何 `a → b → c` 式组合渲染, 对各段做空值判断或 gracefully 隐藏, 禁止裸拼接(易出 `a → → c`).
- 用户看到"其实没发生的事"时优先怀疑**语义标签错配**, 而非数据造假 — 先分清楚"计划/实际执行"两类数据源。