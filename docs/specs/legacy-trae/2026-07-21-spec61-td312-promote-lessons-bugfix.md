---
spec_id: spec-61
title: TD-312 promote_lessons.py 2 bug 修复 (line_count 含 frontmatter + 常量与 frontmatter 无同步)
status: ✅ done
created: 2026-07-21
owner: AI
task_type: bug_fix
td_refs: [TD-312]
---

# spec-61: TD-312 promote_lessons.py 2 bug 修复

## 背景

spec-60 执行 TD-307 时发现 promote_lessons.py 的 `enforce_failure_modes_limit` 函数有 2 个 bug:
1. **bug 1 (常量不同步)**: 代码常量 `FAILURE_MODES_MAX_LINES` 与 frontmatter `p5_max_lines` 长期不同步 (spec-60 前差 30 行)
2. **bug 2 (line_count 含 frontmatter)**: `line_count = len(fm_text.splitlines())` 用总行数 (含 frontmatter 17 行), 但 P5 约束原文 "本文件正文 ≤ p5_max_lines 行 (不含 frontmatter)"

## 修复方案 (A+B 组合)

### Phase 1: 修 enforce_failure_modes_limit 函数

- [x] 1.1 用 `parse_front_matter` 解析 failure-modes.md, 得到 (data, body, had_front_matter)
- [x] 1.2 `body_line_count = len(body.splitlines())` (不含 frontmatter)
- [x] 1.3 `max_lines = int(data.get("p5_max_lines", FAILURE_MODES_MAX_LINES))` (从 frontmatter 读取, fallback 用常量)
- [x] 1.4 用 `body_line_count` + `max_lines` 替代原 `line_count` + `FAILURE_MODES_MAX_LINES` 做判断
- [x] 1.5 更新常量注释 (TD-312 已修, 常量降为 fallback)

### Phase 2: 验证

- [x] 2.1 dry-run 输出 "✅ failure-modes.md body 163 ≤ 170 行 (p5_max_lines), 无需归档" (body 行数, 不是总行数) ✅
- [x] 2.2 无现成 test_promote_lessons.py, dry-run 验证逻辑正确 (小修改豁免全套, N177)

## 验证

- C1: dry-run 输出 body 163 (而非总行数 180) ✅
- C2: dry-run 输出 "≤ 170 (p5_max_lines)" (从 frontmatter 读取) ✅
- C3: pre-commit hook 全过 ✅
- C4: 循环模式第 2 spec, spec-60+spec-61 均小修改 (文档+scripts/), 按 N177 小修改豁免全套; 全套回归推迟到下一中/大修改 spec

## 反思 (小修改 < 20 行, 跑 ① 4 问 + ④ 状态标记)

① 4 问:
1. 改动量是否最小? 是 (1 函数 + 1 常量注释, 约 15 行实质改动)
2. 是否引入新依赖? 否 (复用已有 parse_front_matter)
3. 是否破坏现有功能? 否 (dry-run 验证逻辑正确, fallback 机制保留)
4. 是否需要沉淀? 否 (bug 修复, TD-312 已登记, 无新反模式)

④ 状态标记:
- spec-61: ✅ done
- TD-312: ✅ FIXED (待迁 fixed.md)
- TD-307: ✅ FIXED (spec-60 已迁 fixed.md)
