---
spec_id: 2026-07-25-docs-ai-memory-restructure
title: docs/ 与 .ai-memory/ 双线索重构 + AI 自我进化沉淀闭环
status: completed
created: 2026-07-25
completed: 2026-07-26
owner: AI
applies_to_code_paths:
  - docs/**
  - .ai-memory/**
  - .trae/skills/gaf-orchestrator/SKILL.md
  - .trae/rules/project_rules.md
  - backend/gaf_core/management/commands/run_startup_checks.py
  - backend/gaf_core/startup_checks.py
  - scripts/bootstrap/sync_docs_index.py
  - scripts/bootstrap/sync_ai_memory.py
  - scripts/hooks/check_doc_path_drift.py
  - scripts/hooks/check_doc_code_sync.py (扩展, 不新建)
  - scripts/hooks/doc_sync_rules.py (扩展, 不新建)
related_context: .ai-memory/spec-context/2026-07-25-docs-restructure-context.md
---

# Spec: docs/ 与 .ai-memory/ 双线索重构 + AI 自我进化沉淀闭环

> **本文件是正式 spec**。设计上下文、用户决策原文、三轮对齐检查过程见 [`.ai-memory/spec-context/2026-07-25-docs-restructure-context.md`](../../../.ai-memory/spec-context/2026-07-25-docs-restructure-context.md)。
> **生命周期**: 实施完成（P0/P1/P2 全部 commit）→ 移到 `docs/specs/archived/YYYY-MM/`。

---

## §1 设计目标与原则

### 1.1 目标

让 `docs/` 和 `.ai-memory/` 两个目录从"演进残留"变为"双线索主导的清晰结构"，同时建立 AI 自我进化沉淀闭环和文档与代码同步更新机制。

### 1.2 核心原则

1. **双线索导航**（docs/）
   - 业务线索：按前端侧边栏 9 模块（workspace / game-profile / tasks / devices / resources / accounts / ops / ai / system）
   - 架构线索：按 GAF 五层（frontend / backend / agent / desktop / cross-cutting）
   - 文档归属强制二选一，跨业务+架构的文档放 `architecture/cross-cutting/`

2. **过程 vs 稳定分离**（两个目录分工）
   - `.ai-memory/` = AI 思维链**过程产物**（lessons / evidence / decision matrices / session）
   - `docs/` = **稳定知识库**（业务 / 架构 / 规范 / 技术债），AI L3 按需查询

3. **目录路径 = frontmatter module 值**
   - `docs/business/tasks/pipeline-design.md` → `module: business.tasks`
   - `docs/architecture/backend/celery-design.md` → `module: architecture.backend`
   - `sync_docs_index.py` 自动从目录路径生成 module 字段

4. **分阶段迁移，每阶段独立可验证**
   - P0：双线索建立 + spec 目录合并（最大收益）
   - P1：lessons 改名 + evidence 加清理 + AI 自我进化闭环
   - P2：根目录收敛 + 引用同步 hook（防回退）

5. **不动的部分**
   - `.trae/specs/`（TRAE 工具自动生成，保留原位）
   - `.trae/skills/`、`.trae/rules/`、`.trae/plans/`（不在本次范围；引用路径在 P2 同步更新）
   - `.ai-memory/{meta, knowledge, games, platforms, summaries, checklists, ops, session}/`（结构合理，保留）

### 1.3 成功标准

- 人类按业务或架构找文档，最多 2 次点击定位
- AI 通过 `docs-index.md` 的 `module` 字段过滤，0 跳转直达目标
- 100+ 文件路径引用全部更新，pre-commit hook 防止旧路径回退
- 无任何文件内容丢失（git mv 保留历史）
- AI 自我进化沉淀闭环可运行（启动时 + 会话内触发，无定时任务依赖）
- 文档与代码同步：AI 访问 docs/ 时实时检查 stale，标记过时文档

---

## §2 docs/ 目标结构

### 2.1 目录树

```
docs/
├── README.md                          # 双线索导航入口（新建）
│
├── business/                          # 业务视角（9 模块，对应前端侧边栏）
│   ├── README.md                      # 9 模块索引（新建）
│   ├── workspace/                     # 工作台（.gitkeep 占位）
│   ├── game-profile/                  # 游戏档案（.gitkeep 占位）
│   ├── tasks/                         # 任务
│   │   ├── pipeline-design.md         # ← 移自 general/design/custom-task-design.md + pipeline-authoring-guide.md（重叠则合并，否则分别命名）
│   │   ├── timeline-design.md         # ← 移自 general/design/debug-timeline-design.md
│   │   ├── debug-mode-design.md       # ← 移自 general/design/debug-mode-design.md
│   │   ├── recovery-design.md         # ← 移自 general/design/interface-recovery-design.md
│   │   ├── cancel-design.md           # ← 移自 general/design/task-cancel-design.md
│   │   ├── execution-reality.md       # ← 移自 general/design/task-execution-reality.md
│   │   └── troubleshooting.md         # ← 移自 general/troubleshooting/task-execution-troubleshooting.md
│   ├── devices/                       # 设备
│   │   ├── dpi-coordinate.md          # ← 移自 general/design/dpi-coordinate-system.md
│   │   └── screenshot-optimization.md # ← 移自 general/design/screenshot-optimization.md
│   ├── resources/                     # 资源
│   │   └── resource-pack-design.md    # ← 移自 general/design/resource-pack-design.md
│   ├── accounts/                      # 账户（.gitkeep 占位，待新文档填入）
│   ├── ops/                           # 运维
│   │   ├── monitor-design.md          # ← 移自 general/design/monitor-design.md
│   │   └── governance-dashboard.md    # ← 移自 governance/dashboard.md
│   ├── ai/                            # AI
│   │   ├── llm-integration.md         # ← 移自 general/design/llm-integration-design.md
│   │   └── input-mode-window-wait.md  # ← 移自 general/design/input-mode-and-window-wait-design.md
│   └── system/                        # 系统（.gitkeep 占位，待新文档填入）
│
├── architecture/                      # 架构视角（五层 + 横切）
│   ├── README.md                      # 五层架构索引（新建）
│   ├── overview.md                    # ← 移自 general/design/architecture-overview.md
│   ├── optimal-solution.md            # ← 移自 general/analysis/GAF-optimal-solution.md
│   ├── features-overview.md           # ← 移自 general/design/gaf-features-overview.md（业务×架构映射）
│   ├── frontend/                      # 前端层（.gitkeep 占位）
│   ├── backend/                       # 后端层（.gitkeep 占位）
│   ├── agent/                         # Agent 层（.gitkeep 占位）
│   ├── desktop/                       # Desktop 层
│   │   └── deployment-design.md       # ← 移自 general/design/deployment-design.md
│   └── cross-cutting/                 # 横切关注点
│       ├── concurrency-design.md      # ← 移自 general/design/concurrency-design.md
│       ├── pre-commit-stages.md       # ← 移自 general/design/pre-commit-stages.md
│       └── data-flow.md               # ← 移自 general/design/data-flow.md（若存在；不存在则不迁）
│
├── analysis/                          # 对比分析（保留顶层，因为是外部对比非 GAF 内部架构）
│   ├── GAF-vs-Alas-analysis.md
│   ├── GAF-vs-BD2-analysis.md
│   ├── GAF-vs-MaaFramework-analysis.md
│   ├── GAF-vs-ok-script-analysis.md
│   └── evaluation-zxcvbn-replacement.md
│
├── standards/                         # 编码规范（保持）
│   ├── api-contract.md
│   ├── backend-conventions.md
│   ├── frontend-conventions.md
│   └── testing-conventions.md
│
├── tech-debt/                         # 技术债（移到顶层，原 general/tech-debt/）
│   ├── README.md
│   ├── active.md
│   ├── fixed.md
│   └── wontfix.md
│
├── specs/                             # 合并 4 个 spec 目录为 1 个
│   ├── README.md                      # spec 编写规范（合并自 general/specs/README.md）
│   ├── dependency-graph.md            # ← 移自现有 docs/specs/dependency-graph.md
│   ├── active/                        # 进行中
│   │   └── 2026-07-25-docs-ai-memory-restructure.md  # 本文件
│   └── archived/                      # 已完成按月归档
│       └── YYYY-MM/
│
├── plans/                             # 实施计划（合并 superpowers/plans/）
│   └── 2026-07-25-logging-and-pipeline-hardening.md
│
├── health/                            # 健康检查（移自 general/health-checks/）
│   ├── README.md
│   └── 2026-07.md
│
├── completed-features.md              # ← 移自 general/completed-features.md
├── monthly-health-check.md            # ← 移自 general/monthly-health-check.md
└── pending-roadmap.md                 # ← 移自 general/pending-roadmap.md
```

### 2.2 关键设计决策

1. **`business/` 9 模块对应前端侧边栏** — 人类按"我在用哪个功能"找文档
2. **`architecture/` 五层 + 横切** — 人类按"我在改哪一层"找文档
3. **`features-overview.md` 放 `architecture/` 根** — 它是业务×架构映射表，属架构视角
4. **`analysis/` 保留顶层** — 4 份外部对比文档不属 GAF 内部架构，独立放
5. **`health/` 顶层 vs `business/ops/health-checks/`** — 月度健康报告是过程产物放 `health/`，运维治理放 `business/ops/`；`general/health-checks/` 内容全部移到 `docs/health/`，`business/ops/` 下不建 health-checks 子目录（避免重复）
6. **`specs/active/` + `specs/archived/YYYY-MM/`** — 进行中可快速找，已完成按月归档
7. **`plans/` 提到顶层** — 实施计划是独立产物，不该埋在 `superpowers/` 下
8. **空目录占位**（`workspace/`、`accounts/`、`system/`、`frontend/`、`backend/`、`agent/`）— 9 模块和 5 层都建出来，未来文档有归宿；每个空目录加 `.gitkeep`

### 2.3 `general/` 目录消失

所有内容按双线索重新分配。`docs/general/specs/README.md` 内容合并到新 `docs/specs/README.md`（同时修正过时的"人工维护"描述）。

---

## §3 .ai-memory/ 目标结构

### 3.1 目录树

```
.ai-memory/
├── README.md                          # 入口（保持，更新维护说明）
│
├── meta/                              # 元数据（保持，L1/L2 hard load）
│   ├── ai-operating-handbook.md       # L2 必读
│   ├── failure-modes.md               # L1 硬加载 N## 索引表
│   ├── docs-index.md                  # docs/ 索引（自动生成，加 module 字段）
│   ├── yn-matrices.md                 # Y/N 矩阵汇总
│   ├── yn-matrices/                   # 7 个分类决策矩阵
│   │   ├── _ai-autonomy.md
│   │   ├── _cross-layer-sync.md
│   │   ├── _honest-status.md
│   │   ├── _misc.md
│   │   ├── _refactor-dimensions.md
│   │   ├── _testing.md
│   │   └── _workflow.md
│   ├── auto-kb/                       # 4 个自动 KB（保持）
│   │   ├── agent-protocol.md
│   │   ├── api-endpoints.md
│   │   ├── error-codes.md
│   │   └── pipeline-nodes.md
│   ├── spec-evolution.md              # spec 演进史
│   └── archived-lessons.md            # 已闭环 N##（deprecated 档）
│
├── ref/                               # ★ 新建：根目录收敛 6 + 1 文件
│   ├── tech-stack.md                  # ← 移自根目录
│   ├── version-compat.md              # ← 移自根目录
│   ├── data-flow.md                   # ← 移自根目录
│   ├── cli-cheatsheet.md              # ← 移自根目录
│   ├── session-context.md             # ← 移自根目录（auto-generated）
│   ├── spec-index.md                  # ← 移自根目录
│   └── doc-health-report-schema.md    # ← 移自根目录
│
├── lessons/                           # 教训（文件名简化）
│   ├── README.md                      # 入口（更新命名规则说明 + next_n_id 计数器）
│   ├── archived-early/                # 早期归档（保持 + 接收无 N 编号文件）
│   ├── N188-conda-env-not-enforced.md          # ← 原 platform-env_2026-07-25-n188-conda-env-not-enforced.md
│   ├── N151-architecture-first.md              # ← 原 architecture_2026-07-08-n151-architecture-first-for-major-changes.md
│   ├── N184-node-observability-hard-constraint.md
│   └── ... (60+ 个 N 编号 lesson 全部改名为 N<编号>-<slug>.md)
│
├── evidence/                          # 证据（加 active/archived + cleanup）
│   ├── README.md                      # ★ 新建：说明沉淀规则
│   ├── active/                        # ★ 新建：< 30 天，待沉淀
│   │   └── 2026-07-25-logging-pipeline-hardening/  # ← 移自 evidence/
│   │       ├── problem.md
│   │       ├── solution.md
│   │       └── verification.md
│   ├── archived/                      # ★ 新建：> 30 天，已沉淀或过期
│   │   └── 2026-06/
│   │       └── ... (50+ 个旧 evidence 目录按月归档)
│   └── templates/                     # 模板（保持，无下划线）
│       ├── problem.md
│       ├── solution.md
│       └── verification.md
│
├── knowledge/                         # 领域知识（保持）
├── games/                             # 游戏特定（保持）
├── platforms/                         # 平台特定（保持）
├── summaries/                         # 主题汇总（保持）
├── checklists/                        # 检查清单（保持）
├── ops/                               # 运维旁路（保持）
├── session/                           # 会话临时（保持）
└── spec-context/                      # ★ 上下文承载体目录（本次新建，P0 已存在）
    └── 2026-07-25-docs-restructure-context.md
```

### 3.2 关键设计决策

1. **`ref/` 收敛根目录 6 + 1 文件** — 根目录只留 README.md（spec-context/ 是过程产物，独立目录不收敛到 ref/）
2. **lessons 文件名 = `N<编号>-<slug>.md`** — N 编号是唯一 ID，去掉日期和主题前缀。主题分类靠 frontmatter `topic` 字段
3. **evidence 加 active/archived 二级目录 + cleanup 启动钩子** — 30 天未沉淀的归档
4. **evidence 与 lessons 明确分工** — evidence 是过程（active），lessons 是结论（沉淀后）
5. **evidence/templates/ 保持无下划线命名**（与现有命名一致，不改为 `_templates/`）

### 3.3 lesson 文件 frontmatter schema（基于 lessons/README.md 现有 schema + 加 topic 字段）

> **注意**：本节描述的是 **lesson 文件**（如 `N188-conda-env-not-enforced.md`）的 frontmatter schema，不是 `lessons/README.md` 文件本身的 frontmatter（后者维护 `lessons_count` / `active_n_count` / `next_n_id` 等索引计数器，详见 §4.3）。

```yaml
---
date: 2026-07-25
symptom: [conda 环境未生效, 系统 Python 误用]
solution: L0 硬约束 env-hardrules.md, conda run -n gaf
related_files:
  - .trae/rules/env-hardrules.md
created_by: AI
priority: high
n_id: N188                 # L1 教训必填
level: L1                  # L0 (历史记录) / L1 (可复用经验)
topic: platform-env        # ★ 新增: 替代原文件名前缀, 用于 sync_ai_memory.py --query <topic> 检索
cross_refs: [N154, N155]   # 关联 N## 编号 (可选)
# merged_n_ids: [N154, N155]  # 家族合并主条目标记 (可选)
# l2_candidate: true           # 已沉淀到 ai-operating-handbook.md Part 2 时设 true
---
```

**字段说明**：
- 以 `lessons/README.md` 现有 schema 为基础（11 字段），新增 `topic` 字段（必填）
- **不强制加** `maintainer` / `source` / `load_when` 字段（lessons/README.md 现有 schema 没有这些字段，与 `.ai-memory/README.md §1.1 manual 模式` 8 必填字段不一致是已知问题，本次不修；P1 改名时只加 `topic`）
- `n_id` 字段已是 lessons/README.md 现有字段（L1 教训必填），本次沿用

### 3.4 failure-modes.md §Active 表格扩展

原表格 4 列：`| N## | 主题 | 硬约束 | Lesson 链接 |`

扩展为 6 列：`| N## | 主题 | 硬约束 | Lesson 链接 | trigger_count | last_triggered |`

```markdown
| N## | 主题 | 硬约束 (1 行) | Lesson 链接 | trigger_count | last_triggered |
|:---:|------|--------------|-------------|:-------------:|:--------------:|
| N188 | conda gaf 环境规则多次未生效 | 所有 Python 命令必用 `conda run -n gaf python ...`; L0 硬约束在 `.trae/rules/env-hardrules.md` | `lessons/N188-conda-env-not-enforced.md` | 5 | 2026-07-25 |
| N151 | 大修改架构视角原则 | 大修改必跑 5 步架构视角 (盘点→识别反模式→A/B/C→拒绝反模式→AI 自决) | `lessons/N151-architecture-first.md` | 12 | 2026-07-20 |
```

> 示例中"主题"和"硬约束"列内容为简化版（实际 failure-modes.md 的 N188 主题含"2026-07-25 用户反馈'问题好多次了'"后缀，硬约束含"(alwaysApply: true, 单一权威源); 任务开工必跑 gaf_init.sh; 详见 lesson N188"等附加说明）；示例只展示列结构（6 列）和 trigger_count / last_triggered 字段格式，P1 实施时以实际 failure-modes.md 表格风格为准。

**关键约束**：
- 不新增 `status` 列 — 复用 §Active / §Dormant 段位置表达 hot / cold（§Active 段 = hot，§Dormant 段 = cold）
- `gaf_init.sh` grep `^\| N[0-9]+` 校验不受影响（第一列 N## 不变，实测 grep 模式为 `^\| N[0-9]+`，含转义的 `\|` 和 `+` 量词）

---

## §4 AI 自我进化沉淀闭环

### 4.1 沉淀闭环设计

```
┌─────────────────────────────────────────────────────────────────┐
│  ① 任务执行                                                      │
│    evidence/active/<date>-<topic>/                               │
│    ↓                                                             │
│  ② 模式识别 (AI 任务收尾时扫)                                    │
│    - 同 topic / 同 symptom 在 active/ 出现 ≥ 2 次                │
│    - 或同 root_cause 在 failure-modes.md §Active 出现 ≥ 2 次     │
│    ↓                                                             │
│  ③ 主动沉淀 (AI 自动触发, 无需用户介入)                          │
│    a. 分配 N 编号 (lessons/README.md next_n_id 字段)             │
│    b. 写 lessons/N<编号>-<slug>.md (含 topic/n_id frontmatter)   │
│    c. failure-modes.md §Active 加 N## 索引行 (含 trigger_count   │
│       + last_triggered)                                          │
│    d. 原证据移到 evidence/archived/YYYY-MM/                      │
│    e. 涉及规则 → 同步沉淀到 .trae/rules/ (D3 强制同步)           │
│    ↓                                                             │
│  ④ 自我进化 (AI 会话内触发)                                      │
│    - AI 启动时扫 lessons/ 提取跨 lesson 模式                     │
│    - 高频模式 → 升级为 Y/N 矩阵 (yn-matrices/_<topic>.md)        │
│    ↓                                                             │
│  ⑤ 遗忘机制 (避免无限膨胀, GAF 启动时跑一次)                     │
│    - §Active N## last_triggered > 6 月 + 无 Y/N 矩阵引用         │
│      → 移到 archived-lessons.md (deprecated 档)                  │
│    - §Dormant (家族合并子条目) 超 6 个月 + 无新复发              │
│      + 无 Y/N 矩阵引用 → 移到 archived-lessons.md (deprecated)   │
│    - evidence/active/ > 30 天 → 移 archived/YYYY-MM/             │
│      (cleanup_old_evidence_once)                                 │
│    - evidence/archived/ > 90 天 → 删除                           │
│      (delete_archived_evidence_once)                             │
│                                                                  │
│    ★ §Dormant 段是家族合并子条目专用, 不是 Active 超时归宿      │
│      (Active 超时直接进 archived-lessons.md, 不进 §Dormant)     │
│    ★ N## 四档: Active / Dormant (家族合并子条目) /              │
│      Archived (deprecated, archived-lessons.md) /                │
│      Retired (M0.M 闭环, §Retired 段, 编号永不复用)              │
│    ★ forgetting_check_once 处理两类超时:                        │
│      ① §Active N## last_triggered > 6 月                         │
│      ② §Dormant 子条目超 6 月无新复发                            │
│      两类都移到 archived-lessons.md (deprecated 档)              │
│    ★ M0.M 闭环 N## 走 §4.4 升级路径 (→ §Retired 段),             │
│      不走遗忘机制 (编号永不复用)                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 触发机制

**重要约束**：无 Celery worker/beat，无系统级定时任务。全部改为"GAF 启动时跑一次 + AI 会话内触发"。

**触发点 1：AI 会话启动时（SKILL.md 规则触发，非定时）**
- AI 启动时扫 `evidence/active/` 同 topic 出现次数
- ≥ 2 次 → 标记 `pending_promotion`
- AI 在当前会话内处理 pending_promotion（写 lesson + 更新 failure-modes + 移 evidence 到 archived）
- 由 `gaf-orchestrator` SKILL.md §0.5 之后强制执行

**触发点 2：GAF 启动时跑一次（startup_checks，非定时）**
- `cleanup_old_evidence_once()`：active > 30 天 → 移 archived/YYYY-MM/
- `delete_archived_evidence_once()`：archived > 90 天 → 删除（避免 archived 目录无限膨胀）
- `forgetting_check_once()`：处理两类超时 N##（详见 §4.1 步骤 ⑤）
  - ① §Active 段 last_triggered > 6 月 + 无 Y/N 矩阵引用 → 移到 archived-lessons.md (deprecated 档)
  - ② §Dormant 段家族合并子条目超 6 月 + 无新复发 + 无 Y/N 矩阵引用 → 移到 archived-lessons.md (deprecated 档)
- `cleanup_old_archives_once()`：删 30 天前 tar.gz（已有，改启动时跑）
- 由启动脚本显式调用 `python manage.py run_startup_checks --all`（方案 A，详见 §5）

> ★ §Dormant 段是家族合并子条目专用，forgetting_check_once 不会把 §Active 超时 N## 写入 §Dormant（直接进 archived-lessons.md）；但 forgetting_check_once **会**处理 §Dormant 段已存在的子条目超时（移到 archived-lessons.md）。M0.M 闭环 N## 走 §4.4 升级路径（→ §Retired 段），不走遗忘机制。

**触发点 3：任务执行时写完新 evidence 后（SKILL.md 闭环步骤 5 扩展，非定时）**
- AI 在闭环步骤 5 写完新 evidence 后，扫 `evidence/active/` 同 topic 出现次数
- ≥ 2 次 → 触发 §4.1 步骤 ③ 主动沉淀（分配 N 编号 + 写 lesson + 更新 failure-modes + 移 evidence 到 archived）
- 与触发点 1 互补：触发点 1 处理历史遗留 pending_promotion，触发点 3 处理本次任务产生的新 evidence
- 由 `gaf-orchestrator` SKILL.md 闭环步骤 5 强制执行

**关键变化**：
- 异步任务不调 LLM（成本高且不可控）— 只做模式识别 + 标记 pending_promotion
- 实际 lesson 写作由 AI 会话触发（触发点 1 处理历史 pending_promotion + 触发点 3 处理本次新 evidence）
- 升级为规则走 AskUserQuestion 确认（异步任务无用户交互，必须由 AI 会话处理）

### 4.3 N 编号分配机制

```python
# .ai-memory/lessons/README.md 维护计数器
# next_n_id: N189  (当前最大 N188 + 1, P1 实测后初始化)

def allocate_n_id(topic: str, slug: str) -> str:
    """分配新 N 编号, 原子递增 next_n_id."""
    # 1. 读 lessons/README.md 的 next_n_id
    # 2. 写 lessons/N<next>-<slug>.md
    # 3. next_n_id += 1, 更新 README.md
    # 4. 返回 N<next>
```

**防并发**：用文件锁 `.cache/lessons_n_id.lock`（与 agent PID 锁同模式，相对仓库根的 .cache/ 目录）。

### 4.4 升级路径（lesson → Y/N 矩阵 → 规则 → 退役）

```
evidence (单次) → lesson (N##, 模式) → Y/N 矩阵 (主题级) → 规则 (硬约束)
                                                    ↓
                                            .trae/rules/*.md (L0/L1)
                                                    ↓
                                            M0.M 闭环 → §Retired (编号永不复用)
```

**升级条件**：
- lesson 单独存在 → L3 按需加载
- 同 topic 的 lessons ≥ 3 个 → 升级为 `yn-matrices/_<topic>.md` Y/N 矩阵
- Y/N 矩阵被频繁违反（≥ 5 次）→ 升级为 `.trae/rules/` 硬约束（如 N188 → env-hardrules.md）
- 硬约束已沉淀到 rules/skills (M0.M 闭环) → 移到 `failure-modes.md §Retired` 段（编号永不复用，详见 N181 退役机制）

### 4.5 风险与缓解

| 风险 | 缓解 |
|------|------|
| AI 误沉淀（噪声模式） | trigger_count ≥ 2 才触发；Y/N 矩阵升级需 ≥ 3 lessons |
| N 编号并发冲突 | 文件锁 + 原子递增 |
| lesson 膨胀 | 遗忘机制 + cold 移 archived-lessons.md (deprecated 档); §Active N## > 70 触发 N181 紧急评估 (spec-62) |
| 沉淀后原 evidence 丢失 | 不删除，移 archived/，保留 90 天 |
| 升级为规则过激 | Y/N 矩阵被违反 ≥ 5 次才升级；规则升级走 AskUserQuestion 确认 |

---

## §5 启动钩子 + AI 会话内触发

### 5.1 运行模型

```
┌─────────────────────────────────────────────────────────────┐
│  GAF 启动 (Django runserver / daphne)                       │
│  ↓                                                          │
│  ① 启动脚本显式调用 run_startup_checks --all (方案 A)       │
│     - cleanup_old_archives_once (删 30 天前 tar.gz)         │
│     - cleanup_old_evidence_once (移 30 天前 active→archived)│
│     - delete_archived_evidence_once (删 90 天前 archived)   │
│     - forgetting_check_once (两类超时 → archived-lessons   │
│       deprecated):                                          │
│       ① §Active last_triggered > 6 月 + 无 Y/N 矩阵引用    │
│       ② §Dormant 子条目超 6 月 + 无新复发 + 无 Y/N 矩阵引用│
│  ↓                                                          │
│  ② Django runserver 启动                                    │
│  ↓                                                          │
│  ③ GAF 正常运行 (无后台定时任务, 无 Celery worker/beat)     │
│  ↓                                                          │
│  ④ AI 会话启动 (用户在 TRAE IDE 开新对话)                   │
│     - SKILL.md §0.5 patch 文档健康 (已有)                   │
│     - SKILL.md §4.2 触发点 1 扫 evidence/active/ pending_promotion │
│     - SKILL.md §9.4 访问 docs/ 时实时查 git log 检查 stale │
│  ↓                                                          │
│  GAF 停止                                                   │
│  ↓                                                          │
│  ⑤ 无残留进程, 无 Celery worker, 无 beat, 无系统级任务      │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 实现要点

**1. startup_checks.py（新建）**

```python
# backend/gaf_core/startup_checks.py
"""GAF 启动时跑一次的检查任务 (spec §4/§5).

IDE 开发模式下 GAF 不持续运行, Celery beat 定时任务不会触发.
改为 GAF 启动时 (启动脚本显式调用) 跑一次 cleanup + forgetting.
"""

def cleanup_old_evidence_once(dry_run: bool = False):
    """active > 30 天 → 移 archived/YYYY-MM/ (spec §4.1 步骤 ⑤)."""

def delete_archived_evidence_once(dry_run: bool = False):
    """archived > 90 天 → 删除 (spec §4.1 步骤 ⑤).

    注意: 与 cleanup_old_evidence_once 区分 — 后者移 active→archived,
    本函数删 archived 超 90 天的目录, 避免无限膨胀.
    """

def forgetting_check_once(dry_run: bool = False):
    """遗忘机制: 处理两类超时 N## (spec §4.1 步骤 ⑤).

    1. §Active N## last_triggered > 6 月 + 无 Y/N 矩阵引用
       → 移到 archived-lessons.md (deprecated 档)
    2. §Dormant 段家族合并子条目超 6 月 + 无新复发 + 无 Y/N 矩阵引用
       → 移到 archived-lessons.md (deprecated 档)

    注意: §Dormant 段是家族合并子条目专用, 不是 Active 超时归宿
          (Active 超时直接进 archived-lessons.md, 不进 §Dormant).
    N## 四档: Active / Dormant (家族合并子条目) / Archived (deprecated, archived-lessons.md) /
              Retired (M0.M 闭环, §Retired 段, 编号永不复用).
    M0.M 闭环 N## 走 §4.4 升级路径 (→ §Retired 段), 不走遗忘机制.
    详见 failure-modes.md §归档流程.
    """

def cleanup_old_archives_once(dry_run: bool = False):
    """删 30 天前 tar.gz (已有 cleanup_old_archives, 改为启动时跑一次)."""

def run_startup_checks(dry_run: bool = False):
    """启动脚本显式调用, GAF 启动时跑一次."""
    cleanup_old_archives_once(dry_run)
    cleanup_old_evidence_once(dry_run)
    delete_archived_evidence_once(dry_run)
    forgetting_check_once(dry_run)
```

**2. management command（新建）**

```python
# backend/gaf_core/management/commands/run_startup_checks.py
class Command(BaseCommand):
    help = "GAF 启动时跑一次的检查任务 (spec §5)"
    
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--all', action='store_true')
    
    def handle(self, *args, **options):
        from gaf_core.startup_checks import run_startup_checks
        run_startup_checks(dry_run=options['dry_run'])
```

**3. 启动脚本显式调用（方案 A，推荐）**

```bash
# scripts/start_gaf.sh (P2 实施时新建, 若 scripts/start_backend.py 已存在则在其前面追加 run_startup_checks 调用)
conda run -n gaf python manage.py run_startup_checks --all  # 启动时跑一次
conda run -n gaf python manage.py runserver                  # 然后启动 Django
```

**P2 实施时由 §8.3 实测决定**：
- 若 `scripts/start_backend.py` 已存在 → 在其前面追加 `run_startup_checks --all` 调用
- 若 `scripts/` 下无等价启动脚本 → 新建 `scripts/start_gaf.sh` 含上述两行命令

### 5.3 关键约束

- **无 Celery worker/beat** — 不需要子进程管理
- **无定时任务** — 全部改为启动时 + 对话内触发
- **无系统级调度** — 不用注册表 / cron / 任务计划程序
- **AI 会话是主要触发点** — SKILL.md 规则强制执行

---

## §6 迁移阶段划分

分 P0/P1/P2 三阶段。每阶段独立可验证、可回退。

### 6.1 P0：双线索建立 + spec 目录合并（最大收益）

**目标**：人类按业务/架构找文档，spec 目录单一化。

**改动范围**：

0. **准备阶段（P0 之前）**：建 `docs/specs/active/` 目录（含 `.gitkeep`），本 spec 文档直接放新路径
1. 新建 `docs/business/` 9 模块子目录 + `docs/architecture/` 五层子目录（含空目录 `.gitkeep`）
2. `git mv` 迁移 `docs/general/design/` 18 个文档到双线索结构
3. `git mv` 迁移 `docs/general/analysis/` 5 个对比文档到 `docs/analysis/`
4. `git mv` 迁移 `docs/general/troubleshooting/` 到 `docs/business/tasks/`
5. `git mv` 迁移 `docs/general/tech-debt/` 到 `docs/tech-debt/`
6. `git mv` 迁移 `docs/general/health-checks/` 到 `docs/health/`
7. `git mv` 迁移 `docs/general/specs/` + `docs/specs/dependency-graph.md` + `docs/superpowers/specs/` 合并到 `docs/specs/{active,archived}/`
8. `git mv` 迁移 `docs/superpowers/plans/` 到 `docs/plans/`
9. `git mv` 迁移 `docs/governance/dashboard.md` 到 `docs/business/ops/governance-dashboard.md`
10. `git mv` 迁移 `docs/general/` 顶层 3 文件到 `docs/` 顶层
11. 删除空目录（`docs/general/`、`docs/superpowers/`、`docs/governance/`）
12. 新建 `docs/README.md` + `docs/business/README.md` + `docs/architecture/README.md` + `docs/specs/README.md`（合并自 `general/specs/README.md`，修正过时描述）
13. 更新 `sync_docs_index.py` 适配新结构 + 加 `module` 字段生成 + 加 `applies_to_code_paths` 字段初始化 + 加 `maintainer: ai` 字段初始化（§9.1）
14. 重跑 `sync_docs_index.py` 生成新 `docs-index.md` + 初始化文档 frontmatter 的 `doc_last_updated` 字段（从 git log 获取文档最近修改日期）（§9.1）

**迁移映射表**（关键文档，完整列表见 [承载体文档 §6.1](../../../.ai-memory/spec-context/2026-07-25-docs-restructure-context.md#p0-双线索建立--spec-目录合并最大收益)）：

| 原路径 | 新路径 | module 字段 |
|--------|--------|-------------|
| `docs/general/design/architecture-overview.md` | `docs/architecture/overview.md` | `architecture` |
| `docs/general/analysis/GAF-optimal-solution.md` | `docs/architecture/optimal-solution.md` | `architecture` |
| `docs/general/design/gaf-features-overview.md` | `docs/architecture/features-overview.md` | `architecture` |
| `docs/general/design/custom-task-design.md` + `docs/general/design/pipeline-authoring-guide.md` | `docs/business/tasks/pipeline-design.md`（P0 实施时实测两份内容：重叠则合并，否则分别命名为 `pipeline-design.md` + `pipeline-authoring-guide.md`） | `business.tasks` |
| `docs/general/design/debug-timeline-design.md` | `docs/business/tasks/timeline-design.md` | `business.tasks` |
| `docs/general/design/interface-recovery-design.md` | `docs/business/tasks/recovery-design.md` | `business.tasks` |
| `docs/general/design/task-cancel-design.md` | `docs/business/tasks/cancel-design.md` | `business.tasks` |
| `docs/general/design/task-execution-reality.md` | `docs/business/tasks/execution-reality.md` | `business.tasks` |
| `docs/general/design/monitor-design.md` | `docs/business/ops/monitor-design.md` | `business.ops` |
| `docs/general/design/llm-integration-design.md` | `docs/business/ai/llm-integration.md` | `business.ai` |
| `docs/general/design/deployment-design.md` | `docs/architecture/desktop/deployment-design.md` | `architecture.desktop` |
| `docs/general/design/concurrency-design.md` | `docs/architecture/cross-cutting/concurrency-design.md` | `architecture.cross-cutting` |
| `docs/general/design/pre-commit-stages.md` | `docs/architecture/cross-cutting/pre-commit-stages.md` | `architecture.cross-cutting` |
| `docs/general/design/dpi-coordinate-system.md` | `docs/business/devices/dpi-coordinate.md` | `business.devices` |
| `docs/general/design/screenshot-optimization.md` | `docs/business/devices/screenshot-optimization.md` | `business.devices` |
| `docs/general/design/resource-pack-design.md` | `docs/business/resources/resource-pack-design.md` | `business.resources` |
| `docs/general/design/input-mode-and-window-wait-design.md` | `docs/business/ai/input-mode-window-wait.md` | `business.ai` |
| `docs/general/design/debug-mode-design.md` | `docs/business/tasks/debug-mode-design.md` | `business.tasks` |
| `docs/general/troubleshooting/task-execution-troubleshooting.md` | `docs/business/tasks/troubleshooting.md` | `business.tasks` |
| `docs/superpowers/specs/2026-07-25-logging-pipeline-hardening-design.md` | `docs/specs/active/2026-07-25-logging-pipeline-hardening.md` | `specs.active` |
| `docs/superpowers/plans/2026-07-25-logging-and-pipeline-hardening.md` | `docs/plans/2026-07-25-logging-and-pipeline-hardening.md` | `plans` |

**Commit 信息**：

```
refactor(docs): P0 双线索结构 + spec 目录合并 (spec §6.1)

- 新建 docs/business/ (9 模块) + docs/architecture/ (五层 + 横切)
- 迁移 18 份 design + 5 份 analysis + 1 份 troubleshooting 到双线索
- 合并 4 个 spec 目录为 docs/specs/{active,archived}/
- docs/superpowers/plans/ 提升到 docs/plans/
- 删除 docs/general/ / docs/superpowers/ / docs/governance/
- 新建 docs/README.md (双线索导航入口)
- sync_docs_index.py 适配 + 加 module/applies_to_code_paths/doc_last_updated 字段生成
- 重跑生成新 docs-index.md
```

### 6.2 P1：lessons 改名 + evidence active/archived + 自我进化闭环

**目标**：lessons 文件名简化 + evidence 防堆积 + AI 自我进化沉淀闭环。

**改动范围**：

1. `.ai-memory/lessons/` 60+ 文件改名 `N<编号>-<slug>.md`
2. 无 N 编号文件（如 `circular_mode_no_continue_prompt.md` + `workflow_spec_concentration_2026-07-20.md`）移到 `archived-early/`（保留历史，不参与 sync 索引；archived-early/ 下已有 6 个早期归档文件，本次再迁入 2 个无 N 编号文件）
3. 更新 lessons frontmatter 加 `topic` 字段（基于现有 schema，不强制加 maintainer/source/load_when）
4. 更新 `failure-modes.md` §Active 段表格加 `trigger_count` + `last_triggered` 两列（不加 status 列）
   - **P5 治本约束**：加列不加行，`p5_max_lines` (当前 170) 不受影响；每行长度增加 ~30 字符，`promote_lessons.py --enforce-limits` 不检查列宽
   - **现有 N## 四档分布**：Active (~65 行) / Dormant (家族合并子条目, ~10 行) / Retired (M0.M 闭环, ~7 行) / Archived (deprecated, 在 archived-lessons.md)
5. 新建 `.ai-memory/evidence/active/` + `.ai-memory/evidence/archived/`
6. `git mv` 现有 50+ evidence 目录到 `archived/YYYY-MM/`
7. 新建 `.ai-memory/evidence/README.md`（沉淀规则说明）
8. 更新 `.ai-memory/lessons/README.md`：① frontmatter 加 `next_n_id` 计数器字段（与现有 5 个计数字段 `lessons_count` / `active_n_count` / `retired_n_count` / `archived_n_count` / `dormant_n_count` 并存；初始值 = §8.3 实测最大 N 编号 + 1，当前预期 N189）；② 文档正文 frontmatter schema 表格加 `topic` 字段行（基于 §3.3 lesson 文件 frontmatter schema）
9. 实现 `backend/gaf_core/startup_checks.py`（4 个清理函数 + run_startup_checks：cleanup_old_evidence_once / delete_archived_evidence_once / forgetting_check_once / cleanup_old_archives_once，详见 §5.2）
10. 实现 `backend/gaf_core/management/commands/run_startup_checks.py`
11. 更新 `gaf-orchestrator` SKILL.md：§0.5 之后加 §4.2 触发点 1 扫 evidence/active/ pending_promotion 规则
12. 更新 `gaf-orchestrator` SKILL.md：闭环步骤 5（执行）扩展 §4.2 触发点 3 沉淀规则
13. 单元测试 4 项

**lessons 改名映射表**（示例）：

| 原文件名 | 新文件名 | topic | n_id |
|---------|---------|-------|------|
| `platform-env_2026-07-25-n188-conda-env-not-enforced.md` | `N188-conda-env-not-enforced.md` | `platform-env` | `N188` |
| `architecture_2026-07-08-n151-architecture-first-for-major-changes.md` | `N151-architecture-first.md` | `architecture` | `N151` |
| `workflow_2026-07-22-n184-node-observability-hard-constraint.md` | `N184-node-observability-hard-constraint.md` | `workflow` | `N184` |
| `agent-impl_2026-07-12-n158-langgraph-agent-implementation.md` | `N158-langgraph-agent-implementation.md` | `agent-impl` | `N158` |
| `testing_2026-06-17-n118-m2a-43-tests.md` | `N118-m2a-43-tests.md` | `testing` | `N118` |
| `circular_mode_no_continue_prompt.md` | （移到 `archived-early/`，不改名） | — | — |
| `workflow_spec_concentration_2026-07-20.md` | （移到 `archived-early/`，不改名） | — | — |

**无 N 编号文件迁移规则**：所有无 N 编号的 lessons 文件（不只 `circular_mode_no_continue_prompt.md`）一并迁移到 `archived-early/`，保留原名不参与 sync_ai_memory 索引。P1 实施时需 grep 找出全部无 N 编号文件清单。

### 6.3 P2：根目录收敛 + 引用同步 hook

**目标**：`.ai-memory/` 根目录清爽 + 100+ 路径引用同步 + 防回退 hook + 扩展文档同步检查 hook。

**改动范围**：

1. `.ai-memory/` 根目录 6 文件 `git mv` 到 `.ai-memory/ref/`
2. `git mv` `.ai-memory/doc-health-report-schema.md` 到 `.ai-memory/ref/`
3. 更新所有引用 `.ai-memory/tech-stack.md` 等的文件指向 `ref/`：
   - `.trae/skills/gaf-orchestrator/SKILL.md` L2 hard-load 段 + L3 按需加载段
   - `.ai-memory/README.md` §0.1 加载顺序表
   - `.ai-memory/meta/ai-operating-handbook.md` Part 1 L2/L3 段
   - `.trae/rules/project_rules.md` §6.1 (L659 引用 tech-stack.md)
4. 新增 pre-commit hook `scripts/hooks/check_doc_path_drift.py`（§7 旧路径零兼容），加入 `gaf_governance_batch.py` CHECKS 列表第 13 项
5. 扩展现有 `scripts/hooks/check_doc_code_sync.py` + `scripts/hooks/doc_sync_rules.py`（§9.3 文档同步检查，不新增 hook）
6. 更新 `sync_ai_memory.py` 适配 `ref/` 新路径
7. 更新 `gaf-orchestrator` SKILL.md：闭环步骤 6（提交）扩展 §9.2 文档同步检查 + §9.5 stale 加载提醒规则
8. 全量 grep + 更新 100+ 文件路径引用

---

## §7 旧路径零兼容（彻底迁移）

### 7.1 用户决策

旧路径不保留、不软链、不重定向。迁移完成后旧路径全部消失，引用旧路径的代码/文档**必须**更新为新路径，否则 commit 被 hook 拒绝。

### 7.2 不做的事

| 反模式 | 不做的理由 |
|--------|-----------|
| ~~旧路径留 README.md 重定向~~ | 双重存在期 + AI 不知该读哪个 |
| ~~旧路径软链到新路径~~ | 软链在 Windows 上需管理员权限 + 跨平台不一致 |
| ~~保留旧路径 N 天再删~~ | 永远有人不更新引用，N 天后还是有引用 |
| ~~回退到旧结构~~ | 用户已确认"都用新的"，回退路径不需要 |

### 7.3 check_doc_path_drift.py 永久约束

```python
# scripts/hooks/check_doc_path_drift.py
"""永久约束 (spec §7): 禁止以下旧路径出现在任何 .md / .py / .yaml 文件中.

与现有 check_path_consistency.py (N107) 职责区分:
- check_path_consistency.py: 检查 inline path 构造 (Path("foo") / "bar.json")
- check_doc_path_drift.py:    检查旧路径字符串回退 (如 "docs/general/")

两者不合并, 都加入 gaf_governance_batch.py CHECKS 列表.
"""

FORBIDDEN_PATTERNS = [
    # P0 旧路径
    r'docs/general/',
    r'docs/superpowers/',
    r'docs/governance/',
    r'docs/specs/dependency-graph\.md',
    # P1 旧路径 (负向先行断言排除合法子目录)
    r'\.ai-memory/evidence/(?!active/|archived/|templates/|README\.md)[^/]+/',
    r'\.ai-memory/lessons/(?!archived-early/)[^/]+\d{4}-\d{2}-\d{2}-n\d+',
    # P2 旧路径
    r'\.ai-memory/tech-stack\.md',
    r'\.ai-memory/version-compat\.md',
    r'\.ai-memory/data-flow\.md',
    r'\.ai-memory/cli-cheatsheet\.md',
    r'\.ai-memory/session-context\.md',
    r'\.ai-memory/spec-index\.md',
    r'\.ai-memory/doc-health-report-schema\.md',
]
```

**注册方式**：加入 `scripts/hooks/gaf_governance_batch.py` 的 CHECKS 列表第 13 项（无需在 `.pre-commit-config.yaml` 新增 hook，已合并到 `gaf-governance-batch`）。

```python
# scripts/hooks/gaf_governance_batch.py CHECKS 列表追加:
("hooks.check_doc_path_drift", "main", [], "doc-path-drift"),
```

### 7.4 特殊豁免（白名单）

- `.git/` — 历史记录不可改
- `.ai-memory/spec-context/` — 上下文承载体目录（本次新建）
- `.ai-memory/lessons/archived-early/` — 早期归档文件 + 无 N 编号文件（如 `circular_mode_no_continue_prompt.md`）保留原名
- `.ai-memory/evidence/archived/` — 归档 evidence 保留原名
- `.ai-memory/evidence/active/` — 活跃 evidence
- `.ai-memory/evidence/templates/` — evidence 模板（无下划线，与现有命名一致）

### 7.5 引用更新清单（P0/P1/P2 全量）

**P0 阶段**（约 50+ 处）：

| 引用文件 | 旧引用 | 新引用 |
|---------|--------|--------|
| `.trae/rules/project_rules.md` §0 | `docs/general/analysis/GAF-optimal-solution.md` | `docs/architecture/optimal-solution.md` |
| `.trae/rules/project_rules.md` §0 | `docs/general/design/gaf-features-overview.md` | `docs/architecture/features-overview.md` |
| `.trae/rules/project_rules.md` §0 | `docs/general/design/architecture-overview.md` | `docs/architecture/overview.md` |
| `.trae/skills/gaf-orchestrator/SKILL.md` | `docs/general/specs/dependency-graph.md` | `docs/specs/dependency-graph.md` |
| `.ai-memory/meta/docs-index.md` | 全部 36 条 `docs/general/...` | 全部更新为新路径 |
| `.ai-memory/meta/ai-operating-handbook.md` | `docs/general/standards/` | `docs/standards/`（保持顶层） |
| `.ai-memory/evidence/2026-07-25-logging-pipeline-hardening-spec/solution.md` | `docs/superpowers/specs/...` | `docs/specs/active/...` |

**P1 阶段**（约 30+ 处）：

| 引用文件 | 旧引用 | 新引用 |
|---------|--------|--------|
| `.ai-memory/meta/failure-modes.md` §Active | `lessons/platform-env_2026-07-25-n188-...md` | `lessons/N188-conda-env-not-enforced.md` |
| `.ai-memory/meta/archived-lessons.md` | 旧文件名 | 新文件名 |
| `.ai-memory/lessons/README.md` | 旧文件名 | 新文件名 + next_n_id 计数器 + frontmatter schema 加 topic |
| `.ai-memory/meta/yn-matrices/_*.md` | 旧 lesson 引用 | 新 lesson 引用 |

**P2 阶段**（约 20+ 处）：

| 引用文件 | 旧引用 | 新引用 |
|---------|--------|--------|
| `.trae/rules/project_rules.md` §6.1 (L659) | `.ai-memory/tech-stack.md` | `.ai-memory/ref/tech-stack.md` |
| `.trae/skills/gaf-orchestrator/SKILL.md` L2 hard-load | `.ai-memory/tech-stack.md` | `.ai-memory/ref/tech-stack.md` |
| `.trae/skills/gaf-orchestrator/SKILL.md` L3 按需 | `.ai-memory/version-compat.md` | `.ai-memory/ref/version-compat.md` |
| `.ai-memory/meta/ai-operating-handbook.md` Part 1 | `.ai-memory/data-flow.md` | `.ai-memory/ref/data-flow.md` |
| `.ai-memory/README.md` §0.1 | 根目录 6 文件 | `ref/` 下 6 + 1 文件 |
| `scripts/hooks/doc_sync_rules.py` R3 | `docs/general/design/` | `docs/architecture/` + `docs/business/`（双线索） |
| `scripts/hooks/doc_sync_rules.py` R7 | `docs/general/design/deployment-design.md` | `docs/architecture/desktop/deployment-design.md` |
| `scripts/bootstrap/sync_session_context.py` L44 | `AI_MEMORY / "session-context.md"` (硬编码) | `AI_MEMORY / "ref" / "session-context.md"` |
| `scripts/governance/sync_spec_index.py` L47/L215 | `repo_root / ".ai-memory" / "spec-index.md"` (硬编码) | `repo_root / ".ai-memory" / "ref" / "spec-index.md"` |
| `scripts/hooks/check_spec_id_collision.py` L166 | `.ai-memory/spec-index.md` (错误消息) | `.ai-memory/ref/spec-index.md` |
| `scripts/governance/spec_dependency_graph.py` L396 | `.ai-memory/spec-index.md` (生成内容) | `.ai-memory/ref/spec-index.md` |
| `scripts/README.md` L64 | `.ai-memory/session-context.md` (脚本说明) | `.ai-memory/ref/session-context.md` |

> **说明**：`docs/general/specs/dependency-graph.md` + `docs/specs/dependency-graph.md` 第 105 行的 `.ai-memory/spec-index.md` 引用由 `sync_spec_index.py` 自动生成，P2 改完 sync_spec_index.py 后重跑即可，不需手动更新。`doc-health-report-schema.md` 当前无源代码硬编码引用（仅 frontmatter `source` 字段自引用），P2 git mv 后 grep 验证 0 失效链接即可。

### 7.6 脚本辅助更新

```bash
conda run -n gaf python scripts/migrate_docs_paths.py --stage p0 --dry-run
conda run -n gaf python scripts/migrate_docs_paths.py --stage p0 --apply
```

---

## §8 风险评估 + 验证策略

### 8.1 风险评估

| 等级 | 风险 | 缓解措施 |
|------|------|---------|
| **高** | 批量 git mv 引用断裂（50+ 文档移动，100+ 引用更新） | P0/P1/P2 每阶段跑 `migrate_docs_paths.py --dry-run` 先看影响面；pre-commit hook 兜底 |
| **高** | lessons 改名导致 failure-modes.md 索引失效（60+ 链接） | P1 改名脚本和 failure-modes.md 更新脚本同 commit；改名后立即 grep 验证 0 失效链接 |
| **中** | GAF 启动时跑 cleanup 可能让启动变慢 | startup_checks 同步跑但函数本身轻量（< 2s）；不阻塞 Django ready |
| **中** | AI 会话启动扫 pending_promotion 可能让首次响应变慢 | 限制扫描范围（只扫 evidence/active/ 目录名），< 1 秒完成 |
| **中** | frontmatter 不一致（60+ lessons 逐个加 topic） | 写脚本 `migrate_lessons_frontmatter.py` 批量加，从原文件名解析 topic 和 n_id |
| **中** | sync_docs_index.py 重构 bug 影响所有 AI 加载 | P0 改完后立即跑 `sync_docs_index.py` + 人工抽查 5 份 docs-index.md 条目 |
| **中** | pre-commit hook 误报（正则命中合法引用） | §7.4 白名单豁免清单；hook 加白名单文件 `.doc-path-whitelist.txt` |
| **低** | 空目录 .gitkeep 容易忘 | P0 改动列表明确"每个空目录加 .gitkeep" |
| **低** | P0 commit 粒度大触发 B2 证据检查 | P0 实施时按 N151 流程生成 B2 证据，`scripts/check_big_change.py --staged --acknowledge` |

### 8.2 验证策略

**P0 验证**：

```bash
# 1. 文件数对比（迁移前后总数一致）
conda run -n gaf python -c "import os; print(sum(1 for _ in os.walk('docs') for f in _[2] if f.endswith('.md')))"

# 2. git mv 历史保留
git log --follow docs/architecture/overview.md

# 3. sync_docs_index 无报错
conda run -n gaf python scripts/bootstrap/sync_docs_index.py

# 4. 旧路径零残留
# (用 Grep 工具替代 grep -rn)
# 搜索: docs/general/ | docs/superpowers/ | docs/governance/ 在 .md/.py/.yaml 文件中

# 5. 抽查 5 份 docs-index.md 条目 module 字段
# 用 Grep 工具搜索 "module:" in .ai-memory/meta/docs-index.md
```

**P1 验证**：

```bash
# 1. lessons 改名完成
# 用 Glob 工具列出 .ai-memory/lessons/N*.md 文件数 (应 ≥ 60)

# 2. evidence active/archived 结构
# 用 LS 工具列出 .ai-memory/evidence/active/ 和 archived/

# 3. failure-modes.md 链接无失效（用脚本验证）

# 4. 单元测试
conda run -n gaf python -m pytest backend/gaf_core/tests/test_self_evolution.py -v

# 5. dry-run
conda run -n gaf python manage.py run_startup_checks --all --dry-run
```

**P2 验证**：

```bash
# 1. 根目录收敛
# 用 LS 工具列出 .ai-memory/ 根目录, 应只 README.md + spec-context/

# 2. pre-commit hook (合并到 gaf-governance-batch, 不单独注册)
pre-commit run gaf-governance-batch --all-files  # 含 check_doc_path_drift (新增) + check_doc_code_sync (扩展)

# 3. 旧路径零残留（含 .ai-memory 根目录文件）
# 用 Grep 工具搜索 .ai-memory/tech-stack.md | .ai-memory/data-flow.md | .ai-memory/cli-cheatsheet.md

# 4. 全量回归
conda run -n gaf python -m pytest backend/ -x
conda run -n gaf python -m pytest agent/tests/ -x
```

### 8.3 实施前必做的实测确认

P0 启动前先跑实测，确认假设成立：

```bash
# 1. 确认 docs/general/design/ 实际文件清单
# 用 LS 工具列出 docs/general/design/

# 2. 确认 data-flow.md 是否存在
# 用 Glob 工具查找 docs/general/design/data-flow.md

# 3. 确认 scripts/start_backend.py 或等价启动脚本是否存在
# 用 LS 工具列出 scripts/

# 4. 确认现有 lessons 最大 N 编号
# 用 Grep 工具在 .ai-memory/lessons/ 搜索 n\d+ 取最大值

# 5. 确认 evidence 目录数量
# 用 LS 工具列出 .ai-memory/evidence/

# 6. 确认 sync_docs_index.py 现状
# 用 Glob 工具查找 scripts/bootstrap/sync_docs_index.py
```

---

## §9 文档与代码同步更新机制

### 9.1 文档与代码的映射

docs/ 下每份文档 frontmatter 新增字段：

```yaml
---
maintainer: ai
applies_to_code_paths:              # ★ 该文档适用的代码路径 glob
  - backend/tasks/**
  - agent/src/nodes/tasks/**
  - frontend/src/views/tasks/**
doc_last_updated: 2026-07-25        # ★ 文档最近更新日期 (AI 改文档时手动更新, hook 强制)
---
```

**module → 代码路径映射表**（`docs-index.md` 维护，sync 脚本自动生成）：

| module | applies_to_code_paths | 说明 |
|--------|----------------------|------|
| `business.tasks` | `backend/tasks/**` + `agent/src/nodes/tasks/**` + `frontend/src/views/tasks/**` | 任务模块 |
| `business.devices` | `backend/agents/**` + `agent/src/platforms/**` | 设备模块 |
| `business.resources` | `backend/resources/**` | 资源模块 |
| `business.accounts` | `backend/accounts/**` | 账户模块 |
| `business.ops` | `backend/monitors/**` + `backend/notifications/**` | 运维模块 |
| `business.ai` | `backend/gaf_ai/**` + `backend/skills/**` | AI 模块 |
| `business.workspace` | `[]` | 待新文档填入，暂无对应代码路径 |
| `business.game-profile` | `backend/gamestate/**` + `frontend/src/pages/GameProfiles/**` | 游戏档案模块（P0 实测确认：后端 gamestate app 含 GameProfile 模型/views/serializers/migrations；前端 pages/GameProfiles/ 含 index.tsx/DetailPage.tsx/components/） |
| `business.system` | `[]` | 待新文档填入，暂无对应代码路径 |
| `architecture.backend` | `backend/config/**` + `backend/gaf_core/**` | 后端层 |
| `architecture.agent` | `agent/src/**` | Agent 层 |
| `architecture.frontend` | `frontend/src/**` | 前端层 |
| `architecture.desktop` | `desktop/**` | Desktop 层（P0 实测确认路径） |
| `architecture.cross-cutting` | `backend/protocol/**` + `backend/tracing/**` | 横切关注点 |

> **空数组标记**：`applies_to_code_paths: []` 标记暂无对应代码路径的模块（与 §9.8 风险与缓解"docs-index.md 加 applies_to_code_paths: [] 标记未配文档"对齐）。
>
> **P0 实测已完成**（2026-07-26，见 plan §2.2）：`business.game-profile` 实测路径 `backend/gamestate/**` + `frontend/src/pages/GameProfiles/**`（与 spec 原假设 `backend/game_profiles/**` + `frontend/src/views/game-profile/**` 不一致，已修正本表）；`architecture.desktop` 实测路径 `desktop/**`（与 spec 假设一致，Electron 应用结构 src/main + src/preload）。

### 9.2 任务收尾时同步检查（接入闭环步骤 6「提交」）

在 `gaf-orchestrator` SKILL.md 的"闭环步骤 6（提交）"加文档同步检查：

```
□ 扫描本次 git diff --name-only 涉及的代码路径
□ 反查 docs-index.md 找到对应文档（通过 applies_to_code_paths 匹配）
□ 检查文档内容是否需要更新:
   - 新增/删除字段 → 更新数据模型章节
   - 改接口签名 → 更新 API 章节
   - 改流程 → 更新流程图/时序图
□ 通过 AskUserQuestion 询问用户是否需要更新文档
□ 用户确认后 → AI 更新文档 + 更新 doc_last_updated 字段
□ 用户拒绝 → 标记 sync_status: drifted（下次加载时提醒）
```

**关键约束**：AI 不能自作主张改文档，必须经用户确认（避免乱改）。

### 9.3 pre-commit hook 强制（扩展现有 check_doc_code_sync.py）

**重要**：不新建 `check_doc_sync.py`。现有 `scripts/hooks/check_doc_code_sync.py` (TD-325/spec-87) 已实现代码-文档因果绑定检查，复用其 `[skip-doc-sync]` 跳过机制和 hard/warn/info 三级分级。本节只扩展规则表 `scripts/hooks/doc_sync_rules.py`，新增对 `doc_last_updated` 字段的强制检查。

**扩展点 1**：`doc_sync_rules.py` RULES 列表追加 R8 规则

```python
# scripts/hooks/doc_sync_rules.py 追加:
DocSyncRule(
    id="R8",
    description="docs/ 文档内容变更 → doc_last_updated 字段必须同步更新",
    trigger_pattern="docs/**/*.md",
    content_keywords=(),  # 不扫内容, 任何 docs/*.md 改动都触发
    required_docs=(),     # 自身即文档, 无外部 required_docs
    severity="hard",
    status_filter="M",    # ★ 只对 modified 触发; A(新建)/D(删除)/R(重命名) 不触发 (新建时 doc_last_updated 是初始值, 不需要"更新")
),
```

**扩展点 2**：P0 后更新现有 R3/R7 路径

```python
# R3: 新增 backend app 目录 → 设计文档
# 旧 required_docs: ("docs/general/design/",)
# 新 required_docs: ("docs/architecture/", "docs/business/")  # 双线索目录
DocSyncRule(
    id="R3",
    description="新增 backend app 目录 → 设计文档 (P0 后双线索目录)",
    trigger_pattern="backend/*/apps.py",
    content_keywords=(),
    required_docs=("docs/architecture/", "docs/business/"),
    severity="warn",
    status_filter="A",
),

# R7: backend settings 变更 → 部署设计文档
# 旧 required_docs: ("docs/general/design/deployment-design.md",)
# 新 required_docs: ("docs/architecture/desktop/deployment-design.md",)
DocSyncRule(
    id="R7",
    description="backend settings 变更 → 部署设计文档 (P0 后新路径)",
    trigger_pattern="backend/config/settings/*.py",
    content_keywords=("INSTALLED_APPS", "MIDDLEWARE", "CELERY", "DATABASES", "CACHES", "REST_FRAMEWORK"),
    required_docs=("docs/architecture/desktop/deployment-design.md",),
    severity="warn",
),
```

**扩展点 3**：`check_doc_code_sync.py` 主逻辑加 `doc_last_updated` 字段检查

```python
# scripts/hooks/check_doc_code_sync.py 追加逻辑:
# 当 staged docs/*.md 文件被修改 (status=M) 但 frontmatter 的
# doc_last_updated 字段未更新 → exit 1 (hard fail)
# 实现方式: git diff --cached -U0 <file> 扫 "+doc_last_updated:" 行
```

**Hook 行为分级**（复用现有机制）：
- **hard**：docs/ 文档内容改了但 `doc_last_updated` 字段没更新 → 阻塞 commit（可用 `[skip-doc-sync]` 跳过）
- **warn**：代码改动但对应文档没动 → 打印警告 + 记录到 `.cache/doc_sync_skips.json`
- **info**：新增 spec 文件 → sync_spec_index 自动同步

### 9.4 AI 访问文档时即时检查（接入闭环步骤 4「搜索 L3 硬约束」）

**删除**：原设计的 `check_doc_staleness` Celery 定时任务（IDE 开发模式不可行）

**改为**：AI 会话内实时计算，不依赖后台进程

```
当 AI 通过 docs-index.md 查询文档时 (闭环步骤 4 搜索 L3):
1. 读文档 frontmatter 的 applies_to_code_paths
2. 调用 git log -1 --format="%ci" -- <code_paths> 查代码最近改动日期
3. 比对 code_last_changed vs doc_last_updated
4. code_last_changed > doc_last_updated → 标记 stale, 加载时附提醒
5. 检查结果在会话内缓存（不持久化到 docs-index.md）
```

**实现位置**：`gaf-orchestrator` SKILL.md 加规则，AI 用 RunCommand 跑 git log（每次访问文档时一次，成本可接受）。

### 9.5 AI 加载 stale 文档时的提醒

`gaf-orchestrator` SKILL.md 加规则：

```
当 AI 通过 docs-index.md 查询文档时:
- sync_status: fresh → 正常加载
- sync_status: stale → 加载时附提醒 "此文档可能过时, 代码最近改动于 <date>, 请交叉验证"
- sync_status: drifted → 加载时附提醒 "此文档与代码不同步, 用户曾拒绝更新, 内容可能不准"
```

### 9.6 frontmatter 字段维护责任

| 字段 | 维护方 | 何时更新 |
|------|--------|---------|
| `maintainer` | `sync_docs_index.py` 初始化为 `ai` | P0 重构时初始化（所有 docs/ 文档都是 AI 维护，固定为 `ai`） |
| `applies_to_code_paths` | `sync_docs_index.py` 自动生成 | P0 重构时初始化 + 新增文档时 |
| `doc_last_updated` | AI 改文档时手动更新（hook 强制） | 每次文档内容变更 |
| `code_last_changed` | **不存储**，AI 访问时实时查 git log | — |
| `sync_status` | **不存储**，AI 访问时实时计算 | — |

**简化**：docs-index.md 只存 `maintainer` + `applies_to_code_paths` + `doc_last_updated`，`code_last_changed` 和 `sync_status` 运行时计算，避免缓存失效问题。

### 9.7 与 §4 自我进化的关系

| 维度 | §4 自我进化 | §9 文档同步 |
|------|------------|-------------|
| 处理对象 | `.ai-memory/` 过程产物 | `docs/` 稳定知识库 |
| 触发时机 | AI 会话启动 + GAF 启动 | 代码改动 + 用户确认 + AI 访问文档时实时检查 |
| 自动化程度 | AI 会话内触发沉淀 | 用户确认后 AI 改文档；AI 访问时实时检查 stale |
| 失败兜底 | 遗忘清理（GAF 启动时跑） | stale 标记 + 加载提醒 |

### 9.8 风险与缓解

| 风险 | 缓解 |
|------|------|
| 误报（改了代码但文档不需要更新） | Hook 只警告不阻塞；AI 收尾走 AskUserQuestion |
| `applies_to_code_paths` 配置不全 | P0 初始覆盖主要 app；漏的靠 stale 检测兜底；新增 Django app 时强制配 |
| 文档频繁改动影响 git history | 只更新 `doc_last_updated` 字段即可，不必大改文档 |
| AI 自作主张乱改文档 | 必须经 AskUserQuestion 用户确认 |
| stale 检测漏报（代码路径未配） | docs-index.md 加 `applies_to_code_paths: []` 标记未配文档，定期人工补 |

### 9.9 落地阶段

§9 不单独成阶段，融入 P0/P2：

| 阶段 | §9 落地点 |
|------|----------|
| P0 | `sync_docs_index.py` 加 `applies_to_code_paths` 字段生成；docs-index.md 加 `doc_last_updated` 字段；同步更新 `doc_sync_rules.py` R3/R7 路径（§7.5） |
| P1 | 无需改动（§9 不涉及 lessons/evidence） |
| P2 | 扩展 `doc_sync_rules.py` 加 R8 规则 + 扩展 `check_doc_code_sync.py` 主逻辑加 `doc_last_updated` 字段检查；更新 `gaf-orchestrator` SKILL.md 加文档同步检查项 + stale 加载提醒规则（无新增 hook） |

---

## §10 与现有 AI 工作流对齐

### 10.1 关键设计决策（对齐结果汇总）

经九轮对齐检查（详见承载体文档 §10/§11/§12 + 第四轮实地验证 + 第五轮深度对齐 + 第六轮 failure-modes.md 实地验证 + 第七轮跨章节一致性验证 + 第八轮 13 项跨章节一致性补检 + 第九轮 forgetting_check_once 一致性 + project_rules.md §6.1 实测修正），最终设计决策：

1. **`ref/` 移动需同步更新 5 处文档引用 + 5 处源代码硬编码引用**：
   - **5 处文档引用**（第六轮已确认，第九轮修正 §1.1 → §6.1）：orchestrator SKILL.md L2 hard-load 段 + L3 按需加载段 + README.md §0.1 + handbook Part 1 L2/L3 段 + project_rules.md §6.1 (L659 引用 tech-stack.md)
   - **5 处源代码硬编码引用**（第七轮新发现，详见 §7.5 P2 阶段）：sync_session_context.py L44 + sync_spec_index.py L47/L215 + check_spec_id_collision.py L166 + spec_dependency_graph.py L396 + scripts/README.md L64
2. **`evidence/templates/` 保持无下划线命名**（与现有命名一致）
3. **failure-modes.md 不新增 `status` 字段**，复用现有 §Active/§Dormant 段位置表达 hot/cold
4. **`trigger_count` + `last_triggered` 加在 §Active 段表格右侧**，gaf_init.sh grep `^\| N[0-9]+` 不受影响（第一列 N## 不变，实测 grep 模式为 `^\| N[0-9]+`，含转义的 `\|` 和 `+` 量词）
5. **§4 与 §0.5 互补**：§0.5 先 patch 文档健康，§4 后扫 pending_promotion
6. **`applies_to_code_paths` 是新字段**，与现有 `applies_to` 不同，两个字段都保留
7. **§9.2 接入闭环步骤 6「提交」**（不新增 step）
8. **§9.4 接入闭环步骤 4「搜索 L3 硬约束」**（不新增 step）
9. **§5 startup_checks 用 management command + 启动脚本显式调用**（方案 A，不在 AppConfig.ready() 里自动跑）
10. **P1 更新 lessons/README.md frontmatter schema 表格**，加 `topic` 字段（基于现有 schema，不强制加 maintainer/source/load_when）
11. **P1 改名时所有无 N 编号文件（如 `circular_mode_no_continue_prompt.md` + `workflow_spec_concentration_2026-07-20.md`）一并迁移到 `archived-early/`**
12. **第四轮实测：hooks 目录在 `scripts/hooks/` 不在 `.pre-commit-hooks/`** — `check_doc_path_drift.py` 新建于 `scripts/hooks/`，加入 `gaf_governance_batch.py` CHECKS 列表第 13 项（无需 `.pre-commit-config.yaml` 新增 hook）
13. **第四轮实测：现有 `check_doc_code_sync.py` (TD-325/spec-87) 已实现 §9.3 设计的功能** — 不新建 `check_doc_sync.py`，扩展 `doc_sync_rules.py` 加 R8 规则 + 扩展主逻辑加 `doc_last_updated` 字段检查 + P0 后更新 R3/R7 路径
14. **第四轮实测：现有 `check_path_consistency.py` (N107) 与 `check_doc_path_drift.py` 职责区分** — 前者检查 inline path 构造，后者检查旧路径字符串回退，两者不合并
15. **第四轮实测：`scripts/` 下无 `start_backend.py` 也无 `start_gaf.sh`** — P2 实施时新建 `scripts/start_gaf.sh`
16. **第五轮修正：§3.3 标题改为"lesson 文件 frontmatter schema"** — 明确描述的是 lesson 文件（如 `N188-xxx.md`）的 frontmatter，不是 `lessons/README.md` 文件本身的 frontmatter（后者维护 `lessons_count` / `active_n_count` / `next_n_id` 等索引计数器）
17. **第五轮修正：§3.4 示例表格"主题"列用实际表格内容** — 不用 topic 字段值（如 `platform-env`），用详细描述（如"conda gaf 环境规则多次未生效"），与实际 failure-modes.md 表格风格一致
18. **第五轮修正：§4.2 新增触发点 3（任务执行时沉淀触发）** — 与 §10.2 步骤 5 对齐；触发点 1 处理历史遗留 pending_promotion，触发点 3 处理本次任务产生的新 evidence
19. **第五轮修正：§9.3 R8 规则加 `status_filter="M"`** — 只对 modified 触发，A(新建)/D(删除)/R(重命名) 不触发（新建时 doc_last_updated 是初始值，不需要"更新"）
20. **第五轮修正：§9.1 映射表补全 4 个缺失模块** — `business.workspace` / `business.game-profile` / `business.system` / `architecture.desktop`，空数组 `[]` 标记暂无对应代码路径
21. **第六轮修正：§Dormant 段语义误解（最严重错误）** — 原 spec §4.1 步骤 ⑤ / §4.5 / §5.1 / §5.2 / §10.2 五处把 §Dormant 当成"Active 超时未触发"的归宿；实际 failure-modes.md §Dormant 是"家族合并子条目"专用（如 N107/N110/N114 合并到 N105）；Active 超时未触发应走"Active → archived-lessons.md (deprecated 档)"
22. **第六轮修正：N## 四档分布明确** — Active (本段) / Dormant (家族合并子条目, §Dormant 段) / Archived (deprecated, archived-lessons.md) / Retired (M0.M 闭环, §Retired 段, 编号永不复用)；forgetting_check_once() 实现 "Active → Archived" 而非 "Active → Dormant"
23. **第六轮修正：§4.4 升级路径补充 Retired 路径** — 硬约束已沉淀到 rules/skills (M0.M 闭环) → 移到 §Retired 段（编号永不复用，详见 N181 退役机制）
24. **第六轮修正：§6.2 第 4 项加 P5 治本约束说明** — failure-modes.md frontmatter 有 `p5_max_lines: 170` 行限制；加列不加行，p5_max_lines 不受影响；现有 N## 四档分布实测（Active ~65 行 / Dormant ~10 行 / Retired ~7 行 / Archived 在 archived-lessons.md）
25. **第六轮修正：§6.2 第 8 项加现有计数字段说明** — lessons/README.md frontmatter 现有 5 个计数字段（lessons_count / active_n_count / retired_n_count / archived_n_count / dormant_n_count），加 next_n_id 与现有字段并存，不替换
26. **第六轮修正：§6.2 第 2 项明确 archived-early/ 现状** — archived-early/ 下已有 6 个早期归档文件，本次再迁入 2 个无 N 编号文件（`circular_mode_no_continue_prompt.md` + `workflow_spec_concentration_2026-07-20.md`）
27. **第六轮实测：N## 最大编号是 N188** — lessons/ 实际文件 `platform-env_2026-07-25-n188-conda-env-not-enforced.md`，next_n_id 初始值 N189 正确
28. **第六轮实测：failure-modes.md §Active 表格列标题是"硬约束 (1 行)"** — spec §3.4 示例**列标题**与实际一致 ✓（注意：仅列标题一致，示例表格的"主题"和"硬约束"**内容**是简化版，详见 §3.4 注释）
29. **第六轮实测：gaf_init.sh grep 模式 `^\| N[0-9]+`** — 与 spec §3.4 描述一致 ✓
30. **第七轮修正：§4.2 触发点 2 描述（第 356 行）遗漏修正** — 第六轮只修了 §4.1/§4.5/§5.1/§5.2/§10.2 五处，漏掉 §4.2 触发点 2 forgetting_check_once 描述"移到 §Dormant 段"；修正为"→ archived-lessons.md (deprecated 档)"并加注释说明 §Dormant 段语义
31. **第七轮修正：§4.1 步骤 ⑤ 加 M0.M 闭环路径说明** — 原描述只覆盖"超时未触发"路径，未明确 M0.M 闭环 N## 走 §4.4 升级路径（→ §Retired 段），不走遗忘机制；加注释明确两条路径区分
32. **第七轮修正：§7.5 P2 阶段引用更新清单补 5 处源代码硬编码引用** — 第六轮只列 6 个根目录文件的文档引用，漏掉 sync_session_context.py L44 / sync_spec_index.py L47+L215 / check_spec_id_collision.py L166 / spec_dependency_graph.py L396 / scripts/README.md L64 的源代码硬编码路径引用；补充后 P2 阶段引用更新清单完整
33. **第七轮修正：§4.1 步骤 ⑤ + §5.2 cleanup_old_evidence 函数名冲突 + 功能描述错误** — 原 §4.1 步骤 ⑤ 写"evidence/archived/ > 90 天 → 删除 (cleanup_old_evidence)"，但 §5.2 的 cleanup_old_evidence_once 实现的是"active > 30 天 → 移 archived"，函数名冲突 + 功能描述错位；修正：§4.1 步骤 ⑤ 拆分为两行（cleanup_old_evidence_once 处理 active→archived，delete_archived_evidence_once 处理 archived>90 天删除），§5.2 加新函数 delete_archived_evidence_once + run_startup_checks 调用顺序更新 + §4.2 触发点 2 + §10.2 GAF 启动阶段同步更新
34. **第七轮修正：§4.3 文件锁路径 typo** — 原文 `%.cache/lessons_n_id.lock` 是 typo，应为 `.cache/lessons_n_id.lock`（与 agent PID 锁同模式，相对仓库根的 .cache/ 目录）
35. **第七轮修正：§5.2 cleanup_old_evidence_once docstring 引用错误** — 原 docstring 写"(spec §4.5)"，但 §4.5 是风险与缓解表，cleanup_old_evidence 的实际定义在 §4.1 步骤 ⑤；修正为"(spec §4.1 步骤 ⑤)"
36. **第九轮修正：forgetting_check_once 跨章节不一致（§Dormant 超时处理范围）** — §4.1 步骤 ⑤ 列出 §Active + §Dormant 两类超时处理规则，但 §4.2 触发点 2 / §5.1 / §5.2 docstring / §10.2 GAF 启动阶段四处只描述 §Active 超时，与 §4.1 步骤 ⑤ 矛盾；修正：五处描述统一为"forgetting_check_once 处理两类超时（§Active + §Dormant）→ archived-lessons.md deprecated"，§4.1 步骤 ⑤ 注释从"本步骤只处理'超时未触发'的 Active N##"改为"forgetting_check_once 处理两类超时"明确语义，§4.2 触发点 2 注释从"forgetting_check_once 不写入 §Dormant"改为"forgetting_check_once 不会把 §Active 超时 N## 写入 §Dormant（直接进 archived-lessons.md）；但 forgetting_check_once **会**处理 §Dormant 段已存在的子条目超时"消除歧义
37. **第九轮修正：§10.1 决策 22 表述歧义** — 原"forgetting_check_once() 实现 'Active → Archived' 而非 'Active → Dormant'"易误读为"forgetting_check_once 只处理 §Active"；本次修正后 forgetting_check_once 同时处理 §Active + §Dormant 两类超时（均 → archived-lessons.md），决策 22 表述保留但需结合决策 36 阅读
38. **第九轮修正：project_rules.md §1.1 → §6.1 引用错误** — 第七轮决策 1 / §6.3 改动范围 / §7.5 P2 引用清单 / §10.3 关系表四处都说"project_rules.md §1.1 引用 tech-stack.md"，实测发现 §1.1 是"服务启停"段未引用 tech-stack.md，实际引用在 §6.1 L659（"决策树 step_1 后 → 必 Read 2 个 L2 文件 ai-operating-handbook.md + tech-stack.md"）；修正四处 §1.1 → §6.1 (L659)，避免 P2 实施时改错章节
39. **第九轮实测：scripts/start_backend.py 和 scripts/start_gaf.sh 均不存在** — spec §5.2 + §8.3 + §10.3 都说"P2 实施时若不存在则新建 start_gaf.sh"，实测确认 scripts/ 下无等价启动脚本（仅有 gaf_init.sh / gaf-commit.sh），P2 实施时按方案 A 新建 scripts/start_gaf.sh 前提成立
40. **第十一轮实测修正：§9.1 映射表 business.game-profile 代码路径错误** — spec 设计时基于"前端侧边栏模块名"猜测代码路径 `backend/game_profiles/**` + `frontend/src/views/game-profile/**`；2026-07-26 P0 实测确认实际路径为 `backend/gamestate/**`（含 GameProfile 模型/views/serializers/migrations） + `frontend/src/pages/GameProfiles/**`（含 index.tsx/DetailPage.tsx/components/）；已修正 §9.1 映射表 + 加 P0 实测完成说明；sync_docs_index.py 后续生成 `applies_to_code_paths` 字段需基于实测路径，不能用原假设

### 10.2 统一执行流程（用实际步骤命名）

```
═══ GAF 启动阶段 ═══
1. Django ready()
2. 启动脚本显式调用 run_startup_checks --all (方案 A)
   - cleanup_old_archives_once (删 30 天前 tar.gz)
   - cleanup_old_evidence_once (移 30 天前 active → archived)
   - delete_archived_evidence_once (删 90 天前 archived evidence)
   - forgetting_check_once (两类超时 → archived-lessons.md deprecated):
     ① §Active last_triggered > 6 月 + 无 Y/N 矩阵引用
     ② §Dormant 子条目超 6 月 + 无新复发 + 无 Y/N 矩阵引用
3. Django runserver 启动

═══ AI 会话启动阶段 ═══
1. L1 hard-load: failure-modes.md §Active 段 N## 索引
2. L2 hard-load: ai-operating-handbook.md + tech-stack.md (P2 后改路径为 ref/tech-stack.md)
3. §0.5 spec-42 patch (P0/P1 文档健康, 已有)
4. §4.2 触发点 1 扫 evidence/active/ pending_promotion (新增, §0.5 之后)
   - 同 topic ≥ 2 → 标记 pending_promotion
   - AI 在当前会话内处理 (写 lesson + 更新 failure-modes + 移 evidence)

═══ 任务执行阶段 (闭环步骤 1-5) ═══
1. 开工：bash scripts/gaf_init.sh
2. 判定：按决策树根节点判定 task_type
3. 加载：按 task_type 加载对应 skill + KB
4. 搜索 (L3 硬约束)：sync_ai_memory.py --query "<symptom>"
   - §9.4 实时查 git log 检查 stale (新增, 接入此步骤)
   - sync_status: stale → 加载时附提醒
5. 执行：写代码 + 3 步 evidence + lessons（如新坑）
   - §4.1 沉淀闭环步骤 ② 模式识别 (新增, 扩展此步骤):
     写完新 evidence 后扫 evidence/active/ 同 topic ≥ 2
     → 触发 §4.1 步骤 ③ 主动沉淀:
       a. 分配 N 编号 (从 lessons/README.md next_n_id 取)
       b. 写 lessons/N<编号>-<slug>.md (含 topic/n_id frontmatter)
       c. 更新 failure-modes.md §Active 段 (加 trigger_count + last_triggered)
       d. 移 evidence 到 archived/YYYY-MM/

═══ 任务收尾阶段 (闭环步骤 6) ═══
6. 提交：按 project_rules §3.4 spec 粒度自决 commit
   - 测试通过
   - §9.2 文档同步检查 (新增, 扩展此步骤)
     - 扫 git diff --name-only 涉及的代码路径
     - 反查 docs-index.md 找对应文档
     - 通过 AskUserQuestion 询问用户是否更新文档
   - commit
```

### 10.3 与现有文档的关系

| 现有文档 | spec 影响 | P 阶段 |
|---------|----------|--------|
| `.trae/skills/gaf-orchestrator/SKILL.md` | §0.5 之后加 §4.2 触发点 1 扫 pending_promotion；步骤 4 加 §9.4 stale 检查；步骤 5 加 §4.2 触发点 3 沉淀闭环；步骤 6 加 §9.2 文档同步检查；L2/L3 路径改 ref/ | P1 (§4) + P2 (§9 + ref/) |
| `.trae/rules/project_rules.md` | §0 三份核心文档引用路径更新；§6.1 (L659) tech-stack 路径改 ref/ | P0 (§0) + P2 (§6.1) |
| `.ai-memory/README.md` | §0.1 加载顺序表更新 ref/ 路径；§3 目录结构更新 | P2 |
| `.ai-memory/meta/ai-operating-handbook.md` | Part 1 L2/L3 段路径更新 ref/ | P2 |
| `.ai-memory/meta/failure-modes.md` | §Active 表格加 trigger_count + last_triggered 两列 | P1 |
| `.ai-memory/meta/docs-index.md` | 重生成（含 module + applies_to_code_paths + doc_last_updated 字段） | P0 |
| `.ai-memory/lessons/README.md` | 加 next_n_id 计数器；frontmatter schema 加 topic 字段；文件清单全更新 | P1 |
| `.ai-memory/evidence/README.md` | 新建（沉淀规则说明） | P1 |
| `backend/gaf_core/startup_checks.py` | P1 新建（§5.2 实现要点：4 个清理函数 + run_startup_checks） | P1 |
| `backend/gaf_core/management/commands/run_startup_checks.py` | P1 新建（§5.2 management command） | P1 |
| `backend/gaf_core/tests/test_self_evolution.py` | P1 新建（§6.2 第 13 项单元测试 4 项） | P1 |
| `scripts/hooks/doc_sync_rules.py` | P0 后更新 R3/R7 路径（`docs/general/design/` → `docs/architecture/` + `docs/business/`）；P2 加 R8 规则（doc_last_updated 强制） | P0 (R3/R7) + P2 (R8) |
| `scripts/hooks/check_doc_code_sync.py` | P2 扩展主逻辑加 doc_last_updated 字段检查（不新增 hook） | P2 |
| `scripts/hooks/gaf_governance_batch.py` | P2 CHECKS 列表加第 13 项 `check_doc_path_drift` | P2 |
| `scripts/hooks/check_doc_path_drift.py` | P2 新建（旧路径零兼容检查） | P2 |
| `scripts/bootstrap/sync_session_context.py` | P2 L44 硬编码路径改 `ref/session-context.md` | P2 |
| `scripts/governance/sync_spec_index.py` | P2 L47/L215 硬编码路径改 `ref/spec-index.md` | P2 |
| `scripts/hooks/check_spec_id_collision.py` | P2 L166 错误消息引用改 `ref/spec-index.md` | P2 |
| `scripts/governance/spec_dependency_graph.py` | P2 L396 生成内容引用改 `ref/spec-index.md` | P2 |
| `scripts/README.md` | P2 L64 脚本说明改 `ref/session-context.md` | P2 |
| `scripts/start_gaf.sh` | P2 新建（启动脚本显式调用 run_startup_checks --all + runserver） | P2 |

### 10.4 已知不一致（不在本次范围）

- `.ai-memory/README.md` §3 目录结构缺 `session/`（已有不一致）
- `.ai-memory/README.md` §5 gaf-commit.sh wrapper 与 orchestrator 闭环步骤 6 不一致（已有不一致）
- `.ai-memory/README.md` §1.1 manual 模式 8 必填字段 vs lessons/README.md schema 11 字段不一致（已有不一致）

这些已记录在承载体文档 §10.1，本次不修，避免范围蔓延。

---

## 附录 A：用户决策清单（20 条，原文）

| # | 决策点 | 用户原文/选择 |
|---|--------|--------------|
| 1 | 两个目录都改还是只改一个 | "两个都改" |
| 2 | 分阶段还是一次性 | "分 3 阶段" |
| 3 | `.trae/` 目录动不动 | ".trae 不动" |
| 4 | lessons 文件名格式 | "N编号-slug" |
| 5 | evidence 清理策略 | "active + 30天" |
| 6 | docs/business/ 是否建 9 模块子目录 | "9 模块子目录" |
| 7 | docs/architecture/ 是否按五层架构 | "五层架构" |
| 8 | 引用更新策略 | "全量 grep + hook" |
| 9 | `.ai-memory/` 根目录收敛 | "ref 收敛" |
| 10 | governance/ 怎么处理 | "governance 入 ops" |
| 11 | 先重构还是先加新内容 | "先重构" |
| 12 | frontmatter 加什么字段 | "加 module 字段" |
| 13 | 三个备选方案选哪个 | "A"（双线索主导） |
| 14 | 自动清理用不用系统注册表 | "不用注册表，gaf启动再开启检测即可，完成后就停掉" |
| 15 | 旧路径要不要保留兼容 | "不需要恢复旧目录结构了，都用新的" |
| 16 | AI 自我进化要不要设计 | "这个设计还得考量ai沉淀的自我进化" |
| 17 | 是否需要上下文承载体文档 | "是不是设计一个文档用来承载上下文好点？这不是spec，记录原文给下个对话" |
| 18 | 文档与代码同步更新 | "希望更新对应业务或者架构时，ai能同步更新文档，别之后访问文档又是过时的" |
| 19 | 定时任务可行性 | "定时执行不太可能，顶多是对话访问文档时检查下实际代码行为是否一致吧，因为是在ide开发得，并不是我有设置llm让他定时查看，ide开发时，软件也只在调试时启动" |
| 20 | 检查时机 | "对话访问文档时检查下实际代码行为是否一致"（确认 §9.4 删定时，改对话内即时检查） |

---

## 附录 B：实施前实测确认清单

P0 启动前必跑（详见 §8.3）, 已于 2026-07-26 全部完成 (详见 plan §2.2 实测结果记录):

- [x] 确认 `docs/general/design/` 实际文件清单
- [x] 确认 `data-flow.md` 是否存在
- [x] 确认 `scripts/start_backend.py` 或等价启动脚本是否存在
- [x] 确认现有 lessons 最大 N 编号
- [x] 确认 evidence 目录数量
- [x] 确认 `sync_docs_index.py` 现状

---

## 附录 C：上下文恢复指引

如果你是接手实施的 AI，请按以下步骤恢复上下文：

1. **读本 spec 全文** — 正式规格（含 §1-§10 + 附录 A/B/C）
2. **读 [承载体文档](../../../.ai-memory/spec-context/2026-07-25-docs-restructure-context.md)** — 设计过程、三轮对齐检查、用户决策原文
3. **读 `.trae/rules/env-hardrules.md`** — L0 系统级硬约束（所有 Python 命令必用 `conda run -n gaf`）
4. **读 `.trae/rules/project_rules.md §0`** — 三份核心文档（最优方案/功能总览/架构总览）的引用路径
5. **读 `.ai-memory/meta/failure-modes.md`** — L1 硬加载的 N## 索引表
6. **跑 §8.3 实测确认**
7. **下一步动作**：创建 plan 文档（`docs/plans/2026-07-25-docs-ai-memory-restructure.md`），然后实施 P0

**关键约束**：
- 所有 Python 命令必须用 `conda run -n gaf python ...`
- 旧路径零兼容（§7），不保留任何回退路径
- **无定时任务**（§5）— 全部改为 GAF 启动时跑一次 + AI 会话内触发
- AI 自我进化沉淀闭环是核心需求（§4），但异步任务不调 LLM，只标记 pending_promotion
- 文档与代码同步是核心需求（§9），AI 访问文档时实时查 git log 检查 stale
- AI 改文档必须经 AskUserQuestion 用户确认，不能自作主张
