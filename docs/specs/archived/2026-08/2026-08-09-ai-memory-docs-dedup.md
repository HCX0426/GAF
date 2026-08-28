---
summary: 清除 .ai-memory/ 与 docs/ 之间的 8 个字节级重复文件 + 4 个 spec-context 重复 + 路径漂移修复
applies_to: [docs, ai-memory, governance]
last_updated: 2026-08-09
---

# Spec: .ai-memory 与 docs 跨文件夹去重

> **触发**: 用户反馈 "看下目前的 ai 工作流，规则文档和思维链，怎么访问这两个文件夹的内容" + "目前这些是不是都是有必要的？有优化空间吗，有冗余吗"

## 问题根因

前序重构（spec-41/spec-51/spec-2026-07-26）做了 **"复制+移动"** 而非 **"移动+引用更新"**，导致 `.ai-memory/` 和 `docs/` 之间出现 8 个字节级完全一致的重复文件。此外，spec-context 文件在迁移过程中也在两个位置各留了一份。

## 深度评估发现

### 关键纠正：初始评估方向错误

初始评估建议 "删除 .ai-memory/ 副本，保留 docs/ 副本"。深度扫描证明这是 **错误的**：

- **78 个文件**（skills/scripts/tests/rules/lessons）引用 `.ai-memory/` 路径
- **0 个文件**引用 `docs/reference/knowledge/`、`docs/reference/summaries/`、`docs/standards/checklists/` 路径
- 两份副本的 `source:` frontmatter 都指向 `.ai-memory/`，证明 `.ai-memory/` 是权威源

**正确方向**：删除 `docs/` 侧的孤立镜像副本，保留 `.ai-memory/` 侧的权威副本。

### P0-A: 8 个字节级重复镜像文件

| 权威源 (.ai-memory/) | 孤立镜像 (docs/) | 行数 | 一致性 |
|----------------------|-----------------|------|--------|
| `knowledge/data-chain.md` | `reference/knowledge/data-chain.md` | 208 | IDENTICAL |
| `knowledge/error-recovery.md` | `reference/knowledge/error-recovery.md` | 206 | IDENTICAL |
| `knowledge/task-lifecycle.md` | `reference/knowledge/task-lifecycle.md` | 168 | IDENTICAL |
| `knowledge/terminology.md` | `reference/knowledge/terminology.md` | 169 | IDENTICAL |
| `summaries/architecture-mistakes.md` | `reference/summaries/architecture-mistakes.md` | 904 | IDENTICAL |
| `summaries/code-rules.md` | `reference/summaries/code-rules.md` | 249 | 1 行不同 (路径漂移) |
| `summaries/library-conflicts.md` | `reference/summaries/library-conflicts.md` | 123 | IDENTICAL |
| `checklists/data-chain-checklist.md` | `standards/checklists/data-chain-checklist.md` | 741 | 1 行不同 (路径漂移) |

**总计**: ~2,768 行纯重复内容

**证据**:
- `docs/` 侧副本的 `source:` frontmatter 指向 `.ai-memory/` 原始路径
- 全仓库 grep `docs/reference/knowledge/`、`docs/reference/summaries/`、`docs/standards/checklists/` → 0 个引用
- 全仓库 grep `.ai-memory/knowledge/`、`.ai-memory/summaries/`、`.ai-memory/checklists/` → 78+ 个引用
- 无同步脚本创建镜像 (grep `shutil.copy` + `reference/knowledge` → 无匹配)

### P0-B: 4 个 spec-context 重复文件

| 权威源 (docs/archive/spec-context/) | 孤立镜像 (docs/specs/archived/ root) | 一致性 |
|--------------------------------------|--------------------------------------|--------|
| `2026-08-02-backend-execution-unification-context.md` | 同名文件 | IDENTICAL |
| `2026-08-02-perf-monitor-design-context.md` | 同名文件 | IDENTICAL |
| `2026-08-03-postgres-to-sqlite-removal-context.md` | 同名文件 | IDENTICAL |
| `2026-08-08-architechure-debt-refactor-context.md` | 同名文件 | IDENTICAL |

**权威源**: `docs/archive/spec-context/` (pre-commit hook `check_spec_context.py` 指向此路径)

### P0-C: 2 个 .ai-memory/ 文件路径漂移

| 文件 | 行号 | 旧路径 | 正确路径 |
|------|------|--------|----------|
| `.ai-memory/summaries/code-rules.md` | 227 | `docs/tech-debt/active.md` | `docs/archive/active-tech-debt.md` |
| `.ai-memory/checklists/data-chain-checklist.md` | 11 | `docs/tech-debt/active.md` | `docs/archive/active-tech-debt.md` |

**讽刺点**: `docs/` 侧镜像副本有正确路径，`.ai-memory/` 权威源反而有旧路径 — 说明镜像创建时更新了路径但没回写源文件。

### P1-A: N164/N168 索引重复

- `failure-modes.md` §Archived-Early (L130-138) 列出 N164, N168
- `archived-lessons.md` §Archived N## 索引也列出 N164, N168
- `failure-modes.md` frontmatter L30 明确说 "archived 一档在 archived-lessons.md"，但实际自己也有一份

### P1-B: auto-kb/pipeline-nodes.md 过期

- 有 CONFLICT 标记：34 个源文件比条目新
- 写 "37 nodes" 但 `docs/business/tasks/pipeline-authoring-guide.md` 写 "39 nodes"
- 需重新生成

### P1-C: session-context.md 空壳

- `sync_session_context.py` 生成空模板 (Symptom: none, Solution: none)
- `gaf-knowledge-base/SKILL.md` 声明它为 L2 auto-load
- 要么修复生成器填充实际内容，要么移除 L2 引用

### P1-D: docs/README.md 虚假 "互补" 声明

`docs/README.md` L73 声称：
```
两者互补，不重复：
* docs/reference/ (项目技术栈) vs .ai-memory/knowledge/ (AI 对项目的理解)
```
但实际是字节级完全重复，不是 "互补"。删除镜像后需更新此声明。

### 不冗余（保留不动）

| 项目 | 理由 |
|------|------|
| `ai-cheatsheet.md` | 3 个脚本主动管理 (lifecycle_report.py, cleanup_cheatsheet.py, bump_cheatsheet_usage.py) |
| `.ai-memory/ops/` | `bypass_weekly_review.py` 写入 bypass-patterns.md; `weekly_summary.py` 写入 why-skipped.md |
| `spec-evolution.md` | 18 个文件引用，有独立职责 (spec 路径映射 + 季度评审模板) |
| `governance/` 3 文件 | 自动生成，与 docs/archive/ 健康报告用途不同 |
| `docs/reference/data-flow.md` | 与 `.ai-memory/knowledge/data-chain.md` 范围不同 (系统架构 vs 调试链路) |
| 6 个 archived yn-matrices | 明确保留为 "历史证据" (~1,307 行) |

---

## 实施计划

### Phase 1: 删除 8 个 docs/ 侧孤立镜像 (P0-A)

| Step | 操作 | 文件 |
|------|------|------|
| 1.1 | 删除 `docs/reference/knowledge/data-chain.md` | 208 行 |
| 1.2 | 删除 `docs/reference/knowledge/error-recovery.md` | 206 行 |
| 1.3 | 删除 `docs/reference/knowledge/task-lifecycle.md` | 168 行 |
| 1.4 | 删除 `docs/reference/knowledge/terminology.md` | 169 行 |
| 1.5 | 删除 `docs/reference/summaries/architecture-mistakes.md` | 904 行 |
| 1.6 | 删除 `docs/reference/summaries/code-rules.md` | 249 行 |
| 1.7 | 删除 `docs/reference/summaries/library-conflicts.md` | 123 行 |
| 1.8 | 删除 `docs/standards/checklists/data-chain-checklist.md` | 741 行 |
| 1.9 | 删除空目录 `docs/reference/knowledge/`、`docs/reference/summaries/`、`docs/standards/checklists/` | — |

**验证**: grep `docs/reference/knowledge` + `docs/reference/summaries` + `docs/standards/checklists` → 应为 0 个活跃引用

### Phase 2: 删除 4 个 spec-context 重复 (P0-B)

| Step | 操作 |
|------|------|
| 2.1 | 删除 `docs/specs/archived/2026-08-02-backend-execution-unification-context.md` |
| 2.2 | 删除 `docs/specs/archived/2026-08-02-perf-monitor-design-context.md` |
| 2.3 | 删除 `docs/specs/archived/2026-08-03-postgres-to-sqlite-removal-context.md` |
| 2.4 | 删除 `docs/specs/archived/2026-08-08-architechure-debt-refactor-context.md` |

**验证**: `check_spec_context.py` hook 仍指向 `docs/archive/spec-context/`

### Phase 3: 修复路径漂移 (P0-C)

| Step | 操作 | 文件 | 行号 |
|------|------|------|------|
| 3.1 | Edit `.ai-memory/summaries/code-rules.md` L227 | `docs/tech-debt/active.md` → `docs/archive/active-tech-debt.md` |
| 3.2 | Edit `.ai-memory/checklists/data-chain-checklist.md` L11 | `docs/tech-debt/active.md` → `docs/archive/active-tech-debt.md` |

### Phase 4: 去重 N164/N168 索引 (P1-A)

| Step | 操作 |
|------|------|
| 4.1 | 从 `failure-modes.md` §Archived-Early 段删除 N164, N168 行 (它们已在 `archived-lessons.md` 中) |
| 4.2 | 保留 `archived-lessons.md` 作为 archived 层单一权威源 |

### Phase 5: 重新生成 auto-kb/pipeline-nodes.md (P1-B)

| Step | 操作 |
|------|------|
| 5.1 | 跑 `python scripts/bootstrap/sync_ai_memory.py` 重新生成 auto-kb 文件 |
| 5.2 | 验证 pipeline-nodes.md 节点数与实际代码一致 |

### Phase 6: 更新文档引用 (P1-D)

| Step | 操作 |
|------|------|
| 6.1 | 更新 `docs/README.md` L68-76: 移除 "两者互补，不重复" 的虚假声明，改为说明 `docs/reference/` 只保留项目独有的技术栈参考，`.ai-memory/` 保留 AI 工作记忆 |
| 6.2 | 更新 `docs/project-status.md` 中对 `docs/archive/` 的引用 (如有) |
| 6.3 | 跑 `python scripts/bootstrap/sync_docs_index.py` 重建索引 |

### Phase 7: session-context.md 评估 (P1-C)

| Step | 操作 |
|------|------|
| 7.1 | 检查 `sync_session_context.py` 为何生成空模板 |
| 7.2 | 若生成器有 bug → 修复; 若设计如此 (无数据时输出空) → 从 `gaf-knowledge-base/SKILL.md` 移除 L2 auto-load 声明 |

---

## 验收标准

| ID | 标准 | 验证方法 |
|----|------|----------|
| AC-1 | `docs/reference/knowledge/` 目录不存在 | `LS docs/reference/knowledge/` → not found |
| AC-2 | `docs/reference/summaries/` 目录不存在 | `LS docs/reference/summaries/` → not found |
| AC-3 | `docs/standards/checklists/` 目录不存在 | `LS docs/standards/checklists/` → not found |
| AC-4 | `docs/specs/archived/` 根级无 spec-context 文件 | `LS docs/specs/archived/*.md` → 只剩 `dependency-graph.md` |
| AC-5 | `.ai-memory/summaries/code-rules.md` 无旧路径 | `grep "docs/tech-debt/active.md" .ai-memory/summaries/code-rules.md` → 0 |
| AC-6 | `.ai-memory/checklists/data-chain-checklist.md` 无旧路径 | `grep "docs/tech-debt/active.md" .ai-memory/checklists/data-chain-checklist.md` → 0 |
| AC-7 | `failure-modes.md` §Archived-Early 无 N164/N168 | `grep "N164\|N168" .ai-memory/meta/failure-modes.md` → 0 (或仅在 Retired 段) |
| AC-8 | `docs/README.md` 无 "互补，不重复" 虚假声明 | `grep "互补，不重复" docs/README.md` → 0 |
| AC-9 | pre-commit hook 通过 | `git commit` 不被 hook 阻断 |
| AC-10 | `sync_docs_index.py` 重建后文档数减少 8 | 新索引文档总数 = 旧总数 - 8 |

## 已知限制

- **session-context.md 空壳问题** (P1-C) 可能需要修改 `sync_session_context.py` 生成逻辑，若 bug 复杂则单独登记 TD
- **6 个 archived yn-matrices** (~1,307 行) 评估为保留 (历史证据)，不在本次清理范围
- **`docs/specs/legacy-trae/` 88 个历史 spec** 不删除 (git 已追踪，纯历史归档)
