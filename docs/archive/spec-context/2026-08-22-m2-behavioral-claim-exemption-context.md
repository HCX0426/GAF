# Spec Context: 2026-08-22-m2-behavioral-claim-exemption → v9.2 元规则出清与瘦身

> B2 大修改承载体 (TD-342)。本 spec-context 覆盖同对话内合并推进的三个子 spec（Spec A 出清机制 / Spec B L0 瘦身 / Spec C 张力点消除），按 N176 合并为 1 次 commit。

## 1. 用户决策原文

1. 用户问"我目前的工作流还有什么问题吗"（指 GAF 项目 AI 规则/工作流）→ AI 给出 5 项问题诊断 + 量化评估。
2. 用户："仔细评估后出一个方案先" → AI 产出三 spec 方案（A/B/C，预估 <1500 行 diff）。
3. 用户："**按顺序来吧**" —— 批准 A→B→C 顺序执行，授权按 §3.4 提交纪律自决 commit。

## 2. N151 五步评估

1. **架构盘点**: 元规则体系 5 层（rules/handbook/failure-modes/yn-matrices/lessons）+ 16 hooks + 40 scripts；Active N## 64 条中 77% >30 天未触发；L0 注入 38.5KB。
2. **识别反模式**: ① 只进不出（沉淀纪律强制写入、退役仅软性月度评估）② 单一权威源实为多处复制（N192 单文件出现 8 次）③ 判级靠 AI 自评无后验 ④ 文档词汇与 commit 声称耦合（M2 误判根因）。
3. **A/B/C 备选**: A=仅月度人工清理（维持现状+）；B=全量重构规则体系（推倒重来）；C=机械出清机制+注入砍半+张力点定点修复（选中）。C 的理由：治本（出清机械化）、低风险（lessons 可恢复）、增量收敛（棘轮）。
4. **拒绝反模式**: 拒绝 B 双套并存风险；拒绝"最小化修补"（只清不建机制）；KEEP 决策：保留全部现有 hooks，只增不改语义。
5. **AI 自决边界**: 方案经用户批准后三 spec 内完全自治；判据参数（60 天/≤3 次/上限 35）由数据支撑（49/64 条 >30d 未触发），用户可后续调整常量。

## 3. N167 七维度评分

| 维度 | 方案 C 得分 | 说明 |
|------|:---:|------|
| 1 架构长远性 | 4 | 出清棘轮使体系可持续收敛，不再单调膨胀 |
| 2 全局归一化 | 4 | 出清单一权威源收拢到 promote_lessons.py；判级后验收拢到新 hook |
| 3 性能 | 3 | L0 -55% 直接降低每对话 token 成本 |
| 4 可测试性 | 4 | 判据全部脚本化（--check-cap/--enforce-cap 可 dry-run）|
| 5 兼容性 | 4 | lessons 不删、编号不复用、hooks 全保留，回滚成本≈0 |
| 6 实现成本 | 3 | ~940 行 diff，单对话完成 |
| 7 长期维护成本 | 5 | 月度人工评估退役 → 机械强制，维护面净减 |
| **总分** | **27** | ≥19 且无短板维度 |

## 4. 关键实施决策

- **棘轮语义**（偏离原方案说明）: 原计划一次性出清至 ≤35 条；实测发现 last_triggered 数据太年轻（多数集中 6-7 月），一次只能清 9 条。改为：有可清候选未清 → check-cap 阻塞 commit；无可候选放行。随时间自动收敛到 35。
- **L0 保护判据**: 被 `.skills/rules/*.md` 引用的 N## 永不出清——保守优先，误伤关键约束的代价高于出清不足；Spec B 瘦身后引用减少会自然解锁更多候选（已验证：瘦身立即解锁 N122）。
- **M2 证据判定解耦**（Spec C-2）: claimed N## 若字面出现在 diff 新增行或路径中 → 视为内容关联（positive），不再依赖 lesson diff_keywords 回填；无任何 diff 痕迹的裸声称照常核验。
- **判级后验 warn-only**（Spec C-3）: 中修改反思证据无法机械核验，诚实降级为"输出级别清单 + 无测试文件提醒"，不阻塞；大修改强制仍由既有 B2 hook 承担。
- 过期测试修复: test_n181_retirement_eval 断言具体 N## 在 Active，与动态出清矛盾 → 改为非空断言 + Retired 排除断言（编号永不复用故稳定）。

## N173 用时字段

- start_ts: 2026-08-22T12:30:00+08:00
- end_ts: 2026-08-22T16:10:00+08:00
- duration_min: 215
- within_baseline: false
- root_cause_if_over: 三 spec 合批超出单基线适用范围；处理存量阻塞（REVIEW_TRIGGERED 复盘闭环、B2 evidence/spec-context 补写）；project_rules 字节预算多轮迭代裁剪

## 6. 验证 evidence

- governance batch 17/17 passed
- pytest scripts/tests/ 588 passed, 2 skipped
- Active N##: 66 → 57（首轮棘轮出清 9 条）
- L0 注入: env-hardrules 2808B (≤4KB) + project_rules 14330B (≤14KB)
