---
spec_id: 2026-08-29-services-management-monitor
status: archived
created: 2026-08-29
type: new_feature
scope: scripts/gaf_daemon.py, scripts/services/health.py, backend/monitors, frontend/src/pages/System
prev: 2026-08-29-service-orchestration-health-aware
next: N/A
implemented_in: 7d6736a
archived: 2026-08-29
---

# Spec: 服务管理页 + 服务终端报错捕获/检测/统一查看

> **背景**：用户要求系统页签新增"服务管理"，监控各服务状态；并询问服务终端报错
> GAF 是否能检测、记录、统一查看以解决报错。经排查现状：
> - 已有健康感知（2026-08-29 归档）提供 app 级探针 + daemon 健康循环 + 状态灯服务小节
> - **缺口 1**：`gaf_daemon.start_service` 用 `stdout/stderr=DEVNULL` 启动服务 →
>   redis/frontend 终端输出被丢弃，backend/agent 的 terminal 输出也无人落盘
> - **缺口 2**：无任何机制扫描服务日志里的 ERROR/CRITICAL/Traceback（报错不可发现）
> - **缺口 3**：系统页签无独立服务管理页（现有 /ops/logs 仅查 DB 日志，不含进程终端）

## 1. 目标

1. 系统页签新增"服务管理"页：redis/backend/agent/frontend/daemon 状态一览
   （健康灯 + detail + PID/端口/重启次数/报错计数），支持查看各服务终端日志
2. daemon 捕获服务终端输出（stdout/stderr → `debug/system/services/<name>.log`，替代 DEVNULL）
3. daemon 每轮扫描服务日志 ERROR/CRITICAL/Traceback → 计数 + 最近报错写入健康快照
4. 统一日志查看：服务管理页内嵌日志查看器（tail + ERROR 过滤），配合 /ops/logs 闭环排查

## 2. 阶段状态表

| Phase | 内容 | 状态 |
|-------|------|------|
| P1 | daemon 服务终端输出捕获（固定文件 + 大小轮转，替代 DEVNULL） | ✅ 完成 (debug/system/services/*.log 4 服务落盘实测) |
| P2 | health.py 报错扫描 `scan_log_errors` + 快照扩展（processes/log_errors） | ✅ 完成 (backend 10 条 / agent 4 条真实检测) |
| P3 | backend `GET /api/v2/monitors/services/` + `GET .../services/logs/` | ✅ 完成 (9 测试通过; filter=error 跨文件收集) |
| P4 | 前端 System tab 服务管理页（状态卡片 + 日志 Drawer） | ✅ 完成 (369 vitest 全过 + tsc 0 + 浏览器实测) |
| P5 | 验证：pytest + tsc/vitest + 浏览器实测 + 文档 + commit | ✅ 完成 (backend monitors 45 + scripts 19 + 前端 369 vitest + tsc 0; 浏览器实测 5 卡片/报错标签/日志 Drawer; commit 7d6736a) |

## 3. 实施设计

### P1: 服务终端输出捕获（scripts/gaf_daemon.py）

- 新增常量 `SERVICE_LOG_DIR = GAF_ROOT / "debug" / "system" / "services"`（固定路径，
  不进入日期归档目录，因为是"运行期终端输出"，需 tail 稳定可寻址）
- 新增 `_open_service_log(name) -> BIO`：
  - 文件 `debug/system/services/<name>.log`
  - 若已存在且 > `MAX_SERVICE_LOG_BYTES`（5MB）→ 轮转为 `<name>.log.1`（覆盖旧备份）
  - `open(..., "ab")` 追加（跨重启保留历史，便于排查）
- `ServiceInfo` 增加 `log_fh` 字段；`start_service` 中：
  - stdout=fh, stderr=同一 fh（stderr 与 stdout 合并，保留原始顺序有偏差可接受）
  - 启动失败/停止时 close 句柄
- `ServiceManager.stop_service` / `run()` finally 清理所有 `log_fh`
- redis 无 stderr 输出，但统一走同一机制（记录 PING/日志类输出）

### P2: 报错检测（scripts/services/health.py + gaf_daemon.py）

- health.py 新增：
  - `SERVICE_LOG_DIR` 常量（与 daemon 一致）
  - `ERROR_PATTERN = re.compile(r"(ERROR|CRITICAL|Traceback|Exception|Error:|raise ")`
  - `scan_log_errors(name) -> dict`：统计最近 `LOG_ERROR_WINDOW`（默认全部，行数上限 2000）
    内 ERROR/CRITICAL/Traceback 匹配行数 + `latest`（最后一条匹配行, 截断 300 字符）
  - `service_log_path(name) -> Path`（daemon 捕获文件；backend 服务 fallback 到
    `debug/YYYYMMDD/backend/system/*/run.log|django.log`，agent → `agent/system/agent.log`，
    daemon → `backend/system/daemon.log`，frontend → 捕获文件或空）
- health.py `write_health_snapshot(snapshot, extra=None)`：payload 合并 extra
- gaf_daemon `_run_health_checks`：
  - 组装 `processes`（name → running/pid/port/restart_count，来自 ServiceInfo）
  - 组装 `log_errors`（name → scan_log_errors(name)）
  - `write_health_snapshot(snapshot, extra={"processes": ..., "log_errors": ...})`
- 兼容：`--check` CLI 不变；旧快照字段（services/detailed）保持

### P3: 服务管理 API（backend/monitors/views.py + urls.py）

- `GET /api/v2/monitors/services/`（`services_view`）：
  - 读 `debug/health-status.json`（services/processes/log_errors）+ `debug/gaf_daemon.pid`
  - 合并输出：
    ```
    {updated_at, daemon:{running,pid},
     services:[{name,healthy,detail,ts,running,pid,port,restart_count,error_count,log_file}]}
    ```
  - daemon 未运行/快照缺失 → 各字段 None/False，不阻塞
- `GET /api/v2/monitors/services/logs/`（`service_logs_view`）：
  - query: `service`（必填）+ `lines`(默认 300, 上限 2000) + `filter`(all|error，默认 all)
  - 定位日志文件（新增 `_resolve_service_log_files(name)`，最新一天优先）
  - 读文件尾部 N 行；filter=error 仅返回匹配行；返回 `{service, path, lines:[...]}`
- 权限：IsAuthenticated + RoleBasedPermission(view)
- 挂到 monitors/urls.py：`path('services/', ...)` + `path('services/logs/', ...)`

### P4: 前端服务管理页（frontend/src/pages/System/ServicesPage.tsx）

- 路由 `/system/services` + Sidebar system-group 子项（i18n `sidebar.services`）
- API client（`src/api/misc.ts` 扩展或新建 `src/api/services.ts`）：
  - `fetchSystemServices()` → GET /monitors/services/
  - `fetchServiceLogs(params)` → GET /monitors/services/logs/
- 页面布局：
  - 顶部：daemon 状态 + 总体健康 + 刷新按钮 + 轮询 15s
  - 服务卡片网格：健康点（绿/红/灰）+ name + detail(截断) + PID/端口/重启次数/报错数
    报错数 > 0 → 红色 Tag「N 条报错」+ 可点击跳日志(error 过滤)
  - 日志 Drawer：每服务"查看日志"打开；tail 加载 + ERROR 高亮 + 刷新 + filter 切换(error/all)
- i18n：settings.ts / sidebar.ts 新增 key
- TS 类型：ServicesStatus / ServiceInfo / ServiceLogsResponse

### P5: 验证 + 文档 + 沉淀

- 后端：monitors 新增 `tests/test_services_api.py`（mock 快照 + 临时日志文件）
- 脚本：health.py `scan_log_errors` 单测
- 前端：`npx tsc --noEmit` + vitest（ServicesPage 渲染 + 日志 Drawer）
- 浏览器实测：登录 → 系统 → 服务管理 → 各服务卡片状态 + 打开日志
- 文档：api-contract.md（2 端点）/ features-overview §7.7 附近新增服务管理 / overview.md 服务编排段 /
  scripts/README.md（services 日志目录说明）/ completed-features.md
- spec-context（B2 大修改必写）: docs/archive/spec-context/2026-08-29-services-management-context.md

## 4. 验收标准

| P0 | 判据 |
|----|------|
| P1 | `daemon start` 后 `debug/system/services/backend.log` 等存在且有内容（原 DEVNULL 无文件） |
| P2 | 手工向服务日志注入 ERROR 行 → 快照 log_errors 计数 +1、latest 含该行 |
| P3 | `GET /api/v2/monitors/services/` 返回 5 服务完整状态；`services/logs/?service=backend&filter=error` 只返回匹配行 |
| P4 | 浏览器: 系统页签出现"服务管理"；卡片显示健康/报错；日志 Drawer 可打开并高亮 ERROR |
| P5 | 全量 pytest 通过；tsc 0 错误；相关文档已同步；spec 归档 + hash 回填 |

## 5. 不做（范围外）

- 不写 DB：服务终端日志保持文件形态（量级下 DB 膨胀），接入 /ops/logs 留作后续
- 不做日志告警/通知（MonitorEvent 联动）— 仅页面标红 + 快照计数
- 不做服务启停操作按钮（daemon 已有 CLI，前端操作权限/安全需另行评估）