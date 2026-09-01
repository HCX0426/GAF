---
maintainer: derived-manual
source: Split from yn-matrices/_workflow.md (Phase 4 拆分优化 2026-07-26)
generated: 2026-07-26
auto_updated: 2026-07-26
last_manual_edit: 2026-07-26
load_when: [commit, hook, skill, pre-commit, .trash, 文件命名, git]
priority: high
symptom: [workflow-commit, commit-spec, hook-failure, skill-sync, trash-cleanup]
solution: commit/hook/skill 治理 Y/N 矩阵 (N95/N96/N114/N117/N122/N124/N125/N126/N140/N150/N165/N169/N170) + evidence_source 表; 详见 §1 各家族
related_files:
  - .skills/rules/project_rules.md
  - .pre-commit-config.yaml
  - scripts/hooks/gaf_governance_batch.py
---

# _workflow-commit.md — commit/hook/skill 治理 Y/N 矩阵

> 原 `_workflow.md` (697 行) 按 N## 家族拆分为 3 sub-file。本文件主题: commit/hook/skill 治理 + Hook 失败映射 + .trash + 文件命名。姊妹文件: [_workflow-spec.md](_workflow-spec.md) (spec/plan/阶段/前端/技术债) | [_workflow-reflection.md](_workflow-reflection.md) (反思/工具纪律/bug 排查)

## evidence_source 总览 (Wave 2 — 2026-07-26, spec-2026-07-26-ai-governance-execution-rate-fix)

> 每项 Y/N 检查的真实执行 evidence 来源 (hook 名 / spec 字段 / pytest 输出). 满足 Wave 2 验收 "保留 3 sub-file, 每项含 evidence_source 字段".

| N## | evidence_source | 验证方式 |
|-----|-----------------|---------|
| N95 (分级分发) | `project_rules.md §6.2` L0/L1-小/中/大 子分级表 + lesson 文件 frontmatter `priority` 字段 | grep `priority:.*high\|priority:.*medium` .ai-memory/lessons/*.md |
| N96 (L1/L2/L3 加载) | `scripts/gaf_init.sh` (L1) + `sync_ai_memory.py` (L3) + Read 计数 in session | `bash scripts/gaf_init.sh` exit 0 + sync_ai_memory.py --query 返回条数 |
| N114 (pre-commit staged-only) | `.pre-commit-config.yaml` 4 hook `pass_filenames: true` + `types: [file]` | `grep "pass_filenames\|types:" .pre-commit-config.yaml` |
| N117 (决策树 changelog) | `scripts/bootstrap/sync_skills.py --changelog` + `decision-tree-changelog.md` 6 列表 | `pytest scripts/tests/test_sync_changelog.py` (6 tests) |
| N122 (scripts/ 维护) | `scripts/frontmatter.py` 复用 + `sync_docs_index.py` 重建 + e2e documentation 场景 | `pytest scripts/tests/test_e2e_run_all.py -k documentation` |
| N124/N125/N126 (工作流治理 + .trash + 诚实标记) | `.trash/README.md` manifest + grep "(N126 验证)" + `pending-roadmap.md §二.20` | `ls .trash/` + `grep "(N126 验证)" docs/` |
| N140 (文件命名禁版本号) | `Get-ChildItem -Recurse` 扫描 + git log 同一文件多次 commit | `Get-ChildItem -Recurse | Where BaseName -match 'v\d+'` 应空 |
| N150 (hook 失败根因修复) | `gaf_governance_batch.py` 13 check pass + TD-NNN 登记 + `--no-verify` 检查 | `git log --grep "no-verify"` 应空 + `pre-commit run --all-files` PASS |
| N165/N169/N170 (合并) | `project_rules.md §3.4` N170 硬约束 + `§4.8` N169 硬约束 + L2 handbook Part 2 | grep `N170\|N169` .skills/rules/project_rules.md |

## §1 workflow — commit/hook/skill 治理

### ⑥ N95 分级分发 Y/N 矩阵

> **单一权威源**: `project_rules.md §6.2` (L0/L1-小/L1-中/L1-大 子分级表 + 判定流程)
> 本节仅保留 Y/N 检查项, 完整判定流程和分发层表见 §6.2

| # | 检查项 | Y/N |
|:-:|--------|:---:|
| 1 | 写完教训后问了 2 个问题 (L0 vs L1? L1-小/中/大?) | |
| 2 | L1-小: 只更新 rules + handbook (2 层), 未创建 lesson/N##/Y/N 矩阵 | |
| 3 | L1-中: 更新 lesson + rules + handbook (3 层), 未写 Y/N 矩阵/N## | |
| 4 | L1-大: 5 层全分发 (lesson + arch-mistakes + yn-matrices + rules + failure-modes 索引) | |
| 5 | 未把小改动过度分发 (反例: N170 分发到 7 个地方) | |

### ⑦ N96 L1/L2/L3 加载 Y/N 矩阵（必填，缺一层即视为未闭环）

| 层级 | 触发 | 验证 | Y/N |
|------|------|------|:---:|
| L1 启动 | `bash GAF/scripts/gaf_init.sh` | failure-modes.md `^\| N[0-9]+` entries ≥ 5 (表格格式) | |
| L2 路由 | gaf-orchestrator 决策树 step_1 后 | `meta/ai-operating-handbook.md` 1 文件 Read (v9.3 合并自 loading-strategy + ai-behavior-redlines; v9.4 version-sync 合并入 version-compat; tech-stack/docs-index/version-compat 降 L3) | |
| L3 按需 | skill 内部 grep | `sync_ai_memory.py --query <keyword>` 跑过 + 返回条数 | |

**AI 必做**:
- 必跑 `gaf_init.sh` (L1 硬加载触发)
- 必 Read 1 个 L2 文件 `ai-operating-handbook.md` (v9.3 单一权威源, 不允许跳过)
- 必跑 `sync_ai_memory.py --query <keyword>` (L3 按需)

### ⑬ N114 pre-commit hook staged-only Y/N 矩阵（必填）

> **触发条件**（任意一条即触发）:
> - AI 写/改 `.pre-commit-config.yaml` 中 eslint / prettier / ruff / mypy 任一 hook
> - AI 遇到 pre-commit 阻塞 (ruff/mypy 报历史错误, commit 失败)
> - 用户反馈 "pre-commit hook 怎么还在扫全项目" / "怎么改个文件要等 5 分钟"
> - N110 根因修复场景: 项目历史 lint 错误累积, 阻塞新代码 commit

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | `pass_filenames: true` (或 default) | | `grep "pass_filenames" .pre-commit-config.yaml` |
| 2 | `types: [file]` 显式声明 | | `grep "types:" .pre-commit-config.yaml` |
| 3 | entry 不 hardcode 路径 (如 `backend/ agent/`) | | `grep "entry:" .pre-commit-config.yaml` |
| 4 | `files: <regex>` 限定触发范围 | | `grep "files:" .pre-commit-config.yaml` |
| 5 | hook name 含 "(staged only — N110 fix)" | | `grep "N110 fix" .pre-commit-config.yaml` |
| 6 | 跑 pre-commit 验证: `pre-commit run <hook_id> --files <staged_file>` | | (跳过, 等真 commit 时验证) |

**AI 必做**:
- ✅ **N114 4 原则**: (1) `pass_filenames: true` 默认 (2) entry 不 hardcode 路径 (3) 明确 `types: [file]` (4) hook name 标 "(staged only — N110 fix)"
- ✅ **改前**: 用 `cat .pre-commit-config.yaml` 查 4 hook 当前配置
- ✅ **改后**: 用 `git diff .pre-commit-config.yaml` 确认 4 hook 改 staged-only
- ✅ **N110 治标 vs N114 治本**: `--no-verify` 是治标 (绕过 hook), 改 hook 是治本 (hook 不再误触)
- ❌ NEVER 写 `pass_filenames: false` + entry hardcode 路径 (N110 反模式)
- ❌ NEVER 写 `entry: ruff check backend/ agent/` (扫全项目)
- ❌ NEVER 写 `entry: mypy backend/` (扫全项目)
- ❌ NEVER 写 `entry: npm run lint --prefix frontend` (扫全 frontend)
- ❌ NEVER 写 `entry: npx prettier --check ... frontend/` (扫全 frontend)

**预防规则**（N114 提取）:
- pre-commit hook 写完 → 必跑 3 步验证: `git add <test_file>` + `git commit` + 验证 hook 只跑 1 文件
- 项目历史 lint 错 → 改 hook 为 staged-only (N114 修复), 不再触发
- 真要扫全项目 lint → 单独跑 `pre-commit run --all-files` (CI 用, 不在 commit 时跑)

**同根因家族**: N105 (hook 透传 bug) + N107 (path consistency 兜底) + N110 (项目历史 lint 阻塞) + **N114 (本条 hook 扫全项目 → staged files only)** —— 同根因 (pre-commit 框架误用)

> P-020 ActionChain Y/N 矩阵已归档到 archived-lessons.md（触发条件极窄）

### ⑰ N117 M1.H 决策树 changelog + 季度 review Y/N 矩阵

> **触发条件** (任意一条即触发):
> - 改 `gaf-orchestrator/SKILL.md` 中 `## Decision Tree` ↔ `## End Decision Tree` 块
> - 4 决策树副本任一 hash 漂移 (sync_skills.py --check 报错)
> - 季度首日 (1/1, 4/1, 7/1, 10/1) 跑 review
> - CI pre-commit 触发 `--changelog`

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 改 gaf-orchestrator/SKILL.md 决策树块后, 必跑 `python scripts/bootstrap/sync_skills.py --changelog` | | `git log` 看到对应 commit |
| 2 | `--changelog` 命令带 `--note` 参数 (可读 description) | | `grep "M1.H\|N##" decision-tree-changelog.md` |
| 3 | 表格格式 6 列 (# / date / old_hash / new_hash / note / author) 完整 | | `grep -E "^\| \d+ \|" decision-tree-changelog.md` |
| 4 | note 中 `|` 转义为 `\|`, 表格不破坏 | | `grep -E "block.*\\|.*with.*\\|.*pipes" decision-tree-changelog.md` (仅当 note 含 \|) |
| 5 | 季度首日 (1/1, 4/1, 7/1, 10/1) 跑 review + 写 spec-evolution.md §6 | | `grep "Q[1-4].*review" .ai-memory/meta/spec-evolution.md` |
| 6 | 6 tests 覆盖: bootstrap + idempotent + hash-change + last-hash + note-escape + block-hash | | `pytest scripts/tests/test_sync_changelog.py` |

**AI 必做 (M1.H 决策树 changelog + 季度 review 硬规则)**:
- ✅ **改决策树块必跑 `--changelog --note '<可读原因>'`** (例: "N117 闭环" / "step_2 added")
- ✅ **block hash 计算口径必须一致** (`## Decision Tree` ↔ `## End Decision Tree` 整段, 含 yaml code block)
- ✅ **季度首日 review 5 步**: step 数 / task_type 覆盖 / 反模式覆盖 / KB 路径 / changelog 漂移
- ✅ **review 输出按 spec-evolution §6.2 模板** (Q1-Q4 markdown 段)
- ✅ **共享文件放 `gaf-{name}/_shared/`** (子目录约定, 不平级)
- ❌ **NEVER 改决策树而不跑 --changelog** (N95 家族反模式, 改了不知道)
- ❌ **NEVER 手动编辑 decision-tree-changelog.md** (除非人工修正错误, 否则由 script 维护)
- ❌ **NEVER 跳过季度 review** (即使决策树没改, 也要跑一次, hash 不变 = no-op)
- ❌ **NEVER 在 .skills/skills/ 根平级建 _shared/** (违反子目录约定)

**AI 终止条件 (M1.H 反模式)**:
- 改决策树块 5+ 分钟还没跑 `--changelog` → 停下, 跑后再继续
- 季度 review 漏写 spec-evolution §6 → 补写, 不算"完成"
- `_shared/` 路径用绝对路径 (违反 N106 家族) → 改用相对路径

**同根因家族**: N95 (分级分发) + N100 (文件损坏) + N101 (状态不诚实) + N106 (路径漂移) + N116 (并发状态管理) + **N117 (本条 决策树治理缺位)** —— 同根因 (决策树治理缺位)

### ⑲ N122 scripts/ 维护与路径一致性 Y/N 矩阵

> **触发条件** (任意一条即触发):
> - AI 准备新建 `scripts/` 下的脚本
> - AI 修改/重构 `scripts/` 下现有脚本
> - AI 写/改任何解析 YAML front matter 的代码
> - AI 在测试 fixture 中写 Windows 绝对路径
> - AI 改脚本后发现 `docs-index.md` 或 e2e `documentation` 场景失败

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 新增脚本前已查 `scripts/` 是否有同类工具 | | `ls scripts/` + grep 功能关键词 |
| 2 | Front Matter / YAML 解析复用 `scripts/frontmatter.py` | | `grep "from frontmatter import\|import frontmatter" <script>` |
| 3 | 脚本变更后跑 `python scripts/bootstrap/sync_docs_index.py` 重建索引 | | `.ai-memory/meta/docs-index.md` 更新 |
| 4 | 脚本变更后 e2e `documentation` 场景通过 | | `pytest scripts/tests/test_e2e_run_all.py -k documentation` |
| 5 | 测试 fixture 绝对路径加 `# path-check-ignore` 或优雅 skip | | `grep "path-check-ignore" <test_file>` |
| 6 | 硬编码 Windows 绝对路径被 `check_path_consistency.py` 捕获或显式忽略 | | `python scripts/hooks/check_path_consistency.py --root GAF` |
| 7 | 没有新的 `_append_*.py` 一次性脚本（用 `append_lesson_block.py`） | | `ls scripts/_append_*.py` 应为空 |

**AI 必做 (scripts/ 维护硬规则)**:
- ✅ 新增脚本前先查 `scripts/` 是否已有同类工具，优先参数化复用
- ✅ Front Matter / YAML 解析必须复用 `scripts/frontmatter.py`
- ✅ 脚本变更后必须跑 `python scripts/bootstrap/sync_docs_index.py`
- ✅ 脚本变更后必须检查 e2e `documentation` 场景
- ✅ 测试 fixture 绝对路径加 `# path-check-ignore` 并指向当前环境真实路径或 skip
- ❌ 禁止新建 `_append_*.py` 一次性脚本（用 `scripts/lessons/append_lesson_block.py` 替代）
- ❌ 禁止在业务脚本中重复实现 YAML front matter 解析
- ❌ 禁止脚本变更后不跑 `sync_docs_index.py` 和 e2e documentation 场景

**同根因家族**: N95 (分级分发) + N100 (文件损坏) + N101 (状态不诚实) + N106 (路径漂移) + N110 (lint 阻塞) + N114 (hook 误用) + **N122 (本条 scripts/ 维护缺位)** —— 同根因 (工具/治理缺位)

### ⑳ N124/N125/N126 工作流治理 + .trash + 文档诚实标记 Y/N 矩阵

> **触发条件** (任意一条即触发):
> - AI 删除/重命名 skill
> - AI 创建临时脚本 (`_temp_*.py` / `_commit_msg.txt` / `_*.log`)
> - AI 标记文档 ✅ 已完成 (设计文档/feature spec/roadmap)
> - AI 写 Mock/Stub 实现作为占位
> - AI 审计设计文档与实际代码一致性

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 删除 skill 前 grep 全仓库引用, 同步更新所有 marker/路径 | | `grep -r "<skill_name>" scripts/ .skills/` 无残留 |
| 2 | 决策树块同步用 `\n## Decision Tree\n` 行首匹配, 不用 find() | | 检查同步脚本正则 |
| 3 | 临时脚本放 `GAF/.trash/`, 不散落仓库根目录 | | `git status` 无 `_*.py` 未跟踪 |
| 4 | `.trash/README.md` manifest 表登记每个临时文件 | | 检查 manifest 表 |
| 5 | 对话结束清空 `.trash/` (只留 README.md) | | `ls GAF/.trash/` 只剩 README.md |
| 6 | 文档 ✅ 标记代码级验证 (打开代码文件确认真实实现) | | 检查代码行数/真实依赖 |
| 7 | Mock/Stub 标 🔧, 不标 ✅ | | grep 文档 "Mock\|Stub" 附近标记 |
| 8 | 真实实现引入真实依赖 (cv2/numpy/onnxruntime), 不用 hardcoded | | 检查 import + return 语句 |
| 9 | 虚报修正加 "(N126 验证)" 注释 | | grep "(N126 验证)" 追溯 |
| 10 | N126 缺失功能列入 pending-roadmap.md §二.20 | | 检查 §二.20 表格 |

**AI 必做 (N124/N125/N126 硬规则)**:
- ✅ 删除 skill 前必须 grep 全仓库引用, 同步更新所有 marker/路径
- ✅ 决策树块同步必须用行首匹配 `\n## Decision Tree\n`, 不能用 `find()` 子串匹配
- ✅ 临时脚本必须放 `GAF/.trash/`, 不散落仓库根目录
- ✅ `.trash/README.md` manifest 表登记每个临时文件 (文件名/用途/创建时间/状态)
- ✅ 对话所有任务结束 → 清空 `.trash/` (只留 README.md)
- ✅ 文档 ✅ 标记必须代码级验证, 不能凭印象
- ✅ Mock/Stub 必须标 🔧, 不能标 ✅
- ✅ 真实实现必须引入真实依赖 (cv2/numpy), 不能用 hardcoded 返回值
- ✅ 虚报修正加 "(N126 验证)" 注释, 便于追溯
- ✅ N126 缺失功能列入 pending-roadmap.md §二.20 (按 ROI 排序)
- ❌ NEVER 用 `str.find()` 匹配 markdown header (注释中可能含相同文本)
- ❌ NEVER 把业务脚本放 `.trash/` (需复用的放 `scripts/` 并加测试)
- ❌ NEVER 把临时文件直接放 `GAF/` 根或 workspace 根
- ❌ NEVER 用 Mock 返回固定坐标/区域作为 "已完成"
- ❌ NEVER 把 80 行 stub 标为 "236 行 DSLCompiler 已完成"

**同根因家族**: N14 (假实现) + N16 (状态标记不诚实) + N26 (SKILL.md 放错根) + N95 (分级分发) + N101 (状态不诚实) + N122 (脚本重复) + **N124 (skill 删除引用残留) + N125 (临时文件散落) + N126 (文档虚报 ✅)** —— 同根因 (诚实标记 + 治理缺位)

> **注**: N126 文档诚实标记部分同时归入 §3 honest-status, 见 §3 ㉑-㉓ 系列。

### ㉕ N140 文件命名禁止版本号 Y/N 矩阵

> **触发条件** (任意一条即触发):
> - AI 创建新文件 (脚本/文档/配置)
> - AI 迭代已有文件 (需要新版本)
> - AI 引用文件路径

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 文件名不含 `v1`/`v2`/`v3` 等版本后缀 | | `Get-ChildItem -Recurse | Where BaseName -match 'v\d+'` |
| 2 | 迭代时覆盖同一文件, 不创建 `_v2`/`_v3` | | git log 看同一文件多次 commit |
| 3 | 需保留变体时用描述性后缀 (`_retry`/`_parallel`) | | 文件名后缀有语义 |

**AI 必做 (N140 硬规则)**:
- ✅ 文件名是稳定标识符, 版本由 git 追踪
- ✅ 迭代覆盖同一文件, 不创建版本号副本
- ✅ 需保留不同变体时用描述性后缀 (`_retry`/`_parallel`), 不用 `v2`/`v3`
- ❌ NEVER 文件名带 `v1`/`v2`/`v3` 版本号后缀
- ❌ NEVER 创建 `xxx_v2.py` 作为 `xxx.py` 的"新版本" (应覆盖原文件)

**例外** (不算版本号):
- `version-compat.md` — "version" 是主题词, 非版本号 (spec-38 Phase 6: version-sync.md 已合并进本文件)
- `__version__.py` — 约定俗成的版本声明文件
- 第三方库的 `v2` API 路径 (如 `/api/v2/`) — URL 版本控制, 非文件名

> N30 Y/N 矩阵已归档到 archived-lessons.md（索引已归档）

### ㊱ N165/N169/N170 已合并

> **合并原因**: N165 → N170 (commit 弹窗规则家族) / N169 → N166 (L3 循环被动触发家族) / N170 是 L1-小改动过度分发反例 (§6.2 L1-小不应有 Y/N 矩阵)
> **检查项归属**:
> - N165/N170 (commit -F 弹窗 + PowerShell heredoc) → `project_rules.md §3.4` N170 硬约束 + `ai-operating-handbook.md` Part 2 命令使用段 (L2 硬加载)
> - N169 (TD "延后" 语义 + TD 处理顺序) → `project_rules.md §4.8` 硬约束
> **Lesson**: `lessons/N170-git-commit-m-no-prompt.md` (N165+N170) / `lessons/N169-td-deferred-semantics.md` (N169, 历史可查)

## §7 hook-failure — pre-commit hook 失败

> N91 Hook ID 失败映射表 (5 hook + 12 sub-check 调试参考表) 已迁至 [_workflow-reflection.md](_workflow-reflection.md) §N91 (bug 排查主题)。本节仅保留 N150 (根因修复 + 预存错误处理)。

### N150 pre-commit 失败根因修复 + 预存错误当场处理

> **来源**：用户反馈 "未找到 pre-commit咋会呢，还有预存错误或者开发中的其他问题，都要记录进去，或者当时就解决，不要留着，修改时要从整体框架看下去，不可只以最小修改来弄"
> **跨引用**：N105 (`--no-verify` 原始范围 — gaf-commit.sh 透传 bug)、N91 (hook 失败映射)、N126 (诚实标记)、N128 (3 步验证)、§2.0 三原则 (改动范围由正确性决定)

**触发**：pre-commit hook 失败 / 发现 pre-existing error / commit 前 hook 报错。

**§3 pre-commit 失败处理 — hook 失败时必跑**：

| # | 检查项 | Y/N |
|---|--------|-----|
| 1 | **Y**: hook 失败时先调查根因（路径过期？脚本 bug？数据漂移？language 配置？），而非直接 `--no-verify`？ | |
| 2 | **N**: 是否用 `--no-verify` 绕过非 N105 的 pre-commit 失败？（禁止 — TD-065 反模式） | |
| 3 | **Y**: 修复后重跑 `pre-commit run --hook-stage pre-commit` 验证全部 Passed？ | |
| 4 | **Y**: 修复后用 `git commit`（非 `pre-commit run`）验证 hook 在实际 commit 时也通过？ | |
| 5 | **Y**: 发现"非本轮范围"的 pre-existing error，当场修复或登记 tech-debt/README.md (TD-NNN)？ | |
| 6 | **Y**: 修复一个 bug 后检查同类问题是否存在于其他文件（整体框架视角）？ | |
| 7 | **N**: 是否只改最小范围而忽略同根因问题？（禁止 — §2.0 三原则） | |
| 8 | **Y**: Python-based GAF hooks 使用 `language: python`（非 `language: system`）避免 Windows PATH 漂移？ | |

**§3 预存错误处理 — 发现 pre-existing error 时必跑**：

| # | 检查项 | Y/N |
|---|--------|-----|
| 1 | **Y**: pre-existing error 当场修复（如果是 quick fix）？ | |
| 2 | **Y**: 无法当场修复的，登记 tech-debt/README.md (TD-NNN)（含症状/根因/影响/修复方案/验证标准/何时修）？ | |
| 3 | **N**: 是否"先跳过，下轮再修"但不登记？（禁止 — 会遗忘） | |
| 4 | **Y**: 修复后更新 TD 状态为 ✅ FIXED 并附 commit hash？ | |

**反模式**：
- ❌ `--no-verify` 作为通用 escape hatch（N105 原始范围被泛化）
- ❌ 预存错误"先跳过"不登记 → 遗忘 → 永远不修
- ❌ 只改最小范围（如 check_spec_consistency.py L52 有 path bug，L229 有同样 bug 但没改）

**根因修复流程**（N150 强化 N91 §7）：
1. hook 失败 → 看 hook ID + 错误信息
2. **调查根因**（不是 `--no-verify` 绕过）：
   - hook 找不到 → `pre-commit install` 重装（可能 INSTALL_PYTHON 路径过期）
   - exit 9009 (Windows) → `language: system` hooks 用 PATH 中的 `python`，被 Windows Store stub 拦截 → 改为 `language: python`
   - validator 失败 → 看具体字段/路径问题 → 修复
   - 数据漂移 → `makemigrations --check` 看哪些 app drift → 生成 + migrate
3. 修复后 `pre-commit run --hook-stage pre-commit --all-files` 验证全部 Passed
4. **再用 `git commit` 验证**（`pre-commit run` 用 conda python，`git commit` 用系统 PATH python，环境不同）
5. 检查同类问题（1 个 lesson 路径失效 → 检查所有；1 个脚本 path bug → 检查所有）
6. 登记新 TD（如有）+ 创建新 lesson（如有可复用经验）

**同根因家族**: N82 (审计错觉) + N91 (hook 失败映射) + N105 (`--no-verify` 透传) + N110 (lint 阻塞) + N114 (hook 误用) + N126 (诚实标记) + N128 (3 步验证) + **N150 (本条 hook 失败根因修复)** — 同根因 (hook 治理缺位)

### ㊷ N215 对话起始未加载 orchestrator Y/N 矩阵 (2026-09-01 补登, workflow)

> **触发条件** (任意一条即触发):
> - 对话第一条任务消息未先 `Skill(name='gaf-orchestrator')` 判定 task_type
> - 恢复会话 (summary 续接) 跳过入口判定, 连带收尾 (沉淀/反思) 纪律一起丢

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 每次对话第一条任务消息先判定 task_type 再动手? | | 对话首轮含 orchestrator 判定 |
| 2 | 恢复会话 (summary 续接) 同样重做入口判定? | | 续接首条消息判定 |
| 3 | 收尾该 commit 后跑 gaf-lesson-router collect? | | 收尾含 collect |

**AI 必做 (N215 硬规则)**:
- ✅ 每次对话先 `Skill(name='gaf-orchestrator')` 判定 task_type → 按分支加载 skill+KB 再动手
- ✅ 恢复会话 (summary 续接) 同样必做; 收尾 commit 后跑 gaf-lesson-router collect
- ❌ **NEVER 跳过入口判定直接执行任务** (连带收尾纪律一起丢)

**实测基线 (N215 闭环)**:
- 触发: 2026-08-28 整轮 E2E/文档/沉淀对话无入口判定, 用户追问暴露
- lesson: `lessons/workflow_2026-08-28_n215-load-orchestrator-at-conversation-start.md`

**同根因家族**: N134 (workflow skill 未触发) + **N215 (本条 入口判定)** —— 同根因 (流程入口未强制)

### ㊹ N217 登录"记住我"失效 Y/N 矩阵 (2026-09-01 补登, workflow)

> **触发条件** (任意一条即触发):
> - 跨功能迭代期间用户高频基础流程 (登录/记住我/鉴权恢复) 未纳入回归
> - antd Form.Item 直接子元素是非受控容器 (div/span), value/onChange 不注入受控组件

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 跨功能迭代把用户高频基础流程 (登录/注册/鉴权恢复) 纳入每轮回归清单? | | 回归清单含登录 |
| 2 | antd Form.Item 直接子元素是受控组件 (含 name + valuePropName)? | | Form.Item 子元素为 Checkbox/Input |
| 3 | 免登录持久化 (remember_me → refresh token 存储) 实测验证? | | 勾选后刷新仍登录 |

**AI 必做 (N217 硬规则)**:
- ✅ 跨功能迭代必回归用户高频基础流程 (登录/注册/鉴权恢复)
- ✅ antd Form.Item 直接子元素必须是受控组件 (name + valuePropName 的 Checkbox/Input)
- ❌ **NEVER Form.Item 直接子元素用非受控容器 (UI 与表单值脱节)**

**实测基线 (N217 闭环)**:
- 触发: 2026-08-29 用户反馈 "不是可以记住账号吗，为啥每次都要登录"
- lesson: `lessons/workflow_2026-08-29_n217-login-remember-me-regression.md`

**同根因家族**: N135 (浏览器实测登录) + **N217 (本条 基础流程回归盲区)** —— 同根因 (高频基础流程验证缺位)

### ㊺ N219 今日日程"计划排期"显示成"待执行" Y/N 矩阵 (2026-09-01 补登, workflow)

> **触发条件** (任意一条即触发):
> - 计划型展示 (引擎推导排期) 用执行型状态语义 (pending) 误导用户
> - 前端拼接 device→account→chain 对空字段无条件 `a → b → c` 渲染空段箭头

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 未触发计划用 planned (计划中) 而非 pending (待执行)? | | 状态语义区分 |
| 2 | 前端拼接对空字段做条件渲染, 禁止无条件箭头? | | 空字段不渲染箭头 |
| 3 | 计划型/执行型状态在前端文案与后端枚举语义一致? | | 文案与枚举对齐 |

**AI 必做 (N219 硬规则)**:
- ✅ 计划型展示状态语义与执行型区分 — 未触发计划用 planned 非 pending
- ✅ 前端拼接 device→account→chain 对空字段做条件渲染
- ❌ **NEVER 计划排期用 "待执行" 语义 (误导为任务排队却不跑) / 无条件渲染空段箭头**

**实测基线 (N219 闭环)**:
- 触发: 2026-08-29 用户追问 "今日日程那没问题吗?" (双箭头中间空白 + 标待执行)
- lesson: `lessons/workflow_2026-08-29_n219-today-schedule-planned-vs-pending.md`

**同根因家族**: N218 (统计类卡片数字核对) + **N219 (本条 展示状态语义)** —— 同根因 (前端展示与真实状态脱节)
