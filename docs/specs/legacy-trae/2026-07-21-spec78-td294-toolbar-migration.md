---
spec_id: spec-78
title: TD-294 Phase 4b — 高优 5 文件 toolbar → gaf-toolbar utility class
created: 2026-07-21
status: ✅ done
td: TD-294 (Phase 4b/4)
commit: '-'
---

# spec-78: TD-294 Phase 4b — toolbar → gaf-toolbar

## 范围评估 (Phase 4b)

spec-77 ✅ Phase 4a 完成 (4 文件 hex → antd design token)。Phase 4b 目标: 高优 5 文件 toolbar 区域的 inline style 迁移到 gaf-toolbar utility class。

## 目标文件 (5 个)

1. `frontend/src/pages/Resources/TemplateAnnotation/LiveAnnotationTab.tsx`
2. `frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx`
3. `frontend/src/pages/Ops/ScheduledTasks/DagEditorPage.tsx`
4. `frontend/src/pages/Accounts/GameAccountsPage.tsx`
5. `frontend/src/pages/Resources/TemplateGallery.tsx`

## gaf-toolbar utility class 体系 (spec-75 已扩展)

```css
.gaf-toolbar { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; padding: 8px 12px; min-height: 40px; }
.gaf-toolbar-group { display: flex; align-items: center; gap: 4px; padding: 0 8px; }
.gaf-toolbar-divider { width: 1px; height: 20px; background: var(--colorBorderSecondary, #e5e5e5); flex-shrink: 0; }
.gaf-toolbar-spacer { flex: 1 1 100%; min-width: 8px; }
```

## 迁移规则

- **A 类 (直接迁移)**: toolbar 容器的 `style={{ display: 'flex', ... }}` → `className="gaf-toolbar"` (或加 gaf-toolbar-group)
- **B 类 (部分迁移)**: 可迁移属性从 style 移除, 加 className; 保留属性继续留在 style
- **C 类 (保留)**: 非 toolbar 区域 / 动态值 / 缺工具类 → 保留原 inline style

## 评估结果 (L3-1 subagent 扫描)

5 文件 21 处可迁移 (A 类 11 + B 类 10 + C 类 3 保留):

| 文件 | A 类 | B 类 | 可迁移 |
|------|:---:|:---:|:---:|
| LiveAnnotationTab.tsx | 5 | 3 | 8 |
| ExecutionMonitorPanel.tsx | 2 | 4 | 6 |
| DagEditorPage.tsx | 1 | 2 | 3 |
| GameAccountsPage.tsx | 1 | 1 | 2 |
| TemplateGallery.tsx | 2 | 0 | 2 |
| **总计** | **11** | **10** | **21** |

B 类保留原因: 装饰性 background/borderBottom / dark theme 颜色 / minHeight 不一致 (48 vs 40) / padding 不一致 (6px 16px vs 8px 12px)。

C 类保留: DagEditorPage sidebar header (非 toolbar) / GameAccountsPage 表格 actions 列 / TemplateGallery 主 Row+Col 栅格模式。

## 实施策略

3 路并行 subagent (按工作量平衡):
- Subagent A: LiveAnnotationTab + ExecutionMonitorPanel (8+6=14 处)
- Subagent B: DagEditorPage + GameAccountsPage (3+2=5 处)
- Subagent C: TemplateGallery (2 处)

## 验证

- `npx tsc --noEmit` → 0 errors
- `npx vitest run --reporter=dot` → 现有测试不破坏
- `grep "gaf-toolbar" 5 文件` → 使用点增加

## 后续

- spec-79: Phase 4c — 中优 6 文件 toolbar → gaf-toolbar
