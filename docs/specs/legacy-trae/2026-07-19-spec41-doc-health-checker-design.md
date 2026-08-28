---
spec_id: spec-41
title: 文档健康检查器 (静态层 7 维度) — 自我进化飞轮基础
created: 2026-07-19
status: design
applies_to: [scripts, .ai-memory, docs, .trae]
related_skills: [gaf-orchestrator, gaf-reflect-and-evolve]
related_lessons: [N167, N171, N176]
parent_spec: spec-39 (docs content sync baseline)
child_specs: [spec-42 (自我进化飞轮), spec-43 (遗忘机制), spec-44 (月度检查瘦身)]
---

# Spec-41: 文档健康检查器 (静态层 7 维度)

> **范围声明**: 本 spec 只做静态层 7 维度扫描 + report.json + gaf_init.sh 接入。
> AI patch 流程 (B 自我进化飞轮) 在 spec-42。遗忘机制 (C) 在 spec-43。月度检查瘦身 (D) 在 spec-44。

## 1. 背景与动机

### 1.1 用户原话

> "我希望有个检查可以在 ai 思维链和工作流和规则文档中, 这个两个文件夹下的文件是不是有职责重复, 或者冗余, 或者分配不好的问题, 结合 ai 思维链和工作流和规则文档和两个文件夹的内容, 再次评估 `/d:/code/GAF/docs` `/d:/code/GAF/.ai-memory`, 然后文件夹里的内容都是否是最新的, 这些代码或者架构变更都没有更新对应的文档吧, 在检查下规则文档是否有冲突的地方, 长期维护性, 以及文档的膨胀性..."

### 1.2 现状痛点

- spec-39 修复了 4 类 P0 文档问题 (路径漂移/计数硬编码/frontmatter 不差异/内容过期), 但**没有机制**防止下次再犯
- `gaf_governance_batch.py` 10 checks 偏 **规则一致性** (N## 索引/Y/N 矩阵/spec 一致性), **不覆盖**:
  - 文件级职责重复 (例: `data-flow.md` vs `architecture-overview.md` 数据流段是否有重叠)
  - 单文件膨胀 (例: `architecture-mistakes.md` 2940 行已超阈值)
  - 内容时效 (代码/架构变更后,文档 `last_updated` 是否同步)
- `monthly-health-check.md` 12 类检查是**月度人工评估**,反馈周期长,无法在每次会话启动时跑
- 用户诉求: **AI 自我进化, 人工不干预** → 需要机器可判定的检查维度, AI 消费报告后直接 patch + commit

### 1.3 设计目标

1. **零对话开销**: 静态层在 `gaf_init.sh` 跑完才进对话, 报告 JSON 一次性 Read, 对话中零额外开销
2. **机器可判定**: 7 维度全部用 Python 脚本确定性判定, 不依赖 LLM (LLM 分析在 spec-42)
3. **结构化报告**: JSON 输出, AI 可直接消费, 含 `suggested_fix` + `root_cause_hint`
4. **复用现有护栏**: 不新增 pre-commit hook, 静态层只产出报告, 不修改文件 (修改在 spec-42 由 AI 完成)
5. **N171 性能基线**: 单次执行 < 2s (与 gaf_governance_batch.py 1.56s 同量级)

### 1.4 非目标 (Out of Scope)

- ❌ AI 自动 patch 规则文档 → spec-42
- ❌ 遗忘机制改造 (重要性 × 触发频率 × 时间) → spec-43
- ❌ 月度检查 12 类瘦身为 5 类 → spec-44
- ❌ 语义层规则冲突检测 (需 LLM) → spec-42 L3-1 扫描时跑
- ❌ 修复本次扫描发现的具体问题 → 由 AI 在 spec-42 流程中处理

## 2. 架构设计

### 2.1 系统拓扑

```
gaf_init.sh 启动
    ↓ (existing)
sync_skills.py + sync_session_context.py + build_memory_index.py + sync_docs_index.py
    ↓ (NEW in spec-41)
[静态层] scripts/governance/doc_health_check.py (Python, <2s)
    ├─ 维度 1: 职责重复 (d1_overlap)
    ├─ 维度 2: 内容膨胀 (d2_bloat)
    ├─ 维度 3: 计数漂移 (d3_count_drift)
    ├─ 维度 4: 路径漂移 (d4_path_drift)
    ├─ 维度 5: frontmatter 三模式合规 (d5_frontmatter)
    ├─ 维度 6: 文档时效 (d6_staleness)
    └─ 维度 7: 索引一致性 (d7_index_consistency)
    ↓
输出: .cache/doc_health_report.json (machine-readable)
    ↓
AI 会话启动 (gaf-orchestrator L1 hard-load) → 读取 report.json
    ↓
报告进入 L3-1 扫描输入池 (等待用户触发"扫一下"或循环模式)
```

### 2.2 文件布局

```
scripts/governance/                          # NEW directory
├── __init__.py
├── doc_health_check.py                      # 主入口 (orchestrator)
├── thresholds.yaml                          # 阈值集中配置
├── report_schema.py                         # JSON schema + Pydantic models
└── check_dimensions/                        # 7 个维度独立模块
    ├── __init__.py
    ├── d1_overlap.py                        # 职责重复检测
    ├── d2_bloat.py                          # 内容膨胀检测
    ├── d3_count_drift.py                    # 计数漂移检测
    ├── d4_path_drift.py                     # 路径漂移检测
    ├── d5_frontmatter.py                    # frontmatter 合规检测
    ├── d6_staleness.py                      # 文档时效检测
    └── d7_index_consistency.py              # 索引一致性检测

scripts/tests/
└── test_doc_health_check.py                 # 单元测试 (7 维度各 3+ cases)

.cache/
└── doc_health_report.json                   # 输出 (gitignored)

.ai-memory/
└── doc-health-report-schema.md              # 报告 schema 说明 (供 AI 消费)
```

### 2.3 与现有系统的关系

| 现有系统 | 关系 | 区别 |
|--------|-----|------|
| `gaf_governance_batch.py` (10 checks) | **互补** | governance_batch 偏规则一致性 (N##/Y/N/spec), doc_health 偏文档健康 (重复/膨胀/时效) |
| `monthly-health-check.md` (12 类) | **替代 7/12 类** | spec-44 中 7 类静态检查迁到 doc_health, 月度只保留 5 类深度评估 |
| `sync_skills.py` | **不重叠** | sync_skills 是同步 (写文件), doc_health 是检查 (只读+报告) |
| `check_path_consistency.py` | **维度 4 复用** | 维度 4 调用 check_path_consistency 的逻辑, 不重复实现 |
| `sync_ai_memory.py` | **维度 5 复用** | 维度 5 调用 sync_ai_memory 的 frontmatter 校验逻辑 |
| `check_yn_matrices_index.py` | **维度 7 复用** | 维度 7 调用 check_yn_matrices_index 的索引一致性逻辑 |

**关键设计**: 不重复造轮子。维度 4/5/7 通过 `importlib` 调用现有脚本的 `main()` 或核心函数 (与 gaf_governance_batch.py v2 模式一致, N171 优化), 仅维度 1/2/3/6 是新实现。

**复用方式明细**:
- **d4_path_drift**: `importlib.import_module('scripts.hooks.check_path_consistency')` → 调用其 `check_paths()` 函数 (若不存在则抽取核心逻辑到 `check_path_consistency._check_path_exists()`)
- **d5_frontmatter**: `importlib.import_module('scripts.bootstrap.sync_ai_memory')` → 调用其 `validate_frontmatter(filepath, mode)` 函数 (若不存在则抽取到 `_validate_frontmatter()`)
- **d7_index_consistency**: `importlib.import_module('scripts.hooks.check_yn_matrices_index')` → 调用其 `check_index_consistency()` 函数 (若不存在则抽取到 `_check_index_consistency()`)

若现有脚本无合适函数可 import,则在 spec-41 Phase 3 中先 refactor 抽取核心逻辑到独立函数 (保留原脚本入口不变),再 importlib 调用。这是 N122 (新增前查同类) + DRY 原则的体现。

## 3. 7 维度详细设计

### 3.1 维度 1: 职责重复 (d1_overlap)

**检测目标**: 两个文件描述同一职责 (例: data-flow.md §3 vs architecture-overview.md §X 都在讲"异步消息队列")。

**检测方法**:
- 扫描 `docs/` + `.ai-memory/` 所有 `.md` 文件的 frontmatter `summary` + `applies_to` + H1/H2 标题
- 计算两两文件的 **Jaccard 相似度** (基于关键词集合)
- 阈值: summary 关键词 Jaccard > 0.6 → 报告 P2; > 0.8 → 报告 P1
- 关键词提取: 去 stopword + 词干化 + n-gram (2-3)

**输入**: `docs/**/*.md`, `.ai-memory/**/*.md` (排除 `lessons/`, `evidence/`, `meta/archived-lessons.md`)

**输出**:
```json
{
  "dimension": "d1_overlap",
  "severity": "P2",
  "files": ["docs/general/design/data-flow.md", ".ai-memory/data-flow.md"],
  "evidence": "summary Jaccard=0.72, shared keywords: [异步, Celery, Channels, 消息队列]",
  "suggested_fix": "检查两文件是否需要合并, 或在 summary 中明确区分用途",
  "root_cause_hint": "可能历史遗留: 一个面向用户 (docs/), 一个面向 AI (.ai-memory/), 但 summary 未差异化"
}
```

**白名单** (已知合理重复, 不报告):
- `docs/standards/*.md` vs `backend/<app>/README.md` (规范 vs 子 app 约定)
- `.ai-memory/lessons/*.md` (教训本身允许跨文件引用同一 N##)

### 3.2 维度 2: 内容膨胀 (d2_bloat)

**检测目标**: 单文件超过健康行数阈值, 可能承担过多职责。

**检测方法**:
- 统计每个 `.md` 文件行数 (wc -l 等价)
- 阈值 (在 `thresholds.yaml` 集中配置):
  - `.ai-memory/summaries/architecture-mistakes.md`: 1500 行 (当前 2940, 1.96x → P2)
  - `.ai-memory/meta/yn-matrices/_workflow.md`: 1200 行 (当前 609, 未触发)
  - `docs/general/**/*.md`: 2000 行
  - `.trae/rules/project_rules.md`: 1500 行 (当前 ~1100, 未触发)
  - 其他 `.md`: 默认 1000 行
- severity 区间 (基于 ratio = actual_lines / threshold):
  - `1.5 ≤ ratio < 2.0` → P2
  - `2.0 ≤ ratio < 3.0` → P1
  - `ratio ≥ 3.0` → P0

**输出**:
```json
{
  "dimension": "d2_bloat",
  "severity": "P2",
  "file": ".ai-memory/summaries/architecture-mistakes.md",
  "evidence": "2940 lines, threshold=1500, ratio=1.96x (falls in [1.5, 2.0) → P2)",
  "suggested_fix": "按主题拆分为 _workflow-architecture.md / _data-flow-architecture.md / _api-architecture.md",
  "root_cause_hint": "历史堆积: 多次 spec 修复追加教训, 未触发拆分阈值"
}
```

### 3.3 维度 3: 计数漂移 (d3_count_drift)

**检测目标**: 文档中硬编码的计数与实际不符 (spec-39 已修 3 处, 但新写入的硬编码会再犯)。

**检测方法**:
- Grep 文档中的数字 + 上下文关键词:
  - `N\d+ Active` → 与 `failure-modes.md` 实际 N## 计数对比
  - `\d+ docs` → 与 `docs/` 实际 .md 计数对比
  - `\d+ 个 sub-file` → 与 `yn-matrices/_*.md` 实际计数对比
  - `\d+ 条` (在 lessons/README.md 上下文) → 与 lessons 实际计数对比
- 任何硬编码计数 + 上下文未标"动态计数" → P2
- 硬编码计数 + 实际计数差 > 0 → P1

**输出**:
```json
{
  "dimension": "d3_count_drift",
  "severity": "P1",
  "file": ".ai-memory/meta/failure-modes.md",
  "line": 45,
  "evidence": "硬编码 '51 条 Active N##' vs 实际 53 条",
  "suggested_fix": "改为 '动态计数, 由 gaf_init.sh 自动统计' 或更新数字",
  "root_cause_hint": "新增 N## 时未同步计数 (spec-39 修复过, 但新 N## 写入会再犯)"
}
```

### 3.4 维度 4: 路径漂移 (d4_path_drift)

**检测目标**: frontmatter `related_files` / 文档正文路径与实际文件系统不符。

**检测方法**:
- **复用** `check_path_consistency.py` 的核心逻辑 (importlib 调用)
- 扫描所有 `.md` 的 frontmatter `related_files` + 正文 `file:///` 链接 + 反引号路径
- 对每个路径 `os.path.exists()` 检查
- 不存在 → P0 (影响 AI 引用)

**输出**:
```json
{
  "dimension": "d4_path_drift",
  "severity": "P0",
  "file": ".ai-memory/lessons/workflow_2026-07-19-n176.md",
  "line": 8,
  "evidence": "related_files entry 'docs/general/specs/2026-07-17-xxx.md' does not exist",
  "suggested_fix": "更新路径或删除该 related_files 条目",
  "root_cause_hint": "文件移动/删除后未同步 frontmatter (spec-39 TD-281 同类问题)"
}
```

### 3.5 维度 5: frontmatter 三模式合规 (d5_frontmatter)

**检测目标**: frontmatter 不符合 `auto` / `derived-manual` / `manual` 三模式之一 (spec-39 Phase 7 已定义, TD-282 check_lessons_updated.py 未差异化)。

**检测方法**:
- **复用** `sync_ai_memory.py` 的 frontmatter 校验逻辑
- 三模式必填字段 (单一权威源: `.ai-memory/README.md` §1):
  - `auto` (4 必填): maintainer/source/generated/auto_updated
  - `derived-manual` (9 必填): + load_when/priority/symptom/solution/related_files/last_manual_edit
  - `manual` (8 必填): + created_by (无 generated/auto_updated)
- 缺字段 → P1; 字段类型错误 → P2

**输出**:
```json
{
  "dimension": "d5_frontmatter",
  "severity": "P1",
  "file": ".ai-memory/lessons/workflow_2026-07-19-n176.md",
  "evidence": "maintainer=manual but missing 'created_by' field",
  "suggested_fix": "添加 created_by: AI 或改为 maintainer=derived-manual",
  "root_cause_hint": "新写 lesson 时未按三模式规范填写 frontmatter"
}
```

### 3.6 维度 6: 文档时效 (d6_staleness)

**检测目标**: 文档 `last_updated` 距今 > 90 天, 且 `applies_to` 命中近期 commit 涉及的模块 → 内容可能过期。

**检测方法**:
- 读 frontmatter `last_updated` + `applies_to`
- 计算距今天数
- **applies_to → 目录映射规则** (在 thresholds.yaml 配置):
  - `backend` → `backend/`
  - `frontend` → `frontend/src/`
  - `agent` → `agent/src/`
  - `scripts` → `scripts/`
  - `docs` → 跳过 (docs 自身变更不影响代码文档时效)
  - `project` → 全仓 (除 docs/, .ai-memory/)
- 用 `git log --since="<last_updated>" --name-only -- <mapped_dir>` 取该文档 applies_to 模块下后续 commit 涉及的文件
- 若有 > 0 个后续 commit 涉及 → P1 (文档可能未同步)
- 若 > 5 个后续 commit 涉及 → P0

**输出**:
```json
{
  "dimension": "d6_staleness",
  "severity": "P1",
  "file": "docs/standards/api-contract.md",
  "evidence": "last_updated=2026-07-02, 17 commits since then touching backend/api/ and backend/consumers/",
  "suggested_fix": "Read 文档 + 对比近期 commit diff, 更新 last_updated",
  "root_cause_hint": "代码变更未触发文档同步 (需 spec-42 自我进化飞轮闭环)"
}
```

### 3.7 维度 7: 索引一致性 (d7_index_consistency)

**检测目标**: `failure-modes.md` Active N## vs `lessons/README.md` topic 表 vs `yn-matrices/_*.md` 索引三方一致。

**检测方法**:
- **复用** `check_yn_matrices_index.py` 的核心逻辑
- 三方对比:
  - `failure-modes.md` 中 `| N\d+ |` 行 → Active N## 集合 A
  - `lessons/README.md` topic 表中 `N\d+` 列表 → 集合 B
  - `yn-matrices/_*.md` 中引用的 N## → 集合 C
- A - B ≠ ∅ → P1 (failure-modes 有但 lessons/README.md 未登记, spec-39 N176 已踩过)
- B - A ≠ ∅ → P2 (lessons/README.md 有但 failure-modes 已归档)
- A - C ≠ ∅ → P2 (failure-modes 有但 yn-matrices 未引用, 可能 L1-小/中 不需要)

**输出**:
```json
{
  "dimension": "d7_index_consistency",
  "severity": "P1",
  "evidence": "N176 in failure-modes.md Active but missing from lessons/README.md topic 'workflow'",
  "suggested_fix": "在 lessons/README.md workflow topic 行追加 N176",
  "root_cause_hint": "新沉淀 N## 时未三处同步 (spec-39 N176 已修复, 防止下次再犯)"
}
```

## 4. 报告 Schema

### 4.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "GAF Doc Health Report",
  "type": "object",
  "required": ["generated_at", "git_sha", "summary", "issues"],
  "properties": {
    "generated_at": {"type": "string", "format": "date-time"},
    "git_sha": {"type": "string", "pattern": "^[0-9a-f]{7,40}$"},
    "duration_seconds": {"type": "number"},
    "summary": {
      "type": "object",
      "required": ["total", "by_severity", "by_dimension"],
      "properties": {
        "total": {"type": "integer"},
        "by_severity": {
          "type": "object",
          "properties": {
            "P0": {"type": "integer"},
            "P1": {"type": "integer"},
            "P2": {"type": "integer"}
          }
        },
        "by_dimension": {
          "type": "object",
          "properties": {
            "d1_overlap": {"type": "integer"},
            "d2_bloat": {"type": "integer"},
            "d3_count_drift": {"type": "integer"},
            "d4_path_drift": {"type": "integer"},
            "d5_frontmatter": {"type": "integer"},
            "d6_staleness": {"type": "integer"},
            "d7_index_consistency": {"type": "integer"}
          }
        }
      }
    },
    "issues": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "dimension", "severity", "evidence", "suggested_fix", "root_cause_hint", "consumed"],
        "properties": {
          "id": {"type": "string", "description": "稳定 hash, 用于 consumed 标记"},
          "dimension": {"type": "string", "enum": ["d1_overlap", "d2_blast", "d3_count_drift", "d4_path_drift", "d5_frontmatter", "d6_staleness", "d7_index_consistency"]},
          "severity": {"type": "string", "enum": ["P0", "P1", "P2"]},
          "file": {"type": "string"},
          "line": {"type": "integer"},
          "files": {"type": "array", "items": {"type": "string"}},
          "evidence": {"type": "string"},
          "suggested_fix": {"type": "string"},
          "root_cause_hint": {"type": "string"},
          "consumed": {"type": "boolean", "default": false}
        }
      }
    }
  }
}
```

### 4.2 issue.id 稳定 hash 算法

```
id = sha1(f"{dimension}|{file}|{line}|{evidence}").hexdigest()[:12]
```

**目的**: 同一问题多次扫描 id 不变, AI patch 后标 `consumed=true`, 下次扫描若已修复则不再出现 (因为 evidence 不再匹配); 若未修复则 id 不变, AI 可识别"上次未处理"。

### 4.3 .cache/doc_health_report.json 示例

```json
{
  "generated_at": "2026-07-19T15:30:00+08:00",
  "git_sha": "-",
  "duration_seconds": 1.82,
  "summary": {
    "total": 12,
    "by_severity": {"P0": 1, "P1": 5, "P2": 6},
    "by_dimension": {
      "d1_overlap": 2,
      "d2_bloat": 1,
      "d3_count_drift": 0,
      "d4_path_drift": 1,
      "d5_frontmatter": 0,
      "d6_staleness": 5,
      "d7_index_consistency": 3
    }
  },
  "issues": [
    {
      "id": "a3f4b2c1d5e6",
      "dimension": "d4_path_drift",
      "severity": "P0",
      "file": ".ai-memory/lessons/workflow_2026-07-19-n176.md",
      "line": 8,
      "evidence": "related_files entry 'docs/general/specs/2026-07-17-xxx.md' does not exist",
      "suggested_fix": "更新路径或删除该 related_files 条目",
      "root_cause_hint": "文件移动/删除后未同步 frontmatter",
      "consumed": false
    }
  ]
}
```

## 5. 阈值配置 (thresholds.yaml)

```yaml
# GAF Doc Health Check thresholds
# Single source of truth for all 7 dimensions

# d1_overlap: 职责重复
d1_overlap:
  summary_jaccard_p2: 0.6    # P2 阈值
  summary_jaccard_p1: 0.8    # P1 阈值
  whitelist:
    - "docs/standards/*.md vs backend/*/README.md"  # 规范 vs 子 app
    - ".ai-memory/lessons/*.md"                      # 教训允许跨文件引用

# d2_bloat: 内容膨胀
d2_bloat:
  per_file_thresholds:
    ".ai-memory/summaries/architecture-mistakes.md": 1500
    ".ai-memory/meta/yn-matrices/_workflow.md": 1200
    ".trae/rules/project_rules.md": 1500
    "docs/general/**/*.md": 2000
    "default": 1000
  severity_multipliers:
    p2: 1.5    # 1.5x threshold → P2
    p1: 2.0    # 2.0x threshold → P1
    p0: 3.0    # 3.0x threshold → P0

# d3_count_drift: 计数漂移
d3_count_drift:
  patterns:
    - regex: "(\\d+)\\s+(?:条\\s+)?Active\\s+N##"
      counter: "count_active_n_in_failure_modes"
    - regex: "(\\d+)\\s+docs"
      counter: "count_docs_in_directory"
    - regex: "(\\d+)\\s+个\\s+sub-file"
      counter: "count_yn_matrices_subfiles"
  allow_dynamic_marker: "动态计数"   # 文档中标注此关键词则豁免

# d4_path_drift: 路径漂移 (复用 check_path_consistency.py)
d4_path_drift:
  severity: P0   # 路径不存在一律 P0

# d5_frontmatter: frontmatter 合规 (复用 sync_ai_memory.py)
d5_frontmatter:
  modes:
    auto:
      required: [maintainer, source, generated, auto_updated]
    derived-manual:
      required: [maintainer, source, load_when, priority, symptom, solution, related_files, last_manual_edit]
    manual:
      required: [maintainer, source, load_when, priority, symptom, solution, related_files, created_by]
  missing_field_severity: P1
  wrong_type_severity: P2

# d6_staleness: 文档时效
d6_staleness:
  stale_days_p2: 60     # 60 天未更新 → P2
  stale_days_p1: 90     # 90 天未更新 + 命中近期 commit → P1
  stale_days_p0: 180    # 180 天未更新 + 命中 ≥ 5 个近期 commit → P0
  commit_lookback: true # 检查 applies_to 模块的后续 commit
  applies_to_dir_mapping:
    backend: "backend/"
    frontend: "frontend/src/"
    agent: "agent/src/"
    scripts: "scripts/"
    docs: null             # null = 跳过 (docs 自身变更不影响代码文档时效)
    project: "*"           # 全仓 (除 docs/, .ai-memory/)

# d7_index_consistency: 索引一致性 (复用 check_yn_matrices_index.py)
d7_index_consistency:
  a_minus_b_severity: P1   # failure-modes 有但 lessons/README.md 无
  b_minus_a_severity: P2   # lessons/README.md 有但 failure-modes 已归档
  a_minus_c_severity: P2   # failure-modes 有但 yn-matrices 无 (L1-小/中 可能不需要)
```

## 6. gaf_init.sh 接入

### 6.1 接入位置

```bash
# scripts/gaf_init.sh (现有结构)

# ... existing sync steps ...
echo "[gaf_init] Step 4: sync_skills.py"
python scripts/bootstrap/sync_skills.py

# NEW: doc health check
echo "[gaf_init] Step 5: doc_health_check.py (NEW spec-41)"
python scripts/governance/doc_health_check.py --output .cache/doc_health_report.json

# ... rest of existing steps ...
```

### 6.2 性能预算

| 步骤 | 耗时 | 备注 |
|-----|-----|-----|
| 维度 1 (d1_overlap) | ~0.5s | Jaccard 计算, 文件数 ~50 |
| 维度 2 (d2_bloat) | ~0.1s | wc -l 等价 |
| 维度 3 (d3_count_drift) | ~0.2s | Grep + 计数 |
| 维度 4 (d4_path_drift) | ~0.3s | 复用 check_path_consistency |
| 维度 5 (d5_frontmatter) | ~0.3s | 复用 sync_ai_memory 校验 |
| 维度 6 (d6_staleness) | ~0.3s | git log 调用 |
| 维度 7 (d7_index_consistency) | ~0.1s | 复用 check_yn_matrices_index |
| **总计** | **~1.8s** | 符合 N171 < 2s 基线 |

### 6.3 失败处理

- 任何维度抛异常 → 该维度 issue 记 `{"dimension": "dX", "severity": "P0", "evidence": "check crashed: <error>", "consumed": false}`, 其他维度继续
- 脚本退出码: 0 (报告生成成功, 即使有 P0 issues) / 1 (报告生成失败)
- gaf_init.sh 不因 doc_health_check 失败而中断 (报告缺失不阻塞 AI 会话)

## 7. AI 消费协议

### 7.1 AI 会话启动时

`gaf-orchestrator` L1 hard-load 阶段追加一步:

```
L1 hard-load:
  1. failure-modes.md (existing)
  2. doc_health_report.json (NEW spec-41) ← Read .cache/doc_health_report.json
     - 若 total > 0: 在会话首条消息附"⚠️ doc health: N issues (P0:X/P1:Y/P2:Z), 详见 .cache/doc_health_report.json"
     - 若 P0 > 0: 强制提示用户"启动后建议先跑 L3-1 扫描处理 P0 issues"
```

### 7.2 L3-1 扫描时

用户触发"扫一下" / "评估一下" / 循环模式激活时, AI:

1. Read `.cache/doc_health_report.json`
2. 按优先级排序: P0 → P1 → P2
3. 对每个 `consumed=false` 的 issue:
   - 读取 `suggested_fix` + `root_cause_hint`
   - 执行 patch (Edit 工具)
   - 标记 `consumed=true` (写回 JSON)
4. 走 N176 单对话单 commit

**注**: L3-1 扫描的 AI patch 流程属于 spec-42 范围。spec-41 只负责产出报告 + AI 读取报告,不实现 patch。

## 8. 测试策略

### 8.1 单元测试 (scripts/tests/test_doc_health_check.py)

每个维度 3+ cases:

```python
# d1_overlap
def test_d1_overlap_detects_duplicate_summary(): ...
def test_d1_overlap_whitelist_skips_standards_vs_readme(): ...
def test_d1_overlap_no_false_positive_on_unrelated_files(): ...

# d2_bloat
def test_d2_bloat_triggers_p1_at_2x_threshold(): ...
def test_d2_bloat_uses_per_file_threshold(): ...
def test_d2_bloat_skips_files_under_threshold(): ...

# d3_count_drift
def test_d3_count_drift_detects_hardcoded_n_count(): ...
def test_d3_count_drift_skips_dynamic_marker(): ...
def test_d3_count_drift_handles_missing_failure_modes(): ...

# d4_path_drift (复用 check_path_consistency 测试模式)
def test_d4_path_drift_detects_missing_file(): ...
def test_d4_path_drift_validates_frontmatter_related_files(): ...

# d5_frontmatter
def test_d5_frontmatter_auto_mode_missing_field(): ...
def test_d5_frontmatter_manual_mode_missing_created_by(): ...
def test_d5_frontmatter_derived_manual_all_fields_present(): ...

# d6_staleness
def test_d6_staleness_p1_when_90_days_and_commit_touches_module(): ...
def test_d6_staleness_skips_when_no_related_commits(): ...

# d7_index_consistency
def test_d7_detects_n_in_failure_modes_missing_from_lessons_readme(): ...
def test_d7_detects_archived_n_still_in_lessons_readme(): ...
```

### 8.2 集成测试

```python
def test_doc_health_check_full_pipeline(tmp_path):
    """End-to-end: 7 维度全跑, 生成 report.json, schema 校验"""
    ...

def test_doc_health_check_performance_under_2s():
    """N171: 单次执行 < 2s"""
    import time
    start = time.time()
    subprocess.run(["python", "scripts/governance/doc_health_check.py"])
    assert time.time() - start < 2.0
```

### 8.3 不修改文件的断言

```python
def test_doc_health_check_does_not_modify_files():
    """关键约束: 静态层只读, 不写"""
    before = hashlib.md5(open(".ai-memory/data-flow.md").read().encode()).hexdigest()
    subprocess.run(["python", "scripts/governance/doc_health_check.py"])
    after = hashlib.md5(open(".ai-memory/data-flow.md").read().encode()).hexdigest()
    assert before == after
```

## 9. 实施阶段拆分

### Phase 1: 基础设施 (1 commit)
- 创建 `scripts/governance/` 目录 + `__init__.py`
- 写 `report_schema.py` (Pydantic models)
- 写 `thresholds.yaml`
- 写 `doc_health_check.py` 主入口 (orchestrator, 7 维度 stub)
- 写 `.ai-memory/doc-health-report-schema.md` (供 AI 消费)

### Phase 2: 维度 1-3 (新实现)
- 实现 `d1_overlap.py` + 3 单元测试
- 实现 `d2_bloat.py` + 3 单元测试
- 实现 `d3_count_drift.py` + 3 单元测试

### Phase 3: 维度 4-5-7 (复用现有)
- 实现 `d4_path_drift.py` (复用 check_path_consistency)
- 实现 `d5_frontmatter.py` (复用 sync_ai_memory)
- 实现 `d7_index_consistency.py` (复用 check_yn_matrices_index)
- 各 + 3 单元测试

### Phase 4: 维度 6 (新实现)
- 实现 `d6_staleness.py` (git log 调用)
- + 2 单元测试

### Phase 5: gaf_init.sh 接入 + 集成测试
- 修改 `scripts/gaf_init.sh` 追加 Step 5
- 写 `test_doc_health_check_full_pipeline`
- 写 `test_doc_health_check_performance_under_2s`
- 写 `test_doc_health_check_does_not_modify_files`

### Phase 6: 全量回归 + commit + C-068
- 跑 `pytest scripts/tests/test_doc_health_check.py`
- 跑 `gaf_governance_batch.py` 确认无回归
- 手动跑 `gaf_init.sh` 确认 report.json 生成
- N171 性能测量: `Measure-Command { python scripts/governance/doc_health_check.py }`
- 更新 `completed-features.md` C-068
- N176: spec-41 hash 字段留空, 下次 spec commit 时回填

## 10. N167 七维度评分 (spec-41 自评)

| 维度 | 分数 | 理由 |
|-----|-----|-----|
| 1. 架构长远性 | 5/5 | 7 维度模块化, 阈值集中配置, 复用现有脚本, 支持 spec-42/43/44 扩展 |
| 2. 全局归一化 | 5/5 | 与 gaf_governance_batch.py 模式一致 (importlib 复用), 报告 schema 单一权威源 |
| 3. 新旧兼容方案 | 5/5 | 单人项目, 一次性新增, 无旧系统兼容 |
| 4. 现有业务完善 | 4/5 | 覆盖 7 维度, 但 d6_staleness 的 applies_to → commit 模块映射可能不完整 |
| 5. 性能资源优化 | 5/5 | <2s, 复用 importlib 模式 (N171 验证), 失败不阻塞 gaf_init.sh |
| 6. 安全合规加固 | 4/5 | 静态层只读不写, 但未限制报告文件大小 (极端情况可能膨胀) |
| 7. 长期维护成本 | 5/5 | 阈值 YAML 集中配置, 7 维度独立模块, 单元测试覆盖, AI 自消费报告 |
| **总分** | **33/35** | 通过 (≥ 19 且领先 ≥ 5 分阈值) |

## 11. 验收标准

### 11.1 功能验收

- [ ] `python scripts/governance/doc_health_check.py` 生成 `.cache/doc_health_report.json`
- [ ] JSON 通过 schema 校验
- [ ] 7 维度各至少触发 1 个 issue (在当前 codebase 上跑)
- [ ] 单次执行 < 2s (N171)
- [ ] 不修改任何源文件 (静态层只读)

### 11.2 集成验收

- [ ] `gaf_init.sh` 追加 Step 5 后正常执行
- [ ] AI 会话启动时能 Read `.cache/doc_health_report.json`
- [ ] 现有 pre-commit hooks (gaf_governance_batch.py 10 checks) 无回归

### 11.3 文档验收

- [ ] `.ai-memory/doc-health-report-schema.md` 已创建
- [ ] `scripts/README.md` 已更新 (新增 doc_health_check.py 条目)
- [ ] `completed-features.md` C-068 已添加

## 12. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|-----|-----|-----|-----|
| d1_overlap Jaccard 误报 (不相关文件被标重复) | 中 | 低 (P2 only) | 白名单 + 关键词提取调优 |
| d6_staleness git log 慢 (大仓库) | 低 | 中 | 限制 --since 范围到 last_updated 之后 |
| 复用 sync_ai_memory 失败影响 d5 | 低 | 中 | try/except 隔离, 单维度失败不阻塞 |
| report.json 膨胀 (issues 数百条) | 中 | 低 | AI 消费后标 consumed=true, 旧报告 7 天后自动覆盖 |
| 阈值不合理 (太多/太少误报) | 中 | 中 | thresholds.yaml 集中配置, 跑 1 周后调优 |

## 13. 后续 spec 依赖

- **spec-42** (自我进化飞轮): 实现AI patch 流程, 消费 spec-41 报告
- **spec-43** (遗忘机制): trigger_count.json + 三维度评分, 接入 d6_staleness
- **spec-44** (月度检查瘦身): 7 类静态检查从 monthly-health-check.md 迁到 doc_health_check.py

---

## 附录 A: 与现有 monthly-health-check.md 12 类映射

| monthly-health-check 类 | spec-41 维度 | 处理 |
|------------------------|-------------|-----|
| A. 架构层 | - | 月度保留 (需 LLM) |
| B. 文档层 — 路径漂移 | d4_path_drift | ✅ 迁自动 |
| C. 文档层 — frontmatter | d5_frontmatter | ✅ 迁自动 |
| D. 文档层 — 计数漂移 | d3_count_drift | ✅ 迁自动 |
| E. 规则层 — N## 索引 | d7_index_consistency | ✅ 迁自动 |
| F. 规则层 — Y/N 矩阵 | d7_index_consistency | ✅ 迁自动 |
| G. 文档层 — 文件膨胀 | d2_bloat | ✅ 迁自动 |
| H. 文档层 — 内容时效 | d6_staleness | ✅ 迁自动 |
| I. 业务逻辑层 | - | 月度保留 (需 LLM) |
| J. 集成层 | - | 月度保留 (需 LLM) |
| K. 多 app 层 | - | 月度保留 (需 LLM) |
| L. 用户场景层 | d1_overlap (部分) | 月度保留主体 |

**结论**: 12 类中 7 类 (B/C/D/E/F/G/H) 可迁自动, 5 类 (A/I/J/K/L) 月度保留。

## 附录 B: N171 性能基线对照

| 脚本 | 基线 | spec-41 预期 |
|-----|-----|-------------|
| gaf_governance_batch.py (10 checks) | 1.56s | - |
| sync_ai_memory.py | < 1s | - |
| sync_skills.py | < 0.5s | - |
| **doc_health_check.py (7 dims)** | **< 2s** | **~1.8s** |

## 附录 C: 失败模式登记

本 spec 实施过程中若发现新反模式, 登记到:
- `failure-modes.md` N## 索引
- `lessons/workflow_<date>-<n##>.md`
- `yn-matrices/_workflow.md` (若 L1-大)

按 §6.2 L0/L1 子分级分发。
