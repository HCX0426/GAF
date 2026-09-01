---
spec_id: spec-105
title: TD-330 sub-spec 13 — Notifications.tsx hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-104]
blocks: []
priority: P2
size: 小 (1 文件 ~5 hex 治理, ~5 行 diff)
---

# spec-105: TD-330 sub-spec 13 — Notifications.tsx hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 13 个 sub-spec。`frontend/src/pages/System/Notifications.tsx` 包含 5 处 hex color,分布在 2 行:
- L236: `background: isSelected ? '#e6f4ff' : item.is_read ? '#fff' : '#fafafa'` (3 hex)
- L243: `color={item.is_read ? '#d9d9d9' : '#1890ff'}` (2 hex, Badge dot color)

文件已用 `const { token: designToken } = antTheme.useToken();` (L40),L262/L273 已用 designToken.colorTextSecondary/colorTextTertiary。

## 治理方案

### A 类 (直接迁移 → antd token)

| 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|
| L236 | `#e6f4ff` | `designToken.colorPrimaryBg` | 选中态浅蓝背景 |
| L236 | `#fff` | `designToken.colorBgContainer` | 已读白色容器背景 |
| L236 | `#fafafa` | `designToken.colorBgLayout` | 未读浅灰布局背景 |
| L243 | `#d9d9d9` | `designToken.colorBorder` | 已读 dot 灰色 |
| L243 | `#1890ff` | `designToken.colorPrimary` | 未读 dot 主色蓝 (antd v4 残留 → v5 token) |

### C 类 (保留)

无 C 类保留 (5 hex 全为 antd 语义色对应)。

## 验收标准

- hex color 5 → 0 (无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorPrimaryBg/colorBgContainer/colorBgLayout/colorBorder/colorPrimary 与原 hex 在默认主题下视觉一致)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
