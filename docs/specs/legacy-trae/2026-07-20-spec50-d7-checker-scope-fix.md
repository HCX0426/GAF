---
spec_id: spec-50
title: d7_index_consistency checker scope fix — eliminate b_minus_a false positives
status: ✅ done
created: 2026-07-20
last_updated: 2026-07-20
related: spec-41 (doc health checker), spec-47 (path drift), spec-49 (AI self-decide)
n167_score: 15/15 (3 dimensions, medium modification)
---

# Spec-50: d7 检查器范围修复 — 消除 b_minus_a false positives

> **来源**: spec-49 commit (`-`) 后 `.trash/` 清理引发 7 个 P0 回归 (d4_path_drift), 修复后调查 d7 P2 漂移发现 b_minus_a=20 全部为 false positive (Dormant/Retired/Archived N## 在 lessons/README.md 中被 family-merge 描述引用, 但 d7 检查器只检查 §Active 段)
> **目标**: 修改 d7 检查器, b_minus_a 检查使用 all_known (Active + Retired + Dormant + Archived) 而非仅 Active, 消除 20 个 false positive; 同时回填 spec-49 commit hash + 修复 `.trash/` 清理引入的 P0 回归

## 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | P0 回归修复 (5 lessons + 1 schema, `.trash/spec27-cleanup/` 引用清理) | ✅ | 2026-07-20 | - | doc_health P0 7→0; 5 lessons frontmatter + body 修复 |
| Phase 2 | d7 检查器范围修复 (b_minus_a 用 all_known 而非 Active) | ✅ | 2026-07-20 | - | d7 P2 33→13 (b_minus_a 20→0, a_minus_c 13 保留) |
| Phase 3 | spec-49 hash 回填 + 验证 + 状态同步 | ✅ | 2026-07-20 | - | spec-49 7 Phase hash 回填 + sync 4 工具 PASS + 53 tests PASS |

> spec-51 commit hash 回填: spec-50 commit hash `-` 已回填至本表 (N176 单对话批量 spec 单 commit 规则, 由 spec-51 commit 顺带完成)。

## §1 Background

### 1.1 来源

- **spec-49 commit (`-`) 后 `.trash/` 清理**: 删除 `.trash/spec27-cleanup/` 目录 (159 items, 4.4 MB), 该目录被 5 个 lessons 文件 frontmatter `related_files` 引用 → 7 个 P0 回归 (d4_path_drift)
- **P0 回归修复后调查 d7**: doc_health 报 d7 P2 = 33 (cache), 直接调用检查器函数得 b_minus_a = 20
- **20 个 b_minus_a N## 分类**:
  - **Archived (1)**: N30 (在 archived-lessons.md §归档 N## 索引表)
  - **Dormant in archived-lessons.md (1)**: N14 (在 archived-lessons.md §Dormant N## 索引)
  - **Retired (2)**: N101, N108 (在 failure-modes.md §Retired, M0.M 闭环)
  - **Dormant in failure-modes.md §Dormant (16)**: N107, N110, N114, N113, N115, N127, N119, N128, N130, N147, N153, N155, N162, N163, N165, N169 (家族合并子条目)
- **根因**: d7 检查器 `_active_n_in_failure_modes()` 只解析 §Active 段, 不识别 §Retired/§Dormant/archived-lessons.md; lessons/README.md 中 family-merge 描述 (如 "合并 N14/N101/N128/N130") 触发 false positive

### 1.2 d7 三类 issue 语义分析

| Issue 类型 | 当前实现 | 问题 | 修复后 |
|-----------|---------|------|--------|
| `a_minus_b` (Active - README) | Active N## 未在 README | ✅ 正确 (新 Active N## 必须加到 README) | 不变 |
| `b_minus_a` (README - Active) | README N## 未在 Active | ❌ False positive: Dormant/Retired/Archived N## 在 README 中是合法引用 | 用 all_known (Active + Retired + Dormant + Archived) 而非 Active |
| `a_minus_c` (Active - yn-matrices) | Active N## 未在 yn-matrices | ✅ 正确 (L1-小/中 不需要 yn-matrices, P2 接受) | 不变 |

### 1.3 N167 评分 (3 维度, 中修改)

**方案 A (selected)**: 修改 d7 检查器 — 添加 `_all_known_n()` 函数, b_minus_a 用 all_known 而非 Active

| 维度 | 评分 | 理由 |
|------|------|------|
| 1. 架构长远性 | 5/5 | 修复检查器语义正确性, b_minus_a 真正捕获 orphan N## (而非 family-merge 引用), 长期不会再出现这种 false positive |
| 2. 全局归一化 | 5/5 | 与 a_minus_b (Active 检查) 语义一致, 检查器内部逻辑归一 |
| 7. 长期维护成本 | 5/5 | 一次性修复, 无需长期维护; 配套测试用例覆盖 |

**⑤ 性能资源优化理由**: 检查器多读 1 个文件 (archived-lessons.md), < 1ms 影响, 性能无影响
**⑥ 安全合规加固理由**: 不涉及权限/审计, 安全无影响 (中修改跑 3 维, ⑤⑥ 不评分)

**反向论证 (spec-49 必填)**:
- **为何不选 B** (在 lessons/README.md 中删除所有 family-merge mentions): 损失 family-merge 历史信息 (README 需记录 N126 合并 N14/N101/N128/N130); 不解决根因 (检查器语义错误), 后续家族合并仍会引入新 mentions
- **为何不选 C** (在 d7 checker 加 allowlist 硬编码 20 个 N## 跳过): 硬编码 allowlist 不 scalable; 后续家族合并需手动同步 allowlist; 与检查器语义不一致 (allowlist 是 workaround 而非根因修复)

**硬场景 ③ 业务语义判定**: 这个决策影响数据保留/业务流程吗? N (只改检查器逻辑, 不动数据) → 可自决

**总分**: 15/15 (3 维度), 远超 9/12 阈值, AI 自决 ✅

## §2 Phase 1: P0 回归修复 (已实施)

### 2.1 问题

`.trash/spec27-cleanup/` 目录删除后, 5 个 lessons 文件 frontmatter `related_files` + body path 引用了该目录下文件, 触发 d4_path_drift P0 = 7

### 2.2 修复 (2 轮)

**Round 1** (`fix_spec50_p0_regression.py` 已删除):
- body path 替换为 "spec27-cleanup archive (已删除)" 描述性文字
- frontmatter 移除 `.trash/spec27-cleanup/` entry
- **副作用**: regex 误把 frontmatter `related_files` 中的路径也替换为描述性文字 → 4 个新 P0

**Round 2** (`fix_spec50_p0_phase2.py` 已删除):
- 修复 regex: `^\s*-\s*spec27-cleanup archive \(已删除\)\n` (匹配 2 空格缩进)
- 移除 frontmatter 中的描述性文字
- P0 = 0 恢复

### 2.3 影响文件

- `.ai-memory/doc-health-report-schema.md` — 移除 `related_files` 中的 `.cache/doc_health_report.json` (运行时生成, 不应列入契约)
- `.ai-memory/lessons/agent-impl_2026-07-12-n158-langgraph-agent-implementation.md` — body path 替换 + frontmatter 清理
- `.ai-memory/lessons/architecture_2026-07-08-n151-architecture-first-for-major-changes.md` — frontmatter 清理
- `.ai-memory/lessons/architecture_2026-07-17-n168-backup-restore-security-fix.md` — frontmatter 清理
- `.ai-memory/lessons/command-errors_2026-07-14-n160-n162-context-budget-command-reflection.md` — frontmatter 清理
- `.ai-memory/lessons/workflow_2026-06-28-n134-workflow-skill-not-triggered.md` — frontmatter 清理

## §3 Phase 2: d7 检查器范围修复

### 3.1 修改文件

`scripts/governance/check_dimensions/d7_index_consistency.py`

### 3.2 修改内容

**新增 2 个函数**:
- `_all_n_in_failure_modes(repo_root)`: 解析 failure-modes.md 所有 section (Active/Retired/Dormant) 的 N## table rows
- `_n_in_archived_lessons(repo_root)`: 解析 archived-lessons.md 中所有 N## patterns

**修改 `check()` 函数**:
- `b_minus_a` 计算从 `b - a` 改为 `b - all_known` (all_known = Active ∪ Retired ∪ Dormant ∪ Archived)
- `a_minus_b` 保持不变 (仍用 Active, 因为新 Active N## 必须加到 README)
- `a_minus_c` 保持不变 (仍用 Active, L1-小/中 不需要 yn-matrices)

**evidence 文案更新**:
- `b_minus_a` evidence 从 "not in failure-modes.md Active (archived?)" 改为 "not in any failure-modes.md section or archived-lessons.md (orphan)"
- `suggested_fix` 从 "Remove from README or restore in failure-modes.md" 改为 "Investigate orphan N##: add to failure-modes.md or remove from README"

### 3.3 测试

更新 `scripts/tests/test_doc_health_check.py` (如需) + 跑 doc_health_check 验证 d7 P2 从 33 降到 ~13 (b_minus_a 20→0, a_minus_c 13 保留)

## §4 Phase 3: spec-49 hash 回填 + 验证 + 状态同步

### 4.1 spec-49 hash 回填 (N176)

spec-49 文件状态表 7 Phase 的 commit hash 字段从 "(待回填)" 改为 "-"

### 4.2 验证

- `doc_health_check.py` PASS (P0=0, P1=0, P2 减少)
- `sync_ai_memory.py` PASS
- `sync_skills.py --check` PASS
- `check_yn_matrices_index.py` PASS
- `pytest scripts/tests/test_doc_health_check.py` PASS (50 tests)

### 4.3 状态同步

- `completed-features.md`: 加 C-077 (spec-50)
- `pending-roadmap.md`: 加 P-018 (spec-50)

## §5 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| d7 检查器修改后 b_minus_a 仍不为 0 | 低 | 中 (有 orphan N## 需调查) | 修改后跑 doc_health 验证; 若有残留, 分析具体 N## |
| 测试用例需更新 | 中 | 低 (test 修改) | 跑 pytest 验证, 必要时更新 fixture |
| a_minus_c 仍 13 (未修复) | 高 | 低 (P2 接受, L1-小/中 不需 yn-matrices) | 不在 spec-50 范围, 已接受 |

## §6 一致性检查

- ✅ 与 spec-41 (d7 设计) 一致: 修复检查器实现 bug, 不改 d7 设计语义
- ✅ 与 spec-47 (path drift) 一致: P0 回归修复沿用 spec-47 模式
- ✅ 与 spec-49 (AI 自决) 一致: N167 评分 + 反向论证 + 硬场景 ③ 判定 + AI 自决 (15/15)
- ✅ 与 N176 (单对话批量 spec 单 commit) 一致: spec-49 hash 回填合并到 spec-50 commit

## §7 Open Questions

无 — 修复方案明确, AI 自决实施 (N167 15/15, 硬场景 ③ N → 可自决)
