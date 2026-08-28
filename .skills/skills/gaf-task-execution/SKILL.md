---
name: gaf-task-execution
description: |
  任务执行 skill。AI 接到 new_feature / refactor 任务时加载。
  决策树见 gaf-orchestrator（v9 单一权威源）。
version: 9.0
updated: 2026-08-21
load_when:
  - task_type == new_feature
  - task_type == refactor
  - task_type == documentation (写代码相关文档)
---

# gaf-task-execution — 任务执行（new_feature / refactor）（v9.0 工作流简化版）

> **v9.0 变更**（gaf-workflow-v9-slim 闭环）：
> - 决策树副本已删除，见 `gaf-orchestrator/SKILL.md ## Decision Tree`（单一权威源）
> - superpowers skill（test-driven-development 等）改为"方法论参考"，GAF 项目特定规范见 `docs/standards/`

---

## 1. 加载时机（v8.4 N95 强化）

按 `gaf-orchestrator` 决策树根节点判定，**以下 3 类任务**自动加载本 skill：

| task_type | 触发场景 | 主导工作 |
|-----------|----------|----------|
| `new_feature` | 新增功能 / 实现 / 添加 / 开发 | 5 段实施流程（写代码） |
| `refactor` | 重构 / 拆模块 / 改架构 | 5 段重构流程（评估影响 + 分阶段） |
| `documentation` | 写 API/架构/数据流文档 | 文档化流程（不阻塞 AI 写） |

**前置必跑**：`bash GAF/scripts/gaf_init.sh`（含 L1 硬加载 failure-modes.md + session active）。

---

## 2. 5 段 new_feature 实施流程（v8.4 强化）

### step_1_spec_review（spec 审视）

- **必读 4 份**（L2 hard-load）：
  - `docs/architecture/features-overview.md`（功能定义 + P0/P1/P2 优先级）
  - `docs/architecture/optimal-solution.md`（为什么这样做）
  - `docs/architecture/overview.md`（架构设计、数据模型、模块关系）
  - `gaf-orchestrator/SKILL.md` 决策树（v9.0 单一权威源，开发流程入口）
- **回答 4 问反思**（项目规则 §4.6）：
  1. 本轮要做什么？范围边界是什么？
  2. 现有代码中哪些可以直接复用？哪些需要修改？
  3. 有什么潜在风险或依赖？
  4. 本轮的验收标准是什么（P0 全部通过才标记 ✅）？

### step_2_plan_approval（计划批准）

- 拆分子任务（TodoWrite）
- 估算每个子任务影响范围
- **🆕 v8.4 N115**：计划内任务 AI 自决，不需问"是否开始"
- 跨工作区 / 重写 history / 不可逆删除 → NotifyUser 告知
- `pending-roadmap.md` 写明选 X 不选 Y 理由（N109）

### step_3_implement（实施）

- **后端任务**：先写 API + serializer + test
  - `python manage.py makemigrations` 跑通
  - Django test 写 unit test + integration test
  - pytest 跑 `backend/<app>/tests/test_<feature>.py`
  - **后端规范**：见 `docs/standards/backend-conventions.md`
- **前端任务**：先写 TS 类型 + API client + UI 组件 + e2e
  - 4 步配套（**N112 硬约束**）：
    1. Read backend serializer（字段权威源）
    2. Read backend views（action 端点 + 错误码）
    3. Grep 现有 TS 类型对比
    4. TS 类型同步 + API client 真实调用 + UI 标签 + 过滤下拉
  - `npx tsc --noEmit` 跑通
  - **前端规范**：见 `docs/standards/frontend-conventions.md`
  - **API 契约**：见 `docs/standards/api-contract.md`
- **Agent / Pipeline 任务**：先写节点定义 + protocol handler
  - 单元测试用 mock agent
  - 集成测试用 `e2e/fixtures/mock_agent.py`
- **TDD 原则** (调用 Skill(name='test-driven-development') (方法论参考)):
  - 注释用英文（项目规则 §2）
  - 函数级 docstring（用户规则 3）
  - import 顶部集中（PEP 8）
  - **GAF 项目特定测试规范**：见 `docs/standards/backend-conventions.md` §6 + `docs/standards/frontend-conventions.md`

### step_4_verify（验证）

**必跑 4 项**（pre-commit hook 自动跑 + 手动跑）：

| 工具 | 命令 | 通过标准 |
|------|------|----------|
| ruff | `ruff check scripts/bootstrap/sync_ai_memory.py` | 0 errors |
| mypy | `mypy backend/<app>/` | 0 errors |
| pytest | `pytest backend/<app>/tests/ -v` | 全过 |
| tsc | `cd frontend && npx tsc --noEmit` | 0 errors |

**N114 验证**（pre-commit hook）：
- 跑 `pre-commit run --files <staged_file>` 验证 hook 只跑 1 文件（不扫全项目）

**🆕 阶段验收 (§4.9 — TD-136 修复 2026-07-18)**:
> **触发条件**: 大修改场景 (> 500 行 diff / 跨模块 / DB 迁移 / API 契约变更) 且当前 Phase 是 spec 内某个大阶段的最后一个子任务。小修改/单 Phase spec 豁免。

- **大阶段所有子任务完成后, 必跑 N128 3 步验证**:
  1. **代码验证**: lint + test + sync 跑通 (本 step_4 已含)
  2. **功能验证**: 浏览器实测 (涉及 UI/WS/Agent 时) 或 pytest (纯后端逻辑)
  3. **文档验证**: completed-features.md 阶段验收 evidence 落地 (✅/🔧 + 测试通过数 + 关键文件路径)
- **验收失败**: 修复后重跑, 不允许跳过进入下一阶段 (§4.9 硬约束)
- **验收通过**: 更新 `completed-features.md` 对应条目, 进入下一 Phase
- **与 §3.4 交互**: 阶段验收在 `git add` 暂存之后、`git commit` 之前; 各 Phase 只暂存不 commit, 全部 Phase 完成 + 全量回归通过后才 commit (详见 `project_rules.md §3.4` TD-231 流程图)

### step_5_commit_evidence（提交 + evidence）

**🆕 全量回归前置 (§4.9 — TD-136 修复 2026-07-18)**:
> **触发条件**: spec 内所有大阶段都 ✅ 后, commit 前必跑全量回归。单 Phase spec 豁免。

- 按阶段顺序逐个复查每个阶段的验收标准 (§4.9 硬约束)
- 全部通过才进入 commit 流程; 任一阶段验收不通过 → 回到该阶段修复
- 全量回归 evidence 落地到 `completed-features.md` spec 对应条目

按项目规则 §3.4 spec 粒度自决 commit（默认 1 commit/spec; 复杂任务可分段）：
1. 完成 spec 所有阶段（spec 粒度自决, 各 Phase 只 `git add` 暂存）
2. 本地验证 (lint/test/sync) 全过
3. `git status` 看变更范围 + `git diff` 检查内容
4. `git add <specific_files>` (不用 `-A` 或 `.`)
5. **`git status` 二次确认无未暂存残留 (N153 强化 — spec 改动多, stash 风险高)**
6. `git commit -m "<type>(<scope>): <spec 名>"` (单行 -m 不弹窗; 多行用多个 -m flag; `-F <file>` 已禁用, 见 env-hardrules §Shell N190)
7. `git log --oneline -1` 验证 commit 成功
8. 写 3 步 evidence（problem/solution/verification）到 `.ai-memory/evidence/active/<date>-<task>/`
9. **更新状态文档**: `docs/completed-features.md` + `docs/pending-roadmap.md` 状态标记同步 (§4.5 要求)

**N105/N108/N150 反模式**：
- ❌ 不用 `gaf-commit.sh --no-verify`（hook 透传 bug）
- ❌ 不用 `--no-verify` 绕过非 N105 的 pre-commit 失败（N150 — 必须根因修复，见 `project_rules §3.3`）
- ❌ 不用 `git add -A`（可能包含敏感文件）
- ❌ 不用空 commit（`--allow-empty`）

---

## 3. 5 段 refactor 流程（v8.4 强化 + N151 架构视角约束）

### step_1_impact_assessment（影响评估 + 🆕 N151 架构视角）

> **🆕 N151 大修改架构视角原则**: 大修改 (>500 行/架构变更/跨模块/DB 迁移/API 契约) 必须从架构视角决策, 拒绝"最小化修补"和"保留双套各管一摊"。详见 `gaf-orchestrator/SKILL.md` refactor 分支 step_3 + `.ai-memory/lessons/2026-07-08-n151-architecture-first-for-major-changes.md`。

**N151 5 步架构视角流程**（大修改必跑）:
1. **架构盘点 (4 维度)**: 数据 (DB 行数/schema/字段差异) + 依赖 (FK/import) + 调用 (前端/Agent/Serializer/View/URL) + 历史 (评估报告/TD/历史决策)
2. **识别反模式**: 双套并存 (两套实现 schema 不同 + 用途不同 + 都活跃) / 越界归属 / 重复实现 / schema 分裂
3. **产出 A/B/C 备选 (每个 5 项架构依据)**: ① 当前架构问题 ② 方案对架构的影响 ③ 长期可维护性 ④ 迁移成本/风险 ⑤ 连带影响
4. **拒绝两类反模式路径**: ❌ "保留两套各管一摊" (双套并存=决策推迟) + ❌ "最小化修补" (下游 workaround 适配架构缺陷)
5. **AI 自决同样适用**: N109/N113/N115/N127 自决权不变, 但大修改方向必走架构视角; AI 自决的是"如何执行"不是"走哪个方向"; 方向由架构判定或用户选 (AskUserQuestion)

**通用影响评估**（所有 refactor 必跑）:
- 列出影响范围（哪些模块/接口/数据）
- 评估风险（**是否需要双写期**）
- 评估收益（行数/复杂度/可测试性）

**N151 硬约束**:
- ✅ KEEP 决策必须基于架构判定 (无目标 app / FK 在原 app 更合理), 不是"最小化"借口
- ❌ 禁止 AI 凭"最小改动"自决大修改方向
- ❌ 禁止保留双套并存不决策
- ❌ 禁止在下游加 workaround 适配架构缺陷

### step_2_user_approval（用户批准）

- 提交执行计划（`NotifyUser` 工具）
- 列出 3 类不可自决项（跨工作区 / 重写 history / 不可逆删除）
- 用户批准后才开始（**N93 闭环**）

### step_3_dual_write（双写期，可选）

- 新老实现并存
- 数据迁移脚本
- 监控指标对比

### step_4_cutover（切换）

- 读流量切换
- 回滚预案
- 监控告警

### step_5_cleanup（清理）

- 删老代码
- 删双写期代码
- 更新文档（L1 分发）

---

## 4. 任务执行检查清单

```yaml
before_start:
  - "gaf_init.sh 跑通 (L1 硬加载 failure-modes.md)"
  - "gaf-orchestrator 决策树已读 (单一权威源)"

during_implement:
  - "spec/tasks/checklist 三件套已 Read (项目规则 §0 强制)"
  - "lesson --query 跑过 (L3 按需加载)"
  - "5 段流程 step_1→step_5 严格走"

before_commit:
  - "lint (ruff/mypy) + test (pytest/tsc) 跑通"
  - "git status + git diff 检查变更范围"
  - "commit message 按 <type>(<scope>): <subject> 格式"

after_commit:
  - "git log --oneline -1 验证 (防 N82 审计错觉)"
  - "反思按规模分级 (小/中/大, 见 gaf-reflect-and-evolve §2)"
  - "3 步 evidence 写完 (N97 必填)"
  - "L0/L1 分发走 gaf-lesson-router §3 单一权威源 (真二分制判定, 非按修改规模判定)"
```

---

## 5. 4 步配套 — 后端字段变更（N112 硬约束）

> **来源**：P-024-4 闭环，前端跟后端对不上 → 标签失效 / 点了没反应。

**触发**：AI 改 backend model / serializer / views action。

**AI 必做**（4 步配套）：
1. **TS 类型同步**：`frontend/src/types/models/` 增/改/删字段
2. **API client 真实调用**：`frontend/src/api/<app>.ts` 改 `client.post/put`（禁止 `Promise.resolve()` placeholder）
3. **UI 标签 + 颜色**：severity 4 级 (P0 red / P1 orange / P2 gold / P3 blue)
4. **过滤下拉**：`Select options={[]}` 含新字段

**改后端 → 必跑 3 步核对**：
1. `Read backend/<app>/serializers.py`（字段权威源）
2. `Read backend/<app>/views.py`（action + 错误码）
3. `Grep frontend/src/types/models/ <field>`（看现有 TS 类型）

**反模式**：
- ❌ 留 API placeholder（`Promise.resolve()` 假装已实现）
- ❌ 凭语义编 `dataIndex`（必须 Read serializer 对齐）
- ❌ severity 3 级（info/warning/critical）与后端 4 级（P0-P3）错配
- ❌ 改后端字段后跳过前端 4 步配套

---

## 6. 与其他 skill 的边界

- **`gaf-orchestrator`**：本 skill 是它的子 skill（task_type = new_feature / refactor）；决策树权威源在 orchestrator
- **`gaf-knowledge-base`**：本 skill 主导写代码；KB skill 提供索引，本 skill 调 L3 加载
- **`gaf-reflect-and-evolve`**：commit 后由它主导反思；本 skill 在反思前的"实施"阶段被调用
- **superpowers skills**（`test-driven-development` / `systematic-debugging` / `writing-plans`）：通用方法论参考；GAF 项目特定规范见 `docs/standards/`

---

## Decision Tree

> **v9.0 单一权威源**: 决策树见 `gaf-orchestrator/SKILL.md ## Decision Tree`。
> 本 skill 仅在 task_type=new_feature/refactor/documentation 时被 gaf-orchestrator 加载，不保留决策树副本。
