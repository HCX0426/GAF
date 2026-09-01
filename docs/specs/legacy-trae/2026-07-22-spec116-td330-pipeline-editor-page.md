---
spec_id: spec-116
title: TD-330 sub-spec 24 — PipelineEditorPage.tsx hex color → antd token 治理 (v4 var fallback)
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-115]
blocks: []
priority: P2
size: 小 (1 文件 4 hex 治理, SAVE_STATUS_ICON 函数化, ~15 行 diff)
---

# spec-116: TD-330 sub-spec 24 — PipelineEditorPage.tsx hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 24 个 sub-spec。`frontend/src/pages/Tasks/PipelineEditor/PipelineEditorPage.tsx` 包含 4 处 hex color,全部位于 module-level `SAVE_STATUS_ICON` 常量中,作为 antd v4 CSS var fallback:
- L102: `color: 'var(--ant-color-success, #52c41a)'` (saved 状态图标)
- L103: `color: 'var(--ant-color-primary, #1677ff)'` (saving 状态图标)
- L104: `color: 'var(--ant-color-warning, #faad14)'` (unsaved 状态图标)
- L105: `color: 'var(--ant-color-error, #ff4d4f)'` (error 状态图标)

这些是 antd v4 `var(--ant-color-*, #hex)` CSS var + hex fallback 模式,在 antd v5 中应直接用 design token。文件已 import `theme as antTheme` 和 `GlobalToken`,组件内已有 `const { token } = antTheme.useToken();` (L144),且已有 `getValidateResultStyle(token)` 函数化先例 (L109)。

`SAVE_STATUS_ICON` 是 module-level const,需函数化为 `getSaveStatusIcon(token)`,使用点 L823。

## 治理方案

### A 类 (直接迁移 → antd token,通过函数化)

将 module-level `SAVE_STATUS_ICON` 常量改为 `getSaveStatusIcon(token: GlobalToken)` 函数,与 `getValidateResultStyle(token)` 模式一致:

| 行 | 原 hex (v4 var fallback) | 替换 | 说明 |
|---|---|---|---|
| L102 | `var(--ant-color-success, #52c41a)` | `token.colorSuccess` | 成功语义色 |
| L103 | `var(--ant-color-primary, #1677ff)` | `token.colorPrimary` | 主色 |
| L104 | `var(--ant-color-warning, #faad14)` | `token.colorWarning` | 警告语义色 |
| L105 | `var(--ant-color-error, #ff4d4f)` | `token.colorError` | 错误语义色 |

### 组件内使用点

L823 `SAVE_STATUS_ICON[saveStatus]` → 组件内加 `const saveStatusIcon = getSaveStatusIcon(token);`,引用改为 `saveStatusIcon[saveStatus]`。

### C 类 (保留)

无 C 类保留 (4 hex 全为 antd 语义色对应,v4 var fallback 在 v5 中已无意义)。

## 验收标准

- hex color 4 → 0 (无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorSuccess/colorPrimary/colorWarning/colorError 与原 v4 var fallback 在默认主题下视觉一致)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
