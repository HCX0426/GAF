---
name: gaf-reflect-and-evolve
description: |
  反思 + 演化 skill。AI 接到 bug_fix / refactor 任务时加载。
  commit 后必跑反思。决策树见 gaf-orchestrator（v9 单一权威源）。
version: 9.0
updated: 2026-08-22
load_when:
  - task_type == bug_fix
  - task_type == refactor
  - 任何 commit 完成后必跑反思
  - pre-commit hook 失败时（按 N91 映射表修复）
---

# gaf-reflect-and-evolve — 反思 + 演化（v9.0 工作流简化版）

> **v9.0 变更**（gaf-workflow-v9-slim 闭环）：
> - 决策树副本已删除，见 `gaf-orchestrator/SKILL.md ## Decision Tree`（单一权威源）
> - §3-§5 调试具体内容已移出（见 failure-modes.md + yn-matrices/ + lessons/）
> - 反思清单按变更规模分级（见 §2 + project_rules.md §4.6）

---

## 1. 加载时机（v8.4 N95 强化）

| 触发场景 | 必跑 | 关联 N## |
|----------|------|----------|
| `task_type == bug_fix` | 反思 + 写 lesson + 3 步 evidence | N97 |
| `task_type == refactor` | 反思 + L1 分发 | N95 |
| 任何 commit 完成后 | 循环迭代反思（按规模分级） | N113 |
| pre-commit hook 失败 | 查 N91 映射表 + 跑修复命令 | N91 |
| 失败模式 8 场景外 | 主动追加 failure-modes.md entry | N88 |
| AI 推完停下问"是否开始" | 立即推进下一段（N115 入口自决） | N115 |

**前置必跑**：`bash GAF/scripts/gaf_init.sh`（含 L1 硬加载 failure-modes.md + session active）。

---

## 2. 反思矩阵（v9.0 按变更规模分级）

> **命名归一**: 本节是"反思清单"（改后检查，24 项 = ①-⑤ 前置 5 项 + ⑥-㉔ Y/N 检查表 19 项），与 project_rules §3.7 L3-1 "扫描清单"（找问题，9 维度）+ §2.0.5 "修改清单"（改前评估，7 维度）三层互补，不混淆
> **v9.0 关键变更**：反思清单按变更规模分级，小修改不跑全套。
> 触发：项目规则 §4.6 循环迭代反思（分级触发）。

### 分级触发标准

| 规模 | 判定标准 | 必跑项 |
|------|----------|--------|
| **小修改** | < 50 行 diff / 文档改动 / 单文件 fix | ① 4 问 + ④ 状态标记（2 项） |
| **中修改** | 50-500 行 / 新功能 / 跨文件 refactor | ①②③④⑤（5 项）+ L0 lesson（如适用） |
| **大修改** | > 500 行 / 架构变更 / 跨模块 | ①-㉔ 全套 + L1 分发 |

### P4 治本机制：先跑脚本选 Y/N

> **治本理由**: 24 项 Y/N 让 AI 自决跑哪些 → 走形式 / 漏检查。脚本按 git diff 自动选 3-6 项。

**强制流程**（中/大修改必跑，小修改可跳过）：
1. 跑 `python GAF/scripts/select_reflection_checks.py --diff HEAD~1`
2. 按脚本输出的 N## 清单 `Read .ai-memory/meta/yn-matrices/_<topic>.md`
3. 跑对应 Y/N 检查 → 填反思矩阵

**关键词映射**（脚本内置，详见 `scripts/select_reflection_checks.py`）：
- backend models/serializers → N112 + N128（`_cross-layer-sync.md` + `_honest-status.md`）
- scripts/sync_*.py → N116 + N117（`_misc.md` §concurrency）
- pytest/mypy/ruff → N111 + N119（`_ai-autonomy.md`）
- git add/commit → N150 + N153（`_workflow-commit.md` §7 hook-failure）
- spec 文件 → N164 + N166（`_workflow-commit.md`）
- 默认兜底：3 项核心（N97/N109/N128 — v9.3 从 6 项瘦身）

### ① 4 问反思（项目规则 §4.6 Round 1 必填）
- 本轮要做什么? 范围边界是什么?
- 现有代码中哪些可以直接复用? 哪些需要修改?
- 有什么潜在风险或依赖?
- 本轮的验收标准是什么 (P0 全部通过才标记 ✅)?

### ② A/B/C 分类（中修改以上必填）
- [A] 可立即修复 → 立即修复, 不推迟
- [B] 需要后续 Phase 依赖 → 写入对应 Phase 条目
- [C] 确认无法解决 (技术限制/外部依赖) → 写入已知问题清单并标注原因

### ③ Round 循环检查（中修改以上必填）
- Round 1: 反思 → 发现问题 → 分类 → 解决可立即修复的 → 记录不可解决的
- Round 2: 基于 Round 1 的修复结果, 再次反思 → 发现新问题/遗漏 → 解决
- Round N: 继续直到满足终止条件（无新问题 / 全部 B/C 类 / 连续 2 轮无新增 A 类）

### ④ 状态标记同步（N101 必填）
- 本轮新增功能状态标记是否已更新? Y/N
- 三态定义: ✅ 可用 (浏览器验证过) / 🔧 代码存在 (不可用) / ❌ 未实现
- 跑 `git status` + `git diff --stat` 看本轮新增文件, 确认对应文档已更新

### ⑤ evidence 必须 commit（N97 必填）
- 本轮 evidence 是否已 commit? Y/N
- 跑 `git log --diff-filter=A -- .ai-memory/evidence/active/<date>-<task>/` 验证
- 未 commit 的 evidence = 飞轮读侧断裂, 必须立即 add + commit

### ⑥-㉔ Y/N 检查矩阵（大修改必跑，已集中化）

> **来源**: N132 文档治理 — Y/N 矩阵集中到 `yn-matrices/` (7 个 topic sub-file; 索引在 `yn-matrices.md`)
> **P4 治本机制**: Y/N 项由 `select_reflection_checks.py` 按 git diff 自动选 3-6 项, 不再靠 AI 自决。详见上方"P4 治本机制"段。

**加载流程**:
1. 跑 `python GAF/scripts/select_reflection_checks.py --diff HEAD~1`
2. 按输出清单 `Read .ai-memory/meta/yn-matrices/_<topic>.md`
3. 跑 Y/N 检查 → 填反思矩阵

> **② 归一化**: 原 19 行 N## 矩阵表 (⑥-㉔) 已删除 — 内容与 `yn-matrices.md` 索引 + gaf-orchestrator SKILL.md 重复维护, 且已漂移 (⑮ P-020 vs N121)。单一权威源在 `yn-matrices.md` 索引 + `yn-matrices/_<topic>.md` sub-file。

---

## 3. 失败模式主动追加（O2 / N88）

> **v9.0 边界**：本节只保留触发条件，详细流程见 `.ai-memory/meta/failure-modes.md`
> **沉淀纪律单一权威源**: `gaf-lesson-router/SKILL.md §3` (L1 子分级分发流程); 本节只定义触发条件

**触发**：本次失败原因**不在** failure-modes.md 索引的预定义场景中。

**流程**：
1. 写新 entry 到 `failure-modes.md`（索引格式：N## + 1 行硬约束 + lesson 链接）
2. 写详细 lesson 到 `.ai-memory/lessons/<date>-n##-<name>.md`
3. 跑 `python GAF/scripts/bootstrap/sync_ai_memory.py --query` 验证可命中
4. **L0/L1 分发**: 走 `gaf-lesson-router/SKILL.md §3` 单一权威源 (L1-小/中/大 子分级判定, 不在本节重复定义)

---

## 4. Hook ID 失败映射表（N91）

> **v9.0 边界**：本节只保留核心流程，详细映射表见 `.ai-memory/meta/yn-matrices/_workflow-commit.md` §7 hook-failure

**核心流程**:
1. 看 pre-commit 输出找 `❌` 行（按 hook ID 分段）
2. 查 N91 映射表: `grep "<hook_id>" .ai-memory/meta/yn-matrices/_workflow-commit.md`
3. 跑对应修复命令后重试
4. 修复后 `git log --oneline -1` 验证
5. 仍失败 → 升级 N## (写新 failure-mode)

---

## 5. N105 commit 透传 bug

> **v9.0 边界**：本节只保留核心流程，详细内容见 `.ai-memory/lessons/2026-06-15-n105-commit-bypass-rollback.md`
> **N150 约束**: `--no-verify` **仅限**本节 N105 gaf-commit.sh 透传 bug 场景。其他 pre-commit 失败（hook 找不到 / validator 失败 / 数据漂移 / exit 9009 等）**禁止**用 `--no-verify` 绕过，必须根因修复。详见 `project_rules §3.3`。

**核心流程**:
1. 绕过 gaf-commit.sh 透传 bug: 直接 `git commit --no-verify` 不用 wrapper
2. 重新生成被回滚的 auto-maintained 文件: 跑 `python GAF/scripts/bootstrap/sync_docs_index.py`
3. 重 add + 重 commit: `git add <file>; git commit --no-verify -m "..."`

---

## 6. 与其他 skill 的边界

### 6.1 gaf-* skill 内部边界

- **`gaf-orchestrator`**：本 skill 是它的子 skill（task_type = bug_fix / refactor）；决策树权威源在 orchestrator
- **`gaf-task-execution`**：写代码由它主导；本 skill 在 commit 后主导反思
- **`gaf-knowledge-base`**：本 skill 在反思时调 L3 加载 lessons/ 找相关教训

### 6.2 与 superpowers `systematic-debugging` 的边界（TD-029 闭环）

> **来源**: TD-029 — gaf-reflect-and-evolve 与 systematic-debugging 内容重叠（反思 vs 调试边界模糊）
> **核心原则**: 反思流程归 GAF, 调试方法论归 superpowers; 两者按时间轴前后衔接, 不重叠

**职责划分**:

| 维度 | `gaf-reflect-and-evolve` (GAF) | `systematic-debugging` (superpowers) |
|------|-------------------------------|---------------------------------------|
| 触发时机 | commit 完成后 / task_type=bug_fix,refactor | bug 发生时 / 修复前 |
| 核心问题 | "这次学到了什么? 如何防止复发?" | "根本原因是什么? 如何修复?" |
| 输入 | 已完成的代码变更 + commit hash | 错误信息 / 失败测试 / 异常行为 |
| 输出 | lessons/ 教训文件 + yn-matrices 检查 + A/B/C 分类 | 修复代码 + 失败测试用例 |
| 时间轴 | 修复**之后** | 修复**之前** |

**协作流程** (bug_fix 任务典型链路):

```
1. bug 发生 → gaf-orchestrator 加载 gaf-task-execution + systematic-debugging
2. systematic-debugging 主导根因调查 (4 阶段: 根因 → 模式 → 假设 → 实施)
3. 修复完成 → commit
4. commit 后 → gaf-reflect-and-evolve 主导反思 (4 问 + A/B/C + L0/L1 分发)
5. 反思产出新 lesson → 写入 lessons/ + (如适用) 升级 failure-modes.md
```

**硬约束**:
- ✅ 本 skill **不**重复 systematic-debugging 的根因调查方法论 (4 阶段 / 红线 / 借口表)
- ✅ 本 skill **不**写"如何调试"内容, 只写"调试完成后如何反思"
- ✅ systematic-debugging 修复失败时, 本 skill 不介入 (由 systematic-debugging §第四阶段第 5 步 "质疑架构" 主导)
- ✅ 反思时如发现"根因调查不充分", 调用 Skill(name='systematic-debugging') (方法论参考) 让 AI 回到调试阶段
- ❌ 禁止在本 skill 中写"如何阅读错误信息 / 如何稳定复现 / 如何收集证据" 等调试方法论内容
- ❌ 禁止在 systematic-debugging 中写 "L0/L1 分发 / yn-matrices / failure-modes" 等 GAF 项目特定内容

### 6.3 与 `pipeline-task-diagnosis` 的边界（N204 闭环）

> **核心原则**: pipeline-task-diagnosis 是 GAF 专属的"节点执行诊断"方法论（日志→隔离→验输入→弹窗→降级），
> 在 systematic-debugging 的"根因调查"阶段内按 pipeline 场景细化。三者时间轴：
> `bug 发生 → systematic-debugging (通用根因) + pipeline-task-diagnosis (pipeline 节点细化) → commit → 本 skill (反思)`。

| 维度 | `pipeline-task-diagnosis` (GAF) | 本 skill (反思) |
|------|--------------------------------|-----------------|
| 触发时机 | bug_fix 且 symptom 涉及 pipeline 节点 / 任务失败关键词 / 日志含错误码 | commit 完成后 |
| 核心问题 | "这个节点为什么失败? 配置/数据流/弹窗/代码?" | "这次学到了什么? 如何防止复发?" |
| 输入 | 日志 + 截图 + 节点配置 + pipeline 定义 | 已完成的代码变更 + commit hash |
| 输出 | 失败节点定位 + 修复方向 | lessons/ 教训文件 + yn-matrices 检查 |
| 时间轴 | 修复**之前** | 修复**之后** |

**硬约束**:
- ✅ 反思时发现"诊断不充分 / 有节点级问题", 调用 Skill(name='pipeline-task-diagnosis') (方法论参考) 让 AI 回到诊断阶段
- ✅ 诊断过程中发现新根因模式, 应更新 `../pipeline-task-diagnosis/SKILL.md` 常见错误模式
- ❌ 本 skill 不写节点级诊断方法论 (弹窗检测 / ROI 降级 / 日志路径速查)

**交叉引用**:
- 调用 Skill(name='pipeline-task-diagnosis') (方法论参考)
- 调用 Skill(name='systematic-debugging') (方法论参考)
- 触发硬约束见 `.ai-memory/meta/env-hardrules-contextual.md` §诊断触发硬约束 (N204)
- 详细边界见本文件 §6.2（TD-029 闭环，含职责划分表）

---

## 7. 大修改七维度评分自决模板（N167；命名归一 = 修改清单 — TD-192 修复 2026-07-18, 历史 N151 v2 升级已合并到 N167）

> **命名归一**: 本节是"修改清单"评分模板（改前评估，7 维度），与 project_rules §3.7 L3-1 "扫描清单"（找问题，9 维度）+ 本 skill §2 "反思清单"（改后检查，24 项 = 5 前置 + 19 Y/N）三层互补，不混淆
> **来源**：用户反馈 — "要是 AI 能依据修改四维度评估原则来判断哪个方案或方向好，那其实可以让 AI 自决" + 用户反馈 升级为七维度（线上业务服务完整版）
> **适用场景**：refactor 分支 step_4，A/B/C 备选方案产出后
> **单一权威源**：本节是七维度评分模板的唯一来源；`gaf-orchestrator/SKILL.md` step_4 引用本节
> **N167 升级原因**：原四维度缺少性能/安全/维护成本维度，线上业务服务必备

### 7.1 评分维度（每项 1-3 分）

| 维度 | 3 分（最优） | 2 分（中等） | 1 分（最差） |
|------|------------|------------|------------|
| ① 架构长远性 | 适配 3-5 年扩展，规范分层，清理债务，无循环依赖 | 部分改善，留少量债务 | 治标不治本，留技术债 |
| ② 全局归一化 | 统一编码/DB/接口/业务逻辑，消除重复实现 | 部分归一，仍有双概念 | 双概念并存，无归一 |
| ③ 新旧兼容 | 单人自用项目=不兼容旧系统，一次性切换 | 短期过渡，有明确删除计划 | 保留旧实现 + deprecated 标记 |
| ④ 现有业务完善 | 补齐缺失流程/极端边界/全链路异常/容错 | 部分检查 | 不查同根因 |
| ⑤ 性能资源优化 | 优化 DB 慢查询/事务拆分/循环 IO/并发控制 | 部分优化 | 不优化性能 |
| ⑥ 安全合规加固 | 统一权限/脱敏/SQL 注入防护/审计日志 | 部分加固 | 不加固安全 |
| ⑦ 长期维护成本 | 配套架构/DB/接口文档 + 单元/回归测试 + 标准化注释 | 部分文档/测试 | 无文档无测试 |

> **GAF 项目定位**：7 维度全适用，⑤/⑥ 优先级中/低（单人自用 + Django 后端 + 单人多 agent 客户端）

### 7.2 评分表示例

| 方案 | ① 架构 | ② 归一化 | ③ 兼容 | ④ 完善 | ⑤ 性能 | ⑥ 安全 | ⑦ 维护 | 总分 | 自决? |
|------|------|---------|------|------|------|------|------|------|------|
| A: 删除旧实现 + 迁移 | 3 | 3 | 3 | 3 | 2 | 2 | 3 | 19 | ✅ 自决执行 |
| B: 保留双套过渡 | 1 | 1 | 1 | 2 | 1 | 1 | 1 | 8 | ❌ |
| C: 下游 workaround | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 7 | ❌ |

### 7.3 自决规则

- **总分 ≥ 19 且领先第二名 ≥ 5 分** → AI 自决执行最优方案（满分 21，阈值 19/21 ≈ 原四维度 10/12 比例）
- **总分 < 19 或差距 < 5 分** → `AskUserQuestion` 附评分表让用户选
- **平分** → `AskUserQuestion`（说明平分原因 + 关键差异点）

### 7.4 仍需 AskUserQuestion 的 4 类硬场景

| 场景 | 原因 | 示例 |
|------|------|------|
| ① FK 绊住 | 跨 app 外键迁移影响数据完整性，AI 无法评估业务影响 | 合并两套模型时 FK 跨 app |
| ② schema 分裂无法消除 | A/B/C 都不能消除双 schema 并存 | 两个数据库表结构不同且都活跃 |
| ③ 业务语义判断 | 字段/表是业务保留还是历史遗留，AI 无法判定 | "这个字段是否还在用" |
| ④ §3.5 不可逆/远程操作 | 硬约束红线 | 删除数据 / `git push` / `git branch -D` |

**硬场景 ③ 业务语义判定流程 (spec-49 强化 — 防误判)**:
判定问题: "这个决策影响数据保留/业务流程吗?"
- Y → AskUserQuestion (业务语义需用户判定)
- N → 可自决 (纯技术决策)

### 7.5 评分输出格式（写入 spec/反思矩阵）

> **spec-49 强化**: 加 ⑤⑥ 必填理由 + 反向论证 + 硬场景 ③ 判定 (防主观空间凑分)

```
## N151+N167 七维度评分 (commit <hash>)

| 方案 | ① | ② | ③ | ④ | ⑤ | ⑥ | ⑦ | 总分 | 自决? |
|------|---|---|---|---|---|---|---|------|------|
| A    | 3 | 3 | 3 | 3 | 2 | 2 | 3 | 19   | ✅   |
| B    | 1 | 1 | 1 | 2 | 1 | 1 | 1 | 8    | ❌   |

**⑤ 性能资源优化理由**: <一行理由, 不允许默认 2 分>
**⑥ 安全合规加固理由**: <一行理由, 不允许默认 2 分>
**反向论证 (spec-49 必填)**:
- **为何不选 B**: <理由 1>; <理由 2>
- **为何不选 C**: <理由 1>; <理由 2>
**硬场景 ③ 业务语义判定**: 这个决策影响数据保留/业务流程吗? N → 可自决; Y → AskUserQuestion
**自决决策**: A (总分 19 ≥ 19, 领先 B 11 分 ≥ 5)
**硬场景检查**: ① FK 绊住? N ② schema 分裂? N ③ 业务语义? N ④ 不可逆? N
**执行**: A 方案
```

### 7.6 与 §2.0.5 的关系

- `project_rules.md §2.0.5` 定义七维度原则（硬约束层）
- 本节 §7 定义评分模板（操作层）
- `gaf-orchestrator/SKILL.md` step_4 引用本节（路由层）
- 三层单一权威源，不重复定义
- **详细 Y/N 矩阵 + 维度适用场景表**: `.ai-memory/meta/yn-matrices/_refactor-dimensions.md`

---

## Decision Tree

> **v9.0 单一权威源**: 决策树见 `gaf-orchestrator/SKILL.md ## Decision Tree`。
> 本 skill 仅在 task_type=bug_fix/refactor 时被 gaf-orchestrator 加载，不保留决策树副本。
