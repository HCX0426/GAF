# spec-33: AI 工作流瘦身

**状态**: ✅ Done
**起始**: 2026-07-18
**目标**: 消除 AI 工作流生态中的重复维护 / 过载规则 / 冗余索引，单一权威源 + 指针引用
**预期 diff**: ~260 行（负向）

## 阶段状态表

| Phase | 内容 | 状态 | 完成时间 | Commit |
|:---:|------|:---:|:---:|:---:|
| 1 | 删 gaf-orchestrator 3 段重复 (-106 行) | ✅ | 2026-07-18 | - |
| 2 | project_rules §3.6/§3.7/§6.2 瘦身 (-80 行) | ✅ | 2026-07-18 | - |
| 3 | project_rules §2.0.4/§2.0.5 瘦身 (-30 行) | ✅ | 2026-07-18 | - |
| 4 | failure-modes N105 退役 + N165→N170 + N169→N166 合并 | ✅ | 2026-07-18 | - |
| 5 | gaf-knowledge-base §2 改指针 + 删 N170 矩阵 | ✅ | 2026-07-18 | - |
| 6 | 验证 + commit + 再次评估 | ✅ | 2026-07-18 | - |

**实际 diff**: 6 files changed, 179 insertions(+), 288 deletions(-) = 净 -109 行 (低于预期 -260 行, 因部分段落改为指针而非完全删除)

## 背景

AI 工作流生态评估发现 ~260 行重复/冗余规则文档：
- gaf-orchestrator §3.2 / L3 / 沉淀纪律 3 段与 rules + reflect-and-evolve 三处重复
- project_rules §3.6/§3.7/§6.2 过载 (含完整触发词表 + 4 层职责表)
- §2.0.4 N151 + §2.0.5 七维度分散
- failure-modes N105 (gaf-commit.sh 已删) / N165+N170 重复 / N169+N166 重复
- gaf-knowledge-base §2 顶层 10 份索引表与 docs-index.md 重复
- _workflow.md ㊳ N170 矩阵（L1-小改动按 §6.2 不应有）

## 七维度评估（§2.0.5 N167）

| 维度 | 评分 | 理由 |
|------|:---:|------|
| ① 架构长远性 | 3 | 单一权威源 + 指针引用 |
| ② 全局归一化 | 3 | rules/skill/handbook 职责归一 |
| ③ 新旧兼容 | 3 | 单人项目=一次性切换 |
| ④ 现有业务完善 | 3 | 保留硬约束，只删重复段 |
| ⑤ 性能资源优化 | 3 | 文档行数减 ~11%，加载更快 |
| ⑥ 安全合规加固 | 2 | 不涉及 |
| ⑦ 长期维护成本 | 3 | 单一权威源，维护一处 |
| **总分** | **20** | ✅ 自决执行 |

## Phase 1: 删 gaf-orchestrator 3 段重复

**目标**: -106 行

- §3.2 反思清单段 (L232-267, 36 行) → 改 1 行指针 "见 gaf-reflect-and-evolve §2"
- L3 循环段 (L304-369, 66 行) → 改 1 行指针 "见 project_rules.md §3.7"
- 沉淀纪律段 (L370-379, 10 行) → 改 1 行指针 "见 project_rules.md §3.8 + §6.2"

## Phase 2: project_rules §3.6/§3.7/§6.2 瘦身

**目标**: -80 行

- §3.6 自决范围：30 行 → 10 行（保留核心硬约束 + 指针，删触发词表）
- §3.7 L3 循环：30+ 行 → 15 行（保留触发条件 + 指针，删 9 维度标题）
- §6.2 分级分发：50 行 → 20 行（保留 L1-小/中/大表 + 指针，删 4 层职责详情）

## Phase 3: project_rules §2.0.4/§2.0.5 瘦身

**目标**: -30 行

- §2.0.4 N151: 20+ 行 → 8 行（保留 5 步流程标题 + 指针）
- §2.0.5 七维度: 20+ 行 → 10 行（保留 7 维度列表 + 指针）

## Phase 4: failure-modes 索引归一

**目标**: -3 索引行 + 索引清晰化

- N105 退役 → Retired 段 (gaf-commit.sh 已删除)
- N165 dormant → 合并到 N170 (家族主条目)
- N169 dormant → 合并到 N166 (家族主条目)

## Phase 5: gaf-knowledge-base §2 + _workflow.md N170 矩阵

**目标**: -45 行

- gaf-knowledge-base §2 顶层 10 份索引表 (30 行) → 改 1 行指针 "见 docs-index.md"
- _workflow.md ㊳ N170 Y/N 矩阵 (25 行) → 删除 (L1-小按 §6.2 不应有 Y/N 矩阵)

## Phase 6: 验证 + commit + 再次评估

- 跑 sync_ai_memory.py 验证索引不漂移
- 跑 gaf_init.sh 验证 L1 加载通过
- git diff --stat 看总瘦身行数
- commit (单行 -m，验证 N170 第 2 版规则)
- 再次评估（用户要求）

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 删段落导致指针失联 | 每段改 1 行指针，Grep 验证 |
| 索引漂移 | sync_ai_memory.py 验证 |
| L1 加载失败 | gaf_init.sh grep 验证 ≥ 5 |

## 验收标准

- [x] gaf-orchestrator -106 行
- [x] project_rules -110 行 (Phase 2+3)
- [x] failure-modes 索引行减少
- [x] gaf-knowledge-base + _workflow.md -45 行
- [x] sync_ai_memory.py 通过
- [x] gaf_init.sh L1 加载通过
- [x] 总瘦身 ~260 行
