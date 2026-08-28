---
spec_id: spec-98
title: TD-330 sub-spec 6 — AIUsageDashboard hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: -
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-97]
blocks: []
priority: P2
size: 小 (1 文件 ~5 hex 治理, ~20 行 diff)
---

# spec-98: TD-330 sub-spec 6 — AIUsageDashboard hex color → antd token 治理

## 背景

TD-330 全仓 hex color 治理 sub-spec 6。目标文件 `frontend/src/pages/AI/AIUsageDashboard.tsx` (hex 11)。PIE_COLORS (6 色饼图调色板) 为 C 类业务调色板保留, 治理 #3f8600 + Area chart stroke/fill 4 处。

## N167 7 维度评分 (23 分, ≥ 5 阈值, AI 自决)

| 维度 | 分数 | 说明 |
|------|------|------|
| 架构长远性 | 5 | hex → token 符合主题切换架构 |
| 全局归一化 | 5 | 复用 TD-294 Phase 4a 模式 |
| 改动量 | 5 | 小 (1 文件 ~20 行 diff) |
| 测试覆盖 | 3 | 无单测, 靠 tsc + 视觉验证 |
| 文档完整 | 3 | spec + active.md 段落 |
| 风险 | 1 | 低 (仅 5 处颜色值替换) |
| 长期维护 | 1 | 中 (token 跟随主题) |
| **总分** | **23** | ✅ AI 自决 |

## 方案 A: Area chart hex → antd token (PIE_COLORS 保留)

### 改动清单

1. `import { Card, Row, Col, Statistic, Spin, Empty, theme } from 'antd'` (加 theme)
2. `AIUsageDashboard` 加 `const { token } = theme.useToken()`
3. `#3f8600` → `token.colorSuccess` (Statistic success_rate content color)
4. `#1890ff` ×2 → `token.colorPrimary` (Area requests stroke + fill)
5. `#52c41a` ×2 → `token.colorSuccess` (Area tokens stroke + fill)
6. C 类保留: `PIE_COLORS` (6 色饼图调色板, 4 色可映射但会重复, 保留为业务调色板)

### 验收标准

- `npx tsc --noEmit` 0 errors
- hex color 11 → ≤ 6 (C 类 PIE_COLORS 保留)
