---
date: 2026-07-08
symptom: [n151, architecture-first, major-changes, dual-implementation, minimization-antipattern, ai-autonomy, abc-decision, pipeline-split-brain]
solution: 大修改 (>500行/架构变更/跨模块/DB迁移/API契约) 必须从架构视角决策 — 先盘点真实状态 (数据/FK/schema/调用点) → 识别双套并存反模式 → 产出 A/B/C 备选方案 (每个方案有架构依据) → 拒绝"保留两套各管一摊"和"最小化修补" → AI 自决同样适用 (N109/N113/N115/N127 自决权在大修改场景受架构视角约束)。
diff_keywords: [architecture-first, dual-implementation, split-brain, major-change, minimization]
related_files:
  - .trae/rules/project_rules.md
  - .trae/skills/gaf-orchestrator/SKILL.md
  - .trae/skills/gaf-task-execution/SKILL.md
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/meta/yn-matrices.md
  - .ai-memory/summaries/architecture-mistakes.md
  - docs/project-status.md
created_by: AI
n_id: N151
topic: architecture
title: 大修改必须从架构视角决策 — 拒绝双套并存/最小化修补 (AI 自决同样适用)
category: ai-autonomy
priority: high
load_when: [major-change, architecture-decision, dual-implementation, split-brain, refactor-large, db-migration, api-contract-change, abc-decision-needed]
level: L1
---

# N151 — 大修改必须从架构视角决策 — 拒绝双套并存/最小化修补

> **登记时间**：2026-07-08
> **发现于**：TD-061 Pipeline split-brain 决策准备阶段
> **触发原话**：用户 "ai自决也要从架构看，这得加进规则或者skill里，所有大修改都以架构来看，然后继续任务" + 上一轮 "不要保留两套，要重架构看，自决也要从架构看，这里最小化原则不太好"
> **跨引用**：N109 (决策自决) / N113 (节奏自决) / N115 (入口自决) / N127 (推进自决) / N150 (从整体框架看问题 — 但 N150 限 bug fix 视角，N151 限大修改架构视角) / N95 (L1 4 层分发)

## 1. 症状 (Symptom)

TD-061 Pipeline split-brain 决策准备时，AI 默认倾向"最小化"路径：

1. **`tasks.Pipeline` 与 `pipeline.Pipeline` 两套并存**：
   - `tasks.Pipeline`：BigAutoField PK + `pipeline_data` JSONField + `sub_pipeline` FK + `version` — 用户 CRUD 用
   - `pipeline.Pipeline`：UUIDField PK + `graph_data` JSONField + `is_template` + `estimated_duration_ms` + `version` — React Flow 执行用
   - schema 不同 / API 路径不同 / 前端调用点分散 / Agent 仅用 `pipeline.Pipeline` 的 `graph_data`
2. **AI 默认路径风险**：在 N109/N113/N115/N127 完全自治权下，AI 可能自决选"保留两套各管一摊"（最小改动），而非架构决策（合并或明确分工）
3. **用户反馈**：「不要保留两套，要重架构看，自决也要从架构看，这里最小化原则不太好」
4. **同类历史模式**：
   - TD-021 Stage 6 评估时，初判 "Pipeline/PipelineSnapshot 重复" → 真实盘点后发现是"职责分裂"非"重复" → 标 TD-061 推后
   - TD-065/N150 `--no-verify` 滥用 = 同根因家族（AI 走"最快路径"绕过架构层）

## 2. 根因 (Root Cause)

### 直接根因
1. **N109/N113/N115/N127 自决权没有"架构视角"约束**：
   - N109 已计划任务 AI 完全自治（选/拆/写/commit）
   - 但"完全自治"不等于"凭最小改动自决"
   - 缺一条硬约束：大修改场景必须先盘点架构真实状态再决策
2. **§2.0 三原则（扩展性/逻辑正确性/命名正确性）是写代码层原则**，未覆盖"架构决策"层
3. **N150 "从整体框架看问题" 限 bug fix 场景**（修一个 bug 检查同类），未覆盖"大修改架构决策"场景

### 架构反模式（深层根因）

**「最小化原则用于架构决策」**：
- AI 默认偏好"最小改动"路径（认知负担最低、风险感知最低）
- 但架构决策场景下，"最小改动"往往等于"保留现状 + 加 workaround"
- 短期看是低风险，长期看是技术债堆积（如 TD-061 两套 Pipeline 并存就是历史"最小化"决策的产物）

**「双套并存 = 职责分裂未被决策」**：
- 当两套实现并存且 schema 不同，本质是"职责分工未被明确决策"的产物
- 保留双套 = 把决策推迟到无限期未来
- 每多保留一天，FK 引用 / 前端调用 / 数据漂移风险就增加一点

**「AI 自决 ≠ 最小化自决」**：
- N109 的自决权是"已计划任务不需问用户"
- 不是"已计划任务可凭最小改动自决"
- AI 自决同样受架构视角约束

## 3. 解决方案 (Solution) — 5 步架构视角流程

### Step 1: 架构盘点 (Architectural Inventory)
大修改决策前，必须先盘点当前架构真实状态：
- **数据维度**：DB 行数、表 schema、字段差异
- **依赖维度**：FK 引用（哪些模型引用了待决策对象）、跨 app import
- **调用维度**：前端 API 调用点、Agent 调用点、Serializer/View/URL 路径
- **历史维度**：是否有评估报告、是否有 TD 记录、是否有历史决策

### Step 2: 识别架构反模式 (Antipattern Detection)
盘点后识别是否存在反模式：
- **双套并存**：两套实现职责分裂（schema 不同 + 用途不同 + 都活跃）
- **越界归属**：模型/模块在错误的 app/目录下
- **重复实现**：同一功能多套实现
- **schema 分裂**：同概念不同字段类型/不同 PK

### Step 3: 产出 A/B/C 备选方案 (Options with Architecture Rationale)
每个备选方案必须列 5 项**架构依据**（非工作量估算）：
1. **当前架构问题**：本方案解决什么架构问题
2. **方案对架构的影响**：合并/分工/重命名对架构的影响
3. **长期可维护性**：3-6 个月后这个方案是否仍然合理
4. **迁移成本/风险**：数据迁移/schema 变更/FK 重指向/前端配套
5. **连带影响**：其他 TD/模型/模块的连带变化（如 TD-061 决策影响 Recording/TraceSpan/PipelineSnapshot）

### Step 4: 拒绝两类反模式路径
- ❌ **拒绝"保留两套各管一摊"**：双套并存不是方案，是决策推迟
- ❌ **拒绝"最小化修补"**：不在下游加 workaround 适配架构缺陷
- ❌ **拒绝"为越界而越界"**：盘点后确认无目标 app / 数据无 FK / 模型在原 app 更合理 → KEEP 也是合法决策（与"最小化"不同，KEEP 是架构判定结果）

### Step 5: AI 自决同样适用 (AI Autonomy Bound by Architecture)
- ✅ **AI 自决权保留**：N109/N113/N115/N127 在大修改场景仍生效（不需问"是否开始"）
- ✅ **但自决前必跑 Step 1-4**：盘点 + 识别 + 备选 + 拒绝反模式
- ✅ **决策点用 AskUserQuestion**：A/B/C 方案产出后，如方案对架构有重大影响（如合并两套模型需 schema 迁移），用 AskUserQuestion 让用户选方向
- ❌ **禁止 AI 凭"最小改动"自决大修改方向**：大修改方向必走架构视角，AI 自决的是"如何执行"不是"走哪个方向"

## 4. 验证 (Verification)

### N151 触发判定（大修改场景）
| 规模判定 | 是否触发 N151 |
|---------|--------------|
| > 500 行 diff | ✅ 触发 |
| 架构变更（合并/拆分/迁移 app） | ✅ 触发 |
| 跨模块（涉及 2+ app 或前后端联动） | ✅ 触发 |
| DB 迁移（schema 变更 / FK 重指向 / 数据迁移） | ✅ 触发 |
| API 契约变更（URL/字段/状态码） | ✅ 触发 |
| 单文件 fix / typo / < 50 行 | ❌ 不触发（走 N150 整体框架） |

### Y/N 检查表（大修改决策前必跑）
| # | 检查项 | Y/N |
|:-:|--------|:--:|
| 1 | 是否完成 Step 1 架构盘点（数据/依赖/调用/历史 4 维度） | |
| 2 | 是否识别 Step 2 反模式（双套并存/越界/重复/schema 分裂） | |
| 3 | 是否产出 ≥ 2 个备选方案（A/B/C） | |
| 4 | 每个方案是否列出 5 项架构依据 | |
| 5 | 是否拒绝"保留双套"和"最小化修补"两类反模式路径 | |
| 6 | KEEP 决策（如适用）是否基于架构判定（无目标 app / FK 在原 app 更合理） | |
| 7 | 连带影响（其他 TD/模型）是否列出 | |

### 同根因家族
- **N109/N113/N115/N127 (AI 自决家族)**：N151 是这个家族的"架构视角约束"补丁 — 自决权不变，但大修改场景必先走架构视角
- **N150 (整体框架看问题)**：N150 限 bug fix 视角（修一个查同类），N151 限大修改架构视角（盘点+备选+拒绝反模式）
- **N95 (L1 4 层分发)**：N151 本身是 L1，按 4 层分发
- **§2.0 三原则**：写代码层原则，N151 是架构决策层原则，互补不冲突

## 5. 证据 (Evidence)

### Problem
TD-061 Pipeline split-brain 决策准备时，AI 倾向"最小化"路径（保留两套各管一摊），用户明确否定："不要保留两套，要重架构看，自决也要从架构看，这里最小化原则不太好"。

### Solution
登记 N151 教训，按 L1 4 层分发：
- ① lessons/ 本文件
- ② architecture-mistakes.md 新增 §N151 摘要
- ④ yn-matrices.md §2 ai-autonomy 新增 N151 Y/N 矩阵
- ⑤ project_rules.md 新增 §2.0.4 大修改架构视角原则 + §6.4 N151 索引行 + §6.5 通用硬约束

同步更新 2 个 skill：
- gaf-orchestrator/SKILL.md refactor 分支 step_3_assess_impact → 加架构视角硬约束
- gaf-task-execution/SKILL.md §3 refactor 5 段流程 step_1_impact_assessment → 加架构视角硬约束

### Verification
- 跑 `grep N151 .ai-memory/meta/failure-modes.md` 应找到索引行
- 跑 `grep N151 .ai-memory/meta/yn-matrices.md` 应找到 §2 矩阵
- 跑 `grep N151 .trae/rules/project_rules.md` 应找到 §6.4 索引行 + §6.5 硬约束
- 跑 `grep "2.0.4" .trae/rules/project_rules.md` 应找到新章节
- TD-061 决策备忘录必须按 N151 5 步流程产出
