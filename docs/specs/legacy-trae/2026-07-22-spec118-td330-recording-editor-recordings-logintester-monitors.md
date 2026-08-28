---
spec_id: spec-118
title: TD-330 sub-spec 26 — 5 文件 hex color → antd token 治理 (RecordingStepper/Editor/RecordingsPage/AccountLoginTester/Monitors index)
created: 2026-07-22
status: ✅ done
commit: -
related_td: [TD-330]
related_n: [N167, N151]
depends_on: [spec-117]
blocks: []
priority: P2
size: 小 (5 文件 9 hex 治理, ~15 行 diff)
---

# spec-118: TD-330 sub-spec 26 — 5 文件 hex color → antd token 治理

## 背景

TD-330 全局 hex 治理第 26 个 sub-spec。合并治理 5 个文件共 9 处 hex color (每文件 1-2 hex,模式重复,合并高效):

### RecordingStepper.tsx (2 hex, L292)
- `#e6f4ff` (activeStepId 选中背景) → `token.colorPrimaryBg`
- `#f0f0f0` (步骤分隔线) → `token.colorBorderSecondary`

### Editor.tsx (2 hex, L219/L224)
- L219 `#d9d9d9` (边框) → `token.colorBorder`
- L224 `#f5f5f5` (背景) → `token.colorFillQuaternary`

### RecordingsPage.tsx (2 hex, L239/L316)
- L239 `#1677ff` (Badge color) → `token.colorPrimary`
- L316 `#f5f5f5` (pre 背景) → `token.colorFillQuaternary`

### AccountLoginTester.tsx (1 hex, L117)
- `#888` (testing 文本灰) → `token.colorTextTertiary`

### Monitors/index.tsx (2 hex, L687/L699)
- 2 处 `#999` (占位符 "-" 灰) → `token.colorTextTertiary`

## 治理方案

### A 类 (直接迁移 → antd token)

| 文件 | 行 | 原 hex | 替换 | 说明 |
|---|---|---|---|---|
| RecordingStepper.tsx | L292 | `#e6f4ff` | `token.colorPrimaryBg` | 主色背景 |
| RecordingStepper.tsx | L292 | `#f0f0f0` | `token.colorBorderSecondary` | 次级边框色 |
| Editor.tsx | L219 | `#d9d9d9` | `token.colorBorder` | 边框色 |
| Editor.tsx | L224 | `#f5f5f5` | `token.colorFillQuaternary` | 填充背景灰 |
| RecordingsPage.tsx | L239 | `#1677ff` | `token.colorPrimary` | 主色 (Badge color) |
| RecordingsPage.tsx | L316 | `#f5f5f5` | `token.colorFillQuaternary` | 填充背景灰 |
| AccountLoginTester.tsx | L117 | `#888` | `token.colorTextTertiary` | 三级文本灰 |
| Monitors/index.tsx | L687 | `#999` | `token.colorTextTertiary` | 三级文本灰 |
| Monitors/index.tsx | L699 | `#999` | `token.colorTextTertiary` | 三级文本灰 |

### 文件 useToken 状态

- RecordingStepper.tsx: 需检查/添加
- Editor.tsx: 需检查/添加
- RecordingsPage.tsx: 需检查/添加
- AccountLoginTester.tsx: 需检查/添加
- Monitors/index.tsx: 需检查/添加

### C 类 (保留)

无 C 类保留 (9 hex 全为 antd 语义色对应)。

## 验收标准

- hex color 9 → 0 (无 C 类保留,跨 5 文件)
- `npx tsc --noEmit` 0 errors
- 视觉等价

## 实施步骤

1. ✅ Phase 1: spec 文件创建
2. ✅ Phase 2: 代码改动 + tsc 检查
3. ✅ Phase 3: commit + N176 hash 回填
