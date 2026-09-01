---
spec_id: spec-111
title: TD-330 sub-spec 19 — TemplateEffectiveness.tsx hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-110]
blocks: []
priority: P2
size: 小 (1 文件 ~1 hex 治理, ~3 行 diff)
---

# spec-111: TD-330 sub-spec 19 — TemplateEffectiveness.tsx hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 19 个 sub-spec。`frontend/src/pages/Resources/TemplateEffectiveness.tsx` 包含 1 处 hex color:
- L159: `style: record.degraded ? { backgroundColor: '#fff1f0' } : {}` (degraded 行错误背景)

文件未用 useToken(),需添加。

## 治理方案

### A 类 (直接迁移 → antd token)

| 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|
| L159 | `#fff1f0` | `token.colorErrorBg` | 错误背景浅红 |

### C 类 (保留)

无 C 类保留 (1 hex 为 antd 语义色对应)。

## 验收标准

- hex color 1 → 0 (无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorErrorBg 与原 #fff1f0 在默认主题下视觉一致)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
