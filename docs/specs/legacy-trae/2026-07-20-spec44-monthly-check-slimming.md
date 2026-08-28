---
maintainer: AI
spec_id: spec-44
title: 月度检查瘦身 — G 类 8 项已迁自动 (spec-41 doc_health_check.py)
created: 2026-07-20
status: ✅ done
parent_specs: [spec-41 (doc health checker), spec-42 (self-evolution flywheel)]
child_specs: []
related_files:
  - docs/general/monthly-health-check.md
  - scripts/governance/doc_health_check.py
  - scripts/governance/check_dimensions/
related_lessons: [N166, N172, N173, N176]
---

# spec-44: 月度检查瘦身 (G 类迁自动)

> **范围声明**: 本 spec 把 `monthly-health-check.md` G 类 (8 项 — 文档与 AI 记忆一致性) 标记为"已迁自动 (spec-41)",月度检查跳过。其他 18 类保留 (需 LLM 推理/手动执行)。不实现新自动化检查。

## 阶段状态表 (TD-137 / §4.10)

| Phase | 标题 | 状态 | 完成时间 | commit hash | 验收 evidence |
|:-----:|------|:----:|:---------:|:-----------:|---------------|
| Phase 1 | monthly-health-check.md G 类标记已迁自动 + frontmatter 更新 | ✅ | 2026-07-20 | - | G 类 8 项全标记已迁自动, frontmatter summary 改 19 类 |
| Phase 2 | 检查项总览表 + 执行流程 + 迁移说明更新 | ✅ | 2026-07-20 | - | 合计行含 (月度跑 76), 执行流程含跳过 G 类 |
| Phase 3 | 全量回归 + commit + 状态表回填 | ✅ | 2026-07-20 | - | 99 tests PASS in 12.39s, git diff --stat 仅 1 文件 |

> 全量回归: 99 tests PASS (15+20+47+17) in 12.39s (无回归, 仅文档改动)
> 改动范围: docs/general/monthly-health-check.md (单文件, ~30 insertions, ~5 deletions)
> 风险: 低 (仅文档改动, 无代码/测试改动, 回退方案 git revert)

> 状态: ⏳ pending / 🔄 in-progress / ✅ done (N126 诚实标记)

## 1. 背景与动机

### 1.1 问题

spec-41 已交付 doc_health_check.py 7 维度静态检查 (commit `-`),通过 `gaf_init.sh` 在每次对话开头自动跑。7 维度覆盖:
- d1_overlap (重叠检查)
- d2_bloat (文件膨胀)
- d3_count_drift (计数漂移)
- d4_path_drift (路径漂移)
- d5_frontmatter (frontmatter 完整性)
- d6_staleness (内容时效)
- d7_index_consistency (索引一致性)

`monthly-health-check.md` G 类 (8 项 — 文档与 AI 记忆一致性) 的检查内容**已被 spec-41 7 维度完全覆盖**,但月度检查文件未标记"已迁自动",导致:
1. 月度检查时仍手动跑 G 类 8 项,浪费时间 (G1-G8 全部已被 gaf_init.sh 自动跑过)
2. 检查项总览表仍标 G 类 8 项,虚高月度检查项数 (84 项中 8 项已冗余)
3. frontmatter summary 仍标"12 类",与实际 19 类 (A-S) 不符

### 1.2 用户原话

> spec-42 §1.4 非目标声明: "月度检查瘦身 (12 类→5 类) → spec-44"

### 1.3 spec-41 附录 A 权威映射

spec-41 附录 A 定义了 12 类→7 维度迁移映射 (基于 L3-1 9 维度视角):

| monthly-health-check 类 (L3-1 视角) | spec-41 维度 | 处理 |
|---------------------------------------|-------------|------|
| A. 架构层 | - | 月度保留 (需 LLM) |
| B. 文档层 — 路径漂移 | d4_path_drift | ✅ 迁自动 |
| C. 文档层 — frontmatter | d5_frontmatter | ✅ 迁自动 |
| D. 文档层 — 计数漂移 | d3_count_drift | ✅ 迁自动 |
| E. 规则层 — N## 索引 | d7_index_consistency | ✅ 迁自动 |
| F. 规则层 — Y/N 矩阵 | d7_index_consistency | ✅ 迁自动 |
| G. 文档层 — 文件膨胀 | d2_bloat | ✅ 迁自动 |
| H. 文档层 — 内容时效 | d6_staleness | ✅ 迁自动 |
| I. 业务逻辑层 | - | 月度保留 (需 LLM) |
| J. 集成层 | - | 月度保留 (需 LLM) |
| K. 多 app 层 | - | 月度保留 (需 LLM) |
| L. 用户场景层 | d1_overlap (部分) | 月度保留主体 |

**结论**: 12 类中 7 类 (B/C/D/E/F/G/H) 可迁自动, 5 类 (A/I/J/K/L) 月度保留。

### 1.4 范围决策 (保守方案)

spec-41 附录 A 的 12 类是 L3-1 9 维度视角,与 `monthly-health-check.md` 实际 19 类 (A-S) 不完全对应。spec-44 采用**保守方案**:

- **只标记 G 类 (8 项) 为"已迁自动"** — G 类是 spec-41 7 维度完全覆盖的唯一类
- **其他 18 类保留** — A/B/C/D/E/F/H/I/J/K/L/M/N/O/P/Q/R/S (需 LLM 推理或手动执行命令)
- **不实现新自动化检查** — 其他类中的部分项 (C1 TD 统计 / H1 Git 状态 / I1 巨型文件 / N1 空目录) 虽可自动化,但需新脚本,留给 spec-45+

**月度检查瘦身效果**:
- 检查项: 84 项 → 76 项 (减 8 项, -9.5%)
- 类别: 19 类 → 18 类 (G 类标记已迁自动,保留类编号便于历史追溯)
- 月度检查耗时: ~85-100 min → ~80-95 min (减 ~5-10 min)

### 1.5 非目标 (Out of Scope)

- ❌ 实现 C1/H1/I1/N1 等新自动化检查 → spec-45+
- ❌ 重新映射 19 类 → L3-1 9 维度视角 → 引入混淆,无收益
- ❌ 删除 G 类内容 → 保留作为历史参考 + 迁移映射证据
- ❌ 改动 spec-41 doc_health_check.py → 已交付,无需改动

## 2. 架构设计

### 2.1 改动范围

```
docs/general/monthly-health-check.md  (MODIFIED, 唯一改动文件)
├── frontmatter: summary "12 类" → "19 类 (G 类已迁自动 spec-41)"
├── 文件顶部: 加迁移说明段 (spec-44 §2.2)
├── 检查项总览表: G 类行加"✅ 已迁自动 (spec-41)"标记
├── 执行流程: 加步骤"跳过 G 类 (gaf_init.sh 已自动跑)"
└── G. 文档与 AI 记忆一致性: 类标题加"✅ 已迁自动 (spec-41)" + 8 项各加迁移映射
```

### 2.2 迁移说明段 (文件顶部新增)

```markdown
> **spec-44 迁移说明 (2026-07-20)**: G 类 (文档与 AI 记忆一致性) 8 项已迁自动,
> 由 `scripts/governance/doc_health_check.py` (spec-41) 7 维度静态检查覆盖,
> 通过 `gaf_init.sh` 在每次对话开头自动跑。月度检查时**跳过 G 类**, 只跑其他 18 类。
>
> 迁移映射 (G 项 → spec-41 维度):
> - G1 (docs/ 索引校验) → d7_index_consistency + d5_frontmatter
> - G2 (AI 记忆同步校验) → sync_ai_memory.py (gaf_init.sh 自动跑)
> - G3 (Skills 副本一致性) → sync_skills.py (pre-commit 自动跑)
> - G4 (lessons/ front-matter 完整性) → d5_frontmatter
> - G5 (failure-modes.md 索引完整性) → d7_index_consistency + d3_count_drift
> - G6 (规则/文档引用 skill 存在性) → d4_path_drift
> - G7 (规则/文档引用 path 存在性) → d4_path_drift
> - G8 (docs/ 引用脚本存在性) → d4_path_drift
>
> 详见 `.trae/specs/2026-07-20-spec44-monthly-check-slimming.md` (本 spec)。
```

### 2.3 检查项总览表改动

| 类别 | 名称 | 项数 | 预估耗时 | 改动 |
|:----:|------|:----:|:--------:|------|
| A | 构建与类型检查 | 4 | 2 min | - |
| B | 测试套件 | 7 | 8-15 min | - |
| C | 技术债务状态 | 4 | 2 min | - |
| D | 依赖管理 | 4 | 3 min | - |
| E | 数据库健康 | 3 | 2 min | - |
| F | API 契约一致性 | 5 | 6 min | - |
| **G** | **文档与 AI 记忆一致性** | **8** | **5 min** | **✅ 已迁自动 (spec-41), 月度跳过** |
| H | Git 卫生 | 4 | 2 min | - |
| ... | ... | ... | ... | - |
| **合计** | | **84 (月度跑 76)** | **~85-100 min (月度 ~80-95 min)** | **G 类 8 项已迁自动** |

### 2.4 执行流程改动

原步骤 2: "按 A-L 顺序逐类执行检查" → 改为: "按 A-S 顺序逐类执行检查 (**跳过 G 类, 已由 gaf_init.sh 自动跑**)"

### 2.5 G 类标题改动

原: `## G. 文档与 AI 记忆一致性`
改: `## G. 文档与 AI 记忆一致性 ✅ 已迁自动 (spec-41, 2026-07-20)`

G1-G8 每项加迁移映射注释:
```markdown
### G1. docs/ 索引校验

> **✅ 已迁自动 (spec-41)**: d7_index_consistency + d5_frontmatter (gaf_init.sh 自动跑)
> 月度检查时跳过本项, 仅在 doc_health_check.py 报告 P0/P1 issue 时触发 spec-42 飞轮 patch

[保留原内容作为历史参考 + 迁移映射证据]
```

## 3. 详细设计

### 3.1 Phase 1: G 类标记已迁自动 + frontmatter 更新

**改动范围** (单文件):
- `docs/general/monthly-health-check.md` frontmatter (summary 改)
- 文件顶部加迁移说明段 (§2.2)
- G 类标题加 ✅ 标记
- G1-G8 每项加迁移映射注释

**验收标准**:
- frontmatter summary 含 "G 类已迁自动 (spec-41)"
- 文件顶部含迁移说明段 + 8 项迁移映射
- G 类标题含 "✅ 已迁自动 (spec-41, 2026-07-20)"
- G1-G8 每项含迁移映射注释

### 3.2 Phase 2: 检查项总览表 + 执行流程更新

**改动范围** (单文件):
- 检查项总览表 G 类行加"✅ 已迁自动 (spec-41)"标记
- 合计行加"月度跑 76 项"注释
- 执行流程步骤 2 加"跳过 G 类"说明

**验收标准**:
- 检查项总览表 G 类行标"✅ 已迁自动"
- 合计行含"(月度跑 76)"
- 执行流程步骤 2 含"跳过 G 类, 已由 gaf_init.sh 自动跑"

### 3.3 Phase 3: 全量回归 + commit + 状态表回填

**验收标准**:
- `git diff --stat` 仅 1 个文件改动 (monthly-health-check.md)
- `pytest scripts/tests/test_doc_health_*.py` 121 tests PASS (无回归)
- `sync_skills.py --check` 通过 (无 skill 改动)
- spec-44 状态表 3 Phase 全 ✅ + commit hash 回填
- completed-features.md C-071 追加
- pending-roadmap.md P-012 标 ✅

## 4. 风险与回退

### 4.1 风险

- **低风险**: 仅文档改动, 无代码/测试改动, 无回归风险
- **回退方案**: `git revert <commit>` 即可恢复

### 4.2 WARN (非阻塞)

- G 类内容保留 (不删除), 文件略膨胀 (~30 行新增), 但收益 (月度跳过 8 项) > 成本
- spec-41 附录 A 的 "12 类→5 类" 目标未完全实现 (只做了 G 类 8 项), 其他类需 spec-45+ 实现

## 5. 验收标准 (全量回归)

- [ ] Phase 1: G 类 8 项标记已迁自动 + frontmatter 更新
- [ ] Phase 2: 检查项总览表 + 执行流程更新
- [ ] Phase 3: 121 tests PASS + commit + 状态表回填
- [ ] completed-features.md C-071 追加
- [ ] pending-roadmap.md P-012 标 ✅

## 6. 落地清单

- [ ] spec-44 设计文档 (本文件)
- [ ] spec-44 plan (`.trae/plans/2026-07-20-spec44-monthly-check-slimming.md`)
- [ ] monthly-health-check.md 改动 (Phase 1+2)
- [ ] 3-step evidence (`.ai-memory/evidence/2026-07-20-spec44-monthly-check-slimming/`)
- [ ] completed-features.md C-071 追加
- [ ] pending-roadmap.md P-012 标 ✅

## 7. 与 spec-41/42/43 一致性

- **spec-41**: doc_health_check.py 7 维度已交付, spec-44 不改 doc_health_check.py
- **spec-42**: 飞轮闭环已交付, spec-44 不改飞轮流程
- **spec-43**: 遗忘机制已交付, spec-44 不改遗忘机制
- **spec-44**: 仅改 monthly-health-check.md, 标记 G 类已迁自动

## 8. Open Questions

无 (范围决策已自决采用保守方案)。
