---
spec_id: spec-114
title: TD-330 sub-spec 22 — SpecialtyLogTabs.tsx hex color → antd token 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-113]
blocks: []
priority: P2
size: 小 (1 文件 6 hex 治理, ~15 行 diff)
---

# spec-114: TD-330 sub-spec 22 — SpecialtyLogTabs.tsx hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 22 个 sub-spec。`frontend/src/pages/Ops/Logs/SpecialtyLogTabs.tsx` 包含 6 处 hex color,全部位于 `ArchiveLogTab` 组件的 `renderAnalysisResults` 内部函数中:
- L572: `color: '#999'` (无分析结果提示文本)
- L594: `border: '1px solid #f0f0f0', borderRadius: 6` (分析结果卡片边框)
- L598: `color: '#999'` (模型名文本)
- L600: `color: '#999'` (置信度文本)
- L609: `background: '#fafafa', borderRadius: 6` (result JSON 展示块背景)
- L622: `color: '#666'` (suggestions 文本)

文件未用 useToken(),需在 `ArchiveLogTab` 组件添加。

## 治理方案

### A 类 (直接迁移 → antd token)

| 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|
| L572 | `#999` | `token.colorTextTertiary` | 三级文本灰 |
| L594 | `#f0f0f0` | `token.colorBorderSecondary` | 次级边框色 |
| L598 | `#999` | `token.colorTextTertiary` | 三级文本灰 |
| L600 | `#999` | `token.colorTextTertiary` | 三级文本灰 |
| L609 | `#fafafa` | `token.colorBgLayout` | 布局背景灰 |
| L622 | `#666` | `token.colorTextSecondary` | 二级文本灰 |

### B 类 (utility class 替代)

L594 和 L609 的 `borderRadius: 6` 同步迁移到 `gaf-radius-md` className (TD-294 Phase 3a utility class),与 spec-108 AccountGroupManager 治理模式一致。

### C 类 (保留)

无 C 类保留 (6 hex 全为 antd 语义色对应)。

## 验收标准

- hex color 6 → 0 (无 C 类保留)
- `npx tsc --noEmit` 0 errors
- 视觉等价 (colorTextTertiary/colorBorderSecondary/colorBgLayout/colorTextSecondary 与原 hex 在默认主题下视觉一致)

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
