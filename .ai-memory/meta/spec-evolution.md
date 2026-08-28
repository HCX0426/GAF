---
maintainer: manual
source: GAF/.ai-memory/meta/spec-evolution.md
load_when:
- spec 改版
- spec ↔ code 不一致
- 旧 spec 引用
- 反思历史决策
- 季度决策树 review (§6 模板)
priority: low
symptom:
- kb:spec-evolution
- spec-version
- spec-drift
- spec-deprecation
- quarterly-review
solution: v8.x 历史摘要 + v9.x 指针 + §6 季度 review 模板 (M1.H 闭环, N117); v9.x 详细变更见 failure-modes.md / archived-lessons.md / decision-tree-changelog.md
related_files:
- .ai-memory/meta/docs-index.md
- .ai-memory/summaries/architecture-mistakes.md
- .ai-memory/meta/failure-modes.md
- .ai-memory/meta/archived-lessons.md
- .trae/skills/gaf-orchestrator/_shared/decision-tree-changelog.md
created_by: AI
last_updated: 2026-07-18
---

# GAF Spec 演进史 (v9.1 简化版 — TD-139 修复 2026-07-18)

> **用途**: (1) 旧 v8.x spec 引用映射; (2) 季度决策树 review 模板 (§6, M1.H 闭环 N117)
> **覆盖**: v8.0 → v8.4 (2026-05-30 → 2026-06-16) 历史摘要 + v9.x 指针
> **原则**: spec 改动必须留痕, 旧 spec 引用要可映射; v9.x 详细变更由 decision-tree-changelog.md 自动记录

---

## 1. v8.x 演进时间线 (历史摘要)

| 版本 | 日期 | 阶段 | 关键变更 | commit |
|:----:|:----:|------|---------|:------:|
| **v8.0** | 2026-05-30 | 初始 | 顶层 11 文件 + 5 skills + 1 rule 体系建立 | `-` |
| **v8.1** | 2026-06-01 | 闭环 | N95 5 层分发机制实装 | `-` |
| **v8.2** | 2026-06-08 | 安全 | 路径一致性 + 锁机制 + N82 审计 | `-` |
| **v8.3** | 2026-06-15 | 知识库 | (动态计数 docs) 分组索引 + N104 过期文档警告 | `-` |
| **v8.4** | 2026-06-16 | 闭环 | M0.M 5 层分发硬约束 + M0.N N105 hook 透传修复 + M1.A .ai-memory 顶层 + meta/rules/games/platforms 补全 | `-` |

> v8.x 详细变更记录见 git log (2026-05-30 ~ 2026-06-16); v9.0+ 重构后大部分 v8.x 机制已被替代, 仅保留时间线作历史参考

---

## 2. v9.x 演进 (当前 — 详细变更见外部 changelog)

| 版本 | 日期 | 关键变更 | 权威源 |
|:----:|:----:|---------|--------|
| **v9.0** | 2026-07-07 | gaf-workflow-v9-slim 闭环: 决策树单一权威源 + L0/L1 真二分制 + lessons topic 分类 + archived-early/ 子目录 | `failure-modes.md` + `archived-lessons.md` |
| **v9.1** | 2026-07-14 | project_rules.md 瘦身 (N## 索引迁到 failure-modes.md) + 5 组家族合并 + N140 文件命名规则 | `failure-modes.md` §归档流程 |
| **v9.1+** | 2026-07-16~18 | N165-N171 新教训 + Y/N 矩阵 sub-file 分片 (8 个) + spec 粒度提交 + L3 循环 + 七维度评估 | `decision-tree-changelog.md` (自动) |

> v9.x 决策树变更由 `sync_skills.py --changelog` 自动记录到 `gaf-orchestrator/_shared/decision-tree-changelog.md`, 不再手工维护本文件

---

## 3. 旧 spec 引用映射表 (v8.x → v9.x)

| 旧引用 (v8.x) | 新路径 (v9.x) | 说明 |
|--------|--------|------|
| `.ai-memory/sync-state.json` (仓库根) | `.ai-memory/sync-state.json` | N106 修复: 移到 .ai-memory/ 下 |
| `.trae/specs/...` (related_files) | `docs/specs/legacy-trae/...` 或 `docs/specs/active/...` | hook 解析: 路径基于 GAF 根; spec-2026-07-26-trae-specs-plans-merge 迁移 .trae/specs/ → docs/specs/legacy-trae/ + 新 spec 流程用 docs/specs/active/ |
| `git commit` (需用户授权) | `git commit` (AI 自执行, spec 粒度) | N108 放开 + §3.4 spec 粒度提交 |
| `gaf-commit.sh --no-verify` | `git commit --no-verify` (仅 N105 透传场景) | N105 透传 bug, 绕开兜底脚本; §3.3 禁止滥用 |
| `evidence/templates/{problem,solution,verification}.md` (today dir) | `evidence/{date}/_session_*.md` | hook 强校验 today dir 模板占位符 |
| `specs/` (历史 spec) | `docs/specs/legacy-trae/` (历史) + `docs/specs/active/` (新) | TD-178 修正: 已迁至 .trae/specs/; spec-2026-07-26-trae-specs-plans-merge 再迁到 docs/specs/ |
| `project_rules.md §6.4 N## 索引` | `failure-modes.md` §Active/Dormant/Retired | v9.1 归一化: 单一权威源在 failure-modes.md |
| `project_rules.md §6.5 通用硬约束` | `ai-operating-handbook.md` Part 2 | v9.3 合并: AI 行为红线 43 条 |
| `loading-strategy.md` + `ai-behavior-redlines.md` | `ai-operating-handbook.md` | v9.3 合并为单一 L2 文件 |

---

## 4. 改 spec 流程 (AI 必读)

### 4.1 改 spec 前必做 3 问

1. **是 spec 错了还是 code 错了?** (N95 双向验证)
2. **改后旧引用怎么办?** (本表 §3 映射)
3. **要不要分发到 5 层?** (N95 5 层分发硬约束, v9.0 后按 L0/L1 真二分制分级)

### 4.2 改 spec 后必做 5 步

1. **决策树 changelog**: 跑 `python scripts/bootstrap/sync_skills.py --changelog --note "<描述>"` (自动追加到 decision-tree-changelog.md)
2. **更新映射表**: 本文件 §3 加旧引用 → 新路径 (如有路径变更)
3. **更新 docs-index**: 重跑 `python scripts/bootstrap/sync_docs_index.py`
4. **分发 (按规模分级)**: L1-小 (2 层) / L1-中 (3 层) / L1-大 (5 层), 见 `project_rules.md §6.2`
5. **反思 + 沉淀**: 跑 `gaf-reflect-and-evolve` 分级反思 (中=5 项 / 大=24 项+L1 分发)

---

## 5. 🆕 M1.H: 季度 review 提示

> **来源**: M1.H 决策树 changelog + 季度 review (2026-06-16 闭环, N117)
> **触发**: 每季度 (1/1, 4/1, 7/1, 10/1) 跑一次 `python scripts/bootstrap/sync_skills.py --changelog --note "Q{1-4} 2026 review"`

### 5.1 review 必做 5 步

1. **决策树 step 数量检查**: 当前决策树 step 数 (含 new_feature/bug_fix/documentation/refactor/unknown 5 大分支) 是否 < 20? > 20 考虑拆 skill
2. **task_type 分支覆盖**: 5 类 (new_feature/bug_fix/documentation/refactor/unknown) 是否仍够用? 出现新类型 (如 `migration` / `incident` / `audit`) 考虑加分支
3. **反模式覆盖**: 决策树是否包含最近的高频反模式? (N96 L2 跳过 / N115 入口自决 / N116 协作冲突 / N117 changelog 遗漏 / N166 L3 循环 / N167 七维度评估)
4. **KB 路径存在性**: 决策树 hard-load 的 .ai-memory/ 文件是否仍存在? (`sync_ai_memory.py --query` 抽查)
5. **changelog 漂移**: 最近 90 天 changelog entries 数 vs 实际 commit 数 (gaf-orchestrator SKILL.md 改了几次), 比例应 ≥ 80%

### 5.2 review 输出模板

review 完成后, 在本节追加一段:

```markdown
### Q{1-4} {year} review ({date})

- 决策树 step 数: {N} (< 20 ✅)
- task_type 分支: 5 类 {covered/gap}
- 反模式覆盖: N96/N115/N116/N117/N166/N167 全部进决策树 ✅ / ❌
- KB 路径: 4 文件全存在 ✅ / ❌
- changelog 漂移: 90 天 {N} entries / {M} commit, 比例 {P}%
- 下季度行动: {list}
```

### 5.3 review 跳过条件 (A/B/C 分类)

- [A] 立即修: 决策树反模式遗漏 (N## 家族成员未进决策树)
- [B] 后续: task_type 新分支需求 (用户提了但 spec 没写)
- [C] 无法解决: 决策树 step 数 > 20 (拆 skill = 大型重构, 需 M2 阶段)

---

## 6. 历史回顾 (v8.x 详细记录 — 已简化)

> v8.x 详细变更记录 (§2.1-§2.5 v8.0~v8.4 各版本细节 + §3 兼容性矩阵 + §5.3 旧 spec 引用处理) 已在 TD-139 修复 (2026-07-18) 时简化, 因 v9.0+ 重构后大部分 v8.x 机制已被替代。如需查看 v8.x 完整历史, 见 git log 2026-05-30 ~ 2026-06-16 commit 历史。
