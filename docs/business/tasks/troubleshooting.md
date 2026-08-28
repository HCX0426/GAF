---
summary: 任务执行问题排查步骤 — AI 排查任务执行失败时的可复用步骤指南
applies_to: [agent, backend, ops]
last_updated: 2026-08-01
---

# 任务执行问题排查步骤

> **applies_to**: agent, backend, ops
> **last_updated**: 2026-08-01 (N192/N197 更新: 加调试模式确认、结构化日志路径、Celery Worker 排查、agent 测试命令、URL 归一化)
> **purpose**: AI 排查任务执行问题时的可复用步骤指南
> **usage**: 遇到任务执行失败时按本文档步骤排查；排查不出时询问用户；排查完成后检查是否需要补充本文档

## 0. 排查前确认

### 0.1 调试模式是否开启

调试模式（GAF_DEBUG）控制调试截图和结构化日志的输出。排查前确认是否已开启：

```powershell
# 检查根目录 .env 是否设置了 GAF_DEBUG=1
Select-String -Path ".env" -Pattern "GAF_DEBUG"
# 应输出: GAF_DEBUG=1
```

**未开启时的表现**：
- 无结构化日志（`debug/<YYYYMMDD>/agent/<pipeline>/HH/structured.jsonl` 不存在或为空）
- 无标注截图（`debug/.../screenshots/annotated/` 目录不存在）
- 排查时只能靠 agent.log 文本日志

**开启方法**：在根目录 `.env` 中设置 `GAF_DEBUG=1`，重启服务。

### 0.2 相关服务是否正常运行

| 服务 | 检查命令 | 正常状态 |
|------|---------|---------|
| Redis | `redis-cli ping` | 返回 `PONG` |
| Backend (Daphne) | `curl http://localhost:8000/api/v2/` | 返回 JSON（非 502/503） |
| Agent | 检查 agent.log 是否有心跳日志 | 每 10s 有 heartbeat 日志 |
| Celery Worker | 见 §10 | 任务队列正常消费 |

### 0.3 排查原则

1. **先读日志，再下结论** — 不要凭猜测修改代码，先从 agent 日志找到失败点和错误信息
2. **从失败节点开始** — 找到第一个 `success=False` 的节点，向前查原因
3. **逐层排除** — 截图 → 匹配 → 坐标 → 点击 → 等待，按管线顺序逐层检查
4. **验证后修复** — 修复后必须重新执行验证，不能只改代码不测试
5. **穷尽尝试再询问** — 按 §4.8.2 auto-heal 原则，穷尽所有可行方案后才通知用户

## 1. 通用排查流程

### Step 1: 获取执行 ID 和失败信息

```powershell
# 登录获取 token
$body = @{ username='admin'; password='admin123' } | ConvertTo-Json
$r = Invoke-WebRequest -Uri "http://localhost:8000/api/v2/accounts/auth/login/" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
$token = ($r.Content | ConvertFrom-Json).access

# 查看最近的执行记录
$r = Invoke-WebRequest -Uri "http://localhost:8000/api/v2/pipeline/executions/?ordering=-id&page_size=5" -Headers @{Authorization="Bearer $token"} -UseBasicParsing
$r.Content | ConvertFrom-Json | Select-Object -ExpandProperty results | Format-Table id, status, pipeline_name, error_msg -AutoSize
```

记录 `execution_id` 和 `error_msg`。

### Step 2: 读取 agent 日志

```powershell
# 方式 1: 结构化日志 (推荐 — 按节点事件分段, AI 可程序化解析)
# debug/<YYYYMMDD>/agent/<pipeline>/HH/structured.jsonl
# 包含: node.execute.start / coord_transform / node.execute.complete 等事件

# 方式 2: 标注截图 (debug_mode=1 时)
# debug/<YYYYMMDD>/agent/<pipeline>/HH/screenshots/annotated/
# 命名: HHMMSSmmm_<node_id>_<event>_<status>.png

# 方式 3: agent 文本日志
$logFile = "agent/logs/agent.log"

# 搜索关键信息
Select-String -Path $logFile -Pattern "execution_id=<ID>|success=False|ERROR|click_on_match|reconfigured|Auto-heal" | ForEach-Object { $_.Line }
```

**结构化日志快速定位**:
```powershell
# 找到最新 execution 的 JSONL
$latestDir = Get-ChildItem debug/20*/agent/*/ -Directory | Sort-Object Name -Descending | Select-Object -First 1
$jsonl = Join-Path $latestDir.FullName "structured.jsonl"
Write-Host "Latest: $jsonl"

# 查看所有失败节点
Select-String -Path $jsonl -Pattern '"success": false'

# 查看某节点的坐标转换 trace
Select-String -Path $jsonl -Pattern '"node_id": "open_mailbox"' | Select-String -Pattern "coord_transform"

# 查看 execution 总耗时
Select-String -Path $jsonl -Pattern '"event": "node.execute.complete"' | Select-String -Pattern "elapsed_ms"
```

### Step 3: 定位失败节点

从日志中找到:
- `[PIPELINE] 节点执行结果: id=<node_id>, success=False, error_msg=<msg>`
- `[ORCHESTRATOR] Pipeline 执行完成: state=failed`

记录:
- 失败节点 ID 和类型 (template_match / wait / ocr / branch / key_press)
- error_msg 内容
- 前一个成功节点

### Step 4: 按节点类型深入排查

根据失败节点类型，跳转到对应章节:
- [§2 template_match 失败](#2-template_match-失败排查)
- [§3 wait 节点失败](#3-wait-节点失败排查)
- [§4 click 不生效](#4-click-不生效排查)
- [§5 auto-heal 副作用](#5-auto-heal-副作用排查)

## 2. template_match 失败排查

### 症状
- `confidence=0.xxxx, threshold=0.80` (置信度低于阈值)
- `模板匹配失败` 或 `匹配完成(scaled): confidence=0.xxxx`

### 排查步骤

#### 2.1 检查截图方法

```
日志关键行:
  截图方法尝试: method=<method>, hwnd=0x..., shape=(H, W, 3), black_ratio=0.xxx
  截图成功: method=<method>, ...
```

**检查项**:
- [ ] `shape` 是否为窗口客户区尺寸？(如 864x1536 而非 1600x2560)
  - 如果是全屏尺寸 (1600x2560)，说明 DXGI 捕获了整个屏幕而非窗口客户区 → 坐标变换会出错
- [ ] `black_ratio` 是否接近 0？(>0.95 会被拒绝并降级)
  - DXGI 对 GPU 渲染窗口常返回黑屏 → 降级到 GDI 或 PrintWindow
- [ ] 是否有 "截图方法 <method> 失败" 警告？
  - WGC 在某些系统不可用 (RoGetActivationFactory 失败) → 自动降级

**常见问题**:
| 问题 | 原因 | 修复 |
|------|------|------|
| DXGI 返回全屏截图 (1600x2560) | DXGI 捕获整个显示器而非窗口 | 确保用 GDI/PrintWindow 而非 DXGI |
| WGC 初始化失败 | 系统不支持 WGC (Win10 < 1903) | 自动降级到 GDI |
| PrintWindow 返回黑屏 | GPU 渲染窗口 + PrintWindow 不兼容 | 切换到 GDI |

#### 2.2 检查截图尺寸一致性

```
截图成功，屏幕尺寸: (864, 1536)  ← 这是 PHYSICAL 像素 (height, width)
```

**检查项**:
- [ ] 截图尺寸是否与 `display_context.client_physical_res` 一致？
  - 如果不一致，coord_transformer 的坐标变换会出错
- [ ] 截图尺寸是否 = 客户区物理像素？
  - 窗口化 DPI=1.5: 物理 1536x864, 逻辑 1024x576
  - 全屏 DPI=1: 物理 = 逻辑 = 屏幕分辨率

#### 2.3 检查 ROI 缩放

```
应用 scaled ROI: phys=(x,y,w,h), offset=(x, y)
```

**检查项**:
- [ ] `phys` 坐标是否在截图范围内？(x+w <= 截图宽度, y+h <= 截图高度)
- [ ] ROI 是否太小？(w<10 或 h<10 可能匹配不到)
- [ ] ROI 坐标类型 (`roi_coord_type`) 是否正确？(默认 `base`)

#### 2.4 检查模板缩放

```
匹配完成(scaled): method=TM_CCOEFF_NORMED, confidence=0.xxxx, threshold=0.80, loc=(x,y), scale_ratio=0.xxxx, template=47x36→38x29
```

**检查项**:
- [ ] `scale_ratio` 是否合理？(0.5-2.0 之间正常, 太大/太小说明 base_res 配置错误)
- [ ] `template` 缩放后尺寸是否与截图中的目标大小匹配？
- [ ] `confidence` 是 0.0x 还是 0.7x？
  - 0.0x → 完全不匹配, 可能截图错误或模板错误
  - 0.7x → 接近但不达标, 可能是 DPI/分辨率微差或模板过时

#### 2.5 检查 debug 调试图

debug_mode=1 时, 调试图保存在:
```
debug/<YYYYMMDD>/agent/<pipeline>/HH/screenshots/annotated/
  HHMMSSmmm_<node_id>_<event>_<status>.png  ← 标注图（含 ROI 框、匹配框、点击中心）
  HHMMSSmmm_<node_id>_<event>_<status>.jpg  ← 原图（仅识别类节点）
```

**旧格式**（2026-07-31 前）已废弃，不再使用。

**检查项**:
- [ ] 截图中目标是否可见？
- [ ] 蓝色 ROI 框是否覆盖了目标区域？
- [ ] 红色匹配框是否在正确位置？
- [ ] 绿色点击中心是否在目标元素内？
- [ ] 模板缩放后（右侧缩略图）是否与目标大小一致？

## 3. wait 节点失败排查

### 症状
- `wait(ocr): text '<expected>' not found within <N>s`
- `last: OCR text '<actual>' does not contain expected '<expected>'`

### 排查步骤

#### 3.1 检查 OCR 识别结果

```
OCR text '<actual>' does not contain expected '<expected>'
```

**分析**:
- `<actual>` 是主菜单文字 → 前一步的点击没生效 → 跳到 [§4 click 不生效](#4-click-不生效排查)
- `<actual>` 是目标界面的其他文字 → OCR 识别正确但目标文字不在 ROI 内 → 检查 ROI
- `<actual>` 是乱码 → OCR 引擎问题或截图质量问题

#### 3.2 检查截图尺寸

```
截图成功: method=<method>, shape=(H, W, 3)
```

**检查项**:
- [ ] shape 是否为窗口客户区尺寸？(864x1536 而非 1600x2560)
  - DXGI 全屏截图会导致 ROI 偏移, OCR 识别到错误区域
- [ ] 如果是 DXGI 全屏截图 (1600x2560), 说明前一步的 auto-heal 切换了截图方法 → 跳到 [§5 auto-heal 副作用](#5-auto-heal-副作用排查)

#### 3.3 检查 ROI 缩放

```
应用 scaled ROI: phys=(x,y,w,h), offset=(x, y)
```

**检查项**:
- [ ] phys 坐标是否基于正确的截图尺寸？
  - 截图 864x1536 → phys 应在 (0-1536, 0-864) 范围内
  - 截图 1600x2560 → phys 会被错误放大, OCR 识别到错误区域

## 4. click 不生效排查

### 症状
- template_match `success=True`, `click_on_match 已点击: (x, y)` 日志存在
- 但下一步 wait 节点发现 UI 没有变化 (OCR 识别到原界面文字)

### 排查步骤

#### 4.1 确认点击坐标层级

```
click_on_match 已点击: (857, 30)  ← 这是 LOGICAL 坐标
```

**检查项**:
- [ ] 坐标是否为 LOGICAL 层？(应与 coord_transformer 输出一致)
- [ ] 坐标值是否合理？(不应为 0,0 或超出客户区)

#### 4.2 检查输入方法

```
日志关键行:
  Device windows-0 reconfigured: input_method=<method>  ← 当前输入方法
  PseudoBackground fast-path: ...  ← PseudoBackground 快速路径
  PseudoBackground slow-path: ...  ← PseudoBackground 慢速路径
```

**检查项**:
- [ ] input_method 是否正确？(SendInput / PostMessage / PseudoBackground)
- [ ] PseudoBackground 模式下:
  - fast-path: 窗口已在前台 → 等同 SendInput, 应该能工作
  - slow-path: 窗口不在前台 → 检查 bring_to_foreground 是否成功

#### 4.3 检查 DPI 坐标转换

```
display_context: RuntimeDisplayContext[windowed] base=(1920, 1080) logical=(1024, 576) physical=(1536, 864) dpi=1.50
```

**检查项**:
- [ ] `dpi` 是否与系统设置一致？(1.0=100%, 1.25=125%, 1.5=150%, 2.0=200%)
- [ ] SendInput 路径: LOGICAL 坐标是否被正确转换为 PHYSICAL？
  - `_logical_to_physical(857, 30)` → `(1286, 45)` (DPI=1.5)
  - 如果转换缺失, 点击位置会偏移 (857 而非 1286, 偏移 429px)

**验证方法**:
```python
# 在 agent 中运行临时诊断
from platforms.windows.input import WindowsInputHandler
h = WindowsInputHandler(method="SendInput")
h.set_dpi_ratio(1.5)
print(h._logical_to_physical(857, 30))  # 应输出 (1286, 45)
```

#### 4.4 检查窗口前台状态

```powershell
# 检查当前前台窗口 (PowerShell)
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);
}
"@
$hwnd = [Win32]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 256
[Win32]::GetWindowText($hwnd, $sb, 256) | Out-Null
"Foreground: hwnd=$hwnd, title=$($sb.ToString())"
```

**检查项**:
- [ ] BD2 窗口是否在前台？(title 应为 "BrownDust II")
- [ ] 如果不在前台, PseudoBackground slow-path 会尝试切换前台
  - 检查 "bring_to_foreground: ... success=True/False" 日志

#### 4.5 PseudoBackground 特有问题

| 症状 | 原因 | 修复 |
|------|------|------|
| fast-path 但点击无效 | (不应发生, fast-path 等同 SendInput) | 检查 SendInput 路径 |
| slow-path 点击无效 | 50ms 等待不够 / 前台切换失败 | 增加 sleep 时间 / 检查 bring_to_foreground |
| slow-path 后焦点丢失 | 恢复前台太快, 事件竞争 | 确保 50ms 延迟存在 |
| slow-path cursor restore 导致游戏取消点击 | SetCursorPos 后游戏认为鼠标移走 | 使用 fast-path (窗口已在前台时) |

#### 4.6 坐标系混淆 (N191 §10.10, 2026-07-27 新增)

**症状**: 点击位置偏移量恰好等于 ROI 偏移, 或 OCR boxes 与 best_box 不在同一坐标系。

**排查步骤**:

1. **查 result_data 的 coord_system / box_coord_system 字段**:
   - 应为 `"logical"` (Windows) / `"physical"` (ADB) / `"legacy"` (无 transformer)
   - 若为 `"legacy"` 但 base_resolution 已配置, 说明 transformer 装配失败
2. **查 JSONL 日志的 CoordTraceEvent**:
   - 过滤 `step=sub_image_to_full`, 检查 `converted` 是否 = `raw + roi_offset_phys`
   - 若 `converted == raw`, 节点未调用 `sub_image_to_full` → 节点 bug
3. **查 boxes vs best_box**:
   - OCR 节点 `boxes` 应为全图坐标 (PHYSICAL/LOGICAL), `boxes_sub_image` 才是 SUB_IMAGE
   - 若 `boxes[0]` 与 `best_box` 差值恰好等于 ROI 偏移, 定位为 sub_image_to_full 未调用
4. **ADB 路径**: 检查 `validate_capture_resolution` 日志, 截图分辨率与 transformer 基线不符时会有 warning

详细设计见 [dpi-coordinate.md §11 AI 可调试性设计](../devices/dpi-coordinate.md)。

## 5. auto-heal 副作用排查

### 症状
- 第一个节点 (如 open_mailbox) 经历 auto-heal 后成功
- 后续节点 (如 wait_regular_email) 失败, OCR 识别到错误文字
- 截图尺寸从 864x1536 变为 1600x2560

### 排查步骤

#### 5.1 检查 auto-heal 是否切换了截图方法

```
日志关键行:
  Auto-heal: switching device to <method> (conf=0.xxxx), retrying match
  ScreenshotManager method switched: <old> -> <new>
```

**检查项**:
- [ ] 切换后的 `<new>` 方法是否实际可用？
  - WGC 在某些系统不可用 (RoGetActivationFactory 失败)
  - DXGI 对 GPU 渲染窗口返回黑屏或全屏截图
- [ ] 切换后后续截图是否成功？
  - 如果 `method=<new>` 每次都失败再降级, 说明 auto-heal 切换到了不可用的方法

#### 5.2 检查诊断的 fallback 误标记

```
日志关键行:
  Testing method: wgc
  ...WGC 初始化失败...
  截图方法 wgc 失败: WGC 初始化失败
  截图方法尝试: method=dxgi, ... black_ratio=1.000
  截图成功: method=gdi  ← wgc 请求但 gdi 实际执行
```

**检查项**:
- [ ] 是否有 "Method <X> unavailable (fell back to <Y>), marking as unusable" 日志？
  - 如果没有, 说明诊断未检测到 fallback (旧版本 bug)
  - 如果有, auto-heal 不应切换到该方法

**已知问题 (已修复)**:
- 修复前: 诊断请求 wgc, ScreenshotManager 降级到 gdi, 但诊断标记为 "wgc 可用" → auto-heal 切换到 wgc → 后续每次截图都失败降级
- 修复后: 诊断检查 `_best_method != method`, 标记为不可用 → auto-heal 跳过该方法

#### 5.3 检查后续截图尺寸

```
截图成功: method=<method>, shape=(H, W, 3)
```

**检查项**:
- [ ] shape 是否始终为窗口客户区尺寸？(如 864x1536)
  - 如果变为 1600x2560, 说明 DXGI 被选中并捕获了全屏
  - DXGI 全屏截图会导致 coord_transformer 的 ROI 缩放错误

**修复方法**:
- 如果 auto-heal 切换到了有问题的方法, 手动将设备 screenshot_method 改回可用方法
- 通过后端 API: `PATCH /api/v2/agents/devices/<id>/ {"screenshot_method": "gdi"}`

### 5.4 结构化日志排查节点卡住

**症状**: 任务长时间处于 `running` 状态但无步骤进展，agent.log 无新日志输出。

**排查步骤**:

1. **检查结构化日志是否有新事件**:
```powershell
# 查看最新 structured.jsonl 的最后 10 行
Get-ChildItem debug/20*/agent/*/*/structured.jsonl -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 10
```

2. **检查 agent 日志最后的事件**:
```powershell
Select-String -Path "agent/logs/agent.log" -Pattern "execute\.start|execute\.complete|capture_screen|matchTemplate" | Select-Object -Last 10
```

3. **检查 CPU 占用**（卡在截图/匹配时 CPU 应 > 10%）:
```powershell
Get-Process python | Select-Object CPU, WorkingSet, Id
```

4. **常见卡住原因**:
| 原因 | 表现 | 解决方法 |
|------|------|---------|
| 截图方法阻塞 | agent.log 最后一条是 `capture_screen`，CPU 低 | 检查窗口是否被最小化/遮挡 |
| cv2.matchTemplate 卡死 | 模板尺寸过大（> 1000x1000） | 缩小模板尺寸 |
| 窗口句柄失效 | `hwnd` 无效，截图返回 None | 检查窗口是否关闭 |
| 死循环（loop 节点） | 同一节点反复执行 | 检查 loop 的 exit 条件 |
| 设备被其他 execution 占用 | 设备状态为 `busy` | 清理陈旧 execution（见 §12） |

## 6. 设备配置不生效排查

### 症状
- 在后端修改了设备的 input_method / screenshot_method / control_mode
- 但 agent 执行时仍使用旧配置

### 排查步骤

#### 6.1 检查 reconfigure 日志

```
日志关键行:
  Device windows-0 reconfigured: input_method=<method>
```

**检查项**:
- [ ] reconfigure 日志是否出现？(每次 pipeline 执行开始时应有)
- [ ] 配置值是否正确？

#### 6.2 检查设备匹配

```
日志关键行:
  命中已有 Windows 设备: id=windows-0, by=window_title=BrownDust II
```

**检查项**:
- [ ] 是否命中已有设备？(而非创建新设备)
- [ ] 匹配方式是否正确？(window_title / hwnd)

## 10. Celery Worker 排查

### 症状
- 任务提交后一直处于 `pending` 状态，不会被 agent 执行
- 后端 API 返回 201 但 execution 状态不推进

### 排查步骤

#### 10.1 检查 Celery Worker 是否运行

```powershell
# 检查是否有 celery worker 进程
Get-Process python | Where-Object { $_.CommandLine -match "celery" } | Select-Object Id, CommandLine
```

**无输出** = Celery Worker 未启动。

#### 10.2 启动 Celery Worker

```powershell
D:\code\environment\conda\envs\gaf\python.exe -m celery -A config.celery_app worker --loglevel=info --pool=solo -Q celery -n worker1@%COMPUTERNAME%
```

**注意**:
- 使用 `--pool=solo`（Windows 兼容，避免 `OSError: [WinError 87] 参数错误`）
- 队列名 `-Q celery` 必须与 `CELERY_TASK_DEFAULT_QUEUE` 配置一致
- 启动后看到 `celery@<hostname> ready.` 表示成功

#### 10.3 检查 Celery 任务队列

```powershell
# 通过 Redis 检查队列长度
redis-cli -n 0 LLEN celery
# 返回 0 表示队列为空，任务已被消费
# 返回 > 0 表示有任务堆积
```

#### 10.4 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| Celery worker 启动后立即退出 | `--pool` 参数不支持 Windows | 使用 `--pool=solo` |
| 任务一直 pending | Worker 未启动或队列名不匹配 | 启动 worker，检查 `-Q` 参数 |
| Worker 启动成功但不消费 | 路由配置错误（`CELERY_TASK_ROUTES`） | 检查 `config/celery_app.py` 路由配置 |
| `CELERY_TASK_ALWAYS_EAGER=True` 导致死锁 | HTTP 请求等待 celery 任务完成，但 celery 又等 HTTP 请求释放 | 设为 `False`，让 celery 异步执行 |

## 11. Agent 测试命令

### 症状
- 跑 agent 测试非常慢（单测 > 10s）
- 测试无输出或进度的卡住

### 排查步骤

#### 11.1 检查是否是 pytest-django 插件导致

```powershell
# 默认命令（慢，pytest-django 强制加载 Django，单测 12s+）
D:\code\environment\conda\envs\gaf\python.exe -m pytest agent/tests/test_retry.py::TestRetryExhaustion::test_exhausts_and_reraises
# 耗时: ~12.44s

# 禁用 Django 插件（快，2.5min 跑完全部 2154 个测试）
D:\code\environment\conda\envs\gaf\python.exe -m pytest agent/tests/ -p no:django -o addopts=""
# 耗时: ~2.5min（全量）, 0.02s（单测）
```

**根因**: `pyproject.toml` 配置了 `DJANGO_SETTINGS_MODULE = "config.settings.dev"`，pytest-django 插件检测到后强制 `django.setup()`（含 channels Redis 连接超时）。

#### 11.2 正确命令

```powershell
# ✅ 跑所有 agent 测试（推荐）
D:\code\environment\conda\envs\gaf\python.exe -m pytest agent/tests/ -p no:django -o addopts="" -x --durations=10

# ✅ 跑单个测试文件
D:\code\environment\conda\envs\gaf\python.exe -m pytest "agent/tests/test_retry.py" -p no:django -o addopts="" -x --durations=5

# ✅ 跑单个测试用例
D:\code\environment\conda\envs\gaf\python.exe -m pytest "agent/tests/test_retry.py::TestRetryExhaustion::test_exhausts_and_reraises" -p no:django -o addopts="" --durations=5 --no-header

# ✅ 跑 backend 测试（需要 Django，不能加 -p no:django）
D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/
```

## 12. 任务卡在 pending 状态排查

### 症状
- 任务提交后一直 `pending`
- 没有被 agent 执行
- 无 Celery 相关错误日志

### 排查步骤

#### 12.1 检查 execution 并发控制

查看是否有陈旧 execution 占用了设备资源：

```powershell
# 登录
$body = @{ username='admin'; password='admin123' } | ConvertTo-Json
$r = Invoke-WebRequest -Uri "http://localhost:8000/api/v2/accounts/auth/login/" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
$token = ($r.Content | ConvertFrom-Json).access
$headers = @{ Authorization = "Bearer $token" }

# 查看设备上的陈旧 execution
$r = Invoke-WebRequest -Uri "http://localhost:8000/api/v2/tasks/task-executions/?device_id=17&status=running" -Headers $headers -UseBasicParsing
$r.Content | ConvertFrom-Json | Select-Object -ExpandProperty results | Format-Table id, status, created_at, error_msg -AutoSize
```

**如果有多条 `running` 状态的陈旧 execution**，说明之前执行异常结束但状态未清理。

#### 12.2 清理陈旧 execution

```python
# 通过 Python 取消陈旧 execution
import requests
BASE = "http://localhost:8000"
r = requests.post(f"{BASE}/api/v2/accounts/auth/login/", json={"username": "admin", "password": "admin123"}, timeout=10)
token = r.json().get("token") or r.json().get("access")
headers = {"Authorization": f"Bearer {token}"}

# 取消所有 running 状态的 execution
for eid in [142, 143, 144]:  # 替换为实际的陈旧 execution ID
    resp = requests.post(f"{BASE}/api/v2/tasks/task-executions/{eid}/cancel/", headers=headers, timeout=10)
    print(f"Cancel exec {eid}: {resp.status_code}")

# 重置 agent 状态
resp = requests.post(f"{BASE}/api/v2/agents/td010-repro-agent/reset/", headers=headers, timeout=10)
print(f"Reset agent: {resp.status_code}")
```

#### 12.3 检查 agent 是否在线

```powershell
# 查看 agent 在线状态
$r = Invoke-WebRequest -Uri "http://localhost:8000/api/v2/agents/" -Headers $headers -UseBasicParsing
($r.Content | ConvertFrom-Json).results | Format-Table id, name, status, last_heartbeat -AutoSize
```

Agent 状态应为 `online`，`last_heartbeat` 应为最近 30s 内。

#### 12.4 检查设备是否正常

```powershell
# 查看设备状态
$r = Invoke-WebRequest -Uri "http://localhost:8000/api/v2/agents/devices/17/" -Headers $headers -UseBasicParsing
$r.Content | ConvertFrom-Json | Select-Object id, name, status, agent, game_account, game_profile -ExpandProperty agent
```

设备状态应为 `idle`（空闲）或 `running`（执行中）。如果为 `offline`，检查 Agent 是否已同步设备。

## 13. 排查完成后的检查清单

排查完成并修复后, 检查以下项目:

- [ ] **验证修复**: 重新执行 pipeline, 确认所有节点成功
- [ ] **更新文档**: 本次排查是否发现了新的检查步骤？如果有, 添加到本文档
- [ ] **登记教训**: 如果是新的反模式或常见问题, 登记到 `.ai-memory/lessons/`
- [ ] **更新 Y/N 矩阵**: 如果是可检查的模式, 添加到 `.ai-memory/meta/yn-matrices.md`
- [ ] **技术债务**: 如果发现了非本轮范围的问题, 登记到 `docs/archive/tech-debt-README.md`

## 14. 常见问题速查表

| 症状 | 最可能原因 | 排查章节 |
|------|-----------|---------|
| template_match confidence < 0.1 | 截图方法错误 / 截图全黑 | §2.1 |
| template_match confidence ≈ 0.17 | PrintWindow vs GDI 帧时序差异 | §2.1, §2.5 |
| click 后 UI 无变化 | DPI 坐标转换缺失 | §4.3 |
| click 后 UI 无变化 (PseudoBackground) | cursor restore 副作用 | §4.5 |
| wait OCR 找到主菜单文字 | 前一步 click 没生效 | §4 |
| wait OCR 找到错误文字 | 截图尺寸错误 (全屏 vs 客户区) | §3.2, §5.3 |
| 第一个节点成功后续失败 | auto-heal 切换了截图方法 | §5 |
| 配置修改不生效 | reconfigure 未调用 | §6 |
| WGC 初始化失败 | 系统不支持 WGC | §2.1 |
| DXGI 返回黑屏 | GPU 渲染窗口不兼容 | §2.1 |
| 任务一直 pending | Celery Worker 未启动 | §10 |
| 任务 pending 但 Celery 运行 | 陈旧 execution 占用设备 | §12 |
| 任务长时间 running 无进展 | 节点卡住（截图/匹配/死循环） | §5.4 |
| Agent 测试极慢（单测 > 10s） | pytest-django 强制加载 Django | §11 |
| execution 提交后 500 错误 | Celery retry 参数错误 | 检查 tasks.py self.retry() kwargs |
| 设备状态为 busy 但无执行 | 陈旧 execution 未清理 | §12.2 |
| 调试目录为空 | GAF_DEBUG 未设置或未重启 | §0.1 |

## 15. 相关文档

| 文档 | 内容 |
|------|------|
| [调试模式设计](debug-mode-design.md) | GAF_DEBUG 统一配置、双调试视角 |
| [调试日志记录结构](../../architecture/agent/debug-logging-structure.md) | JSONL 日志完整字段定义 |
| [DPI 坐标系统](../devices/dpi-coordinate.md) | 4 层坐标模型、DPI 缩放原理 |
| [坐标转换全链路](../../architecture/agent/coordinate-transform-pipeline.md) | 每次坐标转换的代码位置与公式 |
| [输入模式设计](../ai/input-mode-window-wait.md) | SendInput / PostMessage / PseudoBackground 设计 |
| [架构设计文档](../../architecture/overview.md) | 单Agent多窗口架构、窗口类型表 |
| [URL 拼接归一化](../../../.ai-memory/meta/env-hardrules-contextual.md) | N197 URL 归一化硬约束 |
| [双调试视角硬约束](../../../.ai-memory/meta/env-hardrules-contextual.md) | N192 双调试视角 |
| [调度链路全貌](../../architecture/cross-cutting/dispatch-flow.md) | 调度协调、异常恢复、服务启动顺序、进程唯一性 |
| `.ai-memory/lessons/` | 历史调试教训 |
| `.ai-memory/meta/yn-matrices.md` | Y/N 检查矩阵 |
