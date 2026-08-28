---
spec_id: spec-76
title: TD-294 Phase 3b — 批量替换 4 文件 50 处 inline style → className
created: 2026-07-21
status: ✅ done
td: TD-294 (Phase 3b/4)
commit: -
---

# spec-76: TD-294 Phase 3b — 批量替换 inline style → className

## 范围评估 (Phase 3b)

spec-75 Phase 1 subagent 评估 4 文件 109 处 inline style; spec-76 L3-1 重新扫描确认 **108 处** (1 处统计差异), 可迁移 **50 处** (A 类 18 直接迁移 + B 类 32 部分迁移), 可迁移率 46.3%。C 类 58 处保留 (动态 token 26 / hex 11 / 一次性值 18 / 完全动态 7 / 缺工具类 9 / 组件特殊 4)。

## 目标文件

1. `frontend/src/pages/AI/LogAnalysisPanel.tsx` — 19 处可迁移 (7 A + 12 B)
2. `frontend/src/pages/Tasks/PipelineEditor/PipelineEditorPage.tsx` — 10 处可迁移 (3 A + 7 B)
3. `frontend/src/pages/Resources/TemplateAnnotation/LiveAnnotationTab.tsx` — 12 处可迁移 (5 A + 7 B)
4. `frontend/src/pages/AI/QAPanel.tsx` — 9 处可迁移 (3 A + 6 B)

## 迁移规则

- **A 类 (直接迁移)**: 整个 `style={{...}}` 替换为 className, 删除 style 属性
- **B 类 (部分迁移)**: 可迁移属性从 style 移除, 加 className; 保留属性继续留在 style={{}}
- **C 类 (保留)**: 不动, 保留原 inline style

## spec-75 新增 utility class (已可用)

- `.gaf-h-full` / `.gaf-flex-shrink-0` / `.gaf-overflow-y-auto` / `.gaf-whitespace-pre-wrap`
- `.gaf-text-13` / `.gaf-cursor-pointer`
- `.gaf-position-relative` / `.gaf-position-absolute`
- `.gaf-w-360` / `.gaf-radius-sm` / `.gaf-radius-md` / `.gaf-radius-lg`

## 实施策略

4 文件独立无依赖, 用 4 个并行 subagent 各负责 1 文件。每个 subagent 拿到详细评估报告 (行号 + 原 style + 迁移 class + 保留 style), 自己 Read 文件确认行号后 Edit。

## 验证

- `npx tsc --noEmit` → 0 errors
- `npx vitest run --reporter=dot` → 21 files 162 tests passed (不破坏现有)
- `grep "style={{" 4 文件` → 残留 ~58 处 (C 类保留, 与评估一致)

## 后续

- spec-77+: Phase 4 (toolbar → gaf-toolbar + hex 颜色治理)
