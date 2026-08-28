---
spec_id: spec-95
title: TD-330 sub-spec 3 — DeviceHealthGrid hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: -
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-94]
blocks: []
priority: P2
size: 小 (1 文件 ~13 hex 治理, ~80 行 diff)
---

# spec-95: TD-330 sub-spec 3 — DeviceHealthGrid hex color → antd token 治理

## 背景与问题

TD-330 第 3 sub-spec, 治理 `frontend/src/pages/Ops/Monitors/DeviceHealthGrid.tsx` (inline 11 + hex 13 = 24). 该文件 hex 集中在:

1. **状态语义色** (A 类迁移): #52c41a (success) / #faad14 (warning) / #ff4d4f (error) — 用于 STATUS_BORDER_MAP + getGaugeColor + getHealthScoreColor, 映射 antd token
2. **文本色** (A 类迁移): #666 (colorTextSecondary) / #bbb (colorTextTertiary) / #f0f0f0 (colorBorderSecondary)
3. **CSS 动画 rgba** (C 类保留): rgba(255, 77, 79, ...) in keyframes criticalPulse — CSS 内联, 保留

### N167 7 维度评分

| 维度 | 分 | 说明 |
|------|---|------|
| 1. 架构长远性 | 3 | TD-330 sub-spec, 复用 spec-93/94 token 迁移模式 |
| 2. 全局归一化 | 4 | 状态色映射 antd token, 主题切换一致 |
| 3. 改动量 | 4 | 1 文件 ~13 hex, ~80 行 diff |
| 4. 测试覆盖 | 3 | typecheck + lint |
| 5. 文档完整 | 4 | 本 spec |
| 6. 风险 | 3 | UI 视觉改动 (状态色), token 体系保底 |
| 7. 长期维护 | 4 | 主题切换一致, 长期受益 |
| **合计** | **25** | ≥ 5 分阈值, AI 自决 |

## 方案 A: 函数参数化 + token 迁移

### 改动清单

1. **`frontend/src/pages/Ops/Monitors/DeviceHealthGrid.tsx`**:
   - import `theme` from antd, DeviceCard 用 `theme.useToken()`
   - STATUS_BORDER_MAP → 函数 `getStatusBorderColor(status, token)` 返回 token.colorSuccess/Warning/Error
   - getGaugeColor(value) → getGaugeColor(value, token)
   - getHealthScoreColor(score) → getHealthScoreColor(score, token)
   - #666 → token.colorTextSecondary
   - #bbb → token.colorTextTertiary
   - #f0f0f0 → token.colorBorderSecondary
   - C 类保留: keyframes rgba (CSS 内联, 无法用 token)

2. **`docs/general/tech-debt/active.md`**: TD-330 段落更新

### 验收标准

- DeviceHealthGrid.tsx hex color 数 13 → ≤ 2 (C 类 keyframes rgba 保留)
- `npx tsc --noEmit` 0 errors
