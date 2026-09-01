---
spec_id: spec-97
title: TD-330 sub-spec 5 — AlertHistoryChart hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-96]
blocks: []
priority: P2
size: 小 (1 文件 ~16 hex 治理, ~50 行 diff)
---

# spec-97: TD-330 sub-spec 5 — AlertHistoryChart hex color → antd token 治理

## 背景

TD-330 全仓 inline style + hex color 治理 sub-spec 5。目标文件 `frontend/src/pages/Ops/Monitors/AlertHistoryChart.tsx` (inline 4 + hex 16 = 20)。LiveAnnotationTab.tsx (inline 17 + hex 5 = 22) 已评估跳过 (已大量用 antTheme.useToken(), 剩余 hex 为 C 类业务调色板 TOOL_COLORS)。

## N167 7 维度评分 (25 分, ≥ 5 阈值, AI 自决)

| 维度 | 分数 | 说明 |
|------|------|------|
| 架构长远性 | 5 | hex → token 符合主题切换架构 |
| 全局归一化 | 5 | 复用 TD-294 Phase 4a 模式 |
| 改动量 | 5 | 小 (1 文件 ~50 行 diff) |
| 测试覆盖 | 3 | 无单测, 靠 tsc + 视觉验证 |
| 文档完整 | 3 | spec + active.md 段落 |
| 风险 | 2 | 低 (颜色值替换 + recharts stroke 改 token) |
| 长期维护 | 2 | 中 (token 跟随主题) |
| **总分** | **25** | ✅ AI 自决 |

## 方案 A: COLOR_* 移入组件 + CustomTooltip/stroke hex → antd token

### 改动清单

1. `import { Card, Spin, Empty, Segmented, theme } from 'antd'` (加 theme)
2. `import type { GlobalToken } from 'antd/es/theme/interface'`
3. 删除 module-level `COLOR_CRITICAL/WARNING/INFO/RESOLVED` 常量
4. `AlertHistoryChart` 加 `const { token } = theme.useToken()`,组件内定义 color 变量 (token.colorError/colorWarning/colorPrimary/colorSuccess)
5. `CustomTooltip` 加 `const { token } = theme.useToken()`
6. CustomTooltip `#fff` → `token.colorBgContainer`
7. CustomTooltip `#d9d9d9` ×2 → `token.colorBorder` (border + dashed borderTop)
8. CustomTooltip `#f0f0f0` → `token.colorBorderSecondary` (header borderBottom)
9. CartesianGrid `#f0f0f0` → `token.colorBorderSecondary`
10. XAxis/YAxis `#d9d9d9` ×4 → `token.colorBorder` (axisLine + tickLine)
11. C 类保留: JSDoc 注释中 hex (L99-102, 4 处说明性文字)

### 验收标准

- `npx tsc --noEmit` 0 errors
- hex color 16 → ≤ 4 (C 类 JSDoc 注释保留)
