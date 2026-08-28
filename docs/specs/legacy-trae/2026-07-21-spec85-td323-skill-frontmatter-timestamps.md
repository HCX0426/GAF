---
spec_id: spec-85
title: TD-323 — SKILL.md frontmatter 时间戳自动化
created: 2026-07-21
status: ✅ done
commit: -
related_td: [TD-323]
related_n: []
depends_on: []
blocks: []
priority: P1
size: 中 (扩展 sync_skills.py + 补 gaf-lesson-router frontmatter + 8 tests, ~559 行)
---

# spec-85: TD-323 — SKILL.md frontmatter 时间戳自动化

## 背景与问题

5 个 gaf-* SKILL.md 的 frontmatter `updated` 字段状态:
- gaf-orchestrator: `updated: 2026-07-17` (滞后, body 含 v9.5 2026-07-21 内容)
- gaf-knowledge-base: `updated: 2026-07-16` (滞后)
- gaf-task-execution: `updated: 2026-07-17` (滞后)
- gaf-reflect-and-evolve: `updated: 2026-07-17` (滞后)
- gaf-lesson-router: **缺 updated 字段**

AI/用户读 frontmatter 误判为旧版本, 但 body 实际已是最新; 违反 SSOT 原则.

## 修复方案

扩展 `scripts/bootstrap/sync_skills.py`:
1. 加 `--update-timestamps` 命令: 从 `git log -1 --format=%cs -- <SKILL.md>` 取最后修改日期, 更新 frontmatter `updated` 字段
2. 补 gaf-lesson-router frontmatter `updated` + `version` 字段
3. `--check` 模式扩展: 检测 `updated` 字段与 git log 不一致时 WARN (不阻塞)

辅助函数:
- `get_skill_last_commit_date(skill_md_path)`: 调 git log 取 `%cs` (committer date short, YYYY-MM-DD)
- `parse_frontmatter_updated(text)`: 解析现有 `updated:` 字段
- `update_frontmatter_updated(text, new_date)`: 替换 `updated:` 行 (或插入到 frontmatter 末尾)

## 实施清单

- [x] 扩展 `scripts/bootstrap/sync_skills.py`:
  - 新增 `--update-timestamps` 命令
  - 新增 `get_skill_last_commit_date()` / `parse_frontmatter_updated()` / `update_frontmatter_updated()` 辅助函数
  - `--check` 模式扩展: `updated` 字段与 git log 不一致 → WARN
- [x] 补 `gaf-lesson-router/SKILL.md` frontmatter `updated` + `version` 字段
- [x] 跑 `python scripts/bootstrap/sync_skills.py --update-timestamps` 同步 5 个 SKILL.md
- [x] 新建 `scripts/tests/test_sync_skills_timestamps.py` (8 tests):
  - parse_frontmatter_updated 解析 (×3 tests)
  - update_frontmatter_updated 替换 + 插入 (×3 tests)
  - get_skill_last_commit_date 真实 repo 集成 (×2 tests)
- [x] 迁移 TD-323 从 active.md 到 fixed.md
- [x] sync_tech_debt_counts.py 同步计数 (active=14, fixed=292, wontfix=30)
- [x] git add + commit (-, B2 is_big=false)
- [x] N176 hash 回填 (-)

## 验证标准

1. 5/5 SKILL.md frontmatter `updated` 字段与 git log last commit 一致
2. gaf-lesson-router 补 `updated` + `version` 字段
3. `sync_skills.py --update-timestamps` 命令存在并工作
4. `sync_skills.py --check` 检测 `updated` 字段不一致 → WARN
5. 3 tests 全通过

## N176 hash 回填

本 spec 完成后 commit hash 立即回填到此 frontmatter (TD-303 N176 规则).
