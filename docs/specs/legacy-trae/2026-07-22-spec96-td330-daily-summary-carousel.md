---
spec_id: spec-96
title: TD-330 sub-spec 4 — DailySummaryCarousel hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-95]
blocks: []
priority: P2
size: 小 (1 文件 ~13 hex 治理, ~60 行 diff)
---

# spec-96: TD-330 sub-spec 4 — DailySummaryCarousel hex color → antd token 治理

## 背景

TD-330 全仓 inline style + hex color 治理 sub-spec 4。目标文件 `frontend/src/pages/Ops/Executions/analytics/DailySummaryCarousel.tsx` (inline 11 + hex 13 = 24, 排名 #4)。

## N167 7 维度评分 (25 分, ≥ 5 阈值, AI 自决)

| 维度 | 分数 | 说明 |
|------|------|------|
| 架构长远性 | 5 | hex → token 符合主题切换架构 |
| 全局归一化 | 5 | 复用 TD-294 Phase 4a 模式 |
| 改动量 | 5 | 小 (1 文件 ~60 行 diff) |
| 测试覆盖 | 3 | 无单测, 靠 tsc + 视觉验证 |
| 文档完整 | 3 | spec + active.md 段落 |
| 风险 | 2 | 低 (仅颜色值替换) |
| 长期维护 | 2 | 中 (token 跟随主题) |
| **总分** | **25** | ✅ AI 自决 |

## 方案 A: STATUS_CONFIG 函数化 + 浅色 hex → antd token

### 改动清单

1. `import { Carousel, Card, Tag, Badge, Spin, Empty, theme } from 'antd'` (加 theme)
2. `import type { GlobalToken } from 'antd/es/theme/interface'`
3. `STATUS_CONFIG` 常量 → `getStatusConfig(status, token)` 函数返回 `{ color, label, borderColor }` 用 `token.colorSuccess/colorPrimary/colorWarning/colorError`
4. `DailySummaryCarousel` 加 `const { token } = theme.useToken()`
5. `#999` ×2 → `token.colorTextSecondary` (device/account label)
6. `#fafafa` → `token.colorBgLayout` (description bg)
7. `#555` → `token.colorTextSecondary` (description text)
8. `#d9d9d9` ×2 → `token.colorBorder` (button border)
9. `#fff` ×2 → `token.colorBgContainer` (button bg)
10. `position: 'relative'` → `gaf-position-relative` className
11. C 类保留: keyframes `#1890ff30`/`#1890ff60` (CSS 内联 8 位 hex 带 alpha, 无法用 token)

### 验收标准

- `npx tsc --noEmit` 0 errors
- hex color 13 → ≤ 2 (C 类 keyframes 8 位 hex 保留)
- inline style 11 → ≤ 10 (position: relative 改 className)
