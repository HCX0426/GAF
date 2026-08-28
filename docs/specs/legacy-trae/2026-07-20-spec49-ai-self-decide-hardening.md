---
spec_id: spec-49
title: AI self-decide framework hardening — 5 layers 7 improvements
status: ✅ done
created: 2026-07-20
last_updated: 2026-07-20
related: spec-42 (AI patch flywheel), spec-47/48 (self-decide practice)
n167_score: 19/21 (AI self-decide)
---

# Spec-49: AI 自决框架加固 — 5 层 7 项改进

> **来源**: spec-48 commit (`-`) 后用户要求"评估下各部分 ai 自决是否完善" → AI 评估 11 项中 6 ✅ + 5 🟡 + 0 ❌ → 用户"开吧, 然后改进上面这些所有内容"
> **目标**: 加固 5 层 AI 自决体系 (L1 红线 + L2 N167 + L3 spec 内 + L4 spec 间 + L5 subagent) 的 5 🟡 缺陷 + 2 P3 改进, 消除评分主观空间 + 循环终止失控 + subagent 质量失控 3 大风险

## 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | L2 N167 评分强化 (反向论证 + ⑤⑥ 必填理由 + 硬场景 ③ 判定) | ✅ | 2026-07-20 | - | gaf-reflect-and-evolve §7.4-7.5 + project_rules §2.0.5 + _refactor-dimensions.md 3 行 Y/N |
| Phase 2 | L4 spec 间循环强化 (触发词分级 + 硬终止 + L3-1 频率归一) | ✅ | 2026-07-20 | - | project_rules §3.6+§3.7 + _workflow.md §㉝ 4 行 Y/N |
| Phase 3 | L5 subagent 并行强化 (隐性冲突 Grep + 质量抽查 + prompt 规则摘要) | ✅ | 2026-07-20 | - | project_rules §3.6 N175 + _ai-autonomy.md §㉙ 3 行 Y/N |
| Phase 4 | L3 spec 内偏离阈值规则 | ✅ | 2026-07-20 | - | project_rules §3.6 偏离阈值 (50%/30%/100%) |
| Phase 5 | AI patch 飞轮连续失败通知 | ✅ | 2026-07-20 | - | gaf-orchestrator §0.5 红线 2 条 |
| Phase 6 | L1 红线文件判定标准 + 文件删除归一 | ✅ | 2026-07-20 | - | project_rules §3.5 三档判定 + 流程 |
| Phase 7 | 验证 + 全量回归 + 状态同步 | ✅ | 2026-07-20 | - | sync 4 工具 PASS + doc_health P0=0 P1=0 + 50 tests PASS |

## §1 Background

### 1.1 来源

- **spec-47 + spec-48 实践**: 两次 19/21 N167 自决成功, 但暴露评分主观空间 (⑤⑥ 默认 2 分凑 19)
- **AI 自决评估** (2026-07-20): 11 项中 6 ✅ + 5 🟡 + 0 ❌, 3 P1 + 2 P2 + 2 P3 改进项
- **核心风险**: 评分主观空间 + 循环终止失控 + subagent 质量失控

### 1.2 7 项改进清单

| ID | 优先级 | 层级 | 缺陷 | 改进 |
|----|--------|------|------|------|
| I1 | P1 | L2 N167 | 主观空间 + 反向论证缺失 + 硬场景 ③ 模糊 | 反向论证必填 + ⑤⑥ 必填理由 + 硬场景 ③ 判定流程 |
| I2 | P1 | L4 spec 间 | 触发词误判 + 无硬终止 + L3-1 频率冲突 | 触发词强/弱分级 + 连续 3 spec 硬终止 + L3-1 频率归一 |
| I3 | P1 | L5 subagent | 隐性冲突无检测 + 质量仅数量核查 + 无规则摘要 | 隐性冲突 Grep + 质量抽查 1 文件 + prompt 含规则摘要 |
| I4 | P2 | L3 spec 内 | 偏离阈值规则缺失 | Phase 数 +50% 或 diff +30% 必更新 spec + commit message 标注 |
| I5 | P2 | AI patch 飞轮 | 连续失败无通知 | 连续 ≥3 个 patch 失败必须停下报告用户 |
| I6 | P3 | L1 红线 | 重要 vs 垃圾文件判定缺失 | 加 "git 追踪 + 涉及代码" 需评估, 纯临时文件直接删 |
| I7 | P3 | 文件删除 | 与 I6 同根因 | 合并到 I6 |

### 1.3 根因

- **L2 评分主观**: 7 维度中 ⑤ 性能 + ⑥ 安全 在 GAF 项目"优先级中/低", AI 易默认打 2 分凑 19
- **L4 循环终止失控**: L3-4 终止条件 "连续 2 轮无新 [A]" 在每轮 P2→P1 升级时永不触发
- **L5 subagent 质量失控**: N175 落地检查仅核查 "数量一致", 未检查内容质量
- **L1 文件判定缺失**: §3.5 "本地文件删除已放开" 未区分 "重要代码文件" vs "临时垃圾文件"

## §2 N167 七维度评分 (方案 A: 单 spec 7 Phase 全量治理)

| 维度 | 分数 | 理由 |
|------|------|------|
| ① 架构长远性 | 3 | 加固 5 层自决体系, 消除评分主观空间 + 循环失控 + 质量失控 3 大风险, 3-5 年受益 |
| ② 全局归一化 | 3 | 统一 project_rules + handbook + skill + yn-matrices 4 处规则, 消除重复 |
| ③ 新旧兼容 | 3 | 单人自用项目, 一次性切换, 无过渡逻辑 |
| ④ 现有业务完善 | 3 | 覆盖 7 项全部改进 (3 P1 + 2 P2 + 2 P3), 无遗漏 |
| ⑤ 性能资源优化 | 2 | 规则文档变更, 不改代码性能 (必填理由: GAF 项目性能优先级中, 规则变更不影响运行时性能) |
| ⑥ 安全合规加固 | 2 | 规则文档变更, 不改代码安全 (必填理由: GAF 项目安全优先级低, 规则变更不影响权限/审计) |
| ⑦ 长期维护成本 | 3 | 配套 evidence + yn-matrices 更新 + 状态同步, 长期受益 (规则明确减少后续 AI 误判) |
| **总分** | **19/21** | ✅ AI 自决 |

### 2.1 反向论证 (spec-49 新增要求)

**为什么不选方案 B (分 3 spec, 每个 P1 一个)?**:
- 3 spec 各自独立 commit, 增加弹窗频次 (违反 N176 单对话单 commit)
- 3 spec 之间有依赖 (L2 评分强化影响 L4/L5 判定), 拆分需协调
- 总 diff 相同, 拆分只增加管理成本

**为什么不选方案 C (只修 3 P1, 跳过 P2/P3)?**:
- P2 (L3 偏离阈值) 在 spec-47 已暴露 (3 轮修复未标偏离)
- P3 (L1 文件判定) 与 I6/I7 同根因, 一起修成本更低
- 留 P2/P3 会成新 TD, 违反"技术债务不堆积" (§0 核心约束)

### 2.2 硬场景检查

- ① FK 绊住? N (纯规则文档)
- ② schema 分裂? N
- ③ 业务语义? N (规则变更不影响业务数据)
- ④ 不可逆? N

## §3 Phase 1: L2 N167 评分强化 (I1)

### 3.1 改进点

1. **反向论证必填**: 评分模板加 "为何不选 B/C" 必填段, 每个 non-selected 方案 ≥2 条具体理由
2. **⑤⑥ 维度必填理由**: 不允许默认 2 分, 必填 "为何打此分" 一行理由
3. **硬场景 ③ 判定流程**: 加 "问: 这个决策影响数据保留/业务流程吗? Y → AskUserQuestion" 判定步骤

### 3.2 涉及文件

- `gaf-reflect-and-evolve/SKILL.md §7` (评分模板权威源)
- `project_rules.md §2.0.5` (硬约束层)
- `.ai-memory/meta/yn-matrices/_refactor-dimensions.md` (Y/N 矩阵)

### 3.3 具体修改

#### 3.3.1 `gaf-reflect-and-evolve/SKILL.md §7.5` 评分输出格式

加 "反向论证" + "⑤⑥ 必填理由" 段:

```markdown
## N167 七维度评分 (commit <hash>)

| 方案 | ① | ② | ③ | ④ | ⑤ | ⑥ | ⑦ | 总分 | 自决? |
|------|---|---|---|---|---|---|---|------|------|
| A    | 3 | 3 | 3 | 3 | 2 | 2 | 3 | 19   | ✅   |
| B    | 1 | 1 | 1 | 2 | 1 | 1 | 1 | 8    | ❌   |

**⑤ 性能资源优化理由**: <一行理由, 不允许默认 2 分>
**⑥ 安全合规加固理由**: <一行理由, 不允许默认 2 分>
**反向论证**:
- **为何不选 B**: <理由 1> + <理由 2>
- **为何不选 C**: <理由 1> + <理由 2>
**硬场景 ③ 业务语义判定**: 这个决策影响数据保留/业务流程吗? N → 可自决; Y → AskUserQuestion
**自决决策**: A (总分 19 ≥ 19, 领先 B 11 分 ≥ 5)
**执行**: A 方案
```

#### 3.3.2 `project_rules.md §2.0.5` 加硬约束

```markdown
**N167 评分硬约束 (spec-49 强化 — 防主观空间凑分)**:
- ✅ **⑤⑥ 维度必填理由**: 不允许默认 2 分, 必填一行 "为何打此分" 理由
- ✅ **反向论证必填**: 每个 non-selected 方案必填 ≥2 条 "为何不选" 具体理由
- ✅ **硬场景 ③ 业务语义判定流程**: "问: 这个决策影响数据保留/业务流程吗? Y → AskUserQuestion"
```

#### 3.3.3 `_refactor-dimensions.md` Y/N 矩阵

加 3 行 Y/N 检查:
- ⑤⑥ 维度是否填理由? Y/N
- 反向论证是否填 ≥2 条理由 per 方案? Y/N
- 硬场景 ③ 是否跑了 "影响数据保留/业务流程?" 判定? Y/N

### 3.4 验收

- spec-49 本身的 N167 评分含反向论证 + ⑤⑥ 理由 + 硬场景 ③ 判定 (本 spec §2 已实践)
- `_refactor-dimensions.md` 新增 3 行 Y/N

## §4 Phase 2: L4 spec 间循环强化 (I2)

### 4.1 改进点

1. **触发词分级**: 强触发 (持续循环) vs 弱触发 (1 spec 后停)
2. **硬终止**: 连续 3 spec 后强制停下报告
3. **L3-1 频率归一**: 循环模式下 "每 3 spec 一次全量扫描"

### 4.2 涉及文件

- `project_rules.md §3.6 + §3.7` (循环模式 + L3 流程)
- `.ai-memory/meta/yn-matrices/_workflow.md §㉝` (N166 Y/N 矩阵)
- `gaf-orchestrator/SKILL.md L3 循环段` (同步)

### 4.3 具体修改

#### 4.3.1 `project_rules.md §3.6` 触发词分级

```markdown
**循环模式触发词分级 (spec-49 强化 — 防误判 + 防失控)**:
- **强触发 (持续循环)**: "循环执行" / "L3 循环" / "按优先级接修" / "任务接着做" (连续多个 spec)
- **弱触发 (单 spec 后停)**: "继续" / "继续做下一个" / "评估一下" / "扫一下" / "看看有啥问题" / "没任务就接着评估" (1 spec 后停下确认)
- **默认 (无触发词)**: spec ✅ → 停下报告 → 等用户指令
```

#### 4.3.2 `project_rules.md §3.7` L3-4 硬终止

```markdown
**L3-4 终止条件 (spec-49 强化 — 防永不终止)**:
- (原) 连续 2 轮无新增 [A] 类 / 所有 [A] 已修 + [B] 已登记 / 上下文预算告警 (N160: ≥ 15 轮) / 用户显式叫停
- **(新增) 硬终止**: 连续 3 个 spec 完成后强制停下报告, 等用户确认继续 (防方向跑偏)
- **(新增) 弱触发模式下**: 1 spec 完成后必须停下 (用户弱触发仅授权 1 个 spec)
```

#### 4.3.3 `project_rules.md §3.7` L3-1 频率归一

```markdown
**L3-1 全量扫描触发条件 (spec-49 归一 — 消除矛盾)**:
- 循环模式下: 每 3 spec 一次全量扫描 (与触发条件 ① 一致)
- 非循环模式: 用户显式要求时跑
- 轻量版 (①+②): 每 spec 跑 (P0/P1 快速扫)
```

### 4.4 验收

- `_workflow.md §㉝` 加 3 行 Y/N: 触发词分级识别? 硬终止执行? L3-1 频率合规?

## §5 Phase 3: L5 subagent 并行强化 (I3)

### 5.1 改进点

1. **隐性冲突 Grep 检测**: subagent 任务描述提到的 "目标文件引用" (e.g., "需在 failure-modes.md 加索引") 需 Grep 检测交叉
2. **质量抽查 1 文件**: 落地检查加 "每个 subagent 至少 Read 1 个修改文件验证内容"
3. **subagent prompt 含规则摘要**: commit 规范 + pre-commit 不能 --no-verify + 文件命名不带版本号

### 5.2 涉及文件

- `project_rules.md §3.6` (N172 + N175)
- `.ai-memory/meta/yn-matrices/_ai-autonomy.md §2 ⑩` (N172 矩阵)

### 5.3 具体修改

#### 5.3.1 `project_rules.md §3.6` N175 落地检查强化

```markdown
**subagent 并行结果落地检查 (N175 — spec-49 强化)**:
- (原) 记录每 subagent 处理的 TD 列表, 核查 len(active_md.updates) == sum(len(s.td_list))
- **(新增) 隐性冲突 Grep**: subagent 任务描述中提到的 "目标文件引用" (如 "需在 failure-modes.md 加索引") 必须 Grep 检测交叉, 重叠则改串行
- **(新增) 质量抽查**: 每个 subagent 至少 Read 1 个修改文件验证内容 (防 "数量一致但实质未修")
- **(新增) subagent prompt 规则摘要**: 启动 subagent 时 prompt 必含 3 条规则:
  1. commit 规范: `<type>(<scope>): <subject>` (§3.4)
  2. pre-commit 失败根因修复, 禁止 --no-verify (§3.3 N150)
  3. 文件命名禁止带版本号 (§2 N140)
```

### 5.4 验收

- `_ai-autonomy.md §2 ⑩` N172 矩阵加 3 行 Y/N

## §6 Phase 4: L3 spec 内偏离阈值规则 (I4)

### 6.1 改进点

- Phase 数 +50% 或 diff +30% 必须更新 spec 文件 + commit message 标注 "deviation: <原因>", 但不停下问

### 6.2 涉及文件

- `project_rules.md §3.6` (spec 内自决) + §4.10 (spec 分阶段)

### 6.3 具体修改

```markdown
**spec 内偏离阈值 (spec-49 新增 — 防 AI 自决扩展范围失控)**:
- ✅ Phase 数 +50% (e.g., 原 4 Phase 实际跑 6+) 或 diff +30% 必须更新 spec 文件 "deviation log" 段
- ✅ commit message 标注 "deviation: <原因>" (e.g., "fix(spec-47): TD-279 path drift (deviation: 3 rounds vs 1 planned, double-prefix bug)")
- ✅ 不停下问 (L3 spec 内自决保留), 但需在 spec 状态表记录偏离
- ❌ 禁止 Phase 数 +100% (e.g., 原 4 跑 8+) 不更新 spec — 必须停下问用户
```

### 6.4 验收

- spec-47 状态表补 "deviation log" 段 (3 轮 vs 1 轮, 双重前缀 bug)

## §7 Phase 5: AI patch 飞轮连续失败通知 (I5)

### 7.1 改进点

- 连续 ≥3 个 patch 失败必须停下报告用户 (不只升级 TD)

### 7.2 涉及文件

- `gaf-orchestrator/SKILL.md §0.5` (AI patch 流程)
- `project_rules.md §3.6` (AI 自决边界)

### 7.3 具体修改

`gaf-orchestrator/SKILL.md §0.5` 加红线:

```markdown
**spec-49 强化红线**:
- ✅ patch 失败 2 次 → mark_failed + 升级 TD (原)
- **(新增) 连续 ≥3 个 patch 失败 → 必须停下报告用户** (防 AI 持续升级 TD 而不通知)
- **(新增) 连续 ≥5 个 patch 成功 → 可继续, 但每 10 个 patch 后停下报告进度** (防上下文耗尽)
```

### 7.4 验收

- spec-49 本身不含 patch 失败场景, 规则更新即可

## §8 Phase 6: L1 红线文件判定标准 + 文件删除归一 (I6 + I7)

### 8.1 改进点

- 加 "git 追踪 + 涉及代码" 需评估, 纯临时文件 (`.trash/` + 自己创建) 直接删

### 8.2 涉及文件

- `project_rules.md §3.5 + §4.1`

### 8.3 具体修改

#### 8.3.1 `project_rules.md §3.5` 文件删除判定

```markdown
**本地文件删除判定标准 (spec-49 新增 — 防 AI 误删重要文件)**:
- ✅ **可直接删 (AI 自决)**: `.trash/` 内文件 + AI 自己创建的临时脚本/调试文件 + `.cache/` 工具缓存
- ⚠️ **需评估后删 (AI 自决 + 风险评估)**: git 追踪的文件 (可恢复) — 列出影响范围 + 确认无引用后删
- ❌ **需用户授权**: 未追踪 + 重要文件 (代码/配置/数据) + 跨工作区/不可逆 (§3.5 原)
- **判定流程**: 
  1. 文件在 `.trash/` 或 `.cache/`? → 直接删
  2. git 追踪? → Grep 引用 + 评估影响 → 删 (可恢复)
  3. 未追踪 + 重要? → 问用户
```

#### 8.3.2 `project_rules.md §4.1` 同步归一

§4.1 已有 "Move-Item 优先 + .trash/ 内可直接 Remove-Item", 与 §3.5 一致, 无需重复修改, 仅加交叉引用.

### 8.4 验收

- §3.5 + §4.1 文件删除判定归一, 无矛盾

## §9 Phase 7: 验证 + 全量回归 + 状态同步

### 9.1 验证

- `doc_health_check.py`: P0=0, P1=0 (维持 spec-48 状态)
- `pytest test_doc_health_check.py`: 50 tests PASS
- `sync_ai_memory.py`: frontmatter 合规
- `sync_skills.py --check`: skill 副本同步
- 全量回归 `pytest scripts/tests/`: 比基线 (316/326) 不退化

### 9.2 evidence

- `.ai-memory/evidence/2026-07-20-spec49-ai-self-decide-hardening/` (problem.md + solution.md + verification.md)

### 9.3 状态同步

- spec-49 状态表 7 Phase ✅
- C-076 追加到 completed-features.md
- P-017 追加到 pending-roadmap.md

## §10 风险

- 低: 纯规则文档变更, 不改代码逻辑
- Phase 1-6 修改 project_rules.md / handbook / skill / yn-matrices, 需跑 sync 脚本验证一致性
- 规则变更后, AI 后续执行可能因新规则 (e.g., 反向论证必填) 略减速, 但长期受益

## §11 一致性检查

- spec-49 涉及 rules + handbook + skill + yn-matrices 4 处, 需跑 4 个 sync 工具:
  - `sync_ai_memory.py` (frontmatter + lessons 计数)
  - `sync_skills.py --check` (skill 副本同步)
  - `check_yn_matrices_index.py` (Y/N 矩阵索引)
  - `check_path_consistency.py` (路径漂移)

## §12 Open Questions

- Q1: 触发词分级 "强/弱" 是否覆盖所有实际场景? — 用户使用中观察, 不够再加
- Q2: 硬终止 "连续 3 spec" 是否太严? — 用户可说 "继续" 快速恢复, 不阻塞
- Q3: subagent prompt 规则摘要 3 条是否够? — 后续按需扩展, 不一次性堆
