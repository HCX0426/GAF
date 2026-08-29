---
spec_id: 2026-08-29-logging-system-consolidation
status: active
created: 2026-08-29
type: new_feature
scope: backend/protocol, backend/debug, backend/gaf_core, backend/monitors, frontend/src/pages, docs
prev: 2026-08-29-services-management-monitor
next: N/A
---

# Spec: 日志体系收口 — 数据源补齐 + 统一文件日志检索 (AI 可调试视角)

> **背景**：2026-08-29 日志体系 meta_audit 实证发现 3 个"日志中心恒空" tab +
> 1 处读侧断层 + 1 处双入口。用户确认开 spec 修 P1 两项，并强调**这些日志最终
> 会在开发调试时交给 AI 查看** → 收口标准 = AI 能跨层统一检索。
>
> 实证数据（DB + API）：
> - LogEntry total=0（spec §2.2 停写，读侧未收口）→ /api/v2/logs/ 返回 0 条
> - MessageFrameLog total=0（无任何生产写入点）
> - CrashReport total=0（前端 error_boundary 上报走 /logs/frontend-errors/ 写
>   logger，不写表）
> - AuditLog 291 / RecoveryLog 59 / Notification 6 正常；MonitorRule 4/4 enabled

## 1. 目标

1. 日志中心 8 tab 全部具备真实数据源：消息帧（P1）、崩溃报告（P1）、应用日志（P2）
2. 统一文件日志检索 API（P2）：`GET /api/v2/logs/files/` 按 service/日期/lines/报错过滤
   读文件层日志（服务终端 + 原生日志），供前端日志中心、服务管理、AI 调试共用
3. 收敛审计日志双入口（P3）
4. AI 可调试性文档 + 服务管理页 e2e（P4）

## 2. 阶段状态表

| Phase | 内容 | TD | 状态 |
|-------|------|----|------|
| P1 | 消息帧日志写入（protocol 收发帧 → MessageFrameLog）+ 崩溃报告写入（FrontendErrorReportView → CrashReport） | TD-416 + 新 | ✅ 完成 (7+1 测试; 环境实测 outbound 帧记录) |
| P2 | 统一文件日志检索 API + 应用日志/时间线收口（前端数据源切换） | TD-417 | ✅ 完成 (log_files.py + /logs/files/; AppLogTab 文件层; 浏览器实测有数据) |
| P3 | 审计日志双入口收敛（日志中心审计 tab 移除） | TD-418 | ✅ 完成 (8→7 tab; 浏览器实测) |
| P4 | 服务管理页 e2e + AI 调试文档（日志查询指引/分界段） | TD-419 | ✅ 完成 (e2e spec + handbook 指引) |
| P5 | 回归（pytest/tsc/vitest/浏览器）+ 文档 + commit + 归档 | — | ⏳ commit 待执行 |

## 3. 实施设计

### P1-1 消息帧日志（TD-416）

- `AgentConsumer`（backend/protocol/consumers.py）收发帧路径写 `MessageFrameLog`：
  - inbound（receive_json）与 outbound（group_send 到 agent 的帧）各一条
  - 字段：trace_id（复用）/message_type/direction/payload（截断保护,
    max 2KB）/agent_session（可空）
  - 开关 `PROTOCOL_FRAME_LOG_ENABLED`（默认开；eager/高帧率可关）
- 测试：WS 交互测试 + MessageFrameLog 计数断言（复用现有 protocol WS 测试）

### P1-2 崩溃报告写入（新）

- `FrontendErrorReportView`（gaf_core/views.py:476）：匿名上报除写
  `gaf_core.frontend_error` logger 外，同时落 `debug.models.CrashReport`
  （component=page_slug / error_type / stack_trace / system_info / user_agent）
  - 保留 resolved 工作流（ops.ts resolveCrashReport）；前端崩溃 tab 直接可查
- 测试：POST /logs/frontend-errors/ → CrashReport 新增 1 条
- window.onerror 的 Script error. 过滤维持（上轮已做）

### P2-1 统一文件日志检索 API

- `GET /api/v2/logs/files/`（gaf_core 新增，挂 /api/v2/logs/files/）：
  - query: `service`（redis|backend|agent|frontend|daemon，可选默认 backend）
    `date`（YYYY-MM-DD 可选，默认当日）`lines`（≤2000 默认 300）`filter`（all|error）
  - 定位逻辑复用 monitors 的 `_resolve_service_log_files`（抽到 gaf_core 公共
    模块 `gaf_core/log_files.py`，monitors 改 import 该模块避免双份）
  - 读文件尾部；filter=error 跨文件收集报错行（与 services/logs 一致）
- 该端点服务：日志中心"应用日志"tab（P2-2）、服务管理/AI 检索

### P2-2 应用日志 tab + 统一时间线收口（TD-417）

- 日志中心"应用日志"tab 数据源改为 `logs/files/?service=backend&lines=300`
  （展示最近文件日志；保留 WS 实时推送体验不变）
- 统一时间线 UNION：LogEntry 分区保留（历史），新增说明文案（应用日志历史
  已迁文件）；timeline 增加可选 `service` 查询参数（读文件日志 ref_type=service_file）
- 前端 `UnifiedLogEntry.ref_type` 增加 `service_file` 分支渲染

### P3 审计双入口收敛（TD-418）

- 日志中心移除"审计日志" tab（AuditLogTab 删除）；审计单入口 = 系统页
  `/system/audit-log`（统一时间线仍含 AuditLog 聚合）
- SpecialtyLogTabs 移除 AuditLogTab 引入与 tab 项；LogCenterPage tab 减至 7

### P4 e2e + AI 文档（TD-419）

- e2e 补 `/system/services`（卡片渲染 + 日志 Drawer + 过滤）+ 日志中心 smoke
  （应用日志 tab 有数据）
- AI 文档：ai-operating-handbook 补"日志查询指引"（去哪查：DB 业务事件/文件
  终端日志/健康快照 + logs/files 用法）；tech-stack 关键路径补 logs/files；
  procedure.md 或 overview 补"日志体系分界"（DB 层=业务事件审计，文件层=
  进程终端/执行日志，服务管理=健康+终端）

## 4. 验收标准

| P0 | 判据 |
|----|------|
| P1-1 | agent 连接后收发 1 帧 → MessageFrameLog 新增; 消息帧 tab 有数据; timeline 出现 MessageFrameLog |
| P1-2 | POST /logs/frontend-errors/ → CrashReport 新增 + resolved 流程可用; 崩溃 tab 有数据 |
| P2-1 | logs/files/?service=backend 返回文件尾部行; filter=error 只返回报错; date 参数生效 |
| P2-2 | 日志中心应用日志 tab 显示最近文件日志; timeline 可选含 service_file |
| P3 | 审计日志仅 /system/audit-log 可达; 日志中心 tab 7 个; timeline 仍含 AuditLog |
| P4 | e2e 新增用例全过; ai-operating-handbook + tech-stack + procedure 已更新 |
| P5 | 全量 pytest + tsc + vitest 通过; 浏览器实测日志中心/服务管理; commit + 归档 |

## 5. 不做（范围外）

- 不恢复 LogEntry 表写 DB（维持文件为主, 控制 DB 膨胀）
- 不把服务终端日志全部导入 DB/统一时间线（量级控制）— 以 logs/files 检索替代
- 不新增通知/告警功能; MonitorRule 未触发属使用情况, 不在本 spec
- 不清理陈旧 DB 表 (LogEntry 历史行保留只读)