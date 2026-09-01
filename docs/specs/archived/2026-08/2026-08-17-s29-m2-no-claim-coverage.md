---
name: 2026-08-17-s29-m2-no-claim-coverage
date: 2026-08-17
task_type: refactor / new_feature
status: ✅ 已归档
start_ts: 2026-08-17T15:30:00+08:00
end_ts: 2026-08-17T15:50:00+08:00
commit_hash: '-'
source: TD-364 (s28 N180 元评估 W6) — M2 激活率只测"声称 N## 的 commit", 未声称的 commit 有覆盖率盲区
applies_to: [scripts/hooks/check_claimed_rules.py, scripts/tests/test_check_claimed_rules.py, docs/archive/active-tech-debt.md]
archived_at: 2026-08-17T15:55:00+08:00
archived_to: docs/specs/archived/2026-08/2026-08-17-s29-m2-no-claim-coverage.md
---

# s29: M2 No-Claim 覆盖率盲区修复 (TD-364)

> **来源**: s28 元评估 W6 → TD-364 登记 (2026-08-17). 弱触发"继续" → 接修下一个 TD.

## 问题

`check_claimed_rules.py` (M2) 只测 commit message 声称的 N##:
- commit message 含 N## → 校验 diff 证据, 追记 claimed-activation.md
- commit message 无声称 → `print("ℹ️ 无声称, 跳过")` + return 0

**盲区**: commit 改了规则文件 (`.skills/rules/` / `.ai-memory/` / `scripts/hooks/` 等) 但 message 未声称 N## → 完全不记录.
M2 数据无法反映"规则未被执行但未声称"的沉默违反, 激活率虚高.

## Phase 1: 实现 no-claim 检测

1. `check_claimed_rules.py` 新增 `RULE_DIRS` 常量 (规则影响文件前缀):
   - `.skills/rules/` (规则层)
   - `.ai-memory/` (记忆层, 排除 `ops/claimed-activation.md` 自身避免自记录循环)
   - `scripts/hooks/` (hook 执行器)
   - `scripts/lessons/` (lesson 管理)
   - `.pre-commit-config.yaml`
2. `main()` 无声称分支改为: 收集 changed_paths → 若命中 RULE_DIRS → 打印提示 + 追记 NO-CLAIM 行 (不阻断).
3. NO-CLAIM 行格式: `| timestamp | commit | claimed | positive | no-evidence | rate | verdict |` 复用表, verdict=`NO-CLAIM`, claimed=`-`(规则文件清单写入说明段或 no_evidence 列).

**设计决策 (N167 维度评估)**:
- 维度 1 架构长远性: 复用现有 7 列表 + 幂等写入, 不新开表 → 保持单一数据源
- 维度 2 全局归一化: RULE_DIRS 与 M3 的 diff 检测对齐 (同一 git diff 数据源)
- 维度 7 长期维护成本: 约 30 行新增, 无新依赖, hook 开销 < 10ms

## Phase 2: 测试

`test_check_claimed_rules.py` 新增:
- `test_rule_dirs_excludes_ops_record`: RULE_DIRS 不含 ops/claimed-activation.md
- `test_main_no_claims_rule_files_records`: 无声称 + 改 .ai-memory/ → 记录 NO-CLAIM 行
- `test_main_no_claims_no_rule_files_skip`: 无声称 + 不改规则文件 → 不记录 (保持原行为)
- `test_no_claim_record_idempotent`: 同 commit 不重复记录

## 验收标准

1. `pytest scripts/tests/test_check_claimed_rules.py` 全过 (原 17 + 新 4 = 21)
2. `python scripts/hooks/check_claimed_rules.py --commit - --no-record` 输出 NO-CLAIM 提示 (该 commit 改了 docs/specs/ 未声称 N##)
3. 普通 commit (无声称 + 非规则文件) 不产生新记录
4. TD-364 迁移到 fixed-tech-debt.md

## Deviation Log

- RULE_DIRS 执行时扩展含 `docs/specs/` (spec 是 AI 工作流承载体, TD-342) + `.skills/skills/` (skill 定义层)
- RULE_DIRS_EXCLUDE 从单文件改为整个 `.ai-memory/ops/` 目录 (why-skipped 等运营产物同样不该触发)
- 测试 6 个新用例 (spec 计划 4 个 + 补 2 个: RULE_DIRS 含 specs / 排除 ops 目录)