---
summary: GAF vs MaaFramework 对比分析
applies_to: ['architecture', 'design']
key_decisions:
  - 五、设计模式总结
last_updated: 2026-08-17 (s30 确认仍有效)
---

# GAF vs MaaFramework 对比分析

> 版本：3.0 | 日期：2026-05-23

## 对比概述

| 维度 | GAF | MaaFramework |
|------|-----|-------------|
| **定位** | 通用游戏自动化框架（Game Automation Framework） | 通用游戏自动化框架（核心 C++ 实现） |
| **架构** | Agent-Server-Client 三层架构 | Tasker + Controller + Resource 三层 |
| **语言** | Python (Django) + React/TypeScript | C++（跨平台核心）+ 多语言绑定 |
| **目标** | 多游戏自动化 + Web UI + LLM 集成 | 跨语言、跨平台的游戏自动化 SDK |
| **Web UI** | React + Ant Design | ❌（SDK 模式，无内置 UI） |
| **LLM 集成** | 内置（DeepSeek/OpenAI/本地模型） | ❌ |
| **设备支持** | Windows 窗口 + 多模拟器 + Android | Windows + Android |
| **任务定义** | JSON 可序列化定义 | Pipeline JSON 声明式 |

**MaaFramework 核心可借鉴点**：Windows 截图竞速选择（6种方式 + speed_test）、伪最小化（透明+穿透+自动包装+守护线程）、输入三模式（9种变体枚举，鼠标/键盘可独立配置，含 FPS 适配）、Pipeline JSON 完整语法（10种识别 + 18种动作 + 条件分支 + JumpBack栈式回溯 + Anchor）、Batch OCR（mask图合并推理）、WaitFreezes 画面稳定检测（TemplateComparator帧间对比）。

---

以下为 MaaFramework 深度源码分析原文：

# MaaFramework 深度源码分析

## 一、项目概览

- **语言**：C++ 实现，核心逻辑跨平台
- **许可证**：LGPL-3.0
- **核心架构**：三大对象协同工作
  - **Tasker**：任务调度器，管理 Pipeline 的执行生命周期
  - **Controller**：控制层，负责截图与输入操作
  - **Resource**：资源管理器，加载 Pipeline JSON、模板图片、模型文件等
- **API 设计**：纯 C API 导出（`MaaAPI.h`），支持跨语言绑定（Python、C#、Rust 等）
- **模块划分**：
  - `MaaWin32ControlUnit`：Windows 平台控制层
  - `MaaVision`：视觉识别引擎
  - `MaaPipeline`：任务 Pipeline 引擎
  - `MaaUtils`：通用工具库

---

## 二、Windows 控制层 (MaaWin32ControlUnit)

### 2.1 截图降级链

MaaFramework 在 Windows 平台实现了六种截图方式，按优先级与场景灵活选择：

| 截图方式 | 实现原理 | 适用场景 |
|---|---|---|
| **GDI** | `BitBlt` + `CreateCompatibleBitmap` | 通用兼容，性能中等 |
| **FramePool (WGC)** | Windows Graphics Capture API，`Direct3D11CaptureFramePool` | Win10+，高性能前台/后台 |
| **DXGI_DesktopDup** | DXGI Desktop Duplication，`IDXGIOutputDuplication` | 全屏/桌面级截图，GPU 直接获取 |
| **DXGI_DesktopDup_Window** | Desktop Dup + 窗口裁剪 | 全屏模式下的窗口截图 |
| **PrintWindow** | `PrintWindow` API，`PW_RENDERFULLCONTENT` | 后台窗口截图，兼容性好 |
| **ScreenDC** | `GetDC(NULL)` + `BitBlt`，截取整个屏幕 | 兜底方案，DPI 敏感 |

#### 关键发现：伪最小化自动包装

在 `build_screencap_units()` 构建截图单元时，**FramePool 和 PrintWindow 会被自动包装为带伪最小化的版本**：

- `FramePoolScreencap` → `FramePoolWithPseudoMinimizeScreencap`
- `PrintWindowScreencap` → `PrintWindowWithPseudoMinimizeScreencap`

这意味着用户无需手动选择是否启用伪最小化，框架在构建截图链时自动为需要后台截图的方式集成伪最小化支持。

此外，**FramePool 截图方式需要 Win10 SDK 10.0.22000.0+ 编译**，由宏 `MAA_FRAMEPOOL_SCREENCAP_AVAILABLE` 控制。若编译环境不满足 SDK 版本要求，FramePool 截图方式将不可用。

#### 竞速选择机制

核心函数 `speed_test()` 的工作流程：

1. **预热阶段**：对每种候选截图方式执行若干次截图，消除首次调用的初始化开销（如 COM 对象创建、GPU 管线预热）
2. **计时阶段**：对每种方式执行 N 次截图，取平均耗时
3. **选择策略**：选择平均耗时最短的方式作为默认截图方式
4. **位标志组合**：用户通过位或运算（`MaaScreencapMethod` 枚举）指定可接受的截图方式集合，竞速仅在该集合内进行

```cpp
// 用户可自由组合截图方式
MaaScreencapMethod method = MaaScreencapMethod_GDI
                           | MaaScreencapMethod_FramePool
                           | MaaScreencapMethod_DXGI_DesktopDup;
```

#### 伪最小化

`PseudoMinimizeHelper` 的设计目标：让窗口在视觉上"最小化"（用户看不到），但截图仍然能正常工作。

**核心实现细节**：

1. **`start()`**：保存窗口的原始 `ex_style`（扩展窗口样式）和 `alpha`（透明度值），为后续恢复做准备
2. **`ensure_not_minimized()`**：截图前同步调用，检测 `IsIconic(hwnd)` 判断窗口是否处于最小化状态，若是最小化则先恢复窗口再应用伪最小化
3. **`apply_pseudo_minimize()`**：核心伪装操作——添加 `WS_EX_LAYERED | WS_EX_TRANSPARENT` 扩展样式，设置 alpha 为 0 使窗口完全透明，调用 `ShowWindow(SW_SHOWNOACTIVATE)` 保持窗口显示但不激活
4. **`monitor_thread_func()`**：守护线程以 100ms 间隔轮询，检测窗口是否被用户恢复到前台（如点击任务栏），若检测到前台恢复则自动 revert 伪最小化，避免用户看到透明窗口
5. **`stop()`**：析构时先恢复窗口原始 `ex_style` 和 `alpha`，然后再将窗口最小化（`SW_MINIMIZE`），确保退出时窗口状态干净
6. **`inactive()`**：由 FramePool/PrintWindow 的包装类在控制器空闲时调用，恢复伪最小化状态（即让窗口回到真正的最小化），减少资源占用

**关键优势**：真正的 `ShowWindow(SW_MINIMIZE)` 会导致 WGC/GDI 截图返回黑屏或失败，而伪最小化避免了这个问题。守护线程确保用户主动操作窗口时能自动恢复可见性。

### 2.2 输入三模式设计

#### 输入方法枚举值

MaaFramework 定义了 9 种输入方法变体，以位标志枚举实现：

| 枚举值 | 名称 | 说明 |
|---|---|---|
| 1 | **Seize** | 前台输入，`SendInput` + `SetCursorPos` |
| 2 | **SendMessage** | 后台 `SendMessageW` 发送消息 |
| 4 | **PostMessage** | 后台 `PostMessageW` 发送消息 |
| 8 | **LegacyEvent** | 旧版 `mouse_event` / `keybd_event` |
| 16 | **PostThreadMessage** | 已废弃，实现中返回 nullptr |
| 32 | **SendMessageWithCursorPos** | `SendMessage` + `WM_MOUSEMOVE` 携带坐标 |
| 64 | **PostMessageWithCursorPos** | `PostMessage` + `WM_MOUSEMOVE` 携带坐标 |
| 128 | **SendMessageWithWindowPos** | `SendMessage` + 60fps 追踪线程 + `WH_MOUSE_LL` 钩子 |
| 256 | **PostMessageWithWindowPos** | `PostMessage` + 60fps 追踪线程 + `WH_MOUSE_LL` 钩子 |

**鼠标与键盘可使用不同输入方法**：控制器内部维护 `mouse_method_` 和 `keyboard_method_` 两个独立成员，允许鼠标操作使用一种输入方法（如 SendMessageWithWindowPos 适配 FPS 游戏），键盘操作使用另一种（如 SendMessage 简单后台按键），灵活适配不同场景。

#### SeizeInput（前台输入）

- 使用 `SendInput` + `SetCursorPos` 发送输入
- **兼容性最高**：模拟真实硬件输入，几乎所有应用都能接收
- **缺点**：必须在前台操作，用户无法同时使用电脑
- 实现简洁，无额外线程或钩子

#### MessageInput（后台输入）

通过 `SendMessage`/`PostMessage` 向目标窗口发送消息，实现后台操作。提供 4 种变体：

| 变体 | 实现方式 | 适用场景 |
|---|---|---|
| **纯消息** | `PostMessageW(hwnd, WM_xxx, ...)` | 最简单的后台输入 |
| **WithCursorPos** | 消息 + `WM_MOUSEMOVE` 携带坐标 | 需要鼠标坐标的场景 |
| **WithWindowPos** | 60fps 追踪线程 + `WH_MOUSE_LL` 钩子 | FPS/RTS 游戏后台操作 |
| **MouseLockFollow** | RawInput 监听 + 反向位移抵消 | FPS/TPS 游戏鼠标锁定 |

**WithWindowPos 详细机制**：

1. **60fps 追踪线程**：独立线程以 ~16ms 间隔持续向目标窗口发送 `WM_MOUSEMOVE`，保持窗口内鼠标位置同步
2. **`WH_MOUSE_LL` 低级钩子**：拦截硬件鼠标事件，防止真实鼠标移动干扰后台操作
3. **`NtSuspendProcess`**：在关键操作期间挂起目标进程，防止中间态（如鼠标位置未同步时的误判）
4. **坐标转换**：`ScreenToClient` 将屏幕坐标转换为目标窗口客户区坐标

**MouseLockFollow 详细机制**：

1. 专为 FPS/TPS 游戏设计，这类游戏会锁定鼠标到窗口中心
2. **RawInput 监听**：注册 `WM_INPUT` 监听原始鼠标输入，获取相对位移
3. **反向位移抵消**：检测到真实鼠标移动后，立即发送等量反向位移，使游戏内视角不变
4. **操作注入**：在抵消真实输入的同时，注入脚本所需的鼠标移动量

#### LegacyEventInput（旧版输入）

- 使用 `mouse_event` / `keybd_event` 发送输入
- 这些 API 已被微软标记为 deprecated，但兼容老旧系统
- 作为兼容性兜底方案保留

#### BackgroundManagedKeyInput（独立按键守护器）

这不是一个输入后端，而是一个**独立的按键状态守护模块**，在 `Win32ControlUnitMgr` 中对受管按键进行路由短路（拦截并自行处理，不传递给底层输入方法）。

**受管按键域设置**：通过 `MaaCtrlOption_BackgroundManagedKeys` 选项配置需要守护的按键列表。

**守护线程 `guard_loop()`**：

- 以 **5ms 间隔**轮询，维护两个集合：
  - `desired_pressed_keys_`：当前需要保持按下状态的按键集合
  - `release_keys_`：当前需要释放的按键集合
- 每轮轮询中，对 `desired_pressed_keys_` 中的按键确保按下，对 `release_keys_` 中的按键确保释放

**核心技巧 `ensure_key_pressed()`**：

1. **`RegisterHotKey`**：为目标按键注册全局热键，拦截该按键的系统级处理
2. **`SendInput`**：发送按键按下事件，确保按键状态被注入
3. **等待 `WM_HOTKEY` 确认**：在消息循环中等待 Windows 回调 `WM_HOTKEY`，确认按键已被系统接收（200ms 超时）
4. **`UnregisterHotKey`**：确认完成后注销热键，释放系统资源

这一流程确保了后台按键状态可靠——即使窗口切换导致按键被释放，守护线程也能通过 RegisterHotKey + SendInput + WM_HOTKEY 三步确认机制重新建立按键状态。

**Generation 同步机制**：

- `wait_until_applied()`：调用方等待守护线程将 generation 推进到期望值
- 超时为 **500ms**
- 类似乐观锁思想：每次按键操作递增 generation 号，守护线程处理完毕后推进当前 generation，调用方通过比对 generation 确认操作已生效
- 解决异步操作中按键状态丢失的问题（如窗口切换导致按键被释放）

**RAII 管理**：`OnScopeLeave` 确保按键释放和热键注销。

### 2.3 DPI 支持

Windows 的 DPI 缩放是截图坐标映射的常见问题源，MaaFramework 采用了多层 DPI 感知策略：

1. **线程级感知**：`SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)`
   - 在截图和输入操作的线程上设置 Per-Monitor V2 感知
   - 确保获取的坐标和尺寸为物理像素值

2. **进程级兜底**：`SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)`
   - 通过 Windows Shell API 设置进程级 DPI 感知
   - 作为线程级设置的兜底方案

3. **`window_scale()` 计算**：
   ```cpp
   double window_scale(HWND hwnd) {
       UINT dpi = GetDpiForWindow(hwnd);
       return dpi / 96.0;
   }
   ```
   - 基于 `GetDpiForWindow` 获取窗口实际 DPI
   - 返回缩放因子，用于坐标转换

---

## 三、识别引擎 (MaaVision)

### 3.1 模板匹配 (TemplateMatcher)

模板匹配是最基础也最常用的识别方式，MaaFramework 的实现有以下特点：

- **多模板 + 多阈值一一对应**：
  ```json
  {
    "template": ["img1.png", "img2.png", "img3.png"],
    "threshold": [0.8, 0.7, 0.9]
  }
  ```
  每个模板可以设置独立的匹配阈值，任一模板命中即视为识别成功。

- **`method >= 10000` 反转分数逻辑**：
  - OpenCV 的 `matchTemplate` 默认返回的分数，某些方法（如 `TM_SQDIFF`）是越小越好
  - 当 `method >= 10000` 时，框架会反转分数逻辑（`1.0 - score`），使阈值判断统一为"大于阈值则命中"

- **green_mask 绿色掩码过滤**：
  - 模板图像中绿色通道（纯绿 `#00FF00`）的像素被视为掩码
  - 匹配时忽略这些像素，仅对非掩码区域进行匹配
  - 适用于模板中有动态内容（如数字、文字）需要忽略的场景

### 3.2 OCR (OCRer)

基于 [FastDeploy](https://github.com/PaddlePaddle/FastDeploy) 集成 PPOCRv4 模型：

#### 处理流程

```
原图 -> 颜色过滤(可选) -> PPOCRv4 检测+识别 -> trim -> replace -> filter_by_required
```

#### 后处理步骤

1. **trim**：去除识别结果首尾空白字符
2. **replace**：按用户指定的映射表替换字符（如 `O` -> `0`，`l` -> `1`），修正 OCR 常见错误
3. **filter_by_required**：正则过滤，仅保留匹配指定正则的识别结果

#### 颜色过滤

在 OCR 之前对图像进行颜色二值化：

- 用户指定目标颜色范围（HSV 或 RGB）
- 使用 `cv::inRange` 提取目标颜色区域
- 二值化后送入 OCR，减少干扰文字

#### Batch OCR

在 `recognize_list()` 中，如果 next 列表中有多个 OCR 节点使用相同模型，会通过 `prepare_batch_ocr()` 创建 mask 图，将多个 OCR 任务的 ROI 区域合并，一次 OCR 推理获取所有结果：

1. **检测共享**：检测（文本定位）是最耗时的步骤，识别（文字识别）相对较快
2. **mask 图合并**：`prepare_batch_ocr()` 为同模型的多个 OCR 节点创建合并的 mask 图，将各节点的 ROI 区域统一标注
3. **单次推理**：同一截图上的多个 OCR 任务复用一次检测结果，仅分别执行识别后处理
4. **性能收益**：避免了 N 个 OCR 节点各自执行一次完整检测的重复开销

### 3.3 特征点匹配 (FeatureMatcher)

适用于旋转、缩放、仿射变换下的识别：

- **支持的检测器**：SIFT / SURF / ORB / BRISK / KAZE / AKAZE
- **匹配流程**：
  1. 检测关键点和描述子
  2. KNN 匹配（K=2）
  3. **Lowe's ratio test**：最近邻距离 / 次近邻距离 < 阈值（默认 0.7），过滤误匹配
  4. **RANSAC**：从匹配点对中估计仿射/单应变换，剔除离群点
- **输出**：匹配点数、变换矩阵、匹配区域

### 3.4 神经网络推理

通过 ONNX Runtime 支持自定义神经网络模型：

- **分类器（NeuralNetworkClassifier）**：输入图像，输出类别标签和置信度
- **目标检测（NeuralNetworkDetector）**：输入图像，输出检测框和类别，内置 YoloV8 后处理
- **推理设备**：
  - CPU（默认，跨平台）
  - DirectML（Windows GPU 加速）
  - CoreML（macOS GPU 加速）
  - CUDA（NVIDIA GPU 加速）

### 3.5 颜色匹配 (ColorMatcher)

最轻量的识别方式，适用于 UI 元素状态判断：

- 使用 `cv::inRange` 提取指定颜色范围
- **计数模式**：`countNonZero` 统计匹配像素数，与阈值比较
- **连通域模式**：`connectedComponentsWithStats` 分析连通域，获取最大连通域面积和位置
- 支持多颜色范围（`lower` + `upper` 数组一一对应）

---

## 四、Pipeline 任务引擎

### 4.1 PipelineData 核心数据结构

每个 Pipeline 节点由 `PipelineData` 结构描述：

| 字段 | 类型 | 说明 |
|---|---|---|
| `recognition` | enum | 识别类型（10种） |
| `inverse` | bool | 反转识别结果 |
| `action` | enum | 动作类型（18种） |
| `next` | vector\<string\> | 识别命中后跳转的节点列表 |
| `on_error` | vector\<string\> | 识别未命中时跳转的节点列表 |
| `rate_limit` | int | 两次执行的最小间隔（ms） |
| `reco_timeout` | int | 识别超时（ms），超时视为未命中 |
| `pre_delay` | int | 执行动作前延迟（ms） |
| `post_delay` | int | 执行动作后延迟（ms） |
| `pre_wait_freezes` | WaitFreezes | 动作前等待画面稳定 |
| `post_wait_freezes` | WaitFreezes | 动作后等待画面稳定 |
| `repeat` | int | 重复执行次数 |
| `max_hit` | int | 最大命中次数，防止无限循环 |

### 4.2 状态机执行流程

```
Entry Node
    │
    ▼
run_next ──────────────────────────────────────┐
    │                                          │
    ▼                                          │
截图 (Controller->screencap)                   │
    │                                          │
    ▼                                          │
recognize_list (遍历当前节点的识别列表)          │
    │                                          │
    ├── 命中 ──▶ run_action ──▶ next ──────────┘
    │                          │
    │                          └── next 为空且栈非空 ──▶ 弹栈回溯 (JumpBack)
    │
    └── 未命中 ──▶ on_error ──▶ 继续执行 on_error 节点
```

#### JumpBack 栈

JumpBack 使用 `std::stack<string>` 实现，具体流程：

1. 在 `run_next()` 中识别命中节点时，检查该节点的 `jump_back` 属性
2. 若 `jump_back` 为 `true`，则将**父节点名**压入栈中
3. 当 `next` 为空且当前不在错误处理路径且栈非空时，弹栈回溯到上一个 JumpBack 节点
4. **错误处理路径不触发回跳**：走 `on_error` 分支时不会弹栈，确保错误处理逻辑不受 JumpBack 干扰

```json
{
  "Main": {
    "recognition": "DirectHit",
    "jump_back": true,
    "next": ["SubTask1", "SubTask2"]
  },
  "SubTask2": {
    "next": []
  }
}
```

执行流程：`Main`(jump_back=true，压栈"Main") -> `SubTask1` -> `SubTask2`(next为空，弹栈) -> 回到 `Main`

#### Hit Count 限制

- `max_hit` 字段限制单个节点的最大命中次数
- 超过 `max_hit` 后，该节点视为未命中，走 `on_error` 分支
- 防止因识别持续命中导致的无限循环

#### Anchor 锚点

- 某些识别结果（如模板匹配）会输出目标位置
- Anchor 机制将位置信息传递给后续节点
- 后续节点可以基于 Anchor 位置进行相对偏移操作（如点击模板右侧 50 像素处）

### 4.3 Pipeline JSON 完整语法

#### 10 种识别类型

| 识别类型 | 说明 |
|---|---|
| `DirectHit` | 无需识别，直接命中 |
| `TemplateMatch` | 模板匹配 |
| `OCR` | 文字识别 |
| `FeatureMatch` | 特征点匹配 |
| `ColorMatch` | 颜色匹配 |
| `NeuralNetworkClassify` | 神经网络分类 |
| `NeuralNetworkDetect` | 神经网络检测 |
| `Custom` | 自定义识别（回调函数） |
| `And` / `Or` | 逻辑组合 |
| `TemplateComparator` | 模板对比（用于 WaitFreezes 帧间对比） |

#### 18 种动作类型

| 动作类型 | 说明 |
|---|---|
| `DoNothing` | 无操作 |
| `Click` | 点击 |
| `Swipe` | 滑动 |
| `PressKey` | 按键 |
| `InputText` | 输入文本 |
| `StartApp` | 启动应用 |
| `StopApp` | 停止应用 |
| `Custom` | 自定义动作（回调） |
| `WaitFreezes` | 等待画面稳定 |
| ... | 其他复合动作 |

#### 节点生命周期调用顺序

每个 Pipeline 节点执行时，各阶段按以下顺序严格调用：

```
pre_wait_freezes → pre_delay → [action × repeat (repeat_wait_freezes → repeat_delay)] → post_wait_freezes → post_delay
```

- **pre_wait_freezes**：动作前等待画面稳定
- **pre_delay**：动作前固定延迟
- **action × repeat**：动作重复执行 repeat 次，每次执行后依次经过 repeat_wait_freezes 和 repeat_delay
- **post_wait_freezes**：动作后等待画面稳定
- **post_delay**：动作后固定延迟

#### 条件分支

- `next` 列表的**顺序即优先级**
- 框架按顺序尝试识别每个 next 节点，第一个命中的节点成为下一个执行节点
- 实现类似 if-elif-else 的分支逻辑

#### 逻辑组合

- **And（all_of）**：所有子识别器都命中才算命中
- **Or（any_of）**：任一子识别器命中即算命中

```json
{
  "CheckReady": {
    "recognition": "And",
    "all_of": [
      { "recognition": "TemplateMatch", "template": "btn_ready.png" },
      { "recognition": "OCR", "text": ["开始"] }
    ]
  }
}
```

#### WaitFreezes

等待画面稳定，用于处理动画、加载等场景：

```json
{
  "pre_wait_freezes": {
    "threshold": 0.95,
    "timeout": 5000,
    "rate_limit": 500
  }
}
```

- **threshold**：相似度阈值，默认 0.95（即连续两帧相似度 > 0.95 视为稳定）
- **timeout**：最大等待时间（ms）
- **rate_limit**：截图间隔（ms）

**具体实现流程**：

1. 获取目标 ROI 区域
2. 截取第一帧 `pre_image`
3. 进入循环等待，每次等待 `rate_limit` 毫秒
4. 检查是否超时（`timeout`），超时则退出
5. 截取当前帧 `cur_image`
6. 使用 `TemplateComparator` 对比 `pre_image` 和 `cur_image` 在 ROI 区域的相似度
7. **如果没有匹配结果**（帧差异大）：说明画面仍在变化，重置 `pre_image` 为当前帧，重置计时
8. **如果有匹配结果**（帧相似）：且从上次变化开始连续 `time` 毫秒无变化，则认为画面已稳定，退出循环

---

## 五、设计模式总结

### 策略模式

截图方式和输入方式均采用策略模式，通过统一的接口抽象，运行时可互换：

```
ScreencapStrategy ─┬─ GDIScreencap
                   ├─ WGCFramePoolScreencap
                   ├─ DXGIDesktopDupScreencap
                   └─ ...

InputStrategy ─┬─ SeizeInput
               ├─ MessageInput
               └─ LegacyEventInput
```

### 竞速选择

`speed_test()` 对所有候选截图方式进行预热+计时，自动选择最快的方式。避免了硬编码降级链的局限性，适应不同硬件环境。

### 模板方法

`VisionBase` 定义识别流程骨架（截图 -> 预处理 -> 识别 -> 后处理），各具体识别器（TemplateMatcher、OCRer 等）实现各自的识别逻辑。

### 伪最小化

将窗口设为透明+点击穿透，使窗口在视觉上"消失"但截图仍可工作。巧妙绕过了 Windows 对最小化窗口截图的限制。FramePool 和 PrintWindow 在构建时自动包装为带伪最小化版本，守护线程确保用户操作窗口时自动恢复可见性。

### 代次机制

`BackgroundManagedKeyInput` 使用递增代次号同步异步状态，解决后台按键状态不可靠的问题。类似乐观锁的思想，代次不匹配时重试。核心流程为 RegisterHotKey → SendInput → 等待 WM_HOTKEY 确认 → UnregisterHotKey。

### RAII

`OnScopeLeave` 工具类确保 Win32 句柄、钩子、COM 对象等资源的正确释放，避免资源泄漏：

```cpp
OnScopeLeave guard([&]() {
    UnhookWindowsHookEx(hook);
    ReleaseCapture();
});
```

---

## 六、GAF 可借鉴点

| # | 课题 | 当前状态 | 说明 |
|---|------|---------|------|
| 1 | 截图竞速选择机制 | ✅ 已实现 | `benchmark.py` — 竞速测试+自动选最优，可进一步参考MaaFramework的位标志组合方式 |
| 2 | 伪最小化 | ❌ 未实现 | `PseudoMinimizeHelper`：`apply_pseudo_minimize()`添加WS_EX_LAYERED+WS_EX_TRANSPARENT+alpha=0+SW_SHOWNOACTIVATE；`monitor_thread_func()`每100ms轮询检测前台恢复时自动revert；`stop()`析构时恢复窗口状态后再最小化；`inactive()`由FramePool/PrintWindow在控制器空闲时恢复伪最小化；FramePool/PrintWindow在`build_screencap_units()`中自动包装为带伪最小化版本 |
| 3 | MessageInput WithWindowPos 追踪线程 | ✅ 已实现 | `advanced_input.py` — MessageInputFPS + MouseLockFollow + BlockInput |
| 4 | Pipeline JSON 语法的完整性和灵活性 | ✅ 已实现 | `parser.py` — 兼容MaaFramework协议，10种识别类型（含TemplateComparator用于WaitFreezes帧间对比），18种动作类型，缺JumpBack栈式回溯 |
| 5 | WaitFreezes 等待画面稳定机制 | ❌ 未实现 | TemplateComparator帧间对比，ROI区域相似度检测，画面变化时重置计时，连续稳定后退出 |
| 6 | Batch OCR 共享检测结果 | ❌ 未实现 | `prepare_batch_ocr()`创建mask图合并同模型OCR节点的ROI区域，一次推理获取所有结果 |
| 7 | BackgroundManagedKeyInput 按键守护 | ❌ 未实现 | `RegisterHotKey`注册全局热键→`SendInput`发送按键→等待`WM_HOTKEY`确认(200ms超时)→`UnregisterHotKey`；守护线程`guard_loop()`以5ms间隔轮询维护`desired_pressed_keys_`和`release_keys_`；Generation同步：`wait_until_applied()`等待守护线程推进generation(500ms超时) |

> **GAF 已超越 MaaFramework 的能力：**
> 
> | 能力 | GAF | MaaFramework |
> |------|-----|-------------|
> | **AI 分割 (SAM/U²-Net)** | ✅ | ❌ |
> | **录制回放系统** | ✅ | ❌ |
> | **脚本 DSL** | ✅ | ❌ |
> | **模拟器同步** | ✅ | ❌ |
> | **设备插件系统** | ✅ | ❌ |
> | **Pipeline 校验器** | ✅ | ❌ |
> | **OCR 引擎注册表+竞速** | ✅ | ❌ |
> | **图执行引擎 (Graph)** | ✅ PipelineGraph | ❌ 仅线性状态机 |
> | **Web UI** | ✅ React + Ant Design | ❌ SDK无UI |
> | **LLM 集成** | ✅ DeepSeek/OpenAI | ❌ |

---

## 七、跨平台兼容性分析

MaaFramework 是4个对比项目中**唯一原生跨三平台（Windows/macOS/Linux）**的项目，其跨平台架构对 GAF 有直接参考价值。

### 7.1 MaaFramework 跨平台架构

MaaFramework 采用**平台抽象层 + 编译时平台选择**的设计：

| 层次 | 说明 |
|------|------|
| 平台抽象层 | 定义统一的 `Controller` 接口，截图/输入/窗口管理均通过抽象类声明 |
| 编译时选择 | 通过 CMake 预处理器宏（`_WIN32`/`__APPLE__`/`__linux__`）选择具体平台实现 |
| 控制单元分离 | 每个平台独立的 ControlUnit（`MaaWin32ControlUnit`/`MaaMacControlUnit`/`MaaLinuxControlUnit`） |
| 识别/执行层 | MaaVision（识别）和 Pipeline（执行）为纯逻辑层，不依赖任何平台 API |

### 7.2 各平台截图方案

| 平台 | 截图 API | 说明 |
|------|---------|------|
| Windows | DXGI Desktop Duplication / GDI BitBlt / WGC | 已在 GAF 中实现 |
| macOS | CoreGraphics `CGWindowListCreateImage` + IOSurface | 高性能窗口截图，IOSurface 支持 GPU 直接读取 |
| Linux (X11) | X11 `XGetImage` / `XShmGetImage` | XShmGetImage 使用共享内存，性能优于 XGetImage |
| Linux (Wayland) | xdg-desktop-portal `Screenshot` / `ScreenCast` | Wayland 安全模型下需通过 Portal DBus 接口获取截图 |

### 7.3 各平台输入方案

| 平台 | 输入 API | 说明 |
|------|---------|------|
| Windows | SendInput / PostMessage / SendMessage | 已在 GAF 中实现 |
| macOS | `CGEventPost` + `CGEventCreateMouseEvent` / `CGEventCreateKeyboardEvent` | CoreGraphics 事件注入，需辅助功能权限 |
| Linux (X11) | `XTestFakeKeyEvent` + `XSendEvent` | XTest 扩展模拟输入事件 |
| Linux (无X11) | uinput / evdev | 内核级输入设备模拟，不依赖显示服务器 |

### 7.4 对 GAF 的启示

| # | 启示 | 说明 |
|---|------|------|
| 1 | 平台抽象层设计 | MaaFramework 的 `Controller` 抽象 + 编译时选择模式值得 GAF 借鉴，GAF 应定义统一的 `ScreenshotProvider` / `InputController` / `WindowManager` 抽象接口 |
| 2 | 控制单元分离 | 每个平台的控制逻辑应封装为独立模块（如 `windows_control.py` / `macos_control.py` / `linux_control.py`），运行时根据平台自动加载 |
| 3 | P0 阶段定义跨平台接口 | GAF 应在 P0 阶段就定义跨平台抽象接口，即使初期只实现 Windows，也需确保接口设计不绑定 Windows 特有概念（如 HWND） |
| 4 | macOS/Linux 控制单元可直接参考 | MaaFramework 的 `MaaMacControlUnit` 和 `MaaLinuxControlUnit` 实现可作为 GAF 对应平台适配的参考蓝本 |
