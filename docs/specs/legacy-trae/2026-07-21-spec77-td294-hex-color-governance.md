---
spec_id: spec-77
title: TD-294 Phase 4a — 4 文件 ~22 处 hex 颜色 → antd design token
created: 2026-07-21
status: ✅ done
td: TD-294 (Phase 4a/4)
commit: '-'
---

# spec-77: TD-294 Phase 4a — hex 颜色治理

## 范围评估 (Phase 4a)

spec-76 L3-1 subagent 扫描 4 文件 hex 颜色位置, 共 ~22 处可迁移到 antd design token (排除业务调色板 TOOL_COLORS / VALIDATE_RESULT_STYLE 需重构 / CSS var 兜底已优先主题变量)。

## 目标文件 + hex 清单

### 1. LogAnalysisPanel.tsx (5 处, 需加 useToken)
- L580 `border: '1px solid #f0f0f0'` → `token.colorBorder`
- L595 `background: '#fafafa'` → `token.colorBgLayout`
- L604 `color: '#666'` → `token.colorTextSecondary`
- L619/L630 `color: '#999'` → `token.colorTextTertiary`

### 2. PipelineEditorPage.tsx (6 处, 已有 useToken)
- L109-111 `VALIDATE_RESULT_STYLE` 常量 hex (fail/warn/pass bg+border) → 重构为 `getValidateResultStyle(token)` 函数
- L576/L578 `#d9d9d9` minimap node color 兜底 → `token.colorBorder` (需传 token 到 getNodeColor 函数)
- L961 `borderLeft: '1px solid #f0f0f0'` → `token.colorBorder`
- L1020 `borderBottom: '1px solid #f0f0f0'` → `token.colorBorder`
- L101-104 `var(--ant-color-xxx, #xxx)` → 保留 (已用 CSS var 兜底)

### 3. LiveAnnotationTab.tsx (5 处, 已有 useToken)
- L165 `#1890ff` 选中态 → `token.colorPrimary`
- L691 `border: '1px solid #d9d9d9'` → `token.colorBorder`
- L757 `#e6f7ff` 选中态背景 → `token.colorPrimaryBg`
- L868 `border: '1px solid #d9d9d9'` → `token.colorBorder`
- L919 `borderTop: '1px solid #f0f0f0'` → `token.colorBorder`
- L701 `rgba(24,144,255,0.9)` + `#fff` → 保留 rgba (画布悬浮提示, alpha 处理复杂)
- L62-66 TOOL_COLORS → 保留 (业务调色板)

### 4. QAPanel.tsx (6 处, 已有 useToken)
- L35 `color: '#fff'` (getBubbleStyleUser) → `token.colorTextLightSolid` (函数加 token 参数)
- L254 `borderRight: '1px solid #f0f0f0'` → `token.colorBorder`
- L279 `#e6f7ff` 选中态背景 → `token.colorPrimaryBg`
- L280 `#91d5ff` 选中态边框 → `token.colorPrimaryBorder`
- L286 `backgroundColor: '#1890ff'` → `token.colorPrimary`
- L294 `color: '#faad14'` → `token.colorWarning`
- L339 `color: msg.role === 'user' ? '#fff' : token.colorText` → `token.colorTextLightSolid`

## 实施策略

4 文件独立无依赖, 用 4 个并行 subagent 各负责 1 文件。

## 验证

- `npx tsc --noEmit` → 0 errors
- `npx vitest run --reporter=dot` → 21 files 162 tests passed
- `grep "#[0-9a-fA-F]{3,8}" 4 文件` → 残留 ~10 处 (业务调色板 + CSS var 兜底 + rgba)

## 后续

- spec-78: Phase 4b — 高优 5 文件 toolbar → gaf-toolbar (LiveAnnotationTab / ExecutionMonitorPanel / DagEditorPage / GameAccountsPage / TemplateGallery)
- spec-79: Phase 4c — 中优 6 文件 toolbar → gaf-toolbar
