---
maintainer: manual
source: worker/src/devices/macos/, backend/device_bridge/platforms/macos/, Apple Quartz Docs
load_when:
- 新功能 (macOS 平台)
- 调试 macOS 截图/输入
- 跨平台适配
priority: medium
symptom:
- kb:platform:macos
- quartz
- coregraphics
- CGEvent
- 沙盒
solution: 4 截图 API (CG/Quartz/screencapture) + 2 输入 API (CGEvent/Quartz Event) + 5 易错点 + 沙盒限制
related_files:
- backend/device_bridge/platforms/macos/screenshot.py
- backend/device_bridge/platforms/macos/input.py
- backend/device_bridge/platforms/macos/
created_by: AI
generated: 2026-06-16
last_manual_edit: 2026-06-16
---
# macOS Platform (macOS 平台) - GAF 速查

> **适用场景**: AI 写 macOS 平台截图/输入/窗口管理代码
> **GAF 状态**: 🟡 部分支持 (需权限授予)
> **最低要求**: macOS 11 Big Sur+

## 1. 平台特性

| 项 | 内容 |
|----|------|
| **最低版本** | macOS 11 Big Sur |
| **推荐版本** | macOS 13 Ventura+ |
| **架构** | x86_64 / Apple Silicon (M1/M2/M3) |
| **Python** | 3.9+ (3.11 推荐) |
| **窗口系统** | Quartz / Cocoa |
| **截图 API** | CG / Quartz / screencapture 命令 |
| **输入 API** | CGEvent (需要辅助功能权限) |
| **DPI** | Retina @2x / @3x (需处理) |
| **沙盒** | TCC (Transparency, Consent, and Control) 权限 |
| **管理员权限** | 截图不需要, 输入**必须**辅助功能权限 |

## 2. 截图 4 种方法

### 2.1 screencapture 命令 (推荐)

**优势**: 系统自带, 权限友好
**用法**:
```bash
# 全屏
screencapture -x screenshot.png    # -x 不播放声音

# 窗口
screencapture -l$(window_id) window.png

# 区域
screencapture -R100,100,800,600 region.png

# Retina 模式 (完整像素)
screencapture -R0,0,2880,1800 retina.png
```

### 2.2 Quartz CG (编程)

**库**: `pyobjc-framework-Quartz`
**安装**: `pip install pyobjc-framework-Quartz`
**用法**:
```python
import Quartz
from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
from Quartz.CoreGraphics import CGImageDestinationCreateWithURL
import LaunchServices

# 截屏
def capture_screen():
    # 创建 CGImage
    image_ref = Quartz.CGWindowListCreateImage(
        Quartz.CGRectInfinite,
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault
    )
    # 保存为 PNG
    url = Quartz.CFURLCreateWithFileSystemPath(None, "screenshot.png", Quartz.kCFURLPOSIXPathStyle, False)
    dest = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(dest, image_ref, None)
    Quartz.CGImageDestinationFinalize(dest)
```

### 2.3 screencapture API (CGSSession)

**库**: CoreGraphics
**用法**: 类似 2.2, 但用 `CGSSession` API

### 2.4 CoreMediaIO (CMIO) - 高级

**用途**: 屏幕录制 (视频流)
**限制**: 需要 Screen Recording 权限
**GAF 用途**: 录制任务过程

## 3. 输入 2 种方法

### 3.1 CGEvent (推荐, 高级)

**优势**: 精细控制, 支持子像素坐标
**限制**: **必须**授予"辅助功能"权限
**安装**: `pip install pyobjc-framework-Quartz pyobjc-framework-ApplicationServices`
**用法**:
```python
import Quartz
from Quartz import (
    CGEventCreateMouseEvent, CGEventPost, kCGEventLeftMouseDown, kCGEventLeftMouseUp,
    kCGMouseButtonLeft, kCGHIDEventTap, CGEventCreateKeyboardEvent, kCGEventKeyDown, kCGEventKeyUp
)

def click_mouse(x: int, y: int):
    """模拟鼠标点击"""
    # 移动
    move = CGEventCreateMouseEvent(None, 5, (x, y), kCGMouseButtonLeft)  # 5 = kCGEventMouseMoved
    CGEventPost(kCGHIDEventTap, move)
    # 按下
    down = CGEventCreateMouseEvent(None, 1, (x, y), kCGMouseButtonLeft)  # 1 = kCGEventLeftMouseDown
    CGEventPost(kCGHIDEventTap, down)
    # 释放
    up = CGEventCreateMouseEvent(None, 2, (x, y), kCGMouseButtonLeft)  # 2 = kCGEventLeftMouseUp
    CGEventPost(kCGHIDEventTap, up)

def type_text(text: str):
    """模拟键盘输入"""
    for char in text:
        keycode = char_to_keycode(char)  # 字符转 keycode
        down = CGEventCreateKeyboardEvent(None, keycode, True)
        up = CGEventCreateKeyboardEvent(None, keycode, False)
        CGEventPost(kCGHIDEventTap, down)
        CGEventPost(kCGHIDEventTap, up)
```

### 3.2 Quartz Event Services (底层)

**优势**: 更底层控制
**限制**: 需要 root 或特殊权限
**用途**: 调试 / 特殊场景

## 4. 窗口管理

### 4.1 查找窗口

```python
import Quartz
from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID

def find_window_by_title(title: str) -> int:
    """根据标题查找 macOS 窗口"""
    windows = Quartz.CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    )
    for window in windows:
        window_title = window.get('kCGWindowName', '')
        if title in window_title:
            return window['kCGWindowNumber']
    return 0
```

### 4.2 窗口操作

```python
# 激活窗口
import AppKit
app = AppKit.NSApplication.sharedApplication()
windows = app.windows()
for window in windows:
    if title in window.title():
        window.makeKeyAndOrderFront_(None)
        break

# 移动窗口
window.setFrameOrigin_(AppKit.NSPoint(x, y))

# 缩放窗口
window.setFrame_display_(AppKit.NSRect(x, y, w, h), True)
```

## 5. 权限 (TCC) - 关键!

### 5.1 必须权限 (3 个)

| 权限 | 用途 | 申请方式 |
|------|------|----------|
| **辅助功能 (Accessibility)** | 模拟键盘/鼠标 | 系统设置 → 隐私与安全 → 辅助功能 |
| **屏幕录制 (Screen Recording)** | CG 截屏 | 系统设置 → 隐私与安全 → 屏幕录制 |
| **自动化 (Automation)** | 控制其他应用 | 系统设置 → 隐私与安全 → 自动化 |

### 5.2 权限申请失败后果

| 失败 | 后果 |
|------|------|
| 辅助功能未授权 | CGEvent 静默失败, 无报错 |
| 屏幕录制未授权 | 截屏全黑 |
| 自动化未授权 | AppleScript 失败 |

### 5.3 检测权限

```python
# 检测辅助功能权限
import Quartz

def check_accessibility_permission() -> bool:
    """检查是否有辅助功能权限"""
    options = {Quartz.kAXTrustedCheckOptionPrompt: True}
    return Quartz.AXIsProcessTrustedWithOptions(options)
```

## 6. 5 个 AI 易错点

### 6.1 ❌ 忽略权限申请 (N68)

**错误**: 直接调 CGEvent, 没检查权限
**后果**: 静默失败, 任务看似成功实际无操作
**正确**: 启动时 `check_accessibility_permission()`, 失败时弹窗引导用户

### 6.2 ❌ 不处理 Retina (N69)

**错误**: 假设逻辑坐标 = 物理坐标
**后果**: Retina 显示器上点击位置偏移 2 倍
**正确**: 用 `Quartz.NSScreen.backingScaleFactor` 获取缩放, 转换坐标

### 6.3 ❌ Apple Silicon 库不兼容 (N70)

**错误**: 用了 x86-only 的二进制库
**后果**: M1/M2 上崩溃
**正确**: 装 arm64 版本 (`arch -arm64 pip install ...`)

### 6.4 ❌ screencapture 包含鼠标光标 (N71)

**错误**: 默认截图含鼠标
**后果**: 模板匹配受光标干扰
**正确**: `-C` 参数 (`screencapture -C ...`)

### 6.5 ❌ 沙盒应用无法截屏 (N72)

**错误**: Mac App Store 应用被沙盒限制
**后果**: 截屏失败
**正确**: 提示用户用 Developer ID 签名版本, 或绕开 Mac App Store

## 7. 速查表

| 场景 | 截图 | 输入 | 备注 |
|------|------|------|------|
| macOS 13 + Apple Silicon | screencapture -x | CGEvent | 推荐 |
| macOS 11 + Intel | Quartz CG | CGEvent | 兼容性 |
| Retina @2x 显示器 | screencapture -R | CGEvent + scale 2x | 坐标转换 |
| 远程 SSH | screencapture | (需 ssh 转发) | 复杂 |
| Mac App Store | ❌ 不支持 | ❌ 不支持 | 沙盒限制 |

## 8. 相关文件

- `backend/device_bridge/platforms/macos/screenshot.py` - 截图抽象
- `backend/device_bridge/platforms/macos/input.py` - CGEvent 输入
- `backend/device_bridge/platforms/macos/discovery.py` - 设备发现
- `backend/device_bridge/platforms/macos/screenshot.py` - 后端平台

## 9. 反思 (Reflection)

- **macOS 是 GAF 次要平台**: 用户量小, 约 15%
- **TCC 权限是最大障碍**: 必须用户手动授予
- **Retina 缩放是常见 bug**: 不处理会点击偏移
- **Apple Silicon 兼容**: 库需 arm64 版本
- **沙盒应用不支持**: 需 Developer ID 签名
- **相关**: windows.md / linux.md / android.md / ios.md
