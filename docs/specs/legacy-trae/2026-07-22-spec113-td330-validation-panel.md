---
spec_id: spec-113
title: TD-330 sub-spec 21 — ValidationPanel.tsx hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-112]
blocks: []
priority: P2
size: 小 (1 文件 ~4 hex 治理 + Text 函数重构, ~20 行 diff)
---

# spec-113: TD-330 sub-spec 21 — ValidationPanel.tsx hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 21 个 sub-spec。`frontend/src/pages/Resources/ValidationPanel.tsx` 包含 4 处 hex color:
- L153: `styles={{ content: { color: '#52c41a' } }}` (Statistic ok 绿色)
- L158: `styles={{ content: { color: '#faad14' } }}` (Statistic partial 黄色)
- L163: `styles={{ content: { color: '#999' } }}` (Statistic stale 灰色)
- L184: `<span style={{ color: secondary ? '#999' : undefined, ...style }}>` (Text 辅助组件 secondary 灰色)

文件未用 useToken(),需添加。L182-188 是内部 `Text` 辅助函数 (非 antd Typography.Text),接受 `secondary` prop。

## 治理方案

### A 类 (直接迁移 → antd token)

| 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|
| L153 | `#52c41a` | `token.colorSuccess` | 成功语义色 |
| L158 | `#faad14` | `token.colorWarning` | 警告语义色 |
| L163 | `#999` | `token.colorTextTertiary` | 三级文本灰 |
| L184 | `#999` | 删除 (Text 函数移除) | 三级文本灰 (Text 函数) |

### C 类 (保留)

无 C 类保留 (4 hex 全为 antd 语义色对应)。

### Text 辅助函数处理

L182-188 的 `Text` 函数是 module-level 辅助组件,唯一使用点 L116 `<Text secondary>`。直接删除该函数,将 L116 改为 `<Typography.Text type="secondary">` (antd 原生组件,语义等价)。

## 验收标准

- hex color 4 → 0 (无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorSuccess/colorWarning/colorTextTertiary 与原 hex 在默认主题下视觉一致)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
