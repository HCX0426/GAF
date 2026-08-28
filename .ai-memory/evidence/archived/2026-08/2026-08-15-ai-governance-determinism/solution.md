# Solution: 落地 3 大确定性机制 (M1/M2/M3)

分 3 阶段实施, 每阶段 1 commit:

## M1 — 代码铁律 AST 静态检测 (Phase 1, commit -)
- `scripts/hooks/check_code_rules.py`: AST 静态分析, 5 条规则数据驱动注册表
  - R001 裸 except / pass-only 空体 → error (N182/N183)
  - R002 测试 time.sleep → warn
  - R003 硬编码 /api/v2 → warn
  - R004 cursor.execute f-string 拼接 SQL → error (放行 :VAR 参数化)
  - R005 schema 残留 (max_wait) → warn
- 增量门禁: 默认只扫 `git diff --cached -U0` 新增行 (R001 存量 84 文件历史债不阻塞);
  `--all` 全量审计; `--no-fail` warn-only
- 独立 hook `gaf-code-rules`: files `^(backend|agent)/.*\.py$`, pass_filenames true,
  pre-commit stage (不进 governance batch — always_run 全量太慢)
- utf-8-sig 读取防 BOM; 仓库外文件不做路径过滤 (测试场景)
- B2 触发 (678 行): 写 b2_acknowledged.json + spec-context 承载体
  (docs/archive/spec-context/2026-08-15-code-rules-hook-m1-context.md)
- 顺手修 gaf_governance_batch.py 注释漂移 (10 → 13)

## M3 — diff→lesson 触发式检索 (Phase 2, commit -)
- `scripts/lessons/match_lessons_by_diff.py`: 匹配 git diff 路径 + 新增行 token
  + 新增行原文子串 (支持复合词 sql-injection); 权重 diff_keywords +3 / related_files +2
- 回填 15 条高频 N## diff_keywords: N112/N124/N150/N151/N157/N166/N168/N169/N174/
  N182/N183/N191/N193/N195/N196 (N168 唯一副本在 archived-early)
- hook `gaf-lesson-diff-trigger`: post-commit stage, --base HEAD~1 --head HEAD
- check_lessons_updated.py 加 diff_keywords 校验 (仅字段存在时, warn-only)
- 更新 gaf-lesson-router SKILL.md §6 + lessons README (Quick Start + front-matter)

## M2 — 声称-激活率回执 (Phase 3, commit -)
- `scripts/hooks/check_claimed_rules.py`: 读 commit message 声称 N##,
  用 diff_keywords 校验 diff 证据 → positive / no-evidence / unknowable 三分
- 正向激活率 < 50% → warn; 结果追记 .ai-memory/ops/claimed-activation.md (幂等)
- 注册为 gaf_post_commit_batch.py CHECKS 第 3 项 (post-commit 只提示不阻断)

## 测试
- test_check_code_rules.py (15 例): 临时仓库 fixture 走真实路径过滤
- test_match_lessons_by_diff.py (9 例): parser/load/score/main
- test_check_claimed_rules.py (9 例): 提取/三分/幂等记录/端到端