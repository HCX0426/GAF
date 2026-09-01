---
spec_id: spec-115
title: TD-330 sub-spec 23 — StepConfigureInfra.tsx hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-114]
blocks: []
priority: P2
size: 小 (1 文件 4 hex 治理, ~8 行 diff)
---

# spec-115: TD-330 sub-spec 23 — StepConfigureInfra.tsx hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 23 个 sub-spec。`frontend/src/pages/Setup/StepConfigureInfra.tsx` 包含 4 处 hex color:
- L83: `borderBottom: '1px solid #f0f0f0'` (健康项列表分隔线)
- L86: `color: '#666', fontSize: 13` (健康项消息文本)
- L99: `background: '#f6f8fa'` (信息卡片背景)
- L106: `background: '#fff2f0', border: '1px solid #ffccc7'` (失败提示卡片背景+边框)

文件未用 useToken(),需在 `StepConfigureInfra` 组件添加。

## 治理方案

### A 类 (直接迁移 → antd token)

| 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|
| L83 | `#f0f0f0` | `token.colorBorderSecondary` | 次级边框色 |
| L86 | `#666` | `token.colorTextSecondary` | 二级文本灰 |
| L99 | `#f6f8fa` | `token.colorBgLayout` | 布局背景灰 (GitHub 风格浅灰 → antd layout 背景) |
| L106 | `#fff2f0` | `token.colorErrorBg` | 错误背景色 |
| L106 | `#ffccc7` | `token.colorErrorBorder` | 错误边框色 |

### C 类 (保留)

无 C 类保留 (4 处 hex 全为 antd 语义色对应)。

## 验收标准

- hex color 4 → 0 (无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorBorderSecondary/colorTextSecondary/colorBgLayout/colorErrorBg/colorErrorBorder 与原 hex 在默认主题下视觉一致)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
