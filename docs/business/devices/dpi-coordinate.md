---
summary: DPI 坐标系统设计 — 不同 DPI 缩放和分辨率下正确截图/匹配模板/点击目标
applies_to: [agent, backend, frontend, design]
last_updated: 2026-08-01
---

# DPI 坐标系统设计文档

> **applies_to**: agent, backend, frontend
> **last_updated**: 2026-08-01 (N197 更新: 加单Agent多窗口概念、窗口类型表、控制模式说明)
> **status**: ✅ 已实现并验证 (execution_id=74 SendInput, execution_id=79 PseudoBackground)
>
> **N191 更新 (2026-07-27)**: 新增 SUB_IMAGE 坐标系 (§2.1 §11)、ADBCoordinateTransformer 双路径 (§8.3)、sub_image_to_full 语义化方法 (§4.3)、CoordTraceEvent AI 可调试性日志 (§11)、box_coord_system 字段 (§9.5)、validate_capture_resolution 校验 (§9.6)。

## 1. 问题背景

GAF 需要在不同 DPI 缩放和分辨率下正确截图、匹配模板、点击目标。典型场景：

| 场景 | 屏幕分辨率 | DPI 缩放 | 模板来源 | 窗口模式 |
|------|-----------|---------|---------|---------|
| 开发机 | 2560x1600 | 150% (1.5) | 1920x1080 DPI=1 | 窗口化 |
| 标准机 | 1920x1080 | 100% (1.0) | 1920x1080 DPI=1 | 全屏 |
| 4K 机 | 3840x2160 | 200% (2.0) | 1920x1080 DPI=1 | 窗口化 |

**核心矛盾**：
- 模板图片从 1920x1080 DPI=1 截取（BASE 坐标系）
- 游戏窗口化时，图标大小受 DPI 影响（DPI=1.5 时客户区物理像素 1536x864，逻辑尺寸 1024x576）
- 游戏全屏时，DPI 始终为 1（全屏独占渲染绕过 DPI 虚拟化），图标大小不随 DPI 变化
- 截图得到的是物理像素，模板匹配在物理像素层完成
- SendInput 点击需要物理坐标（ClientToScreen 期望物理），PostMessage 需要逻辑坐标（消息 lparam 约定）

### 1.1 Agent/Device 概念澄清

> GAF 的架构是 **单 Agent 多窗口**：一台运行 GAF 的电脑 = 一个 Agent，该电脑上的每个可控窗口 = 一个 Device。Device 模型实际代表的是"窗口"（Window 或 模拟器实例），而非"运行 GAF 的机器"。

**窗口类型与 DPI 行为差异**：

| 类型 | 发现方式 | ADB 序列号 | 能否最小化 | DPI 缩放 | 控制方式 |
|:---:|:---:|:---|:---:|:---|:---|
| **emulator** | EmulatorDiscovery | `127.0.0.1:5555` | ✅ 可最小化 | 无 DPI（ADB 截图直接物理像素） | ADB（不依赖窗口前台） |
| **windows** | WindowDiscovery | - | ❌ 视控制模式而定 | 受系统 DPI 影响（1.0~2.0） | Win32 API（依赖窗口状态） |

**非模拟器窗口的控制模式**（决定 DPI 坐标转换路径）：

| 控制模式 | 窗口要求 | 输入方式 | 坐标转换路径 | 适用场景 |
|---------|---------|---------|-------------|---------|
| **foreground** | 窗口必须在前台 | SendInput | logical→physical→screen | 需要真实输入，抗检测强 |
| **background** | 可被遮挡/最小化 | PostMessage | logical 直接打包 | 可后台操作，效率高 |
| **pseudo_background** | 临时切换到前台 | 混合（SendInput + 前台切换） | logical→physical→screen | 部分操作必须前台的游戏 |

**对 DPI 的影响**：
- 模拟器窗口（emulator）通过 ADB 控制，截图和输入都不依赖窗口前台，`ADBCoordinateTransformer` 做 base→physical 直接缩放（无 DPI 层）
- 非模拟器窗口（windows）受系统 DPI 缩放影响，`CoordinateTransformer` 走完整的 BASE→LOGICAL→PHYSICAL→SCREEN 四层转换
- 详见 [架构文档](../../architecture/overview.md) §4.3 窗口类型与行为

## 2. 5 层坐标模型

```
BASE (参考分辨率, 例如 1920x1080)
  │  scale_x = client_logical_w / orig_w
  ▼
LOGICAL (客户区, DPI 无关)
  │  × dpi_ratio
  ▼
PHYSICAL (客户区像素 = 截图像素)
  │  + client_screen_origin (via ClientToScreen)
  ▼
SCREEN (绝对屏幕坐标, 供 SendInput 使用)

  ───── 同时, PHYSICAL 内部派生 ─────

SUB_IMAGE (ROI 子图局部坐标, 原点=ROI 左上角)
  │  + roi_offset_phys (via sub_image_to_full)
  ▼
PHYSICAL (全图, 模板匹配结果回加偏移)
```

### 2.1 各层定义

| 层级 | 名称 | 含义 | 示例 (DPI=1.5 窗口化) |
|------|------|------|----------------------|
| BASE | 参考分辨率 | pipeline JSON 中定义的 ROI/模板坐标基准 | 1920x1080 |
| LOGICAL | 客户区逻辑坐标 | DPI 无关的客户区坐标，PostMessage 使用此层 | 1024x576 |
| PHYSICAL | 客户区物理像素 | 实际渲染像素，截图和模板匹配使用此层 | 1536x864 |
| SCREEN | 屏幕绝对坐标 | 物理坐标 + 窗口在屏幕上的偏移，SendInput 使用 | 窗口位置相关 |
| SUB_IMAGE | ROI 子图局部坐标 | cv2.matchTemplate / OCR 引擎在 ROI 裁剪子图上的输出, 原点=ROI 左上角 | ROI 内 (10, 20) |

> **N191 §10.10 决策点 3 (2026-07-27)**: SUB_IMAGE 是 PHYSICAL 的内部派生层, 用于显式标注节点 crop 子图后的局部坐标。OCR / template_match / feature_match 在 ROI 子图上工作, 引擎输出的坐标默认是 SUB_IMAGE 坐标, 节点必须通过 `transformer.sub_image_to_full(sub_coord, roi_offset_phys)` 回加 ROI 偏移还原到 PHYSICAL 坐标。本坐标系的存在意义是堵住 "节点 crop 子图后忘了加 ROI 偏移就 publish" 类 bug 的调试盲点 (OCR §10.2 已发生过)。

### 2.2 层级映射公式

```
BASE → LOGICAL:
  scale_x = client_logical_w / base_w
  scale_y = client_logical_h / base_h
  logical_x = round(base_x * scale_x)
  logical_y = round(base_y * scale_y)

LOGICAL → PHYSICAL:
  physical_x = round(logical_x * dpi_ratio)
  physical_y = round(logical_y * dpi_ratio)
  (全屏模式 dpi_ratio = 1.0, logical == physical)

PHYSICAL → SCREEN:
  screen_x = physical_x + client_origin_x
  screen_y = physical_y + client_origin_y
  (通过 Win32 ClientToScreen API 完成)
```

### 2.3 数学抵消关系

template_match 产出 **LOGICAL** 坐标（供 click 接口使用）。SendInput 路径内部再做 LOGICAL→PHYSICAL 转换：

```
匹配阶段:  BASE × scale_x = LOGICAL,  LOGICAL × dpi_ratio = PHYSICAL (匹配)
输出阶段:  PHYSICAL / dpi_ratio = LOGICAL (反向, 供 click)
点击阶段:  LOGICAL × dpi_ratio = PHYSICAL (正向, ClientToScreen)
```

**净效果**: DPI 转换在输出和点击阶段两次抵消，click 坐标在 BASE 缩放后与截图物理像素对齐。这个设计让 click 接口统一接收 LOGICAL 坐标，使 SendInput 和 PostMessage 路径都能使用同一个坐标值。

## 3. 全屏 vs 窗口模式

### 3.1 检测逻辑

`display_builder.py` 通过比较客户区物理尺寸和屏幕分辨率检测全屏：

```python
tolerance = 5  # px
is_fullscreen = (
    abs(client_phys_w - screen_phys_w) < tolerance
    and abs(client_phys_h - screen_phys_h) < tolerance
)
```

### 3.2 全屏模式

| 属性 | 值 | 原因 |
|------|-----|------|
| dpi_ratio | 1.0 | 全屏独占渲染绕过 DPI 虚拟化 |
| logical == physical | 是 | DPI=1, 无缩放 |
| client_origin | (0, 0) | 全屏窗口覆盖整个屏幕 |
| 图标大小 | 不随 DPI 变化 | 游戏在全屏下以原生分辨率渲染 |

### 3.3 窗口模式

| 属性 | 值 | 原因 |
|------|-----|------|
| dpi_ratio | physical / logical | 窗口客户区受 DPI 缩放影响 |
| logical ≠ physical | 否 | DPI>1 时物理像素 > 逻辑像素 |
| client_origin | 窗口位置 | 窗口可在屏幕任意位置 |
| 图标大小 | 随 DPI 变化 | 窗口化时 UI 按 DPI 缩放渲染 |

### 3.4 用户场景示例

**开发机**: 屏幕 2560x1600, DPI=1.5, BD2 窗口化

```
base_res         = (1920, 1080)   # 模板来源
client_logical   = (1024, 576)    # 1024 = 1536 / 1.5
client_physical  = (1536, 864)    # GetClientRect
screen_physical  = (2560, 1600)   # 显示器原生
dpi_ratio        = 1.5            # 1536 / 1024

# 坐标转换示例: BASE (857, 30) 邮箱图标
BASE     (857, 30)
  → LOGICAL  (457, 16)    # 857 * (1024/1920) = 457, 30 * (576/1080) = 16
  → PHYSICAL (686, 24)    # 457 * 1.5 = 686, 16 * 1.5 = 24  (截图中的像素位置)
  → SCREEN   (686+ox, 24+oy)  # 加窗口偏移
```

## 4. ROI 缩放流程

### 4.1 ROI 坐标类型

pipeline JSON 中 ROI 可指定 `roi_coord_type`:

| 类型 | 含义 | 使用场景 |
|------|------|---------|
| `base` (默认) | BASE 坐标系 | 模板从 1920x1080 截取, ROI 也基于此 |
| `logical` | LOGICAL 坐标系 | 手动按客户区逻辑尺寸标注 ROI |
| `physical` | PHYSICAL 坐标系 | 按截图像素直接标注 ROI |

### 4.2 缩放管线

`CoordinateTransformer.process_roi()` 执行完整管线：

```
输入: roi (BASE/LOGICAL/PHYSICAL) + coord_type
  │
  ├─ 1. validate (检查 w/h > 0)
  ├─ 2. mode-adapt
  │    ├─ PHYSICAL → 直接使用
  │    ├─ 全屏模式 → 直接使用 (logical == physical)
  │    └─ BASE/LOGICAL → 转 logical, 裁剪到 client_logical 边界
  ├─ 3. clamp (裁剪到客户区边界)
  ├─ 4. optional expand (debug 模式扩展 ROI 边界)
  │
  ▼
输出: (physical_roi, roi_offset_phys)
  physical_roi = (x, y, w, h) in PHYSICAL 坐标
  roi_offset_phys = (x, y) 偏移量, 用于子图匹配坐标还原
```

### 4.3 子图匹配坐标还原

模板匹配在 ROI 裁剪后的子图上进行，匹配结果需要加 ROI 偏移还原到全图坐标。N191 §10.10 决策点 3 (2026-07-27) 起统一使用语义化方法 `sub_image_to_full`：

```python
# 旧写法 (仍兼容, 但意图不清晰)
match_bbox_phys = transformer.apply_roi_offset_to_subcoord(match_loc, roi_offset_phys)

# 新写法 (推荐, N191 §10.10): 显式标注 SUB_IMAGE → PHYSICAL 转换意图
match_bbox_phys = transformer.sub_image_to_full(match_loc, roi_offset_phys)
```

**双路径一致性**: Windows `CoordinateTransformer` 和 ADB `ADBCoordinateTransformer` 都实现了 `sub_image_to_full`, 节点代码无需 hasattr 分支。该方法内部仅做 sub_coord + roi_offset_phys 加法 (不涉及 DPI / 缩放), 因为 `roi_offset_phys` 已由 `process_roi` 在更早阶段完成 BASE→PHYSICAL 缩放。

**PaddleOCR 4-point 格式**: 当 sub_coord 是 `[[x1,y1], [x2,y2], [x3,y3], [x4,y4]]` 4 点列表时, `sub_image_to_full` 会对每个点加偏移, 然后返回最小外接矩形 `(min_x, min_y, w, h)`。

**CoordTraceEvent**: 节点调用 `sub_image_to_full` 后, 应通过 `context.emit_coord_trace(step="sub_image_to_full", raw=sub_coord, converted=result, coord_system_in="sub_image", coord_system_out="physical")` 记录 trace, 让 AI 调试时能从 JSONL 日志反推偏移是否加对。

## 5. 模板匹配坐标流

### 5.1 完整流程

```
[device.capture_screen()]
  → screen (PHYSICAL 像素, shape = client_physical)

[transformer.process_roi(roi_BASE)]
  → (roi_PHYSICAL, roi_offset_PHYSICAL)

[screen_cropped = screen[roi_PHYSICAL]]

[transformer.calculate_template_scale_ratio(screen_PHYSICAL)]
  → scale_ratio = min(screen_w / base_w, screen_h / base_h)

[cv2.resize(template, template_size * scale_ratio)]
  → template_scaled

[cv2.matchTemplate(screen_cropped, template_scaled)]
  → match_loc (子图坐标)

[match_loc + roi_offset]
  → match_bbox_PHYSICAL (全图物理坐标)

[transformer.get_unified_logical_rect(match_bbox_PHYSICAL)]
  → logical_rect (LOGICAL 坐标)  ← 反向转换

[center = (logical_rect.x + w/2, logical_rect.y + h/2)]
  → center_LOGICAL

[device.click(center_LOGICAL)]
```

### 5.2 为什么输出 LOGICAL 而非 PHYSICAL

click 接口统一接收 LOGICAL 坐标，原因：
1. **PostMessage 兼容**: PostMessage 的 lparam 使用逻辑坐标（Windows 消息模型约定）
2. **接口统一**: SendInput 和 PostMessage 路径使用同一个坐标值，降低复杂度
3. **数学自洽**: SendInput 路径内部做 LOGICAL→PHYSICAL，与匹配阶段的 PHYSICAL→LOGICAL 抵消

## 6. 输入方法 DPI 处理

### 6.1 三种输入方法的坐标需求

| 方法 | 期望坐标 | 原因 |
|------|---------|------|
| SendInput | LOGICAL → 内部转 PHYSICAL | ClientToScreen 期望物理客户区坐标 |
| PostMessage | LOGICAL (直接使用) | WM_LBUTTONDOWN lparam 携带逻辑坐标 |
| PseudoBackground | LOGICAL → 内部转 PHYSICAL | 底层调用 SendInput |

### 6.2 SendInput 路径

```python
# input.py _click_sendinput
phys_x, phys_y = self._logical_to_physical(x, y)      # LOGICAL → PHYSICAL
screen_x, screen_y = _client_to_screen(hwnd, phys_x, phys_y)  # PHYSICAL → SCREEN
abs_x = int(screen_x * 65535 / GetSystemMetrics(0))   # SCREEN → 归一化
abs_y = int(screen_y * 65535 / GetSystemMetrics(1))
# SendInput(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE, abs_x, abs_y)
```

### 6.3 PostMessage 路径

```python
# input.py _click_postmessage
lparam = (y << 16) | (x & 0xFFFF)  # LOGICAL 坐标直接打包
# PostMessageW(hwnd, WM_LBUTTONDOWN, wparam, lparam)
```

### 6.4 PseudoBackground 路径

```python
# input.py _click_pseudo_background
if prev_hwnd == hwnd:
    # Fast-path: 窗口已在前台, 直接 SendInput
    return self._click_sendinput(target, x, y, button)
else:
    # Slow-path: 临时切换前台 → SendInput → 50ms 等待 → 恢复前台
    bring_to_foreground(hwnd)
    result = self._click_sendinput(target, x, y, button)
    time.sleep(0.05)
    _set_foreground_window(prev_hwnd)
```

**Fast-path 设计原因**: 当窗口已在前台时，cursor save/restore 会导致部分游戏（BD2/Unity）取消点击。跳过 cursor 操作使 PseudoBackground 行为与 SendInput 完全一致。

## 7. DPI Bug 案例 (2026-07-12)

### 7.1 症状

DPI=1.5 窗口化下，template_match 匹配成功 (conf=0.9590, center=(857, 30))，但点击位置偏移约 429px，邮箱未打开。

### 7.2 根因

`_click_sendinput` 接收 LOGICAL 坐标 (857, 30)，但未做 LOGICAL→PHYSICAL 转换就直接传给 `ClientToScreen`：

```python
# 修复前 (错误)
screen_x, screen_y = _client_to_screen(hwnd, x, y)  # x=857 是 logical, ClientToScreen 期望 physical
# ClientToScreen(857, 30) → 屏幕 (857+ox, 30+oy)  ← 偏移!
# 正确应为 ClientToScreen(1286, 45) → 屏幕 (1286+ox, 45+oy)
```

DPI=1.5 时, logical (857, 30) 应转为 physical (1286, 45), 差值 (429, 15) 即偏移量。

### 7.3 修复

添加 `_logical_to_physical` 转换层:

```python
# 修复后 (正确)
phys_x, phys_y = self._logical_to_physical(x, y)  # 857→1286, 30→45
screen_x, screen_y = _client_to_screen(hwnd, phys_x, phys_y)
```

### 7.4 验证

- 13 个 DPI 转换单元测试全部通过
- execution_id=74 (SendInput): 9/9 节点成功, 耗时 28.2s
- execution_id=79 (PseudoBackground): 9/9 节点成功, 耗时 12.6s

## 8. Orchestrator DPI 装配

### 8.1 装配流程

```
orchestrator.execute_pipeline(pipeline_json, device)
  │
  ├─ 读取 pipeline_json.metadata.original_base_res (默认 1920x1080)
  │
  ├─ build_transformer(device, base_res)
  │    └─ display_builder.build_display_context(hwnd)
  │         ├─ GetClientRect → client_physical
  │         ├─ get_dpi_scale_factor(hwnd) → dpi_scale
  │         ├─ client_logical = physical / dpi_scale
  │         └─ MonitorFromWindow → screen_physical
  │
  ├─ device.set_dpi_ratio(display_context.logical_to_physical_ratio)
  │    └─ input_handler._dpi_ratio = ratio
  │
  └─ engine.load(coord_transformer, display_context)
       └─ PipelineContext.coord_transformer = transformer
       └─ PipelineContext.display_context = display_context
```

### 8.2 装配时机

- **每次** `execute_pipeline` 调用时重新构建
- 全屏/窗口切换后自动适应（display_context 每次重新计算）
- 无 `metadata.original_base_res` 时, coord_transformer=None, 节点回退到原始像素行为

### 8.3 双路径: Windows vs ADB (N191 §10.7 P0-2, 2026-07-27)

orchestrator 根据 device 类型在两条路径间分发, 两条路径产出**不同**的 `coord_system` 标签, 由 `PipelineContext.coord_system` 字段传递给 `publish_match_pos` / `structured_logger` / `resolve_target`:

```
orchestrator.execute_pipeline(pipeline_json, device)
  │
  ├─ is_windows_device = (getattr(device, "hwnd", None) is not None)
  │
  ├─ Windows 路径 (is_windows_device=True):
  │    ├─ build_display_context(hwnd) → RuntimeDisplayContext
  │    ├─ CoordinateTransformer(display_context=ctx)
  │    └─ coord_system = "logical"  ← transformer 输出 LOGICAL
  │
  └─ ADB 路径 (is_windows_device=False):
       ├─ device.get_resolution() → device_physical_res
       ├─ ADBCoordinateTransformer(
       │     base_res=base_resolution,
       │     device_physical_res=device_phys,
       │   )
       └─ coord_system = "physical"  ← transformer 输出 PHYSICAL
```

**关键差异**:

| 维度 | Windows CoordinateTransformer | ADB ADBCoordinateTransformer |
|------|------------------------------|------------------------------|
| 输入依赖 | hwnd / DPI / 客户区 rect / 屏幕 rect | base_res + device_physical_res |
| 4 层链路 | BASE→LOGICAL→PHYSICAL→SCREEN 全支持 | base→physical 直接缩放 (无 DPI) |
| logical↔physical | DPI 缩放 (非恒等) | 恒等变换 (ADB 无 DPI) |
| `coord_system` 输出 | `"logical"` | `"physical"` |
| `is_fullscreen` | 客户区 vs 屏幕 rect 比较 | 恒为 True (整屏) |
| `validate_capture_resolution` | 比较截图 vs `client_physical_res`（⚠️ 该方法仅 ADB 路径实现；Windows CoordinateTransformer 无此方法，由节点侧校验） | 比较截图 vs `device_physical_res` |

**Fail-fast 行为 (N191 §10.11 D5)**: Windows 设备 hwnd 失效时, `build_display_context` 返回 None, orchestrator 显式抛 `CoordTransformerError` (而不是静默走 ADB 路径导致坐标系不匹配):

```python
if coord_transformer is None and is_windows_device:
    raise CoordTransformerError(
        "Windows build_transformer returned None (hwnd invalid ...)",
        root_cause_category="device",
        missing_field="hwnd/display_context",
        device_id=device_id_str,
        base_resolution=str(base_res),
    )
```

**ADB 路径稳定性 (N191 §10.13)**: ADB 截图降级链 (nemu→scrcpy→droidcast→screencap) 不同方法可能返回不同分辨率截图。OCR / template_match / feature_match / color_detect 节点截图后调用 `transformer.validate_capture_resolution(screen.shape[1::-1])` 校验, 不一致时记 warning + 触发 transformer 重建。

## 9. 新增节点的坐标约定

### 9.1 接收坐标

新增节点从 `PipelineContext` 获取 `coord_transformer`，ROI 使用 BASE 坐标（默认）。

### 9.2 产出坐标

点击/操作坐标应产出 **LOGICAL** 坐标，通过 `transformer.get_unified_logical_rect()` 从 PHYSICAL 反向转换。

### 9.3 截图坐标

`device.capture_screen()` 返回 PHYSICAL 像素。模板匹配在 PHYSICAL 层完成。

### 9.4 ROI 标注

```json
{
  "roi": {"x": 1720, "y": 20, "w": 120, "h": 70},
  "roi_coord_type": "base"
}
```

- `base`: 基于模板来源分辨率 (推荐, 可跨 DPI)
- `logical`: 基于客户区逻辑尺寸 (需知道当前窗口大小)
- `physical`: 基于截图像素 (不可跨 DPI, 不推荐)
- `sub_image`: ROI 子图局部坐标 (仅用于节点内部中间结果, 不应在 pipeline JSON 中出现)

### 9.5 识别节点 result_data 的 coord_system / box_coord_system 字段 (N191 §10.2, 2026-07-27)

识别节点 (OCR / template_match / feature_match / color_detect) 的 `result_data` 必须显式标注坐标系, 避免 AI 调试时混淆:

```python
# OCR 节点示例
result_data = {
    'text': '\n'.join(texts),
    'boxes': boxes_full_image,        # 全图 PHYSICAL 坐标
    'boxes_sub_image': boxes_raw,     # 原始子图 SUB_IMAGE 坐标 (调试用)
    'best_box': best_box_full_image,  # 全图坐标
    'coord_system': coord_system_str, # 'logical' / 'physical' / 'legacy'
    'box_coord_system': coord_system_str,  # boxes 字段的坐标系 (与 coord_system 一致)
    'engine': engine_name,
    'region': region,
}
```

- **coord_system**: 整个 result_data 主坐标系的标签, 由 `PipelineContext.coord_system` 传递 (Windows 路径 = `"logical"`, ADB 路径 = `"physical"`, 老路径无 transformer = `"legacy"`)。
- **box_coord_system**: `boxes` 字段的坐标系标签, 与 `coord_system` 一致。
- **boxes_sub_image**: 保留原始 SUB_IMAGE 坐标供调试 / 单测比对, 不参与下游 publish_match_pos 链路。

### 9.6 截图分辨率校验 (N191 §10.13, 2026-07-27)

识别节点截图后, 应调用 `transformer.validate_capture_resolution(capture_shape)` 校验截图分辨率与 transformer 基线一致:

```python
screen = context.device.capture_screen()
# ADB 截图降级链可能切换方法, 导致分辨率变化
if transformer is not None:
    transformer.validate_capture_resolution(
        (screen.shape[1], screen.shape[0])  # (width, height)
    )
# 不一致时仅记 warning, 不阻断执行 (允许 legacy 路径继续)
```

**为什么必须校验**: ADB 截图降级链 (nemu→scrcpy→droidcast→screencap) 不同方法可能返回不同分辨率。若截图分辨率与 transformer `device_physical_res` 不符, base→phys 缩放比例会错, 所有下游坐标全部偏移。

**为什么非阻断**: 校验失败时只记 warning, 由 orchestrator 后续根据 trace 日志决定是否重建 transformer。节点内部不应自行 raise, 避免阻塞 pipeline。

## 10. 相关文件索引

| 文件 | 职责 |
|------|------|
| `agent/src/utils/coord_transformer.py` | Windows 5 层坐标变换核心 (含 SUB_IMAGE / sub_image_to_full) |
| `agent/src/utils/adb_coord_transformer.py` | ADB 路径坐标变换 (N191 §10.7 P0-2, 2026-07-27 新增) |
| `agent/src/utils/display_context.py` | RuntimeDisplayContext 数据类 (从 platforms/windows/ 迁出) |
| `agent/src/platforms/windows/display_builder.py` | RuntimeDisplayContext 构建 (从 hwnd / DPI / 客户区 rect) |
| `agent/src/platforms/windows/dpi.py` | DPI 缩放检测 |
| `agent/src/platforms/windows/input.py` | 输入处理 + DPI 坐标转换 |
| `agent/src/core/orchestrator.py` | DPI 装配入口 + Windows/ADB 双路径分发 + CoordTransformerError fail-fast |
| `agent/src/core/exceptions.py` | CoordTransformerError 异常类 |
| `agent/src/engine/context.py` | PipelineContext.coord_system + emit_coord_trace 接口 |
| `agent/src/engine/nodes/template_match.py` | 模板匹配坐标流 + CoordTraceEvent |
| `agent/src/engine/nodes/ocr.py` | OCR 坐标流 + box_coord_system 字段 |
| `agent/src/engine/nodes/feature_match.py` | 特征匹配 + CoordTraceEvent + validate_capture_resolution |
| `agent/src/engine/nodes/color_detect.py` | 颜色检测 + CoordTraceEvent + validate_capture_resolution |
| `agent/src/engine/nodes/swipe.py` / `long_press.py` | 动作节点 + device_swipe/device_long_press trace |
| `agent/tests/test_windows_input_dpi_conversion.py` | DPI 转换单元测试 (13 个) |

## 11. AI 可调试性设计 (N191 §10.10 决策点 3, 2026-07-27)

### 11.1 设计目标

让 AI 在出现坐标相关 bug 时, 能从结构化日志 (JSONL) 反推完整转换链路, 定位到具体哪一步偏移加错 / 哪一层坐标系混淆。7 个评估维度:

1. **转换链路可观测性**: 每一次坐标转换都有 trace 日志
2. **错误归因粒度**: CoordTransformerError 携带 root_cause_category / missing_field / device_id 等归因字段
3. **跨设备 schema 统一**: Windows 和 ADB 路径产出结构相同的 result_data (含 coord_system 字段)
4. **bug 现场可重建**: trace 日志含 raw / converted / formula / coord_system_in / out, 单测可重放
5. **坐标系显式标注**: result_data 必须含 coord_system / box_coord_system 字段
6. **SUB_IMAGE 概念显式化**: 节点 crop 子图后必须用 sub_image_to_full 回加偏移 (而非裸加法)
7. **截图分辨率校验**: validate_capture_resolution 在 ADB 路径截图后必跑

### 11.2 CoordTraceEvent 结构

每个 CoordTraceEvent 是一条 JSONL log, 字段:

| 字段 | 类型 | 含义 |
|------|------|------|
| `step` | str | 转换步骤名: `process_roi` / `sub_image_to_full` / `convert_original_to_current_client` / `device_click` / `device_swipe` 等 |
| `raw` | any | 转换前坐标 (tuple/list) |
| `converted` | any | 转换后坐标 (tuple/list) |
| `coord_system_in` | str | 输入坐标系: `base` / `logical` / `physical` / `sub_image` / `screen` |
| `coord_system_out` | str | 输出坐标系 |
| `formula` | str (可选) | 转换公式描述 (如 `"sub + roi_offset_phys = full"`) |
| `device_id` | str (可选) | 关联设备 ID |
| `node_id` | str (可选) | 关联节点 ID |

### 11.3 调试反推示例

假设 OCR 节点点击位置偏移 (差值恰好等于 ROI 偏移), AI 调试流程:

1. 查 JSONL 日志, 过滤 `step=sub_image_to_full` 的 trace
2. 检查 `raw` (sub_coord) + `coord_system_in=sub_image` 是否合理
3. 检查 `converted` (结果) 是否 = `raw + roi_offset_phys`
4. 若 `converted` 等于 `raw` (未加偏移), 定位为 sub_image_to_full 未调用 → 节点 bug
5. 若 `converted` 正确但下游点击仍偏移, 检查 `device_click` trace 的 coord_system_in 是否匹配 (publish_match_pos 写入 logical, 点击应接收 logical)
6. 若 coord_system 不匹配, 定位为 publish_match_pos / resolve_target 链路 bug

### 11.4 CoordTransformerError 归因字段

orchestrator / 节点抛出 CoordTransformerError 时, 必须携带归因字段:

```python
raise CoordTransformerError(
    message,
    root_cause_category="device" | "config" | "screenshot" | "roi",
    missing_field="hwnd" | "display_context" | "device_id" | ...,
    device_id=device_id_str,
    base_resolution=str(base_res),
    device_resolution=str(device_res),
)
```

`root_cause_category` 帮助 AI 判断是设备问题 (hwnd 失效) 还是配置问题 (base_resolution 缺失) 还是截图问题 (分辨率不匹配)。
