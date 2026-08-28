---
spec_id: spec-90
title: TD-325 — 治理指标 dashboard (当前快照版)
created: 2026-07-22
status: ✅ done
commit: -
related_td: [TD-325]
related_n: [N167, N151]
depends_on: [spec-89]
blocks: []
priority: P2
size: 中 (新建 governance_dashboard.py ~435 行 + 首次生成 dashboard.md + 22 tests)
---

# spec-90: TD-325 — 治理指标 dashboard (当前快照版)

## 背景与问题

### 根因分析

TD-325 登记 (2026-07-21): doc_health P0/P1 趋势 + patch 成功率 + B1/B2/B4 调用频率 + spec 完成率等治理指标无统一可视化, 散落在各 spec evidence 中.

现状盘点 (本 spec 启动时实测):
- `docs/general/health-checks/2026-07.md` 有月度健康检查报告 (46 项, 28 通过/6 失败/12 需关注)
- `.trae/specs/` 67 个 spec 文件, frontmatter `status` 字段可统计完成率
- `docs/general/tech-debt/` active/fixed/wontfix 三文件计数已自动同步 (sync_tech_debt_counts.py)
- `.ai-memory/lessons/README.md` frontmatter 含 lessons_count/active_n_count/retired_n_count/archived_n_count/dormant_n_count
- `.ai-memory/meta/failure-modes.md` 含 Active/Retired/Dormant 段
- **无统一 dashboard** 汇聚这些指标

### 影响

- 治理健康度难以全局把握
- 趋势分析需人工翻 spec
- 指标散落, 无法快速回答 "当前治理状态如何"

## 修复方案

### N167 7 维度评分 (A/B/C 方案)

| 维度 | A 方案 (当前快照 dashboard) | B 方案 (历史趋势 dashboard) | C 方案 (CI 定时生成) |
|------|------|------|------|
| 1 架构长远性 | 3 (新建 dashboard 子系统) | 4 (含历史趋势, 更长远) | 3 (CI 集成) |
| 2 全局归一化 | 3 (单源汇聚) | 3 (多源 + 历史) | 3 (单源) |
| 3 改动量 | 4 (~350 行, 无 CI) | 2 (~800 行, 需数据持久化) | 2 (~500 行 + CI 配置) |
| 4 测试覆盖 | 4 (易测, 6+ tests) | 3 (需 mock 历史数据) | 3 (CI 难本地验证) |
| 5 文档完整 | 3 (新建 docs/governance/) | 3 (新建) | 3 (新建) |
| 6 风险 | 4 (低, 独立脚本) | 2 (高, 数据持久化复杂) | 3 (中, CI 配置) |
| 7 长期维护 | 3 (持续手动跑) | 3 (持续) | 4 (CI 自动) |
| **总分** | **24** | **20** | **21** |

### AI 自决 (用户授权"不用停"循环模式)

A 方案 24 分领先 B 4 分, 领先 C 3 分, 未达 N167 ≥ 5 分阈值. 但用户原话"按循环模式下开始, 短期和中期长都排进去, 不用停"明确授权 AI 自决推进. A 方案为最佳选择, 理由:
1. **风险最低**: 独立脚本, 无数据持久化复杂度, 无 CI 配置风险
2. **规模最小**: ~350 行, 适合循环模式快速推进
3. **可扩展**: 后续可加历史趋势 (B 方案) + CI (C 方案), 不影响当前实现

### 方案 A 详细设计

新建 `scripts/governance/governance_dashboard.py`:

1. **数据源** (5 类指标):
   - **spec 完成率**: 扫描 `.trae/specs/*.md` frontmatter `status` 字段, 统计 ✅ done vs 🚧 in_progress vs 无 frontmatter
   - **TD 计数**: 扫描 `docs/general/tech-debt/active.md` + `fixed.md` + `wontfix.md` (复用 sync_tech_debt_counts.py 逻辑)
   - **lessons 计数**: 读 `.ai-memory/lessons/README.md` frontmatter (lessons_count/active_n_count/retired_n_count/archived_n_count/dormant_n_count)
   - **failure-modes 计数**: 解析 `.ai-memory/meta/failure-modes.md` Active/Retired/Dormant 段 (复用 n181_retirement_eval.py 逻辑)
   - **doc_health 最新报告**: 读 `docs/general/health-checks/*.md` 最新文件 frontmatter (通过率/失败数)
2. **输出 `docs/governance/dashboard.md`**:
   - frontmatter (date + source + generated_by)
   - 概述段 (生成时间 + 5 类指标总数)
   - spec 完成率段 (✅ done / 🚧 in_progress / 无 frontmatter 计数 + 百分比)
   - TD 计数段 (active / fixed / wontfix 表格)
   - lessons 计数段 (5 字段表格)
   - failure-modes 计数段 (Active / Retired / Dormant 表格)
   - doc_health 最新报告段 (最新报告摘要)
3. **CLI 模式**:
   - 默认: 生成 / 更新 `docs/governance/dashboard.md`
   - `--check`: 仅报告, 不写文件 (CI 友好, exit 0)
   - `--dry-run`: 打印 dashboard 到 stdout
   - `--root <path>`: 覆盖默认 repo root

集成策略:
- **不加 pre-commit hook** (避免与 sync_tech_debt_counts.py 重复)
- **不集成到 gaf_init.sh** (避免每次启动跑全扫描)
- **不加 CI** (留到 TD-327 e2e CI 接入时一并加入)
- **手动跑** (与 spec_dependency_graph.py 策略一致)

## 实施清单

- [ ] 新建 `scripts/governance/governance_dashboard.py`:
  - `collect_spec_completion(specs_dir)`: 扫描 spec frontmatter status, 返回 {done, in_progress, no_frontmatter, total}
  - `collect_td_counts(tech_debt_dir)`: 扫描 active/fixed/wontfix, 返回 {active, fixed, wontfix, total}
  - `collect_lessons_counts(lessons_readme)`: 读 frontmatter, 返回 {lessons_count, active_n_count, retired_n_count, archived_n_count, dormant_n_count}
  - `collect_failure_modes_counts(failure_modes_path)`: 解析 Active/Retired/Dormant 段, 返回 {active, retired, dormant}
  - `collect_doc_health_latest(health_checks_dir)`: 读最新报告 frontmatter, 返回 {date, total, passed, failed, attention, pass_rate}
  - `render_markdown(metrics)`: 生成完整 markdown
  - `main()`: argparse + 文件写入
- [ ] 新建 `docs/governance/` 目录 (首次创建)
- [ ] 首次生成 `docs/governance/dashboard.md` (跑脚本写入)
- [ ] 新建 `scripts/tests/test_governance_dashboard.py` (≥ 6 tests):
  - `test_collect_spec_completion_real_repo` (真实 repo 集成)
  - `test_collect_td_counts_real_repo` (真实 repo 集成)
  - `test_collect_lessons_counts_real_repo` (真实 repo 集成)
  - `test_collect_failure_modes_counts_real_repo` (真实 repo 集成)
  - `test_collect_doc_health_latest_real_repo` (真实 repo 集成)
  - `test_render_markdown_full` (完整 markdown 内容)
  - `test_main_check_mode_exit_0` (CLI 端到端)
- [ ] 迁移 TD-325 从 `active.md` 到 `fixed.md` (✅ FIXED 段落)
- [ ] `sync_tech_debt_counts.py` 同步计数
- [ ] git add + commit (单行 `-m` per project_rules §3.4)
- [ ] N176 hash 回填 (follow-up edit, 不单独 commit)

## 验证标准

1. `scripts/governance/governance_dashboard.py` 存在并跑通: 输出 5 类指标
2. `docs/governance/dashboard.md` 存在, 含:
   - frontmatter (date + source + generated_by)
   - 概述段 (生成时间 + 5 类指标总数)
   - spec 完成率段 (done / in_progress / no_frontmatter 计数 + 百分比)
   - TD 计数段 (active / fixed / wontfix 表格)
   - lessons 计数段 (5 字段表格)
   - failure-modes 计数段 (Active / Retired / Dormant 表格)
   - doc_health 最新报告段 (最新报告摘要)
3. `--check` 模式: exit 0, 不写文件
4. `--dry-run` 模式: 打印 dashboard 到 stdout, 不写文件
5. ≥ 6 tests 全通过 (conda gaf env)
6. pre-commit hook 全通过 (gaf-governance-batch + B2 + spec_id + N105)
7. TD-325 段落从 active.md 迁移到 fixed.md
8. sync_tech_debt_counts.py 三源计数一致

## 范围说明 (本 spec 不做)

- **不做历史趋势**: 数据持久化机制未建立, 仅当前快照 (留到后续 spec)
- **不做 CI 定时生成**: 留到 TD-327 e2e CI 接入时一并加入
- **不做 HTML dashboard**: markdown 已足够, HTML 留到后续需求

## N176 hash 回填

本 spec 完成后 commit hash 立即回填到此 frontmatter (TD-303 N176 规则).

## 循环模式说明

用户原话"按循环模式下开始, 短期和中期长都排进去, 不用停":
- spec-89 TD-326 (spec 依赖图) ✅ commit `-`
- 本 spec 接修 TD-325 (dashboard, N167 评分 24, 当前快照版)
- 下一 spec 候选: TD-327 (e2e CI) / TD-335 (节点归一化长期)
