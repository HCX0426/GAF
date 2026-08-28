# spec-2026-08-15-governance-redundancy-consolidation

> **日期**: 2026-08-15
> **类型**: refactor (治理体系冗余 + 漂移收敛)
> **状态**: ✅ 已归档（2026-08-16 归档至 `docs/specs/archived/2026-08/`，含 followup 补丁 - + 历史数据清理 -）
> **任务规模**: 大修改 (跨 rules/skills/lessons ~15 文件)
> **触发**: 用户提问"目前gaf的工作流，规则文档，思维链，部分有冗余吗，案例是不是冗余" → 4 维度扫描 → 用户选择"开治理 spec 全部处理"

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit hash | 验收 evidence |
|------|------|---------|-------------|---------------|
| Phase 1: 规则漂移对齐 (3 处) | ✅ | 2026-08-15 | - | D1/D2/D3 全部对齐，含 task-execution 第三处 `-F` 残留 |
| Phase 2: 整段冗余收敛 (5 处) | ✅ | 2026-08-15 | - | R1 N199 删重述留指针; R2 N177 精简重复 MemoryError 细节; R3 七维度阈值 4 处收敛到 2 处权威; R4 gaf_init 经查仅 2 处职责性引用无冗余; R5 UTF-8 两处各属职责保留 |
| Phase 3: lesson 家族合并 (4 组) | ✅ | 2026-08-15 | - | L1 N182-N185 合并为家族文件 (N183/184/185 移 .trash/lesson-family-merge/); L2 N172-N175 合并; L3 N171-N173 合并; L4 N165 标 superseded_by N190 + solution 段修正; L5 N191 压缩 874→~330 行 (§10.8 标 superseded, 检查清单原样保留) |
| Phase 4: 验证 + 反思 + 提交 | ✅ | 2026-08-16 | - | check_lessons_updated 77 lessons ✅; sync_skills 4+1 ✅; check_yn_matrices ✅; path_consistency 0 error ✅; pre-commit 全链 8/8 passed (governance-batch 12/13 + 5 GAF hooks); doc-code-sync R4 用 GAF_SKIP_DOC_SYNC=1 (5 deleted lesson refs 已验证无 live 残留) |

## N173 用时字段

- start_ts: 2026-08-15T23:15:00+08:00
- end_ts: 2026-08-16T00:30:00+08:00
- duration_min: 75
- within_baseline: false (大修改基线 60 min，超 15 min)
- root_cause_if_over: ① 4 维度扫描含 2 subagent 并行研究 (~20 min) 计入本 spec 大修改范畴; ② pre-commit 阶段暴露 2 个 B2 门槛 (evidence 三件套 + spec-context 承载体 + doc-sync R4 skip 机制) 需额外处置 (~15 min)；③ N191 压缩需在保留 L0 引用编号 (§10.7-10.12) 前提下重写 (~10 min)

---

## 1. 背景与触发

用户对 GAF 治理体系（工作流 / 规则文档 / 思维链 / 案例库）提出冗余性质疑。经 4 维度扫描：

1. **工作流（决策树）**: orchestrator 决策树 4 分支与 task-execution 双流程定义并存，步骤号冲突（orchestrator `step_5_implement` vs task-execution `step_5_commit_evidence`）
2. **规则文档**: 3 处事实漂移（`-F` L0/L2 矛盾、反思分级 3 版本、沉淀判定 1/2 问）+ 5 处整段冗余
3. **思维链（反思清单）**: 反思分级标准散布 10+ 文件，reflect-and-evolve §2 是权威源但其他文件各自维护
4. **案例库（lessons）**: 行级几乎零重复（Jaccard < 0.16），但 4 组家族合并候选 + 1 个内容反转退役文件 + 1 个超大内部过期

> **扫描脚本**: `C:\Users\hcx\AppData\Local\Temp\opencode\dup_scan.py` / `lesson_dup.py`（临时，不入库）

## 2. N151 架构评估（5 步）

### step_1 架构盘点

- **治理体系 5 层**: L0 env-hardrules (硬约束) → L1 failure-modes (N## 索引) → L2 handbook (必读) → L3 lessons/skills (按需) → yn-matrices (检查矩阵)
- **权威源模式 (v9.1 归一化)**: 每主题应有单一权威源，其他文件只放 1 行硬约束 + 指针
- **当前健康**: 行级去重已成功（无 ≥8 行相同块），v9.1 瘦身设计有效

### step_2 识别反模式

| # | 反模式 | 位置 | 影响 |
|---|--------|------|------|
| R1 | 同一规则多版本并存（漂移） | `-F` 提交、反思分级、沉淀判定 | AI 加载不同文件得到不同义务 |
| R2 | 整段重述不收敛权威源 | N199、N177、七维度阈值、gaf_init、heredoc | 改一处忘另一处 → 二次漂移 |
| R3 | lesson 同事件多文件 | N182-185 / N172+175 / N171+173 | 同事件检索出 4 个文件 |
| R4 | 退役文件内容反转 | N165（建议 `-F`，N190 已禁用） | AI 误读旧方案 |
| R5 | 超大文件内部过期 | N191（874 行，§10.8/10.9 被覆盖但保留） | 检索噪声 + 维护成本 |
| R6 | 索引含退役 N## | lesson-router §1 | 引用失效路径 |

### step_3 A/B/C 备选方案

| 方案 | 描述 | ① 架构 | ② 归一 | ③ 兼容 | ④ 完善 | ⑤ 性能 | ⑥ 安全 | ⑦ 维护 | 总分 | 自决? |
|------|------|-------|-------|-------|-------|-------|-------|-------|------|------|
| A: 权威源收敛 + 家族合并 | 漂移以 L0/权威源为准对齐；冗余删重述留指针；lesson 家族合并 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | **20** | ✅ |
| B: 只修漂移不删冗余 | 仅对齐 3 处漂移，其余登记 TD | 2 | 2 | 3 | 2 | 2 | 2 | 2 | 15 | ❌ |
| C: 大重构（重写 handbook 降指针） | handbook 降为纯红线，所有操作级内容外迁 | 3 | 3 | 2 | 2 | 3 | 2 | 2 | 17 | ❌ |

### step_4 拒绝反模式

- **拒绝"最小修补"（B）**: 用户已明确"全部处理"，且 R2 冗余不清理会导致二次漂移（N177 已在两处维护）
- **拒绝"大重构"（C）**: handbook 339 行已瘦身过，降为纯红线损失 L2 可读性；AI 需要操作级上下文
- **拒绝"保留双套"**: 双流程定义（R1 工作流）必须收敛到决策树单一权威源

### step_5 AI 自决

- 方案 A 总分 20 ≥ 19，领先 B 5 分 ≥ 5 → **AI 自决执行方案 A**
- 硬场景检查: ① FK 绊住? N ② schema 分裂? N ③ 业务语义? N ④ 不可逆? N → 全部通过
- **注意**: 本任务已通过 AskUserQuestion 获得用户明确选择"开治理 spec 全部处理"，双重确认

## 3. 变更清单（Phase 划分）

### Phase 1: 规则漂移对齐（3 处事实漂移）

| # | 漂移 | 权威源 | 修改文件 | 动作 |
|---|------|--------|---------|------|
| D1 | `-F` 提交 L0 vs L2 矛盾 | env-hardrules N190（禁用 `-F`） | `ai-operating-handbook.md` L247-248 命令使用段 | 删 `-F` 等价句 + 删 N170 引用，改为"以 env-hardrules N190 为准：禁用 `-F`，多行用多个 `-m` flag" |
| D2 | 反思分级 3 版本（中=1问/5项/4问） | reflect-and-evolve §2（中=5 项） | `project_rules.md` §4.6 L524-529 + handbook L263-264 | project_rules 对齐为"中=跑 §2 5 项"，handbook 反思纪律改为指针 |
| D3 | 沉淀判定 1 问 vs 2 问 | project_rules §3.8（1 问） | `ai-operating-handbook.md` L149 | 改为"判定标准（1 问）"，规模分级归 §6.2 |

### Phase 2: 整段冗余收敛（5 处）

| # | 冗余 | 保留处（权威） | 删除处 | 动作 |
|---|------|--------------|--------|------|
| R1 | N199 环境归一化重述 7 行 | env-hardrules §环境归一化 | `project_rules.md` §1.3 L123 | 删重述，留 1 行指针 |
| R2 | N177 测试策略表全表 | tech-stack §9.2 | `project_rules.md` §4.9 | 删全表，留 1 行指针（注：grep 未在 §4.9 找到表，实际可能已在别处，需确认） |
| R3 | 七维度阈值复读 5 处 | reflect-and-evolve §7.3 + project_rules §2.0.5 | orchestrator L254 + handbook L134 | 改为"评分模板见 reflect §7" |
| R4 | gaf_init 步骤 3 处 | tech-stack §9.5 | handbook L27-32 + orchestrator L23-28 | 各留 1 行"跑 gaf_init.sh" |
| R5 | UTF-8 校验注释行级重复 | env-hardrules L75-77 | tech-stack L338-340 | 同步保留（这是刚加的，两处都需）→ 改为 1 行引用 |

### Phase 3: lesson 家族合并（4 组）

| # | 文件 | 动作 |
|---|------|------|
| L1 | N182 + N183 + N184 + N185（4 文件 1 事件） | 合并为 `N182-n185-ocr-three-dimensional-investigation.md`，N182 保留主条目，其余 3 文件正文并入 + 删除，failure-modes.md 索引行更新 |
| L2 | N172 + N175（subagent 家族） | 合并为 `N172-n175-subagent-parallel-landing.md`，N175 正文并入 |
| L3 | N171 + N173（时间测量家族） | 合并为 `N171-n173-time-measurement.md` |
| L4 | N165 内容反转 | 保留文件，frontmatter 标 `superseded_by: N190` + 修正 solution 段指向 N190 |

**注意**: N191 内部压缩（§10.8/10.9 标 superseded）归入 Phase 3 子项 L5（874 行压缩 ~250 行）

### Phase 4: 验证 + 反思 + 提交

- 跑 `check_lessons_updated.py`（lesson 合并后 N## 索引校验）
- 跑 `sync_skills.py --check`（skill 副本一致性）
- 跑相关 pytest（lesson-router 相关测试如有）
- pre-commit 全链 + commit
- N167 反思矩阵

## 4. 验收标准

1. **漂移清零**: grep `-F.*等价` / `1 问.*2 问` / `中=.*问` 三主题无跨文件矛盾
2. **冗余收敛**: 5 处冗余主题各只剩单一权威源 + 指针
3. **家族合并**: N182-185 / N172+175 / N171+173 各 1 文件；N165 标 superseded；N191 压缩完成
4. **索引一致**: failure-modes.md / lessons/README.md / check_lessons_updated.py 三者一致
5. **hooks 通过**: pre-commit 全链通过，无新 drift 引入

## 5. 已知限制

- 工作流双流程定义（决策树 vs task-execution）属于结构性边界，本次只消除步骤号冲突，不合并决策树（决策树是单一权威源，task-execution 是操作细节）
- N169+N174 TD 登记家族合并原计划登记 TD，经架构调查发现 **N169 已在 spec-33 Phase 4 退役合并进 N166**（failure-modes §Retired + yn-matrices ㊱ 已标），合并前提不成立 → 本 spec followup 改为 N165 模式：N169 lesson 补退役标注 (superseded_by N166) + README 状态同步，N174 保持独立活跃仅修路径，无需登记 TD

## 6. Deviation Log

- **Phase 3 家族文件名**: spec 计划合并为新文件名（`N182-n185-ocr-three-dimensional-investigation.md` / `N172-n175-subagent-parallel-landing.md` / `N171-n173-time-measurement.md`），实际保留母文件名（N182 / N172 / N171）作为家族载体。验收标准仅要求"各 1 文件"，N## 是编号非文件路径，failure-modes/handbook 引用均按 N## 解析 → 保留母名零契约破坏，更低迁移成本
- **N169+N174 家族合并取消 (followup 架构调查)**: 原 spec 已知限制段计划"N169+N174 家族合并降级登记 TD"，实际调查发现 N169 已在 spec-33 Phase 4 退役合并进 N166（failure-modes §Retired + yn-matrices ㊱），合并前提不成立 → 改为 N165 模式：N169 lesson 补退役标注 (superseded_by N166) + README 状态同步，N174 保持独立活跃仅修路径，无需登记 TD
- **N191 压缩目标**: spec 计划 ~250 行，实际 ~330 行。原因：§10.9 G1-G7 必须保留（L0 env-hardrules N191 段引用 "§10.9 G1-G7"），§10.7-§10.12 编号必须保留（L0 引用区间），压缩空间仅限 §10.8 superseded 明细 + §10.13-§10.15 结论
- **pre-commit 处置**: B2 evidence TTL 过期（122 min > 30 min）需 `--acknowledge` 重生成；evidence-completeness 需填三件套；spec-context carrier 需新建承载体；doc-code-sync R4 需 `GAF_SKIP_DOC_SYNC=1`（`-m` 不填充 COMMIT_EDITMSG，skip token 需 env var）
- **followup 补丁 — tech-debt 路径漂移修复 (2026-08-16)**: 主 spec commit - 后遗留路径漂移（`docs/tech-debt/` → `docs/archive/`，2026-08-09 迁移后未全链路清理）。本补丁修复: ① N169 退役标注 (N165 模式) + README 同步; ② 5 个 tech-debt 脚本路径迁移 (sync_tech_debt_counts / governance_dashboard / monthly_health_check / sync_tech_debt_archive 休眠 / split_active_tech_debts 休眠); ③ fixed 计数语义修正 (索引表行数 123，非旧 fixed.md 快照 243); ④ rules/handbook/hook/测试 fixtures 路径同步; ⑤ d2_bloat 阈值迁移到 fixed-tech-debt-details.md (15000)。验证: 4 测试文件 52 passed + doc-path-drift 0 violation + sync --check consistent

## 7. N167 反思矩阵（大修改 — commit 后）

| # | 维度 | 结果 | 说明 |
|---|------|------|------|
| 1 | 架构长远性 | ✅ | 权威源收敛延续 v9.1 归一化，未来加规则只改 1 处 |
| 2 | 全局归一化 | ✅ | 反思分级 10+ 文件 → reflect §2 权威源 + 指针；`-F` 禁用全仓对齐 N190 |
| 3 | 新旧兼容 | ✅ | N## 编号全部保留，仅 lesson 载体合并，无外部契约破坏；5 deleted lessons 引用已验证无 live 残留 |
| 4 | 现有业务完善 | ✅ | 修复 3 处事实漂移 + 5 处冗余，无功能回归 |
| 5 | 性能资源优化 | ✅ | 文件 77→73 核心，N191 874→330 行，lessons 索引读取更快 |
| 6 | 安全合规加固 | ✅ | N165 superseded_by N190（旧方案建议 `-F` 已禁用），消除误读风险 |
| 7 | 长期维护成本 | ✅ | 家族文件单点维护，索引一致（77 lessons / lessons_count=67）|
| L1 | 教训分发 | ✅ | 新教训: "B2 大修改 3 门槛预处置"（evidence 三件套 + spec-context + B2 --acknowledge 需在 commit 前统一准备，而非 hook 报错后逐个救火）；"GAF_SKIP_DOC_SYNC=1 替代 -m skip token"（`-m` 不填充 COMMIT_EDITMSG）— 已检查 4 项反模式: N178-A1 反向论证循环 / A2 评分合理化 / A3 过度治理 / A4 范围扩张 均不适用（方案经用户双重确认，偏差均已记录 deviation log）|