# Spec-Context: 服务管理页 + 服务终端报错捕获/检测/统一查看 (2026-08-29)

## 用户决策原文
- "系统的那个页签，加一个服务管理？监控各个服务的状态，还有每个服务的终端如果有报错，gaf会检测到吗，会记录吗，到时候统一看记录就能解决报错了，目前的日志？" — 两个诉求：
  1) 系统页签新增"服务管理"页监控服务状态；
  2) 服务终端报错要能被检测 + 记录 + 统一查看以解决报错；并询问当前日志现状。

## 现状核查（回答"目前的日志？"）
- backend: `FileLogHandler` → DB LogEntry + `debug/YYYYMMDD/backend/system/*/run.log`；agent → `agent.log`；daemon → `daemon.log`；
  日志中心 `/ops/logs` 8 tab 统一查看 DB 层日志（应用/审计/恢复/消息帧/LLM/崩溃/归档）。
- **根缺陷**: `gaf_daemon.start_service` 用 `stdout/stderr=DEVNULL` 启动服务 → redis/frontend 终端输出被丢弃、
  服务控制台任何报错 GAF 完全无感知；且无任何机制扫描服务日志 ERROR。

## N151 5 步法评估
1. **架构盘点**: 已归档 spec `2026-08-29-service-orchestration-health-aware` 提供 app 级健康探针（scripts/services/health.py）
   + daemon 健康循环 + 状态灯服务小节（monitors/system_status services 字段）。缺口 = 终端输出捕获 + 报错检测 + 独立管理页。
2. **识别反模式**: (a) DEVNULL 丢终端输出（运维盲区）; (b) 服务日志散落多目录无统一入口; (c) 状态灯信息量不足以排查。
3. **备选方案**: A) daemon 捕获终端 → 服务日志文件 + 看门狗 ERROR 扫描 → 服务管理页统一查看（自研，复用现有探针层）;
   B) 接入现成 log 聚合（ELK/Loki，重、引入外部依赖）; C) 只写日志不建页面（半途）。
4. **拒绝反模式**: 拒绝 B（外部依赖与单人项目不合，N167 已考量）、C；选 A（最小增量复用 health.py + daemon 既有循环）。
5. **AI 自决边界**: scripts + monitors + 前端纯增量；不写 DB（服务终端日志保持文件形态防膨胀）；不做启停按钮（权限/安全另行评估）。

## N167 七维度评分（方案 A）
- **架构长远性**: 终端输出→文件→扫描→页面为服务可观测性标准链路，与 daemon 单一 Owner 架构契合 — 4
- **全局归一化**: 日志查看与 /ops/logs 职责分界清晰（DB 应用日志 vs 进程终端日志），无重叠 — 4
- **新旧兼容**: 快照新增字段（processes/log_errors）向后兼容（status 仍读 services）— 4
- **现有业务完善**: "服务终端报错"首次可发现/可排查 — 4
- **性能资源优化**: 5MB 轮转 + 扫描上限 5000 行，看门狗开销 <50ms — 4
- **安全合规加固**: 日志读取走 IsAuthenticated + RoleBasedPermission(view)，无敏感字段 — 3
- **长期维护成本**: 捕获/扫描集中在 daemon+health.py，页面独立组件 — 4
- **总分**: 27（≥19 自决免问）

## 关键实施决策
- **日志落盘路径**: `debug/system/services/<name>.log`（固定路径便于 tail，不进日期归档；>5MB 轮转 `.log.1` 覆盖旧备份）；
  backend/agent/daemon 原生日志（django.log/agent.log/daemon.log）作为 fallback 供扫描与 filter=error 跨文件收集。
- **报错检测**: `health.py scan_log_errors` 正则（`\b(ERROR|CRITICAL|FATAL)\b` | `Traceback(...)` | `(Exception|Error)[:(]`），
  daemon `_run_health_checks` 每 15s 组装 `processes` + `log_errors` 注入健康快照（`write_health_snapshot(snapshot, extra=...)`）。
- **API**: `GET /api/v2/monitors/services/`（快照 + gaf_daemon.pid 合并 5 服务字段）；
  `GET /api/v2/monitors/services/logs/?service=&lines=&filter=all|error`（tail 400 默认 / 上限 2000；error 跨文件收集报错行）。
- **前端**: System tab 新增"服务管理"（sidebar.services i18n 4 语言 + /system/services 路由 + ServicesPage 卡片网格 + 日志 Drawer）；
  15s 轮询；ERROR 高亮（前端独立正则，与后端语义一致）。
- **daemon 生命周期**: ServiceInfo 增加 `log_fh`，start/stop/watchdog 退出/reconcile 处 close；启动失败 fallback DEVNULL。
- **测试**: backend `monitors/tests/test_services_api.py`（9 用例，patch DEBUG_ROOT 隔离 tmp 目录）；
  scripts `tests/test_health_services.py`（19 用例）；前端 ServicesPage.test.tsx（3 用例）；浏览器实测全过。

## 已知限制（spec 记录，非本次实现）
- 服务终端日志不入 DB（量级控制），不接入 /ops/logs 统一时间线（留作后续）。
- 前端不做服务启停操作按钮（daemon CLI 已够用，安全待评估）。
- 报错检测不做告警联动（MonitorEvent），仅页面标红 + 快照计数。

## 范围外检出（本次发现的既有问题 → TD）
- `worker/src/utils/log_rotation.py` DateRotatingFileHandler 跨天轮转偶发 `_stream=None` → AttributeError
  （status/daemon 命令日志重复报错）— 已登记 active-tech-debt.md，非本次修复。

## N173 用时字段
- start_ts: 2026-08-29T01:10:00+08:00
- end_ts: 2026-08-29T01:52:00+08:00
- duration_min: ~42 (跨 scripts/backend/frontend 三端 + 浏览器实测 + 文档同步 + TD 登记; 分类属大修改, 基线 < 60 min)
- within_baseline: true (42 < 60)