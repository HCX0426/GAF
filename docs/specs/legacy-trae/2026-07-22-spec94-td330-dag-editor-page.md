---
spec_id: spec-94
title: TD-330 sub-spec 2 — DagEditorPage inline style + hex color 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-93]
blocks: []
priority: P2
size: 中 (1 文件 ~56 处治理, ~120 行 diff)
---

# spec-94: TD-330 sub-spec 2 — DagEditorPage inline style + hex color 治理

## 背景与问题

TD-330 第 2 sub-spec, 治理 `frontend/src/pages/Ops/ScheduledTasks/DagEditorPage.tsx` (排名 #2, inline 30 + hex 26 = 56). 该文件含:

1. **业务调色板** (C 类保留): #722ed1 (pipeline 紫, antd 无直接 token) — 提取为 COLOR_PIPELINE 常量
2. **浅色主题 hex** (A 类迁移): #1677ff (= antd colorPrimary) / #f0f0f0 (colorBorderSecondary) / #fafafa (colorBgLayout) / #fff (colorBgContainer) / #888 (colorTextTertiary) / #e8e8e8 (colorBorderSecondary) — 映射 antd token
3. **布局 inline style** (B 类 utility class): borderRadius 6/8 → gaf-radius-md/lg, height 100% → gaf-h-full, overflow hidden → gaf-overflow-hidden

### N167 7 维度评分

| 维度 | 分 | 说明 |
|------|---|------|
| 1. 架构长远性 | 3 | TD-330 sub-spec, 复用 spec-93 模式 (token + utility class) |
| 2. 全局归一化 | 4 | 复用 spec-93 .gaf-terminal* + TD-294 utility class 体系 |
| 3. 改动量 | 3 | 1 文件 ~56 处, ~120 行 diff |
| 4. 测试覆盖 | 3 | typecheck + lint 验证 |
| 5. 文档完整 | 4 | 本 spec + TD-330 方案 |
| 6. 风险 | 3 | UI 视觉改动, token 体系保底 |
| 7. 长期维护 | 4 | 治理一批, 长期受益 |
| **合计** | **24** | ≥ 5 分阈值, AI 自决 |

## 方案 A: antd token 迁移 + COLOR_PIPELINE 常量 + utility class

### 改动清单

1. **`frontend/src/pages/Ops/ScheduledTasks/DagEditorPage.tsx`**:
   - import `theme` from antd, `const { token } = theme.useToken()`
   - 提取 `const COLOR_PIPELINE = '#722ed1'` 常量 (C 类保留, antd 无直接 token)
   - #1677ff → token.colorPrimary
   - #f0f0f0 → token.colorBorderSecondary
   - #fafafa → token.colorBgLayout
   - #fff → token.colorBgContainer
   - #888 → token.colorTextTertiary
   - #e8e8e8 → token.colorBorderSecondary
   - borderRadius 6 → gaf-radius-md, 8 → gaf-radius-lg
   - height '100%' → gaf-h-full, overflow 'hidden' → gaf-overflow-hidden

2. **`docs/general/tech-debt/active.md`**: TD-330 段落更新 (sub-spec 进度)

### 验收标准

- DagEditorPage.tsx hex color 数 26 → ≤ 5 (C 类 COLOR_PIPELINE 保留)
- `npx tsc --noEmit` 0 errors
- DagEditorPage.tsx 无新增 lint 错误
