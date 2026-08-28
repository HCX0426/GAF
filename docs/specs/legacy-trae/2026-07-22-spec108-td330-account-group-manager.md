---
spec_id: spec-108
title: TD-330 sub-spec 16 — AccountGroupManager.tsx hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: -
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-107]
blocks: []
priority: P2
size: 小 (1 文件 ~5 hex 治理, ~7 行 diff)
---

# spec-108: TD-330 sub-spec 16 — AccountGroupManager.tsx hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 16 个 sub-spec。`frontend/src/pages/Accounts/components/AccountGroupManager.tsx` 包含 5 处 hex color:
- L148: `style={{ color: '#888' }}` (quick_create 文本灰)
- L187: `style={{ border: '1px dashed #d9d9d9', borderRadius: 6, background: '#fafafa' }}` (group card)
- L252: `style={{ border: '1px solid #f0f0f0', borderRadius: 6, cursor: 'grab' }}` (unassigned account card)
- L255: `style={{ color: '#888' }}` (account.username)

文件未用 useToken(),需添加。

## 治理方案

### A 类 (直接迁移 → antd token)

| 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|
| L148 | `#888` | `token.colorTextTertiary` | 三级文本灰 |
| L187 | `#d9d9d9` | `token.colorBorder` | 边框灰 (dashed) |
| L187 | `#fafafa` | `token.colorBgLayout` | 浅灰布局背景 |
| L187 | `borderRadius: 6` | `gaf-radius-md` (className) | utility class |
| L252 | `#f0f0f0` | `token.colorBorderSecondary` | 次级边框灰 |
| L252 | `borderRadius: 6` | `gaf-radius-md` (className) | utility class |
| L255 | `#888` | `token.colorTextTertiary` | 三级文本灰 |

### C 类 (保留)

无 C 类保留 (5 hex 全为 antd 语义色对应)。

## 验收标准

- hex color 5 → 0 (无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorTextTertiary/colorBorder/colorBgLayout/colorBorderSecondary 与原 hex 在默认主题下视觉一致)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
