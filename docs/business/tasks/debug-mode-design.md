---
summary: 调试模式设计 — 统一 GAF_DEBUG 环境变量控制所有 app 调试行为
applies_to: [agent, backend, frontend, ops]
last_updated: 2026-08-01
---

# 调试模式设计

> **日期**: 2026-08-01 (初版 2026-07-12, 本次重写反映最新实现)
> **状态**: 已实现 — 统一调试模式通过 `GAF_DEBUG` 环境变量控制

## 1. 统一调试模式配置 (N196)

### 核心原则

**一个配置点控制所有 app 的调试行为**。不再需要单独配置 agent 的 `--debug` 参数、backend 的 `debug_mode` 参数、前端设置页开关。

### 配置方式

根目录 `.env` 文件:

```ini
# 统一调试模式（控制所有 app 的调试行为）
# 设置为 1 启用：agent 保存标注调试截图、backend 传递 debug_mode=True、结构化日志全量输出
GAF_DEBUG=1
```

### 优先级规则

CLI 参数 > 环境变量 `GAF_DEBUG` > 配置默认值

```
CLI --debug (最高优先级)
    ↓ 有则覆盖, 无则继续
env GAF_DEBUG=1
    ↓ 有则使用, 无则继续
config default (False)
```

### 覆盖范围

| app | 读取位置 | 行为 |
|-----|---------|------|
| Agent | `agent/src/__main__.py` `build_config()` | 读取 `GAF_DEBUG` 环境变量，CLI `--debug` 可覆盖 |
| Backend | `backend/config/settings/base.py` `settings.GAF_DEBUG` | 读取 `.env` 中的 `GAF_DEBUG` |
| Backend tasks | `backend/tasks/tasks.py` `settings.GAF_DEBUG` | 派发任务时传递 `debug_mode` |
| Backend pipeline | `backend/pipeline/tasks.py` `settings.GAF_DEBUG` | 执行管道时传递 `debug_mode` |
| 启动脚本 | `scripts/gaf_services.ps1` `$env:GAF_DEBUG = "1"` | 启动时设置环境变量，agent 和 backend 都继承 |

> ⚠️ 归属校正(2026-08-28)：启动配置已迁 `scripts/gaf_daemon.py`（gaf_services.ps1 为兼容薄壳）；`GAF_DEBUG` 未由脚本强制置 1。

### 历史演进

- **2026-07-12**: 原始设计 — 通过前端设置页 AppSettings(agent_debug) 开关，后端 API 透传
- **2026-07-28**: N192 双调试视角硬约束 — 调试模式默认开启，不再依赖前端开关
- **2026-08-01**: N196 统一配置 — 引入 `GAF_DEBUG` 环境变量，一个配置点控制所有 app

## 2. 调试目录结构

### 当前结构 (2026-08-01)

```
debug/
└── YYYYMMDD/                              ← 日期（如 20260730）
    ├── agent/                             ← agent 端（执行 pipeline 的进程）
    │   └── <pipeline_basename>/           ← 任务名（如 get_email）
    │       └── HH/                        ← 小时桶（如 05，本地时区）
    │           ├── structured.jsonl       ← 一小时内追加写入
    │           └── screenshots/
    │               ├── annotated/         ← 标注图 PNG
    │               │   └── HHMMSSmmm_<node_id>_<event>.png
    │               └── raw/               ← 原图 JPEG（识别类节点）
    │                   └── HHMMSSmmm_<node_id>_<event>.jpg
    ├── backend/                           ← backend 端（Django + channels）
    │   ├── system/                        ← 系统日志（跨任务）
    │   │   └── HH/
    │   │       ├── django.log             ← Django 请求/异常
    │   │       ├── channels.log           ← WebSocket
    │   │       └── scheduler.log          ← 调度器/恢复引擎
    │   └── tasks/                         ← 任务执行日志（JSONL）
    │       └── <pipeline_basename>/
    │           └── HH/
    │               └── execution.jsonl    ← 派发/状态/恢复动作
    └── frontend/                          ← 前端控制台日志
        └── <page_slug>/
            └── HH/
                └── console.jsonl
```

> ⚠️ 目录实现校正(2026-08-28)：agent 分支实为 N194 嵌套执行目录 `debug/YYYYMMDD/<task>/<HHMMSS_suffix>/`（A1 小时桶分支存在但未启用）；backend/system 下的 `channels.log` / `scheduler.log` 未实现，仅有 `django.log` 兜底。

### 历史结构对比

| 时期 | 目录格式 | 说明 |
|------|---------|------|
| 2026-07-12 设计 | `debug/{YYYYMMDD_HHMMSS}_{pipeline_name}/` | 扁平结构，单目录 |
| 2026-07-28 N192 | `debug/{YYYYMMDD}/{pipeline_name}/{HHMMSS}_{execId}/` | 嵌套结构，按日期+任务+执行分桶 |
| 2026-07-30 spec | `debug/{YYYYMMDD}/agent/{pipeline_name}/HH/` | 按 agent/backend/frontend 分桶，小时桶 |
| 2026-08-01 当前 | 同上 | 已实现 |

## 3. 服务启动与调试模式

### gaf_services.ps1

服务管理脚本 `scripts/gaf_services.ps1` 统一管理 4 个服务:

1. **Redis** — 缓存/消息队列
2. **Backend (Daphne)** — ASGI 服务器，支持 WebSocket
3. **Agent** — 任务执行引擎
4. **Frontend (Vite)** — 前端开发服务器

启动顺序: Redis → Backend → Agent → Frontend
停止顺序: Frontend → Agent → Backend → Redis

### 环境变量传递

`gaf_services.ps1` 在启动 backend 和 agent 时设置:

```powershell
$env:GAF_DEBUG = "1"
$env:GAF_ALLOW_LOCALHOST_BYPASS = "1"
```

> ⚠️ 归属校正(2026-08-28)：gaf_services.ps1 为兼容薄壳，实际启动配置在 `scripts/gaf_daemon.py`；`GAF_DEBUG` 未由脚本强制置 1。

### 进程唯一性

- 每个服务启动前先杀已有实例（按端口/命令行匹配）
- Agent 使用 `--skip-singleton-check` 避免锁文件冲突
- 停止时优先使用 `taskkill /F`（跨权限杀进程），失败时回退 `Stop-Process`

### 正常请求响应

后端 API 通过 `UnifiedResponseMiddleware` 统一包装响应格式:

```json
// HTTP 200 — 成功
{"code": 0, "message": "ok", "data": <实际数据>}

// HTTP 4xx/5xx — 错误（code 使用 ErrorCode 业务码）
{"code": 1001, "message": "未授权", "data": null}
```

- 成功的 HTTP 状态码为 **200**（body 中 `code: 0`）
- 错误码使用 ErrorCode 4 位业务码体系（非 HTTP status_code），便于前端统一映射

## 4. 结构化日志

### 日志文件位置

| 日志 | 路径 | 说明 |
|------|------|------|
| Agent 结构化日志 | `debug/{YYYYMMDD}/agent/{pipeline}/{HH}/structured.jsonl` | 节点执行事件 |
| Agent 文本日志 | `agent/logs/agent.log` | 默认日志文件 |
| Backend 执行日志 | `debug/{YYYYMMDD}/backend/tasks/{pipeline}/{HH}/execution.jsonl` | 任务状态机 |
| Backend 系统日志 | `debug/{YYYYMMDD}/backend/system/{HH}/django.log` | Django 请求/异常 |
| Backend Channels | `debug/{YYYYMMDD}/backend/system/{HH}/channels.log` | WebSocket 日志 |
| 全局日志 | `debug/_global/run.log` | FileLogHandler 自动写 |

### 关键事件类型

| 事件 | 触发时机 | 包含字段 |
|------|---------|---------|
| `task_started` | 任务开始执行 | execution_id, pipeline_name, device_id, task_definition_hash |
| `node_started` | 节点开始执行 | node_id, node_type, input |
| `node_completed` | 节点执行完成 | node_id, node_type, success, elapsed_ms, result |
| `coord_transform_context` | 坐标转换初始化 | display_context: {dpi, screen_width, screen_height, scale_x, scale_y, base_res} |
| `task_failed` | 任务执行失败 | error_msg, error_code, failed_node_id |
| `task_recovered` | 恢复引擎接管 | recovery_strategy |

### 结构化日志 vs 文本日志

| 维度 | structured.jsonl | agent.log |
|------|-----------------|-----------|
| 格式 | JSONL（每行一个 JSON 对象） | 文本（时间戳 + 级别 + 消息） |
| 用途 | AI 程序化解析 | 人工阅读 |
| 粒度 | 节点级事件 | 函数级调试 |
| 关联字段 | trace_id + execution_id | 同 |

## 5. 双调试视角硬约束 (N192)

从 AI 调试和用户调试两个视角确保系统可调试性:

### AI 调试视角 (A1-A7)

1. **报错可读性**: 异常 raise 含节点 id / 输入参数 / 失败原因三要素
2. **中间结果落盘**: 节点 result_data 完整写入（含 coord_system / source / extra）
3. **日志分段**: pipeline 执行日志按节点 boundary 分段
4. **节点链路可追溯**: 失败时能回溯上一个节点输出 → 当前节点输入
5. **retry/fallback trace**: 重试/降级路径留 trace
6. **截断保护**: 长字符串/图像数据/大 dict 合理截断
7. **报错边界**: 节点内部异常被捕获并包装为节点级失败

### 用户调试视角 (B1-B7)

1. **错误提示归一**: 后端校验失败/agent 执行失败 报错转换为用户可读文案
2. **错误码映射**: error_code → user_message 映射表
3. **错误定位**: UI 上显示第几个节点/哪个字段/为什么不合法
4. **模板可跑通**: resources/*/custom_tasks/template.json 可照着改
5. **校验前置**: 前端 schema 校验拦截
6. **执行反馈**: UI 展示节点链路 + 失败节点高亮 + 失败原因
7. **复现路径**: 用户可自行复现/修复

## 6. 相关文档

| 文档 | 内容 |
|------|------|
| [调试日志记录结构](../../architecture/agent/debug-logging-structure.md) | JSONL 日志完整字段定义 |
| 调试目录重构 spec（历史文档未留存；目录结构以本文件 §2 为准） | 目录结构详细设计 |
| [故障排查指南](./troubleshooting.md) | 常见问题排查步骤 |
| [DPI 坐标系统](../devices/dpi-coordinate.md) | 4 层坐标模型 |
| [N192 双调试视角硬约束](../../../.ai-memory/meta/env-hardrules-contextual.md) | L0 系统级约束 |
| [N196 统一调试模式](../../../.ai-memory/meta/env-hardrules-contextual.md) | L0 系统级约束 |