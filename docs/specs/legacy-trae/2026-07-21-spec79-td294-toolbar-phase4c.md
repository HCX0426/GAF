---
spec_id: spec-79
title: TD-294 Phase 4c — 中优 6 文件 toolbar → gaf-toolbar utility class
created: 2026-07-21
status: ✅ done
td: TD-294 (Phase 4c/4)
commit: -
---

# spec-79: TD-294 Phase 4c — toolbar → gaf-toolbar

## 范围评估 (Phase 4c)

spec-78 ✅ Phase 4b 完成 (5 文件 21 处 toolbar → gaf-toolbar)。Phase 4c 目标: 中优 6 文件 toolbar 区域迁移到 gaf-toolbar utility class。

## 评估结果 (L3-1 subagent 扫描)

从 8 候选文件中挑选 6 个, 共 26 处可迁移 (A 类 8 + B 类 18):

| 文件 | A 类 | B 类 | 可迁移 |
|------|:---:|:---:|:---:|
| ConfigManagementPage.tsx | 2 | 6 | 8 |
| EmulatorManagementPage.tsx | 2 | 3 | 5 |
| Marketplace.tsx | 2 | 3 | 5 |
| WindowManagementPage.tsx | 0 | 4 | 4 |
| DeviceCenterPage.tsx | 2 | 0 | 2 |
| UnattendedControlBar.tsx | 2 | 0 | 2 |
| **总计** | **8** | **18** | **26** |

落选: SystemSettings.tsx (1 处, 大量垂直 Space) / Tasks/index.tsx (1 处)。

3 路并行 subagent:
- 路径 A: ConfigManagementPage + UnattendedControlBar (10 处)
- 路径 B: EmulatorManagementPage + DeviceCenterPage (7 处)
- 路径 C: Marketplace + WindowManagementPage (9 处)

## gaf-toolbar utility class 体系

```css
.gaf-toolbar { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; padding: 8px 12px; min-height: 40px; }
.gaf-toolbar-group { display: flex; align-items: center; gap: 4px; padding: 0 8px; }
.gaf-toolbar-divider { width: 1px; height: 20px; background: var(--colorBorderSecondary, #e5e5e5); flex-shrink: 0; }
.gaf-toolbar-spacer { flex: 1 1 100%; min-width: 8px; }
```

## 迁移规则

- A 类 (直接迁移): toolbar 容器 `<Space>` 或 `style={{ display: 'flex', ... }}` → `className="gaf-toolbar"` 或 `gaf-toolbar-group`
- B 类 (部分迁移): 部分属性迁移, 保留动态值/不匹配值
- C 类 (保留): 非 toolbar / 垂直 Space / 动态值

## 后续

Phase 4c 完成后, TD-294 全部 Phase (1/2/3a/3b/4a/4b/4c) 结束, 评估是否闭环。
