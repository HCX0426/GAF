---
name: gaf-knowledge-base
description: |
  Knowledge base 索引 + 场景路由。AI 任务中需要查 KB 时加载。
  决策树见 gaf-orchestrator（v9 单一权威源）。
version: 9.0
updated: 2026-08-21
load_when:
  - task_type == documentation
  - task_type == bug_fix AND need to search lessons/
  - task_type == new_feature AND need to read API / pipeline / agent protocols
  - task_type == refactor AND need architecture-mistakes context
---

# gaf-knowledge-base — KB 索引 + 场景路由（v9.0 工作流简化版）

> **v9.0 变更**（gaf-workflow-v9-slim 闭环）：
> - 决策树副本已删除，见 `gaf-orchestrator/SKILL.md ## Decision Tree`（单一权威源）
> - 职责不变：把 `.ai-memory/` 10 份顶层 + `meta/` 子目录 + 9 类子目录 + `docs/` 52 份索引，按 `load_when` 路由到 AI

---

## 1. 加载时机（v8.4 N95 强化）

按 `gaf-orchestrator` 决策树根节点判定，**以下 4 类任务**自动加载本 skill：

| task_type | 触发场景 | 必加载 KB |
|-----------|----------|-----------|
| `documentation` | 写 / 改 / 整理文档 | `docs-index.md` + `docs/` (按 `applies_to` 路由) |
| `bug_fix` | 报错 / 不工作 / 失败 | `failure-modes.md` + `lessons/` (按 symptom 搜) |
| `new_feature` | 新增功能 / 接口 | `api-endpoints.md` / `pipeline-nodes.md` / `agent-protocol.md` (按 task domain) |
| `refactor` | 重构 / 改架构 | `architecture-mistakes.md` + `lessons/` 找 refactor 教训 |

**L2 hard-load 联动**：本 skill 加载时，AI **必须** Read `meta/docs-index.md`（M0.N 加项）按 `applies_to` 查原文，禁止凭印象写代码。

---

## 2. `.ai-memory/` 顶层 6 份手写 + `meta/` 子目录 + `meta/auto-kb/` 4 份 auto-generated

> 路径：`GAF/.ai-memory/*.md`（6 份手写）+ `.ai-memory/meta/*.md`（ai-operating-handbook / docs-index / failure-modes / yn-matrices / archived-lessons / spec-evolution）+ `.ai-memory/meta/auto-kb/`（4 份 auto-generated）

### 2.1 顶层 6 份手写文档

| 文件 | 用途 | 加载时机 |
|------|------|----------|
| `tech-stack.md` | 4 栈版本 (Python 3.11 / Django 5.2 / React 19.2 / ADB) | new_feature step_2 |
| `version-compat.md` | Python/Django/React/ADB 版本兼容 + 已知问题 + 漂移表 + 6 类版本同步规则 (spec-38 Phase 6 合并 version-sync.md) | L3 按需 (版本/依赖决策/跨文件版本同步) |
| `data-flow.md` | 数据流向图（UI → API → Task → Agent） | refactor / 排查 |
| `cli-cheatsheet.md` | 常用 CLI 命令速查 | 任意 task_type |
| `README.md` | front matter 规范 + 3 模式说明 | 任意 task_type（首读） |
| `session-context.md` | 当前 session 上下文 | 任意 task_type |

### 2.2 `meta/` 子目录 (6 份手写)

| 文件 | 用途 | 加载时机 |
|------|------|----------|
| `meta/ai-operating-handbook.md` | L1/L2/L3 加载机制 + AI 行为红线 (v9.3 合并自 loading-strategy + ai-behavior-redlines) | 任意 task_type L2 必加载 |
| `meta/failure-modes.md` | 失败模式索引（50+ entries） | bug_fix / pre-commit 失败 |
| `meta/docs-index.md` | `docs/` 52 份文档分组索引 | documentation / new_feature L2 |
| `meta/yn-matrices/` | 7 个 Y/N 检查矩阵 sub-file | 反思时按 topic 加载 |
| `meta/spec-evolution.md` | 季度 review 提示 | 季度回顾 |
| `meta/archived-lessons.md` | 已闭环 N## 索引 | 查历史教训 |

### 2.3 `meta/auto-kb/` 子目录 (4 份 auto-generated, spec-38 Phase 4 迁入)

| 文件 | 用途 | 加载时机 |
|------|------|----------|
| `meta/auto-kb/api-endpoints.md` | 后端 REST / DRF 端点速查 | new_feature (domain=backend) |
| `meta/auto-kb/pipeline-nodes.md` | Agent Pipeline 节点类型速查 | new_feature (domain=pipeline) |
| `meta/auto-kb/agent-protocol.md` | Agent ↔ Pipeline 通信协议 | new_feature (domain=agent) |
| `meta/auto-kb/error-codes.md` | 错误码 → 修复命令映射 | bug_fix step_2 |

---

## 3. 9 类子目录

| 子目录 | 用途 | 加载时机 |
|--------|------|----------|
| `lessons/` | 单次教训 (front matter + symptom/solution/related_files) | bug_fix step_3 搜 `--query` |
| `summaries/` | 累计汇总 (architecture-mistakes / code-rules / library-conflicts) | 任意 task_type 首读 |
| `meta/` | 元数据 (failure-modes / docs-index / spec-evolution / auto-kb/ 4 份 auto-generated KB) | 任意 task_type L2 |
| `ops/` | 运营记录 (bug-tracker / deletion-queue / why-skipped / bypass-patterns / completed-features) | 反思 / 状态查询 |
| `evidence/` | 3 步 evidence 模板 + 实战记录 | bug_fix 写证据 |
| `knowledge/` | 4 份业务速查 (data-chain / error-recovery / task-lifecycle / terminology) | 任意 task_type（高频查） |
| `games/browndust-ii/` | 4 份游戏速查 (overview / assets / common-tasks / coordinate-system) | 写 BD2 任务时 |
| `platforms/` | 5 份平台速查 (android / ios / linux / macos / windows) | 跨平台代码时 |
| `checklists/` | 审计 / 诊断清单 (data-chain-checklist 等) | bug_fix diagnose / 反思审计 |

---

## 4. `docs/` 索引（M0.N 加项）

> 路径：`GAF/docs/`（52 份，按 `sync_docs_index.py` 生成索引 `meta/docs-index.md`）

**4 组分类**（详见 `meta/docs-index.md`）：

| 分组 | 文件数 | 必读 task_type |
|------|:------:|----------------|
| `docs/standards/` | 4 | 全部 new_feature / refactor (frontend / backend / api-contract / testing) |
| `docs/business/` + `docs/architecture/` | ~30 | 架构决策 / 设计 / 教训 / specs / tech-debt / health-check (P0 双线索重构后) |
| `docs/specs/legacy-trae/` | 5 | 历史修复 spec（按日期组织, spec-2026-07-26-trae-specs-plans-merge 迁移）|
| `docs/archive/tech-debt-*.md` | 4 | active-tech-debt / fixed-tech-debt / fixed-tech-debt-details / wontfix-tech-debt |
| `docs/analysis/` | 5 | GAF vs Alas/BD2/Maa/ok-script 对比分析 + zxcvbn 替换评估 |
| `docs/specs/` | active + archived/ | 跨设计文档的 spec 索引 (P0 合并自原 4 个 spec 目录) |
| `docs/plans/` | active | 跨设计文档的实施 plan (P0 合并自原 superpowers/plans/) |
| `docs/health/` | 月度归档 | 月度健康检查报告 |

**AI 必跑**：`python GAF/scripts/bootstrap/sync_docs_index.py --check` 验证索引不漂移；`> 90` 天未更新的 `docs/` 会被 gaf_init.sh 警告。

---

## 5. 场景路由决策树

```yaml
routes:
  documentation:
    target_spec:
      kb: ["docs/specs/legacy-trae/.../spec.md", "tasks.md", "checklist.md"]
      workflow: "修订现有节，不允许新增"
    target_api:
      kb: [".ai-memory/meta/auto-kb/api-endpoints.md", "docs/standards/api-contract.md"]
    target_ai_lesson:
      kb: [".ai-memory/lessons/"]
      workflow: "新增 lesson (front matter 必填) 或修订现有"
    target_docs:
      kb: ["docs/standards/", "docs/business/", "docs/architecture/", "docs/analysis/"]
      workflow: "按 docs-index 路由 (applies_to 字段)"
    target_kb:
      kb: [".ai-memory/**/*.md"]
      workflow: "auto 文件跑 sync_ai_memory.py 自动重生成"

  bug_fix:
    search_lessons:
      command: "python GAF/scripts/bootstrap/sync_ai_memory.py --query '<symptom>'"
      fallback: "查 .ai-memory/meta/failure-modes.md N## entries"
    diagnose:
      skill: "pipeline-task-diagnosis (N204: 任务失败/节点异常时必调, 见 env-hardrules-contextual.md §诊断触发硬约束)"
      tools: [".ai-memory/checklists/data-chain-checklist.md", "docs/business/tasks/troubleshooting.md", "agent/src/utils/screenshot_diagnostic.py"]

  new_feature:
    by_domain:
      backend: [".ai-memory/meta/auto-kb/api-endpoints.md", "docs/standards/backend-conventions.md", "docs/standards/api-contract.md"]
      frontend: ["frontend/src/api/*.ts", "docs/standards/frontend-conventions.md"]
      agent: [".ai-memory/meta/auto-kb/agent-protocol.md"]
      pipeline: [".ai-memory/meta/auto-kb/pipeline-nodes.md"]

  refactor:
    context: [".ai-memory/summaries/architecture-mistakes.md", ".ai-memory/lessons/", ".ai-memory/meta/docs-index.md"]
```

---

## 6. 5 步 KB 加载工作流（v8.4 M1.D 完整版）

```yaml
step_1_identify_domain:
  - "读 .ai-memory/meta/ai-operating-handbook.md 确认 L1/L2/L3 状态"
  - "判定 task domain (backend/frontend/agent/pipeline/docs)"

step_2_load_top_level:
  - "按 §2 表格加载对应顶层 .md"

step_3_load_subdirs:
  - "按 §3 表格加载子目录 (按需)"

step_4_load_docs:
  - "跑 python GAF/scripts/bootstrap/sync_docs_index.py 看 docs-index.md"
  - "按 applies_to 查原文 (architecture 8 / backend 10 / frontend 2)"

step_5_query_lessons:
  - "跑 python GAF/scripts/bootstrap/sync_ai_memory.py --query '<keyword>'"
  - "返回 0 条 → 写新 lesson (front matter 必填)"
  - "返回 ≥ 1 条 → 按 symptom 路由"
```

---

## 7. 与其他 skill 的边界

- **`gaf-orchestrator`**：本 skill 是它的子 skill（按 task_type 路由到本 skill）；决策树权威源在 orchestrator
- **`gaf-task-execution`**：写代码时由它主导；本 skill 提供 KB 索引，不主导流程
- **`gaf-reflect-and-evolve`**：commit 后反思；本 skill 在反思前的"查 KB"阶段被调用

---

## Decision Tree

> **v9.0 单一权威源**: 决策树见 `gaf-orchestrator/SKILL.md ## Decision Tree`。
> 本 skill 仅在需要查 KB 时被 gaf-orchestrator 加载，不保留决策树副本。
