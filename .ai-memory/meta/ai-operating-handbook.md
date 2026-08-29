# AI 操作手册（L2 启动必读，单一权威源）

> **updated: 2026-07-26 (v9.6 P2 重构)**
> **L2 加载清单**: 2 文件 (本文件 + `docs/reference/tech-stack.md`)。`meta/docs-index.md` / `docs/reference/version-compat.md` 保持 L3 按需加载。
> **v9.6 变更**: 根目录 7 个 ref 文件迁移到 `.ai-memory/ref/` 子目录。
> **v9.5 变更**: `docs/reference/tech-stack.md` 从 L3 升级为 L2 硬加载, 含 4 栈版本 + 开发环境速查段。

---

## Part 1: L1/L2/L3 加载策略

### 命名消歧

> **同名 L1 双义问题**: "L1 硬加载" (加载机制层, 本 Part 1 主题) vs "L1 教训级别" (教训分级层, 见 `project_rules.md §6`)

| 简写 | 含义 1 (加载机制层 — 本 Part 1) | 含义 2 (教训分级层 — §沉淀纪律 真二分制) |
|:---:|------|------|
| **L0** | (无) | 一次性事件, 无可复用 Y/N 价值, 仅写 lessons/ (1 层) |
| **L1** | 启动硬加载 (< 1s), gaf_init.sh grep failure-modes ≥ 5 N## | 可复用经验, 按规模 L1-小(2层)/中(3层)/大(5层), 见 §6.2 |
| **L2** | 任务路由加载 (< 5s), AI 必 Read 本文件 | (无) |
| **L3** | 任务按需加载 (< 10s), sync_ai_memory.py --query | (无) |

**判定规则**: 出现 "L1 硬加载" / "L2 hard-load" / "L3 按需" → 加载机制层; 出现 "L1 教训" / "L0/L1 真二分制" / "L1-小/中/大" → 教训分级层

### L1 — 启动硬加载 (< 1s)

| 项 | 内容 |
|---|---|
| 触发 | `bash scripts/gaf_init.sh` 启动时 |
| 内容 | `meta/failure-modes.md` (active N## 条目) |
| 机制 | gaf_init.sh 步骤 4.5 硬 grep `^\| N[0-9]+` 数量 (failure-modes.md 表格格式), ≥ 5 才算通过 |
| 失败 | exit 1 (硬约束, 不允许 fallback) |

### L2 — 任务路由加载 (< 5s)

| 项 | 内容 |
|---|---|
| 触发 | gaf-orchestrator 决策树 step_1 路由后 |
| 内容 | 本文件 `ai-operating-handbook.md` + `docs/reference/tech-stack.md` (2 文件, v9.5) |
| 机制 | gaf-orchestrator §step_1 后加 "L2 hard-load hooks" 段, 强制 Read 2 文件 |
| 失败 | 任务路由前 AI 必须 read, 否则视为未加载 (反思矩阵 [L2] 必标 N, N96 触发) |

### L3 — 任务按需加载 (< 10s)

| 触发场景 | 加载文件 | 命令 |
|---------|---------|------|
| 涉及版本/依赖/TS 严格选项 | `docs/reference/version-compat.md` | Read |
| 涉及 docs/ 设计文档 | `meta/docs-index.md` | Read |
| 涉及 CLI 命令速查 | `docs/reference/cli-cheatsheet.md` | Read |
| 涉及跨层数据流 | `docs/reference/data-flow.md` | Read |
| 查 spec_id 索引 | `ref/spec-index.md` | Read |
| 改 backend model/serializer | `yn-matrices/archived-yn-matrices/_cross-layer-sync.md` (N112) | Read |
| 跑长命令 (pytest/migrate/pip) | `yn-matrices/archived-yn-matrices/_ai-autonomy.md` (N111) | Read |
| 审计文档状态 (标 ✅/🔧/❌) | `yn-matrices/archived-yn-matrices/_honest-status.md` (N128/N129/N130) | Read |
| pre-commit hook 失败 | `yn-matrices/_workflow-commit.md` §7 (N91/N150) | Read |
| 改 sync 脚本 | `yn-matrices/archived-yn-matrices/_misc.md` §concurrency (N116) | Read |
| 写测试 | `yn-matrices/_testing.md` (N118) | Read |
| bug 修复 | `lessons/<n##>.md` | `sync_ai_memory.py --query <topic>` |
| 前端 i18n | `yn-matrices/archived-yn-matrices/_ai-autonomy.md` (§N127 i18n 子段) | Read |
| commit 前/任务完成前反思 | `yn-matrices.md` (索引) + `yn-matrices/_<topic>.md` | Read |

> **v9.5 (2026-07-21)**: `docs/reference/tech-stack.md` 从 L3 升级为 L2 硬加载 (用户反馈 "ai 每次都要找技术环境"), 详见 §Part 1 L2 段

### 症状 → 知识点映射表 (N191 新增, 2026-07-27)

> 症状/关键词 → 知识点显式映射, AI 看到主动加载 (不依赖 --query 模糊匹配)。与上方 L3 表互补。

| 症状/关键词 | 知识点位置 |
|------------|----------|
| schema 重构/字段重命名/坐标偏移/chain schema 残留/跨层数据流不一致 | `.ai-memory/meta/env-hardrules-contextual.md` §Schema 归一化硬约束 (N191) |
| conda 环境/Python 失败 | `.skills/rules/env-hardrules.md` §Python (N188 已 Retired, 约束 L0 常驻) |
| PowerShell heredoc/git commit 失败/&& 短路/-F 临时文件 | `.skills/rules/env-hardrules.md` §Shell + `_archive/lessons-retired/N190-*.md` |
| InMemoryChannelLayer/WS 消息丢失/execution stuck | `.ai-memory/meta/failure-modes.md` (A3 教训, lesson 已不存在勿引用) |
| pre-commit hook 失败 | `meta/yn-matrices/_workflow-commit.md` §7 (N91/N150) |
| 文档过时/drift/文档与代码不一致 | `meta/yn-matrices/archived-yn-matrices/_honest-status.md` (N128/N129/N130) |
| venv gaf-agent/opencv headless/部署依赖 drift | `.ai-memory/meta/failure-modes.md` §Retired N187 |

**触发规则**: AI 看到症状主动加载; L0 段每次对话强制; L3 需 AI 主动 Read/`sync_ai_memory.py --query`; 中大修改必跑 `--query "<topic>"` (gaf-orchestrator step_4 硬约束)。

### 加载顺序示意

- AI 启动 → `gaf_init.sh` (强制) → L1 硬加载 failure-modes.md → session active (24h TTL)
- AI 收到任务 → gaf-orchestrator 决策树 → L2 硬加载 2 文件 (本文件 + `docs/reference/tech-stack.md`, v9.5) → 路由 5 skill
  - new_feature → gaf-task-execution (L3: version-compat 按需)
  - bug_fix → gaf-reflect-and-evolve (L3: lessons/ --query + error-codes)
  - documentation → gaf-knowledge-base (L3: docs-index + docs/)
  - refactor → gaf-task-execution + gaf-reflect-and-evolve (L3: architecture-mistakes + lessons/)
  - unknown → gaf-orchestrator 兜底
- AI 完成任务 → 写 3 步 evidence + lessons/ (M0.M: 同时跑 promote_lessons 提议提升)

### AI 自决加载原则

- ✅ 按 task_type 主动加载 (new_feature→workflow+cross-layer-sync; bug_fix→hook-failure+honest-status); 按场景主动 grep 对应 N##; 反思时按 topic 章节读 yn-matrices; bug 修复先 `sync_ai_memory.py --query <symptom>`
- ❌ 禁止跳过 L1/L2 硬加载 (gaf_init.sh + 本文件必读); ❌ 禁止凭印象写代码 (写前必跑 L3 query 找相关教训)

### 日志查询指引 (spec 2026-08-29-logging-system-consolidation, AI 调试必读)

| 我要查什么 | 去哪里 |
|-----------|--------|
| 应用级最近日志 (服务终端+原生日志) | `GET /api/v2/logs/files/?service=backend&filter=error` (service ∈ backend/agent/daemon/frontend/redis) — 读 `debug/system/services/*.log` + `debug/YYYYMMDD/...` |
| 服务健康/报错计数 | `debug/health-status.json` (daemon 每 15s 写, 含 services/processes/log_errors) 或 `/api/v2/monitors/services/` |
| 业务事件 (审计/恢复/消息帧/LLM/崩溃) | `/api/v2/logs/timeline/` (UNION 6 模型) 或日志中心 7 tab |
| agent↔backend 消息帧 | `MessageFrameLog` 表 (协议层收发帧) — 日志中心"消息帧"tab |
| 前端崩溃 | `CrashReport` 表 (前端 error_boundary 上报) — 日志中心"崩溃报告"tab + 控制台 JSONL |
| 任务执行级日志 | `debug/<YYYYMMDD>/<task>/<HHMMSS>_<exec_id>/` (run.log + structured.jsonl + screenshots 同目录) |

分工: **DB 层 = 业务事件** (审计/恢复/消息帧/LLM/崩溃), **文件层 = 进程终端/执行日志**.
`LogEntry` 表已停写 (spec §2.2), 应用日志以文件层为准 — 不要在 `/api/v2/logs/` 找新日志.
审计日志单入口 = 系统页 `/system/audit-log` (日志中心审计 tab 已移除).

---

## Part 2: AI 行为红线

> **来源**: N126-N163 教训提炼。完整教训见 `.ai-memory/lessons/`。
> **更新规则**: 新 L1 教训沉淀时，同步更新本节对应红线。

### 自治边界（N109/N113/N115/N127/N151/N161/N163/N166/N167）

- ❌ 禁止等待式提问 ("要我处理X吗"/"是否继续"/"下一步"/"继续?") → ✅ 立即处理+推进; spec 内自决推进下一阶段 (N109); 循环模式每个 spec ✅ 后主动接修下一个 TD/spec
- ❌ 禁止架构 A/B/C 一律 AskUserQuestion / 优先级让用户拍板 → ✅ N167 七维度自决 (仅 4 类硬场景: FK/schema/业务语义/不可逆 找用户); 优先级按 P0>P1>P2>P3+依赖+改动量自决
- ⚠️ spec 全部 ✅ 后停下报告 (hash+evidence+候选) 等指令; AskUserQuestion 仅用于: 规则未覆盖歧义/不可逆授权/七维度不自决/4 类硬场景
- 完整清单见 `lessons/archived-early/circular_mode_no_continue_prompt.md` + `gaf-reflect-and-evolve/SKILL.md §7.3`

### 沉淀纪律（N166/N172/N206 — 强制）

- ❌ 禁止只当前对话生效 / 只写 lessons 不更新 rules / 小改动过度分发 (N170) / 假沉淀(说"应该沉淀"不调工具) → ✅ 当轮结束前按 L1-小(2层)/中(3层)/大(5层) 分发; "应该沉淀"=同回复内立即 Write/Edit
- ✅ 判定标准(1问): "下次对话 AI 是否需遵守?" → 是必沉淀; 反问/追问(N206)非必然沉淀; 沉淀验证必列实际修改文件路径 (N172 evidence); 治理评估 N189 区分"必需治理"vs"形式化", 禁以文件数判定
- ✅ commit message 不写规则编号 (N208): 写 N## 被 M2 当声称核验 diff 证据, 无证据触发 `REVIEW_TRIGGERED`; 仅 diff 真有证据才写; 沉淀效率 3 优化: frontmatter 必填+Glob 验证路径+Grep 定位并行 Edit
- 完整清单见 `project_rules.md §3.8` + `lessons/` 同名条目

### spec/plan 用时测量（N173 — 强制, Wave 1 hook 强制 2026-07-26）

- ❌ 禁止 spec/plan 不测用时 / 只报 hash+测试数不报 duration → ✅ 必记 `start_ts`(首调用前)/`end_ts`(commit后)/`duration`, 报告含是否基线内+超基线根因
- ✅ 基线: 小<5/中<15/大<60/沉淀<5 min; 超基线必跑 6 项根因 (应并行未并行/pre-commit 重试/凭印象写路径/应 1 次 Grep/未拆 spec/重复 Read); AI 听到反馈自决沉淀 (问"下次是否需遵守")
- ✅ N173 hook 强制: spec-context 必含 5 字段, 缺失/占位符→commit 失败, `within_baseline=false` 时 `root_cause_if_over` 必填; B2 大修改 3 门槛 (check_big_change + evidence 三件套 + spec-context); doc-code-sync skip 用 `$env:GAF_SKIP_DOC_SYNC="1"` (非 `-m` token), skip 前必 grep 验证无 live 引用残留
- 详见 `scripts/hooks/check_spec_context.py` + `spec-2026-07-26-ai-governance-execution-rate-fix`

### TD 登记修复方案验证（N174 — 强制）

- ❌ 禁止 TD 登记凭印象写"保留 X 删 Y" / wontfix 评估不核查"修复方案验证"字段 → ✅ 必跑 grep 验证关键字段, 写入必填字段 `修复方案验证` (≥1 grep+结果); 自检矛盾即调方案; 批量 wontfix 率 > 30% 必跑 N174 根因
- 完整清单见 `lessons/` 同名条目

### subagent 并行结果落地检查（N175 — 强制）

- ❌ 禁止 subagent 结果未全部落地 active.md / 数不一致未核查 → ✅ commit 前跑落地检查清单, 核查 `len(updates)==sum(td_list)`, 丢失重读补更新 (evidence 标 "via subagent #N"); 失败回退: 重试1次/串行接管/登记TD
- 完整清单见 `lessons/` 同名条目

### 并行 subagent 纪律（N172 — 强制）

- ❌ 禁止串行处理 ≥2 独立 TD / 等用户提醒才用 → ✅ 主动 `Task` 并行; 分工: 评估类→`search`, 修复类→`general_purpose_task`; 主会话统一更新 active.md+commit; 触发 (`dispatching-parallel-agents`): 2+ 独立任务无共享状态 → 必用
- 完整清单见 `lessons/` 同名条目

### 实测验证纪律（N166 L3-5 — 强制）

- ❌ 禁止只跑 pytest 标 ✅ / 单测覆盖够 → ✅ 启动 backend+frontend+agent 浏览器点击; 单测只覆盖逻辑; L3-5 清单 (WS 连通/UI 可点/端到端/Agent 响应); 工具 Playwright E2E (`scripts/e2e/`) + browser-use; 记录 ✅/❌+JS 错误数 (`project_rules.md §4.1`)
- 完整清单见 `lessons/` 同名条目

### 7 维度评估纪律（N167 — 强制；命名归一 = 修改清单）

> **单一权威源**: `_refactor-dimensions.md` + `gaf-reflect-and-evolve/SKILL.md §7`; `project_rules.md §2.0.x` 仅指针。三层互补: 本节"修改清单"(7 维, 改前) + L3-1"扫描清单"(9 维) + reflect §2"反思清单"(24 项 Y/N, 改后)

- ✅ 7 维度清单详见 `_refactor-dimensions.md`; 适用范围: 代码/规则/Skill 修改; 分级触发: 小豁免 / 中 3 维(1/2/7) / 大 7 维 + N151
- ❌ 禁止"最小改动"自决 / 迁移成本误算入长期维护成本 / 单人项目新旧兼容打低分 → ✅ 维度 1 架构长远性首要判据; 维度 3 单人项目一律 5/5; 维度 7 看 3-5 年长期受益; 优先选维度 1+7 双 5/5 方案
- 完整清单见 `_refactor-dimensions.md` + `gaf-reflect-and-evolve/SKILL.md §7`

### 诚实标记 + 验证（N126/N128/N157）

- ❌ 标 ✅ 但 E2E 未做 → ✅ 有前端改动的阶段必跑 Playwright E2E
- ❌ 标 ✅ 但只跑单 app 测试 → ✅ 全量回归（受影响 app 全部）
- ❌ 标"spec 全部完成"不提范围外问题 → ✅ 追加"范围外关注"段
- ❌ related_files 猜路径 → ✅ Glob 验证存在再写入
- ❌ 引用 skill/doc/path 不验证存在 → ✅ Glob/LS 验证
- ❌ 验证只测只读命令就标 ✅ FIXED → ✅ 必须覆盖写命令 (TD-119 #1: 只测 status/log 就判 FIXED, 写命令仍弹窗)
- ❌ 从单个命令不弹窗推广到整类不弹窗 → ✅ 必须逐个测试命令变体 (TD-119 #2: Trae 按逐命令逐 flag 判定, 非按读/写类别)
- 完整清单见 `meta/yn-matrices/archived-yn-matrices/_honest-status.md` (N128/N129/N130)

### 命令使用（N111/N153/N160 — 完整 Shell/git 约束见 env-hardrules.md §Shell / project_rules §3）

- ❌ 禁止 `pytest -v` / 用非 gaf 环境跑代码 / 多行 `python -c` / `git add -A` 或 `.` / `&&` 链式 / bash heredoc (N165) / `-F <file>` → ✅ `pytest -q`; `conda run -n gaf`; 写临时 .py; `git add <specific>`; `;` 分隔; 单行 `-m` 提交 (多行用多 `-m`), `-F` 禁用 (N190)
- ❌ 禁止每子任务 1 commit / 大阶段 commit 前不确认 staging / 重复启动 dev server / 命令失败直接换 / 杀超时放弃目标 → ✅ 按 spec 粒度提交 (§3.4); `git add` 后 `git status` 二次确认 (N153); 先查已在运行 (N155); 先根因分析; 换方式继续 (N111 §3.5)
- ⚠️ commit 弹窗: 单行 `git commit -m "..."` 不弹窗, 多行多 `-m` 弹窗 (Trae 看参数数量); 优先单行
- ❌ 禁止命令超时傻等/放弃 → ✅ CheckCommandStatus → StopCommand → 换方式继续 (N111)
- ❌ 禁止脚本不复用不落地 → ✅ 可复用脚本持久化到 `scripts/` 对应子目录 + 更新 `scripts/README.md`; 新增前查同类 (N122)
- 完整清单见 `.skills/rules/env-hardrules.md` §Shell + `lessons/` 同名条目

### 脚本性能测量（N171 — 强制）
> **单一权威源**: 本节。核心反模式: 只看 exit code 不看耗时 → 71s/commit 性能问题数月未发现

- ❌ 禁止脚本只看 Passed/Failed / commit>5s 不分析 / batch 用 subprocess 调 N 子脚本 / 框架开销>>实际 → ✅ 必加 `Measure-Command { ... } | Select-Object TotalSeconds`; 对照基线 (单 hook<1s / commit<5s / pytest 单文件<5s / 全套<30s / sync<1s) 优化; 优先 `from <module> import main`; 合并 hooks / 换 `language: system` / 内联 import
- 完整清单见 `lessons/N171-script-performance-measurement.md` (N171 家族)

### 反思纪律（N134/N162）

> 反思分级触发标准见 `project_rules.md §4.6` + `gaf-reflect-and-evolve/SKILL.md §2`（行数判定）

- ❌ 禁止命令用错只当场改 / commit 后跳过反思 / 小改走全套 → ✅ 反思根因+替代+防错; 中>50 行必跑分级 (中 5 项/大 ①-㉔); 小<50 行只跑 ①4问+④状态 (2 项)
- 完整清单见 `gaf-reflect-and-evolve/SKILL.md §2`

### 上下文管理（N159/N160）

- ❌ 禁止 E2E selector 逐次试错(>2轮)/大文件整读/长输出不过滤/独立任务全主对话/≥15轮不提示 → ✅ 诊断脚本一次性 dump; offset+limit; `Select-Object -Last N`; Task 分发; 主动提示新开对话
- 完整清单见 `lessons/` 同名条目

### 文件命名 + 路径（N125/N140）

- ❌ 禁止文件名带版本号 / 临时文件放子目录 / 在 backend/ 跑 pytest → ✅ 覆盖或描述性后缀; 统一 `.trash/`; 仓库根目录跑
- 完整清单见 `lessons/` 同名条目

### L3 按需加载纪律

- ❌ 禁止版本升级不加载 version-compat / 凭印象写兼容性 / docs 不查索引 → ✅ 必 Read `docs/reference/version-compat.md` (N137/N144) + `docs-index.md` (见 `scripts/bootstrap/sync_docs_index.py`)
- 完整清单见上方 L3 表 + `meta/yn-matrices/`

### AI patch 红线 (spec-42)

- **触发/上限**: 对话开头自动 (gaf-orchestrator §0.5); 上限 10 issues/对话(P0+P1) / 单 dimension 批量 / 单次对话 1 commit
- **验证/失败**: C1 重跑 `python scripts/governance/doc_health_check.py --no-fail` patched issue.id 消失; C2 跑 `scripts/tests/test_doc_health_*.py`; 失败 1 次重试, 2 次 mark_failed+登记 TD, recurrence≥2 升级; commit `fix(doc-health): patch <dim> issues <id> (auto, spec-42)`; D2 recurrence≥3 写 lesson, D3 patch 规则文件同步沉淀 (§3.8)
- ✅ **白名单**: `.ai-memory/{lessons,summaries,meta}/*.md` / `.skills/rules/project_rules.md` / `.skills/skills/gaf-*/SKILL.md` / `docs/{business,architecture,standards}/**` + `docs/archive/*tech-debt*.md` + `docs/analysis/**`
- ❌ 禁止 patch 代码文件 (backend/agent/frontend) — 走 bug_fix 分支; ❌ 禁止 patch spec/plan 文件 (docs/specs/legacy-trae/, docs/plans/legacy-trae/) — 历史不修改

### bug 排查纪律（N182-N185 家族 + N204 — 强制）

> 家族文件: `lessons/N182-bug-investigation-three-dimensional-root-cause.md` (N182-N185 合并, 各 N## 独立生效)

- **N182** 排查启动 (动手前) 必跑链路归一化评估 (fail 节点上下游, 非只看本身); **N183** commit 前/TD 登记必跑三维根因 (代码+工作流+规则), TD 新增"三维根因评估"必填; **N184** fail_result 必带 logger.warning+exc_info+上下文, 禁静默吞错 (含输入参数+上游状态+原因); **N185** 写测试前必跑覆盖盲区反思, 同类同步补单测
- **N204** 失败关键词 (失败/超时/报错/识别不到/没反应/卡住/error/timeout) 或 pipeline 错误码 (NODE_TIMEOUT / TEMPLATE_NOT_FOUND / OCR_LOW_CONFIDENCE) → 必须调用 `Skill(name='pipeline-task-diagnosis')`; 即使 new_feature/refactor/documentation 也适用; 跳过须记录理由; L3 触发见 `.ai-memory/meta/env-hardrules-contextual.md` §诊断触发硬约束 (N204)

### 3 大确定性机制 (M1/M2/M3, 2026-08-15 — TEST_SFCAPI 借鉴)

把"AI 自觉遵守"升级为"机制强制/自动提示" (治理执行率靠机制不靠记忆):

- **M1 代码铁律 AST 静态检测 (pre-commit 强制)**: `gaf-code-rules` hook 扫 staged 的 `backend|agent` .py **新增行** (增量门禁; `--all` 全量). error 级: R001 裸/空 except (N182/N183), R004 `cursor.execute` 拼接 SQL; warn 级: R002 测试 time.sleep, R003 硬编码 `/api/v2`, R005 schema 残留 (`max_wait`). 逃生门 = `git commit --no-verify` (记录 bypass log). 详见 `scripts/hooks/check_code_rules.py`
- **M2 声称-激活率回执 (post-commit 自动)**: `check_claimed_rules.py` 读 commit message 声称的 N##, 用 M3 的 diff_keywords 校验 diff 证据, 结果追记 `.ai-memory/ops/claimed-activation.md`. N201 增强: effective_rate 排除 unknowable (分母 0 → N/A); 累计有效记录 ≥ 3 且最近 3 条中 ≥ 2 条 < 50% → 🔴 警告 + REVIEW_TRIGGERED. 详见 `scripts/hooks/check_claimed_rules.py`
- **M3 diff→lesson 触发式检索 (post-commit 自动)**: `gaf-lesson-diff-trigger` hook 按 diff (路径+新增行) 匹配 lessons `diff_keywords`, 输出相关教训 (score 排序); 新 lesson 必补 `diff_keywords`. 详见 `scripts/lessons/match_lessons_by_diff.py`
- ✅ 写代码必符合 M1 5 条铁律 (R001-R005); commit message 声称 N## 时确保有真实 diff 证据 (M2 会查); 高频 lesson 回填 `diff_keywords` 让 M3 检索生效

### M2 复盘触发处理 (N201 — 强制)

> TEST workflow_rules §3 借鉴 (2026-08-16). 防"数据报警但无闭环".

- ❌ M2 打出 🔴 复盘触发警告 / claimed-activation.md 有 REVIEW_TRIGGERED 标记却跳过 → ✅ 任务开工或 commit 反思时必按复盘模板: Q1 连续低激活率根因 → Q2 哪些规则需调整 → Q3 声称清单是否需更新 → Q4 规则文件是否需更新; 结果写回 claimed-activation.md 并标记已处理
- ❌ rate 分母含 unknowable (声称无 lesson 的 N## 被误判 LOW) → ✅ effective_rate 排除 unknowable; 分母为 0 记 N/A 不参与判定
- ❌ 用户质疑时辩解 / 跳过查证直接给结论 → ✅ 四步响应 (TEST §11): ① 确认事实 (Read/Grep 查证) → ② 追根因 (规范缺失? 没加载? 执行偏差?) → ③ 修问题 → ④ 判沉淀 (会则沉淀到规则系统)
- 完整流程见 `scripts/hooks/check_claimed_rules.py` + `.ai-memory/ops/claimed-activation.md`
