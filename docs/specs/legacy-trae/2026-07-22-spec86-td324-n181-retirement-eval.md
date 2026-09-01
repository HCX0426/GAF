---
spec_id: spec-86
title: TD-324 — N181 月度退役机制自动化
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-324]
related_n: [N181]
depends_on: []
blocks: []
priority: P1
size: 中 (新建 n181_retirement_eval.py + gaf_init.sh 集成 + 3+ tests, ~250 行)
---

# spec-86: TD-324 — N181 月度退役机制自动化

## 背景与问题

N181 月度退役机制已建立 (spec-59-C 2026-07-21, spec-62 TD-311 强化):
- 月度评估 failure-modes.md §Active N## 索引, 识别可退役候选
- Active N## > 70 硬阈值紧急评估
- 退役条件 A/B/C (连续 3 spec 未触发 / 已被新 N## 覆盖 / AI 默认行为已符合)
- 仅执行 1 次 (N165+N170 spec-59-D), 月度评估 + 紧急评估的执行频率和效果待观察
- **无自动化评估脚本**, 依赖 AI/人工手动检查

## 修复方案

新增 `scripts/governance/n181_retirement_eval.py`:
1. 解析 `failure-modes.md` Active N## 索引表, 提取所有 Active N## 编号
2. 检查 gaf_init.sh 已有 N_COUNT 统计, 但仅是行数统计, 不区分 Active/Retired/Dormant — 需要本脚本按段解析
3. 输出退役候选清单:
   - **条件 A 检查**: 扫描最近 3 个 spec 文件 (`.trae/specs/*.md`), 检查 N## 是否被提及 (grep `N<编号>`). 未提及 → 候选
   - **条件 B 检查**: 不自动判定 (需 AI 判断), 仅打印提示
   - **条件 C 检查**: 不自动判定 (需 AI 判断), 仅打印提示
4. 紧急阈值检查: Active N## > 70 → 打印警告 (不阻塞, 仅提示)
5. `--check` 模式: 仅报告, 不修改文件 (CI 友好)
6. `--threshold <N>`: 覆盖默认 70 阈值

集成到 gaf_init.sh:
- 在 L1 hard-load failure-modes.md 之后, 加一段 Active N## 计数 + > 70 警告 (非阻塞)
- 不调用本脚本 (避免每次启动跑全 spec 扫描), 仅做简单行数统计 + 阈值警告

## 实施清单

- [x] 新建 `scripts/governance/n181_retirement_eval.py`:
  - `parse_active_n_ids(failure_modes_path)`: 解析 Active N## 段, 返回 list of N##
  - `scan_recent_specs(specs_dir, n_ids, recent_count=3)`: 扫描最近 N 个 spec, 返回 {n_id: mention_count}
  - `find_retirement_candidates(active_n_ids, mention_map)`: 条件 A 候选 (mention_count=0)
  - `main()`: argparse + 报告生成
- [x] gaf_init.sh 加 Active N## > 70 警告 (在 L1 hard-load 之后)
- [x] gaf_init.ps1 同步加 Active N## > 70 警告 (TD-320 已建 PowerShell 版本)
- [x] 新建 `scripts/tests/test_n181_retirement_eval.py` (≥ 3 tests):
  - parse_active_n_ids 真实 repo 集成
  - scan_recent_specs 真实 repo 集成
  - find_retirement_candidates 逻辑测试 (tmp_path fixture)
- [x] 迁移 TD-324 从 active.md 到 fixed.md
- [x] sync_tech_debt_counts.py 同步计数
- [x] git add + commit
- [x] N176 hash 回填

## 验证标准

1. `n181_retirement_eval.py` 存在并跑通: 输出 Active N## 计数 + 退役候选清单
2. `--check` 模式: Active N## > 70 → exit 0 + WARN (非阻塞)
3. gaf_init.sh L1 hard-load 之后有 Active > 70 警告段
4. gaf_init.ps1 同步有 Active > 70 警告段
5. ≥ 3 tests 全通过

## N176 hash 回填

本 spec 完成后 commit hash 立即回填到此 frontmatter (TD-303 N176 规则).
