---
spec_id: spec-109
title: TD-330 sub-spec 17 — CustomSkillEditor.tsx hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: -
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-108]
blocks: []
priority: P2
size: 小 (1 文件 ~2 hex 治理, ~2 行 diff)
---

# spec-109: TD-330 sub-spec 17 — CustomSkillEditor.tsx hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 17 个 sub-spec。`frontend/src/pages/AI/CustomSkillEditor.tsx` 包含 2 处 hex color (antd v4 残留色):
- L366: `background: editingId === skill.id ? '#e6f7ff' : 'transparent'` (选中态浅蓝背景)
- L367: `border: editingId === skill.id ? '1px solid #91d5ff' : '1px solid transparent'` (选中态边框)

文件已用 `const { token } = antTheme.useToken();` (L175)。

## 治理方案

### A 类 (直接迁移 → antd token)

| 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|
| L366 | `#e6f7ff` | `token.colorPrimaryBg` | 选中态浅蓝背景 (v4 残留 → v5 token) |
| L367 | `#91d5ff` | `token.colorPrimaryBorder` | 选中态边框 (v4 残留 → v5 token) |

### C 类 (保留)

无 C 类保留 (2 hex 全为 antd 语义色对应)。

## 验收标准

- hex color 2 → 0 (无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorPrimaryBg/colorPrimaryBorder 与原 v4 hex 在默认主题下视觉接近)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
