---
maintainer: manual
source: worker/src/devices/windows/, backend/device_bridge/platforms/windows/, Microsoft Docs
load_when:
- 新功能 (Windows 平台)
- 调试 Windows 截图/输入
- 跨平台适配
priority: high
symptom:
- kb:platform:windows
- win32
- WGC
- DXGI
- PostMessage
solution: 3 截图 API 降级链 (WGC→DXGI→BitBlt) + 4 输入 API + 5 易错点 + DPI 适配
related_files:
- backend/device_bridge/platforms/windows/screenshot.py
- backend/device_bridge/platforms/windows/input.py
- worker/src/platforms/windows/dxgi_capture.py
- worker/src/platforms/windows/wgc.py
- worker/src/platforms/windows/window.py
- backend/device_bridge/platforms/windows/
created_by: AI
generated: 2026-06-16
last_manual_edit: 2026-06-16
---
# Windows Platform (Windows 平台) - GAF 速查

> **适用场景**: AI 写 Windows 平台截图/输入/窗口管理代码
> **GAF 状态**: ✅ 完整支持, 主力平台
> **最低要求**: Windows 10 1903+ (WGC API)

## 1. 平台特性

| 项 | 内容 |
|----|------|
| **最低版本** | Windows 10 1903 (May 2019 Update) |
| **推荐版本** | Windows 11 22H2+ |
| **架构** | x64 / ARM64 |
| **Python** | 3.9+ (3.11 推荐) |
| **关键 API** | WGC / DXGI / BitBlt / PrintWindow / PostMessage |
| **窗口系统** | Win32 / WinUI / WPF / Qt |
| **DPI** | 支持 100% / 125% / 150% / 200% (需特殊处理) |
| **管理员权限** | 截图不需要, 输入可能需要 UAC |

## 2. 截图 3 档降级链

```
[WGC] Windows Graphics Capture (Win10 1903+)
    │ 失败 (旧系统/无 GPU)
    ▼
[DXGI] DirectX Graphics Infrastructure (Win8+)
    │ 失败 (无 DirectX)
    ▼
[BitBlt] GDI Bit Block Transfer (WinXP+)
    │ 失败 (极少数情况)
    ▼
[PrintWindow] Win32 API (兜底)
```

### 2.1 WGC (Windows Graphics Capture) - 首选

**优势**: 高性能, 截屏含 GPU 内容, 支持现代应用
**限制**: Win10 1903+ 必须
**实现**: `worker/src/platforms/windows/wgc.py` (基于 `windows-capture` 库)
**性能**: 60+ FPS, 16ms 延迟

```python
from device_bridge.src.devices.windows.wgc import WGCScreenshot

wgc = WGCScreenshot()
screenshot = wgc.capture(hwnd=hwnd)  # bytes, PNG
```

### 2.2 DXGI (Desktop Duplication API) - 次选

**优势**: 截屏含 GPU, 兼容性较好
**限制**: Win8+, 需 DirectX 11+
**实现**: `worker/src/platforms/windows/dxgi_capture.py`
**性能**: 30-60 FPS, 30ms 延迟

```python
from device_bridge.src/devices.windows.dxgi_capture import DXGIScreenshot

dxgi = DXGIScreenshot()
screenshot = dxgi.capture_desktop()  # 全屏截图
```

### 2.3 BitBlt (GDI) - 兜底

**优势**: 兼容性最好 (WinXP+)
**限制**: 不能截 GPU 内容 (游戏全屏可能黑屏)
**实现**: `backend/device_bridge/platforms/windows/screenshot.py`
**性能**: 20-30 FPS, 50ms 延迟

```python
from device_bridge.src.devices.windows.screenshot import BitBltScreenshot

bitblt = BitBltScreenshot()
screenshot = bitblt.capture(hwnd=hwnd, region=(0, 0, 1920, 1080))
```

### 2.4 降级链自动选择

```python
# worker/src/devices/windows/benchmark.py
def select_best_screenshot_method() -> ScreenshotMethod:
    if is_wgc_available():
        return WGCScreenshot()
    elif is_dxgi_available():
        return DXGIScreenshot()
    else:
        return BitBltScreenshot()
```

## 3. 输入 4 种 API

### 3.1 PostMessage (推荐, 跨进程)

**优势**: 不需要焦点, 跨进程, 模拟器透传
**限制**: 仅特定消息 (WM_KEYDOWN/WM_LBUTTONDOWN)
**实现**: `backend/device_bridge/platforms/windows/input.py` 的 `post_click()`

```python
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202

def post_click(hwnd: int, x: int, y: int):
    """通过 PostMessage 发送鼠标点击, 不需要窗口焦点"""
    lparam = (y << 16) | x
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
```

### 3.2 SendInput (需要焦点)

**优势**: 真实硬件级输入, 兼容性好
**限制**: 需要窗口在前台 + 焦点
**实现**: `input.py` 的 `send_input_click()`

```python
import ctypes

user32 = ctypes.windll.user32

def send_input_click(x: int, y: int):
    """通过 SendInput 发送硬件级鼠标点击"""
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]
    # ... (构造 INPUT 结构, 调 SendInput)
```

### 3.3 SendMessage (同步, 阻塞)

**优势**: 同步等待返回
**限制**: 阻塞调用, 性能差
**用途**: 调试 / 需要返回值的场景

### 3.4 pyautogui (跨平台, 兜底)

**优势**: 跨平台, 简单
**限制**: 需要焦点, 慢
**用途**: 简单场景兜底

## 4. 窗口管理

### 4.1 查找窗口

```python
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
GetWindowText = user32.GetWindowTextW
GetWindowTextLength = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible

def find_window_by_title(title: str) -> int:
    """根据标题查找窗口句柄"""
    hwnd_found = [0]
    
    def callback(hwnd, lparam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                if title in buff.value:
                    hwnd_found[0] = hwnd
                    return False  # 停止枚举
        return True
    
    EnumWindows(EnumWindowsProc(callback), 0)
    return hwnd_found[0]
```

### 4.2 窗口操作

```python
# 激活窗口
user32.SetForegroundWindow(hwnd)

# 移动/缩放
user32.MoveWindow(hwnd, x, y, width, height, True)

# 检查窗口是否最小化
user32.IsIconic(hwnd)  # True = 最小化

# 恢复最小化窗口
user32.ShowWindow(hwnd, 9)  # SW_RESTORE
```

## 5. 5 个 AI 易错点

### 5.1 ❌ 假设 32-bit 颜色 (N58)

**错误**: 假设 screenshot 是 32-bit BGRA
**后果**: 颜色通道错位 (R 变 B)
**正确**: 检查 `bitmap.bmBitsPixel`, 转换时用 `cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)`

### 5.2 ❌ 不处理高 DPI (N59)

**错误**: 假设 `GetSystemMetrics(SM_CXSCREEN)` 返回物理像素
**后果**: 高 DPI 显示器坐标偏移
**正确**: 用 `GetDpiForSystem()` 获取 DPI, 缩放坐标

### 5.3 ❌ PostMessage 给非响应窗口 (N60)

**错误**: 窗口"假死"时 PostMessage 失败
**后果**: 任务卡住
**正确**: 加 timeout + fallback 到 SendInput

### 5.4 ❌ WGC 句柄泄漏 (N61)

**错误**: 创建 WGC session 后忘记关闭
**后果**: 系统句柄耗尽, 后续截图失败
**正确**: 用 `with` 语句或 try/finally 关闭

### 5.5 ❌ 焦点竞争 (N62)

**错误**: 多个脚本同时抢窗口焦点
**后果**: 输入错乱
**正确**: 用 mutex/锁, 或用 PostMessage (无需焦点)

## 6. DPI 适配

### 6.1 Windows DPI 问题

**症状**: 100% DPI 截图和 150% DPI 截图坐标不通用
**原因**: Windows 应用可能报告"逻辑坐标" (DIP), 不是物理像素
**解决**: 用 `GetDpiForWindow(hwnd)` 获取窗口 DPI, 缩放到物理像素

### 6.2 GAF 的 DPI 处理

```python
# coordinate utility (已删除)
def get_window_dpi_scale(hwnd: int) -> float:
    """获取窗口 DPI 缩放比例"""
    dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
    return dpi / 96.0  # 96 DPI = 100% 缩放

def scale_to_physical(hwnd: int, x: int, y: int) -> tuple:
    """逻辑坐标 → 物理坐标"""
    scale = get_window_dpi_scale(hwnd)
    return int(x * scale), int(y * scale)
```

## 7. 速查表

| 场景 | 截图 API | 输入 API | 备注 |
|------|----------|----------|------|
| 模拟器 (LDPlayer) | WGC | PostMessage | 透传到模拟器 |
| 现代应用 (Edge) | WGC | SendInput | GPU 内容 |
| 旧应用 (Office) | BitBlt | SendInput | 无 GPU 加速 |
| 游戏全屏 | WGC | SendInput | 独占模式 |
| UAC 弹窗 | DXGI | SendInput | 需管理员 |
| 远程桌面 | BitBlt | SendInput | 兼容性优先 |

## 8. 相关文件

- `backend/device_bridge/platforms/windows/screenshot.py` - BitBlt 实现
- `worker/src/platforms/windows/dxgi_capture.py` - DXGI 实现
- `worker/src/platforms/windows/wgc.py` - WGC 实现
- `backend/device_bridge/platforms/windows/input.py` - PostMessage/SendInput
- `worker/src/platforms/windows/window.py` - 窗口管理
- `worker/src/devices/windows/benchmark.py` - 性能测试
- `backend/device_bridge/platforms/windows/` - 后端平台抽象

## 9. 反思 (Reflection)

- **Windows 是 GAF 主力平台**: 80% 用户用 Windows
- **WGC 是首选**: 性能 + 兼容性最好
- **DPI 是最大坑**: 高 DPI 显示器坐标偏移
- **PostMessage 跨进程**: 不需要焦点, 模拟器透传
- **降级链保证兼容性**: WGC → DXGI → BitBlt
- **相关**: linux.md / macos.md / android.md / ios.md
