---
spec_id: spec-117
title: TD-330 sub-spec 25 — ExecutionReplay.tsx + 3 Setup 文件 hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: -
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-116]
blocks: []
priority: P2
size: 小 (4 文件 5 hex 治理, ~12 行 diff)
---

# spec-117: TD-330 sub-spec 25 — ExecutionReplay.tsx + 3 Setup 文件 hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 25 个 sub-spec。合并治理 4 个文件共 5 处 hex color (每文件 1-2 hex,模式重复,合并高效):

### ExecutionReplay.tsx (2 hex)
- L198: `color: step.status === 'failed' ? '#ff4d4f' : '#1890ff'` (步骤状态图标色)

### EnvDiagnosisPanel.tsx (1 hex)
- L70: `borderBottom: '1px solid #f0f0f0'` (诊断项分隔线)

### StepCreateAdmin.tsx (1 hex)
- L85: `background: '#f6f8fa'` (信息卡片背景,与 spec-115 StepConfigureInfra L99 同模式)

### StepDeviceScan.tsx (1 hex)
- L128: `background: '#f6f8fa'` (信息卡片背景,同模式)

注: StepRecommendedTemplates.tsx L75 `#f0f0f0` 与 EnvDiagnosisPanel L70 同模式,本 spec 一并合并。

## 治理方案

### A 类 (直接迁移 → antd token)

| 文件 | 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|---|
| ExecutionReplay.tsx | L198 | `#ff4d4f` | `token.colorError` | 错误色 |
| ExecutionReplay.tsx | L198 | `#1890ff` | `token.colorPrimary` | 主色 (antd v4 残留色) |
| EnvDiagnosisPanel.tsx | L70 | `#f0f0f0` | `token.colorBorderSecondary` | 次级边框色 |
| StepCreateAdmin.tsx | L85 | `#f6f8fa` | `token.colorBgLayout` | 布局背景灰 |
| StepDeviceScan.tsx | L128 | `#f6f8fa` | `token.colorBgLayout` | 布局背景灰 |
| StepRecommendedTemplates.tsx | L75 | `#f0f0f0` | `token.colorBorderSecondary` | 次级边框色 |

### 文件 useToken 状态

- ExecutionReplay.tsx: 需添加 `theme` import + `const { token } = theme.useToken();`
- EnvDiagnosisPanel.tsx: 需添加 (与 StepConfigureInfra 同目录)
- StepCreateAdmin.tsx: 需添加
- StepDeviceScan.tsx: 需添加
- StepRecommendedTemplates.tsx: 需添加

### C 类 (保留)

无 C 类保留 (5 hex 全为 antd 语义色对应)。

## 验收标准

- hex color 5 → 0 (无 C 类保留,跨 4 文件 + StepRecommendedTemplates)
- `npx tsc --noEmit` 0 errors
- 视觉等价

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
