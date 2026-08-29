---
date: 2026-08-15
symptom: [meta, index, overview, topic-classification, diff-trigger]
solution: AI Lessons 索引 — 按 topic 分类索引全部教训文件, 支持快速检索 + M3 diff_keywords 触发式检索
related_files:
  - .ai-memory/summaries/architecture-mistakes.md
  - .ai-memory/summaries/code-rules.md
  - .ai-memory/summaries/library-conflicts.md
  - .ai-memory/meta/yn-matrices.md
  - .ai-memory/meta/failure-modes.md
  - scripts/lessons/match_lessons_by_diff.py
created_by: AI
priority: high
# lessons_count: counts all lesson files in lessons/ root (excludes README.md + archived-early/; includes archived N30 in root); synced by sync_ai_memory.py
lessons_count: 73
active_n_count: 37
# retired_n_count: M0.M 闭环 N## (硬约束沉淀到 rules/skills, 在 failure-modes.md §Retired; 2026-08-28 校准: 实测 §Retired 索引行 26 条, 旧注释值 43 计错(含家族子条目数误加)已修正)
retired_n_count: 26
# archived_n_count: only true archived N## (N30); dormant markers + P2 auto-archived are in archived-lessons.md
archived_n_count: 3
# dormant_n_count: family-merged sub-entries in failure-modes.md §Dormant (15 N## across 10 family-merged rows; TD-315 2026-07-21)
dormant_n_count: 15
# next_n_id: 下一个可用的 N 编号 (spec §6.2 P1-8 新增; AI 写新 lesson 时原子递增 + 文件锁; 2026-08-28 校准: N209-N216 均已分配, 新 lesson 从 N217 起; 2026-08-29: N217/N218/N219 已分配)
next_n_id: 220
---

# AI Lessons — Topic 分类索引（N132 文档治理）

> **N132 更新** (2026-06-22): 按 topic 分类, 支持 `sync_ai_memory.py --query <topic>` 快速检索
> **Y/N 矩阵**: 已集中到 `.ai-memory/meta/yn-matrices.md` (按 topic 分章节)
> **加载策略**: AI 自决 — 见 `.ai-memory/meta/ai-operating-handbook.md`（v9.3 单一权威源）
> **v9.1 P2 整理** (2026-07-14): 全量文件加 topic 前缀 (`<topic>_2026-MM-DD-nNNN-slug.md`); 5 组同主题 lessons 家族合并 (N154+N155 / N160+N162 / N161+N163 / N156+N147 / N150+N153); 补全 N141-N164 条目; 新增 4 个 topic (platform-env / command-errors / architecture / debug-autoheal / agent-impl)。
> **v9.1+ 更新** (2026-07-16/17/18, spec-36 2026-07-19 N170 撤销分发): 新增 N165 (command-errors) + N166 (workflow) + N167 (architecture topic; Y/N 矩阵在 refactor-dimensions) + N168 (architecture, backup/restore 安全) + N169 (workflow, TD 延后语义) + ~~N170~~ (spec-36 撤销: L1-小过度分发反例, lesson 文件归档, 仅保留 rules §3.4 + handbook Part 2 两层) + N171 (workflow, 脚本性能测量纪律); 计数口径以 frontmatter 各 _count 字段为准 (⚠️ sync_ai_memory.py 仅自动校准 lessons_count, active/retired/next 由 AI 手动维护, 见 TD-392)。

> **口径说明 (TD-174/199 修复 — 2026-07-18; TD-315 计数再校准 — 2026-07-21; s28 校准 — 2026-08-17; retired 校准 — 2026-08-28)**: frontmatter 计数字段语义:
> - `lessons_count` (63) = lessons/ root 下 .md 文件总数 (排除 README.md + archived-early/; 含 archived N30 + dormant N119 保留文件)
> - `active_n_count` (36) = failure-modes.md §Active N## 编号数 (2026-08-28 校准: 34 行 + 新增 N210/N211 = 36)
> - `archived_n_count` (3) = true archived N## (N30/N164/N168, lesson 文件保留在 root)
> - `dormant_n_count` (15) = 家族合并子条目 (failure-modes.md §Dormant 10 行覆盖 15 个 N## 编号)
> - `retired_n_count` (26) = §Retired 索引行 N## 编号数 (2026-08-28 实测校准: 26 条; 旧注释 43 为误计)
> 数学关系: 36 (active) + 26 (retired) + 3 (archived) + 15 (dormant, 与 active 主条目重叠) = 80 N## 编号提及 (含重叠)

---

## Topic 分类索引

| Topic | 描述 | 包含 N## | 文件数 | 家族主条目 |
|-------|------|---------|-------|-----------|
| `workflow` | 工作流治理 (commit/hook/skill 删除/临时文件/加载机制/持续评估循环/脚本性能/主动并行+真沉淀/spec 用时测量/TD 修复方案验证/subagent 结果落地/单对话批量 spec 单 commit/分级测试/AI 思维链纠偏/反思分级/元评估闭环/规则退役/循环模式不问继续/bug 排查三维根因评估/节点观测性/测试覆盖盲区/AI 主导开发治理必要性元层认知/M2 激活率复盘触发闭环/文档归属判定/调度协调 L0/对话起始入口判定/基础流程回归盲区+antd Form.Item 间接子元素坑/计划排期与执行状态语义分离+拼接防空段) | N95, N105, N108, N117, N121, N122, N123, N124, N125, N134, N140, N149, N164, N166, N171, N172, N173, N174, N175, N176, N177, N178, N179, N180, N181, N182, N183, N184, N185, N189, N198, N200, N201, N208, N215, N217, N219 | 30 | N105, N134 (N165/N169/N170 已退役见 §Retired) |
| `ai-autonomy` | AI 自决 (决策/节奏/入口/推进/超时/架构决策/优先级排序/主动用 subagent/任务归属硬约束/AskUserQuestion 边界) | N109, N111, N161+N163, N172, N193, N206 | 6 | N109, N161+N163 |
| `honest-status` | 文档诚实标记 (虚报✅/Mock/审计/虚构实现) | N126, N129, N157 | 3 | N126 |
| `cross-layer-sync` | 跨层同步 (路径漂移/前后端字段/标识符同步/复制重命名/认证 blob/DRF 分页) | N106, N112, N142, N143, N152 | 5 | — |
| `concurrency` | 并发状态管理 | N116 | 1 | — |
| `testing` | 测试套件环境依赖 + 重构验证 + e2e + Python import 验证 + pytest-django 拖慢 + 实机测试工作流 + 服务未重启假绿 + E2E 前置构造而非跳过 + E2E 脚本坑 + E2E 环境造数 | N118, N133, N135, N156+N147, N194, N196, N209, N210, N212, N214 | 10 | N135, N156+N147 |
| `hook-failure` | pre-commit hook 失败映射 | N91 | 1 | — |
| `browser-automation` | 浏览器自动化 | N131 | 1 | — |
| `version-compat` | 版本兼容 (TS/Django/库升级坑/antd 弃用) | N137, N144 | 2 | — |
| `agent-platform` | Agent 平台层 (COM/Win32/ctypes + 窗口设备动态绑定/失效重连) | N138, N146, N211 | 3 | — |
| `doc-governance` | 文档职责分离 + 教训分类 + skill 漂移 | N132 | 2 (1 active + 1 archived N30, 文件在 lessons/ 根目录) | — |
| `api-design` | API 设计问题 + URL 拼接归一化 (L0 硬约束, 无独立 lesson) + DRF 装饰器顺序 + DRF ViewSet 缺失过滤静默忽略 query 参数 | N136, N197, N213, N218 | 3 (+1 early unnumbered archived in `archived-early/`) | — |
| `agent-protocol` | Agent 协议问题 (消息路由/consumer/heartbeat/僵尸连接假离线) | N145, N148, N216 | 3 (+3 early unnumbered archived in `archived-early/`) | — |
| `platform-env` | 平台环境问题 (Vite proxy/ADB 风暴/黑屏/agent 单例锁/venv 依赖漂移/conda gaf 环境规则未生效/环境归一化 L0) | N139, N154+N155, N186, N187, N188, N199 | 5 | N154+N155 |
| `command-errors` | 命令使用错误 + 反思纪律 (pre-commit stash/上下文预算/命令防错/PowerShell heredoc/git commit -m vs -F) | N150+N153, N160+N162, N165, N190 | 4 (N170 spec-36 撤销分发) | N150+N153, N160+N162 |
| `architecture` | 架构视角原则 (大修改架构优先 / backup-restore 安全 / 7 维度评估 / schema 归一化全链路扫描 / AI 可调试性 review gate / 双调试视角硬约束 / 任务归属硬约束) | N151, N167, N168, N191, N192, N193 | 6 | — |
| `debug-autoheal` | Debug 模式 AI auto-heal (截图方法基准盲点) | N141 | 1 | — |
| `agent-impl` | Agent 实现层 (LangGraph 子 agent 分发/透明 PNG alpha mask) | N158, N159, N195 | 3 | — |
| `pipeline` | 流水线问题 | — | 0 (+1 early unnumbered archived in `archived-early/`) | — |
| `spec` | 规范过度设计 | — | 0 (+1 early unnumbered archived in `archived-early/`) | — |

> **v9.0 家族合并 (2026-07-07)**: 6 个同根因家族已合并，每个家族主条目含"家族成员复发时间线"段保留历史。i18n 主题已并入 N109 家族时间线。
> **v9.0 taxonomy 补全 (2026-07-07)**: 补登 9 个未登记 lessons (N30/N142-N149)，topic 表全覆盖。
> **v9.0 Task B.1 早期归档 (2026-07-07)**: 6 个无 N## 编号的早期 lessons 移到 `archived-early/` 子目录，不参与 sync_ai_memory 索引。详见 `.ai-memory/meta/archived-lessons.md` § 早期无编号 lessons 索引。
> **v9.1 P2 家族合并 (2026-07-14)**: 5 组同主题 lessons 合并为家族主条目 (含 `merged_n_ids` front-matter + 家族合并说明段 + 两份原文件完整内容用 `---` 分隔):
> - `platform-env_2026-07-11-n154-n155-black-screen-agent-storm.md` (N154 + N155, 黑屏家族)
> - `command-errors_2026-07-14-n160-n162-context-budget-command-reflection.md` (N160 + N162, 工具使用纪律家族)
> - `ai-autonomy_2026-07-14-n161-n163-self-reliance-no-deferral.md` (N161 + N163, 自决不推卸家族)
> - `testing_2026-07-11-n156-n147-test-before-understand.md` (N156 + N147, 测试先于理解家族)
> - `command-errors_2026-07-08-n150-n153-pre-commit-stash-governance.md` (N150 + N153, pre-commit 治理家族)

---

## Quick Start — 按任务类型加载

| 任务类型 | 必读 topic | 检索命令 |
|---------|-----------|---------|
| new_feature | workflow + cross-layer-sync + agent-impl | `sync_ai_memory.py --query workflow` |
| bug_fix | hook-failure + honest-status + command-errors | `sync_ai_memory.py --query hook-failure` |
| documentation | honest-status + workflow + doc-governance | `sync_ai_memory.py --query honest-status` |
| refactor | workflow + concurrency + architecture | `sync_ai_memory.py --query workflow` |
| 测试相关 | testing | `sync_ai_memory.py --query testing` |
| 前端 i18n | ai-autonomy + browser-automation | `sync_ai_memory.py --query ai-autonomy` |
| 大修改 (> 500 行 diff) | architecture + command-errors + ai-autonomy | `sync_ai_memory.py --query architecture` |
| Agent / 设备相关 | agent-platform + agent-protocol + platform-env | `sync_ai_memory.py --query agent-platform` |

> **M3 diff 触发检索 (2026-08-15)**: 每次 commit 后 `gaf-lesson-diff-trigger` hook
> 自动跑 `scripts/lessons/match_lessons_by_diff.py --base HEAD~1 --head HEAD`,
> 按 diff 路径/新增行匹配 lesson front-matter `diff_keywords` 字段, 输出相关教训.
> 高频 lesson 建议补 `diff_keywords` (非空小写字符串列表, 取"下次这类改动 diff 里会出现
> 的词", 如 `sql-injection`/`cursor.execute`/`template_match`). 字段可选, 缺失不报错.

---

## 文件清单（按 N## 编号）

### workflow (28 files)
- `workflow_2026-06-15-n95-distribution-gap.md` — 4 层分发缺位
- `workflow_2026-06-15-n105-commit-bypass-rollback.md` — commit 透传 bug ⭐ **家族主条目** (合并 N107/N110/N114/M2.D)
- `workflow_2026-06-16-n108-commit-rule-relaxation.md` — commit 规则过严
- `workflow_2026-06-16-n117-m1h-decision-tree-changelog.md` — 决策树 changelog
- `workflow_2026-06-17-n121-m2f-bypass-weekly-review.md` — M2.F bypass weekly review
- `workflow_2026-06-21-n122-script-consolidation.md` — scripts/ 维护
- `workflow_2026-06-21-n123-ai-memory-restructure.md` — ai-memory restructure
- `workflow_2026-06-21-n124-skill-deletion-and-decision-tree-sync.md` — skill 删除引用残留
- `workflow_2026-06-21-n125-trash-temp-staging.md` — .trash/ 临时文件暂存
- `workflow_2026-06-28-n134-workflow-skill-not-triggered.md` — workflow skill 未联合触发 ⭐ **家族主条目** (合并 N134-recurrence)
- `workflow_2026-07-03-n140-filename-no-version.md` — 文件命名禁止版本号 (已退役见 §Retired, N181 条件 C)
- `workflow_2026-07-06-n149-r37-p3-wrapup-task-device-info-and-skill-sync-direction.md` — R37-P3 收尾: task.assign device_info gap + skill sync direction (已退役见 §Retired, N181 条件 A)
- `workflow_2026-07-14-n164-l1-l2-no-content-load-repeated-mistakes.md` — L1/L2 不加载教训内容 → AI 重复犯错
- `workflow_2026-07-16-n166-continuous-evaluation-loop.md` — 持续评估+循环修复模式 (L3 循环) + 沉淀纪律
- `workflow_2026-07-18-n171-script-performance-measurement.md` — 时间测量家族 (N171-N173 合并: 脚本性能 + spec/plan 用时测量) ⭐ **家族主条目**
- `workflow_2026-07-18-n172-ai-proactive-subagent-and-real-sedimentation.md` — subagent 并行家族 (N172-N175 合并: 主动并行 + 真沉淀 + 落地检查清单) ⭐ **家族主条目** (N175 已退役见 §Retired, N181 条件 C)
- `N174-td-registration-requires-fix-verification.md` — TD 登记必填"修复方案验证"字段
- `workflow_2026-07-19-n167-architecture-long-term-priority.md` — N167 七维度评分时架构长远性优先, 禁止"最小改动"自决方向
- `circular_mode_no_continue_prompt.md` — 循环模式 spec ✅ 后不问"继续?" (N166 L3-2 规则强化, 无 N## 编号)
- `workflow_2026-07-22-n182-bug-investigation-three-dimensional-root-cause.md` — bug 排查三维根因家族 (N182-N185 合并, TD-336 元 TD; 4 项思维链检查点: 链路归一化 / 三维根因 / 节点观测性 / 测试覆盖盲区) ⭐ **家族主条目**
- `N189-ai-led-development-governance-necessity.md` — AI 主导开发治理必要性元层认知 (N178-A3 增强: 区分 AI 自我治理 vs 治理形式化)
- `N201-m2-activation-review-loop.md` — M2 激活率"只测不治" (6 条全 LOW 无复盘闭环) → 复盘触发闭环 (effective_rate 排除 unknowable + REVIEW_TRIGGERED 标记 + 用户质疑四步响应) ⭐ **N201**
- `workflow_2026-08-09_n200-doc-placement.md` — 文档归属判定 (创建文档前必按 4 项清单判定归属; spec 完成立即归档) ⭐ **L0 硬约束** (project_rules.md §2.1.1)
- `N204-task-failure-auto-diagnosis.md` — 任务失败不自动诊断 (pipeline-task-diagnosis 仅在 bug_fix 条件分支被引用 → 需 L0 硬约束强制触发) ⭐ **L0 硬约束** (env-hardrules.md N204 段)
- `N202-large-file-split-patch-point-contract.md` — 大文件拆分踩坑家族 (s34-s40 共 27 坑: patch 点语义失效 / 装饰器行丢失 / re-export F401 / TS 顶层 import 丢失 / 级联 any 降级) — 拆前必跑 23 项检查清单 ⭐ **N202**
- `N208-commit-message-no-claim.md` — commit message 不写规则编号 (写 N## 被 M2 当声称核验 diff 证据, 无证据触发 REVIEW_TRIGGERED; 行为/合规类由 BEHAVIORAL_N 豁免) ⭐ **N208**
- `workflow_2026-08-28_n215-load-orchestrator-at-conversation-start.md` — 对话起始未加载 gaf-orchestrator (自执行入口步骤被跳过 → 判定/收尾纪律连带丢失) ⭐ **N215**

### ai-autonomy (5 files)
- `ai-autonomy_2026-06-16-n109-decision-relaxation.md` — AI 决策自决 ⭐ **家族主条目** (合并 N113/N115/N127, N108 保留独立)
- `ai-autonomy_2026-06-16-n111-command-timeout.md` — 命令超时主动中止
- `ai-autonomy_2026-07-14-n161-n163-self-reliance-no-deferral.md` — 架构决策不推卸 + 优先级排序自决 ⭐ **家族主条目** (合并 N161 + N163)
- `ai-autonomy_2026-07-28-n193-task-ownership-hard-constraint.md` — 任务归属硬约束 (spec 全部 ✅ ≠ 任务完成) ⭐ **L0 硬约束** (env-hardrules.md 任务归属段)
- `N206-askuserquestion-overreach.md` — AskUserQuestion 过度使用 (可自决误判为不可逆授权; 判定档位: 可恢复清理/机制扩展 → 自决; 仅跨机器 push/不可逆删除/N167 4 类硬场景 → 问)

### honest-status (3 files)
- `honest-status_2026-06-21-n126-honest-status-audit.md` — 文档诚实标记审计 ⭐ **家族主条目** (合并 N14/N101/N128/N130)
- `honest-status_2026-06-21-n129-audit-scope-must-be-comprehensive.md` — 审计范围 3 棵代码树
- `honest-status_2026-07-11-n157-ai-memory-doc-fabrication.md` — AI memory 文档虚构实现 (写前必 Glob/Read 实际代码)

### cross-layer-sync (5 files)
- `cross-layer-sync_2026-06-15-n106-sync-state-path.md` — 路径漂移
- `cross-layer-sync_2026-06-16-n112-p024-frontend-sync.md` — 后端字段→前端 4 步配套
- `cross-layer-sync_2026-07-05-n142-copy-paste-rename-all-identifiers.md` — 复制重命名必须改全部标识符
- `cross-layer-sync_2026-07-05-n143-authenticated-image-blob-fetch.md` — 认证图片 blob fetch
- `cross-layer-sync_2026-07-09-n152-drf-pagination-array-mismatch.md` — DRF 分页与前端数组期望不匹配 (ViewSet 必须显式声明 pagination_class)

### concurrency (1 file)
- `concurrency_2026-06-16-n116-m1g-concurrency-and-tier-benchmark.md` — 协作冲突+性能分层

### testing (10 files + 1 dormant)
- `testing_2026-06-17-n118-m2a-43-tests.md` — 测试套件环境依赖
- `testing_2026-06-23-n133-emulator-control-gap.md` — 模拟器设备控制 + 测试脚本循环点击
- `testing_2026-06-28-n135-refactor-needs-browser-login-verification.md` — 批量重构后浏览器验证 ⭐ **家族主条目** (合并 N135-ws)
- `testing_2026-07-11-n156-n147-test-before-understand.md` — 测试先于理解 (Python import + E2E 验证) ⭐ **家族主条目** (合并 N156 + N147)
- `testing_2026-07-29-n194-pytest-django-slowdown-agent-tests.md` — pytest-django 插件拖慢 agent 测试 (单测 12s → 0.02s, 全量 2h → 2.5min) ⭐ **L0 硬约束** (env-hardrules.md 测试运行段)
- `N196-real-device-pipeline-test-workflow.md` — 实机测试 pipeline 四步流程 (测前确认 → 节点链路分析 → 分阶段执行 → 日志驱动诊断); ADB 在线 ≠ 窗口可点击
- `testing_2026-08-28_n209-restart-backend-before-e2e.md` — 改码后服务未重启 → E2E 假绿 (旧签名恰兼容掩盖); E2E 前必确认服务已加载新代码 ⭐ **N209**
- `testing_2026-08-28_n210-e2e-prereqs-should-be-built.md` — E2E 前置配置缺失 ≠ 跳过, 应主动构造配置跑通入口 ⭐ **N210**
- `misc_2026-08-28_n212-playwright-e2e-script-pitfalls.md` — Playwright E2E 脚本三坑 (urljoin 吞路径段/页外请求不共享 JWT/antd Modal 隐藏 DOM 判定用 :visible) ⭐ **N212**
- `testing_2026-08-28_n214-e2e-env-data-hazards.md` — E2E 环境造数四坑 (测试自造 429/纯色模板病态/模拟器双视角重复注册/遗留假设备阻塞预检) ⭐ **N214**
- (dormant, merged to N111 family — kept for historical reference) `testing_2026-06-17-n119-m2b-command-hang.md` — 命令挂起 (N119, 家族主条目 N111 in ai-autonomy topic)

### hook-failure (2 files)
- `hook-failure_2026-06-17-n91-m2b-hook-failure.md` — pre-commit hook 失败映射
- `N203-evidence-session-cross-day-commit-failures.md` — evidence/session 跨天三坑 (session TTL / evidence 当天命名 / verification 格式)

### browser-automation (1 file)
- `browser-automation_2026-06-22-n131-playwright-browser-automation.md` — Playwright/browser-use 共存

### version-compat (2 files)
- `version-compat_2026-06-30-n137-ts60-erasable-syntax-and-baseurl-deprecation.md` — TS 6.0 erasableSyntaxOnly (enum→const) + baseUrl 弃用
- `version-compat_2026-07-05-n144-r37-p3-c5-antd-deprecation-and-fetch-on-mount.md` — antd 5.x Card bodyStyle 弃用 + store 空时直接进子页需 fetch

### agent-platform (3 files)
- `agent-platform_2026-06-30-n138-ctypes-hresult-signed-comparison.md` — ctypes HRESULT 有符号比较陷阱
- `agent-platform_2026-07-06-n146-ldopengl-singleton-ctypes-hot-loop.md` — ctypes.CDLL 热循环必须模块级单例缓存 (TD-011 LDOpenGL)
- `agent-platform_2026-08-28_n211-window-device-dynamic-binding.md` — 窗口设备动态绑定 (title/hwnd 会变 → 实时匹配 + 失效重连) ⭐ **N211**

### doc-governance (2 files: 1 active + 1 archived N30 in lessons/ root)
- `doc-governance_2026-06-24-n132-drf-react-pitfalls.md` — 文档职责分离 + 教训分类
- (archived N30, 文件在 lessons/ 根目录) `doc-governance_2026-07-07-n30-skill-rules-drift.md` — SKILL.md 与 project_rules.md 章节漂移 (v9.2 归档, 已被 N95+N132 覆盖)

### api-design (2 files + 1 archived)
- `api-design_2026-06-29-n136-url-routing-duplicate-prefix.md` — URL 路由前缀重复
- `misc_2026-08-28_n213-drf-decorator-order.md` — DRF 装饰器顺序 (policy 装饰器必须在 @api_view 之下, 否则 import 期 TypeError 全站 500) ⭐ **N213**
- (archived) `early archived lesson (已归档)` — API 404 tasks

### agent-protocol (4 files + 3 archived)
- `agent-protocol_2026-07-05-n145-login-poc-agent-no-response.md` — login PoC: agent heartbeat 正常但执行卡 pending, consumer 只 ACK 不更新 DB
- `agent-protocol_2026-07-06-n148-control-message-routing-and-db-pk-vs-business-id.md` — 双向控制消息缺路由标识被静默丢弃 + Channels group 路由混淆
- `agent-protocol_2026-08-28_n216-zombie-consumer-false-offline.md` — Agent 假离线 (僵尸 consumer 的 _heartbeat_checker 覆盖心跳状态, status↔offline 抖动; 重启后端即清) ⭐ **N216**
- `protocol_2026-08-29-message-frame-log-db-writes.md` — (L0) 消息帧 DB 写入三坑 (async sync ORM / thread_sensitive 并发 TMError / FK UUID) + 测试日志污染服务报错 (test.py NullHandler)
- (archived) `early archived lesson (已归档)` — agent popup bug
- (archived) `early archived lesson (已归档)` — capability mismatch
- (archived) `early archived lesson (已归档)` — message frame format

### platform-env (5 files)
- `platform-env_2026-07-02-n139-vite-proxy-localhost-ws-handshake.md` — Vite dev proxy 必须用 127.0.0.1 (避免 IPv6/IPv4 WS handshake 500)
- `platform-env_2026-07-11-n154-n155-black-screen-agent-storm.md` — ADB subprocess storm + autoreload 重复启动终端 → 黑屏 ⭐ **家族主条目** (合并 N154 + N155)
- `platform-env_2026-07-23-n186-agent-standalone-process-no-pid-lock.md` — agent 独立进程无 PID 文件锁单例检测 → 多进程冲突 WS 路由失效 (TD-339)
- `platform-env_2026-07-23-n187-venv-deploy-dep-drift.md` — venv gaf-agent 部署脚本 requirements.txt 漂移 → rapidocr-onnxruntime 缺失 (TD-337)
- `platform-env_2026-08-29-windows-detached-subprocess-console.md` — (L0) Windows detached 后台进程 spawn 控制台子进程 (redis-cli/tasklist/taskkill) 必须 CREATE_NO_WINDOW 防弹窗 + GBK 输出勿 text+utf-8, 用 bytes 比较

### command-errors (3 files)
- `command-errors_2026-07-08-n150-n153-pre-commit-stash-governance.md` — pre-commit 失败根因修复 + stash 丢失防护 ⭐ **家族主条目** (合并 N150 + N153)
- `command-errors_2026-07-14-n160-n162-context-budget-command-reflection.md` — 对话上下文预算管理 + 命令防错反思 ⭐ **家族主条目** (合并 N160 + N162)
- `command-errors_2026-07-16-n165-powershell-heredoc-repeated-mistake.md` — PowerShell heredoc 重复犯错 (无防错机制)

### architecture (3 files)
- `architecture_2026-07-08-n151-architecture-first-for-major-changes.md` — 大修改架构视角原则 (> 500 行 diff 必跑 5 步架构盘点)
- `architecture_2026-07-17-n167-refactor-evaluation-dimensions.md` — 代码重构/大规模修改 7 维度评估清单 (升级 §2.0.5 四维度)
- `architecture_2026-07-17-n168-backup-restore-security-fix.md` — backup/restore 双套反模式 + cursor.execute SQL 注入漏洞 (N168, create/restore 对称化 + 恶意输入拒绝测试)

### debug-autoheal (1 file)
- `debug-autoheal_2026-07-05-n141-screenshot-method-benchmark-blindspot.md` — 截图方法基准盲点 (Debug auto-heal 必须穷尽方案)

### agent-impl (3 files)
- `agent-impl_2026-07-12-n158-langgraph-agent-implementation.md` — LangGraph agent 实现层问题
- `agent-impl_2026-07-13-n159-long-task-subagent-delegation.md` — 长任务子 agent 分发 (上下文预算根本解法)
- `N195-transparent-png-alpha-mask-bug.md` — 透明 PNG 模板 alpha 通道丢失 → matchTemplate 置信度暴跌 (加载模板保留 alpha mask; TM_CCOEFF_NORMED 不支持 mask 时自动切 TM_CCORR_NORMED)

### pipeline (0 files + 1 archived)
- (archived) `early archived lesson (已归档)` — pipeline stuck running

### spec (0 files + 1 archived)
- (archived) `early archived lesson (已归档)` — spec overengineering

---

## 摘要文件（必读）

| # | File | What It Contains | Why Read It |
|:-:|------|-----------------|-------------|
| 1 | [summaries/code-rules.md](../summaries/code-rules.md) | Code patterns, tool limits, env rules | Prevents 38+ code errors, 9 tool errors, 10 env errors |
| 2 | [summaries/library-conflicts.md](../summaries/library-conflicts.md) | antd v5 deprecated APIs, React StrictMode, Vite parser issues | Prevents 15 runtime crashes from library conflicts |
| 3 | [summaries/architecture-mistakes.md](../summaries/architecture-mistakes.md) | Design errors, mock implementations, API mismatches, document status honesty | Prevents 19 architectural mistakes (including Phase R6 lessons) |
| 4 | [meta/yn-matrices.md](../meta/yn-matrices.md) | Y/N 检查矩阵 (按 topic 分类) | 反思清单/commit 前必读 |
| 5 | [meta/failure-modes.md](../meta/failure-modes.md) | 失败模式索引 (N## 编号 + 3 步兜底) | L1 启动硬加载 |

---

## Frontmatter Schema

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `date` | string (YYYY-MM-DD) | ✅ | 教训创建日期 |
| `symptom` | list[string] | ✅ | 症状关键词 (用于 `sync_ai_memory.py --query` 检索) |
| `solution` | string | ✅ | 根因 + 修复方案 + 防错机制 |
| `related_files` | list[string] | ✅ | 关联文件路径 (Glob 验证存在再写入) |
| `created_by` | string | ✅ | AI / manual |
| `priority` | string | ✅ | high / medium / low |
| `n_id` | string | ❌ | N## 编号 (L1 教训必填) |
| `level` | string | ❌ | L0 (历史记录) / L1 (可复用经验) |
| `cross_refs` | list[string] | ❌ | 关联 N## 编号 |
| `merged_n_ids` | list[string] | ❌ | 家族合并主条目标记 (如 [N150, N153]) |
| `l2_candidate` | bool | ❌ | 🆕 P1b (2026-07-16): true = 已沉淀到 `ai-operating-handbook.md` Part 2 (L2 硬加载); false/missing = 未沉淀, 高频时 `promote_lessons.py` 提议沉淀 |

**l2_candidate 字段规则**:
- 新建 lesson 时默认不写 (false)
- 当 lesson 沉淀到 `ai-operating-handbook.md` Part 2 红线段后, AI 手动设 `l2_candidate: true`
- `promote_lessons.py --dry-run` 检测到 `priority=high + cross_refs >= 3 + l2_candidate != true` 时提议沉淀
- 已标记 `l2_candidate: true` 的 lesson 不再被提议 (避免重复)

**新建 lesson frontmatter 模板** (复制后填充字段):

```yaml
---
date: 2026-MM-DD
symptom: [keyword1, keyword2]
solution: 根因 + 修复方案 + 防错机制
related_files:
  - path/to/file
created_by: AI
priority: high  # high / medium / low
n_id: NNNN      # L1 教训必填, L0 不写
level: L1       # L0 (历史记录) / L1 (可复用经验)
topic: <topic>  # 必填 (spec §6.2 P1-3 新增): workflow/ai-autonomy/honest-status/cross-layer-sync/concurrency/testing/hook-failure/browser-automation/version-compat/agent-platform/doc-governance/api-design/agent-protocol/platform-env/command-errors/architecture/debug-autoheal/agent-impl/pipeline/spec
cross_refs: [NXXX, NYYY]  # 关联 N## 编号 (可选)
# l2_candidate: true  # 仅当已沉淀到 ai-operating-handbook.md Part 2 时才设 true
---
```

---

## When to Re-Read

- **Starting any new feature** → Read topic `workflow` + `cross-layer-sync` + `agent-impl`
- **After fixing a bug** → Add the lesson to the relevant topic file
- **After discovering a new conflict** → Append to the relevant topic file immediately
- **commit 前** → Read `.ai-memory/meta/yn-matrices.md` 对应 topic
- **审计文档状态** → Read topic `honest-status`
- **大修改前 (> 500 行 diff)** → Read topic `architecture` + `command-errors`
- **Agent / 设备相关工作** → Read topic `agent-platform` + `agent-protocol` + `platform-env`

---

## Source

All entries extracted from actual mistakes recorded in:
- `docs/archive/completed-features.md` (Phase 完成记录)
- `docs/archive/pending-roadmap.md` (待实现功能计划)
- `.ai-memory/summaries/architecture-mistakes.md` (架构教训汇总)
