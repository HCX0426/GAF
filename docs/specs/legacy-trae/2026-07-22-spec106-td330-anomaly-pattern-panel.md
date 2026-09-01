---
spec_id: spec-106
title: TD-330 sub-spec 14 — AnomalyPatternPanel.tsx hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-105]
blocks: []
priority: P2
size: 小 (1 文件 ~4 hex 治理, ~15 行 diff)
---

# spec-106: TD-330 sub-spec 14 — AnomalyPatternPanel.tsx hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 14 个 sub-spec。`frontend/src/pages/AI/AnomalyPatternPanel.tsx` 包含 4 处 hex color,全在 SEVERITY_CONFIG 常量 (L40-45):
- critical: `#f5222d`
- high: `#ff4d4f`
- medium: `#faad14`
- low: `#52c41a`

文件已用 `const { token } = antTheme.useToken();` (L59),L152/L180/L230 已用 token.colorError/colorBgLayout。

SEVERITY_CONFIG 用于:
- L173: `<Tag color={SEVERITY_CONFIG[pattern.severity]?.color}>` (Tag color prop)
- L207: `<Progress strokeColor={cfg.color}>` (Progress strokeColor prop)

## 治理方案

### A 类 (直接迁移 → antd token)

SEVERITY_CONFIG → `getSeverityConfig(token)` 函数化:

| severity | 原 hex | 替换 | 说明 |
|---|---|---|---|
| critical | `#f5222d` | `token.colorErrorActive` | 更深红 (active state),符合 critical > high 视觉层级 |
| high | `#ff4d4f` | `token.colorError` | 错误语义色 |
| medium | `#faad14` | `token.colorWarning` | 警告语义色 |
| low | `#52c41a` | `token.colorSuccess` | 成功语义色 |

### C 类 (保留)

无 C 类保留 (4 hex 全为 antd 语义色对应)。

## 验收标准

- hex color 4 → 0 (无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorErrorActive/colorError/colorWarning/colorSuccess 与原 hex 在默认主题下视觉一致,critical 比 high 更深红)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
