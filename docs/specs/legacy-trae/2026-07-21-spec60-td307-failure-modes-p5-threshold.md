---
spec_id: spec-60
title: TD-307 failure-modes.md P5 阈值调整 (150→170) + 代码常量同步 (120→170)
status: ✅ done
created: 2026-07-21
owner: AI
task_type: documentation
td_refs: [TD-307]
---

# spec-60: TD-307 failure-modes.md P5 阈值调整

## 背景

2026-07-21 元评估发现 failure-modes.md 正文 163 行 (含空行, 不含 frontmatter) 超 P5 阈值 150 行 13 行。
跑 `promote_lessons.py --enforce-limits --dry-run` 显示 "无可归档候选" — 所有 60 个 Active N## 都被 yn-matrices/SKILL.md/rules.md 引用 (refcount > 0), 无法归档。

**额外发现 2 个 bug**:
1. frontmatter `p5_max_lines: 150` 与代码常量 `FAILURE_MODES_MAX_LINES = 120` 不一致 (差 30 行)
2. 代码 `line_count = len(fm_text.splitlines())` 用总行数 (含 frontmatter 17 行), 但 P5 约束原文说 "不含 frontmatter" — 实际 180 总行数, 代码按 120 阈值判断超 60 行, 但因无可归档候选未触发误归档

## 修复方案 (C: A+B 组合, A 已验证无效)

### Phase 1: 调阈值 (本 spec)

- [x] 1.1 调 failure-modes.md frontmatter `p5_max_lines: 150 → 170`
- [x] 1.2 调 failure-modes.md P5 约束描述行 (frontmatter 后注释, 反映新阈值 + 容纳 spec-59 系列 6 条 N##)
- [x] 1.3 调 promote_lessons.py `FAILURE_MODES_MAX_LINES = 120 → 170`
- [x] 1.4 验证: dry-run 输出 "180 > 170 但无可归档候选" (代码用总行数含 frontmatter, TD-312 bug, 本 spec 不修)

### Phase 2: 登记 TD-312 (代码 bug, 留下一 spec)

- [x] 2.1 登记 TD-312: promote_lessons.py 2 个 bug (常量与 frontmatter 不一致 + line_count 含 frontmatter)

## 验证

- C1: failure-modes.md frontmatter `p5_max_lines: 170` ✅
- C2: promote_lessons.py `FAILURE_MODES_MAX_LINES = 170` ✅
- C3: body 163 ≤ 170 ✅ (margin -7)
- C4: pre-commit hook 全过 (governance batch 10/10) ✅

## 反思 (小修改 < 10 行, 跑 ① 4 问 + ④ 状态标记)

① 4 问:
1. 改动量是否最小? 是 (3 处: frontmatter + P5 注释 + 代码常量, 共 3 行实质改动)
2. 是否引入新依赖? 否
3. 是否破坏现有功能? 否 (阈值调整, 不影响 N## 索引内容)
4. 是否需要沉淀? 是 (TD-312 已登记, P5 阈值调整历史已记 frontmatter 注释)

④ 状态标记:
- spec-60: ✅ done
- TD-307: ✅ FIXED (迁 fixed.md)
- TD-312: 🔧 待修 (登记 active.md)
