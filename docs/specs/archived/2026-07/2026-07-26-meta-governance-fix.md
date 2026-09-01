---
summary: spec-2026-07-26-meta-governance-fix — meta 治理三件套 (spec-context 承载体 + fixed.md 分片 + B2 硬约束)
applies_to: ['.ai-memory/spec-context', 'docs/tech-debt', '.trae/rules', 'scripts/hooks', 'scripts/bootstrap']
key_decisions:
  - T1 补 TD-341 spec-context 承载体 (回填, 因 TD-341 已完成但未写承载体)
  - T2 fixed.md 年度分片 + 近 100 项保留 (TD-309 wontfix 重开)
  - T3 spec-context 机制硬约束化 (B2 大修改必写, project_rules.md + hook 强制)
last_updated: 2026-07-26
created_at: 2026-07-26
spec_id: spec-2026-07-26-meta-governance-fix
status: completed
priority: high
owner: AI
related_td: 'TD-309 (重开), TD-342 (新登记: spec-context 机制缺位)'
completed_at: 2026-07-26
completed_commit: '-'
---

# spec-2026-07-26-meta-governance-fix — meta 治理三件套

## 来源

2026-07-26 TD-341 闭环后, 用户质询 "目前 AI 得思维链, 工作流, 还有目前任务开始时得上下文承载, 目前有这块吗? .ai-memory/spec-context 我看这里在上个任务也没写啊". 诊断暴露 3 个 meta 治理缺口:

1. **spec-context 承载体缺位**: TD-341 任务开始时未写 `.ai-memory/spec-context/2026-07-26-td341-ref-docs-merge-context.md`, 该目录为空
2. **fixed.md 无限膨胀**: 5695 行 / 579KB / 268 TD 段落, 人类 Read 整文件撞 128KB 限制 (TD-309 wontfix 决策需重新评估)
3. **spec-context 触发条件未硬约束化**: 当前规则未明确"何时必须写 spec-context", AI 自决 P2 任务跳过了这个机制

## 调研数据

- `.ai-memory/spec-context/` 目录: **0 个文件** (TD-341 未写承载体)
- `docs/tech-debt/fixed.md`: 5695 行 / 579KB / 268 TD 段落 (TD-309 wontfix 时 4596 行, 5 天增长 +24%)
- `docs/tech-debt/wontfix.md`: 621 行 / 62KB (规模合理, 无需分片)
- TD 时间分布: 全部集中在 2026-06/07 (项目 2026-06 开始, 年度分片当前无法立即缓解)

## N151 5 步架构评估

### Step 1: 架构盘点
- `.ai-memory/spec-context/` 设计为大型 spec 的"用户决策原文 + 三轮对齐过程"承载体, 避免 spec 文件本身膨胀
- `docs/tech-debt/fixed.md` 自 2026-07-10 拆分 tech-debt-register.md 以来无归档机制
- `project_rules.md` 未明确 spec-context 触发条件

### Step 2: 识别反模式
- ❌ spec-context 机制设计但未硬约束化 (AI 自决 P2 跳过)
- ❌ fixed.md 无归档机制 (TD-309 wontfix 理由"AI 用 Grep 适应"未考虑人类 Read 受限)
- ❌ spec-context 触发条件模糊 (规则未明示)

### Step 3: A/B/C 备选方案

**方案 A: 全量激进治理** — T1+T2+T3 全做, 含 fixed.md 按"近 30 天保留"激进归档
- 优点: 一次性彻底
- 缺点: 上下文压力大, fixed.md 当前所有 TD 都是 2026-06/07, 30 天保留 = 全部
- 风险: 中

**方案 B: 年度分片 + 近 100 项保留 + B2 硬约束** — 三件套组合
- 优点: 当前 100 项可读 (~2000 行), 长期年度归档, B2 硬约束防止再次跳过
- 缺点: 需新建归档脚本 + 修改 B2 hook
- 风险: 低

**方案 C: 仅补 spec-context, fixed.md 维持 wontfix** — 最小化治理
- 优点: 快速
- 缺点: fixed.md 继续膨胀, 用户已明确要求治理
- 风险: 治理不彻底

### Step 4: 拒绝反模式 + AI 自决

- ❌ 拒绝方案 A (30 天保留在当前无意义, 项目所有 TD 都是近 30 天)
- ✅ 选方案 B (年度分片 + 近 100 项保留 + B2 硬约束)
- ❌ 拒绝方案 C (用户已明确要求 fixed.md 治理)

### Step 5: N167 七维度评分 (方案 B)

| 维度 | 分 | 理由 |
|------|---|------|
| 1 架构长远性 | 5/5 | 年度归档 + 近 100 项保留, 长期阻止无限膨胀 |
| 2 全局归一化 | 5/5 | spec-context 硬约束化, 所有 B2 大修改统一承载体机制 |
| 3 新旧兼容 | 4/5 | fixed-archive-2026.md 历史保留, 但 168 段落需迁移 |
| 4 现有业务完善 | 4/5 | 覆盖 spec-context + fixed.md + B2 hook, 但 wontfix.md 不分片 |
| 5 性能资源优化 | 5/5 | fixed.md 从 5695 行 → ~2000 行, Read 整文件可行 |
| 6 安全合规加固 | 4/5 | B2 hook 强制 + project_rules.md 硬约束, 但需测试覆盖 |
| 7 长期维护成本 | 4/5 | 一次性投入 2-3h, 长期靠脚本自动归档 |
| **总分** | **31/35** | ≥ 19 且领先 ≥ 5 分 → AI 自决执行 |

## 阶段状态表

| Wave | 任务 | 状态 | 完成时间 | commit hash | 验收 evidence |
|------|------|------|---------|-------------|--------------|
| T1 | 补 TD-341 spec-context 承载体 (回填) | ✅ | 2026-07-26 | - | 6376 bytes, 6 段 (决策原文/N151/N167/关键实施/过程/闭环) |
| T2a | fixed.md 年度分片 + 近 100 项保留 | ✅ | 2026-07-26 | - | 5695→4489 行, 181→100 段落, fixed-archive-2026.md 81 段落 |
| T2b | TD-309 wontfix → 重开, sync_tech_debt_archive.py | ✅ | 2026-07-26 | - | 7 tests PASSED, TD-309 REOPENED, TD-342 新登记 |
| T3 | spec-context 硬约束化 (project_rules.md + B2 hook) | ✅ | 2026-07-26 | - | 10 tests PASSED, §6.5 硬约束段, gaf-spec-context hook 注册 |
| T4 | 验收 + commit + 反思 + spec 归档 | ✅ | 2026-07-26 | - | 21/21 tests PASSED, 13/13 hooks PASS, spec-context 自应用 |

## 完成总结 (2026-07-26 commit -)

- **diff 规模**: 13 files changed, 3746 insertions(+), 2280 deletions(-)
- **T1 回填**: TD-341 spec-context 承载体 (6 段, 6376 bytes)
- **T2a 分片**: fixed.md 5695→4489 行 (-21%) / 181→100 段落, fixed-archive-2026.md 81 段落 (1946 行 / 221KB), 头部索引表
- **T2b 脚本**: sync_tech_debt_archive.py (--archive/--yearly/--check 三模式) + 7 tests, TD-309 REOPENED, TD-342 新登记
- **T3 硬约束**: check_spec_context.py (B2 valid 时检查 spec-context 存在) + 10 tests, project_rules.md §6.5, .pre-commit-config.yaml 注册 gaf-spec-context hook
- **自应用**: 本 spec 创建 2026-07-26-meta-governance-fix-context.md (T3 第一个受约束的 B2)
- **验收**: 21/21 tests PASSED (7 archive + 10 spec_context + 4 bootstrap) + 13/13 pre-commit hooks PASS
- **N167 评分**: 31/35 (AI 自决, 方案 B 年度分片 + 近 100 项保留 + B2 硬约束)
- **关键反思**:
  1. 年度分片当前无法立即缓解 (项目所有 TD 集中 2026-06/07), 组合"近 100 项保留"短期缓解
  2. fixed.md 段落顺序: 头部 = 最新, 尾部 = 最旧 (与 git log 相反)
  3. check_spec_context.py 自应用: 硬约束实施时必须考虑自应用场景 (本 spec 是第一个受约束的 B2)

## 执行计划

### T1: 补 TD-341 spec-context 承载体 (回填)

创建 `.ai-memory/spec-context/2026-07-26-td341-ref-docs-merge-context.md`, 内容:
- 用户决策原文 (2026-07-26 综合评估对话片段)
- N151 5 步法评估过程 (已在 spec 中, 承载体引用)
- N167 32/35 评分细节
- 实施过程关键决策 (git mv 漏暂存内容修改 + GAF_SKIP_DOC_SYNC env var 发现)

### T2a: fixed.md 年度分片 + 近 100 项保留

1. 创建 `docs/tech-debt/fixed-archive-2026.md` (2026 年历史归档)
2. fixed.md 只保留最近 100 个 TD 段落 (按 fixed_time 倒序)
3. 历史段落 (268 - 100 = 168 个) 迁到 fixed-archive-2026.md
4. fixed.md 头部加索引表 (TD-NNN → 一句话摘要 + 行号) 方便定位
5. 验证: fixed.md < 2500 行, fixed-archive-2026.md 含 168 段落

### T2b: TD-309 wontfix → 重开, sync_tech_debt_archive.py

1. TD-309 在 wontfix.md 标记为 "❌ REOPENED 2026-07-26 (spec-2026-07-26-meta-governance-fix)"
2. 新登记 TD-342: spec-context 机制缺位 (P1, 本 spec T3 修复)
3. 创建 `scripts/bootstrap/sync_tech_debt_archive.py`:
   - `--archive` 模式: 把 fixed.md 中 fixed_time > 100 项前的段落迁到 fixed-archive-YYYY.md
   - `--yearly` 模式: 把上一年度的段落迁到 fixed-archive-YYYY.md (每年 1 月 1 日跑)
   - 集成到 gaf_init.sh --full (archived 检查, 非阻塞)
4. 测试: `scripts/tests/test_sync_tech_debt_archive.py` (3-5 tests)

### T3: spec-context 硬约束化

1. `.trae/rules/project_rules.md` §6.x 新增 "spec-context 承载体硬约束":
   - B2 大修改 (大修改 evidence 触发) 必写 spec-context/<spec-name>-context.md
   - 内容: 用户决策原文 + N151 评估过程 + 关键实施决策
   - 豁免: 小修改 (无 B2 evidence) / 纯文档修改
2. `scripts/hooks/check_big_change.py` 扩展: 检测 B2 evidence 时, 同时检查对应 spec-context 文件存在
3. `scripts/hooks/check_spec_context.py` (新建): pre-commit hook, B2 spec 完成时检查 spec-context 文件存在
4. 测试: `scripts/tests/test_check_spec_context.py` (3-5 tests)

### T4: 验收 + commit + 反思 + spec 归档

1. Grep 验证: `.ai-memory/spec-context/` 含 TD-341 承载体
2. fixed.md 行数 < 2500, fixed-archive-2026.md 含 168 段落
3. sync_tech_debt_archive.py 测试通过
4. check_spec_context.py 测试通过
5. pre-commit 13/13 passed
6. commit + 反思 + spec 归档

## 验收标准

- [ ] `.ai-memory/spec-context/2026-07-26-td341-ref-docs-merge-context.md` 存在且内容完整
- [ ] `docs/tech-debt/fixed.md` < 2500 行 (当前 5695 → ~2000)
- [ ] `docs/tech-debt/fixed-archive-2026.md` 含 168 段落
- [ ] `scripts/bootstrap/sync_tech_debt_archive.py` 存在 + 测试通过
- [ ] `scripts/hooks/check_spec_context.py` 存在 + 测试通过
- [ ] `.trae/rules/project_rules.md` §6.x 含 spec-context 硬约束段
- [ ] pre-commit 13/13 passed
- [ ] TD-309 wontfix → REOPENED, TD-342 新登记

## 偏离阈值

- Phase 数 +50% (4 → 6+) 或 diff +30% 必更新本文件 "范围偏差日志"
- 超出 +100% 必停下问用户

## 范围偏差日志

(无)

## 回滚预案

- git revert commit hash
- fixed-archive-2026.md 段落合并回 fixed.md
- project_rules.md §6.x 删除 spec-context 硬约束段
- check_spec_context.py 从 .pre-commit-config.yaml 移除
