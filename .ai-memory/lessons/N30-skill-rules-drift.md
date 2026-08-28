---
date: 2026-07-07
symptom: [skill, rules, drift, documentation-sync, n95, lesson-router]
solution: Add bidirectional validation between SKILL.md and project_rules.md sections; run sync_skills.py --check before commit.
diff_keywords: ["skill", "project", "rules", "project_rules", "drift", "documentation-sync", "n95", "lesson-router"]
related_files:
  - .trae/skills/gaf-lesson-router/SKILL.md
  - .trae/rules/project_rules.md
created_by: AI
level: L1
n_id: N30
topic: doc-governance
---


# N30 — Skill SKILL.md 与 project_rules.md 章节漂移

> **来源**: gaf-restructure-foundation Stage 3d 评估（2026-07-07）
> **级别**: L1 可复用经验（架构反模式：文档同步漂移）
> **分发**: lessons + arch-mistakes + yn-matrices（3 层）

## 症状

`.trae/skills/gaf-lesson-router/SKILL.md` §3 步骤 5 写 "Run 5-layer distribution check (① lessons ② architecture-mistakes ③ spec ④ SKILL.md ⑤ project_rules.md)"，但 `project_rules.md §6.2` v8.5（2026-07-05 修订）已改为 L0/L1/L2 分级矩阵：L0=①lessons only / L1=①+②+④ / L2=all 5 layers。

两份文件长期漂移 2 天，AI 通过 lesson-router 加载 N95 教训时会看到过时的"5-layer"指引，强制把所有教训都分发到 5 层，违反 v8.5 "L0 默认 1 层"原则。

## 根因

v8.5 修订 project_rules.md §6.2 时，未同步更新 gaf-lesson-router/SKILL.md 的 N95 引用和步骤 5。两份文件是"引用关系"（lesson-router SKILL.md 引用 project_rules.md §6.2 的分级矩阵），但缺乏双向校验机制。

## 影响

- AI 按 lesson-router 的"5-layer"指引，强制把所有教训都分发到 5 层
- 违反 N132（文档职责分离）精神：rules 层是硬约束源，SKILL 层应同步
- 用户反馈"五层分发太麻烦"未被落地（lesson-router 仍指引 5 层）

## 修复

1. `.trae/skills/gaf-lesson-router/SKILL.md` L12 N95 行 "Load When" 列改为 "writing any new lesson / N95 L0/L1/L2 distribution (v8.5)"
2. `.trae/skills/gaf-lesson-router/SKILL.md` L74 步骤 5 改为 "Run N95 L0/L1/L2 distribution check per `project_rules.md §6.2` v8.5 matrix (L0=①lessons only / L1=①+②+④ / L2=all 5 layers). Decide level by asking 3 questions in order: (a) global AI hard rule? → L2; (b) Y/N checklist or arch antipattern? → L1; (c) one-off event? → L0."
3. 登记为 TD-020（P0，本轮已修，commit -）

## 预防

**Y/N 检查矩阵**（修改 project_rules.md 任一章节时必跑）：

| 修订 project_rules.md 章节 | 是否有 SKILL.md 引用？ | 必同步更新哪些 SKILL.md？ |
|---------------------------|:---------------------:|--------------------------|
| §0 执行宪法 | ✅ | gaf-orchestrator/SKILL.md（决策树 step_0） |
| §1 项目环境 | ❌ | 无 |
| §2 代码规范 | ❌ | 无 |
| §3 Git 操作规范 | ✅ | gaf-orchestrator/SKILL.md（commit 分支） |
| §4 变更操作规范 | ✅ | gaf-reflect-and-evolve/SKILL.md（反思矩阵） |
| §5 工具使用规范 | ❌ | 无 |
| §6 教训分发机制 | ✅ | gaf-lesson-router/SKILL.md（N95 分级） |
| §6.4 N## 教训索引表 | ✅ | gaf-lesson-router/SKILL.md（taxonomy 表） |
| §6.5 通用硬约束 | ✅ | 全部 5 个 gaf-* SKILL.md |

**校验机制建议**（后续 Phase 落地）：
- `sync_skills.py` 增加 `--rules-drift-check` 选项：提取 project_rules.md §N.M 章节号 + 关键词，与 5 份 gaf-* SKILL.md 中的引用做比对，不一致时 exit 1
- 类似决策树 5 份副本校验机制，扩展到 rules ↔ SKILL 引用校验

## 相关文件

- `d:\code\GAF\.trae\rules\project_rules.md` §6.2 v8.5 分级矩阵
- `d:\code\GAF\.trae\skills\gaf-lesson-router\SKILL.md` §3 N95 引用 + 步骤 5
- `d:\code\GAF\docs\general\tech-debt\README.md` TD-020
- `d:\code\GAF\docs\architecture\harness-layer-evaluation.md` §3 调研 2（发现源）

## 登记

- **时间**: 2026-07-07
- **发现于**: gaf-restructure-foundation Stage 3d 评估
- **修复于**: commit -（同 Stage 3 commit）
- **级别**: L1 可复用经验（架构反模式：文档同步漂移）
