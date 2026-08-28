---
spec_id: spec-99
title: TD-330 sub-spec 7 — ScheduledTasks/index.tsx hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: -
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-98]
blocks: []
priority: P2
size: 小 (1 文件 ~8 hex 治理, ~20 行 diff)
---

# spec-99: TD-330 sub-spec 7 — ScheduledTasks/index.tsx hex color → antd token 治理

## 背景

TD-330 全仓 hex color 治理 sub-spec 7。目标文件 `frontend/src/pages/Ops/ScheduledTasks/index.tsx` (inline 7 + hex 12 = 19)。TASK_TYPE_COLORS (4 色 FullCalendar 调色板) 为 C 类保留, 治理 diff 结果 8 处 hex (bg/border 语义色)。

## N167 7 维度评分 (25 分, ≥ 5 阈值, AI 自决)

| 维度 | 分数 | 说明 |
|------|------|------|
| 架构长远性 | 5 | hex → token 符合主题切换架构 |
| 全局归一化 | 5 | 复用 TD-294 Phase 4a 模式 + antd 语义色 Bg/Border token |
| 改动量 | 5 | 小 (1 文件 ~20 行 diff) |
| 测试覆盖 | 3 | 无单测, 靠 tsc + 视觉验证 |
| 文档完整 | 3 | spec + active.md 段落 |
| 风险 | 2 | 低 (diff 结果颜色值替换) |
| 长期维护 | 2 | 中 (token 跟随主题) |
| **总分** | **25** | ✅ AI 自决 |

## 方案 A: diff 结果 hex → antd 语义色 Bg/Border token

### 改动清单

1. `import { ..., theme } from 'antd'` (加 theme)
2. `ScheduledTasksPage` 加 `const { token } = theme.useToken()`
3. diff removed: `#fff1f0` → `token.colorErrorBg`, `#ffccc7` → `token.colorErrorBorder`
4. diff modified: `#fffbe6` → `token.colorWarningBg`, `#ffe58f` → `token.colorWarningBorder`
5. diff added: `#f6ffed` → `token.colorSuccessBg`, `#b7eb8f` → `token.colorSuccessBorder`
6. C 类保留: `TASK_TYPE_COLORS` (4 色 FullCalendar 事件调色板)

### 验收标准

- `npx tsc --noEmit` 0 errors
- hex color 12 → ≤ 4 (C 类 TASK_TYPE_COLORS 保留)
