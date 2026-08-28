# s30 — doc_health_check 报告治理 (d5 + d4 patch)

> **类型**: refactor (文档治理) | **日期**: 2026-08-17 | **来源**: 用户第三次"继续" → active-tech-debt 空 / pending-roadmap 空 → doc_health_check 94 issues 扫描
> **状态**: ✅ 已归档 (2026-08-17, commit -) | **归档位置**: `docs/specs/archived/2026-08/2026-08-17-s30-doc-health-patch.md`
> **关联**: §0.5 doc_health_check 流程 (上限 10 issues, 按 dimension 分组) / spec-41 (d5 frontmatter 3-mode) / spec-46 + spec-53 (d4 evidence 语义)

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit hash | 验收 evidence |
|------|------|---------|------------|--------------|
| Phase 1 扫描 + 范围判定 | ✅ | 2026-08-17 20:52 | — | doc_health 94 issues (P0:33 P1:41 P2:20); 已排除历史快照 (fixed-tech-debt-details 17 d3 / pending-roadmap 历史行 / session-context auto 文件) |
| Phase 2 d5 frontmatter 修复 | ✅ | 2026-08-17 20:52 | — | 3 文件 16 issues: docs-index.md +1 last_manual_edit, _workflow-commit.md +5, archived-yn-matrices 2 文件各 +5; 重跑后 d5 全清 (94→78) |
| Phase 3 d4 path drift 修复 | ✅ | 2026-08-17 | — | 33 issues → 2 (legacy-trae 豁免后 0): auto-kb 2 (llm_client.py 移 agent/src/ai/, engine.py → pipeline_engine.py); games 10 (BrownDust-II 连字符→空格 + bd2-task-reference→task-reference + pipelines→tasks); lessons 15 body 路径 (docs/archive 迁移 / yn-matrices 归档 / .skills 前缀); knowledge 1; health-report 5 (→docs/health/procedure.md); d4 检查器加 legacy-trae + archived skip |
| Phase 4 检查器误报修复 | ✅ | 2026-08-17 | — | d7: N202 next_n_id frontmatter 误报修复 + 13 个 N177-N201 whitelist (L1-小/中/L0 硬约束, 无需 yn-matrices); d3: git hash tail 误报修复 + "L3 docs/" 路径片段误报修复 + archived/fixed-details 豁免 |
| Phase 5 d6 staleness | ✅ | 2026-08-17 | — | 6 个 P2 分析文档 last_updated 更新为 2026-08-17 (s30 确认仍有效) |
| Phase 6 验证 + consumed | ✅ | 2026-08-17 | — | 94→1 (剩余 pending-roadmap 历史行已标记 consumed); 测试 144 passed (test_doc_health_* 全量) |
| Phase 7 commit + 归档 | ✅ | 2026-08-17 | - | 38 文件 310+/91- 单 commit; pre-commit 10 hooks + post-commit 全过; 已复制到 docs/specs/archived/2026-08/ |

## 背景与根因

doc_health_check.py 报告 94 issues, 分布: d3_count_drift 25 / d4_path_drift 33 / d5_frontmatter 16 / d6_staleness 6 / d7_index_consistency 14。

**已排除 (历史快照, 不应机械改)**:
- d3: fixed-tech-debt-details.md 17 个 (硬编码 '60'/'3463'/'4'/'8'/'20' 是历史快照); pending-roadmap.md:112 ('60' 是 P-042 行历史描述); session-context.md 是 auto_updated 文件 (应重新生成非手改); ai-operating-handbook.md:79 疑似行号误报 (grep 无匹配)
- d4: legacy-trae specs (历史归档); health-report 引用 docs/monthly-health-check.md (文件不存在 — 月度报告机制已迁移到 docs/health/, 待评估)

**确定性可修**:
- d5 全部 16 个 (3 文件 frontmatter 缺字段, derived-manual 8 字段契约)
- d4 auto-kb 2 个 (活跃 KB 引用已删除代码路径)
- d4 BrownDust-II 8 个 (frontmatter 引用 `resources/BrownDust-II/` 实际目录 `resources/BrownDust II/` 带空格)

## Phase 3 详细任务 (d4 path drift)

| # | 文件 | issues | 修复方案 | 状态 |
|---|------|--------|---------|------|
| 1 | .ai-memory/games/browndust-ii/assets.md | 3 | frontmatter related_files: BrownDust-II → `BrownDust II` | ✅ |
| 2 | .ai-memory/games/browndust-ii/common-tasks.md | 3 | 同上 + bd2-task-reference.md → docs/task-reference.md + pipelines/back_to_main.json 删除 (目录不存在) | ✅ |
| 3 | .ai-memory/games/browndust-ii/coordinate-system.md | 2 | frontmatter related_files: 同上 | ✅ |
| 4 | lessons/ 15 个文件 | 15 | 评估: lesson related_files 是 cross-ref 契约 (promote 脚本用), 需逐条验证实际路径 | ✅ |

## 验收标准

1. `doc_health_check.py` 重跑: d5_frontmatter = 0
2. d4_path_drift: BrownDust 8 个清零 (≤ 10 issues/组)
3. lessons 15 个: 逐条验证, 能确认实际路径的修, 无法确认的登记 consumed
4. 不修改: fixed-tech-debt-details.md / pending-roadmap 历史行 / session-context.md (auto) / legacy-trae
5. 提交前: `git status` 无未暂存残留; 只 add 明确修改文件
6. performance-baseline.md 噪声不提交

## 已知限制

- **最终剩余 1 个 issue**: `docs/archive/pending-roadmap.md:112` — P-042 spec-60 完成时的历史快照描述 (写入时计数 60, 现 Active 数 69), 语义正确不改, 已标记 consumed (flywheel 跳过)
- **d3 archived spec 豁免**: `docs/specs/archived/` + `fixed-tech-debt-details.md` 加入 skip (历史快照), 与 d4/d5 legacy 语义一致
- **auto-kb 文件**: frontmatter 手动维护段与 auto 生成段不一致 (生成器重跑会覆盖) — 本次同步修改 frontmatter + 正文 related_files 两处 (error-codes.md: backend/qa/llm_client.py → agent/src/ai/llm_client.py; pipeline-nodes.md: engine.py → pipeline_engine.py); 生成器源 (sync_ai_memory.py) 若重跑需确认其 source 列表已更新
- **d7 whitelist 新增 13 个 N##** (N177-N201): 这些 L1-小/中/L0 硬约束教训的检查清单在 env-hardrules.md / lesson 内联 / tech-stack, 不依赖 yn-matrices; 后续新增 L1-小/中 N## 应加入 `a_minus_c_whitelist` (thresholds.yaml)
- **检查器修复 3 处误报**: d7 README frontmatter next_n_id; d3 git hash tail + "L3 docs/" 路径片段; d3/d4 archived 豁免 — 均带回归测试 (test_doc_health_check.py)
