---
summary: GAF vs ok-script 对比分析
applies_to: ['architecture', 'design']
key_decisions:
  - 对比概述
last_updated: 2026-08-17 (s30 确认仍有效)
---

# GAF vs ok-script 对比分析

> 版本：3.0 | 日期：2026-05-23

## 对比概述

| 维度 | GAF | ok-script |
|------|-----|-----------|
| **定位** | 通用游戏自动化框架（Game Automation Framework） | 通用游戏自动化框架（原神/崩坏专精） |
| **架构** | Agent-Server-Client 三层架构 | DeviceManager + TaskExecutor + FeatureSet + Config 四模块 |
| **语言** | Python (Django) + React/TypeScript | Python (PyQt6) |
| **目标** | 多游戏自动化 + Web UI + LLM 集成 | 原神/崩坏自动化，桌面 GUI 操作 |
| **Web UI** | React + Ant Design | PyQt6 桌面 GUI |
| **LLM 集成** | 内置（DeepSeek/OpenAI/本地模型） | ❌ |
| **设备支持** | Windows 窗口 + 模拟器（ADB） | Windows 窗口 + 模拟器 |
| **任务定义** | JSON 可序列化定义 | Python 继承体系 (BaseTask) |

**ok-script 核心可借鉴点**：WGC 截图完整 ctypes 实现（D3D11 + WinRT）、BitBlt DC/Bitmap 缓存机制、多子窗口合成（composite_hwnds）、PostMessage 动态子窗口定位、Debug 浮层（OverlayWidget 透明穿透+绘制）、Config 自动持久化 + verify_config、拟人化贝塞尔曲线滑动、OCR 多引擎支持（4引擎）、COCO JSON 标注格式。

---

以下为 ok-script 深度源码分析原文：

# ok-script 深度源码分析

## 一、项目概览

ok-script 是一个基于 Python 和 PyQt6 的通用游戏自动化框架，最初针对原神（Genshin Impact）开发，后扩展支持崩坏：星穹铁道等多款游戏。其核心架构围绕以下四大模块构建：

- **DeviceManager**：设备管理，负责截图方式选择、输入方式选择、窗口查找与状态监控
- **TaskExecutor**：任务执行引擎，管理一次性任务与触发任务的调度与中断
- **FeatureSet**：模板匹配与特征识别，基于 OpenCV 的多尺度模板匹配 + COCO JSON 标注
- **Config**：配置系统，继承 dict 实现自动持久化到 JSON 文件

整体架构采用策略模式与降级链设计，截图模块和输入模块均支持多种实现方式的自动切换，确保在不同运行环境下都能找到可用的方案。

---

## 二、截图模块 (capture_methods)

### 2.1 架构

截图模块采用**策略模式 + 降级链**的架构设计，支持 8+ 种截图方式：

```
BaseCaptureMethod (抽象基类)
    └── BaseWindowsCaptureMethod (Windows 平台通用基类)
            ├── BitBltCapture (BitBlt 截图)
            ├── BitBltRenderFullCapture (PrintWindow 截图)
            ├── ForegroundBitBltCapture (前台桌面截图)
            ├── WGCCapture (Windows Graphics Capture)
            ├── DXGICapture (DXGI Desktop Duplication)
            ├── NemuIpcCapture (MuMu12 IPC 截图)
            ├── BrowserCaptureMethod (Playwright + WGC，后台可用)
            └── ImageCaptureMethod (调试用，从文件读取)
```

- **BaseCaptureMethod**：定义 `do_capture()` 抽象方法，提供 `get_frame()` 统一接口
- **BaseWindowsCaptureMethod**：增加 `hwnd` 属性，绑定目标窗口句柄
- 每种截图方法实现各自的 `do_capture()` 逻辑，返回 numpy 数组（BGR 格式）

### 2.2 BitBlt 截图 (ctypes 完整实现)

BitBlt 是最经典的 Windows 截图方式，ok-script 通过 ctypes 直接调用 Win32 API 实现，并引入了 **DC/Bitmap 缓存机制**以提升性能。

#### DC/Bitmap 缓存机制

缓存按 **hwnd + width + height** 三元组作为缓存键，当三者均未发生变化时，复用已创建的 DC 和 Bitmap 对象，避免重复调用 `CreateCompatibleDC`、`CreateCompatibleBitmap` 等昂贵操作。当检测到 hwnd 或尺寸变化时，调用 `clean_up_bitblt()` 释放旧资源并重新创建；异常发生时也会自动释放缓存对象，防止 GDI 资源泄漏：

```python
class BitBltCtxDummy:
    """BitBlt 缓存上下文，按 hwnd+width+height 缓存"""
    window_dc = None       # GetWindowDC 获取的窗口 DC
    dc_object = None       # SelectObject 返回的原位图对象
    compatible_dc = None   # CreateCompatibleDC 创建的兼容内存 DC
    bitmap = None          # CreateCompatibleBitmap 创建的兼容位图
    cached_hwnd = None
    cached_width = 0
    cached_height = 0
```

#### capture_by_bitblt

核心截图流程：

1. `GetWindowDC(hwnd)` 获取目标窗口的设备上下文
2. `CreateCompatibleDC(hdc)` 创建兼容内存 DC
3. `CreateCompatibleBitmap(hdc, width, height)` 创建兼容位图
4. `SelectObject(hdc_mem, hbitmap)` 选入位图
5. `BitBlt(hdc_mem, 0, 0, width, height, hdc, 0, 0, SRCCOPY)` 执行位块传输
6. `GetDIBits()` 将位图数据拷贝到 numpy 数组

#### capture_desktop_by_bitblt

前台桌面截图方式，使用 `GetDC(0)` 获取整个屏幕的 DC，然后通过 BitBlt 截取目标窗口对应的屏幕区域。此方式要求目标窗口必须在前台可见。

#### composite_hwnds：多子窗口合成

部分游戏（如原神）的渲染区域位于子窗口中，需要将多个子窗口的截图合成为一张完整图像。该功能的关键挑战在于处理 **DPI 缩放差异**——不同子窗口可能具有不同的 DPI 缩放比例：

1. 遍历 `hwnds` 列表（非 EnumChildWindows 枚举），对每个子窗口独立调用 `capture_by_bitblt`，各自拥有独立的 `BitBltCtxDummy` 缓存上下文
2. 对每个子窗口使用 `GetDpiForWindow()` 获取其 DPI 缩放比，计算虚拟化比率 `ratio = m_scaling / w_scaling`
3. 按比率缩小截图尺寸（虚拟化后的逻辑尺寸），再通过 `cv2.resize` 放大回物理分辨率
4. 逐通道像素拷贝合成到最终图像

#### PrintWindow(PW_RENDERFULLCONTENT)

`PrintWindow` 是 BitBlt 的增强版本，通过 `PW_RENDERFULLCONTENT` 标志（值为 2）可以渲染 DirectX/OpenGL 内容。其调用方式与 BitBlt 类似，但使用 `PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)` 替代 `BitBlt`。此方法在某些系统上可能比 BitBlt 稍慢，但兼容性更好。

### 2.3 WGC 截图 (Windows Graphics Capture)

WGC 是 Windows 10 1903+ 引入的现代截图 API，支持后台截图且兼容性最佳。ok-script 通过**纯 ctypes** 实现（非 pythonnet），完全不依赖 pythonnet 或任何第三方 Python 包。

#### 纯 ctypes COM 绑定实现

WGC 的 WinRT 接口通过 `combase.dll` 的 `RoGetActivationFactory` 获取激活工厂，配合自定义 `idldsl` COM 绑定完成所有 WinRT 对象的创建和方法调用。整个实现链路为：

1. `combase.dll` → `RoGetActivationFactory` 获取 WinRT 激活工厂
2. 自定义 `idldsl` 模块定义 COM 接口的 vtable 布局和方法签名
3. 通过 ctypes 直接调用 COM vtable 方法，无需 pythonnet

#### D3D11 ctypes 绑定

WGC 需要 D3D11 设备来创建帧池和处理纹理：

```python
# 创建 D3D11 设备
D3D11CreateDevice(
    None,                          # 默认适配器
    D3D_DRIVER_TYPE_HARDWARE,      # 硬件驱动
    None,                          # 无软件光栅化器
    0,                             # 创建标志
    None,                          # 特性级别（自动选择）
    0,                             # 特性级别数量
    D3D11_SDK_VERSION,             # SDK 版本
    byref(ppDevice),               # 输出 ID3D11Device
    byref(pFeatureLevel),          # 输出特性级别
    byref(ppImmediateContext)      # 输出 ID3D11DeviceContext
)
```

通过 COM vtable 调用 `ID3D11Device` 和 `ID3D11Texture2D` 的方法，实现纹理的创建、拷贝和映射。

#### WinRT 激活工厂创建 CaptureItem

使用 `RoGetActivationFactory` 获取 `GraphicsCaptureItem` 的激活工厂，通过 `IActivationFactory` 创建 `CaptureItem` 实例：

1. `RoInitialize(RO_INIT_MULTITHREADED)` 初始化 WinRT
2. `RoGetActivationFactory()` 获取 `GraphicsCaptureItem` 的工厂
3. 调用工厂的 `CreateFromInterop` 方法，传入窗口句柄
4. 设置 `IsBorderRequired = False` 自动去除黄色边框（需要 Windows Build >= 20348）

#### Direct3D11CaptureFramePool

```python
# 创建帧池
frame_pool = Direct3D11CaptureFramePool.CreateFreeThreaded(
    d3d_device,                    # D3D11 设备
    DXGI_FORMAT_B8G8R8A8_UNORM,   # 像素格式
    2,                             # 缓冲区数量
    size                           # 截图尺寸
)

# 创建捕获会话
session = frame_pool.CreateCaptureSession(capture_item)
session.IsCursorCaptureEnabled = False  # 不捕获光标
session.Start()
```

#### D3D11 纹理到 numpy

WGC 返回的是 D3D11 纹理，需要转换为 numpy 数组：

1. 创建 **Staging 纹理**（`D3D11_USAGE_STAGING`，CPU 可读）
2. `CopyResource()` 将 GPU 纹理拷贝到 Staging 纹理
3. `Map()` 映射 Staging 纹理到系统内存
4. `np.ctypeslib.as_array()` 将映射的内存指针转为 numpy 数组
5. `Unmap()` 释放映射

#### 帧池回调

使用 `frame_arrived_callback` 回调机制接收新帧通知，避免轮询开销：

```python
def frame_arrived_callback(frame_pool, *args):
    frame = frame_pool.TryGetNextFrame()
    if frame:
        # 处理帧数据
        process_frame(frame)
```

### 2.4 DXGI Desktop Duplication

基于 `d3dshot` 库实现的 DXGI Desktop Duplication 截图方式。DXGI 是 DirectX Graphics Infrastructure 的缩写，提供了桌面复制的底层 API：

- 使用 `IDXGIOutputDuplication` 接口获取桌面帧
- 支持 GPU 直接处理，避免 CPU-GPU 数据传输
- 速度较慢，但兼容性中等
- 不支持后台截图

### 2.5 NemuIpc 截图

MuMu12 模拟器专用截图方式，通过 MuMu 的 `external_renderer_ipc.dll` 实现高性能截图和输入：

```python
# 连接模拟器实例
nemu_connect(instance_id)

# 截图
nemu_capture_display(
    connection,                    # 连接句柄
    display_id,                    # 显示器 ID
    width,                         # 截图宽度
    height,                        # 截图高度
    byref(buffer_size),            # 缓冲区大小
    buffer                         # 像素数据缓冲区
)

# 触摸输入
nemu_input_event_touch_down(connection, display_id, x, y)
nemu_input_event_touch_up(connection, display_id)
```

特点：
- 速度极快（直接内存共享）
- 仅支持 MuMu12 模拟器
- 支持后台操作
- 同时支持触摸输入（无需 ADB）

### 2.6 降级链机制

当首选截图方式不可用时，自动降级到其他可用方式：

```python
def update_capture_method(self):
    # 按优先级遍历方法列表
    for method_name in self.capture_method_priority:
        method = self.capture_methods.get(method_name)
        if method and method.is_available():
            self.selected_method = method
            return
    # 所有方法均不可用，回退到 ADB
    self.selected_method = self.capture_methods.get('adb')
```

- 优先级由配置文件 `capture_method_priority` 决定
- `selected_method` 优先尝试用户选择的方式
- 每种方法实现 `is_available()` 自检方法
- 最终兜底为 ADB 截图（兼容性最高但速度最慢）

### 2.7 截图方法对比表

| 方法 | 速度 | 兼容性 | 后台支持 | 关键技术 |
|------|------|--------|---------|---------|
| BitBlt | 最快 | 最低(不支持DX) | 否 | GetWindowDC + BitBlt |
| BitBlt_RenderFull | 快 | 中(PrintWindow) | 否 | PrintWindow(PW_RENDERFULLCONTENT) |
| ForegroundBitBlt | 最快 | 最低(需前台) | 否 | GetDC(0) 桌面BitBlt |
| WGC | 快 | 最高 | 是 | WinRT Graphics.Capture + D3D11 |
| DXGI | 慢 | 中 | 否 | d3dshot库 |
| ADB | 最慢(~300ms) | 最高 | 是 | adb screencap |
| NemuIPC | 快 | 仅MuMu12 | 是 | external_renderer_ipc.dll |
| Browser | 快 | 高(需Playwright) | 是 | Playwright + WGC，后台可用 |
| Image | - | - | - | 调试用，从文件读取 |

---

## 三、输入模块 (interaction_methods)

### 3.1 PostMessageInteraction

后台输入方式，通过 `PostMessage` / `SendMessage` 向目标窗口发送输入消息，无需窗口在前台：

#### 鼠标输入

```python
# 鼠标左键按下
PostMessage(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
# 鼠标左键释放
PostMessage(hwnd, WM_LBUTTONUP, 0, lparam)
```

其中 `lparam` 编码了坐标信息：`y << 16 | x`

#### 键盘输入

```python
# 按键按下
PostMessage(hwnd, WM_KEYDOWN, vk_code, lparam)
# 按键释放
PostMessage(hwnd, WM_KEYUP, vk_code, lparam)
```

`lparam` 的构造使用 `make_lparam` 函数：

```python
def make_lparam(vk_code, repeat_count=1):
    scan_code = MapVirtualKey(vk_code, MAPVK_VK_TO_VSC)
    return (scan_code << 16) | repeat_count
```

- 扫描码左移 16 位
- 重复计数默认为 1

#### 动态子窗口定位

游戏窗口通常包含多个子窗口（如渲染区域、控制面板等），直接向父窗口发送点击消息可能无法正确路由。ok-script 在 `update_mouse_pos` 中通过 `ClientToScreen` 将客户端坐标转换为绝对屏幕坐标，再遍历 `hwnds` 列表找到包含该坐标的子窗口，自动切换 PostMessage 目标：

```python
def update_mouse_pos(self, x, y):
    """通过 ClientToScreen 转绝对坐标，遍历 hwnds 找到目标子窗口"""
    abs_x, abs_y = ClientToScreen(self.hwnd, x, y)
    for child_hwnd in self.hwnds:
        rect = GetWindowRect(child_hwnd)
        if point_in_rect(abs_x, abs_y, rect):
            self.target_hwnd = child_hwnd
            return
    self.target_hwnd = self.hwnd
```

#### try_activate 激活窗口

在执行操作前，`try_activate` 方法发送 `WM_ACTIVATE` 消息激活目标窗口，确保窗口能正确接收后续的输入消息：

```python
def try_activate(self):
    """操作前发送 WM_ACTIVATE 消息激活窗口"""
    PostMessage(self.hwnd, WM_ACTIVATE, WA_ACTIVE, 0)
```

#### BlockInput 阻止用户输入

在执行自动化操作时，调用 `BlockInput(True)` 阻止用户的键盘和鼠标输入，防止干扰自动化流程。操作完成后调用 `BlockInput(False)` 恢复。

### 3.2 GenshinInteraction（原神专用）

原神专用输入方式，使用 `SendInput` 实现相对鼠标移动：

#### SendInput 相对鼠标移动

```python
# 构造 MOUSEINPUT 结构体
mouse_input = MOUSEINPUT()
mouse_input.dx = delta_x
mouse_input.dy = delta_y
mouse_input.dwFlags = MOUSEEVENTF_MOVE
# 发送输入
SendInput(1, byref(input), sizeof(INPUT))
```

#### 前台/后台自动切换

由于 `SendInput` 需要目标窗口在前台，ok-script 实现了前台/后台自动切换机制：

**后台模式操作流程：**
1. **activate**：激活目标窗口到前台
2. **BlockInput(True)**：阻止用户的键盘和鼠标输入，防止干扰自动化流程
3. **执行操作**：通过 SendInput 发送鼠标/键盘输入
4. **deactivate**：操作完成后恢复原窗口
5. **恢复光标位置**：`SetCursorPos(saved_pos)` 恢复操作前的光标位置
6. **BlockInput(False)**：恢复用户输入

**相对鼠标移动**使用 SendInput 的 `MOUSEINPUT` 结构体实现 dx/dy：

```python
mouse_input = MOUSEINPUT()
mouse_input.dx = delta_x
mouse_input.dy = delta_y
mouse_input.dwFlags = MOUSEEVENTF_MOVE
SendInput(1, byref(input), sizeof(INPUT))
```

整个过程在极短时间内完成（通常 < 50ms），用户几乎感知不到窗口切换。

### 3.3 拟人化滑动

为了模拟真实用户的滑动操作，ok-script 实现了基于**三次贝塞尔曲线**的拟人化滑动算法：

#### 三次贝塞尔曲线轨迹

```python
def bezier_slide(p0, p1, p2, p3, num_points):
    """三次贝塞尔曲线：P(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3"""
    points = []
    for i in range(num_points):
        t = i / (num_points - 1)
        x = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
        y = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
        points.append((int(x), int(y)))
    return points
```

#### 随机控制点

两个中间控制点 P1、P2 在直线路径的基础上添加随机偏移。P1 的计算方式为 `p1 = 2/3*p0 + 1/3*p3 + random_theta()*random_rho(distance*0.1)`，即在起终点连线的 2/3 处添加随机角度和随机距离（约为总距离的 10%）的偏移，使每次滑动轨迹都不同：

```python
offset = distance * 0.1
p1 = (2/3*p0[0] + 1/3*p3[0] + random_theta()*random_rho(offset),
      2/3*p0[1] + 1/3*p3[1] + random_theta()*random_rho(offset))
p2 = (1/3*p0[0] + 2/3*p3[0] + random_theta()*random_rho(offset),
      1/3*p0[1] + 2/3*p3[1] + random_theta()*random_rho(offset))
```

#### 非均匀参数 t

参数 t 的分布采用**先 sin 映射再幂函数**的变换：`abs(t)^0.9`，使得滑动在**起始和结束阶段密集**（速度慢），**中间阶段稀疏**（速度快），更符合人类操作习惯：

```python
# sin 映射 + 幂函数变换：两端密集、中间稀疏
t_values = np.linspace(0, 1, num_points)
t_values = np.sin(t_values * np.pi / 2)  # sin 映射
t_values = np.abs(t_values) ** 0.9        # 幂函数变换
```

#### Box.relative_with_variance

在目标区域内添加随机偏移，避免每次都点击完全相同的位置：

```python
def relative_with_variance(self, variance=0.1):
    """在框内随机偏移，variance 控制偏移幅度"""
    offset_x = self.width * variance * (random.random() * 2 - 1)
    offset_y = self.height * variance * (random.random() * 2 - 1)
    return (self.center_x + offset_x, self.center_y + offset_y)
```

---

## 四、OCR 模块

ok-script 支持 4 种 OCR 引擎，可根据环境和需求灵活选择：

### 4.1 PaddleOCR

百度开源的 OCR 引擎，支持中英文识别：

- 使用 `paddleocr` Python 包
- 支持检测 + 识别两阶段
- 可选 GPU 加速（CUDA）

### 4.2 DGOCR

自定义轻量级 OCR 引擎，针对游戏场景优化：

- 专注于游戏内文字识别
- 模型体积小，推理速度快
- 使用 **DirectML GPU 加速**，兼容所有 Windows GPU（NVIDIA/AMD/Intel）

### 4.3 ONNXPaddleOcr

将 PaddleOCR 模型转换为 ONNX 格式运行：

- 使用 `onnxruntime` 推理
- 无需安装 PaddlePaddle 框架
- 支持 **NPU 加速**（Intel NPU）
- 支持 **OpenVINO** 推理后端

### 4.4 RapidOCR

基于 PaddleOCR 的轻量封装：

- 使用 `rapidocr_onnxruntime` 包
- 安装简单，依赖少
- 适合快速部署

### 4.5 OCR 结果修正

OCR 识别结果经过 `fix_texts()` 多层修正处理：

1. **繁简转换**：使用 `opencc` 将繁体中文转为简体
2. **gettext 翻译**：通过 `gettext` 进行游戏专有名词翻译（如角色名、地名）
3. **自定义修正字典**：针对常见误识别进行替换

```python
def fix_texts(texts):
    """多层 OCR 结果修正：opencc 繁简转换 → gettext 翻译 → 自定义修正字典"""
    for i, text in enumerate(texts):
        text = opencc_convert(text)           # 繁简转换
        text = gettext_translation(text)      # gettext 翻译
        text = apply_correction_dict(text)    # 自定义修正字典
        texts[i] = text
    return texts
```

### 4.6 GPU 加速

自动检测 CUDA 12+ 环境，启用 GPU 加速：

```python
def check_cuda_available():
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False
```

---

## 五、模板匹配模块 (FeatureSet)

### 5.1 COCO JSON 标注格式

ok-script 使用 COCO JSON 格式管理模板标注数据：

```json
{
    "images": [{"id": 1, "file_name": "screenshot.png", "width": 1920, "height": 1080}],
    "annotations": [
        {
            "id": 1,
            "image_id": 1,
            "category_id": 1,
            "bbox": [x, y, width, height],
            "area": 12345
        }
    ],
    "categories": [{"id": 1, "name": "button_confirm"}]
}
```

#### compress_coco() 打包合成

`compress_coco()` 将多张标注图合成为打包图，减少文件数量：

1. **按尺寸分组**：将尺寸相近的标注图归为同一组
2. **冲突检测**：检查打包图中各标注区域是否重叠冲突
3. **canvas 拼贴**：在一张大 canvas 上拼贴多张标注图，调整 annotations 的坐标偏移
4. **输出打包 COCO JSON**：合并后的 images 和 annotations 写入单一 JSON

### 5.2 find_one_feature 查找流程

```python
def find_one_feature(self, feature, screenshot, threshold=0.8):
    # 1. ROI 裁剪：只搜索特征所在区域
    roi = crop_roi(screenshot, feature.roi)

    # 2. 预处理：灰度化或 Canny 边缘检测
    if feature.preprocess == 'canny':
        roi = cv2.Canny(roi, 50, 150)
        template = cv2.Canny(feature.image, 50, 150)
    else:
        roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        template = cv2.cvtColor(feature.image, cv2.COLOR_BGR2GRAY)

    # 3. 缩放：支持多尺度匹配
    for scale in feature.scales:
        scaled_template = cv2.resize(template, None, fx=scale, fy=scale)
        result = cv2.matchTemplate(roi, scaled_template, cv2.TM_CCOEFF_NORMED)
        # 4. 阈值过滤
        if result.max() >= threshold:
            return True

    return False
```

### 5.3 NMS 去重

`filter_and_sort_matches` 使用非极大值抑制（NMS）去除重叠的匹配结果：

```python
def filter_and_sort_matches(matches, iou_threshold=0.5):
    # 按置信度降序排列
    matches.sort(key=lambda m: m.confidence, reverse=True)
    kept = []
    for match in matches:
        if not any(iou(match, k) > iou_threshold for k in kept):
            kept.append(match)
    return kept
```

### 5.4 Feature/Box 类

```python
class Box:
    x: int          # 左上角 x
    y: int          # 左上角 y
    width: int      # 宽度
    height: int     # 高度
    confidence: float  # 置信度
    name: str       # 特征名称

class Feature:
    name: str           # 特征名称
    image: np.ndarray   # 模板图像
    roi: tuple          # 搜索区域
    threshold: float    # 匹配阈值
    scales: list        # 缩放比例列表
    preprocess: str     # 预处理方式（gray/canny）
```

---

## 六、配置系统

### 6.1 Config 类

Config 类继承自 `dict`，实现了自动持久化到 JSON 文件的功能：

```python
class Config(dict):
    def __init__(self, config_path):
        self._path = config_path
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                super().__init__(json.load(f))
        else:
            super().__init__()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._save()

    def _save(self):
        with open(self._path, 'w', encoding='utf-8') as f:
            json.dump(dict(self), f, indent=4, ensure_ascii=False)
```

#### verify_config

配置验证方法，确保配置文件与代码定义一致：

1. **删除多余键**：配置文件中存在但代码未定义的键将被移除
2. **补充缺失键**：代码定义但配置文件中缺失的键将使用默认值填充
3. **类型检查**：验证配置值的类型是否与定义一致，不一致则重置为默认值

```python
def verify_config(self, config_options):
    # 删除多余键
    defined_keys = {opt.name for opt in config_options}
    for key in list(self.keys()):
        if key not in defined_keys:
            del self[key]

    # 补充缺失键 + 类型检查
    for opt in config_options:
        if opt.name not in self:
            self[opt.name] = opt.default
        elif not isinstance(self[opt.name], type(opt.default)):
            self[opt.name] = opt.default
```

### 6.2 GlobalConfig 完整设置项

#### Basic Options

| 设置项 | 默认值 | 说明 |
|--------|--------|------|
| auto_start | False | 自动启动任务 |
| minimize_to_tray | True | 最小化到系统托盘 |
| background_mute | True | 后台时静音 |
| auto_adjust_window | False | 自动调整窗口大小 |
| directml | False | 使用 DirectML 加速 |
| trigger_interval | 0.5 | 触发任务检查间隔（秒） |
| hotkey | "F4" | 全局热键 |

#### DeviceManager

| 设置项 | 默认值 | 说明 |
|--------|--------|------|
| preferred_device | "pc" | 首选设备类型 |
| pc_path | "" | PC 游戏路径 |
| capture_method | "wgc" | 截图方式 |
| interaction_method | "postmessage" | 交互方式 |

### 6.3 config_type 类型系统

```python
class ConfigOption:
    name: str           # 配置项名称
    default: Any        # 默认值
    description: str    # 描述
    config_type: str    # 类型标识
    validator: callable # 验证函数
    icon: str           # 图标
```

#### drop_down：下拉选择

配置项为下拉选择类型，提供可选值列表：

```python
ConfigOption(
    name="capture_method",
    default="wgc",
    config_type="drop_down",
    options=["bitblt", "bitblt_renderfull", "foreground_bitblt", "wgc", "dxgi", "adb", "nemuipc"]
)
```

#### HotKey：热键配置

配置项为热键类型，支持键盘快捷键录制和显示：

```python
ConfigOption(
    name="hotkey",
    default="F4",
    config_type="HotKey"
)
```

---

## 七、任务执行模块

### 7.1 继承体系

```
ExecutorOperation (基础操作)
    └── FindFeature (特征查找)
            └── OCR (文字识别)
                    └── BaseTask (基础任务)
                            └── TriggerTask (触发任务)
```

- **ExecutorOperation**：提供截图、点击、等待等基础操作
- **FindFeature**：增加模板匹配能力（find_one_feature, find_features）
- **OCR**：增加文字识别能力（find_text, wait_text）
- **BaseTask**：增加任务生命周期管理（start, stop, pause, resume）
- **TriggerTask**：增加触发条件检查（should_run, trigger_interval）

### 7.2 TaskExecutor

主循环负责调度所有注册的任务：

```python
def run(self):
    while not self._stop_event.is_set():
        # 优先执行一次性任务
        while self.one_time_tasks:
            task = self.one_time_tasks.pop(0)
            self._execute_task(task)

        # 轮询触发任务
        for task in self.trigger_tasks:
            if task.should_run():
                self._execute_task(task)

        # 可中断睡眠
        self.sleep_check(self.trigger_interval)
```

#### 可中断睡眠

`sleep_check` 方法实现了可中断的睡眠，每 1ms 检查一次暂停/退出标志：

```python
def sleep_check(self, seconds):
    """睡眠中定期检查暂停/退出状态"""
    end_time = time.time() + seconds
    while time.time() < end_time:
        if self._stop_event.is_set():
            raise TaskStoppedException()
        if self._pause_event.is_set():
            self._wait_for_resume()
        time.sleep(0.001)  # 1ms 检查间隔
```

### 7.3 异常体系

| 异常类 | 说明 | 处理方式 |
|--------|------|---------|
| TaskDisabledException | 任务被禁用 | 跳过该任务 |
| CannotFindException | 找不到目标特征/文字 | 等待重试 |
| FinishedException | 任务已完成 | 移出任务队列 |
| WaitFailedException | 等待超时 | 记录日志 |
| CaptureException | 截图失败 | 尝试降级截图方式 |

---

## 八、GUI/Debug 模块

### 8.1 OverlayWidget 浮层绘制

浮层绘制组件，在游戏窗口上叠加调试信息：

#### paint_border：红色边框

在匹配到的特征区域周围绘制红色边框：

```python
def paint_border(self, painter, box):
    painter.setPen(QPen(Qt.red, 2))
    painter.drawRect(box.x, box.y, box.width, box.height)
```

#### paint_boxes：匹配框 + 名称_置信度

绘制匹配结果框，显示特征名称和置信度：

```python
def paint_boxes(self, painter, boxes):
    for box in boxes:
        painter.drawRect(box.x, box.y, box.width, box.height)
        text = f"{box.name}_{box.confidence:.2f}"
        painter.drawText(box.x, box.y - 5, text)
```

#### paint_mouse_position：鼠标坐标

实时显示鼠标在游戏窗口中的坐标：

```python
def paint_mouse_position(self, painter, pos):
    painter.drawText(10, 20, f"Mouse: ({pos.x()}, {pos.y()})")
```

#### paint_logs：左下角日志

在窗口左下角显示最近的日志信息，使用半透明黑色背景：

```python
def paint_logs(self, painter, logs):
    painter.fillRect(0, height - 200, 400, 200, QColor(0, 0, 0, 128))
    for i, log in enumerate(logs[-10:]):
        painter.drawText(10, height - 190 + i * 20, log)
```

#### paint_alt_overlay：Alt 键辅助线

按住 Alt 键时显示辅助线和坐标，方便标注模板：

- 十字辅助线
- 当前坐标值
- 点击复制坐标到剪贴板

#### paint_uid_cover：UID 遮盖

遮挡游戏中的 UID 信息，防止截图泄露：

```python
def paint_uid_cover(self, painter, uid_region):
    painter.fillRect(uid_region, QColor(0, 0, 0))
```

### 8.2 OverlayWindow 透明覆盖窗口

透明覆盖窗口，叠加在游戏窗口上方显示调试信息：

```python
class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)     # 透明背景
        self.setWindowFlags(
            Qt.FramelessWindowHint |                       # 无边框
            Qt.WindowStaysOnTopHint |                      # 置顶
            Qt.Tool |                                      # 不在任务栏显示
            Qt.WindowTransparentForInput                   # 鼠标穿透
        )
```

- **WA_TranslucentBackground**：窗口背景完全透明
- **FramelessWindowHint**：无标题栏和边框
- **WindowStaysOnTopHint**：始终置顶
- **Tool**：不在任务栏显示窗口
- **WindowTransparentForInput**：鼠标事件穿透到下层窗口

窗口跟随目标窗口的位置和尺寸变化：

```python
def update_position(self, target_hwnd):
    rect = GetWindowRect(target_hwnd)
    self.setGeometry(rect.left, rect.top, rect.width, rect.height)
```

### 8.3 Screenshot 截图管理器

管理截图上的绘制元素（匹配框、日志等）：

```python
class Screenshot:
    def __init__(self):
        self.ui_dict = {}  # key -> [boxes, timestamp, color]

    def draw_box(self, key, boxes, color=Qt.red):
        """添加绘制元素"""
        self.ui_dict[key] = [boxes, time.time(), color]

    def remove_expired(self, expire_seconds=4):
        """移除过期元素（默认4秒）"""
        now = time.time()
        expired = [k for k, v in self.ui_dict.items() if now - v[1] > expire_seconds]
        for k in expired:
            del self.ui_dict[k]
```

### 8.4 Communicate 信号总线

PyQt6 信号总线，用于模块间通信：

| 信号 | 参数 | 说明 |
|------|------|------|
| log | str | 日志消息 |
| draw_box | str, list, QColor | 绘制匹配框 |
| clear_box | str | 清除指定匹配框 |
| task | str | 任务状态变更 |
| task_done | str | 任务完成 |
| window | str | 窗口事件 |
| notification | str, str | 通知消息（标题+内容） |
| screenshot | np.ndarray | 截图数据 |
| adb_devices | list | ADB 设备列表 |
| executor_paused | bool | 执行器暂停状态 |
| quit | - | 退出信号 |

---

## 九、窗口管理

### 9.1 HwndWindow

窗口管理类，在后台线程中持续监控目标窗口的状态：

```python
class HwndWindow:
    def __init__(self):
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def _monitor_loop(self):
        while not self._stop_event.is_set():
            self._update_window_state()
            time.sleep(0.2)  # 200ms 更新间隔
```

#### 监控的窗口状态

| 属性 | 说明 |
|------|------|
| hwnd | 窗口句柄 |
| rect | 窗口位置和尺寸 |
| visible | 窗口是否可见 |
| muted | 窗口是否静音 |
| dpi_scale | DPI 缩放比例 |

#### 窗口不可见时暂停执行

当检测到目标窗口不可见（最小化或被遮挡）时，自动暂停任务执行，避免无效的截图和操作：

```python
def _update_window_state(self):
    self.visible = IsWindowVisible(self.hwnd)
    if not self.visible:
        self.executor.pause()
    elif self.executor.is_paused and self._was_paused_by_visibility:
        self.executor.resume()
```

### 9.2 find_hwnd

多策略窗口查找，支持多种匹配方式：

#### 查找策略

1. **标题精确匹配**：`FindWindow(None, exact_title)`
2. **标题正则匹配**：遍历所有窗口，`re.match(pattern, title)`
3. **类名匹配**：`FindWindow(class_name, None)`
4. **EXE 名匹配**：`CreateToolhelp32Snapshot` 枚举进程，匹配 EXE 名后获取其主窗口
5. **Player ID 匹配**：针对模拟器多开场景，通过窗口标题中的序号区分

#### 子窗口枚举

游戏渲染区域通常位于子窗口中，需要通过宽高比匹配找到正确的子窗口：

```python
def find_render_child(parent_hwnd, aspect_ratio=16/9):
    result = []
    def enum_callback(hwnd, _):
        rect = GetClientRect(hwnd)
        if rect.width > 0 and rect.height > 0:
            ratio = rect.width / rect.height
            if abs(ratio - aspect_ratio) < 0.1:
                result.append(hwnd)
        return True
    EnumChildWindows(parent_hwnd, enum_callback, 0)
    return max(result, key=lambda h: area(GetClientRect(h))) if result else parent_hwnd
```

#### DPI 缩放计算

正确处理高 DPI 环境下的坐标转换：

```python
def get_dpi_scale(hwnd):
    dpi = GetDpiForWindow(hwnd)
    return dpi / 96.0

def get_monitor_dpi_scale(hwnd):
    monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    dpi_x, dpi_y = GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI)
    return dpi_x / 96.0
```

---

## 十、GAF 可借鉴点

| # | 课题 | 当前状态 | 说明 |
|---|------|---------|------|
| 1 | WGC 截图的完整 ctypes 实现 | ✅ 已实现（纯ctypes） | `wgc.py` — D3D11 + WinRT 完整实现，无需第三方包 |
| 2 | BitBlt DC/Bitmap 缓存机制 | ❌ 未实现 | hwnd/尺寸不变时复用DC/Bitmap，显著提升性能 |
| 3 | 多子窗口合成（composite_hwnds） | ❌ 未实现 | 处理游戏多子窗口场景，自动枚举+DPI修正+合成 |
| 4 | PostMessage 动态子窗口定位 | ❌ 未实现 | EnumChildWindows 查找点击位置的实际目标子窗口 |
| 5 | Debug 浮层覆盖窗口 | ❌ 未实现 | 透明穿透实时绘制匹配框/日志，调试利器 |
| 6 | Config 自动持久化 + verify_config | ❌ 未实现 | dict继承自动保存+类型校验，确保配置一致性 |
| 7 | 拟人化贝塞尔曲线滑动 | ✅ 已实现 | `humanize.py` — 贝塞尔曲线+随机偏移 |
| 8 | OCR 多引擎支持 | ✅ 已实现（PaddleOCR+RapidOCR双引擎+引擎注册表） | PaddleOCR + RapidOCR 双引擎 + 引擎注册表 |
| 9 | COCO JSON 标注格式 | ❌ 未实现 | 标准化标注格式，便于标注工具复用 |
| 10 | 窗口状态后台监控线程 | ✅ 已实现 | `window_monitor.py` — 后台线程监控窗口状态 |

> **GAF 已超越 ok-script 的能力：**
>
> | 能力 | GAF | ok-script |
> |------|-----|----------|
> | **截图竞速选择** | ✅ benchmark.py | ❌ 固定优先级 |
> | **Pipeline 图执行引擎** | ✅ 16节点+校验器+三模式 | ❌ 继承体系 |
> | **ONNX 推理 (YOLOv8)** | ✅ DirectML/CUDA | ✅ ONNXPaddleOcr(OCR only) |
> | **AI 分割 (SAM/U²-Net)** | ✅ | ❌ |
> | **录制回放系统** | ✅ | ❌ |
> | **脚本 DSL** | ✅ | ❌ |
> | **5层异常恢复** | ✅ | ❌ 基础异常体系 |
> | **ADB 多级降级链** | ✅ 6截图+4输入 | ✅ 仅单级ADB |
> | **多用户 Web UI** | ✅ Django+React | ❌ PyQt6本地GUI |
> | **LLM 集成** | ✅ DeepSeek/OpenAI | ❌ |
> | **设备插件系统** | ✅ | ❌ |
> | **Debug 浮层** | ❌ | ✅ OverlayWidget |

---

## 十一、跨平台兼容性分析

ok-script 是 **Windows-only** 项目，核心功能（截图/输入/窗口管理）深度依赖 Win32 API，跨平台迁移需对平台绑定模块进行完整替换。

### 11.1 Windows 绑定分析

| 绑定类型 | 具体依赖 | 跨平台可用 | 说明 |
|---------|---------|-----------|------|
| WGC 截图 | Windows Graphics Capture（纯 ctypes 实现） | ❌ 仅 Windows | D3D11 + WinRT 完整实现，macOS/Linux 无对应 API |
| BitBlt 截图 | GDI `BitBlt` + DC/Bitmap 缓存 | ❌ 仅 Windows | hwnd/尺寸不变时复用 DC/Bitmap，性能优化显著 |
| 多子窗口合成 | `EnumChildWindows` + BitBlt 合成 | ❌ 仅 Windows | 处理游戏多子窗口场景 |
| 伪最小化 | `WS_EX_LAYERED` + `WS_EX_TRANSPARENT` + alpha=0 | ❌ 仅 Windows | Windows 窗口风格特有机制 |
| PostMessage 输入 | `PostMessage` / `SendMessage` 后台输入 | ❌ 仅 Windows | 仅 Windows 消息机制支持后台输入 |
| SendInput 输入 | `SendInput` 前台输入 | ❌ 仅 Windows | Windows 输入注入 API |

### 11.2 各平台替代方案

**截图替代：**

| 平台 | 替代方案 | 说明 |
|------|---------|------|
| macOS | CoreGraphics `CGWindowListCreateImage` + `screencapture` 命令 | `CGWindowListCreateImage` 支持指定窗口 PID 截取，`screencapture` 为命令行备选 |
| Linux (X11) | X11 `XGetImage` / `XShmGetImage` | XShmGetImage 使用共享内存，性能更优 |
| Linux (Wayland) | xdg-desktop-portal `Screenshot` / `ScreenCast` | Wayland 安全模型限制，需通过 Portal DBus 接口 |

**输入替代：**

| 平台 | 替代方案 | 说明 |
|------|---------|------|
| macOS | `CGEventPost` + `CGEventCreateMouseEvent` / `CGEventCreateKeyboardEvent` | CoreGraphics 事件注入，需辅助功能权限（Accessibility） |
| Linux (X11) | `XTestFakeKeyEvent` + `XSendEvent` | XTest 扩展模拟输入，XSendEvent 可发送至特定窗口 |
| Linux (无X11) | uinput / evdev | 内核级输入设备模拟，不依赖显示服务器 |

### 11.3 跨平台通用模块

| 模块 | 说明 | 跨平台 |
|------|------|--------|
| 拟人化贝塞尔曲线 | 纯数学算法，随机偏移 + 曲线插值 | ✅ 纯 Python |
| OCR 多引擎 | PaddleOCR / RapidOCR 双引擎 | ✅ 跨平台 Python 包 |
| COCO JSON 标注格式 | 标准化标注格式 | ✅ 纯数据格式 |
| Config 自动持久化 | dict 继承 + 自动保存 + 类型校验 | ✅ 纯 Python |
| 模板匹配 | OpenCV `matchTemplate` | ✅ 跨平台 |
| 特征点匹配 | SIFT/ORB 特征提取与匹配 | ✅ 跨平台 |

### 11.4 对 GAF 的启示

| # | 启示 | 说明 |
|---|------|------|
| 1 | 截图/输入封装为平台插件 | 将 ok-script 的 Windows 截图（WGC/BitBlt）和输入（PostMessage/SendInput）封装为 `WindowsScreenshotProvider` / `WindowsInputController` 平台插件，macOS/Linux 实现对应插件 |
| 2 | 后台输入是 Windows 独有能力 | `PostMessage`/`SendMessage` 后台输入仅 Windows 支持，macOS 的 `CGEventPost` 和 Linux 的 `XTest` 均为前台输入，GAF 需在跨平台设计中明确标注此后台输入能力差异 |
| 3 | BitBlt 缓存/多子窗口合成/伪最小化为 Windows 专用 | 这些优化手段均依赖 Windows 窗口管理机制，macOS/Linux 需寻找各自平台的对应优化方案（如 macOS 的 `NSWindow` 透明化） |
| 4 | 纯算法/数据模块直接复用 | 拟人化曲线、OCR 多引擎、COCO JSON、Config 持久化等纯 Python 模块可直接参考，无需平台适配 |