---
summary: GAF 坐标转换全链路文档，以模板匹配节点为例，从任务开始到点击落地经历的每一次坐标系变换
status: active
applies_to: ['agent', 'architecture']
key_concepts:
  - 四层坐标系：base / logical / physical / screen
  - 两类转换边界：coord_transformer（节点级） + device.click（输入级）
  - DPI 感知：logical_to_physical_ratio 由 RuntimeDisplayContext 推导
  - trace_id 全链路贯穿：HTTP 请求级 UUID，从 context.emit_coord_trace 注入到每次坐标转换 trace
last_updated: 2026-07-31
---

# GAF 坐标转换全链路

> 版本：2.0 | 日期：2026-07-31 | 关联 spec：`2026-07-30-debug-directory-restructure.md` | 关联硬约束：`env-hardrules-contextual.md` N191 Schema 归一化 / N192 双调试视角

## 1. 为什么需要这份文档

GAF 是「前端编辑器 → backend → agent 执行」三方协作系统，坐标在链路上要经历 **4 层坐标系** 和 **2 类转换边界**。任何一层不归一化都会导致点击偏移（如 BD2 窗口 DPI=150% 时偏左 300+ px）。

本文档以 `resources/BrownDust-II/pipelines/get_email.json` 的 `open_mailbox` 节点为例，完整追踪一次模板匹配从任务开始到点击落地的每一次坐标转换。

## 2. 四层坐标系定义

| 坐标系 | 别名 | 典型来源 | 物理含义 |
|--------|------|---------|---------|
| **base** | 原始基准坐标 | pipeline.json 的 ROI 配置 / 模板图 | 游戏在 1920×1080 分辨率下设计的坐标 |
| **logical** | 逻辑客户区坐标 | coord_transformer 输出 / device.click 入参 | Windows 客户区的逻辑像素（DPI 缩放后） |
| **physical** | 物理客户区坐标 | _logical_to_physical 输出 / ClientToScreen 入参 | Windows 客户区的物理像素（真实像素） |
| **screen** | 屏幕绝对坐标 | ClientToScreen 输出 / SendInput 绝对坐标 | 整个显示器的绝对像素位置 |

### 2.1 为什么有四层而不是两层

- **base ≠ logical**：游戏设计基准是 1920×1080，但窗口可能被拉大到 2560×1440 或缩小到 1280×720，需要按窗口逻辑分辨率缩放
- **logical ≠ physical**：Windows DPI 缩放（150%/200%）下，逻辑像素 1 个 = 物理像素 1.5 个，PostMessage/SendInput 的 API 契约不同
- **physical ≠ screen**：窗口可能不在屏幕左上角，ClientToScreen 负责客户区坐标 → 屏幕绝对坐标的平移

## 3. 全链路转换图（以 open_mailbox 为例）

> **trace_id 贯穿**：下方每次 `记 trace` 的转换步骤都会通过 `context.emit_coord_trace(...)` 写一行 JSONL，并由 A3 (spec 2026-07-30) 从 ContextVar `get_current_user_trace_id()` 注入 HTTP 请求级 trace_id。AI 调试时 `grep <trace_id>` 即可串联同一用户操作链路下的所有坐标转换记录。

```
┌─────────────────────────────────────────────────────────────────────┐
│  pipeline.json (base 坐标)                                          │
│  ROI = [1564, 28, 95, 61]  threshold=0.8  template_id=邮箱.png     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼ 转换① process_roi (base → physical)
┌─────────────────────────────────────────────────────────────────────┐
│  coord_transformer.process_roi                                      │
│  base [1564,28,95,61]                                               │
│    → convert_original_rect_to_current_client (按 logical_res 缩放)  │
│    → logical [1043,19,63,41]                                        │
│    → convert_client_logical_to_physical (× dpi_ratio)               │
│    → physical [1564,28,95,61]  (本例 base 物理恰好等于 base)        │
│  裁剪子图：img[28:89, 1564:1659]                                    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼ 模板匹配（子图内）
┌─────────────────────────────────────────────────────────────────────┐
│  cv2.matchTemplate(sub_img, template_scaled, TM_CCOEFF_NORMED)      │
│  匹配位置（子图坐标）= (15, 9, 38, 29)                              │
│  置信度 = 0.9861                                                    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼ 转换② sub_image_to_full (sub_image → physical)
┌─────────────────────────────────────────────────────────────────────┐
│  coord_transformer.apply_roi_offset_to_subcoord                    │
│  sub (15,9,38,29) + roi_offset_phys (1564,28)                      │
│    → physical (1579, 37, 38, 29)  match_location                    │
│  记 trace: event=coord_transform step=sub_image_to_full             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼ 转换③ get_unified_logical_rect (physical → logical)
┌─────────────────────────────────────────────────────────────────────┐
│  coord_transformer.get_unified_logical_rect                        │
│  physical (1579,37,38,29) ÷ dpi_ratio 1.5                           │
│    → logical (1053,25,25,19)                                        │
│  center = (1053+12, 25+9) = (1065, 34)  逻辑点击坐标               │
│  记 trace: event=coord_transform step=publish_match_pos             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼ publish_match_pos + device.click(logical)
┌─────────────────────────────────────────────────────────────────────┐
│  device.click(1065, 34)  ← 入参是 logical 坐标                      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼ 转换④ _logical_to_physical (logical → physical)
┌─────────────────────────────────────────────────────────────────────┐
│  InputHandler._logical_to_physical                                  │
│  logical (1065, 34) × dpi_ratio 1.5                                 │
│    → physical (1598, 51)                                            │
│  记 trace: event=coord_transform step=logical_to_physical           │
│  ← N191 遗漏点 #3/#4 修复后才有此 trace                             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼ 转换⑤ ClientToScreen (physical → screen)
┌─────────────────────────────────────────────────────────────────────┐
│  Win32 ClientToScreen(hwnd, 1598, 51)                               │
│    → screen (X, Y)  取决于窗口在屏幕的位置                          │
│  SendInput: dx = X * 65535 / screen_w  绝对坐标归一化               │
└─────────────────────────────────────────────────────────────────────┘
```

## 4. 每次转换的代码位置与契约

### 转换① process_roi (base → physical)

- **位置**：`worker/src/utils/coord_transformer.py:274` `process_roi()`
- **调用者**：`TemplateMatchNode._match_with_scaling()` 在匹配前裁剪子图
- **入参**：base ROI `[1564, 28, 95, 61]` + `roi_coord_type=BASE`
- **出参**：physical ROI `(1564, 28, 95, 61)` + `roi_offset_phys=(1564, 28)`
- **中间步骤**：
  1. `convert_original_rect_to_current_client`：base → logical（按 `client_logical_res / original_base_res` 缩放）
  2. `convert_client_logical_to_physical`：logical → physical（× `logical_to_physical_ratio`）
- **trace 记录**：无（此步骤是 ROI 准备，不记 trace）

### 转换② sub_image_to_full (sub_image → physical)

- **位置**：`worker/src/utils/coord_transformer.py:401` `apply_roi_offset_to_subcoord()`
- **调用者**：`TemplateMatchNode._match_with_scaling()` 匹配后还原坐标
- **入参**：子图内匹配位置 `(15, 9, 38, 29)` + `roi_offset_phys=(1564, 28)`
- **出参**：全图物理位置 `(1579, 37, 38, 29)`
- **trace 记录**：✅ `event=coord_transform, step=sub_image_to_full`
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

### 转换③ get_unified_logical_rect (physical → logical)

- **位置**：`worker/src/utils/coord_transformer.py:381` `get_unified_logical_rect()`
- **调用者**：`TemplateMatchNode._match_with_scaling()` 计算点击中心
- **入参**：physical rect `(1579, 37, 38, 29)`
- **出参**：logical rect `(1053, 25, 25, 19)`，center `(1065, 34)`
- **中间步骤**：`convert_client_physical_rect_to_logical`（÷ `logical_to_physical_ratio`）
- **trace 记录**：✅ `event=coord_transform, step=publish_match_pos`
  ```json
  {
    "timestamp": "2026-07-29T16:50:57.760Z",
    "execution_id": "exec-308cd6276342",
    "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "event": "coord_transform",
    "node_id": "open_mailbox",
    "step": "publish_match_pos",
    "device_type": "windows",
    "converted": {"x": 1065, "y": 34, "coord_system": "logical", "confidence": 0.9861},
    "formula": "publish(_last_match_pos) with coord_system=logical",
    "coord_system_out": "logical"
  }
  ```

### 转换④ _logical_to_physical (logical → physical)

- **位置**：`worker/src/platforms/windows/input.py:390` `_logical_to_physical()`
- **调用者**：`_click_sendinput` / `_click_postmessage` / `_swipe_sendinput` / `_swipe_postmessage`
- **入参**：logical 坐标 `(1065, 34)`（来自 `device.click()` 入参）
- **出参**：physical 坐标 `(1598, 51)`
- **公式**：`physical = logical × dpi_ratio`
- **trace 记录**：✅ `event=coord_transform, step=logical_to_physical`（**需要遗漏点 #3 修复后才有**）
  ```json
  {
    "timestamp": "2026-07-29T16:50:57.780Z",
    "execution_id": "exec-308cd6276342",
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
- **N191 遗漏点 #3**：`WindowsDevice` 缺 `set_coord_trace_callback` 转发方法 → callback 不注入 → 此 trace 不记录 → AI 调试黑盒
- **N191 遗漏点 #4**：`_click_postmessage` 没调 `_logical_to_physical` → PostMessage 路径点击偏移
- **N191 遗漏点 #5**：`_swipe_postmessage` 同 #4

### 转换⑤ ClientToScreen (physical → screen)

- **位置**：`worker/src/platforms/windows/input.py:51` `_client_to_screen()`
- **调用者**：`_click_sendinput` 在 `_logical_to_physical` 之后
- **入参**：physical client `(1598, 51)` + hwnd
- **出参**：screen absolute `(X, Y)`（取决于窗口位置）
- **后续**：SendInput 绝对坐标 `dx = X * 65535 / GetSystemMetrics(SM_CXSCREEN)`
- **trace 记录**：无（Win32 API 调用，不记 trace）

## 5. 不同 input_method 的转换差异

| input_method | 转换④ | 转换⑤ | 说明 |
|--------------|-------|-------|------|
| **SendInput** | ✅ `_logical_to_physical` | ✅ `ClientToScreen` | 前台输入，需窗口前台 |
| **PostMessage** | ✅ `_logical_to_physical`（遗漏点 #4 修复后） | ❌ 直接用 physical 作 lParam | 后台输入，不需窗口前台 |
| **PseudoBackground** | ✅ `_logical_to_physical`（通过 `_click_sendinput`） | ✅ `ClientToScreen` | 临时前台 + SendInput |

### 5.1 PostMessage 的特殊性

PostMessage 的 lParam 在 DPI-aware 进程中期望 **physical** client 坐标。修复前（遗漏点 #4）：
- 传入 logical (1065, 34) → 直接作 lParam → PostMessage 期望 physical (1598, 51)
- 点击位置偏左 `1598 - 1065 = 533px`（DPI=150% 时）

修复后：
- 传入 logical (1065, 34) → `_logical_to_physical` → physical (1598, 51) → 作 lParam
- 点击位置正确

## 6. 关键参数推导

### 6.1 logical_to_physical_ratio 怎么来

**位置**：`worker/src/utils/display_context.py` `RuntimeDisplayContext.logical_to_physical_ratio`

```python
@property
def logical_to_physical_ratio(self) -> float:
    if self.is_fullscreen:
        return 1.0  # 全屏模式 logical == physical
    if self.client_logical_width <= 0:
        return 1.0  # 无效逻辑分辨率，退化
    return self.client_physical_width / self.client_logical_width
```

**BD2 实例**：
- `client_physical_width = 1540`（截图宽度）
- `client_logical_width = 1027`（1540 / 1.5）
- `logical_to_physical_ratio = 1540 / 1027 = 1.4995 ≈ 1.5`

### 6.2 orchestrator 如何注入

**位置**：`worker/src/core/orchestrator.py:712-720`

```python
coord_transformer = build_transformer(device, base_res_tuple)
if coord_transformer is not None:
    display_context = coord_transformer.display_context
    dpi_ratio = display_context.logical_to_physical_ratio
    if hasattr(device, "set_dpi_ratio"):
        device.set_dpi_ratio(dpi_ratio)
```

### 6.3 PipelineExecution 如何注入 trace callback

**位置**：`worker/src/engine/pipeline_execution.py:177-184`（N202 拆分: 原 engine.py → pipeline_execution/pipeline_lifecycle/pipeline_node_execution 等模块）

```python
device_for_trace = getattr(self._context, "device", None)
if device_for_trace is not None and hasattr(device_for_trace, "set_coord_trace_callback"):
    device_for_trace.set_coord_trace_callback(self._context.emit_coord_trace)
```

**遗漏点 #3 修复前**：`WindowsDevice` 没有 `set_coord_trace_callback` → `hasattr` 返回 False → callback 不注入 → 转换④不记 trace

**修复后**：`WindowsDevice.set_coord_trace_callback` 转发到 `InputHandler.set_coord_trace_callback` → callback 注入 → 转换④记 trace

### 6.4 trace_id 如何注入到坐标转换 trace（A3 新增）

**位置**：`worker/src/engine/context.py:195-249` `PipelineContext.emit_coord_trace()`

```python
def emit_coord_trace(self, *, node_id, step, raw, converted, formula, ...):
    logger_ref = self.structured_logger
    if logger_ref is None:
        return
    # A3: trace_id 从 ContextVar 取 (HTTP 请求级, 全链路贯穿),
    # 不再用 logger.execution_id (那是 agent 内部 execution_id, 与 HTTP trace_id 是两套体系).
    from core.context_vars import get_current_user_trace_id
    logger_ref.emit_coord_trace(
        node_id=node_id, step=step, ...,
        trace_id=get_current_user_trace_id(),
    )
```

**trace_id 全链路传递路径**：

```
前端 (crypto.randomUUID) → sessionStorage
  → axios 拦截器加 X-Trace-Id header
  → backend TracingMiddleware 读 header → current_trace_id ContextVar
  → WS 帧顶层 trace_id 字段
  → agent handler _dispatch_to_handler 提取 → set_current_user_trace_id(trace_id)
  → context.emit_coord_trace() 从 get_current_user_trace_id() 取
  → 写入 structured.jsonl 每行 coord_transform 事件
```

**trace_id 为空字符串的含义**：CLI / Celery 触发的执行无 HTTP 请求上下文，trace_id 为空字符串，`emit_coord_trace` 传空字符串给 `logger_ref.emit_coord_trace`，logger 端 `if trace_id:` 检查为 False → 省略 `trace_id` 字段。AI 调试时按 "trace_id 字段不存在" 过滤即可识别这类执行。

## 7. 已知限制

### 7.1 monitor/handlers.py 路径未接入 coord_transformer

**位置**：`worker/src/monitor/handlers.py:175,180,295,301,324,329`

弹窗检测、剧情跳过等 monitor 路径直接调用 `device.click(x, y)`，传入的是 base 坐标，没有经过 coord_transformer 转换。DPI>100% 时这些路径的点击位置会偏移。

**影响**：弹窗跳过可能点偏，但不影响主 pipeline 执行。

**建议**：后续将 monitor 路径也接入 coord_transformer，或在 monitor 启动时注入 dpi_ratio。

### 7.2 fallback 动作分发路径无 coord 转换

**位置**：`worker/src/engine/pipeline_node_execution.py:363-372`（fallback 动作分发, 原 engine.py:1496）

```python
device.click(params.get("x", 0), params.get("y", 0))
```

直接透传 params 中的坐标，未经过 coord_transformer。此路径为节点失败后的 fallback 动作分发（recovery 流程），当前仍在用。

## 8. 调试要点

### 8.1 从 JSONL 反推点击位置

遇到点击偏移问题时，按以下步骤从 JSONL 反推：

1. 定位 JSONL 文件路径：`debug/<YYYYMMDD>/agent/<pipeline>/HH/structured.jsonl`（A1 新结构）
2. 可选：用 trace_id 过滤本次用户操作链路的记录（A3 新增），避免被其他并发执行干扰：
   ```powershell
   Select-String -Path 'debug\20260731\agent\get_email\16\structured.jsonl' -Pattern 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
   ```
3. 找 `step=sub_image_to_full` 的记录 → 得到 `converted`（physical match_location）
4. 找 `step=publish_match_pos` 的记录 → 得到 `converted`（logical 点击坐标）
5. 找 `step=logical_to_physical` 的记录 → 得到 `converted`（实际传给 Win32 的 physical 坐标）
6. 对比 step②和 step④的 physical 坐标：
   - 一致 → 点击位置正确，问题在别处
   - 不一致 → 转换④有问题，检查 `dpi_ratio` 是否正确

### 8.2 如果 JSONL 中没有 step=logical_to_physical

说明遗漏点 #3 未修复（`WindowsDevice` 缺 `set_coord_trace_callback`），或 `pipeline_execution.py` 的 `hasattr` 检查失败。此时无法从日志确认实际点击位置，只能加临时 log。

### 8.3 常见偏移模式

| 现象 | 可能根因 |
|------|---------|
| 偏左 300+ px，Y 方向也偏 | `_click_postmessage` 没调 `_logical_to_physical`（遗漏点 #4） |
| 偏移量正好是 DPI 倍数 | `dpi_ratio` 未设置或为 1.0，但实际 DPI>100% |
| 偏移量是固定值 | `ClientToScreen` 的窗口原点不对，或截图有标题栏偏移 |
| X 正确 Y 偏 | 截图包含了标题栏，但坐标计算假设不包含 |

### 8.4 跨端关联同一次点击问题（A1/A3 新增）

当用户反馈"点击偏了"，可通过 trace_id 串联三端日志，确认是 agent 坐标转换问题还是前端配置 / backend 派发问题：

```
1. 前端 console.jsonl 中的 trace_id → 看用户在哪个页面、点了什么按钮
2. backend execution.jsonl 中的 trace_id → 看 backend 派发时 task_definition 是否正确
3. agent structured.jsonl 中的 trace_id → 看坐标转换链路 (本文档 8.1 步骤)
```

trace_id 为空时（CLI / Celery 触发）跳过前端 / backend 步骤，直接看 agent JSONL。

## 9. 相关文档

- [调试日志记录结构](./debug-logging-structure.md) — JSONL 日志的完整字段定义和记录时机
- `docs/business/devices/dpi-coordinate.md` — DPI 坐标系的业务层面说明
- `env-hardrules-contextual.md` N191 — Schema 归一化硬约束
- `env-hardrules-contextual.md` N192 — 双调试视角硬约束
- `docs/specs/2026-07-30-debug-directory-restructure.md` — 调试目录重构 spec（A1/A2/A3 任务来源）
