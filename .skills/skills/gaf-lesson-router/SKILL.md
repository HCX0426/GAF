---
name: "gaf-lesson-router"
description: "Routes AI to the right lessons and collects new lessons at task end. Invoke when gaf-orchestrator needs lesson loading or end-of-task reflection."
version: 9.1
updated: 2026-08-21
---

# gaf-lesson-router — AI 教训路由与收集

> **v9.1 归一化**: §1 N## taxonomy 表已删除 (原 50 行 N91-N152 表), 改为引用 `failure-modes.md` 单一权威源。原表只到 N152 但 failure-modes.md 已有 N153-N167, 重复维护导致漂移。N## 索引统一在 `failure-modes.md` 维护, 本 skill 只负责加载路由 + 收集流程。

## 1. Lesson Taxonomy（错误分类 + 路径）

**N## 索引单一权威源**: `.ai-memory/meta/failure-modes.md` (50+ 条活跃 N## + 归档索引)

**加载流程**:
1. `Read .ai-memory/meta/failure-modes.md` 看 N## 索引表 (每条 1 行表格行: N## | 主题 | 硬约束 | Lesson 链接)
2. 按 task_type / 场景匹配 N## → Read 对应 lesson 文件
3. lesson 文件路径格式: `.ai-memory/lessons/<topic>_YYYY-MM-DD-n###-<short-name>.md` (含 `<topic>_` 前缀, 见 lessons/README.md Topic 分类索引)

**Topic 分组** (匹配 `yn-matrices/` 子目录, 7 个 active sub-file + 2 已合并孤儿):
- `workflow` — commit/hook/skill 治理 (N95/N96/N105/N108/N117/N121/N122/N123/N124/N125/N134/N140/N149/N164/N166; N114 dormant 合并到 N105; N91/N150)
- `ai-autonomy` — AI 决策/节奏/入口/推进 (N109/N111/N113/N115/N127/N151; N155 dormant Y/N 矩阵已迁 `_misc.md §12 platform-env`, spec-25 Phase 5 TD-248 修复 cross-topic 遗留)
- `honest-status` — 文档状态标记/审计 (N126/N128/N129/N130)
- `cross-layer-sync` — 路径漂移/前后端字段同步 (N106/N112/N142/N143/N152)
- `testing` — 测试套件环境依赖 (N118/N119/N142/N143/N147)
- `misc` — 并发 + 浏览器自动化 + 控制消息路由 (N116/N146/N131/N148)
- `refactor-dimensions` — N167 修改七维度评估
- `i18n` — 已合并到 ai-autonomy (N127 部分)
- `hook-failure` — 已合并到 workflow §7 (N91/N150)

> 完整 N## 索引 + 硬约束 + lesson 链接在 `failure-modes.md`; Y/N 检查矩阵在 `yn-matrices/_<topic>.md`。

## 2. Load Timing Matrix（加载时机）

| Task Type              | Must-Load Categories                                     |
|------------------------|----------------------------------------------------------|
| new_feature_backend    | api-contract, backend-conventions, tech-stack, cross-layer-sync |
| new_feature_frontend   | frontend-conventions, react-antd, tech-stack, cross-layer-sync |
| new_feature_agent      | agent-protocol, platform, tech-stack, cross-layer-sync |
| bug_fix                | failure-modes, version-compat, hook-failure, command-timeout, command-hang, test-environment |
| refactor               | architecture-mistakes, cross-layer-sync, concurrency, decision-tree |
| documentation          | docs-index, lesson-taxonomy (only if changing this skill) |
| task_complete          | rhythm-autonomy, bypass-review, distribution |

## 3. End-of-Task Collection（任务结束收集）

After a task completes (before commit):

1. Review files changed and failures encountered in this session.
2. If a new N##-class mistake occurred, create `GAF/.ai-memory/lessons/<topic>_YYYY-MM-DD-n###-<short-name>.md` (含 `<topic>_` 前缀, topic 见 lessons/README.md Topic 分类索引)。
3. Fill required sections: symptom, root cause, fix, prevention, related_files.
4. **Register the new lesson in `.ai-memory/meta/failure-modes.md`** (N## 索引单一权威源 — 在 Active N## 索引表末尾追加 1 行表格行, 4 列: `| N## | 主题 | 硬约束 | `lessons/<topic>_<date>-n<编号>-<slug>.md` |`)。**禁止**在本 SKILL.md 维护 N## 表 (v9.1 归一化: 已删除, 改为引用 failure-modes.md)。
5. Run N95 distribution check per `project_rules.md §6.2` v9.1 (L1-小/中/大 子分级): 问 2 个问题判定级别 → Q1 Y/N checklist OR arch antipattern? → L1; one-off event? → L0; Q2 (仅 L1): 改动规模决定 L1-小(2层)/L1-中(3层)/L1-大(5层, 含新 N##), 见 §6.2 表。
6. Run `python scripts/lessons/promote_lessons.py --dry-run` and propose promotion if high-frequency.

## 4. Path Convention

All lesson references use **relative paths from the workspace root**:

```
GAF/.ai-memory/lessons/N150-n153-pre-commit-stash-governance.md
```

No absolute paths. This keeps the skill portable across clones. (文件名格式: N<N>-<slug>.md, P1 改名后无 <topic>_ 前缀)

## 5. How gaf-orchestrator invokes this skill

- `load: <task_type>:<domain>` — returns the read list for that context.
- `collect` — runs the end-of-task collection checklist.

## 6. M3 diff-trigger 检索 (2026-08-15)

**被动检索补充**: 除主动 `load` 外, 每次 commit 后 pre-commit post-commit hook
`gaf-lesson-diff-trigger` 会自动跑 `python scripts/lessons/match_lessons_by_diff.py
--base HEAD~1 --head HEAD`, 按本次 diff 的路径 + 新增行匹配 lesson 的
`diff_keywords` front-matter 字段, 输出相关教训清单 (score 排序, 只提示不阻断).

**新 lesson 编写要求** (v9.1.1): 新建 lesson 时推荐补 `diff_keywords` 字段 —
非空小写字符串列表, 内容是"下一次这类改动会出现在 diff 里的词" (模块名/文件名/函数名/
错误 token/复合词如 `sql-injection`), 而非中文抽象词. 示例:

```yaml
diff_keywords: [sql-injection, cursor.execute, backup-restore]
```

- 字段缺失不报错 (check_lessons_updated.py warn-only)
- 校验规则: 字段存在时必须是非空 list, 每项非空字符串

检索脚本: `scripts/lessons/match_lessons_by_diff.py` (可指定文件/--json/--top)。
