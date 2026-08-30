---
summary: Pre-commit Hook Stages 治理文档
applies_to: ['pre-commit', 'tooling', 'workflow']
last_updated: 2026-07-22
---

# Pre-commit Hook Stages 治理 (M2.D v8.4 + N134 + M2.C + N150 + TD-321/322)

> **来源**: 2026-06-17 M2.D 闭环 — 4 lint hook 移到 manual stage, 本地 commit 不阻塞
> **扩展**: N134 (2026-06-28) post-commit reflection guard + M2.C pre-push bypass rate guard
> **扩展**: 2026-07-18 N150 性能优化 — 10 治理 hook 折叠为 1 batch hook (单 venv, commit 71s → ~22s, 3.2x speedup)
> **扩展**: 2026-08-23 TD-377 — 再将 7 个独立 pre-commit Python hook (code-rules/tier-alignment/auto-archive/b2-evidence/spec-context/spec-id-collision/evidence-completeness) 折叠进 gaf-governance-batch, 共 24 项检查, 单 interpreter 进程
> **扩展**: TD-321 / TD-322 (2026-07-21) pre-commit 新增 B2 evidence + spec_id 冲突检查
> **扩展**: 2026-07-16 P2 季度审计 hook (manual stage, 90 天未修改脚本检测)
> **问题**: pre-commit `--all-files` 跑 12 hook ~ 60-90s, ruff 215 历史 errors + mypy 可执行文件缺失 → 本地 commit 必失败; 10 独立 GAF hook 各自 venv 启动 ~5-6s → commit 总耗时 71s
> **方案**: pre-commit 跑 4 GAF hook (1 batch 折叠 10 项检查 + B2 evidence + spec_id 冲突 + git-status guard, ~22s), manual 跑 5 hook (4 lint + 1 季度审计), pre-push 跑 1 skip-rate guard, post-commit 跑 1 batch guard (reflection + P4 checklist)

## 1. Stage 划分

| Stage | Hooks | 耗时 | 触发 |
|:-----:|-------|:----:|------|
| **`pre-commit`** (默认) | gaf-governance-batch (含 24 项检查, 内嵌原 b2-evidence/spec-id-collision/code-rules 等 7 hook), gaf-git-status-check (2 hook) | ~7s | `git commit` 自动 |
| **`manual`** | eslint, prettier, ruff, mypy, gaf-audit-scripts (5 hook) | 30-60s | `pre-commit run --hook-stage manual` |
| **`pre-push`** | gaf-skip-rate (1 hook) | < 0.5s | `git push` 自动 (滚动 30 commit + 30% 阈值) |
| **`post-commit`** | gaf-post-commit-batch (含 reflection + P4 checklist, 1 hook) | ~1.2s | `git commit` 完成后 (N134 evidence + A/B/C 软提醒) |

## 2. 使用方法

### 2.1 本地 commit (默认, 走 fast hooks)

```bash
# 正常 commit, 只跑 2 pre-commit hook (含 batch 内 24 项检查, ~7s)
git add <files>
git commit -m "feat(xxx): ..."
# → 2 hook 跑过 (governance-batch 内 24 项检查 → git-status-check), commit 成功
```

### 2.2 手动跑 lint (改前端 / 后端时, 按需)

```bash
# 跑所有 manual hook (frontend + backend lint 全跑)
pre-commit run --hook-stage manual --all-files

# 只跑单个 hook, 只针对 staged files
pre-commit run --hook-stage manual ruff --files backend/agents/models.py
pre-commit run --hook-stage manual eslint --files frontend/src/components/Foo.tsx

# 跑所有 manual hook, 只针对 staged files
pre-commit run --hook-stage manual
```

### 2.3 CI 集成 (推荐)

```yaml
# .github/workflows/lint.yml
- name: Run lint (manual stage)
  run: pre-commit run --hook-stage manual --all-files
- name: Run knowledge system (pre-commit stage)
  run: pre-commit run --all-files
```

### 2.4 跳过某 hook (紧急情况, 不推荐)

```bash
# 跳过全部 pre-commit hook
git commit --no-verify -m "..."

# 只跳过 manual stage 的 hook (默认 commit 不跑 manual, 实际不需要)
SKIP=eslint,prettier,ruff,mypy git commit -m "..."
```

## 3. Pre-commit Stage Hooks (2 hook)

| Hook ID | 触发命令 | 用途 | 耗时 |
|---------|----------|------|:----:|
| `gaf-governance-batch` | `python scripts/hooks/gaf_governance_batch.py` | 24 项治理检查折叠为单 hook (单 venv, 含 TD-377 内嵌的 b2-evidence/spec-id-collision/code-rules/tier-alignment/auto-archive/evidence-completeness/spec-context) | ~6.7s |
| `gaf-git-status-check` | `python scripts/hooks/check_git_status_after_hook.py` | N105 MM state guard (必须最后跑, 捕获 hook 误改 working tree) | < 0.1s |

> **为什么折叠成 batch hook (N150 性能优化)**:
> pre-commit 的 `language: python` 每次调用会创建一个 managed virtualenv, 单 hook ~5-6s venv 启动开销. 原先 10 个独立 governance hook 累积 ~60s 纯框架开销, 加上检查本身 commit 总耗时 71s.
> 折叠为单一 `gaf-governance-batch` hook (单 venv + v2 in-process import) 后, commit 总耗时 71s → ~22s (3.2x speedup).
> 见 `.pre-commit-config.yaml:15-19` 注释与 `scripts/hooks/gaf_governance_batch.py` 模块 docstring.
>
> **为什么 `gaf-git-status-check` 不折叠进 batch**:
> N105 要求它在所有 hook 跑完后**最后**执行, 以捕获 hook 误改 working tree 引起的 MM/MD/AM/AD 状态. 若折叠进 batch, batch 内前序检查的合法写操作会被误判为脏状态. 故保留为独立 hook, 在 batch 之后运行 (注册顺序见 `.pre-commit-config.yaml:117-123`).
>
> **紧急 bypass**: `git commit --no-verify` (会记录到 bypass log, 触发 `gaf-skip-rate` 阈值).

### 3.1 Batch Hook 内含的 24 项检查 (CHECKS 顺序)

> 来源: `scripts/hooks/gaf_governance_batch.py` `CHECKS` 列表 (权威顺序).
> v2 采用 in-process import (非 subprocess), 消除 subprocess 启动开销 (N171); TD-377 进一步将 7 个独立 pre-commit Python hook (auto-archive/spec-id-collision/evidence-completeness/B2-evidence/spec-context/tier-alignment/code-rules) 折叠进本 batch, 消除其各自 interpreter 冷启动.
>
> **运行分流 (TD-377 option B)**: commit 热路径只跑 18 项 (24 − 6; 跳过 6 个 pure-verify 模块 — sync_skills/sync_docs_index/sync_spec_index/deps-sync/scan_scripts_vs_readme/promote_lessons, 其中 promote_lessons 占 2 条 CHECKS); 被跳过的 6 模块在 pre-push 由 `gaf-governance-batch-push` 重验 (§4.1).
> **Gate-4 分级 (2026-08-26)**: 形式合规类 (session active/3-step evidence/M2 review-closure/doc-path-drift) 降级 WARN, 失败不阻塞 commit; 真防护类保持 hard.

| # | 子检查 | 触发命令 | 用途 | 运行 |
|:-:|---------|----------|------|:----:|
| 1 | session active | `check_session_active.py --check` | session 有效 (WARN) | commit |
| 2 | sync_ai_memory | `sync_ai_memory.py` | .ai-memory 索引同步 (regenerates auto-files) | commit |
| 3 | 3-step evidence | `check_3step_evidence.py` | 3 步 evidence 模板校验 (WARN) | commit |
| 4 | lessons front-matter | `check_lessons_updated.py` | lesson front-matter 校验 | commit |
| 5 | TD-170 [B] specs | `check_spec_consistency.py` | spec/tasks/checklist 一致性 | commit |
| 6 | 5 skills + 1 rule | `sync_skills.py --check` | 决策树 4 副本 hash 一致 | push |
| 7 | promote lessons | `promote_lessons.py --dry-run` | lessons 提议提升 (软检查) | push |
| 8 | active N## cap | `promote_lessons.py --check-cap` | v9.2 Active 35 条硬上限 (棘轮, 有候选未清则阻塞) | push |
| 9 | docs/ index | `sync_docs_index.py --check` | docs-index 索引检查 | push |
| 10 | path consistency | `check_path_consistency.py` | N106 inline path 防漂移 | commit |
| 11 | Y/N matrices index | `check_yn_matrices_index.py` | Y/N matrix 索引漂移 guard | commit |
| 12 | spec index drift | `sync_spec_index.py --check` | TD-322 spec-index.md 漂移 guard (8 组同号多版本 WARN) | push |
| 13 | doc-code sync | `check_doc_code_sync.py` | TD-331 (spec-87) 代码-文档因果绑定 (R1/R2/R4 硬阻断 + R3/R5/R7 WARN + R6 INFO) | commit |
| 14 | doc-path-drift | `check_doc_path_drift.py` | 文档内部相对路径漂移 guard (WARN) | commit |
| 15 | M2 review-closure | `check_claimed_rules.py check_unclosed_review` | REVIEW_TRIGGERED/激活率 <50% 复盘闭合检查 (WARN) | commit |
| 16 | deps-sync | `check_deps_sync.py` | requirements/package.json 依赖一致性 | push |
| 17 | scripts-readme | `scan_scripts_vs_readme.py --check` | scripts/ 目录 vs README 引用一致性 | push |
| 18 | auto-archive specs | `bootstrap/auto_archive_specs.py` | 完成的 spec 自动归档 (仅检查, 不自动提交) | commit |
| 19 | spec-id collision | `check_spec_id_collision.py` | 新 spec_id 冲突防撞 | commit |
| 20 | evidence completeness | `check_evidence_completeness.py` | N126 3-file triplet 完整性 | commit |
| 21 | B2 evidence | `check_big_change_hook.py` | TD-321 大修改 B2 evidence | commit |
| 22 | spec-context carrier | `check_spec_context.py` | TD-342 spec-context 承载体 | commit |
| 23 | tier alignment | `check_tier_alignment.py` | v9.2 分级反馈 | commit |
| 24 | code rules (M1) | `check_code_rules.py` | M1 AST 静态检查 (规则文件冲突) | commit |

> **第 13-24 项来源**: #13 为 spec-87 (TD-331); #14-17 为后续新增检查; #18-24 为 TD-377 从独立 pre-commit hook 折叠进 batch 的 7 项 (2026-08-23).
>
> **N105 MM state guard 不折叠**: `check_git_status_after_hook.py` 保持独立 `gaf-git-status-check` hook 并在 batch 之后最后运行, 捕获 hook 误改 working tree 引起的 MM/MD/AM/AD 状态 (若折叠进 batch, 前序检查的合法写操作会被误判为脏状态).

## 4. Manual Hooks 列表 (5 hook = 4 lint + 1 季度审计)

| Hook ID | 触发命令 | 用途 | 修复命令 |
|---------|----------|------|----------|
| `eslint` | `npx eslint --no-warn-ignored` | 前端 TS/TSX/JS/JSX lint | `npx eslint --fix` |
| `prettier` | `npx prettier --check --config frontend/.prettierrc` | 前端代码格式 | `npx prettier --write` |
| `ruff` | `ruff check` | 后端 Python lint | `ruff check --fix` |
| `mypy` | `mypy` | 后端类型检查 | 改类型注解或 `# type: ignore` |
| `gaf-audit-scripts` | `python scripts/bootstrap/audit_scripts.py` | P2 季度审计 (90 天未修改 + 无 README 引用脚本, informational only, exit 0) | 删除/归档/补 README 引用 |

> **为什么移到 manual**: ruff 历史 215 errors + mypy executable 缺失 → 本地 commit 必失败; CI 跑 manual 一次性解决
>
> **`gaf-audit-scripts` 触发方式** (季度审计手动触发):
> ```bash
> pre-commit run --hook-stage manual gaf-audit-scripts
> ```
> 不带 `--check`: informational only, exit 0 (不阻塞 manual stage). `always_run: true` — manual stage 需显式 `always_run`, 否则无 staged 文件时 skip.

## 4.1 Pre-push Hook (2 hook)

| Hook ID | 触发命令 | 用途 |
|---------|----------|------|
| `gaf-skip-rate` | `python scripts/hooks/check_skip_rate.py` | 滚动 30 commit 窗口内 `--no-verify` 比例超 30% 阻止 push |
| `gaf-governance-batch-push` | `python scripts/hooks/gaf_governance_batch.py --select bootstrap.sync_skills hooks.check_deps_sync bootstrap.sync_docs_index bootstrap.scan_scripts_vs_readme lessons.promote_lessons governance.sync_spec_index` | TD-377 冷路径 — 6 个 heavy pure-verify 模块 (7 条目) 从 commit 热路径拆出, push 时重验 (verify-only, 失败阻断 push 由用户重提交修复) |

## 4.2 Post-commit Hook (2 hook, 软提醒)

| Hook ID | 触发命令 | 用途 |
|---------|----------|------|
| `gaf-post-commit-batch` | `python scripts/hooks/gaf_post_commit_batch.py` | N134 + N171 — 折叠 2 项检查为单 hook (单 venv, post-commit 2.37s → ~1.2s): ① 50+ 行 commit 缺反思 evidence + A/B/C 分类时打印 WARNING (project_rules.md §4.6); ② P4 auto-select Y/N reflection checklist (`select_reflection_checks.py`). 均 advisory (always exit 0, git 限制不能阻止 commit) |
| `gaf-lesson-diff-trigger` | `python scripts/lessons/match_lessons_by_diff.py --base HEAD~1 --head HEAD` | M3 (2026-08-15) — 按提交 diff (路径 + 新增行) 匹配 lessons front-matter diff_keywords, 输出相关教训清单 (只提示不阻断, 让教训在"下一次踩坑"时自动出现) |

> **为什么折叠成 batch**: 同 pre-commit batch, 避免每个 post-commit hook ~1s venv 启动开销. 见 `.pre-commit-config.yaml:134-142` 注释.

## 5. 故障排查

| 症状 | 原因 | 修复 |
|------|------|------|
| `InvalidConfigError: ... line 9, column 7` | `stages` 写在 repo 顶层而非 hook 内 | 删除顶层 `stages:`, 移到每个 hook 的 `stages:` 字段 |
| `Executable mypy not found` | mypy 未装 | `pip install mypy` 或留作 manual 不阻塞 |
| ruff 215 errors | 历史 backend/agent 代码 | 跑 `ruff check --fix` 自动修, 剩余 `# noqa` 注释 |
| `pre-commit run` 跳过某些 hook | 该 hook 在 manual stage, 改用 `--hook-stage manual` | 见 §2.2 |
| pre-commit commit 超时 | N111 反模式 | 加 `wait_ms_before_async=30000` (N119 规则) |

## 6. 5 层分发 (N95 闭环)

- ✅ 层 ① `.ai-memory/lessons/2026-06-17-m2d-pre-commit-stages.md` (待写)
- ✅ 层 ② `.ai-memory/summaries/architecture-mistakes.md #49 M2.D` (待加)
- ✅ 层 ③ `docs/archive/pending-roadmap.md §二.18` (本任务完成后加)
- ✅ 层 ④ `.skills/skills/gaf-reflect-and-evolve/SKILL.md` (N91 映射表 +1 hook stage)
- ✅ 层 ⑤ `.skills/rules/project_rules.md §5.10` (待加)
- ✅ 附 `.ai-memory/meta/failure-modes.md N110 + M2.D` (待加)

## 7. 反模式家族

- N82 + N100 + N101 + N105 + N106 + N110 + N114 + N116 + N117 + N118 + N91 + N119 + **M2.D (本条 pre-commit stages 治理)** — 同根因 (工具调用治理缺位)
