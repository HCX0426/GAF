---
maintainer: derived-manual
source: .ai-memory/meta/failure-modes.md
load_when: [pre-commit 失败, e2e 失败, sync 异常, AI 主动追加, L1 启动硬加载]
priority: high
symptom: [workflow=failure-mode, hook-failed, sync-error, evidence-missing]
solution: 看 hook 输出找 ❌ 行 → 跑对应修复命令 → 重试
related_files:
  - .ai-memory/meta/yn-matrices/
  - .ai-memory/lessons/
  - .skills/skills/gaf-reflect-and-evolve/SKILL.md
created_by: AI
generated: 2026-06-14
auto_updated: 2026-07-18
p5_max_lines: 190
last_manual_edit: 2026-07-23
---

# Failure Modes — 失败模式索引

> **单一权威源** (v9.0+): 本文件只保留 N## 索引（N## + 主题 + 硬约束 1 行 + lesson 链接）; 详细触发/检测/兜底/根因/预防在 `lessons/<n##>.md`; Y/N 矩阵分片到 `yn-matrices/_<topic>.md`; 教训分类在 `lessons/README.md`
> **L1 硬加载**: `gaf_init.sh` grep `^| N[0-9]` ≥ 5 才算过
> **P5 治本硬约束**: 本文件正文 ≤ `p5_max_lines` (当前 190) 行 (不含 frontmatter), 超过触发 `promote_lessons.py --enforce-limits` 自动归档未被 yn-matrices 引用的 N## (注: 代码常量 FAILURE_MODES_MAX_LINES 需同步, 见 TD-312)

## 归档流程 (移动 N## 到 archived-lessons.md)

> **目的**: 控制 Active 段 N## 索引膨胀 (动态计数 — 由 `gaf_init.sh` / `sync_ai_memory.py` 自动 grep, 不硬编码), 保持高信噪比。
> **自动化状态**: 仅文档规则, 脚本自动化登记为 TD-214 (P3 [B] 类)。
> **状态四档判定标准**: 见 `archived-lessons.md` §状态四档判定标准 (活跃 / dormant / 归档 / 退役); 本节只描述移动流程, 不重复定义状态档。
> **四档分布**: Active/Retired/Dormant 三档在本文件 (段落行号随编辑漂移, 勿硬编码); archived (deprecated) 在 `archived-lessons.md`。§Dormant 只含家族合并子条目, M0.M 闭环 N## 在 §Retired 段 (硬约束已沉淀到 rules/skills), 两档不混。

**归档/退役触发条件** (按 `archived-lessons.md` 四档判定):
1. **dormant → 归档(deprecated)**: dormant (家族合并子条目) 超过 6 个月 + 无新复发 + 无 Y/N 矩阵引用
2. **Active → 退役(retired)**: M0.M 闭环 (硬约束已沉淀到 rules/skills, 不再需要独立索引)
3. **Active → 归档(deprecated)**: 近 30 天无触发 + 无 Y/N 矩阵引用 (罕见场景)

**归档/退役流程**:
1. AI 在 L3-1 扫描时主动检查 Active 段 N## 的 last-triggered 时间
2. 满足归档/退役条件 → 移动索引行到 `archived-lessons.md` 对应段 (§ Dormant N## 索引 / § 归档 N## 索引表)
3. lesson 文件保留在 `lessons/` (不删除, 历史可查)
4. Y/N 矩阵 sub-file 中对应 N## section 标 `archived: true`
5. 跑 `python scripts/bootstrap/sync_ai_memory.py` 重建索引

**归档撤销**: 若 archived N## 再次触发, AI 主动移回 Active 段 + 更新 mtime

**归档评估 (动态计数 — 不硬编码 N## 数量; 由 `sync_ai_memory.py` / `gaf_init.sh` 自动统计 Active/Dormant/Retired/Archived 四档分布; 历史退役见 `archived-lessons.md`)**。



### N## 出清与退役双机制（v9.2 Spec A cap + n181 月度评估）

- **cap 机械出清（`promote_lessons.py --enforce-cap`）**：硬上限 `ACTIVE_N_CAP=35`；判据 `last_triggered>30d && trigger_count≤5 && 未被 rules 层引用`；棘轮语义——有候选未清则 `--check-cap` 阻塞 commit，无可候选放行。维度=时效性+硬预算守门。
- **n181 月度退役评估（`n181_retirement_eval.py`）**：按"最近 N 个 spec 提及率=0"输出退役候选供人工决策。维度=活跃度（是否被引用）。
- **关系（互补非冲突）**：cap 守硬上限防膨胀，n181 做软活跃度体检；cap 已清条目自然退出 n181 候选集（已迁出 Active），两机制输出不冲突毋需去重。调参：想更快收敛到 35，优先削减 rules 层对陈旧 N## 的引用（被引用者永不出清是主要滞留原因）。

## Active N## 索引表（按编号排序 — 有独立 lesson 文件 + 被 yn-matrices 引用）

> N## 索引分 4 档: Active (本段) / Dormant (家族合并子条目, 见 §Dormant N## 索引) / Archived (见 `archived-lessons.md`) / Retired (M0.M 闭环, 编号永不复用, 见本文件 §Retired N## 索引).
> AI L1 硬加载只 grep Active 段。Dormant/Archived 按需 grep。

| N## | 主题 | 硬约束 (1 行) | Lesson 链接 | trigger_count | last_triggered |
|:---:|------|--------------|------------- |:---:|:---:|
| N109 | 计划内任务仍问用户 | 已计划任务 AI 自决选/拆/写/commit, 不问"是否开始" | `lessons/N109-decision-relaxation.md` | 6 | 2026-06-16 |
| N126 | 文档诚实标记 | Mock/Stub 标 🔧, 真实实现标 ✅, 虚报=假实现 | `lessons/N126-honest-status-audit.md` | 16 | 2026-06-21 |
| N134 | workflow skill 未被触发 | skill 调用需显式触发; 检查 skill 注册路径与 IDE 识别 | `lessons/N134-workflow-skill-not-triggered.md` | 11 | 2026-07-07 |
| N150 | pre-commit 失败根因修复 + 预存错误当场处理 | hook 失败必根因修复; `--no-verify` 仅限透传 bug 场景 (N105 已归档); 预存错误当场修或登记 TD | `lessons/N150-n153-pre-commit-stash-governance.md` | 8 | 2026-07-12 |
| N151 | 大修改架构视角原则 | 大修改必跑 5 步架构视角 (盘点→识别反模式→A/B/C→拒绝反模式→AI 自决); 详见 archived-yn-matrices/_ai-autonomy.md §2 ㉕ | `lessons/N151-architecture-first-for-major-changes.md` | 20 | 2026-07-16 |
| N154 | ADB subprocess storm + N146 backend gap → 黑屏 | 后台循环 >= 30s; 危险操作默认禁用 (opt-in); N146 单例修复必须覆盖 ALL 代码路径; ADB 优先用模拟器自带 | `lessons/N154-n155-black-screen-agent-storm.md` | 6 | 2026-07-11 |
| N166 | L3 持续评估循环 + 沉淀纪律 | L3 循环被动触发 (默认 spec ✅ 后停下, 触发词见 §3.6); 沉淀纪律强制 (边执行边沉淀); 详见 project_rules §3.6+§3.7+§3.8 | `lessons/N166-continuous-evaluation-loop.md` | 9 | 2026-07-21 |
| N167 | 代码重构 7 维度评估清单 | 修改前必跑 7 维度评估 (详见 project_rules §2.0.5 + _refactor-dimensions.md); 小修改豁免, 中修改跑 3 维, 大修改跑 7 维 + N151 | `lessons/N167-refactor-evaluation-dimensions.md` | 33 | 2026-07-21 |
| N171 | 脚本性能测量纪律 (71s/commit 数月未发现) | 所有脚本执行必加 `Measure-Command`; 对照性能基线 (单 hook < 1s / commit < 5s); batch 优先 import 而非 subprocess; 框架开销 >> 实际工作必重构; 详见 project_rules §5.6 | `lessons/N171-script-performance-measurement.md` | 7 | 2026-07-18 |
| N173 | spec/plan 不算用时 + AI 等用户提醒才沉淀 | 每个 spec/plan 完成后必测用时 (start_ts/end_ts); 对照基线 (小<5min/中<15min/大<60min/沉淀<5min); 超基线必跑根因 6 项检查; AI 自决沉淀不等用户提醒 (§3.8+N172 修复 B); 详见 N171-N173 家族 lesson (N173 section) + project_rules §4.9+§5.6 | `lessons/N171-script-performance-measurement.md` (N173 section) | 10 | 2026-07-26 |
| N176 | spec 完成立即 commit 再回填 hash 再 commit (spec-38 Phase 8 反模式: - + - 两次 commit) | 一次对话内完成的多个 spec 合并 1 次 commit; spec 完成后立即 follow-up edit 回填 hash (spec-59-C 修订, 原下次 spec commit 时回填实测常遗漏); 详见 project_rules §3.4 N176 段 | _(L1-中, 仅 rules + failure-modes 两层, 无独立 lesson 文件)_ | 19 | 2026-07-22 |
| N177 | 测试时间越来越久 (用户 2026-07-21 反馈) — 全套 pytest 默认跑 | spec Phase 2.1 测试范围按改动规模分级 (小<60s/中<120s/大<600s); 循环模式下每 2 spec 后必跑一次全套回归 (spec-59-C 修订); 详见 project_rules §4.9 N177 段 | _(L1-中, 仅 rules + failure-modes 两层, 无独立 lesson 文件)_ | 8 | 2026-07-21 |
| N178 | AI 思维链纠偏 — 既是规则制定者又是评分者 (spec-59-A 新增) | A1 反向论证无循环论证 / A2 维度 4-7 必须给理由 / A3 过度治理检查 / A4 spec 范围限制; 详见 _refactor-dimensions.md N178 段 (spec-59-B 单一权威源) | _(L1-中, 仅 rules + failure-modes 两层, 无独立 lesson 文件)_ | 7 | 2026-07-21 |
| N181 | 规则膨胀无退役 — N## 只增不减 (spec-59-C 新增; spec-62 TD-311 强化) | N## 月度评估 (原季度, spec-62 改) + Active N## > 70 硬阈值紧急评估 (spec-62 新增); 退役条件 A 连续 3 spec 未触发 (原 5, spec-62 改) / B 已被新 N## 覆盖 / C AI 默认行为已符合; 退役 ≠ 删除 (迁 §Retired); 详见 project_rules §4.12 N181 段 | _(L1-中, 仅 rules + failure-modes 两层, 无独立 lesson 文件)_ | 9 | 2026-07-22 |
| N182 | bug 排查三维根因评估系统性盲区 (TD-336 元 TD; 2026-07-22 OCR bug 排查暴露) | bug 排查启动阶段必跑 4 项思维链检查点: ① 链路归一化评估 (fail 节点上下游) ② 三维根因评估 (代码层+工作流层+规则层) ③ 节点观测性检查 (logger.warning+exc_info, 禁止静默吞错) ④ 测试覆盖盲区反思 (为什么测试没覆盖到); 详见 lesson N182 + TD-336 | `lessons/N182-bug-investigation-three-dimensional-root-cause.md` | 8 | 2026-07-22 |
| N183 | bug 修复三维根因评估 (TD-336; 2026-07-22 OCR bug 修复暴露) | bug 修复 commit 前 / TD 登记必跑三维根因评估 (代码层 + 工作流层 + 规则层), TD 模板新增"三维根因评估"必填字段; 详见 N182-N185 家族 lesson (N183 section) + TD-336 | `lessons/N182-bug-investigation-three-dimensional-root-cause.md` (N183 section) | 4 | - |
| N184 | 节点观测性硬约束 (TD-336; 2026-07-22 OCR bug 排查暴露) | 节点 fail_result 必带 logger.warning + exc_info + 上下游上下文 (输入参数 + 上游节点状态 + 失败原因), 禁止静默吞错; 用户原话"错误一定不能被隐藏了, 一定要有日志"; 详见 N182-N185 家族 lesson (N184 section) + TD-336 | `lessons/N182-bug-investigation-three-dimensional-root-cause.md` (N184 section) | 4 | - |
| N191 | schema 归一化数据流全链路扫描缺失 (2026-07-27 用户反馈"继续检查数据流" + "每次新对话真的还会知道怎么查吗") + 架构归一化 review gate 缺失 (2026-07-27 用户反馈"写完代码没从架构,归一化来看?") + **AI 可调试性 review gate 缺失 (2026-07-27 用户反馈"ai主导的项目,要是ai无法调试,那肯定不行啊")** + **mock_context fixture 漏设字段 (2026-07-27 P2 完成时发现 47+11+1 测试预先失败)** | schema 重构类任务完成前必跑 7 项数据流全链路扫描 (输出端/读取端/类型定义/测试/文档/资源/端到端); 节点间数据流必查 ROI 偏移传递; **架构归一化类任务 (坐标/设备/ROI/缩放/点击) 完成前必跑 §10.9 G1-G7 架构 review gate + §10.11 D1-D7 AI 可调试性 review gate**; spec 阶段识别架构决策点必用 8 维评分法 (D1-D4 AI 可调试性权重 > D5-D8 架构纯度); **AI 主导项目核心约束: 架构纯度再高, AI 调不了也是死路**; **节点加 `getattr(context, '<新字段>', None)` 后必同步更新所有 mock_context fixture 显式设该字段为 None (MagicMock 默认 truthy 会误走 transformer 路径); orchestrator 加 `hasattr(device, '<新方法>')` 后必同步更新 mock device fixture 设 return_value**; L3 触发加载, 见 `.ai-memory/meta/env-hardrules-contextual.md` §Schema 归一化硬约束 (N191) | `.ai-memory/meta/env-hardrules-contextual.md` §Schema 归一化硬约束 (N191) | 7 | 2026-07-27 |
| N192 | 双调试视角 review gate 缺失 (2026-07-27 用户反馈"需要你在写代码或者架构角度等加上这两个, 沉淀下") — AI 默认只从「代码正确性」单视角检查, 缺 AI 调试视角 + 用户调试视角双视角强制复查 | 任何 fix/add/refactor 类任务完成前必跑视角 A (AI 调试 7 项: 报错可读性/中间结果落盘/日志分段/节点链路可追溯/retry trace/截断保护/报错边界) + 视角 B (用户调试 7 项: 错误提示归一/错误码映射/错误定位/模板可跑通/校验前置/执行反馈/复现路径); **L0 强制常驻** (env-hardrules.md §L0 强制常驻提醒) + contextual 详细, 见 `.ai-memory/meta/env-hardrules-contextual.md` §双调试视角硬约束 (N192); spec 已归档 `docs/specs/archived/2026-07/2026-07-27-dual-debug-perspective-fixes.md` (13 问题 11 TDD 任务) | `.ai-memory/meta/env-hardrules-contextual.md` §双调试视角硬约束 (N192) | 19 | 2026-07-29 |
| N193 | 任务归属硬约束缺失 (2026-07-28 用户反馈"为啥遗留优化没加进这个spec的里面，以后在当前任务发现的问题都归属当前任务") — AI 在 spec 阶段全部 ✅ 后默认任务完成, 把实现过程中发现的优化建议/新问题作为"遗留建议"抛给用户决定, 而非自动纳入当前 spec 并实现 | 当前任务中发现的所有问题 (优化建议/新 bug/schema 不一致/测试缺口/文档过时) 必须立即纳入当前 spec (新增 task 或扩展现有 task), 不得作为"遗留建议"/"超出 spec 范围"/"如需实现请告知"抛给用户; spec 全部 ✅ ≠ 任务完成 (任务完成 = spec 全部实现 AND 发现的问题全部处理); 超出范围的优化必须在 spec "已知限制"段显式记录 (含描述+影响范围+建议优先级+为何不本次实现); L3 触发加载, 见 `.ai-memory/meta/env-hardrules-contextual.md` §任务归属硬约束 (N193); 详见 lesson N193 | `lessons/N193-task-ownership-hard-constraint.md` | 6 | 2026-07-29 |
| N195 | 透明 PNG 模板 alpha 通道丢失 → matchTemplate 置信度暴跌 (2026-07-30 用户测试 get_email.json 暴露; TD-335 根因) | 加载模板保留 alpha 通道作为 mask, 匹配用 `cv2.matchTemplate(..., mask=alpha)` 让透明区不贡献差异; 禁用 `PIL.convert('RGB')` 丢 alpha (透明区填纯黑 (0,0,0) 被当模板内容); TM_SQDIFF/TM_CCORR_NORMED 支持 mask, TM_CCOEFF_NORMED 不支持 mask 时自动切 TM_CCORR_NORMED; 详见 lesson N195 | `lessons/N195-transparent-png-alpha-mask-bug.md` | 2 | 2026-07-30 |
| N196 | 实机测试 pipeline 无标准流程 → 4 个反复错误 (2026-07-30 用户测试 get_email.json 暴露; 用户反馈"这种任务调试的经验需要沉淀下吗") | 实机测试 pipeline 必走"测前确认 → 节点链路分析 → 分阶段执行 → 日志驱动诊断"四步; 测前用 OCR+模板匹配确认当前画面处于节点链路哪个阶段, 不在起点则问用户返回路径 (不假设画面); "ADB 在线" ≠ "窗口可点击" (模拟器最小化也能跑 ADB), 必须额外检查窗口可见性; 点击失败优先查窗口前台状态 + input_method (SendInput 需前台, PostMessage 对 Unity 游戏无效); 详见 lesson N196 | `lessons/N196-real-device-pipeline-test-workflow.md` | 2 | 2026-07-30 |
| N200 | 文档归属判定缺失 — AI 将 spec 放入 Skill 目录 (2026-08-09 违反示例) | 创建任何新文档前必按 4 项清单判定归属 (Skill 定义 → .skills/; Spec/Plan → docs/specs/active/; 架构评估 → docs/architecture/; 用户可读 → docs/); 禁止 spec/plan/design 放入 Skill 目录; spec 完成后立即归档 docs/specs/archived/YYYY-MM/; L0 硬约束在 `.skills/rules/project_rules.md §2.1.1`; 详见 lesson N200 | `lessons/workflow_2026-08-09_n200-doc-placement.md` | 1 | 2026-08-09 |
| N201 | M2 激活率"只测不治" (2026-08-16 对比 TEST_SFCAPI 发现) — claimed-activation.md 已 6 条记录全 LOW 却无复盘闭环; rate 分母含 unknowable (声称无 lesson 的 N## 误判 LOW); 用户质疑无标准化响应协议 | 复盘触发闭环: effective_rate 排除 unknowable (分母 0 → N/A 不参与判定); 累计有效记录 ≥ 3 且最近 3 条中 ≥ 2 条 < 50% → 🔴 警告 + REVIEW_TRIGGERED 标记 (幂等); AI 看到标记必按复盘模板 Q1-Q4 执行; 用户质疑四步响应 (确认→根因→修复→判沉淀); 详见 lesson N201 | `lessons/N201-m2-activation-review-loop.md` | 1 | 2026-08-16 |
| N202 | 大文件拆分踩坑家族 (s34 views.py + s35 pipeline_engine.py + s36 device.py + s37 models.ts 共 16 坑) — patch 点语义失效最隐蔽 (execute 移出后测试 patch 模块属性注入 fake 失效, 12 测试失败); 方法区间丢装饰器行 (@staticmethod/@dataclass 丢失 → N805/TypeError); header 过滤 set 匹配误伤同字符串行; re-export 被 ruff F401 删 (测试 import 契约断); 多行括号 import 正则漏扫; mixin 带参 super().__init__ MRO 到 object; TS 拆丢顶层 import (API 命名空间 TS2503) + 注释内类型名生成假跨域 import (TS6133) + 类型级联降级 any 误伤组件 | 拆前必跑 16 项检查清单 (patch 点 grep / AST import 契约 / decorator_list[0].lineno / 顺序块匹配 / logger 置后 / __all__ re-export / mixin 继承基类 / 源码断言拼接 / 脚本幂等 / 全量测试 / TS 顶层 import 保留 / 注释排除 / 基线对比); 被 patch 属性用转发函数运行时查原模块; 详见 lesson N202 | `lessons/N202-large-file-split-patch-point-contract.md` | 4 | 2026-08-18 |
| N203 | pre-commit evidence/session 跨天失败三坑 (s45, 2026-08-20) — session 24h TTL 跨午夜过期; evidence 目录日期前缀必须 == commit 当天; verification.md 需 `## Verification` 标题 + 行首命令 | commit 前自检: 跨午夜先 `check_session_active.py --create`; evidence 目录按当天命名 (跨天 git mv); verification.md 含 `## Verification` 标题 + bash 块内行首命令 (pytest/ruff/npm); 详见 lesson N203 | `lessons/N203-evidence-session-cross-day-commit-failures.md` | 1 | 2026-08-20 |
| N204 | 任务失败不自动诊断 — pipeline-task-diagnosis 仅在 bug_fix 条件分支被引用, 规则层无 L0 硬约束, AI 可合法跳过诊断 (2026-08-21 三方联动评估发现) | 对话中出现失败关键词 / 日志含 pipeline 错误码 (NODE_TIMEOUT/TEMPLATE_NOT_FOUND/OCR_LOW_CONFIDENCE) 时, 必须调用 `Skill(name='pipeline-task-diagnosis')`; 即使任务分类为 new_feature/refactor/documentation 也适用; 跳过诊断必须记录理由; **L0 强制常驻** (env-hardrules.md §L0 强制常驻提醒) + contextual 详细, 见 `.ai-memory/meta/env-hardrules-contextual.md` §诊断触发硬约束 (N204) | `.ai-memory/meta/env-hardrules-contextual.md` §诊断触发硬约束 (N204) | 0 | 2026-08-21 |
| N206 | AskUserQuestion 过度使用 (2026-08-21 config/scripts 整理; 复发 2026-08-24 元评估后问"要不要沉淀"; 复发 #2 2026-08-24 修完明显 bug 问"要不要修它" — 明显缺陷修复属自决) — 可自决误判为不可逆授权, 连续询问清理范围/机制扩展/是否沉淀/是否修复 (规则 §3.5 本地删除可自决 + §3.6 计划内自治 + §3.8 沉淀自决 + N193 任务归属已覆盖) | 判定档位: 可恢复清理 (git 追踪删除 / git mv / 副本去重 / README 登记) + 机制内扩展 (hook 扩展) + 计划内推进 + **沉淀动作 → 自决不问** (N172: "应该沉淀"=同回复立即调工具落盘, 勿反问用户) + **明显缺陷修复 (可复现/根因明确/方案在架构内) → 自决修不问**; 仅 4 类必须 AskUserQuestion (跨机器 push / 不可逆删除 branch -D 等 / N167 4 类硬场景 FK/schema/业务语义/不可逆 / 规则未覆盖歧义); 自检一句: "git 能恢复吗? 能 → 自决"; 详见 lesson N206 | `lessons/N206-askuserquestion-overreach.md` | 2 | 2026-08-24 |
| N208 | commit message 写规则编号(N##)声称 (2026-08-22 创建 lesson 却漏登 Active 索引; 2026-08-24 正确性审计补登) | commit message 是改动描述面, 不写 N## (写 N## 被 M2 当声称核验 diff 证据, 无证据触发 REVIEW_TRIGGERED); 仅在 diff 真有证据时才可写对应编号; 行为/合规类 (N192/N204/N193) 已由 BEHAVIORAL_N 豁免但仍不建议写; **L0 常驻** (env-hardrules.md §L0 常驻提醒 + project_rules §3.4); 详见 lesson N208 | `lessons/N208-commit-message-no-claim.md` | 1 | 2026-08-24 |
| N209 | 改码后服务未重启 → E2E 部分入口"假绿" (2026-08-28 TaskChain B1 force_agent_id 500, 而 Task/Pipeline 旧签名恰兼容显示 SUCCESS) | 改 backend/agent 代码后 E2E 前必确认服务已加载新代码 (daphne/celery/agent 进程启动时间或重启验证); 新参数/新分支必须有独立 E2E 用例, 防"旧签名恰兼容"掩盖; 与 N99 (Vite 缓存旧代码) 同族: 改了却不全通过先查服务是否加载新代码; 详见 lesson N209 | `lessons/testing_2026-08-28_n209-restart-backend-before-e2e.md` | 1 | 2026-08-28 |
| N210 | E2E 前置配置缺失就跳过 (2026-08-28 用户两次纠正: 缺 GameProfile.routine/设备绑定/默认链) | E2E 前置缺失 ≠ 跳过 — 应主动构造配置把入口跑通; 禁止以"环境前置缺失"标跳过, 除非构造成本超出测试价值并显式告知; 详见 lesson N210 | `lessons/testing_2026-08-28_n210-e2e-prereqs-should-be-built.md` | 0 | 2026-08-28 |
| N211 | 窗口设备固定 title/hwnd 锚定失效 (2026-08-28: 页面标题会变/句柄随浏览器重启变) | 浏览器/游戏窗口设备不靠固定 title 或固定 hwnd 锚定 — 执行时实时匹配 (子串/进程名) + 缓存 hwnd 失效即强制重连重绑; 详见 lesson N211 | `lessons/agent-platform_2026-08-28_n211-window-device-dynamic-binding.md` | 0 | 2026-08-28 |
| N212 | Playwright E2E 脚本三坑 (2026-08-28 full_routes 首跑 + I-06 复核) — urljoin 吞路径段 / context.request 不共享前端 localStorage JWT / antd5 Modal 关闭后保留隐藏 DOM | 脚本三查: URL f-string 直拼禁 urljoin; 页面外请求(probe/fetch)手动带 Authorization(sessionStorage access_token); DOM 判定用 `:visible` 而非 count; 详见 lesson N212 | `lessons/misc_2026-08-28_n212-playwright-e2e-script-pitfalls.md` | 0 | 2026-08-28 |
| N213 | DRF 装饰器顺序 (2026-08-28 新增模板匹配端点致全站 500) — @permission_classes 写在 @api_view 之上 → import 期 TypeError | 新 DRF FBV 装饰器顺序: extend_schema → api_view → permission_classes (policy 在 api_view 之下); 后端 500 + 日志指 urls import 链先查装饰器顺序; 详见 lesson N213 | `lessons/misc_2026-08-28_n213-drf-decorator-order.md` | 0 | 2026-08-28 |
| N214 | E2E 环境造数四坑 (2026-08-28 全量测试 + 匹配端点 + 模拟器补测) — 测试自造 429(throttle) / cv2 纯色模板病态 / 雷电 ldconsole+adb 双视角重复注册 / 遗留假设备阻塞预检 | 造数前四查: throttle 额度是否被测试总量打爆(先查设置); 匹配测试图带纹理; 设备多数据源先归一再去重; 数据库遗留假记录定期清理; 详见 lesson N214 | `lessons/testing_2026-08-28_n214-e2e-env-data-hazards.md` | 0 | 2026-08-28 |
| N215 | 对话起始未加载 gaf-orchestrator (2026-08-28 整轮 E2E/文档/沉淀对话无入口判定; 用户追问暴露) — 自执行入口步骤被跳过, 连带收尾(沉淀/反思)纪律一起丢 | 每次对话第一条任务消息先 `Skill(name='gaf-orchestrator')` 判定 task_type → 按分支加载 skill+KB 再动手; 恢复会话(summary 续接)同样必做; 收尾该 commit 后跑 gaf-lesson-router collect; 详见 lesson N215 | `lessons/workflow_2026-08-28_n215-load-orchestrator-at-conversation-start.md` | 0 | 2026-08-28 |
| N216 | Agent 假离线 (2026-08-28 状态灯显示未启动但 agent 心跳新鲜) — 僵尸 consumer 的 _heartbeat_checker 永不取消, 每 10s set_agent_offline 覆盖新连接写入的 idle, 形成 idle↔offline 抖动 | 诊断口诀: status 与 last_heartbeat 矛盾 + 日志"心跳超时 15xxx s"(秒数递增) = 僵尸连接, 重启后端进程树 (`gaf_daemon.py restart`) 即清; 治本: Agent 加 active_channel 字段做最新连接仲裁; 详见 lesson N216 | `lessons/agent-protocol_2026-08-28_n216-zombie-consumer-false-offline.md` | 0 | 2026-08-28 |


### Archived-Early N## 索引（低触发归档）

> 以下 N## trigger_count ≤ 1, 按 TD-343 归档标准迁移。保留 lesson 文件在 `lessons/archived-early/`，按需 grep 加载。
> 归档标准: trigger_count ≤ 1 且不是 very-recent (last_triggered ≠ '-')
> 注意: 完整的 archived 索引在 `archived-lessons.md`（单一权威源），此处仅保留归档段标题。

## Retired N## 索引 (M0.M 闭环 — 硬约束已沉淀到 rules/skills, 不再独立索引)

> 以下 N## 已闭环, 硬约束已沉淀到 `project_rules.md` 或 skills, 不再独立索引。编号永不复用。
> AI 按需 grep 即可, L1 不硬加载。

| N## | 主题 | 硬约束沉淀位置 | 闭环原因 |
|:---:|------|--------------|---------|
| N96 | 跳过 L2 软指导 | `ai-operating-handbook.md` Part 1 L2 段 | M0.M 闭环 (L2 已硬加载) |
| N97 | evidence 不进仓库 | `project_rules.md §3.4` + `gaf-reflect-and-evolve/SKILL.md §2 ⑤` | M0.M 闭环 (evidence commit 已成习惯) |
| N100 | Set-Content 损坏 f-string | `ai-operating-handbook.md` Part 2 命令使用段 | M0.M 闭环 (已用 Write 工具) |
| N101 | 状态标记不诚实 | `project_rules.md §0` + `ai-operating-handbook.md` Part 2 诚实标记段 | M0.M 闭环 (已沉淀到红线) |
| N108 | commit 规则过严 | `project_rules.md §3.4` (AI 可自执行 git add + git commit) | M0.M 闭环 (commit 自决已沉淀到 §3.4) |
| N165 | PowerShell heredoc 不支持 + 重复犯错 | `ai-operating-handbook.md` Part 2 命令使用段 (L2 硬加载) + `project_rules.md §5.2` Shell 命令限制 | N181 条件 C 退役 (AI 默认行为已符合 + L2 硬加载已沉淀; spec-59-D 2026-07-21) + **superseded_by N190 (2026-07-26): N190 反转原修复建议 — 禁用 `-F` 改多 `-m`, L0 硬约束在 env-hardrules.md Shell 段** |
| N170 | `git commit -F` 弹窗 vs `-m` 不弹窗 | `project_rules.md §3.4` (N176 + N153 已覆盖 commit 机制) | N181 条件 B 退役 (已被新 N## 覆盖; spec-36 2026-07-19 撤销分发 → spec-59-D 2026-07-21 退役) |
| N138 | ctypes HRESULT 有符号比较 | `../_archive/lessons-retired/N138-ctypes-hresult-signed-comparison.md` (archived, TD-374) | N181 条件 A 退役 (trigger=1, 连续 3 spec 未触发; s28 2026-08-17 退役) |
| N139 | Vite dev proxy localhost 解析歧义 | `project_rules.md §1.3` (Vite dev proxy 必须用 127.0.0.1) | N181 条件 C 退役 (硬约束已沉淀 §1.3; s28 2026-08-17 退役) |
| N140 | 文件命名禁止版本号 | `project_rules.md §2` (文件命名禁止带版本号) | N181 条件 C 退役 (硬约束已沉淀 §2; s28 2026-08-17 退役) |
| N142 | 复制重命名必须改全部标识符 | `../_archive/lessons-retired/N142-copy-paste-rename-all-identifiers.md` (archived, TD-374) | N181 条件 A 退役 (trigger=1, 连续 3 spec 未触发; s28 2026-08-17 退役) |
| N143 | 认证图片 blob fetch | `../_archive/lessons-retired/N143-authenticated-image-blob-fetch.md` (archived, TD-374) | N181 条件 A 退役 (trigger=1, 连续 3 spec 未触发; s28 2026-08-17 退役) |
| N144 | antd 5.x Card bodyStyle 弃用 + store 空时直接进子页需 fetch | `../_archive/lessons-retired/N144-r37-p3-c5-antd-deprecation-and-fetch-on-mount.md` (archived, TD-374) | N181 条件 A 退役 (trigger=1, 连续 3 spec 未触发; s28 2026-08-17 退役) |
| N149 | task.dispatch device_info gap + skill 编辑方向 | `../_archive/lessons-retired/N149-r37-p3-wrapup-task-device-info-and-skill-sync-direction.md` (archived, TD-374) | N181 条件 A 退役 (trigger=1, 连续 3 spec 未触发; s28 2026-08-17 退役) |
| N157 | AI memory 文档虚构实现 — 路径/文件名/节点类型/成熟度全错 | `../_archive/lessons-retired/N157-ai-memory-doc-fabrication.md` (archived, TD-374) | N181 条件 A 退役 (trigger=1, 连续 3 spec 未触发; s28 2026-08-17 退役) |
| N175 | subagent 并行结果落地不清 (Spec 25: 8 TD 并行, 仅 3 TD evidence) | `project_rules.md §3.6` (subagent 并行结果落地检查清单) | N181 条件 C 退役 (硬约束已沉淀 §3.6; s28 2026-08-17 退役) |
| N188 | conda gaf 环境规则多次未生效 (2026-07-25 用户反馈"问题好多次了") | `env-hardrules.md` Python 环境硬约束段 (L0 alwaysApply) | N181 条件 C 退役 (L0 硬约束完全覆盖; TD-371 2026-08-20 退役) |
| N190 | PowerShell heredoc / && / | `env-hardrules.md` Shell 命令硬约束段 (L0 alwaysApply) | N181 条件 C 退役 (L0 硬约束完全覆盖; TD-371 2026-08-20 退役) |
| N194 | pytest-django 插件拖慢 agent 测试 (2026-07-29 用户反馈"测试为啥这么久, 看慢的原因") — `pyproject.toml` 配置 `DJANGO_SETTINGS_MODULE` 导致 pytest-django 插件在 agent 测试时也强制 `django.setup()` (含 channels Redis 连接超时), 单测试 12s 起步, 全量 ~2h; AI 历史上多次跑 agent 测试都用默认命令, 慢但未深究根因, 误判为 retry 真睡 / Windows IO 慢 | `env-hardrules-contextual.md` §测试运行硬约束 (N194, 已退役) | N181 条件 C 退役 (L0 硬约束完全覆盖; TD-371 2026-08-20 退役) |
| N197 | URL 拼接归一化缺失 — agent/前端/脚本硬编码 `/api/v2` (2026-08-01 用户反馈"只改动一个地方的版本就可以变所有app") | `env-hardrules-contextual.md` §URL 拼接归一化硬约束 (N197, 已退役) | N181 条件 C 退役 (L0 硬约束完全覆盖; TD-371 2026-08-20 退役) |
| N198 | 调度协调机制架构缺位 — Worker/Beat 未启动、进程重复、Pending 无恢复 (2026-08-02 用户反馈系统卡住排查) | `env-hardrules-contextual.md` §调度协调硬约束 (N198, 已退役) | N181 条件 C 退役 (L0 硬约束完全覆盖; TD-371 2026-08-20 退役) |
| N199 | 双环境 (conda gaf + venv gaf-agent) 归一化缺失 (2026-08-02 归一化) | `env-hardrules-contextual.md` §环境归一化 (N199, 已退役) | N181 条件 C 退役 (L0 硬约束完全覆盖; TD-371 2026-08-20 退役) |
| N179 | 反思形式化 — "无 A 类" 就过 (spec-59-A 新增) | `project_rules.md §4.6` + `gaf-reflect-and-evolve/SKILL.md §2` (反思分级检查清单) | N181 条件 A 退役 (trigger=1, >30 天未触发; 治理瘦身 gate-2 2026-08-26, 检查清单已沉淀, 退役) |
| N180 | 元评估死循环 — 只列弱项不开 spec (spec-59-A 新增) | `project_rules.md §4.11` (元评估闭环 4 项必填: 弱项/根因/建议/闭环) | N181 条件 A 退役 (trigger=1, >30 天未触发; 治理瘦身 gate-2 2026-08-26, 闭环机制已沉淀, 退役) |
| N186 | agent 独立进程单例锁缺失 (TD-339; 2026-07-23 BD2 测试暴露) | `lessons/N186-agent-standalone-process-no-pid-lock.md` + `project_rules.md §1` (agent 单例锁指针) | N181 条件 A+C 退役 (trigger=1, >30 天未触发; 治理瘦身 gate-2 2026-08-26, 技术约束存于 lesson + §1 指针, 退役) |
| N187 | venv 部署脚本依赖漂移 (TD-337; 2026-07-23 BD2 测试暴露) | `lessons/N187-venv-deploy-dep-drift.md` + handbook 症状表已标 "§Retired N187" | N181 条件 A+C 退役 (trigger=2, >30 天未触发; 治理瘦身 gate-2 2026-08-26, 技术约束存于 lesson, 退役) |

## Dormant N## 索引 (家族合并子条目 — 不独立索引, Y/N 矩阵保留在家族主条目)

> 以下 N## 已合并到家族主条目, 不独立索引, 但编号永不复用。
> 详细复发历史在主条目"家族成员复发时间线"段; Y/N 矩阵保留在家族主条目对应 sub-file。

| N## | 主题 | 家族主条目 | Y/N 矩阵位置 |
|:---:|------|-----------|--------------|
| N107/N110/N114 | commit 透传 bug 早期变体 | N105 | `_workflow.md` N105 段 |
| N113/N115/N127 | AI 决策自决早期变体 | N109 | `archived-yn-matrices/_ai-autonomy.md` N109 段 |
| N119 | 命令挂起 | N111 | `archived-yn-matrices/_ai-autonomy.md` N111 段 |
| N128/N130 | 文档诚实标记早期变体 | N126 | `archived-yn-matrices/_honest-status.md` N126 段 |
| N147 | 测试先于理解早期变体 | N156 | `_testing.md` N156 段 |
| N153 | pre-commit stash 早期变体 | N150 | `_workflow.md` §7 N150 段 |
| N155 | 黑屏 agent storm 早期变体 | N154 | `archived-yn-matrices/_misc.md §12 platform-env` (spec-25 Phase 5 TD-248 从 `archived-yn-matrices/_ai-autonomy.md §㉖` 迁入, 主 lesson 在 platform-env topic) |
| N162 | 上下文预算早期变体 | N160 | `_workflow.md` ㊲ N160/N162 Y/N 矩阵段 (TD-316 修复 2026-07-21, 原引用 `_command-errors.md` 断链) |
| N163 | 自决不推卸早期变体 | N161 | `archived-yn-matrices/_ai-autonomy.md` N161 段 |
| N169 | TD "延后" 语义 + L3 循环被动触发早期变体 (spec-33 Phase 4 合并) | N166 | `_workflow.md` N166 段 |

## 加载策略 (AI 自决 — N132 强化, v9.3 归一化)

> **v9.3 归一化 (2026-07-16)**: 本节原含 L1/L2/L3 加载策略表, 与原 `loading-strategy.md` §加载决策表重复且漂移。已删除, 单一权威源在 `meta/ai-operating-handbook.md`。
> **L2 文件数 (v9.5)**: 2 文件 (ai-operating-handbook.md + tech-stack.md)。
> 详见 `meta/ai-operating-handbook.md` Part 1 加载决策表。

## AI 主动追加流程（O2 / N88 修复）

**何时追加**: 当本次失败原因**不在上述索引表中**时, AI 必须追加新 entry。

**追加格式** (v9.1 表格归一化 — 2026-07-17 spec-13 Phase 1 [A]-R3-1 修复):

在 Active N## 索引表末尾追加 1 行表格行 (4 列), 格式参考 N168 最新条目:

```markdown
| N<编号> | <一句话失败名> | <1 行硬约束> | `lessons/<topic>_<date>-n<编号>-<slug>.md` |
```

**配套动作** (L1-大 5 层分发, 见 `gaf-lesson-router/SKILL.md §3`):
1. 创建 lesson 文件: `.ai-memory/lessons/<topic>_<date>-n<编号>-<slug>.md` (topic 见 `lessons/README.md`)
2. 在 `yn-matrices/_<topic>.md` 追加 `### ⑲ N<编号> ...` Y/N 矩阵段
3. 在 `yn-matrices.md` 索引表对应 topic 行的"包含 N##"列追加 `N<编号>`
4. (如适用) 在 `summaries/architecture-mistakes.md` 追加同根因家族摘要
5. (如适用) 在 `project_rules.md` 对应章节追加硬约束 1-3 行 + 索引引用

**预 commit 验证**（`gaf-lessons-updated` hook, spec-13 Phase 2 升级支持表格格式）:
- 缺 `硬约束` / `Lesson` 链接 → 拒绝
- 编号冲突 (N## 重复) → 拒绝
- 不在 `lessons/` 里找到对应文件 → 拒绝
