# spec-27: 文件夹重构 (plans/specs/architecture → .trae/)

> **创建时间**: 2026-07-18
> **来源**: 用户反馈 2026-07-18 — "`/d:/code/GAF/docs/general/plans``/d:/code/GAF/docs/general/specs`这两个不应该放在`/d:/code/GAF/.trae`这下面的吗，为啥会在docs里，有过时的或者完成的，都可以删掉了`/d:/code/GAF/docs/architecture`，这个还要不要呢，还是移动到`/d:/code/GAF/.trae/`？"
> **状态**: ✅ Phase 1-3 完成, Phase 4 同步更新待办登记

## 阶段状态表

| Phase | 内容 | 状态 | 完成时间 | Commit |
|:-----:|------|:---:|:----:|:----:|
| Phase 1 | 子 agent 评估 71 个文件 (plans 5 + specs 54 + architecture 9) | ✅ | 2026-07-18 | - |
| Phase 2 | 创建批量删除脚本 `.trash/batch_cleanup.py` | ✅ | 2026-07-18 | - |
| Phase 3 | 执行脚本迁移 68 项 + 恢复 spec25/26 到 .trae/specs/ | ✅ | 2026-07-18 | - |
| Phase 4 | 同步更新待办登记 (跨文件路径引用) | ✅ | 2026-07-18 | - + - (TD-251 follow-up) | 立即同步完成 + TD-251 已登记 (P3, 跨 spec 待办) |

## 背景

用户反馈: `docs/general/plans` + `docs/general/specs` + `docs/architecture` 这三个文件夹是 AI 工作产物, 应放在 `.trae/` 下而非 `docs/`。`docs/` 应只保留用户可读文档 (analysis/design/standards/tech-debt)。过时/完成的文件可删除。

spec-26 已在 §2.1 文档分层规则中确立归属原则:
- `.trae/` = AI 工作产物 (rules/skills/plans/specs/architecture-evaluation)
- `docs/` = 用户可读文档 (analysis/design/standards/tech-debt)
- `.ai-memory/` = AI 记忆 (lessons/evidence/meta)

本 spec 执行文件夹重构。

## Phase 1: 子 agent 评估

子 agent 评估三个文件夹的所有文件:
- `docs/general/plans/`: 5/5 全部删除 (所有计划已完成)
- `docs/general/specs/`: 54 删除 + 2 保留迁移 (spec-25/spec-26 活跃)
- `docs/architecture/`: 9/9 全部删除 (所有评估/计划已落地)
- 总计: 68 个文件/目录移到 `.trash/spec27-cleanup/`, 2 个迁移到 `.trae/specs/`

## Phase 2: 批量删除脚本

创建 `.trash/batch_cleanup.py`, 包含:
- 5 个 plans 项
- 9 个 architecture 项 (2 目录 + 7 文件)
- 54 个 completed specs (排除 spec25/spec26)
- 冲突处理 (suffix counter)
- 空目录清理

## Phase 3: 执行迁移

执行 `batch_cleanup.py`:
- ✅ 68 项移动到 `.trash/spec27-cleanup/`
- ✅ `docs/general/plans/` 空目录已删除
- ✅ `docs/architecture/` 空目录已删除
- ✅ 创建 `.trae/specs/` + `.trae/plans/` + `.trae/architecture/` 目录
- ⚠️ spec25/spec26 因 Trae safe_rm wrapper 拦截 Move-Item 丢失, 用 `git show HEAD:path` 恢复到 `.trae/specs/`
- ✅ `docs/general/specs/` 空目录已删除

**迁移后状态**:
- `.trae/specs/`: spec25 + spec26 + spec27 (本文件)
- `.trae/plans/`: 空 (为未来使用)
- `.trae/architecture/`: 空 (为未来使用)

## Phase 4: 同步更新待办

### 立即同步 (本 spec commit 前)

- ✅ `project_rules.md §4.10` 路径 `docs/general/specs/` → `.trae/specs/`
- ✅ `project_rules.md §2.1` 文档分层规则表已含 `.trae/specs/` (spec-26 已更新)

### 跨 spec 待办 (登记到 active.md)

以下文件引用旧路径 `docs/general/specs/` / `docs/general/plans/` / `docs/architecture/`, 需在后续 spec 中批量更新:

**必改 (活跃规则/索引)**:
- `.trae/skills/gaf-orchestrator/SKILL.md`
- `.trae/skills/gaf-reflect-and-evolve/SKILL.md`
- `.trae/skills/gaf-knowledge-base/SKILL.md`
- `.ai-memory/meta/docs-index.md`
- `.ai-memory/meta/yn-matrices/_workflow.md`
- `scripts/README.md`
- `scripts/hooks/check_spec_consistency.py`
- `scripts/bootstrap/sync_skills.py`

**评估后改 (可能含历史引用)**:
- `docs/general/tech-debt/active.md` (顶部清单已更新, 各 TD 内部历史引用保留)
- `docs/general/pending-roadmap.md`
- `docs/general/completed-features.md`
- `.ai-memory/ops/completed-features.md`
- `docs/general/design/input-mode-and-window-wait-design.md`
- `docs/standards/backend-conventions.md`
- `scripts/select_reflection_checks.py`
- `scripts/tests/test_select_reflection_checks.py`
- `scripts/lessons/promote_lessons.py`
- `backend/agents/models.py` (代码注释?)
- `agent/src/core/orchestrator.py`
- `agent/tests/test_llm_auto_heal.py`
- `backend/tasks/tests/test_device_status_lifecycle.py`
- `.trae/specs/2026-07-18-spec25-...md` (spec-25 内部引用)

**不改 (历史记录)**:
- `.ai-memory/lessons/*.md` (历史教训, 不改)
- `.ai-memory/evidence/*.md` (历史 evidence, 不改)
- `docs/general/tech-debt/fixed.md` / `wontfix.md` (历史 TD 记录, 不改)
- `.ai-memory/summaries/architecture-mistakes.md` (历史摘要, 不改)

### 登记为 TD

将"跨 spec 待办"登记为 TD-251 (P3, spec-32 文档治理 spec 统一处理)。

## 验证

- ✅ `docs/general/plans/` 不存在
- ✅ `docs/general/specs/` 不存在
- ✅ `docs/architecture/` 不存在
- ✅ `.trae/specs/` 含 spec25 + spec26 + spec27
- ✅ `.trae/plans/` 存在 (空, 为未来使用)
- ✅ `.trae/architecture/` 存在 (空, 为未来使用)
- ✅ `project_rules.md §4.10` 路径已更新
- 📋 跨文件路径引用登记为 TD-269 (P3, spec-32 文档治理 spec 待定, 不在本 spec 范围)
