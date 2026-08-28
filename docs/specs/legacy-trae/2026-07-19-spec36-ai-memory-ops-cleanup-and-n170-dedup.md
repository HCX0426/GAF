# spec-36: .ai-memory/ops/ 清理 + docs-index 重生成 + N170 撤销过度分发

> **来源**: 2026-07-19 用户评估请求 — "docs/ 与 .ai-memory/ 在 ai 思维链和工作流和规则文档中是否职责重复/冗余/分配不好"
> **评估结果**: 2 个 subagent 并行评估发现 P0 严重问题 3 项, P1 中等问题 4 项, P2 轻微问题 6 项
> **本 spec 范围**: 仅修 P0 三项 (ops/ 清理 + docs-index 重生成 + N170 撤销分发); P1/P2 进 spec-37 文档治理 spec (与 TD-279 合并)
> **状态**: ✅ Done (2026-07-19)

## 阶段状态表

| Phase | 内容 | 优先级 | 行数估计 | 状态 | 完成时间 | Commit | 验收 evidence |
|:-----:|------|:------:|:--------:|:----:|:--------:|:------:|--------------|
| 1 | 删除 .ai-memory/ops/ 5 陈旧文件 + 迁移 monthly-health-checks/ | P0 | ~50 行 | ✅ | 2026-07-19 | - | 3 失效文件归档 + monthly-health-checks 迁到 docs/general/health-checks/ + 7 处路径引用更新 + README.md 更新 |
| 2 | 跑 sync_docs_index.py 重生成 docs-index.md | P0 | ~1 命令 | ✅ | 2026-07-19 | - | docs-index 重生成 (27 docs, 0 失效路径) + health-checks 2 文件补 frontmatter + sync_ai_memory.py 跑通 |
| 3 | 撤销 N170 过度分发 (3 层: lesson + Active 索引 + Y/N 矩阵) | P0 | ~30 行 | ✅ | 2026-07-19 | - | N170 lesson 文件归档到 .trash/ + failure-modes.md §Active 索引行标记撤销 + 计数 51→50 + lessons/README.md 条目更新; rules+handbook 两层保留 |
| 4 | 全量回归 + commit + C-064 | P0 | - | ✅ | 2026-07-19 | - | sync_ai_memory/sync_skills/check_yn_matrices_index/check_path_consistency 全 PASS (0 errors, 185 warnings 均为模拟器 ADB 路径硬编码) |

**总计**: 3 项 P0, ~80 行

## Phase 1: 删除 .ai-memory/ops/ 5 陈旧文件 + 迁移 monthly-health-checks/

### 1.1 删除 5 个陈旧文件 (Move-Item 到 .trash/)

| 文件 | 陈旧时长 | 处理 |
|---|---|---|
| `.ai-memory/ops/completed-features.md` | 17 天未更新, 已被 docs/general/completed-features.md 取代 | 删 |
| `.ai-memory/ops/bug-tracker.md` | 33 天未更新, 已被 docs/general/tech-debt/active.md 三件套取代 | 删 |
| `.ai-memory/ops/bypass-patterns.md` | 33 天未更新, 9 项绕过 100% 已在对应 N## lesson 中 | 删 |
| `.ai-memory/ops/deletion-queue.md` | 32 天未更新, 3 项 deletion 全部处理完毕 | 删 |
| `.ai-memory/ops/why-skipped.md` | 5 次相同 e2e 失败重复记录, 未触发修复 | 删 |

### 1.2 迁移 monthly-health-checks/ 到 docs/general/health-checks/

- `.ai-memory/ops/monthly-health-checks/` → `docs/general/health-checks/`
- 月度报告是用户可读运营产物, 符合 §2.1 docs/ 定位
- 同步检查是否有 .ai-memory/ 内部文件引用 monthly-health-checks/ 路径

### 1.3 删除空目录 .ai-memory/ops/

- 全部文件迁出后删除空目录
- 在 .ai-memory/README.md 中更新目录结构说明 (移除 ops/ 段)

### Phase 1 验收
- [x] 3 个陈旧文件移到 .trash/ (completed-features.md / bug-tracker.md / deletion-queue.md); 保留 bypass-patterns.md + why-skipped.md 作为脚本输出目标
- [x] monthly-health-checks/ 迁到 docs/general/health-checks/
- [x] .ai-memory/ops/ 保留 (含 2 个脚本输出目标文件)
- [x] .ai-memory/README.md 目录结构更新
- [x] grep `.ai-memory/ops/` 无活跃引用 (剩余引用均在 fixed.md / spec 历史记录中)

## Phase 2: 跑 sync_docs_index.py 重生成 docs-index.md

### 2.1 跑同步脚本

```
conda run -n gaf python scripts/bootstrap/sync_docs_index.py
```

- 预期: 重生成 .ai-memory/meta/docs-index.md, 消除 50+ 失效路径引用
- 验证: grep `docs/general/plans/` docs-index.md = 0; grep `docs/general/specs/` = 0; grep `docs/architecture/` = 0

### 2.2 检查 sync_ai_memory.py 是否需要重跑

- 如果 docs-index.md 重生成后, sync_ai_memory.py --query <keyword> 仍能正确返回, 则不需要重跑
- 如果 sync_ai_memory.py 内部维护了独立计数, 需要重跑同步

### Phase 2 验收
- [x] sync_docs_index.py 跑通 (exit 0, 5.06s)
- [x] docs-index.md 中 0 处 `docs/general/plans/` / `docs/general/specs/` / `docs/architecture/` 引用
- [x] sync_ai_memory.py 跑通 (5.42s)
- [x] 2 个 health-checks 文件 (README.md + 2026-07.md) 补 frontmatter

## Phase 3: 撤销 N170 过度分发 (3 层)

### 3.1 删除 N170 lesson 文件

- 文件: `.ai-memory/lessons/command-errors_2026-07-18-n170-git-commit-m-no-prompt.md`
- 操作: Move-Item 到 .trash/
- 理由: N170 是 L1-小 (1-3 行规则变更), 按 §6.2 不应创建 lesson

### 3.2 移除 failure-modes.md §Active 中 N170 索引行

- 文件: `.ai-memory/meta/failure-modes.md`
- 操作: 删除 N170 的索引行 (在 Active 段)
- 同时更新 Active N## 计数 (51 → 50)

### 3.3 移除 yn-matrices/_workflow.md 中 N170 Y/N 矩阵段

- 文件: `.ai-memory/meta/yn-matrices/_workflow.md`
- 操作: 删除 N170 对应的 Y/N 矩阵段
- 同时更新 yn-matrices 索引计数 (如有)

### 3.4 更新 lessons/README.md

- 文件: `.ai-memory/lessons/README.md`
- 操作: 移除 N170 lesson 文件条目

### 3.5 保留 N170 在 rules + handbook (2 层)

- `.trae/rules/project_rules.md §3.4` — 保留 (硬约束层)
- `.ai-memory/meta/ai-operating-handbook.md Part 2` — 保留 (行为红线层)
- 编号 N170 永不复用, 标记为 "L1-小不再分发"

### Phase 3 验收
- [x] N170 lesson 文件移到 .trash/
- [x] failure-modes.md §Active 中 N170 索引行标记撤销分发 + 计数 51→50
- [x] yn-matrices/_workflow.md §6 ㊱ 是合并说明 (非 Y/N 矩阵), 保留作历史记录
- [x] lessons/README.md 中 N170 条目标记撤销分发
- [x] project_rules.md §3.4 + ai-operating-handbook.md Part 2 中 N170 内容保留
- [x] grep `N170` 全仓库, 仅保留 rules + handbook + 历史引用 (failure-modes / yn-matrices / lessons/README / fixed.md)

## 全量回归 (Phase 1-3 完成后)

- [x] `python scripts/bootstrap/sync_ai_memory.py` PASS (4.57s)
- [x] `python scripts/bootstrap/sync_skills.py` PASS (4.92s)
- [x] `python scripts/hooks/check_yn_matrices_index.py` PASS (4.10s)
- [x] `python scripts/hooks/check_path_consistency.py` PASS (0 errors; 185 warnings 均为 LDPlayer/MuMu/Nox/BlueStacks 模拟器 ADB 路径硬编码, 项目设计如此)
- [x] commit + 更新 completed-features.md C-064

## 后续 (spec-37, 不在本 spec 范围)

P1 中等问题 4 项 + P2 轻微问题 6 项进 spec-37 文档治理 spec (与 TD-279 合并):
- docs/backend/operations/ 9 份迁到 docs/general/design/
- resource-pack + task-execution 双套合并
- knowledge/common-pitfalls.md 删除 + terminology.md 路径修复
- summaries/architecture-mistakes.md §0 去重
- N95/N116 状态归档 + N119 双重引用清理
- README.md TD 计数更新 + checklets/ 合并 + pre-commit-stages 迁移
