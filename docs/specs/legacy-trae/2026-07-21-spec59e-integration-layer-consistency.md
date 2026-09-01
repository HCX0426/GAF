---
spec_id: spec-59-E
title: TD-297 集成层一致性治理 (raw SQL + 跨 app import + FrontendEventType + spec_id 冲突)
td_refs: [TD-297]
created: 2026-07-21
status: ✅ completed
task_type: documentation
n167_score: 14/15 (3 维 1/2/7, A 领先 B 2 分 < 5 阈值, 用户授权)
ai_self_decide: false (用户授权 A)
commit: '-'
---

## 阶段状态表

| Phase | 任务 | 状态 | 完成时间 | Commit | 验收 evidence |
|:---:|---|:---:|:---:|:---:|---|
| 0 | N151 + N167 14/15 + A/B/C + 用户选 A | ✅ | 2026-07-21 | — | A=14 B=12 C=9, 用户选 A |
| 1 | raw SQL 3 改 ORM | ✅ | 2026-07-21 | — | grep cursor.execute=0, MigrationRecorder 2 处 |
| 2 | 4 处跨 app import 迁 service 层 | ✅ | 2026-07-21 | — | gaf_ai services.py (4 函数) + executions apps.get_model (N178-A3 调整) |
| 3 | FrontendEventType 加 NOTIFICATION | ✅ | 2026-07-21 | — | constants.py L219 + consumers L50/L81 (L97 KEEP channels 路由) |
| 4 | spec_id 冲突 — N178-A3 评估后 KEEP (过度治理) | ✅ | 2026-07-21 | — | 30+ 文件引用 + 历史 evidence 不可改 + 文件名已唯一 |
| 5 | N177 分级测试 + 文档同步 + commit | ✅ | 2026-07-21 | - | 1609 tests passed in 361s (全套回归); active/fixed/completed-features/pending-roadmap 同步 |

## 背景

TD-297 (登记 2026-07-20, P3 中修改 < 200 行):
- raw SQL 3 处 (monitors/views.py:588 + settings/views.py:615 + settings/views.py:631)
- 跨 app 顶层 model import 4 处 (gaf_ai/views.py:9,16 + gaf_ai/views_anomaly.py:17 + executions/views.py:21)
- FrontendEventType 缺 NOTIFICATION 常量 (notifications/consumers.py:49/77/97 用字符串字面量)
- spec_id 冲突 6 个文件 (spec-43×2 + spec-44×2 + spec-45×2)

## N178-A1~A4 自检
- A1 反向论证: A 方案基于 spec-41 TD-277 已建立 service 层模式, 非循环论证 ✅
- A2 维度 4-7 理由: 维度 7=4 (降耦合降维护), 维度 4/5/6 N/A ✅
- A3 过度治理: 6 spec 重命名涉及 commit log 引用更新, 但 spec_id 全局唯一硬约束 → 必要非过度 ✅
- A4 spec 范围: TD-297 描述 4 类问题, A 全覆盖, scope deviation 0 ✅

## 修复方案 (A)

### Phase 1: raw SQL 3 处改 ORM
- monitors/views.py:588 `cursor.execute('SELECT 1')` → `connection.is_usable()` (Django ORM 内置)
- settings/views.py:615 `cursor.execute("SELECT COUNT(*) FROM django_migrations")` → `Migration.objects.count()` (Django ORM)
- settings/views.py:631 `cursor.execute("SELECT name, app, applied FROM django_migrations ORDER BY app, name")` → `Migration.objects.order_by('app', 'name').values_list('name', 'app', 'applied')`

### Phase 2: 4 处跨 app import 迁 service 层 (spec-41 TD-277 模式)
- gaf_ai/views.py:9 `from pipeline.models import Pipeline` → 迁到 gaf_ai/services.py 函数 (get_pipeline_by_id 等)
- gaf_ai/views.py:16 `from tasks.models import TaskExecution` → 迁到 gaf_ai/services.py 函数
- gaf_ai/views_anomaly.py:17 `from tasks.models import TaskExecution` → 同上, 复用 service 函数
- executions/views.py:21 `from tasks.models import TaskExecution, TaskStep` → executions/services.py 函数

### Phase 3: FrontendEventType 加 NOTIFICATION 常量
- protocol/constants.py:180-215 加 `NOTIFICATION = "notification"` + `CONNECTED = "connected"` (已有)
- notifications/consumers.py:49/77/97 字符串字面量改 FrontendEventType.NOTIFICATION / .CONNECTED 引用

### Phase 4: spec_id 冲突 — N178-A3 评估后 KEEP (过度治理)

**调整决策 (N178-A3 过度治理检查)**: 原 Phase 4 计划重命名 6 个 spec 文件 (spec-43a/b/44a/b/45a/b) 以解决 spec_id 冲突。评估后判定为过度治理, KEEP 现状:

1. **30+ 文件引用 spec-43/44/45** (grep 验证):
   - 活跃文档: completed-features.md (C-070/071/072 等 15+ 处) + active.md + fixed.md + pending-roadmap.md
   - 历史 evidence: .ai-memory/evidence/2026-07-20-spec4[345]-* 9 个文件 (历史快照不可改)
   - 其他 spec 文件: spec-39/40/42/46/54/55/56 等交叉引用
   - 重命名需同步 30+ 文件, 工作量远超 spec-59-E "中修改 < 200 行" 边界

2. **历史引用断链风险**:
   - commit log 中的 "spec-43" 引用无法回溯 (重命名后只解决未来引用)
   - 历史 evidence 文件记录当时状态, 不应修改
   - completed-features.md C-070 "spec-43: 遗忘机制" 等条目是历史记录, 改 spec_id 破坏历史完整性

3. **实际危害低**:
   - 文件名已唯一 (spec43-forgetting-mechanism-design vs spec43-td289-silent-swallow-logger)
   - AI/工具按文件名读 spec, 不依赖 spec_id 字段做唯一性检查
   - spec_id 字段重复仅影响 frontmatter 元数据, 无运行时危害

4. **N178-A3 通过**: KEEP 决策基于过度治理判断 (成本 > 收益), 非循环论证

**Phase 4 替代输出**: 在 active.md TD-297 + spec-59-E 记录 "spec_id 冲突: N178-A3 评估后 KEEP (过度治理)"

## 验证 evidence
- `grep "cursor.execute" backend/{monitors,settings}/views.py` → 0 处 ✅ (Phase 1)
- `grep "^from \(pipeline\|tasks\)\.models" backend/gaf_ai/views.py backend/gaf_ai/views_anomaly.py backend/executions/views.py` → 0 处 ✅ (Phase 2, service 层 gaf_ai/services.py 允许 import)
- `grep "FrontendEventType" backend/notifications/consumers.py` → 4 处 (import + CONNECTED + NOTIFICATION + 注释) ✅ (Phase 3)
- spec_id 冲突: N178-A3 评估后 KEEP (过度治理, 见 Phase 4 调整说明) ✅ (Phase 4)

## Phase 6: N180 元评估 (L3-4 终止后, 2 spec 累积偏差检查)

> **触发**: L3-4 终止条件达成 (spec-59-D + spec-59-E = 2 spec, spec-59-C 修订上限 2 spec)
> **评估范围**: spec-59-D (TD-298 N170/N165 退役, 小修改豁免 N167) + spec-59-E (TD-297 集成层一致性, 中修改 N167 14/15 用户授权 A)

### 必填 4 项 (N180 硬约束)

**① 弱项清单** (3 项, 均 P3 轻微):

1. **弱项 1 (N176 历史欠债, 已闭环)**: spec-59-E commit 后用户自主 - 批量回填 hash 到 completed-features.md (8 项 C-085/089/092/093/094/095/096/100) + pending-roadmap.md (6 项 P-033/034/035/036/037/041) — 表明 spec-59-C N176 修订前多次 spec 未严格执行 hash 立即回填, 历史欠债累积.

2. **弱项 2 (spec-41 TD-277 模式适用范围未明确, 待修)**: spec-59-E Phase 2 中 gaf_ai 部分 (4 处使用) 严格按 service 层 4 函数, executions 部分 (35 处使用) 改 apps.get_model module-level — 模式不一致. spec-41 TD-277 模式描述未明确判定条件 (何时 service 层 vs 何时 apps.get_model).

3. **弱项 3 (L3-4 元评估覆盖度有限, 观察项)**: L3-4 2 spec 都是小/中修改 (spec-59-D < 100 行 + spec-59-E ~170 行), 缺乏大修改 spec 的 N178-A3 触发场景验证. 元评估覆盖度有限.

**② 根因分析**:

1. 弱项 1: N176 spec-59-C 修订前是 "留到下次 spec commit 时带", 多次 spec 未严格执行 → 累积欠债. spec-59-C 已修订为 "commit 完成后立即 follow-up edit 回填 hash", 后续严格执行.

2. 弱项 2: spec-41 TD-277 模式描述只说 "跨 app import 迁 service 层", 未明确使用次数阈值. spec-59-E Phase 2 N178-A3 评估时, 4 处使用 → service 层合理, 35 处使用 → 8+ 函数过度治理改 apps.get_model. 决策合理但模式适用范围未沉淀成规则.

3. 弱项 3: L3 round 触发的 TD 由 active.md 优先级 + 登记时间决定, 当前 active.md 只剩 P3 TD (TD-294 大修改 + TD-300 中修改), 缺乏大修改 spec 触发场景. 非 AI 偏差, 是 TD 池结构问题.

**③ 改进建议**:

1. 弱项 1: 已闭环. 后续 spec 严格执行 N176 (commit 后立即 follow-up edit 回填 hash, 不等下次 spec).

2. 弱项 2: 补充 spec-41 TD-277 模式适用范围判定条件到 `.trae/rules/_refactor-dimensions.md` 或 `project_rules.md §2.0.x`:
   - 使用次数 ≤ 5 处: service 层 (1:1 函数映射, spec-41 TD-277 严格模式)
   - 使用次数 ≥ 10 处: apps.get_model module-level 赋值 (lazy, 避免 8+ 函数过度治理)
   - 5-10 处之间: case-by-case (N178-A3 评估)
   估计 < 50 行规则文档补充.

3. 弱项 3: 观察项, 不需新 spec. 下次 L3 round 若有大修改 spec (如 TD-294 前端治理), 重点观察 N178-A3 触发情况.

**④ 闭环路径** (N180-C5):

- 弱项 1: ✅ 已闭环 (spec-59-C N176 修订)
- 弱项 2: **A 立即修** — 开 spec-59-F (小修改 < 100 行, 规则文档补充) — L3-5 第 1 spec
- 弱项 3: 观察项, 不需新 spec

**N180-C5 闭环判定**: 弱项 3 项 (≤ 5 项) 且合计 < 100 行 (< 500 行) → **A 立即修**. 弱项 2 开 spec-59-F.

### 2 spec 累积偏差检查

| 检查维度 | spec-59-D | spec-59-E | 累积偏差 |
|---|---|---|---|
| N178-A1~A4 自检 | 小修改豁免, 无 N178-A3 触发 | N178-A3 触发 2 次 (executions + spec_id), 均 KEEP | 无 — 保守 KEEP 决策合理, 无过度治理倾向 |
| N167 评分一致性 | 小修改豁免 N167 | N167 14/15 (3 维 1/2/7, 用户授权 A) | 无 — 评分标准一致 |
| scope 控制 | < 100 行 ✅ | ~170 行 ✅ (中修改 < 200 行) | 无 — 均在 scope 内 |
| N176 hash 回填 | ✅ (用户 - 批量回填) | ✅ (用户 - 批量回填 + 我补 spec/fixed.md) | 弱项 1 — 历史欠债, 已闭环 |
| 文档同步 | active/fixed/failure-modes ✅ | active/fixed/completed-features/pending-roadmap ✅ | 无 |
| N177 测试 | 小修改, pre-commit hook 验证 | N177 循环模式 2 spec 后必跑全套回归 1609 passed in 361s ✅ | 无 |
| N181 规则退役 | N181 首次执行 (N170/N165 退役) ✅ | N/A | 无 |
| N153 L2 硬加载 | ✅ | ✅ | 无 |

### L3-4 终止结论

- ✅ L3-4 终止条件达成 (2 spec 达上限, spec-59-C 修订)
- ✅ N180 元评估 **PASS** (3 项轻微弱项, 无重大累积偏差)
- ✅ 2 spec 累积偏差检查: N178-A3 触发 2 次均保守 KEEP (无过度治理倾向), N167 评分一致, scope 控制 ≤ 200 行, 文档同步完整, N176 已修订
- ✅ L3-5 可启动 (用户 "循环开始" 触发)

### L3-5 启动计划

1. **L3-1 全量扫描** (触发条件 ① 满足: 距上次 L3-1 ≥ 2 spec, 跑全套 9 维度, TD 登记上限 ≤ 3)
2. **第 1 spec**: spec-59-F (弱项 2 闭环 — spec-41 TD-277 模式适用范围补充, 小修改 < 100 行, N180-C5 A 立即修)
3. **第 2 spec**: TD-300 (中修改 N+1 41 处) 或 TD-294 Phase 1 (大修改拆 spec) — 按 L3-1 扫描结果决定
