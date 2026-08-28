---
title: "TD-335 前端架构债务剩余项修复"
status: "✅ FIXED"
created: 2026-08-09
applies_to: [frontend]
---

# TD-335 前端架构债务剩余项修复

## 1. 背景

TD-335 登记于 2026-07-23，涵盖前端架构 4 个维度：类型安全 / i18n / react-query / DOM 反模式。

**已完成的验收标准**：
- ✅ AppLayout 无 document.querySelector
- ✅ 0 处硬编码中文（8/8 文件，lint 规则强制）
- ✅ react-query 覆盖 5 个高频查询 hook
- ✅ 0 处 as unknown as 真实问题
- ✅ 0 处执行控制静默吞错
- ✅ SLADashboard loading 正确
- ✅ 无废弃组件

**本 spec 处理剩余未完成项**。

## 2. 范围

### 2.1 P0 #1: tsconfig strict 分阶段开启

**现状**：
- `tsconfig.app.json` 无 `strict` / `noImplicitAny` / `strictNullChecks`
- 当前 `tsc --noEmit` 仅 14 行错误（全部在测试文件 `__tests__/` 中）
- 生产代码 0 类型错误（当前宽松配置下）
- `check-types.ps1` 脚本声称"noImplicitAny + strictNullChecks enabled"但实际未在 tsconfig 中开启

**方案**：分 3 阶段开启

| 阶段 | 配置变更 | 预期新错误 | 工作量 |
|------|---------|-----------|--------|
| Phase 1 | `noImplicitAny: true` | ~50-80 处 | 中 |
| Phase 2 | `strictNullChecks: true` | ~100-200 处 | 大 |
| Phase 3 | `strict: true`（含前两项） | 累加 | 大 |

**本 spec 范围**：Phase 1 仅 `noImplicitAny`。

### 2.2 P1 #8: useEffect fetch 缺 AbortController

**现状**：多个 useEffect 中直接调用 API 而不使用 AbortController，组件卸载后请求可能泄漏或产生竞态。

**已修复的**：
- ✅ `useGlobalSearch.ts` — 完整 AbortController 实现
- ✅ `AppLayout.tsx` — 未读通知轮询已有 AbortController
- ✅ `useSSEStream.ts` — 完整 AbortController 实现

**待修复的**（分批）：

| 批次 | 文件 | 行 | API 调用 | 依赖 | 说明 |
|------|------|-----|---------|------|------|
| Batch 1 | `Dashboard/TodaySchedule.tsx` | 76 | fetchTodaySchedule | [load] | 仪表盘高频组件 |
| Batch 1 | `Dashboard/AlertSummary.tsx` | 50 | fetchMonitorEvents | [load] | 仪表盘高频组件 |
| Batch 1 | `Tasks/index.tsx` | 74 | fetchResourcePacks | [] | 任务列表页 |
| Batch 1 | `Tasks/index.tsx` | 170 | fetchTasks | [resourcePackFilter] | 任务列表页 |
| Batch 1 | `ScheduledTasks/index.tsx` | 119 | fetchScheduledTasks | [] | 定时任务页 |
| Batch 1 | `ScheduledTasks/index.tsx` | 143 | fetchSchedulerExecutions | [] | 定时任务页 |
| Batch 1 | `PipelineEditor/PipelineEditorPage.tsx` | 443 | pipelineApi.getPipeline | [pipelineId] | 流水线编辑器 |
| Batch 1 | `Login/index.tsx` | 86 | getInitStatus | [] | 登录页 |
| Batch 2 | 其余低优先级 useEffect fetch | — | 各类 API | — | 后续批次 |

### 2.3 P2: Sidebar eslint-disable 可优化

**位置**：`Sidebar.tsx:180,187` — 2 处 `eslint-disable-next-line @typescript-eslint/no-unused-vars`

**现状**：
```typescript
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const { permission: _permission, ...rest } = item;
return rest;
```

**方案**：用 `Pick` 或直接解构所需字段替代 `_permission` 解构，消除 eslint-disable。

### 2.4 P2: useSSEStream 硬编码中文

**位置**：`useSSEStream.ts:180` — `'SSE 连接错误'`

**方案**：改为通过 options 传入 errorMessage，默认值保留中文。

## 3. 验收标准

### Phase 1: tsconfig noImplicitAny

- [x] `tsconfig.app.json` 添加 `noImplicitAny: true`
- [x] 所有 `noImplicitAny` 新增类型错误修复
- [x] `tsc --noEmit --project tsconfig.app.json` 通过（0 错误）
- [x] `check-types.ps1` 脚本与 tsconfig 实际配置一致

### Batch 1: AbortController

- [x] 每个待修复的 useEffect 添加 AbortController
- [x] 组件卸载时 abort 进行中的请求
- [x] 二次触发时先 abort 旧请求再发起新请求
- [x] 所有改动的组件功能正常（回归验证）

### Sidebar eslint-disable

- [x] Sidebar.tsx 0 处 eslint-disable（前序提交已修复）
- [x] 功能无变化

### useSSEStream 硬编码中文

- [x] useSSEStream.ts 无硬编码中文（已支持 errorMessage 参数）
- [x] 调用方可以传入自定义错误消息

## 4. 实现步骤

### Step 1: tsconfig noImplicitAny

1. 在 `tsconfig.app.json` 添加 `"noImplicitAny": true`
2. 运行 `tsc --noEmit` 收集所有新错误
3. 逐文件修复（主要模式：函数参数加显式类型、泛型约束补全）
4. 验证 `tsc --noEmit` 0 错误

### Step 2: AbortController Batch 1

1. 为每个待修文件添加 useRef<AbortController> 管理控制器
2. useEffect 内创建 AbortController，cleanup 时 abort
3. 有依赖变化的 useEffect：先 abort 旧请求再发起新请求

### Step 3: Sidebar eslint-disable

1. 将 `const { permission: _permission, ...rest } = item` 改为 `const { children, ...rest } = item`
2. 确认 `permission` 字段不参与 `rest` 的展开

### Step 4: useSSEStream 硬编码中文

1. 在 `UseSSEStreamOptions` 接口添加可选 `errorMessage?: string`
2. 默认值 `'SSE 连接错误'`
3. 修改 `setError` 调用处使用 `options.errorMessage || 'SSE 连接错误'`

## 5. 不处理项

- **tsconfig Phase 2 (strictNullChecks)**: 工作量太大，标记为后续批次
- **tsconfig Phase 3 (strict)**: 依赖 Phase 1+2 完成
- **AbortController Batch 2**: 低优先级 useEffect fetch，后续批次
- **大列表无虚拟化 (@tanstack/react-virtual)**: 转长期，架构变更大