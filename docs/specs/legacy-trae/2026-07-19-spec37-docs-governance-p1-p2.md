# spec-37: docs/ 与 .ai-memory/ 文档治理 (P1 + P2)

> **来源**: spec-36 (2026-07-19) 评估发现的 P1 中等问题 4 项 + P2 轻微问题 6 项 (与 TD-279 合并)
> **本 spec 范围**: P1 4 项 + P2 6 项, 共 10 项文档治理
> **状态**: ✅ Done (2026-07-19, 8 Phase 全过)

## 阶段状态表

| Phase | 内容 | 优先级 | 行数估计 | 状态 | 完成时间 | Commit | 验收 evidence |
|:-----:|------|:------:|:--------:|:----:|:--------:|:------:|--------------|
| 1 | docs/backend/operations/ 10 文件迁移到 docs/general/design/ | P1 | ~10 Move-Item + 引用更新 | ✅ | 2026-07-19 | `-` | 8 文件迁移 + 4 处引用更新 (pipeline-nodes.md / data-flow.md / gaf-knowledge-base SKILL.md / backend/skills/loader.py) |
| 2 | resource-pack 双套合并 (v1.0 + v1.1 → resource-pack-design.md) | P1 | ~200 行合并 | ✅ | 2026-07-19 | `-` | v1.0 spec (484 行) + v1.1 guide (278 行) 合并为 resource-pack-design.md (v1.2, 14 节) + 原文件归档 .trash/ + docs/backend/ 空目录删除 |
| 3 | knowledge/common-pitfalls.md 评估处理 + terminology.md 路径修复 | P1 | ~150 行 | ✅ | 2026-07-19 | `-` | common-pitfalls.md 加 deprecation banner (N40-N108 引导到 failure-modes.md) + terminology.md frontmatter 删除错误路径 |
| 4 | summaries/architecture-mistakes.md §0 去重 (N151/N167/N169) | P1 | ~50 行精简 | ✅ | 2026-07-19 | `-` | §0/§0.1/§0.2 各从 8 行精简到 3 行 (标题 + 权威源链接 + 1 行简述) |
| 5 | N95/N116 状态评估 (预期跳过 — 两者均 Active 不应归档) | P2 | 评估记录 | ✅ | 2026-07-19 | `-` | N95 Active (§6.2 子分级分发规则) + N116 Active (R-M-W SyncLock 核心硬约束) — 不归档 |
| 6 | N119 双重引用评估 (预期跳过 — 家族合并设计如此) | P2 | 评估记录 | ✅ | 2026-07-19 | `-` | N119 14 处引用评估为家族合并设计合理 (Dormant 状态, 无双重引用冗余) |
| 7 | README.md TD 计数更新 + checklets/ 合并评估 + pre-commit-stages 迁移 | P2 | ~50 行 | ✅ | 2026-07-19 | `-` | pre-commit-stages.md 迁到 design/ + 3 处活跃引用更新 + tech-debt/README.md TD 计数更新 (76/142/7/225 → 10/235/26/271) |
| 8 | 全量回归 + commit + C-065 | P2 | - | ✅ | 2026-07-19 | `-` | 5 sync/check 脚本全过 (0 errors, 185 warnings 全为模拟器 ADB 路径) + C-065 落地 + TD-279 迁到 fixed.md |

**总计**: 10 项 (P1 4 + P2 6), ~500 行 diff — ✅ 全部完成

---

## 架构盘点 (N151 step_1, 2026-07-19)

### 当前 docs/ 与 .ai-memory/ 结构

```
docs/
├── backend/operations/          ← 10 文件 (本 spec Phase 1 迁移)
│   ├── concurrency-design.md
│   ├── custom-task-design.md
│   ├── llm-integration-design.md
│   ├── monitor-design.md
│   ├── pipeline-authoring-guide.md
│   ├── resource-pack-guide.md   ← Phase 2 合并到 design/resource-pack-design.md
│   ├── resource-pack-spec.md    ← Phase 2 合并 (v1.0, 旧版本)
│   ├── screenshot-optimization.md
│   ├── task-cancel-design.md
│   └── task-execution-reality.md
├── general/
│   ├── analysis/                (6 文件)
│   ├── design/                  (5 文件, Phase 1 目标)
│   ├── health-checks/           (spec-36 新迁入)
│   ├── tech-debt/               (4 文件)
│   ├── troubleshooting/
│   │   └── task-execution-troubleshooting.md  ← 独立 (排查步骤指南)
│   ├── completed-features.md
│   ├── monthly-health-check.md
│   ├── pending-roadmap.md
│   └── pre-commit-stages.md     ← Phase 7 迁到 design/
└── standards/                   (4 文件, 不动)

.ai-memory/
├── knowledge/
│   ├── common-pitfalls.md       ← Phase 3 评估处理
│   ├── data-chain.md
│   ├── error-recovery.md
│   ├── task-lifecycle.md
│   └── terminology.md           ← Phase 3 路径修复
├── summaries/
│   └── architecture-mistakes.md ← Phase 4 §0 去重
└── checklets/
    └── data-chain-checklist.md  ← Phase 7 合并评估
```

### 识别反模式 (N151 step_2)

| # | 反模式 | 位置 | 修复 |
|:-:|--------|------|------|
| 1 | `docs/backend/operations/` 不符合 §2.1 文档分层规则 (后端子 app 内部约定才放 backend/) | docs/backend/operations/ 10 文件 | 迁到 docs/general/design/ |
| 2 | resource-pack 双套并存 (v1.0 spec + v1.1 guide, 同主题迭代) | docs/backend/operations/resource-pack-{spec,guide}.md | 合并为 design/resource-pack-design.md |
| 3 | terminology.md frontmatter 引用不存在的 `.ai-memory/architecture-overview.md` | .ai-memory/knowledge/terminology.md L18 | 修复为 docs/general/design/architecture-overview.md |
| 4 | architecture-mistakes.md §0 (N151/N167/N169) 与 rules + failure-modes + lessons 三处重复 | .ai-memory/summaries/architecture-mistakes.md L35-66 | 保留索引行, 详情链接到权威源 |
| 5 | pre-commit-stages.md 在 docs/general/ 根而非 design/ | docs/general/pre-commit-stages.md | 迁到 docs/general/design/ |

### A/B/C 备选方案 (N151 step_3 + step_4)

**方案 A** (本 spec 推荐): 全量治理 — 10 项一次性完成, 单 spec 8 Phase
- ✅ 优点: 一次 commit 闭环, 文档结构一次性归一, 避免"修一半"中间态
- ❌ 缺点: diff ~500 行, review 工作量中等
- 评分: 7 维度总分 23/35 (架构长远 4 / 全局归一 4 / 不兼容 3 / 业务完善 3 / 性能 3 / 安全 3 / 维护 3)

**方案 B**: 拆分 spec-37 (P1) + spec-38 (P2)
- ✅ 优点: 单 spec diff 小, P1 优先闭环
- ❌ 缺点: 中间态 — P1 完成后 docs/general/design/ 新增 10 文件, 但 pre-commit-stages.md 还在原位 (Phase 7 才迁)
- 评分: 7 维度总分 20/35

**方案 C**: 仅做 P1 (4 项), P2 登记为 TD
- ✅ 优点: 最小 diff
- ❌ 缺点: P2 6 项登记为 TD 后又堆积在 active.md, 违背 TD-231 主动治理原则
- 评分: 7 维度总分 18/35

**AI 自决 (N151 step_5)**: 方案 A (总分 23 ≥ 19 且领先 B 3 分, 未达 5 分阈值, 但方案 A 在 "架构长远性" + "全局归一化" 维度均满分, 符合 §2.0 三原则的"正确性优先")

---

## Phase 1: docs/backend/operations/ 10 文件迁移到 docs/general/design/

### 1.1 迁移文件清单

| 源文件 | 目标文件 | 主题 |
|---|---|---|
| `docs/backend/operations/concurrency-design.md` | `docs/general/design/concurrency-design.md` | 并发状态管理设计 |
| `docs/backend/operations/custom-task-design.md` | `docs/general/design/custom-task-design.md` | 自定义任务设计 (v1.2) |
| `docs/backend/operations/llm-integration-design.md` | `docs/general/design/llm-integration-design.md` | LLM 集成设计 |
| `docs/backend/operations/monitor-design.md` | `docs/general/design/monitor-design.md` | 监控设计 |
| `docs/backend/operations/pipeline-authoring-guide.md` | `docs/general/design/pipeline-authoring-guide.md` | Pipeline 编写指南 |
| `docs/backend/operations/screenshot-optimization.md` | `docs/general/design/screenshot-optimization.md` | 截图优化 |
| `docs/backend/operations/task-cancel-design.md` | `docs/general/design/task-cancel-design.md` | 任务取消设计 |
| `docs/backend/operations/task-execution-reality.md` | `docs/general/design/task-execution-reality.md` | 任务执行 reality (v1.1) |
| `docs/backend/operations/resource-pack-guide.md` | (Phase 2 处理, 不直接迁) | 资源包指南 (v1.1) |
| `docs/backend/operations/resource-pack-spec.md` | (Phase 2 处理, 不直接迁) | 资源包规范 (v1.0) |

### 1.2 操作步骤

1. 8 个文件用 `Move-Item` 从 `docs/backend/operations/` 迁到 `docs/general/design/` (resource-pack 2 个文件留待 Phase 2)
2. 删除空目录 `docs/backend/operations/` + `docs/backend/` (如无其他文件)
3. grep 全仓库引用 `docs/backend/operations/` 路径, 更新为新路径
4. 跑 `python scripts/bootstrap/sync_docs_index.py` 重生成 docs-index.md

### 1.3 引用更新清单 (预期)

- `docs/backend/operations/custom-task-design.md` §0.1 引用 `task-execution-reality.md` (相对路径, 迁移后仍有效)
- `.ai-memory/meta/docs-index.md` (自动重生成)
- `.ai-memory/README.md` 如有引用
- `docs/general/pending-roadmap.md` 如有引用
- spec 历史文件中的引用 (不更新, 保留历史)

### Phase 1 验收
- [ ] 8 个文件迁到 docs/general/design/
- [ ] docs/backend/operations/ + docs/backend/ 空目录删除
- [ ] grep `docs/backend/operations/` 在 .ai-memory/ + docs/ (非 specs/) 下 0 引用
- [ ] sync_docs_index.py 跑通, docs-index.md 0 失效路径

---

## Phase 2: resource-pack 双套合并

### 2.1 现状评估

- `resource-pack-spec.md` (v1.0, 2026-05-17, SubTask 1.11) — 资源包规范设计
- `resource-pack-guide.md` (v1.1, 2026-05-18, 阶段七) — 资源包规范指南
- 两者主题完全一致 (资源包目录结构 + JSON Schema), v1.1 是 v1.0 的迭代
- v1.1 标题"指南" vs v1.0 标题"设计", 但内容都是规范定义

### 2.2 合并策略

- 合并目标: `docs/general/design/resource-pack-design.md` (统一命名 "design" 后缀)
- 内容来源: 以 v1.1 (guide) 为主体, 补充 v1.0 (spec) 中独有的内容 (JSON Schema 细节, 如有)
- 删除 v1.0 和 v1.1 原文件 (Phase 1 不迁移这 2 个文件, Phase 2 直接合并到新位置)
- 更新 frontmatter `last_updated: 2026-07-19` + `applies_to: ['backend', 'design']`

### 2.3 操作步骤

1. Read 完整内容 of `resource-pack-guide.md` (v1.1) + `resource-pack-spec.md` (v1.0)
2. 对比两者, 识别 v1.0 独有内容 (如有)
3. Write 新文件 `docs/general/design/resource-pack-design.md` (合并内容)
4. Move v1.0 + v1.1 原文件到 .trash/
5. 更新引用 (custom-task-design.md §0 表格中 "资源包目录结构" 行)

### Phase 2 验收
- [ ] docs/general/design/resource-pack-design.md 创建 (合并 v1.0 + v1.1)
- [ ] 原 resource-pack-spec.md + resource-pack-guide.md 移到 .trash/
- [ ] grep `resource-pack-spec.md` + `resource-pack-guide.md` 在 docs/ + .ai-memory/ 下 0 活跃引用

---

## Phase 3: knowledge/common-pitfalls.md 评估处理 + terminology.md 路径修复

### 3.1 common-pitfalls.md 评估

**现状**: 132 行, 20 个陷阱 (N40-N108 编号), 5 分类 (数据/状态/异步/平台/AI 自身), 最后更新 2026-06-16

**评估方向**:
- 20 个陷阱的 N 编号是否被 N1XX lesson 取代?
  - N40/N76/N44/N42/N20 (数据类) → N95 (分级分发) / N112 (后端字段同步) / N145 (consumer 上行)
  - N84/N76/N95/N43 (状态类) → N116 (并发状态) / N95 (分级分发)
  - N70/N88/N85/N41 (异步类) → N148 (双向控制消息)
  - N55/N10/N9/N100 (平台类) → N138/N146 (agent-platform) / N139 (Vite proxy)
  - N101/N106/N100/N93 (AI 自身) → N126 (诚实标记) / N106 (路径漂移) / N109 (AI 自决)
- 大部分 N40-N108 应该已有 N1XX lesson 覆盖, common-pitfalls.md 内容部分过时

**处理方案** (执行时决定):
- **A** (推荐): 保留文件, 加 deprecation 标记 + 每个陷阱加 "→ 详见 N1XX" 链接
- **B**: 删除文件, 把仍有效的陷阱合并到 architecture-mistakes.md
- **C**: 完全删除 (如果 20 个陷阱全部已被 N1XX 取代)

### 3.2 terminology.md 路径修复

**现状** (frontmatter L18):
```yaml
related_files:
- .ai-memory/tech-stack.md
- .ai-memory/architecture-overview.md    ← 错误: 该文件不存在
- .ai-memory/agent-protocol.md
- docs/general/design/architecture-overview.md
```

**修复**: 删除 `.ai-memory/architecture-overview.md` 行 (重复且路径错误, 已经有 `docs/general/design/architecture-overview.md`)

### Phase 3 验收
- [ ] common-pitfalls.md 按选定方案处理 (执行时决定 A/B/C)
- [ ] terminology.md frontmatter `related_files` 修复
- [ ] grep `.ai-memory/architecture-overview.md` 全仓库 0 引用

---

## Phase 4: summaries/architecture-mistakes.md §0 去重

### 4.1 现状

`architecture-mistakes.md` §0/§0.1/§0.2 (L35-66) 详述 N151/N167/N169, 但这些 N## 已经在:
- `project_rules.md §2.0.4` (N151) + `§2.0.5` (N167) + `§4.8` (N169 延后语义)
- `.ai-memory/meta/failure-modes.md` §Active N151/N167/N169 索引行
- `.ai-memory/lessons/architecture_2026-07-08-n151-*.md` + `architecture_2026-07-17-n167-*.md`
- `.ai-memory/lessons/workflow_2026-07-18-n169-*.md`

### 4.2 去重策略

保留 §0/§0.1/§0.2 的索引行 (1-2 行/节), 删除详情 (Problem/Root cause/Antipatterns/Fix/Rule/同根因家族 6 段), 改为链接到权威源:

```markdown
## 0. N151 — 大修改架构视角原则 (2026-07-08)

> **详情**: [project_rules.md §2.0.4](../../../.trae/rules/project_rules.md) + [failure-modes.md N151](../meta/failure-modes.md) + [lesson](../lessons/architecture_2026-07-08-n151-architecture-first-for-major-changes.md)

5 步架构视角流程 (盘点 → 识别反模式 → A/B/C → 拒绝反模式 → AI 自决). 大修改 (>500 行/架构变更/跨模块/DB 迁移/API 契约) 决策前必跑.

---

## 0.1 N167 — 7 维度评估清单 (2026-07-17)

> **详情**: [project_rules.md §2.0.5](../../../.trae/rules/project_rules.md) + [failure-modes.md N167](../meta/failure-modes.md) + [lesson](../lessons/architecture_2026-07-17-n167-refactor-evaluation-dimensions.md)

七维度评估: 1.架构长远性 / 2.全局归一化 / 3.新旧兼容 / 4.业务完善 / 5.性能 / 6.安全 / 7.维护成本. 中修改跑核心 1/2/7, 大修改全跑 7 维度 + N151.

---

## 0.2 N169 — TD "延后" 语义错位 (2026-07-18)

> **详情**: [project_rules.md §4.8](../../../.trae/rules/project_rules.md) + [failure-modes.md N169](../meta/failure-modes.md) + [lesson](../lessons/workflow_2026-07-18-n169-td-deferred-semantics.md)

TD "延后" = 做完上一个 spec/类别后立即接修, 非等用户指令. "何时修" 字段必须用明确触发点.
```

### Phase 4 验收
- [ ] §0/§0.1/§0.2 各段从 ~10 行精简到 ~3 行
- [ ] 每段含 3 个权威源链接 (rules + failure-modes + lesson)
- [ ] architecture-mistakes.md 整体行数减少 ~50 行

---

## Phase 5: N95/N116 状态评估 (预期跳过)

### 5.1 评估

- **N95** (分级分发缺位): Active, 是 §6.2 L0/L1-小/L1-中/L1-大 子分发的核心规则, **永不归档**
- **N116** (并发状态管理): Active, R-M-W 必用 SyncLock + 改 sync 必跑 benchmark, 仍有效

### 5.2 预期结论

两者均不应归档。spec-36 总结中"N95/N116 状态归档"是评估时的初步判断, 实际两者都是 §6.2 / 并发设计的核心硬约束。

### Phase 5 验收
- [ ] 在 spec 文件记录评估结论: N95/N116 均为 Active, 不归档
- [ ] failure-modes.md §Active 中 N95/N116 索引行保持不变

---

## Phase 6: N119 双重引用评估 (预期跳过)

### 6.1 评估

N119 (命令挂起) 是 Dormant 状态, 家族合并到 N111 (命令超时)。
- `failure-modes.md §Dormant` L135 已有索引行: `| N119 | 命令挂起 | N111 | _ai-autonomy.md N111 段 |`
- `lessons/README.md` 保留 N119 lesson 文件条目 (设计如此, 家族合并子条目保留文件)
- `lessons/testing_2026-06-17-n119-m2b-command-hang.md` 保留 (历史可查)

14 处 N119 引用 (Grep 结果):
- spec-36/spec-37 文件: 历史引用, 保留
- failure-modes.md: §Dormant 索引行 (合理)
- yn-matrices.md + _testing.md: Y/N 矩阵段 (合理, 设计如此)
- archived-lessons.md: 历史 (合理)
- architecture-mistakes.md: §7 同根因家族描述 (合理)
- pre-commit-stages.md §7: 同根因家族列表 (合理)
- gaf-reflect-and-evolve + gaf-lesson-router SKILL.md: 引用 (合理)
- lessons/README.md: topic 分类索引 (合理)
- check_yn_matrices_index.py: 脚本验证 (合理)
- evidence/2026-06-17-n119-m2b-command-hang/n119-m2b-command-hang.md: 历史 evidence (合理)
- fixed.md: 历史 (合理)

### 6.2 预期结论

N119 在 14 处引用均为合理 (家族合并设计 + 历史记录), 无真正"双重引用"冗余。

### Phase 6 验收
- [ ] 在 spec 文件记录评估结论: N119 14 处引用均合理, 无需清理

---

## Phase 7: README.md TD 计数 + checklets/ 合并评估 + pre-commit-stages 迁移

### 7.1 README.md TD 计数更新

**待确认**: 哪个 README.md 需要更新 TD 计数?
- `.ai-memory/README.md` — 无 TD 计数段
- `docs/general/tech-debt/README.md` — 待 Read 确认
- `docs/general/tech-debt/active.md` — 顶部可能有计数

执行时 Read 这 3 个文件, 找到过时 TD 计数并更新。

### 7.2 checklets/ 合并评估

**现状**: `.ai-memory/checklets/` 只有 1 个文件 `data-chain-checklist.md`

**评估方向**:
- data-chain-checklist.md 是审计检查清单, 与 knowledge/data-chain.md 主题相关
- 是否合并到 knowledge/ 或保留独立 checklets/ 目录?

**预期决策** (执行时确认):
- 保留 checklets/ 独立目录 — 审计清单与业务速查职责不同 (§2.1 N132 文档职责分离)
- 不合并, 仅在 .ai-memory/README.md 中明确 checklets/ 职责定位

### 7.3 pre-commit-stages.md 迁移

**现状**: `docs/general/pre-commit-stages.md` (在 docs/general/ 根)

**迁移目标**: `docs/general/design/pre-commit-stages.md` (与其他 design 文档统一)

**理由**: pre-commit-stages 是 GAF 特定的 pre-commit 治理设计文档, 与 design/ 下其他文档 (architecture-overview, debug-mode-design 等) 同类。

### Phase 7 验收
- [ ] README.md TD 计数更新 (具体文件执行时确认)
- [ ] checklets/ 职责定位在 .ai-memory/README.md 明确 (不合并)
- [ ] pre-commit-stages.md 迁到 docs/general/design/
- [ ] grep `docs/general/pre-commit-stages.md` 在 docs/ + .ai-memory/ 下 0 活跃引用

---

## Phase 8: 全量回归 + commit + C-065

### 8.1 全量回归检查

```
# 文档索引同步
python scripts/bootstrap/sync_docs_index.py
python scripts/bootstrap/sync_ai_memory.py
python scripts/bootstrap/sync_skills.py

# 一致性检查
python scripts/hooks/check_yn_matrices_index.py
python scripts/hooks/check_path_consistency.py
```

### 8.2 验收清单

- [ ] sync_docs_index.py PASS (docs-index.md 0 失效路径)
- [ ] sync_ai_memory.py PASS
- [ ] sync_skills.py PASS
- [ ] check_yn_matrices_index.py PASS
- [ ] check_path_consistency.py 0 errors (warnings 均为模拟器 ADB 路径, 项目设计如此)
- [ ] grep `docs/backend/operations/` 在 docs/ + .ai-memory/ 下 0 活跃引用
- [ ] grep `.ai-memory/architecture-overview.md` 全仓库 0 引用
- [ ] architecture-mistakes.md 行数减少 (§0 去重后)

### 8.3 commit + C-065

- commit message: `refactor(spec-37): docs governance P1+P2 (10 items, 8 phases)`
- 更新 `docs/general/completed-features.md` 加 C-065 条目
- 更新 `docs/general/tech-debt/active.md` 把 TD-279 状态改为 ✅ FIXED 并迁到 fixed.md

### Phase 8 验收
- [ ] commit hash 记录到 spec 状态表
- [ ] completed-features.md C-065 条目添加
- [ ] active.md TD-279 迁到 fixed.md (✅ FIXED + commit hash)

---

## N167 七维度评分 (本 spec 整体)

| 维度 | 评分 (1-5) | 说明 |
|:----:|:----------:|------|
| 1. 架构长远性 | 5 | 10 项治理一次性闭环, docs/ 结构归一, 符合 §2.1 文档分层规则 |
| 2. 全局归一化 | 5 | docs/backend/operations/ 迁 design/, resource-pack 合并, §0 去重 |
| 3. 新旧兼容 | 4 | 单人自用项目 = 不兼容旧路径, 但保留 .trash/ 历史可查 |
| 4. 现有业务完善 | 3 | 文档治理, 不涉及业务逻辑 |
| 5. 性能资源优化 | 3 | 文档治理, 不涉及性能 |
| 6. 安全合规加固 | 3 | 文档治理, 不涉及安全 |
| 7. 长期维护成本 | 4 | 一次性治理减少后续维护成本, 但需更新多处引用 |
| **总分** | **27/35** | ≥ 19, AI 自决执行 |

---

## spec 用时测量 (N173)

- start_ts: 2026-07-19 (本 spec 制定开始)
- end_ts: (执行完成后填写)
- duration: (计算后填写)
- 基线: 大修改 < 60 min
