---
maintainer: derived-manual
source: Split from yn-matrices/_workflow.md (Phase 4 拆分优化 2026-07-26)
generated: 2026-07-26
auto_updated: 2026-07-26
last_manual_edit: 2026-07-26
load_when: [spec, plan, 阶段验收, 前端, 技术债, L3循环]
priority: medium
symptom: [workflow-spec, spec-execution, tech-debt-register]
solution: spec/plan 执行 + 阶段验收 + 跨会话续接 + 前端工作流 + 技术债登记 + subagent 并行 Y/N 矩阵; 详见各家族段
related_files:
  - .skills/rules/project_rules.md
  - docs/archive/active-tech-debt.md
---

# _workflow-spec.md — spec/plan/阶段/前端/技术债 Y/N 矩阵

> 原 `_workflow.md` (697 行) 按 N## 家族拆分为 3 sub-file。本文件主题: spec/plan 执行 + 阶段验收 + 跨会话续接 + 前端开发工作流 + 技术债登记 + Debug auto-heal + subagent 并行落地 + L3 持续评估循环。姊妹文件: [_workflow-commit.md](_workflow-commit.md) (commit/hook/skill 治理) | [_workflow-reflection.md](_workflow-reflection.md) (反思/工具纪律/bug 排查)

### ㉙ N173 spec/plan 用时测量 + AI 自决沉淀 Y/N 矩阵（必填, L1-大 5 层分发）

> **触发条件**（任意一条即触发）:
> - spec/plan 完成 + commit 后
> - AI 听到用户反馈新规则/新要求
> - 用户原话触发: "每个计划或者spec算用时" / "不是合适的时间就找原因" / "这需要我告诉你要沉淀才会沉淀？"
> - AI 在回复末尾写 "应该沉淀" 类语句

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | spec/plan 完成后是否记录 start_ts + end_ts + duration? | ☐ | 报告含 duration 字段 |
| 2 | duration 是否对照 spec 规模基线 (小<5/中<15/大<60/沉淀<5 min)? | ☐ | 报告含 "在基线内" 或 "超基线 X min" |
| 3 | 超基线时是否跑根因 6 项检查? | ☐ | 报告含根因分析 (① 串行 / ② pre-commit / ③ 路径 / ④ Read / ⑤ 拆分 / ⑥ 上下文) |
| 4 | AI 听到用户新要求是否自决判定沉淀 (不等用户说"沉淀")? | ☐ | 同一回复内有 Write/Edit 工具调用 |
| 5 | 沉淀是否在同一回复内调用工具 (N172 修复 B)? | ☐ | 工具调用记录 |
| 6 | 沉淀完成是否列文件路径 evidence (N172 修复 B)? | ☐ | 回复中文件路径列表 |

**硬约束**:
- ✅ spec/plan 完成必测用时 (start_ts/end_ts/duration)
- ✅ 超基线必跑根因 6 项检查 + 沉淀优化
- ✅ AI 自决沉淀 (§3.8 + N172 修复 B, 不等用户提醒)
- ❌ NEVER spec/plan 完成后不测用时
- ❌ NEVER 等用户说"这个要沉淀"才开始沉淀
- ❌ NEVER 把"应该沉淀"当结束语修辞 (N172 修复 B)

**spec 规模基线**:
- 小 (typo/1-3 行/配置): < 5 min, 工具调用 < 10
- 中 (加 API/组件/修 bug): < 15 min, 工具调用 10-50
- 大 (跨模块/架构/新功能): < 60 min, 工具调用 50-200
- 沉淀 (L1-大 5 层分发): < 5 min, 工具调用 < 15

### ㉚ N174 TD 登记修复方案验证 Y/N 矩阵（L1-中 3 层分发）

> **触发条件**:
> - 登记新 TD 到 `docs/tech-debt/active.md`
> - wontfix 评估前
> - 单次批量 TD 处理 wontfix 率 > 30%

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | TD 登记时是否跑 grep 验证修复方案? | ☐ | `grep -r "<字段A>" backend/` |
| 2 | grep 结果是否写入"修复方案验证"字段? | ☐ | active.md TD 条目含字段 |
| 3 | grep 结果与修复方案矛盾时是否调整方案? | ☐ | TD 修复方案与 grep 结果一致 |
| 4 | wontfix 评估时是否先核查"修复方案验证"字段? | ☐ | 评估前先 Read active.md 该字段 |
| 5 | 单次批量 wontfix 率 > 30% 时是否跑根因分析? | ☐ | 跑 N174 根因分析 |

**硬约束**:
- ✅ TD 登记必填"修复方案验证"字段
- ✅ grep 结果与方案矛盾时立即调整方案
- ❌ NEVER 凭印象写"保留 X 删 Y" 不验证
- ❌ NEVER wontfix 率 > 30% 不跑根因分析

### ㉛ N175 subagent 并行结果落地检查 Y/N 矩阵（L1-中 3 层分发）

> **触发条件**:
> - 主会话用 subagent 并行处理多个 TD
> - subagent 返回结果后, 主会话 commit 前
> - subagent 失败/超时/exit≠0

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | 主会话是否记录每个 subagent 处理的 TD 列表? | ☐ | subagent 调用前记录 td_list |
| 2 | commit 前是否核查 subagent 数 vs active.md 更新数一致? | ☐ | `len(updates) == sum(td_lists)` |
| 3 | 结果丢失时是否重新读取 subagent 返回结果补更新? | ☐ | 重新 Task 查询或串行补 |
| 4 | active.md evidence 是否标注 "via subagent #N"? | ☐ | active.md 条目含标注 |
| 5 | subagent 失败时是否回退串行 (重试/接管/登记 TD)? | ☐ | 回退策略执行 |

**硬约束**:
- ✅ commit 前必跑"落地检查清单"
- ✅ subagent 失败必回退串行
- ❌ NEVER subagent 数 vs active.md 更新数不一致就 commit
- ❌ NEVER subagent 失败直接放弃任务 (N111 换方式继续原则)

### ㉝ N166 L3 持续评估+循环修复 Y/N 矩阵 (§3.7)

> **来源**: 用户反馈 "没任务就接着评估这个项目能评估的地方啊，评估完然后有问题就开始修复"
> **适用范围**: spec 全部 ✅ 后 / 任务完成后 / 无活跃任务时
> **终止条件 (spec-53 增强)**: 连续 2 轮无新增 [A]+[B] 类 / 所有 [A] 已修 + [B] 已登记并附修复方向 + 何时修 / 上下文预算告警 (≥ 15 轮) / 用户显式叫停 / **(spec-53 已接受复查) 已接受 [B]/[C] 类每 5 spec 复查一次, 防"已接受"永久化**

**L3 循环流程**:
```
L3-1 扫描可评估清单 (9 维度 — 用户反馈扩充):
  ① 文档层: tech-debt/active.md 🔧/🚧 + pending-roadmap.md Review Checklist + `docs/health/` 上次报告 ❌/⚠️ + `.trae/architecture/*-evaluation.md` "待优化" + specs/ 中 ⏳/🔄
  ② 代码层: ruff/mypy/tsc 预存错误、测试覆盖率、死代码、重复实现
  ③ 架构层: 跨平台抽象是否到位、模块边界、FK 合理性、双套并存反模式
  ④ 界面层: 前端页面功能是否完整实现、交互元素是否全部可点击、响应式布局、无障碍属性
  ⑤ 功能层: spec 中设计的功能是否全部落地、是否有"🔧代码存在"标记未升 ✅
  ⑥ 业务逻辑层: 状态机流转、边界条件、错误处理、并发安全
  ⑦ 数据层: 变量/属性命名是否准确、字段是否被使用、DB schema 是否合理、migration 是否一致
  ⑧ 多 app 层: 各 Django app 功能是否独立完整、app 间依赖是否合理、是否有死 app
  ⑨ 集成层: 前后端 API 契约一致性、WS 实际连通、Agent ↔ Backend 协议一致性
     ↓
L3-2 评估发现 → 分级:
  [A] 立即开 spec 修复 (P0/P1 + < 500 行)
  [B] 登记到 tech-debt/active.md (P2/P3 或 > 500 行)
  [C] 无法解决 (登记 wontfix.md)
     ↓
L3-3 [A] 类 → 开新 spec → 修复 → 回到 L3-1 继续扫描
     [B]/[C] 类 → 登记后继续扫描下一个评估点
     ↓
L3-5 实测验证 (用户反馈强制):
  启动 backend+frontend+agent, 浏览器实际点击页面交互元素
  验证 WS 实际连通 / UI 交互 / 端到端数据流 / Agent 实际响应
  Playwright E2E (主推) + browser-use (快速验证)
```

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | 循环模式触发条件已确认 (用户明确说"循环执行"/"任务接着做"/"评估一下"才进入 L3-1) | | 自检 |
| 2 | 已扫描 tech-debt/active.md 🔧/🚧 条目 | | `grep -n "🔧\|🚧" docs/tech-debt/active.md` |
| 3 | 已扫描 pending-roadmap.md Review Checklist | | `grep -n "⏳\|🔧\|🚧" docs/pending-roadmap.md` |
| 4 | 已扫描 monthly-health-check 上次报告 ❌/⚠️ 项 | | `ls docs/health/` + Read 最新 |
| 5 | 已扫描 architecture/*-evaluation.md "待优化" 项 | | `grep -rn "待优化\|TODO\|FIXME" .trae/architecture/` |
| 6 | 已扫描 specs/ 中 ⏳/🔄 未完成阶段 | | `grep -rn "⏳\|🔄" docs/specs/` |
| 7 | 已跑代码 lint 检查预存错误 | | `ruff check backend/ agent/ \| head -50` + `npx tsc --noEmit` |
| 8 | 已评估架构层 (跨平台/模块边界/FK/双套并存) | | 自检 |
| 9 | 已评估界面层 (页面功能/交互元素/响应式/无障碍) | | 自检 + grep "aria-label" frontend/src/ |
| 10 | 已评估功能层 (spec 设计功能落地/🔧→✅) | | `grep -rn "🔧" docs/completed-features.md` |
| 11 | 已评估业务逻辑层 (状态机/边界/错误/并发) | | 自检 |
| 12 | 已评估数据层 (命名/字段使用/schema/migration) | | 自检 |
| 13 | 已评估多 app 层 (app 独立性/依赖/死 app) | | `ls backend/` + 自检 |
| 14 | 已评估集成层 (API 契约/WS/Agent 协议) | | 自检 |
| 15 | [A] 类已开 spec 修复 (非直接改代码) | | 自检: spec 文件已创建 |
| 16 | [B] 类已登记到 tech-debt/active.md | | 自检: 含症状/根因/影响/修复方案/验证标准/何时修 |
| 17 | [C] 类已登记到 wontfix.md (含理由) | | 自检 |
| 18 | 循环到 L3-4 终止条件 (spec-53 增强: 连续 2 轮无 [A]+[B] / 满足其他终止条件 / 已接受 [B]/[C] 每 5 spec 复查) | | 自检 |
| 19 | L3-5 实测验证: 修改涉及 UI/WS/Agent 时启动浏览器点击测试; 纯后端/规则修改跑 pytest | | 自检 |
| 20 | 沉淀用户要求: 本轮对话工作模式要求已沉淀到 rules+handbook | | `git diff .trae/rules/project_rules.md` |
| 21 | (spec-49) 触发词分级识别正确? 强触发 (持续循环) vs 弱触发 (单 spec 后停) vs 默认 (停下) | | 自检: 触发词归类 |
| 22 | (spec-49) 连续 3 spec 完成后强制停下报告 (硬终止, 防方向跑偏)? | | 自检: spec 计数 |
| 23 | (spec-49) 弱触发模式下 1 spec 完成后必停下 (用户弱触发仅授权 1 个 spec)? | | 自检 |
| 24 | (spec-49) L3-1 频率归一: 循环模式下每 3 spec 一次全量扫描, 每 spec 跑轻量版? | | 自检: 全量扫描计数 |

**AI 必做**:
- ✅ **循环模式下** spec ✅ 后立即进入 L3-1 扫描; **非循环模式 (默认)** spec ✅ 后停下报告用户, 等指令
- ✅ **[A] 类必须开 spec**: 用户要求 "所有要修的弄个 spec 再开始", 禁止直接改代码
- ✅ **循环到 L3-4 终止条件**: 不评估一轮就停
- ✅ **L3-5 实测验证**: 修改涉及 UI/WS/Agent 时打开 GAF 实际点击测试; 纯后端/规则修改跑 pytest
- ✅ **沉淀用户要求**: 本轮对话中用户提出的工作模式要求, 当轮任务结束前沉淀到 rules + handbook
- ❌ **禁止** 非循环模式下主动进入 L3-1 / 评估 [A] 类不开 spec / 评估一轮就停 / 只跑 pytest 就标 ✅ / 用户要求不沉淀

### ㉙ 前端开发工作流 Y/N 矩阵 (§4.7)

> **适用范围**: 新页面开发、页面重构、组件库扩展、全局样式变更
> **流程**: 规范查阅阶段（实现前必读 `docs/standards/frontend-conventions.md`）→ 合规自检阶段（实现完成后对照检查清单逐项验证）

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | 实现前已读 `docs/standards/frontend-conventions.md` | | 自检 |
| 2 | 使用 PageWrapper 统一页面容器 | | grep "PageWrapper" frontend/src/ |
| 3 | 使用 gaf-toolbar 分组工具栏 + gaf-* utility classes | | grep "gaf-toolbar\|gaf-" frontend/src/ |
| 4 | 响应式布局（flex-wrap 自动换行） | | 自检 |
| 5 | 无障碍属性（aria-label） | | grep "aria-label" frontend/src/ |
| 6 | 表单规范（name + autocomplete） | | grep "autocomplete" frontend/src/ |
| 7 | 实现完成后对照检查清单逐项验证，修复 P0/P1 问题后标记完成 | | 自检 |

### ㉚ 技术债务登记 + Debug auto-heal Y/N 矩阵 (§4.8)

> **来源**: 用户反馈 — "做项目要考虑全面的，不要遗留技术债务"

**技术债务登记 Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | 范围外问题已登记到 `docs/tech-debt/active.md` TD-NNN 条目 | | grep "TD-" docs/tech-debt/active.md |
| 2 | TD 条目必填字段完整（症状/根因/影响/修复方案/验证标准/何时修/登记时间） | | 自检 |
| 3 | 每轮 plan 实现完成后跑 Review Checklist（扫 🔧/🚧 条目，挑 1-2 个推进） | | 自检 |
| 4 | 修复后状态改为 ✅ FIXED 并附 commit hash + evidence | | grep "✅ FIXED" docs/tech-debt/ |
| 5 | "修不了"的 debt 未留在 🔧 状态超过 3 轮 | | 自检 |

**Debug auto-heal Y/N 检查表** (debug_mode=True 且节点失败时):
| # | 检查项 | Y/N |
|:-:|--------|:---:|
| 1 | 调用 `screenshot_diagnostic.run_diagnostic()` 诊断 | |
| 2 | 尝试所有可行方案（切换截图方法/输入模式/已知 workaround） | |
| 3 | 穷尽后才通知用户（带完整诊断报告 + 尝试方法列表 + confidence/error + 推荐方向） | |
| 4 | 未第一次失败就通知用户 | |

**禁止行为**:
- ❌ 跳过 tech-debt 检查直接进入下一轮 plan
- ❌ 把"修不了"的 debt 留在 🔧 状态超过 3 轮
- ❌ 登记新 debt 时不写"何时修"字段
- ❌ 第一次失败就通知用户（必须先穷尽自动修复尝试）

### ㉛ 阶段验收 + 全量回归 Y/N 矩阵 (§4.9)

> **来源**: 用户反馈 — "spec后者plan做完一个大阶段的任务就得检查下这一阶段是否完成再下一个阶段，全部开发任务完成时，还得先全部检查这些阶段的，然后才可以最终测试"

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | 大阶段所有子任务完成后跑阶段验收（按 spec §X.Y "验收标准"段） | | `grep "<spec-id>.*阶段.*验收" docs/completed-features.md` |
| 2 | 阶段验收逐项 Glob + Grep + pytest 验证（N128 3 步验证） | | `pytest --tb=short -q` exit 0 + Glob 非空 + Grep 非空 |
| 3 | 阶段验收 evidence 写入 `completed-features.md`（✅/🔧 + 测试通过数 + 关键文件路径） | | grep "✅" docs/completed-features.md |
| 4 | 验收失败 → 修复 → 重跑验收清单（不进入下一阶段） | | 自检 (行为不可外部留痕) |
| 5 | 所有阶段 ✅ 后跑全量回归（按阶段顺序逐个复查） | | `grep "全量回归" docs/completed-features.md` |
| 6 | 全量回归通过后才进入最终测试 | | `grep "最终测试.*✅" docs/completed-features.md` |

**与 N134 反思的关系**:
- N134 反思 = 每 commit 后跑（4 问 + A/B/C 分类）
- §4.9 阶段验收 = 每阶段完成后跑（按 spec 验收标准）
- §4.9 全量回归 = 所有阶段完成后跑（按阶段顺序复查）
- 三者层级不同，不可互相替代

### ㉜ Spec 分阶段与跨会话续接 Y/N 矩阵 (§4.10)

> **来源**: 用户反馈 — "考虑到对话的上下文限制，压缩限制来划分，spec执行完每个阶段，新的对话能否继续"
> **触发条件**: 复杂修复（> 1500 行 diff / 跨模块 / 多缺陷 / AI 架构缺陷修复等）

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | 复杂修复拆分为多个 spec 阶段（单阶段 diff < 1500 行） | | git diff --stat |
| 2 | spec 文件首部含"阶段状态表"（阶段编号 + 状态 + 完成时间 + commit hash + 验收 evidence） | | grep "阶段状态表" docs/specs/ |
| 3 | 单文件多阶段（一个 .md 文件含所有阶段，不拆分为多个文件） | | ls docs/specs/active/*.md |
| 4 | spec 文件路径 `docs/specs/active/YYYY-MM-DD-<topic>.md` | | ls docs/specs/active/ |
| 5 | 每阶段完成后立即更新 3 处（spec 状态表 + completed-features.md + pending-roadmap.md） | | `git diff --name-only \| grep -E "specs/\|completed-features\|pending-roadmap"` 输出 ≥ 3 |
| 6 | 阶段间状态标记诚实（⏳/🔄/✅ 与实际代码状态一致，N126） | | 自检 |
| 7 | 对话上下文预算管理（N160）：pytest 用 -q；E2E 调试 ≤ 2 轮；大文件用 offset+limit；≥ 15 轮提示新开对话 | | 自检 |

**新对话续接流程**:
1. 用户说"继续 spec `docs/specs/active/YYYY-MM-DD-xxx.md`"
2. AI Read spec 文件首部状态表
3. 找到第一个 ⏳ 或 🔄 阶段
4. Read 该阶段详细内容（spec §N 段）
5. 从该阶段开始执行
6. 完成后更新状态表 + commit + 推进下一阶段

**禁止行为**:
- ❌ 禁止单 spec 超过 1500 行 diff（上下文溢出风险 + 压缩丢失关键信息）
- ❌ 禁止 spec 文件拆分为多个文件（增加续接成本 + 状态分散）
- ❌ 禁止阶段完成后不更新状态表（续接时 AI 无法判断进度）
- ❌ 禁止 E2E 调试逐次试错（每次只改 1 个 selector 就重跑，吃满上下文）— N160

> **交叉引用**: N160/N162 工具使用纪律 (上下文预算管理) 详见 [_workflow-reflection.md](_workflow-reflection.md) §㊲
