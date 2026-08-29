---
summary: 活跃技术债务清单 — 🔧 待修/待办/待决 和 🚧 进行中 条目 (完整详情)
applies_to: [project]
last_updated: "2026-08-29 (TD-415 登记: log_rotation 弹窗; TD-416~419 登记: 日志体系评估; TD-420/421 登记: 通知链路)"
---

# Active Tech Debts (待修 / 进行中)

> Only active tech debts listed here. Closed/WONTFIX entries moved to `fixed.md` or `wontfix.md`.
>
> 本文件只包含真正活跃的技术债务（🔧 待修/待办/待决 和 🚧 进行中）。
> 已关闭条目（✅ FIXED / ❌ WONTFIX / ❌ INVALIDATED / ❌ EVALUATED）已迁移到 `fixed.md` 或 `wontfix.md`。
>
> **状态**: ✅ 全部闭环（TD-412/413/414 已于 2026-08-28 迁出 fixed.md，active 为空）

## TD 处理顺序 (2026-07-18 spec-26 强化)

> **来源**: 用户反馈 2026-07-18 — "要是有技术债务，为啥会延后，延后也是指在做完上一个类别接着做，而不是等我的指令"
> **硬约束**: 见 `project_rules.md §4.8` — "延后" = 做完上一个 spec/类别后立即接着做, **不是等用户指令**

**AI 自动接修规则**:
1. 当前 spec 全部 ✅ 后, AI **主动**按优先级 + 登记时间接修下一个 TD, 不等用户指令
2. 优先级排序: P1 > P2 > P3; 同优先级按登记时间 (先登记先修)
3. 批量合并: 若剩余 TD 均 P3 且合计 < 500 行, 合并 1 个 spec 批量处理
4. 单独 spec: 若单个 TD > 500 行或跨模块, 单独开 spec

**"何时修" 字段语义**:
- ✅ 合法写法: "spec-XX 完成后立即接修" / "下一 spec" / "L3 Round N 后接修" (明确触发点)
- ❌ 禁止写法: "后续 Phase" / "下次重构" / "待定" / "看情况" (模糊延后 = 等用户指令)

**完整待修 TD 清单见 tech-debt/README.md 总览表**

---

## TD-XXX: <title> (🔧 待修)

- **状态**: 🔧 待修
- **优先级**: P1/P2/P3
- **登记时间**: YYYY-MM-DD
- **来源**: <where this TD was discovered>
- **症状**: <observable symptom>
- **根因**: <root cause>
- **影响**: <impact on functionality/performance/etc>
- **修复方案**: <proposed fix>
- **验证标准**: <how to verify the fix>
- **何时修**: <when to fix>
-->

---

> 2026-08-26 迁移记录：
> - TD-395/396/397/398/399 → fixed（spec-2026-08-26 闭环，commit - 等；TD-396 由 2026-08-26 连续 10 次执行全 success 终确）
> - TD-400 → fixed（loop rotation 实现 + 关闭，commit - / -）
> - TD-401 → fixed（18 vitest 用例，commit -）
> - TD-402 → fixed（链执行器可靠性 5 项，commit -）
> - TD-403 → fixed（伪失败确认：tasks 全量 215 passed --create-db 干净库，判定为并发 create-db 重建窗口假象）
> - TD-404 → fixed（前端 tsc 归零：NodePropertyPanel TS1117 重复键 + test TS6133 未用导入）
> - TD-405 → fixed（doc_health P1=0：docs-index.md 补 last_manual_edit）
> **Note**: TD 状态迁移 (✅ FIXED → fixed-tech-debt.md) 按 §4.5 执行。
> - TD-406 → fixed（策略页恢复流程摘要改为随配置动态拼接，commit -）
> - TD-407 → fixed（TaskExecutionSerializer 增 task_name/agent_hostname + 执行列表渲染名称，commit -）
> - TD-408 → fixed（backend ruff 79 条归零，commit -）
> - TD-409 → fixed（frontend eslint 165 条归零：compiler 规则降级 warn + 31 真实问题修复，commit -）
> - TD-410 → fixed（agent ruff 276 条归零，commit -）
> - TD-411 → fixed（frontend prettier 全仓 272 文件格式收敛，commit -）
> - TD-412 → fixed（N105 出清 + N201 行修复，check-cap 35 ≤ 35，2026-08-28）
> - TD-414 → fixed（N209/N210/N211 补 yn-matrices 条目，doc_health 0，2026-08-28）
> - TD-413 → fixed（SKILL.md 27.6KB→18.3KB 瘦身，9 处冗余外迁/压缩，2026-08-28）

---

## TD-415: DateRotatingFileHandler 跨天轮转偶发 _stream=None (🔧)

- **状态**: 🔧 (登记 2026-08-29, 本次 spec 范围外检出)
- **优先级**: P3
- **登记时间**: 2026-08-29
- **来源**: spec 2026-08-29-services-management-monitor 实测 daemon status 时发现
- **症状**: `gaf_daemon.py status --json` / daemon 运行时 `log_rotation.py:139 emit → AttributeError: 'NoneType' object has no attribute 'write'`
  反复打印 Logging error; stdout 正常但文件 handler 失效 (跨天轮转后 `_stream` 为 None 未重建)
- **根因**: `DateRotatingFileHandler._rotate_if_needed` 在日期变化时 close 旧流后, 若 `_open_today()` 之前某异常路径
  或并发 (多进程同 handler) 导致 `_stream` 保持 None; 跨午夜后首条日志 emit 即崩 (handleError 吞掉, 日志持续丢失)
- **影响**: daemon/agent 跨天首条日志丢失 + 每次 status 调用刷 Logging error traceback; 文件句柄泄漏风险
- **修复方案**: `emit` 前对 None 自愈: `if self._stream is None: self._open_today()`; 并用 `single-file lock` 防止多进程并发写
- **验证标准**: ① 设置系统日期跨天 (或 mock datetime) 触发 rotate; ② 首条 emit 不再 AttributeError; ③ status/daemon 连续 3 次调用无 Logging error; ④ 当天日志文件持续增长且无 .gz 缺失
- **何时修**: 下一轮 L3 循环 (agent 日志可靠性, 涉及 agent+scripts 两处 import 同一 handler)
- **三维根因评估**: 代码 (emit 无 None 守卫) + 工作流 (跨天场景长期未测) + 规则 (无跨天轮转测试用例)
- **修复方案验证**: ✅ grep `log_rotation.py` emit/None/rotate 三处确认缺口; 复现命令 `python scripts/gaf_daemon.py status --json` → Logging error (2026-08-29 实测复现)

---

## TD-416: 消息帧日志 MessageFrameLog 无生产写入点，日志中心 tab 恒空 (🔧)

- **状态**: 🔧 (登记 2026-08-29, 日志体系 meta_audit 检出)
- **优先级**: P1
- **登记时间**: 2026-08-29
- **来源**: 日志体系评估 (2026-08-29) — `MessageFrameLog` 表 total=0
- **症状**: 日志中心"消息帧日志"tab 恒空; DB 实证 `protocol.models.MessageFrameLog` total=0 且 `060 /logs/timeline/` 无 MessageFrameLog 条目
- **根因**: `backend/protocol/views.py` 只有查询 ViewSet, **全仓无任何 `MessageFrameLog.objects.create` 生产写入点** (仅测试引用) — 协议层帧记录从未实现或实现被删
- **影响**: agent↔backend 协议帧不可回溯 (N216 僵尸连接排查等需帧日志); 日志中心 8 tab 中 2 个恒空
- **修复方案**: protocol consumer/handler (AgentConsumer 收发帧路径) 补 `MessageFrameLog` 记录 (开关默认开; 复用 trace_id; 方向 inbound/outbound; payload 截断保护)
- **验证标准**: ① agent 连接后发 1 帧 → 表新增 1 条; ② 日志中心消息帧 tab 可查; ③ timeline 出现 MessageFrameLog ref_type
- **何时修**: 下一轮日志体系复盘 (与 TD-417 同批)
- **三维根因评估**: 代码 (记录逻辑缺失) + 工作流 (UI 先于数据源落地) + 规则 (日志中心 tab 无"数据源为空"校验)
- **修复方案验证**: ✅ grep `MessageFrameLog.objects` 全仓仅 views.py 查询 + tests; DB 查询 total=0 (2026-08-29 实证)

---

## TD-417: 应用日志数据源断层 — LogEntry 停写，/logs/ 恒空 + timeline 缺应用日志 (🔧)

- **状态**: 🔧 (登记 2026-08-29, 日志体系 meta_audit 检出)
- **优先级**: P1
- **登记时间**: 2026-08-29
- **来源**: 日志体系评估 (2026-08-29) — `/api/v2/logs/` 返回 0 条
- **症状**: 日志中心"应用日志"tab 恒空 (刷新即无数据); "统一时间线"UNION 6 类中 LogEntry 分区冻结 (0 条); 仅 WS 实时推送 (id=None 不持久化)
- **根因**: spec §2.2 (2026-07-28 N194 归一化) 把 DatabaseLogHandler → FileLogHandler (写文件, LogEntry 表改只读), 但前端 `/api/v2/logs/` 查询端点 + timeline UNION 未同步收口 → UI 层仍读空表
- **影响**: 用户感知"应用日志没了"; AI 无法按 LogEntry 追溯应用日志 (需改查文件)
- **修复方案**: 二选一 — (a) 前端应用日志 tab 数据源改为文件级 API (新端点读 `debug/YYYYMMDD/backend/system/*/django.log`) + timeline 增加文件日志 ref_type; (b) 恢复 LogEntry 写 DB (仅 ERROR+ 落库控制量级); 推荐 (a) 与文件层归一化一致
- **验证标准**: ① 应用日志 tab 显示最近文件日志行; ② timeline 含应用日志近期条目; ③ 后端产生一条 ERROR → tab/时间线出现
- **何时修**: 下一轮日志体系复盘 (与 TD-416 同批)
- **三维根因评估**: 代码 (前端未收口) + 工作流 (归一化只改写入侧没改读侧) + 规则 (日志中心 tab 缺"数据源异常"检查)
- **修复方案验证**: ✅ DB 查询 LogEntry total=0 (近 24h 新增 0); `/api/v2/logs/` 实测返回 0 条 (2026-08-29)

---

## TD-418: 审计日志双入口重复 — /system/audit-log 与 /ops/logs 审计 tab 同源 (🔧)

- **状态**: 🔧 (登记 2026-08-29, 日志体系 meta_audit 检出)
- **优先级**: P3
- **登记时间**: 2026-08-29
- **来源**: 日志体系评估 (2026-08-29)
- **症状**: 系统页签"审计日志"页与日志中心"审计日志"tab 调用同一 API (`/accounts/audit-logs/`), 功能完全重复 (AuditLog 291 条正常写入)
- **根因**: I-26 前端归一化时审计日志从 /ops 移入系统分组 (管理入口), 但日志中心聚合 tab 未删除
- **影响**: 两个入口观感重复; 维护成本双份; 新功能 (审计过滤/导出) 需同步两处
- **修复方案**: 收敛为单一入口 — 日志中心审计 tab 移除 (审计属系统管理功能, 保留 /system/audit-log + 统一时间线聚合即可); 或系统页改为对日志中心 tab 的重定向
- **验证标准**: ① 审计日志只在一个菜单导航可达 (或另一处明确跳转); ② 页面跳转无 404; ③ 统一时间线仍含 AuditLog
- **何时修**: 前端页面收敛批次
- **三维根因评估**: 代码 (两页面同数据源) + 工作流 (归一化未收敛重复入口) + 规则 (菜单 page 去重检查缺失)
- **修复方案验证**: ✅ grep 确认 AuditLogPage.tsx 与 SpecialtyLogTabs.tsx 均 import fetchAuditLogs → /accounts/audit-logs/ (2026-08-29)

---

## TD-419: 服务管理页 e2e 缺失 + 服务终端日志未入统一查看入口 (🔧)

- **状态**: 🔧 (登记 2026-08-29, 日志体系 meta_audit 检出)
- **优先级**: P3
- **登记时间**: 2026-08-29
- **来源**: 日志体系评估 (2026-08-29)
- **症状**: (1) 新功能"服务管理页" (/system/services) 无 Playwright e2e 用例 (仅浏览器手动实测); (2) 服务终端日志 (debug/system/services/*.log, 文件层) 与 DB 应用日志两套体系并存, 无统一入口/文档边界说明
- **根因**: (1) spec 2026-08-29-services-management-monitor P4 未列 e2e; (2) 文件层 (进程日志) 与 DB 层 (应用事件) 分属两类视图, 尚无 README/文档界定
- **影响**: (1) 页面回归无自动化保障; (2) 用户需在两处 (运维/日志中心 + 系统/服务管理) 分别查日志, 认知成本
- **修复方案**: (1) e2e 补 /system/services 用例 (卡片渲染+日志 Drawer+过滤切换); (2) docs/health/procedure.md 或 overview 增"日志体系分界"段: DB 层=业务事件审计, 文件层=进程终端/执行日志, 服务管理=健康+终端
- **验证标准**: ① e2e 用例落地并全过; ② 文档明确两套体系边界与协同方式
- **何时修**: 下轮 E2E 补全批次 (与 TD-416/417 可同批文档化)
- **三维根因评估**: 代码 (e2e 未覆盖新页) + 工作流 (spec 未强制新页 e2e) + 规则 (新前端页必带 e2e 的清单项缺失)
- **修复方案验证**: ✅ glob 确认 frontend/e2e 无 services 相关 spec; 服务终端日志路径 grep 确认无统一入口 (2026-08-29)

---

## TD-420: MonitorRule 模型被游戏 UI 规则占用, "监控/告警规则"概念空缺 (🔧)

- **状态**: 🔧 (登记 2026-08-29, 通知中心巡检)
- **优先级**: P2
- **登记时间**: 2026-08-29
- **来源**: 通知中心巡检 (2026-08-29) — MonitorRule 4 条全为 `story_skip`/`popup_handler` (剧情跳过/弹窗点击, template→action), 属 agent 游戏 UI 处理规则
- **症状**: 通知中心升级链路的"监控规则"名不副实 — MonitorRule 表存储的并非告警规则; 真正 MonitorEvent 输入来自 monitors/bus.py 事件总线 (OCR mismatch 等), 与 MonitorRule 无关联
- **根因**: MonitorRule 模型被游戏规则借用 (2026 前历史设计), 未拆分; 导致用户/开发者误以为"配置了监控规则"
- **影响**: 监控告警概念缺失; 通知中心上游依赖隐式打点 (bus), 规则配置无法驱动告警
- **修复方案**: 方案 A — agent 游戏 UI 规则迁移到独立模型 (如 tasks/或 resources), MonitorRule 恢复纯监控语义; 方案 B — MonitorRule 增加 `rule_kind` 字段区分 monitor/game_ui, 展示过滤; 推荐 A (长期)
- **验证标准**: ① MonitorRule 只含监控语义规则; ② 游戏规则悬停到目标模型; ③ 文档 (features-overview monitors 段) 同步
- **何时修**: 架构演进批次 (涉及模型迁移, 需规划)
- **三维根因评估**: 代码 (模型复用未隔离) + 工作流 (无监控规则创建入口) + 规则 (模型语义约束缺失)
- **修复方案验证**: ✅ DB 查询 MonitorRule 4 条 rule_definition 全部为 game template→action; grep 无"创建监控规则"UI (2026-08-29)

---

## TD-421: 通知中心输入侧缺口 — dev 环境 MonitorEvent 几乎无新事件, 升级链路空转 (🔧)

- **状态**: 🔧 (登记 2026-08-29, 通知中心巡检)
- **优先级**: P2
- **登记时间**: 2026-08-29
- **来源**: 通知中心巡检 (2026-08-29)
- **症状**: 通知中心 20h+ 无新通知; MonitorEvent 仅 3 条 (08-28 e2e 遗留, P0×2+P2×1); 手动运行 escalate_unhandled_alerts 正常 (0 候选 no-op)
- **根因**: 通知链路 (bus→MonitorEvent→escalate(5min)→Notification) 引擎全正常, 但**上游打点缺失**: agent/业务侧几乎不向 EventBus 发布监控事件 (OCR mismatch 等); dev 场景无真实触发源
- **影响**: 通知中心形同"空壳" (链路可用但无输入); 用户无法判断"是没告警还是告警线路断了"
- **修复方案**: ① 补齐 agent 事件发布 (badge: OCR/模板匹配/执行失败向 EventBus 打点, 开关默认开); ② 通知中心加"链路健康"展示 (升级任务最近运行时间/事件计数趋势, 空态说明); ③ README 说明 eager/APScheduler 下升级已注册运行
- **验证标准**: ① dev 环境触发一次 OCR 失败 → MonitorEvent 新增 + escalate 后 Notification 出现; ② 通知中心空态可区分"无告警"与"链路异常"
- **何时修**: 下轮监控/通知功能迭代
- **三维根因评估**: 代码 (上游打点缺失) + 工作流 (无监控验收场景) + 规则 (无"通知链路健康"检查项)
- **修复方案验证**: ✅ DB 查询 MonitorEvent 仅 3 条历史; 手动 escalate apply 成功返回 0 候选 (2026-08-29)

---






