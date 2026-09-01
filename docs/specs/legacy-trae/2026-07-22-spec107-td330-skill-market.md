---
spec_id: spec-107
title: TD-330 sub-spec 15 — SkillMarket.tsx hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-106]
blocks: []
priority: P2
size: 小 (1 文件 ~4 hex 治理, ~5 行 diff)
---

# spec-107: TD-330 sub-spec 15 — SkillMarket.tsx hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 15 个 sub-spec。`frontend/src/pages/AI/SkillMarket.tsx` 包含 4 处 hex color:
- L226: `<StarOutlined style={{ color: '#faad14' }} />` (rating 列,marketColumns)
- L309: `<StarOutlined style={{ color: '#faad14' }} />` (rating 列,myColumns)
- L439: `style={{ color: '#888' }}` (review modal skill_name)
- L479: `<StarOutlined style={{ color: '#faad14' }} />` (detail modal rating)

文件未用 useToken(),需添加。

## 治理方案

### A 类 (直接迁移 → antd token)

| 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|
| L226 | `#faad14` | `token.colorWarning` | 评分星星警告色 (antd 语义色) |
| L309 | `#faad14` | `token.colorWarning` | 同上 (myColumns) |
| L439 | `#888` | `token.colorTextTertiary` | 三级文本灰 (review modal) |
| L479 | `#faad14` | `token.colorWarning` | 同上 (detail modal) |

### C 类 (保留)

无 C 类保留 (4 hex 全为 antd 语义色对应)。

## 验收标准

- hex color 4 → 0 (无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorWarning/colorTextTertiary 与原 hex 在默认主题下视觉一致)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
