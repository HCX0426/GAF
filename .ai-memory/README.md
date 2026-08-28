---
maintainer: derived-manual
source: GAF/.ai-memory/README.md
load_when: [新功能, 文档, AI 启动会话]
priority: high
symptom: [kb:entry, ai-memory, front-matter-spec]
solution: 看下面 3 模式 + front matter 必填字段
related_files:
  - .ai-memory/lessons/
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/evidence/active/
  - .ai-memory/ref/
created_by: AI
generated: 2026-06-14
auto_updated: 2026-06-24
last_manual_edit: 2026-07-26
---

# GAF AI Memory 入口（v8.3.1）

> **本目录是给 AI 用的**：AI 自动维护，无需人类 review。
> **AI 唯一入口**：[`.skills/skills/gaf-orchestrator/SKILL.md`](../.skills/skills/gaf-orchestrator/SKILL.md)
> **维护命令**：`python scripts/bootstrap/sync_ai_memory.py`

---

## 0. 3 种 maintainer 模式

每个 `.md` 文件必须在 front matter 里声明 `maintainer`：

| 模式 | 含义 | 跑 sync 时的行为 |
|:----:|------|------------------|
| `auto` | 内容从 `source:` 路径自动生成 | **覆盖重写** body |
| `derived-manual` | 自动生成骨架，AI 追加手动注释 | **保留**已有 + 打 hint |
| `manual` | 完全人工维护，sync 跳过 | **跳过**（不打 hint） |

## 0.1 `ref/` 子目录手写参考文档加载顺序表 (spec-38 Phase 4 新增, P2 重构 2026-07-26)

`.ai-memory/ref/` 保留 7 个手写参考文档 (高频 AI 启动加载, P2 重构从根目录迁入), 4 个 auto-generated KB 在 `meta/auto-kb/`:

| 文件 | 用途 | 加载时机 |
|------|------|---------|
| [README.md](../README.md) | AI Memory 入口 + 3 种 maintainer 模式 | 新会话首次访问 .ai-memory/ 时 |
| [tech-stack.md](../docs/reference/tech-stack.md) | GAF 技术栈完整版 (v8.4) | L2 硬加载 (v9.5 升级) |
| [version-compat.md](../docs/reference/version-compat.md) | GAF 跨文件版本兼容 + 跨文件版本同步 (spec-38 Phase 6 合并) | L3 按需 (版本升级/依赖变更/TS 严格选项时) |
| [data-flow.md](../docs/reference/data-flow.md) | GAF 数据流 (v8.4 必读) | L2/L3 按需 (跨层数据流问题) |
| [cli-cheatsheet.md](../docs/reference/cli-cheatsheet.md) | GAF CLI 速查 (v8.4) | L3 按需 (命令速查) |
| [ref/session-context.md](ref/session-context.md) | 会话上下文 (auto-generated) | L2 自动 |
| [ref/spec-index.md](ref/spec-index.md) | spec 索引 (auto-generated) | L3 按需 (查 spec_id) |
| [ref/doc-health-report-schema.md](ref/doc-health-report-schema.md) | doc-health 报告 schema | L3 按需 (doc-health 治理) |

**4 个 auto-generated KB** (从根目录迁到 `meta/auto-kb/` 子目录, 2026-07-19):
- [meta/auto-kb/agent-protocol.md](meta/auto-kb/agent-protocol.md) — 16 种消息类型 + 5 字段帧 + TaskState 6 状态机
- [meta/auto-kb/api-endpoints.md](meta/auto-kb/api-endpoints.md) — 22 个 Django app 路由表 + Swagger UI 入口
- [meta/auto-kb/error-codes.md](meta/auto-kb/error-codes.md) — Agent 端 6 类 AutoBaseError + 后端异常 + DRF 状态码
- [meta/auto-kb/pipeline-nodes.md](meta/auto-kb/pipeline-nodes.md) — 37 个节点类型 @register_node 注册

**默认**：在 `lessons/` 下的文件若未声明 `maintainer` → 视作 `manual`，永不重写。

---

## 1. front matter 必填字段 (按 maintainer 模式差异化 — spec-39 Phase 7, 2026-07-19)

> **设计原则**: 不同 maintainer 模式有不同维护场景, 字段必填集合应差异化, 避免一刀切导致 auto 文件被 pre-commit 卡住 (auto 文件无法手工填 generated 等字段)

### 1.1 三种 maintainer 模式 + 必填字段

| 模式 | 场景 | 必填字段 | 选填字段 |
|:----:|------|---------|---------|
| **auto** | sync_ai_memory.py / sync_docs_index.py 自动生成 (auto-kb/* 等) | `maintainer`, `source`, `generated`, `auto_updated` (4 字段) | `load_when`, `priority`, `symptom`, `solution`, `related_files`, `created_by` (由脚本决定是否输出) |
| **derived-manual** | 手写为主但部分内容由脚本衍生 (failure-modes.md / docs/reference/version-compat.md / docs/reference/data-flow.md / docs/reference/cli-cheatsheet.md / docs-index.md / yn-matrices.md / archived-lessons.md 等) | `maintainer`, `source`, `load_when`, `priority`, `symptom`, `solution`, `related_files`, `auto_updated`, `last_manual_edit` (9 字段, 无 `created_by`/`generated`) | `created_by`, `generated` (可省略, 默认 `AI` + 文件 mtime) |
| **manual** | 完全手写 (lessons/* / docs/reference/tech-stack.md / summaries/* / platforms/* / games/* 等) | `maintainer`, `source`, `load_when`, `priority`, `symptom`, `solution`, `related_files`, `created_by` (8 字段) | `generated`, `auto_updated` (可省略, 默认 = 文件 mtime) |

### 1.2 通用模板 (按模式选)

**auto 模式** (4 必填):
```yaml
---
maintainer: auto
source: backend/foo/urls.py              # 脚本扫描根路径
generated: 2026-07-19                    # 脚本生成日期
auto_updated: 2026-07-19                 # 脚本写入时间
---
```

**derived-manual 模式** (9 必填):
```yaml
---
maintainer: derived-manual
source: backend/, agent/, frontend/, docs/
load_when: [必读]
priority: high
symptom: [kb:xxx, xxx]
solution: 一句话解决思路
related_files: [path/to/file.py]
auto_updated: 2026-07-19
last_manual_edit: 2026-07-19
---
```

**manual 模式** (8 必填):
```yaml
---
maintainer: manual
source: backend/foo/urls.py
load_when: [新功能, Bug修复]
priority: high|medium|low
symptom: [类别:子类别, 中文, 英文]
solution: 一句话解决思路
related_files: [path/to/file.py]
created_by: AI|user
---
```

**校验工具**：`python scripts/hooks/check_lessons_updated.py` (按 maintainer 模式差异化校验, N176 关联)
**`gaf-lessons-updated` pre-commit hook** 会自动跑这个校验。
**迁移**: 现有 frontmatter 不强制立即迁移; 下次修改文件时按本节模式对齐即可 (TD-282, P3)。

---

## 2. L1 / L2 / L3 加载策略

| 级别 | 时机 | 范围 | 典型文件 |
|:----:|------|------|----------|
| L1 | 启动时（< 1s）| 仅 `meta/failure-modes.md` (active N## 表格) | 兜底 |
| L2 | AI 任务开始（< 5s）| `meta/ai-operating-handbook.md` + `docs/reference/tech-stack.md` (2 文件, v9.5) | 必读 |
| L3 | 决策树路由后按需 | `docs/reference/version-compat.md` / `docs/reference/data-flow.md` / `docs/reference/cli-cheatsheet.md` / `meta/docs-index.md` / `meta/auto-kb/api-endpoints.md` / `meta/auto-kb/agent-protocol.md` / `lessons/` | 任务相关 |

完整策略见 [meta/ai-operating-handbook.md](meta/ai-operating-handbook.md)（v9.3 单一权威源）。

---

## 3. 目录结构（v8.4 N132 文档治理态, v9.6 P2 重构 2026-07-26）

```
.ai-memory/
├── README.md                 ← 本文件
├── ref/                      ← P2 重构 (2026-07-26): 7 个手写参考文档从根目录迁入
│   ├── tech-stack.md         ← L2 硬加载 (v9.5 升级)
│   ├── version-compat.md     ← L3 (v9.2 降级; v9.4 合并 version-sync.md)
│   ├── data-flow.md          ← L3
│   ├── cli-cheatsheet.md     ← L3
│   ├── session-context.md    ← L2 自动 (auto-generated)
│   ├── spec-index.md         ← L3 (auto-generated, sync_spec_index.py 输出)
│   └── doc-health-report-schema.md  ← L3 (doc-health 报告 schema)
├── loading-strategy.md       ← [已删除 v9.3, 合并入 meta/ai-operating-handbook.md]
├── evidence/
│   ├── active/               ← P1 重构: 活跃 evidence (30 天内)
│   ├── archived/             ← P1 重构: 归档 evidence (>30 天)
│   └── templates/            ← 3 步模板
├── lessons/                  ← 单次教训 (N## 编号, 按 topic 分类, 见 README.md)
├── summaries/                ← 累计汇总 (architecture-mistakes / code-rules / library-conflicts)
├── knowledge/                ← 4 份业务速查 (data-chain / error-recovery / task-lifecycle / terminology)
├── checklists/               ← 审计检查清单 (data-chain-checklist 8 步)
├── meta/
│   ├── failure-modes.md      ← L1, 失败模式索引 (N1-N132+ 详细 + 索引格式)
│   ├── ai-operating-handbook.md  ← L2, AI 操作手册 (v9.3 合并自 loading-strategy + ai-behavior-redlines)
│   ├── yn-matrices.md        ← N132 新增: Y/N 检查矩阵集中 (按 topic 分类, 从 SKILL.md 移出)
│   ├── docs-index.md         ← docs/ 索引 (auto-generated)
│   ├── spec-evolution.md     ← 季度 review 提示
│   ├── auto-kb/              ← spec-38 Phase 4: 4 个 auto-generated KB (agent-protocol/api-endpoints/error-codes/pipeline-nodes)
│   └── version-sync.md       ← [已删除 v9.4, 合并入 docs/reference/version-compat.md §10-§14]
├── ops/                      ← 审计脚本输出目标 (spec-36 清理后 + M2 回执 2026-08-15)
│   ├── bypass-patterns.md    ← 7 天 bypass 复盘 (scripts/lessons/bypass_weekly_review.py 输出)
│   ├── why-skipped.md        ← e2e 失败原因 (scripts/lessons/weekly_summary.py 输出)
│   └── claimed-activation.md ← commit N## 声称-激活率回执 (hooks/check_claimed_rules.py 输出, M2 2026-08-15)
├── games/browndust-ii/       ← 游戏特定 4 份（M1.A）
└── platforms/                ← 平台特定 5 份（M1.A）
```

> **spec-36 (2026-07-19) 清理说明**: 原 ops/ 5 个陈旧文件中 3 个删除 (completed-features/bug-tracker/deletion-queue 已被 docs/ 取代), monthly-health-checks/ 迁到 `docs/health/`; 仅保留 bypass-patterns.md + why-skipped.md 作为脚本输出目标。原 "运营记录 (bug/feature/bypass)" 职责已由 docs/{completed-features.md, tech-debt/} 取代。

**N132 文档职责分离** (2026-06-22, spec-36 2026-07-19 更新):
- `lessons/` — 单次教训历史 (按 topic 分类, 20 个 topic)
- `summaries/` — 累计汇总 (规则汇总, 非单次教训)
- `meta/failure-modes.md` — 失败模式索引 (L1 硬加载)
- `meta/yn-matrices.md` — Y/N 检查矩阵集中 (从 SKILL.md 移出)
- `knowledge/` — 业务速查 (什么是 X)
- `checklists/` — 审计检查清单 (如何审计 X)
- `ops/` — 审计脚本输出目标 (bypass-patterns + why-skipped + M2 claimed-activation; 运营记录已迁 docs/)
- `games/` — 游戏特定速查 (M1.A)
- `platforms/` — 平台特定速查 (M1.A)

---

## 4. 常用命令

```bash
# 同步（按 maintainer 模式分发）
python scripts/bootstrap/sync_ai_memory.py

# 模糊查询 lessons
python scripts/bootstrap/sync_ai_memory.py --query popup
python scripts/bootstrap/sync_ai_memory.py --query 弹窗

# 校验
python scripts/hooks/check_lessons_updated.py
python scripts/hooks/check_spec_consistency.py
python scripts/hooks/check_3step_evidence.py
python scripts/bootstrap/sync_skills.py --check
```

---

## 5. AI 工作流

每次 AI 任务开工前必跑：

```bash
bash scripts/gaf_init.sh           # 7 步：env → dep → sync → evidence → AI 入口 → session
```

开工后，参考决策树（[`.skills/skills/gaf-orchestrator/SKILL.md`](../.skills/skills/gaf-orchestrator/SKILL.md)）路由到 5 个 skill。

写代码完成后：

```bash
# 1. 写 3 步 evidence
mkdir -p .ai-memory/evidence/active/$(date +%Y-%m-%d)-<task-name>
cp .ai-memory/evidence/templates/{problem,solution,verification}.md .ai-memory/evidence/active/$(date +%Y-%m-%d)-<task-name>/
# 填写 problem / solution / verification
# P1 重构 (2026-07-26): evidence 必须放在 active/ 下, 30 天后由 startup_checks.py 自动迁到 archived/

# 2. 写 lesson（如有新坑）
# 参考 .ai-memory/lessons/archived-early/2026-06-10-agent-popup-bug.md 模板

# 3. sync 验证
python scripts/bootstrap/sync_ai_memory.py

# 4. commit
bash scripts/gaf-commit.sh -m "..."
# 或紧急：GAF_BYPASS_REASON="<原因>" bash scripts/gaf-commit.sh --no-verify -m "..."
```
