---
maintainer: derived-manual
source: GAF/.ai-memory/meta/yn-matrices.md (索引); topic 分片在 yn-matrices/
load_when: [反思清单, commit 前, 任务完成前]
priority: high
symptom: [yn-matrix, reflection-checklist, lesson-checklist]
solution: 反思时按 topic 加载对应 sub-file, 跑 Y/N 检查表
related_files:
  - .skills/skills/gaf-orchestrator/SKILL.md
  - .skills/skills/gaf-reflect-and-evolve/SKILL.md
  - .ai-memory/lessons/
  - .ai-memory/meta/yn-matrices/  # topic 分片
created_by: AI (N132 文档治理)
generated: 2026-06-22
auto_updated: 2026-09-01
last_manual_edit: 2026-07-26
---

# Y/N Matrices — 反思清单检查矩阵（N132 集中化）

> **来源**: N132 文档治理 — 用户反馈 "skill里也不该记录教训，这个不是有专门的地方记录吗"
> **职责**: 集中存放所有 Y/N 检查矩阵, SKILL.md 只保留框架引用
> **检索**: 按 topic 分章节, 每个 topic 独立 sub-file; 主文件只保留索引 + 加载策略
> **加载时机**: AI 自决 — 反思时 / commit 前 / 遇到对应场景时
> **拆分**: Phase 4 Task 4.2 — 87KB 主文件按 topic 拆分到 `yn-matrices/` 子目录, 主文件仅保留索引 (≤30KB)。各 topic 完整内容原样保留在对应 sub-file 中。

## Topic 索引 (Slice index)

> 每个 topic 的完整 Y/N 矩阵在对应 sub-file 中, 点击链接查看。
> **家族子条目明示 (TD-232 修复 — 2026-07-18)**: "包含 N##" 列中 `X/Y/Z (合并)` 表示家族合并子条目, 主条目为最后一个 N##; 详细家族关系见 `failure-modes.md` §Dormant。
> **Wave 2 精简 (2026-07-26, spec-2026-07-26-ai-governance-execution-rate-fix)**: 9 sub-file → 3 active + 6 archived. 保留真实执行率 > 50% + 有 evidence 的 (refactor-dimensions / workflow-commit / testing); 归档执行率 < 10% + 无 evidence 的 (workflow-spec / ai-autonomy / cross-layer-sync / honest-status / misc / workflow-reflection). 归档 sub-file 移入 `archived-yn-matrices/`, N## 引用关系保留 (作为历史 Y/N 矩阵的 evidence), `d7_index_consistency.py` / `sync_ai_memory.py` / `promote_lessons.py` 同时扫描 active + archived 目录.
> **lessons Topic → yn-matrices sub-file 映射 (TD-140 修复 — 2026-07-18; 2026-07-26 _workflow.md 拆分为 3 sub-file + Wave 2 精简)**: lessons/ 有 20 个 topic (按文件名前缀), yn-matrices/ 有 3 个 active sub-file + 6 个 archived sub-file, 映射关系: lessons `workflow`/`command-errors`/`hook-failure` → yn-matrices active `_workflow-commit.md` (commit/hook/skill 治理) + archived `archived-yn-matrices/_workflow-spec.md` (spec/plan/阶段/前端/技术债) + archived `archived-yn-matrices/_workflow-reflection.md` (反思/工具纪律/bug 排查); lessons `ai-autonomy` → archived `archived-yn-matrices/_ai-autonomy.md`; lessons `honest-status` → archived `archived-yn-matrices/_honest-status.md`; lessons `cross-layer-sync` → archived `archived-yn-matrices/_cross-layer-sync.md`; lessons `concurrency`/`browser-automation`/`control-message-routing`/`platform-env`/`agent-impl`/`agent-platform`/`agent-protocol` → archived `archived-yn-matrices/_misc.md`; lessons `testing` → active `_testing.md`; lessons `architecture`/`refactor-dimensions` → active `_refactor-dimensions.md`; lessons `version-compat`/`debug-autoheal`/`doc-governance` 无独立 Y/N 矩阵 (复用相关 topic)。

| Topic | Sub-file | 包含 N## | 触发场景 |
|-------|----------|---------|---------|
| workflow-commit | [§1](_workflow-commit.md) | N95, N96, N114, N117, N122, N124/N125/N126, N140, N150 (§7 hook-failure), N165, N169, N170 (合并 ㊱ 指针段, L1-小过度分发反例); P-020 已归档 archived-lessons.md (历史标识符 R25 闭环, 含 lesson N30, TD-179 修复 2026-07-18) | commit/hook/skill 治理 + pre-commit hook 失败根因修复 (N150); N165/N169/N170 合并到 ㊱ 指针段 (L1-小过度分发反例); N91 Hook ID 失败映射表 cross-ref 至 [archived-yn-matrices/_workflow-reflection.md](archived-yn-matrices/_workflow-reflection.md) §8 |
| workflow-spec | [§1-spec](archived-yn-matrices/_workflow-spec.md) | N173, N174, N175, N166 (L3 持续评估+循环修复 §3.7); §4.7 前端开发工作流 / §4.8 技术债务登记+Debug auto-heal / §4.9 阶段验收+全量回归 / §4.10 Spec 分阶段与跨会话续接 | spec/plan 执行 + 阶段验收 + 跨会话续接 + 前端开发工作流 + 技术债登记 + Debug auto-heal + subagent 并行结果落地 (N175) + L3 持续评估循环 (被动触发); N173 spec 用时测量 + AI 自决沉淀; N174 TD 登记必填修复方案验证; 脚本性能 (171) 在 project_rules §5.6 无独立 Y/N 矩阵; 主动并行+真沉淀 (172) 在 §2 ai-autonomy |
| workflow-reflection | [§1-reflection](archived-yn-matrices/_workflow-reflection.md) | N164, N166 (沉淀纪律 §3.8), N160/N162 (TD-316 修复 2026-07-21, 原引用 _command-errors.md 断链, 现并入 ㊲), N91 (Hook ID 失败映射表, 从 §7 hook-failure 迁入), §4.6 循环迭代反思分级触发, §8 bug 排查与根因评估 (N182/N183/N184/N185) | 反思分级触发 + 沉淀纪律 + L1/L2 不加载教训 + 工具使用纪律 (上下文预算管理 + 命令防错反思) + bug 排查链路归一化/三维根因/节点观测性/测试盲区 + N91 Hook ID 失败映射表 (bug 排查主题) |
| ai-autonomy | [§2](archived-yn-matrices/_ai-autonomy.md) | N109, N111, N113/N115/N127 (合并), N151, N172 | AI 决策/推进自决 (2026-07-18 N113/N115/N127 三矩阵合并为单一矩阵); N155 黑屏家族 Y/N 矩阵已迁 §12 misc platform-env; N167 七维度评估已归 §11 refactor-dimensions; N172 主动用 subagent + 真沉淀 (2026-07-18) |
| honest-status | [§3](archived-yn-matrices/_honest-status.md) | N126 (cross-ref), N128, N129, N130, N157 | 文档状态标记/审计/虚构实现 |
| cross-layer-sync | [§4](archived-yn-matrices/_cross-layer-sync.md) | N106, N112, N152 | 路径漂移/前后端字段同步 + DRF 分页契约 |
| misc (concurrency + browser-automation + control-message-routing + platform-env + agent-platform) | [§5+§8+§10+§12](archived-yn-matrices/_misc.md) | N116, N146, N131, N148, N154, N155, N211 | 并发状态管理 + native 句柄热循环单例 + Playwright/browser-use + 双向控制消息路由 + 平台环境 (黑屏家族 N154 代码层 + N155 行为层, 迁入) + 窗口设备动态绑定 (N211) |
| testing | [§6](_testing.md) | N118, N119, N142, N143, N147, N156, N196, N209/N210 | 测试套件环境依赖 + 复制粘贴/认证图片 + Playwright 前置读代码 + 实机测试四步流程 + E2E 前置构造/服务重启 (N209/N210) |
| i18n | 已合并到 [§2](archived-yn-matrices/_ai-autonomy.md) §N127 i18n 子段 | N127 (部分) | i18n 接入 (Phase 4 A14 合并孤儿文件) |
| hook-failure (§7) | 已拆分: N150 → [_workflow-commit_](_workflow-commit.md) §7 / N91 → [_workflow-reflection_](archived-yn-matrices/_workflow-reflection.md) §8 | N91, N150 | pre-commit hook 失败 (spec-17 合并孤儿文件; 2026-07-26 _workflow.md 拆分后 N91 迁至 reflection) |
| refactor-dimensions | [§11](_refactor-dimensions.md) | N167, N168, N178 | 代码/规则/skill 文档修改前 7 维度评估 + backup/restore 对称检查 + AI 思维链纠偏硬约束 A1-A4 (spec-59-B 从 rules §2.0.5 迁入, 单一权威源) |

## 各 Topic 摘要

### §1 workflow-commit — [查看完整](_workflow-commit.md)
commit/hook/skill 治理 Y/N 矩阵。涵盖分级分发 (N95)、L1/L2/L3 加载 (N96)、pre-commit hook staged-only (N114)、决策树 changelog (N117)、scripts/ 维护 (N122)、工作流治理 + .trash + 文档诚实标记 (N124/N125/N126)、文件命名禁版本号 (N140)、§7 hook-failure 段 (N150 pre-commit 失败根因修复 + 预存错误当场处理)。N91 Hook ID 失败映射表 cross-ref 至 [archived-yn-matrices/_workflow-reflection.md](archived-yn-matrices/_workflow-reflection.md) §8。P-020/N30 已归档 archived-lessons.md。

### §1 workflow-spec — [查看完整](archived-yn-matrices/_workflow-spec.md)
spec/plan 执行 + 阶段验收 + 跨会话续接 Y/N 矩阵。涵盖 spec/plan 用时测量 + AI 自决沉淀 (N173)、TD 登记修复方案验证 (N174)、subagent 并行结果落地检查 (N175)、L3 持续评估+循环修复 (N166 §3.7)、前端开发工作流 (§4.7)、技术债务登记 + Debug auto-heal (§4.8)、阶段验收 + 全量回归 (§4.9)、Spec 分阶段与跨会话续接 (§4.10)。

### §1 workflow-reflection — [查看完整](archived-yn-matrices/_workflow-reflection.md)
反思/工具纪律/bug 排查 Y/N 矩阵。涵盖循环迭代反思分级触发 (§4.6)、沉淀纪律 (N166 §3.8)、L1/L2 不加载教训内容 (N164)、工具使用纪律 (N160/N162 上下文预算管理 + 命令防错反思)、§8 bug 排查与根因评估 (N182 链路归一化 + N183 三维根因 + N184 节点观测性 + N185 测试盲区)、N91 Hook ID 失败映射表 (从 §7 hook-failure 迁入, bug 排查主题)。

### §2 ai-autonomy — [查看完整](archived-yn-matrices/_ai-autonomy.md)
AI 决策/节奏/入口/推进自决 Y/N 矩阵。涵盖 AI 自决范围 (N109)、命令超时主动中止 (N111)、节奏自决 (N113)、入口自决 (N115)、推进自决 (N127)、大修改架构视角原则 (N151)。(N155 黑屏家族已迁 §12 misc platform-env; N167 七维度评估已归 §11 refactor-dimensions。)

### §3 honest-status — [查看完整](archived-yn-matrices/_honest-status.md)
文档状态标记/审计 Y/N 矩阵。涵盖文档状态 3 步验证 (N128)、审计范围 3 棵代码树 (N129)、Roadmap 双向验证 (N130)、AI memory 文档虚构实现 (N157)。N126 文档诚实标记 cross-ref 自 §1。

### §4 cross-layer-sync — [查看完整](archived-yn-matrices/_cross-layer-sync.md)
路径漂移/前后端字段同步 Y/N 矩阵。涵盖路径一致性 (N106)、后端字段变更 → 前端 4 步配套 (N112)、DRF 全局分页 vs 前端数组期望 (N152)。

### §5+§8+§10+§12 misc — [查看完整](archived-yn-matrices/_misc.md)
小主题合并文件 (spec-14 合并 + platform-env 迁入)。涵盖 §5 并发状态管理 (N116 协作冲突 + N146 ctypes 热循环单例) + §8 browser-automation (N131 Playwright/前端路径漂移) + §10 双向控制消息路由 (N148 FK pk vs 业务标识符) + §12 platform-env (N154 代码层 + N155 行为层 黑屏家族, 从 §2 ai-autonomy 迁入) + 窗口设备动态绑定 (N211, 2026-08-28 补登)。

### §6 testing — [查看完整](_testing.md)
测试套件环境依赖 Y/N 矩阵。涵盖测试套件环境依赖 (N118)、命令卡死 (N119)、复制-粘贴重命名 (N142)、认证图片 blob (N143)、Python import 遗漏 + 端到端验证 (N147)、写 Playwright 前先读前端代码 (N156)、实机测试 pipeline 四步流程 (N196, s28 2026-08-17 补登)、E2E 服务重启 (N209) + E2E 前置构造 (N210, 2026-08-28 补登)。

### §7 hook-failure — 已拆分到 workflow-commit/workflow-reflection (spec-17 + 2026-07-26 拆分)
pre-commit hook 失败 Y/N 矩阵已拆分: N150 pre-commit 失败根因修复 在 [§1 workflow-commit §7 hook-failure 段](_workflow-commit.md); N91 Hook ID 失败映射表 在 [§1 workflow-reflection §8 bug 排查](archived-yn-matrices/_workflow-reflection.md)。原 `_hook-failure.md` 孤儿文件已删除; 原 `_workflow.md` 已于 2026-07-26 拆分为 3 sub-file 并移至 .trash/。

### §9 i18n — 已合并到 §2 ai-autonomy (Phase 4 A14)
i18n 接入模式 (useTranslation hook / 插值 / namespace / 日期本地化) 已合并到 [§2 ai-autonomy §N127 i18n 子段](archived-yn-matrices/_ai-autonomy.md)。原 `_i18n.md` 孤儿文件已删除。

### §11 refactor-dimensions — [查看完整](_refactor-dimensions.md)
N167 修改七维度评估 Y/N 矩阵。涵盖架构长远性/全局归一化/新旧兼容/现有业务完善/性能资源优化/安全合规加固/长期维护成本 7 维度。所有代码/规则文档/skill 文档修改前必跑。N178 AI 思维链纠偏硬约束 (A1-A4) 已从 rules §2.0.5 迁入 (spec-59-B 单一权威源)。

---

## 加载策略 (AI 自决)

| 场景 | 加载哪个 topic | 检索命令 |
|------|---------------|---------|
| commit 前 / 反思时 | 全部 topic 按需 | `Read yn-matrices/<topic>.md` |
| 改后端字段 | §4 cross-layer-sync | `Read .ai-memory/meta/yn-matrices/archived-yn-matrices/_cross-layer-sync.md` |
| 跑长命令 | §2 ai-autonomy (N111) | `Read .ai-memory/meta/yn-matrices/archived-yn-matrices/_ai-autonomy.md` |
| 审计文档状态 | §3 honest-status | `Read .ai-memory/meta/yn-matrices/archived-yn-matrices/_honest-status.md` |
| pre-commit hook 失败 | §1 workflow-commit §7 (N150) + workflow-reflection §8 (N91) | `Read .ai-memory/meta/yn-matrices/_workflow-commit.md` §7 + `Read .ai-memory/meta/yn-matrices/archived-yn-matrices/_workflow-reflection.md` §8 |
| 改 sync 脚本 / 并发锁 / native 句柄单例 | §5 misc (concurrency) | `Read .ai-memory/meta/yn-matrices/archived-yn-matrices/_misc.md` §concurrency |
| 写测试 | §6 testing | `Read .ai-memory/meta/yn-matrices/_testing.md` |
| 浏览器自动化 (Playwright/browser-use) | §8 misc (browser-automation) | `Read .ai-memory/meta/yn-matrices/archived-yn-matrices/_misc.md` §browser-automation |
| 写 WS 控制消息 (start/stop, subscribe/unsubscribe) | §10 misc (control-message-routing) | `Read .ai-memory/meta/yn-matrices/archived-yn-matrices/_misc.md` §control-message-routing |
| 涉及 Agent / Channels group | §10 misc (control-message-routing) | `Read .ai-memory/meta/yn-matrices/archived-yn-matrices/_misc.md` §control-message-routing |
| 启动 dev server 终端 / 黑屏 / ADB storm | §12 misc (platform-env) | `Read .ai-memory/meta/yn-matrices/archived-yn-matrices/_misc.md` §platform-env |

**AI 自决原则**:
- ✅ 任务开始时按 task_type 主动加载对应 topic sub-file
- ✅ 遇到特定场景（如改路径、跑长命令、审计状态）主动 Read 对应 sub-file
- ✅ 反思时按需加载, 不强制全读
- ❌ 禁止跳过反思清单 (§3.2 ①-⑤ 框架仍强制)
