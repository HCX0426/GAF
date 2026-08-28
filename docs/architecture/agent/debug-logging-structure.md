---
summary: GAF 调试日志记录结构文档，覆盖 agent/backend/frontend 三端 JSONL 结构化日志、系统日志（agent.log/daemon.log/django.log）和标注截图的完整记录时机、字段定义与合理性评估
status: active
applies_to: ['agent', 'architecture']
key_concepts:
  - 双轨调试：JSONL 结构化日志 + PNG 标注截图
  - 三端归一化：agent / backend / frontend 共用 YYYYMMDD/ 统一目录（任务级执行目录 + agent/system + backend/tasks + frontend/<page>）
  - trace_id 全链路贯穿：前端生成 UUID → HTTP header → backend → WS 帧 → agent logger
  - 节点生命周期：start → coord_transform(0~N) → complete
  - 坐标转换 trace：sub_image_to_full / publish_match_pos / logical_to_physical
  - AI 可调试性：从日志反推点击位置的能力
  - 系统日志按日期轮转：agent.log/daemon.log/django.log 按日期+小时分桶写入
  - 任务日志双通道：run.log（文本）+ execution.jsonl（结构化 JSON）
last_updated: 2026-08-09
---

# GAF 调试日志记录结构

> 版本：2.1 | 日期：2026-08-09 | 关联 spec：`2026-07-30-debug-directory-restructure.md` | 关联硬约束：`env-hardrules-contextual.md` N192 双调试视角 / N197 URL 归一化

## 1. 调试日志体系总览

GAF 的调试日志是**双轨制 + 三端归一化**：结构化 JSONL 日志记录"发生了什么"，标注截图记录"画面长什么样"；agent / backend / frontend 三端共用 `debug/<YYYYMMDD>/` 统一目录，便于 AI 调试时在同一日期目录下浏览三端日志。任务级执行目录（`<task_name>/<HHMMSS>_<suffix>/`）由 backend dispatch 创建并与 agent 共写，backend/frontend 的系统与页面日志按 `backend/`、`frontend/` 归集，`agent/system/` 放 agent 常驻日志。

```
debug/
└── YYYYMMDD/                              ← 日期（如 20260825，本地时区）
    ├── <task_name>/                       ← 任务级执行目录（dispatch_task 创建，按任务名分组）
    │   └── <HHMMSS>_<exec_id_suffix>/     ← 单次执行目录（backend 与 agent 共写）
    │       ├── run.log                    ← 任务执行日志（FileLogHandler，文本格式）
    │       ├── structured.jsonl           ← Agent 结构化日志（节点事件 + coord_transform trace）
    │       ├── screenshots/               ← 本次执行的截图
    │       │   ├── annotated/             ← 标注图 PNG（含 ROI/match/center 框）
    │       │   │   └── HHMMSSmmm_<node_id>_<event>.png
    │       │   └── raw/                   ← 原图 JPEG（识别类节点才保留）
    │       │       └── HHMMSSmmm_<node_id>_<event>.jpg
    │       └── meta.json                  ← 用户可读元信息（status: running → completed）
    ├── agent/
    │   └── system/                        ← 系统级日志（N197 2026-08-09 新增）
    │       └── agent.log                  ← Agent 运行日志（设备发现、心跳、WebSocket）
    ├── backend/                           ← backend 端（Django + channels）
    │   ├── system/                        ← 系统日志（跨任务，N197 归一化）
    │   │   ├── daemon.log                 ← Daemon 日志（服务状态、重启、端口探测）
    │   │   └── HH/django.log              ← Django 应用日志（API 请求、序列化、业务异常）
    │   │   ├── channels.log               ← WebSocket 日志（★ 规划中，尚未实现）
    │   │   └── scheduler.log              ← 调度器/恢复引擎（★ 规划中，尚未实现）
    │   └── tasks/                         ← 任务执行日志（JSONL，BackendTaskLogger）
    │       └── <task_name>/
    │           └── HH/
    │               └── execution.jsonl    ← 派发/状态/恢复动作（与 agent structured.jsonl 平行）
    └── frontend/                          ← 前端控制台日志（按页面归集）
        └── <page_slug>/                   ← 页面 slug（如 dashboard, tasks_pipeline, ops_logs）
            └── HH/
                └── console.jsonl          ← 错误上报 + 主动日志
```

> **历史变更**：
> - 2026-07-30 spec (debug-directory-restructure): A1 曾规划 agent 结构化日志按 `agent/<pipeline>/HH/` 小时桶写入（`get_logger` 中 A1 分支的实现已保留），但 orchestrator 始终传入 backend 构建的完整 exec_dir，实际命中 N194 分支写 `structured.jsonl` 到任务级执行目录内 —— **A1 小时桶路径从未启用**，任务级执行目录是 agent 结构化日志的唯一实际位置。
> - 2026-08-09 (N197): 新增系统级日志 — `agent/system/agent.log`、`backend/system/daemon.log`、`backend/system/HH/django.log`，按日期+小时分桶写入，`cleanup_old_archives` 定期清理。新增任务级执行日志 `run.log`（FileLogHandler）。`channels.log` 和 `scheduler.log` 规划中。
> - 2026-08-24: `backend/tasks/<pipeline>` 目录名由 `execution_mode`（固定值 "pipeline"，所有任务混排）改为 `task_name` 任务名分组，与 agent 任务级执行目录一致。

### 1.1 日志通道说明

| 日志类型 | 文件名 | 写入器 | 格式 | 路径层级 |
|----------|--------|--------|------|----------|
| Agent 系统日志 | `agent.log` | `DateRotatingFileHandler` | 纯文本 | `agent/system/` |
| Daemon 日志 | `daemon.log` | `DateRotatingFileHandler` | 纯文本 | `backend/system/` |
| Django 应用日志 | `django.log` | `FileLogHandler` | 纯文本 | `backend/system/HH/` |
| 任务执行日志 | `run.log` | `FileLogHandler` | 纯文本 | `<task_name>/<exec_id>/` |
| Agent 结构化日志 | `structured.jsonl` | `StructuredLogger` | JSONL | `<task_name>/<exec_id>/` |
| 后端任务日志 | `execution.jsonl` | `BackendTaskLogger` | JSONL | `backend/tasks/<task_name>/HH/` |
| 前端控制台日志 | `console.jsonl` | `FrontendConsoleLogger` | JSONL | `frontend/<page>/HH/` |

### 1.2 两个文件的关系

| 维度 | JSONL 日志 | 标注截图 |
|------|-----------|---------|
| **记录什么** | 坐标转换链路、节点状态、变量快照 | 画面 + ROI 框 + 匹配框 + 点击中心 |
| **回答什么问题** | "点击位置是怎么算出来的" | "匹配到了什么，画面是什么状态" |
| **AI 调试用途** | 反推坐标转换链路，定位偏移根因 | 确认模板是否匹配到正确位置 |
| **用户调试用途** | 排查"为什么点偏了" | 排查"为什么没识别到" |

### 1.2 三端日志的关联纽带：trace_id

`trace_id` 是一次用户操作链路的唯一标识（完整 UUID，由前端 `crypto.randomUUID()` 生成），贯穿三端：

```
前端 (axios 拦截器) → HTTP X-Trace-Id header → backend TracingMiddleware
   → current_trace_id ContextVar → WS 帧顶层 trace_id → agent handler
   → ContextVar → StructuredLogger / BackendTaskLogger / FrontendConsoleLogger
```

AI 调试时 `grep trace_id` 即可串联三端日志，定位一次用户操作的全链路：
- `debug/<YYYYMMDD>/<task_name>/<HHMMSS>_<exec_id>/structured.jsonl` — agent 执行的节点事件
- `debug/<YYYYMMDD>/backend/tasks/<task_name>/HH/execution.jsonl` — backend 派发/状态事件
- `debug/<YYYYMMDD>/frontend/<page_slug>/HH/console.jsonl` — 前端错误上报

trace_id 为空字符串时表示无 HTTP 请求上下文（如 CLI / Celery 触发的执行），AI 调试时按 "trace_id 为空" 过滤即可。

## 2. JSONL 日志记录时机

### 2.1 节点生命周期中的记录点

一次 `open_mailbox` 节点执行（`template_match` + `click_on_match=true`）会产生 **4~5 条 JSONL 记录**：

```
节点执行时间线
═══════════════════════════════════════════════════════════════════
[1] node.execute.start          ← 节点开始，记录输入配置
      │
      │  process_roi (base → physical)        ← 转换① 不记 trace
      │
[2]   coord_transform            ← 转换② sub_image_to_full
      step=sub_image_to_full        (子图匹配位置 → 全图物理位置)
      │
      │  cv2.matchTemplate                   ← 模板匹配本身不记
      │
[3]   coord_transform            ← 转换③ publish_match_pos
      step=publish_match_pos         (physical → logical，发布点击坐标)
      │
      │  device.click(logical)               ← 转换④ 在 device 内部
      │
[4]   coord_transform            ← 转换④ logical_to_physical
      step=logical_to_physical       (logical → physical，N191 #3 修复后才有)
      │
[5] node.execute.complete        ← 节点完成，记录完整诊断数据
═══════════════════════════════════════════════════════════════════
```

### 2.2 不同节点类型的记录数

| 节点类型 | coord_transform trace 数 | 总记录数 |
|---------|-------------------------|---------|
| `template_match` (click_on_match=true) | 3（sub_image_to_full + publish_match_pos + logical_to_physical） | 5 |
| `template_match` (click_on_match=false) | 2（sub_image_to_full + publish_match_pos） | 4 |
| `ocr` (click_on_match=true) | 3（sub_image_to_full + publish_match_pos + logical_to_physical） | 5 |
| `click` / `swipe` (有 coord_transformer) | 1~2（resolve_target + logical_to_physical） | 3~4 |
| `wait` (ocr mode) | 2（sub_image_to_full + publish_match_pos） | 4 |
| `key_press` / `direct_hit` | 0~1 | 2~3 |

## 3. JSONL 记录字段定义

### 3.1 node.execute.start（节点开始）

**记录时机**：节点 `execute()` 入口处

**字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | ISO 8601 | UTC 时间戳 |
| `execution_id` | str | 执行 ID（与文件名对应） |
| `trace_id` | str | HTTP 请求级 trace_id（A1 新增，空时省略字段；CLI / Celery 触发时为空） |
| `pipeline_name` | str | pipeline 名称（A1 新增，空时省略字段） |
| `node_id` | str | 节点 ID（如 `open_mailbox`） |
| `node_type` | str | 节点类型（如 `template_match`） |
| `step_index` | int | 节点在 pipeline 中的序号 |
| `event` | str | 固定 `"node.execute.start"` |
| `elapsed_ms` | float | 已耗时（start 时为 0） |
| `retry_count` | int | 重试次数 |
| `device_type` | str | 设备类型（start 时为空） |
| `input_config` | dict | 节点输入配置（threshold/roi/template_id 等） |
| `previous_node_id` | str | 上一节点 ID（首节点为空） |

**示例**：
```json
{
  "timestamp": "2026-07-29T16:50:57.591Z",
  "execution_id": "exec-308cd6276342",
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "pipeline_name": "get_email",
  "node_id": "open_mailbox",
  "node_type": "template_match",
  "step_index": 0,
  "event": "node.execute.start",
  "elapsed_ms": 0.0,
  "retry_count": 0,
  "device_type": "",
  "input_config": {
    "threshold": 0.8,
    "roi": [1564, 28, 95, 61],
    "roi_coord_type": "base",
    "click_on_match": true,
    "template_id": "BrownDust-II/templates/get_email/邮箱.png"
  },
  "previous_node_id": ""
}
```

### 3.2 coord_transform（坐标转换 trace）

**记录时机**：每次坐标转换发生时（`emit_coord_trace` 调用）

**字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | ISO 8601 | UTC 时间戳 |
| `execution_id` | str | 执行 ID |
| `event` | str | 固定 `"coord_transform"` |
| `node_id` | str | 节点 ID（或 `windows_device` 表示 device 内部转换） |
| `step` | str | 转换步骤名（见下表） |
| `device_type` | str | 设备类型 |
| `raw` | dict/null | 转换前坐标 |
| `converted` | dict | 转换后坐标 |
| `formula` | str | 转换公式描述 |
| `transformer_id` | str | transformer 实例标识 |
| `coord_system_in` | str | 输入坐标系标签 |
| `coord_system_out` | str | 输出坐标系标签 |
| `trace_id` | str | HTTP 请求级 trace_id（A3 新增，由 context.emit_coord_trace 从 ContextVar 注入；空时省略字段） |
| 额外字段 | any | 如 `roi_offset_phys` / `box_idx` / `var_name` 等 |

**`step` 取值**：

| step 值 | 含义 | 记录位置 |
|---------|------|---------|
| `sub_image_to_full` | 子图坐标 → 全图物理坐标 | coord_transformer.apply_roi_offset_to_subcoord |
| `publish_match_pos` | 发布匹配位置到 _last_match_pos | coord_transformer + 节点 |
| `logical_to_physical` | logical → physical（device.click 内部） | InputHandler._logical_to_physical |
| `resolve_target` | 解析目标坐标（click/swipe 节点） | 节点内部 |
| `device_click` | device.click 调用（旧版，部分路径） | 节点 |
| `template_scale` | 模板缩放 | _match_with_scaling |

**示例（sub_image_to_full）**：
```json
{
  "timestamp": "2026-07-29T16:50:57.704Z",
  "execution_id": "exec-308cd6276342",
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "event": "coord_transform",
  "node_id": "open_mailbox",
  "step": "sub_image_to_full",
  "device_type": "windows",
  "raw": {"x": 15, "y": 9, "w": 38, "h": 29},
  "converted": {"x": 1579, "y": 37, "w": 38, "h": 29},
  "formula": "sub_image_to_full(sub=(15,9,38,29), roi_offset_phys=(1564,28)) -> phys=(1579,37,38,29)",
  "transformer_id": "win_logical",
  "coord_system_in": "sub_image",
  "coord_system_out": "physical",
  "roi_offset_phys": [1564, 28]
}
```

**示例（logical_to_physical，N191 #3 修复后才有）**：
```json
{
  "timestamp": "2026-07-30T...",
  "execution_id": "exec-xxx",
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "event": "coord_transform",
  "node_id": "windows_device",
  "step": "logical_to_physical",
  "device_type": "windows",
  "raw": [1065, 34],
  "converted": [1598, 51],
  "formula": "physical = logical * dpi_scale(1.5000)",
  "coord_system_in": "logical",
  "coord_system_out": "physical"
}
```

### 3.3 node.execute.complete（节点完成）

**记录时机**：节点 `execute()` 返回前

**字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | ISO 8601 | UTC 时间戳 |
| `execution_id` | str | 执行 ID |
| `trace_id` | str | HTTP 请求级 trace_id（A1 新增，空时省略字段；与 start 事件一致） |
| `pipeline_name` | str | pipeline 名称（A1 新增，空时省略字段） |
| `node_id` | str | 节点 ID |
| `node_type` | str | 节点类型 |
| `step_index` | int | 节点序号 |
| `event` | str | 固定 `"node.execute.complete"` |
| `elapsed_ms` | float | 节点总耗时 |
| `retry_count` | int | 重试次数 |
| `success` | bool | 是否成功 |
| `error_msg` | str | 错误信息（成功时为空） |
| `error_code` | str | 错误码（如 `TIMEOUT`） |
| `confidence` | float | 匹配置信度（识别类节点） |
| `threshold` | float | 匹配阈值 |
| `match_location` | dict | 匹配位置（物理坐标） |
| `roi_physical` | list | 物理坐标 ROI |
| `screenshot_path` | str | 标注图路径 |
| `raw_screenshot_path` | str | 原图路径（识别类节点） |
| `coord_system` | str | 坐标系（`logical` / `physical`） |
| `device_type` | str | 设备类型 |
| `transformer_id` | str | transformer 实例标识 |
| `variables_snapshot` | dict | 变量快照（含本节点产出的所有变量） |
| `previous_node_id` | str | 上一节点 ID |
| `previous_node_type` | str | 上一节点类型 |
| `inter_node_gap_ms` | int | 与上一节点的间隔时间 |
| `previous_node_result_data` | dict | 上一节点的结果数据（截断长字符串） |

**示例（成功）**：
```json
{
  "timestamp": "2026-07-29T16:50:57.805Z",
  "execution_id": "exec-308cd6276342",
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "pipeline_name": "get_email",
  "node_id": "open_mailbox",
  "node_type": "template_match",
  "step_index": 0,
  "event": "node.execute.complete",
  "elapsed_ms": 172.0,
  "retry_count": 0,
  "success": true,
  "error_msg": "",
  "confidence": 0.9861,
  "threshold": 0.8,
  "match_location": {"x": 1579, "y": 37},
  "roi_physical": [1564, 28, 95, 61],
  "screenshot_path": "D:\\code\\GAF\\debug\\20260729\\agent\\get_email\\16\\screenshots\\annotated\\165057805_open_mailbox_match_success.png",
  "raw_screenshot_path": "D:\\code\\GAF\\debug\\20260729\\agent\\get_email\\16\\screenshots\\raw\\165057805_open_mailbox_match_success.jpg",
  "coord_system": "logical",
  "device_type": "windows",
  "transformer_id": "win_logical",
  "variables_snapshot": {
    "open_mailbox_match_result": {
      "confidence": 0.9861,
      "x": 1065, "y": 34,
      "match_loc": {"x": 1579, "y": 37},
      "template_size": {"w": 38, "h": 29, "orig_w": 47, "orig_h": 36, "scale_ratio": 0.8019},
      "screen_size": {"w": 1540, "h": 866},
      "clicked": true
    }
  }
}
```

**示例（失败）**：
```json
{
  "timestamp": "2026-07-29T16:51:02.813Z",
  "node_id": "wait_regular_email",
  "node_type": "wait",
  "event": "node.execute.complete",
  "success": false,
  "error_msg": "节点 wait_regular_email 执行超时 (5.0s)",
  "error_code": "TIMEOUT",
  "variables_snapshot": {
    "wait_regular_email_ocr_ocr_result": {
      "text": "公会\n好友",
      "texts": ["公会", "好友"],
      "confidence": 0.9996,
      "boxes": [[406, 347, 87, 78], [232, 345, 84, 83]]
    }
  }
}
```

## 4. 标注截图记录结构

### 4.1 文件命名

A2 (spec 2026-07-30) 起统一为 `HHMMSSmmm_<node_id>_<event>_<status>.<ext>` 格式，时间前缀可排序，便于与日志时间戳对应：

```
HHMMSSmmm_<node_id>_<event>_<status>.png    ← 标注图（PNG 无损）
HHMMSSmmm_<node_id>_<event>_<status>.jpg    ← 原图（JPEG q=85，仅识别类节点）

# 实例
165057805_open_mailbox_match_success.png    ← template_match 节点 open_mailbox 成功
165057805_open_mailbox_match_success.jpg    ← 原图
002221123_ocr_email_fail.jpg                ← ocr 节点 email 失败
004710538_wait_regular_email_wait_success.png  ← wait 节点 wait_regular_email 成功
004710740_exit_mailbox_key_press_success.png   ← key_press 节点 exit_mailbox 成功
```

**命名规则**：
- `<event>` = 节点类型（`match` / `ocr` / `click` / `swipe` / `key_press` / `wait` 等）
- `<status>` = `success` / `fail`
- 旧格式 `match_{success|fail}_{template_id}_{HHMMSSmmm}.png` 已废弃（A2 前）

### 4.2 标注内容

```
+----------------------------------------+--------+
| Template: 邮箱.png                      |        |
| Status: SUCCESS                         | Orig   |
| Score: 0.9861 | Threshold: 0.80        | 47x36  |
| Scale: 0.8019 | Screen: 1540x866       |        |
| ROI(phys): (1564, 28, 95, 61)          +--------+
| Match(phys): (1579, 37, 38, 29)        |        |
|                                         | Scaled |
|    [截图 + 蓝色ROI框 + 红色匹配框]       | 38x29  |
|    [绿色点击中心点]                      |        |
+----------------------------------------+--------+
```

| 元素 | 颜色 | 含义 |
|------|------|------|
| 蓝色框 | BGR (255,0,0) | ROI 搜索区域（物理坐标） |
| 红色框 | BGR (0,0,255) | 匹配位置（成功时） |
| 绿色点 | BGR (0,255,0) | 点击中心（成功且 click_on_match=true 时） |
| 红色连线 | BGR (0,0,255) | 缩略图 → 匹配位置的连线 |
| 左上文字 | 白色 | Template / Status / Score / Threshold / Scale / Screen / ROI / Match |

### 4.3 原图（raw）

- **格式**：JPEG quality=85（节省空间）
- **保留策略**：仅识别类节点（template_match / ocr / feature_match / color_detect）保留原图
- **动作类节点**（click / swipe / key_press / wait）不保留原图（标注图已包含全部诊断信息）

## 5. 日志结构合理性评估

### 5.1 优点

| 设计点 | 优势 |
|--------|------|
| **JSONL 格式** | 每行一条记录，可流式读取，`jq` 友好 |
| **execution_id 贯穿** | 一次 pipeline 执行的所有记录可关联 |
| **trace_id 全链路贯穿** | A1/A3 新增。前端 → backend → agent 三端日志可通过同一 trace_id 串联，AI 一次 grep 即可定位全链路 |
| **三端统一目录结构** | spec 2026-07-30 新增。agent/backend/frontend 共用 `debug/<YYYYMMDD>/`（任务级执行目录 + agent/system + backend/tasks + frontend/<page>），AI 在同一日期目录下浏览三端日志 |
| **coord_transform trace** | 坐标转换链路完全可观测，AI 可反推点击位置 |
| **variables_snapshot** | 节点产出变量完整快照，跨节点数据流可追溯 |
| **双轨制（JSONL + 截图）** | 逻辑链路 + 画面状态互补 |
| **标注图信息密度高** | 一张图包含 ROI/match/center/template/scale 全部信息 |
| **小时桶分桶** | A1 设计并实现于 `get_logger`（`agent/<pipeline>/HH/`），但 orchestrator 始终传入完整 exec_dir，实际命中 N194 分支 —— **未启用**（见 §1 历史变更）；backend execution.jsonl / frontend console.jsonl 的小时桶已生效 |
| **截图时间前缀命名** | A2 新增。`HHMMSSmmm_<node_id>_<event>_<status>.<ext>` 时间前缀可排序，与日志时间戳对应 |
| **长字符串截断** | `previous_node_result_data` 中的长路径自动截断（`_truncated: true, _len: 113`） |

### 5.2 已修复的缺陷

| 缺陷 | 修复 | 影响 |
|------|------|------|
| **N191 遗漏点 #3**：WindowsDevice 缺 `set_coord_trace_callback` → `step=logical_to_physical` 不记录 | 2026-07-30 修复，新增转发方法 | device.click 内部坐标转换从黑盒变可观测 |
| **N191 遗漏点 #4**：`_click_postmessage` 不调 `_logical_to_physical` → PostMessage 路径点击偏移 | 2026-07-30 修复，加入转换调用 | PostMessage 路径点击位置正确 |
| **N191 遗漏点 #5**：`_swipe_postmessage` 同 #4 | 2026-07-30 修复 | PostMessage 路径滑动位置正确 |
| **N194 双写机制冗余**：agent 本地镜像 + backend 归一化目录双份镜像，造成代码冗余和路径维护成本 | 2026-07-31 曾规划移除双写，实际**保留**：任务级执行目录 `structured.jsonl`（主）+ backend `backend/debug/...` mirror（run.log）+ agent cwd mirror（structured.jsonl）三者并存，镜像只放日志不重复截图 | 路径仍有多份镜像，交付维护；主调试入口为任务级执行目录 |
| **trace_id 体系割裂**：HTTP 和 WS 两套 trace_id 体系不互通，无法跨进程关联 | 2026-07-31 A1/A3 修复，前端生成 UUID → HTTP header → backend ContextVar → WS 帧 → agent logger | 三端日志可通过 trace_id 串联 |
| **A2 截图命名不可排序**：旧命名 `match_<status>_<template_id>_<HHMMSSmmm>.png` 时间戳在末尾，无法按时间排序 | 2026-07-31 A2 修复，改为 `HHMMSSmmm_<node_id>_<event>_<status>.<ext>` 时间前缀 | 截图按时间排序，与日志时间戳对应 |

### 5.3 仍存在的问题

| 问题 | 严重程度 | 说明 |
|------|---------|------|
| **转换① process_roi 不记 trace** | 低 | ROI base→physical 转换无 trace，但 `node.execute.complete` 的 `roi_physical` 字段记录了最终物理 ROI，可反推 |
| **转换⑤ ClientToScreen 不记 trace** | 低 | physical→screen 的窗口原点偏移无 trace，但此步骤是 Win32 API 调用，偏移量固定且可从窗口矩形推算 |
| **monitor/handlers.py 路径无 trace** | 中 | 弹窗跳过路径的点击不记 coord_transform，不影响主 pipeline 调试 |
| **fallback 动作分发 (pipeline_node_execution.py:363-372) 无 trace** | 中 | fallback 动作点击不记 coord_transform，不影响主 pipeline 调试 |
| **标注图不含点击后画面** | 低 | 标注图在点击前保存，无法反映点击后的画面变化。但 `wait` 节点的超时截图可部分补偿 |

### 5.4 改进建议

| 建议 | 优先级 | 说明 |
|------|--------|------|
| 补齐 monitor 路径的 coord_transformer 接入 | P2 | 弹窗跳过路径 DPI>100% 时可能点偏 |
| 标注图增加点击后画面快照 | P3 | 在 click 后延迟 200ms 再截一张图，确认点击生效 |
| coord_transform trace 增加 `thread_id` | P3 | 多线程并发时区分不同线程的转换 |
| JSONL 增加 `pipeline_id` 字段 | P3 | 便于跨 execution 关联同一 pipeline 的多次执行 |

## 6. AI 调试操作指南

### 6.1 从 JSONL 反推点击位置

```bash
# 1. 找到最新日期的 agent JSONL（新结构按 YYYYMMDD/HH 分桶）
ls -d debug/*/agent/*/  | sort -r | head -3      # 列出最近的日期/pipeline 目录
ls debug/20260731/agent/get_email/16/structured.jsonl  # 定位到具体小时桶

# 2. 提取某节点的所有 coord_transform trace
python -c "
import json
with open('debug/20260731/agent/get_email/16/structured.jsonl', encoding='utf-8') as f:
    for line in f:
        if 'coord_transform' in line and 'open_mailbox' in line:
            print(json.dumps(json.loads(line), ensure_ascii=False, indent=2))
"

# 3. 检查是否有 logical_to_physical trace（N191 #3 修复验证）
Select-String -Path 'debug\20260731\agent\get_email\16\structured.jsonl' -Pattern 'logical_to_physical'
# 如果无输出，说明 trace callback 未注入

# 4. 按 trace_id 串联三端日志（A1 新增）
Select-String -Path 'debug\20260731\*\*\*\*\*.jsonl' -Pattern 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
# 同时匹配 agent / backend / frontend 三端包含此 trace_id 的日志行
```

### 6.2 从标注截图诊断匹配问题

```python
# 读取标注图，检查：
# 1. 蓝色 ROI 框是否覆盖了目标元素
# 2. 红色匹配框是否在正确位置
# 3. 绿色点击中心是否在目标元素内
# 4. 右侧缩略图的 Scale 是否合理（0.5~1.5 为正常范围）
import cv2
img = cv2.imdecode(np.fromfile(
    "debug/20260731/agent/get_email/16/screenshots/annotated/165057805_open_mailbox_match_success.png",
    dtype=np.uint8), cv2.IMREAD_COLOR)
cv2.imshow("debug", img)
```

### 6.3 常见问题诊断流程

```
点击偏移问题
  │
  ├─ JSONL 有 logical_to_physical trace?
  │    ├─ 有 → 检查 converted 是否正确（logical × dpi_ratio = physical?）
  │    │       ├─ 正确 → 问题在 ClientToScreen 或窗口状态
  │    │       └─ 错误 → dpi_ratio 设置不对，检查 RuntimeDisplayContext
  │    └─ 无 → 遗漏点 #3 未修复，或 engine.py hasattr 检查失败
  │
  ├─ 标注图红色匹配框位置正确?
  │    ├─ 正确 → 匹配没问题，问题在点击环节
  │    └─ 错误 → 模板问题或 ROI 问题
  │
  └─ 标注图蓝色 ROI 框覆盖目标?
       ├─ 覆盖 → ROI 没问题
       └─ 未覆盖 → ROI 配置过时，需更新
```

## 7. 相关文档

- [坐标转换全链路](./coordinate-transform-pipeline.md) — 每次坐标转换的代码位置与公式
- `docs/business/devices/dpi-coordinate.md` — DPI 坐标系的业务层面说明
- `env-hardrules-contextual.md` N192 — 双调试视角硬约束
- `agent/src/utils/structured_logger.py` — JSONL 日志写入器实现
- `agent/src/utils/debug_image_saver.py` — 标注截图生成器实现
- `backend/gaf_core/task_logger.py` — backend BackendTaskLogger 实现
- `backend/gaf_core/frontend_logger.py` — backend FrontendConsoleLogger 实现

## 8. backend execution.jsonl 结构

> B2 (spec 2026-07-30) 新增。backend 端按任务级 JSONL 日志，与 agent `structured.jsonl` 平行，记录 backend 视角的任务派发 / 状态机 / 恢复动作。

### 8.1 文件路径

```
debug/<YYYYMMDD>/backend/tasks/<safe_pipeline>/HH/execution.jsonl
```

- `<safe_pipeline>`：pipeline_name 经 `_sanitize_pipeline_name` 处理（最长 40 字符，路径分隔符替换为 `_`）
- `HH`：本地时区小时桶，小时切换自动创建新文件

**实现**：[backend/gaf_core/task_logger.py](../../../backend/gaf_core/task_logger.py) `BackendTaskLogger`

### 8.2 字段定义

每行一条 JSON 对象，必填字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | ISO 8601 | 本地时区 ISO 格式（带毫秒，如 `2026-07-31T14:30:25.123`） |
| `level` | str | 日志级别（`info` / `warning` / `error`） |
| `trace_id` | str | HTTP 请求级 trace_id（完整 UUID，由 TracingMiddleware 注入；CLI / Celery 触发时为空） |
| `execution_id` | str | backend 执行标识（如 `exec-<pk>`） |
| `pipeline_name` | str | pipeline 原始名称（未 sanitize） |
| `event` | str | 事件名（如 `task_started` / `node_completed` / `task_failed` / `task_cancelled`） |

payload 字段由调用方传入，合并到 JSON 顶层（不嵌套在 `payload.` 前缀下），便于 AI 用 `jq` 直接读取。

### 8.3 典型事件

| event | 触发时机 | 典型 payload |
|-------|---------|-------------|
| `task_started` | backend 派发任务到 agent 时 | `{"device_id": "...", "task_definition_hash": "..."}` |
| `node_completed` | agent 通过 WS 回报节点完成 | `{"node_id": "...", "node_type": "...", "success": true, "elapsed_ms": 172}` |
| `task_failed` | 任务执行失败 | `{"error_msg": "...", "error_code": "..."}` |
| `task_cancelled` | 用户取消任务 | `{"cancel_reason": "user_manual"}` |
| `task_recovered` | 恢复引擎接管 | `{"recovery_strategy": "resume_from_last_node"}` |

### 8.4 示例

```json
{"timestamp": "2026-07-31T14:30:25.123", "level": "info", "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "execution_id": "exec-42", "pipeline_name": "get_email", "event": "task_started", "device_id": "BD2-PC", "task_definition_hash": "abc123"}
{"timestamp": "2026-07-31T14:30:28.456", "level": "info", "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "execution_id": "exec-42", "pipeline_name": "get_email", "event": "node_completed", "node_id": "open_mailbox", "node_type": "template_match", "success": true, "elapsed_ms": 172}
{"timestamp": "2026-07-31T14:31:02.789", "level": "error", "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "execution_id": "exec-42", "pipeline_name": "get_email", "event": "task_failed", "error_msg": "节点 wait_regular_email 执行超时", "error_code": "TIMEOUT"}
```

### 8.5 与 agent structured.jsonl 的关系

| 维度 | agent structured.jsonl | backend execution.jsonl |
|------|------------------------|------------------------|
| **视角** | 节点执行内部（coord_transform / 匹配 / 截图） | 任务状态机（派发 / 状态 / 恢复） |
| **写入者** | agent 进程 | backend Django 进程 |
| **关联字段** | `trace_id` + `execution_id` | `trace_id` + `execution_id` |
| **粒度** | 节点级（每次坐标转换、每次节点 start/complete） | 任务级（派发 / 状态变更 / 完成 / 失败） |
| **用途** | 诊断"点击为什么偏" | 诊断"任务为什么没跑 / 为什么卡住 / 恢复策略是否正确" |

AI 调试时通过 `trace_id` 同时读取两端 JSONL，可看到：backend 派发 → agent 执行节点 → backend 收到节点完成回报 → backend 任务状态变更 的完整链路。

## 9. frontend console.jsonl 结构

> C3 (spec 2026-07-30) 新增。前端错误上报（及未来前端主动日志）按页面归集到 `console.jsonl`。

### 9.1 文件路径

```
debug/<YYYYMMDD>/frontend/<safe_page_slug>/HH/console.jsonl
```

- `<safe_page_slug>`：page_slug 经 `_sanitize_page_slug` 处理（最长 40 字符，路径分隔符替换为 `_`）
- `HH`：本地时区小时桶

**为什么按 page_slug 而不是 pipeline 分桶**：
1. 前端错误大多发生在页面交互（表单校验 / 路由 / 渲染），不在 pipeline 执行期间
2. 同一页面可能触发多个 pipeline（Dashboard 快速运行），同一 pipeline 也可能从多个页面触发（TaskEditor 预览 + Dashboard 快速运行）
3. "用户在哪儿遇到问题"是前端 UX 调试最实用的第一刀过滤条件，page_slug 匹配这个心智模型

**实现**：[backend/gaf_core/frontend_logger.py](../../../backend/gaf_core/frontend_logger.py) `FrontendConsoleLogger`

### 9.2 字段定义

每行一条 JSON 对象，必填字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | ISO 8601 | 本地时区 ISO 格式（带毫秒） |
| `level` | str | 日志级别（默认 `error`；未来 `frontend.console` 事件可用 `info`） |
| `trace_id` | str | HTTP 请求级 trace_id（由 TracingMiddleware 注入；匿名访问 / trace_id 未设置时为空） |
| `page_slug` | str | 前端页面 slug（未 sanitize） |
| `event` | str | 事件名（如 `frontend.error`） |

payload 字段（由前端 `reportFrontendError` 上报，合并到顶层）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `trigger` | str | 触发源（`error_boundary` / `page_error_boundary` / `window_error` / `unhandled_rejection`） |
| `message` | str | 错误消息 |
| `stack` | str | 错误堆栈（截断到 2000 字符） |
| `page_url` | str | 发生错误的页面 URL |
| `session_id` | str | 前端会话 ID |
| `error_type` | str | 错误类型（如 `TypeError` / `ReferenceError`） |
| `source` | str | 源文件 URL（window.onerror 上报） |
| `lineno` | int | 行号 |
| `colno` | int | 列号 |
| `user_agent` | str | 浏览器 UA |
| `component_stack` | str | React 组件堆栈（ErrorBoundary 上报） |

### 9.3 触发源（trigger）

| trigger | 触发场景 | 上报入口 |
|---------|---------|---------|
| `error_boundary` | React 根组件 ErrorBoundary 捕获渲染错误 | `ErrorBoundary.componentDidCatch` → `reportFrontendError` |
| `page_error_boundary` | 页面级 PageErrorBoundary 捕获渲染错误 | `PageErrorBoundary.componentDidCatch` → `reportFrontendError` |
| `window_error` | 全局 `window.onerror` 捕获未处理异常 | `window.addEventListener('error')` → `reportFrontendError` |
| `unhandled_rejection` | 全局 `unhandledrejection` 捕获未处理 Promise 拒绝 | `window.addEventListener('unhandledrejection')` → `reportFrontendError` |

### 9.4 示例

```json
{"timestamp": "2026-07-31T14:35:10.456", "level": "error", "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "page_slug": "tasks_pipeline", "event": "frontend.error", "trigger": "error_boundary", "message": "Cannot read properties of undefined (reading 'map')", "stack": "TypeError: Cannot read properties of undefined...\n    at TaskList (TaskList.tsx:42:18)\n    at TaskEditor (TaskEditor.tsx:25:7)", "page_url": "http://localhost:5173/tasks/pipeline/edit/get_email", "session_id": "sess-abc123", "error_type": "TypeError", "component_stack": "    in TaskList\n    in TaskEditor\n    in div\n    in App"}
{"timestamp": "2026-07-31T14:36:22.789", "level": "error", "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "page_slug": "dashboard", "event": "frontend.error", "trigger": "window_error", "message": "Network Error", "stack": "AxiosError: Network Error\n    at XMLHttpRequest.handleErr...", "page_url": "http://localhost:5173/dashboard", "session_id": "sess-abc123", "error_type": "AxiosError", "source": "http://localhost:5173/assets/api-abc.js", "lineno": 42, "colno": 18}
```

### 9.5 与 agent / backend 日志的关系

| 维度 | frontend console.jsonl | backend execution.jsonl | agent structured.jsonl |
|------|------------------------|------------------------|------------------------|
| **记录什么** | 前端渲染错误 / 资源加载失败 / 未处理异常 | 任务派发 / 状态机 / 恢复动作 | 节点执行 / 坐标转换 / 截图 |
| **关联字段** | `trace_id` | `trace_id` + `execution_id` | `trace_id` + `execution_id` |
| **写入者** | backend Django 进程（前端通过 `/api/frontend/error` 上报） | backend Django 进程 | agent 进程 |
| **粒度** | 单次错误事件 | 任务级状态变更 | 节点级执行事件 |
| **用途** | 诊断"用户看到什么错误" | 诊断"任务为什么没跑" | 诊断"点击为什么偏" |

AI 调试时通过 `trace_id` 串联三端：前端报错 → backend 派发 → agent 执行，定位"用户操作 → 前端错误 → 后端处理 → agent 执行"的完整链路。

前端错误上报端点：`POST /api/frontend/error`，返回 204（避免阻塞浏览器），由 [backend/gaf_core/frontend_logger.py](../../../backend/gaf_core/frontend_logger.py) 写入 `console.jsonl`。
