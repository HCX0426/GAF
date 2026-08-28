---
source: GAF/.ai-memory/lessons/N112-p024-frontend-sync.md
load_when: [后端 model 字段变更, 前端 TS 类型同步, P-024 告警升级, severity 标签]
priority: high
symptom: [kb:lesson:n112, p024-frontend-sync, ts-type-drift, severity-mismatch]
solution: '后端 model 改字段后, 前端第一时间同步: (1) TS 类型 (2) API client (3) UI 标签 (4) 过滤下拉 — 4 步配套, 缺一不可'
diff_keywords: [frontend-sync, cross-layer-sync, types/models, monitors, severity]
related_files:
  - backend/monitors/models.py
  - backend/monitors/serializers.py
  - backend/monitors/views.py
  - backend/monitors/tasks.py
  - frontend/src/types/models/
  - frontend/src/api/monitors.ts
  - frontend/src/pages/Ops/Monitors/index.tsx
created_by: AI
date: 2026-06-16
generated: 2026-06-16
level: L1
n_id: N112
topic: cross-layer-sync
---

# N112: P-024 前端同步踩坑 (后端字段变更 → 前端 4 步同步)

> **触发**: P-024 告警升级策略后端 5 commit (- → -) 完成后, 前端 `frontend/src/pages/Ops/Monitors/index.tsx` 仍是旧字段
> **时间**: 2026-06-16 | **commit**: `-` (frontend 同步)

## 1. 问题 (Problem)

P-024 后端 5 commit 修改了 `MonitorEvent` 模型:
- 新增 `severity` 字段 (P0/P1/P2/P3 4级, 后端用 TextChoices)
- 新增 `acknowledged_at`, `acknowledged_by`, `acknowledged_by_username` (确认状态)
- 新增 `escalated_at` (升级时间)
- 新增 `acknowledge` API action (`POST /monitors/monitor-events/{id}/acknowledge/`)
- 新增 Celery `escalate_unhandled_alerts` 任务 (P1 → P0 升级)

但前端:
- `MonitorEvent` TS 类型**没有**新字段, 仍用 `event_type/handling_result/...`
- 表格列用旧字段 `severity` (info/warning/critical 3级) + `resolved` (后端无此字段!)
- `acknowledgeEvent()` 是 **placeholder** (`Promise.resolve()`, 没真打 backend)
- 过滤下拉 3级 (info/warning/critical) 与后端 4级 (P0/P1/P2/P3) 不匹配

**用户后果**: 打开监控告警页 → severity 标签全显示 `default` 色, acknowledge 按钮点了没反应, 过滤不到 P0/P1 告警

## 2. 根因 (Root Cause) — 5 维

### 2.1 同步检查清单缺失
- AI 完成后端后, 没在前端建立"后端字段变更 → 前端 4 步配套" checklist
- 现有规则只说"分段提交", 但**没说后端 model 改字段时前端必须同步**

### 2.2 表格列名错位
- `dataIndex: 'rule'` 在前端定义, 但后端是 `event_type`
- `dataIndex: 'details'` 但后端是 `handling_result`
- `dataIndex: 'resolved'` 但后端**根本没有**此字段
- AI 写前端时凭"看起来对", 没 grep 后端 serializer 确认

### 2.3 severity 4 级 vs 3 级错配
- 后端 P-024 用 4 级: P0 紧急 / P1 高 / P2 中 / P3 低
- 前端旧 3 级: info / warning / critical (Ant Design 默认 Tag 配色)
- 静默期间只显示 `info`, 应改为 `P3` (低级别)

### 2.4 acknowledge 行为错位
- 后端 `acknowledge()` action: POST + 校验幂等 (409 if already acknowledged)
- 前端 `acknowledgeEvent()` 是 **placeholder** (`Promise.resolve()`)
- 真实场景下, 用户点击"确认"后 → 前端乐观更新 resolved=true → 但后端其实**没**收到请求 → 刷新后又变回 unresolved
- 状态不同步, 用户以为成功了实际没成功

### 2.5 acknowledgeBy 用户名缺失
- 后端 serializer 暴露 `acknowledged_by_username` (从 User model 取 username)
- 前端表格没显示"谁确认的"和"什么时候确认的", 审计追溯困难

## 3. 修复 (Solution) — 4 步配套 (缺一不可)

### 3.1 步骤 ① TS 类型同步 (frontend/src/types/models/)

```typescript
/** 监控事件严重级别 — matches backend MonitorEvent.Severity */
export type MonitorEventSeverity = 'P0' | 'P1' | 'P2' | 'P3';

/** 监控事件 — matches backend MonitorEventSerializer (P-024 escalation) */
export interface MonitorEvent {
  id: number;
  event_type: string;          // ← 改: rule/details → event_type/handling_result
  severity: MonitorEventSeverity;  // ← 新
  handling_result?: string | null;
  ...
  acknowledged_at?: string | null;        // ← 新
  acknowledged_by?: number | null;        // ← 新
  acknowledged_by_username?: string | null;  // ← 新
  escalated_at?: string | null;           // ← 新
  created_at: string;
}
```

### 3.2 步骤 ② API client 真实后端调用 (frontend/src/api/monitors.ts)

```typescript
// 旧: placeholder
export async function acknowledgeEvent(_eventId: number): Promise<void> {
  console.warn('[MONITORS] acknowledgeEvent is not yet implemented on backend');
  return Promise.resolve();
}

// 新: 真实后端调用 + 错误处理
export async function acknowledgeEvent(eventId: number, note?: string): Promise<MonitorEvent> {
  const res = await client.post<MonitorEvent>(`/monitors/monitor-events/${eventId}/acknowledge/`, {
    note: note || '',
  });
  return res.data;
}
```

### 3.3 步骤 ③ UI 标签 + 颜色 (frontend/src/pages/Ops/Monitors/index.tsx)

```typescript
// 旧 3 级
const SEVERITY_COLOR_MAP: Record<string, string> = {
  info: 'blue', warning: 'orange', critical: 'red',
};

// 新 4 级 (P-024)
const SEVERITY_COLOR_MAP: Record<MonitorEventSeverity, string> = {
  P0: 'red',    // 紧急
  P1: 'orange', // 高
  P2: 'gold',   // 中
  P3: 'blue',   // 低
};
```

### 3.4 步骤 ④ 过滤下拉 + 静默提示

```typescript
// 旧: 3 级 + resolved 状态 (后端无 resolved 字段)
options={[
  { value: 'info', label: '信息' },
  { value: 'warning', label: '警告' },
  { value: 'critical', label: '严重' },
]}

// 新: 4 级 + 3 态 (未处理/已确认/已升级)
options={[
  { value: 'P0', label: 'P0 紧急' },
  { value: 'P1', label: 'P1 高' },
  { value: 'P2', label: 'P2 中' },
  { value: 'P3', label: 'P3 低' },
]}

// 静默文案: 旧 "信息级别" → 新 "P3 低级别"
"静默期间仅显示 P3 低级别事件, P0/P1/P2 告警已被隐藏"
```

### 3.5 附加: acknowledge 错误处理 (409 已确认)

```typescript
const handleAcknowledge = async (eventId: number) => {
  try {
    const updated = await acknowledgeEvent(eventId);
    setEvents((prev) => prev.map((e) => (e.id === eventId ? updated : e)));
    msg.success('已确认告警');
  } catch (err: unknown) {
    const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } };
    const detail = axiosErr?.response?.data?.detail;
    if (axiosErr?.response?.status === 409) {
      msg.warning(detail || '该告警已被确认');
      loadEvents();  // 重新拉取以同步状态
    } else {
      msg.error(detail ? `确认失败: ${detail}` : '确认失败,请重试');
    }
  }
};
```

## 4. 预防 (Prevention) — AI 必读

### 4.1 后端 model 改字段 → 前端 4 步配套 checklist

| # | 步骤 | 文件 | 验证 |
|:-:|------|------|------|
| ① | TS 类型同步 | `frontend/src/types/models/` | `npx tsc --noEmit` 通过 |
| ② | API client 真实调用 | `frontend API client files` | 移除 placeholder 警告 |
| ③ | UI 标签 + 颜色 | `frontend/src/pages/**/*.tsx` | 4 级颜色映射 |
| ④ | 过滤下拉 + 静默提示 | 同上 | 后端字段全覆盖 |

### 4.2 写前端前必读后端 (L3 按需)

```
[AI 写前端前 3 步]
  1. Read backend/<app>/serializers.py (字段权威源)
  2. Read backend/<app>/views.py (action 端点 + 错误码)
  3. Grep frontend/src/types/models/ (对比现有 TS 类型)
  4. 4 步配套改前端
```

### 4.3 表格列名严格对齐后端

- ❌ 旧: `dataIndex: 'rule'` / `'details'` / `'resolved'` (前端编造字段名)
- ✅ 新: `dataIndex: 'event_type'` / `'handling_result'` / `'acknowledged_at'` (后端字段名)

**规则**: `dataIndex` 必须是后端 serializer `fields` 列表中的字段, 不能凭语义编

### 4.4 severity 标签色一致性 (P-024)

| 级别 | 含义 | 颜色 | antd Tag color |
|:----:|------|:----:|:----:|
| P0 | 紧急 (escalated) | 红 | `red` |
| P1 | 高 (升级候选) | 橙 | `orange` |
| P2 | 中 (默认) | 黄 | `gold` |
| P3 | 低 (静默保留) | 蓝 | `blue` |

### 4.5 acknowledge 错误码 409 处理

后端 409 = 已确认, 前端必须:
1. 显示 `msg.warning(detail)` (不显示 error, 避免误判)
2. 重新拉取事件列表 (`loadEvents()`), 同步状态

## 5. 同根因家族 (N95)

- **N95**: 5 层分发缺位 (教训写完没分发)
- **N100**: Set-Content 损坏 (路径/编码错)
- **N101**: 状态不诚实 (前端 placeholder 假装已实现)
- **N106**: 路径漂移 (TS 类型路径与 serializer 漂移)
- **N110**: hook 误触项目历史 (commit 被 block)
- **N111**: AI 傻等命令 (commit 卡住)
- **N112** (本条): **后端字段变更 → 前端 4 步配套缺位** ← 同根因: **跨层同步缺位**

## 6. 验证 (Verification)

| 验证项 | 命令 | 结果 |
|--------|------|:----:|
| TypeScript 编译 | `npx tsc --noEmit -p tsconfig.json` | ✅ exit 0 |
| ESLint 新代码段 | `npx eslint src/pages/frontend/src/pages/Ops/Monitors/index.tsx` | ⚠️ 29 错误 (N110 既有问题, 无关本轮) |
| Git commit | `git log --oneline -1` | ✅ `-` |
| 前端规范 audit | web-design-guidelines | ✅ aria-label 齐, Intl.DateTimeFormat 正确, 错误信息含 next step |

## 7. R24 标记 ✅ (Phase R24 完成)

P-024 告警升级策略: 100% 完成
- 后端 5 commit: - / - / - / - / -
- 前端 1 commit: -
- 测试: 8/8 (TC-P024-1~8) 通过

**added_by**: AI
**added_at**: 2026-06-16
**example_run_id**: P-024 4 子任务, commit -
**migrated_from**: 无
**related**: failure-modes.md N112, architecture-mistakes.md #40, pending-roadmap.md §二.9
