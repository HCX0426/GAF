---
maintainer: manual
source: agent/src/devices/linux/, backend/device_bridge/platforms/linux/, xdotool/grim docs
load_when:
- 新功能 (Linux 平台)
- 调试 Linux 截图/输入
- 跨平台适配
priority: medium
symptom:
- kb:platform:linux
- x11
- wayland
- xdotool
- grim
solution: 2 显示协议 (X11/Wayland) + 4 截图工具 + 3 输入工具 + 5 易错点
related_files:
- backend/device_bridge/platforms/linux/screenshot.py
- backend/device_bridge/platforms/linux/input.py
- backend/device_bridge/platforms/linux/
created_by: AI
generated: 2026-06-16
last_manual_edit: 2026-06-16
---
# Linux Platform (Linux 平台) - GAF 速查

> **适用场景**: AI 写 Linux 平台截图/输入/窗口管理代码
> **GAF 状态**: 🟡 部分支持 (X11 完整, Wayland 有限)
> **最低要求**: Ubuntu 20.04+ / X11 (Wayland 兼容性有限)

## 1. 平台特性

| 项 | 内容 |
|----|------|
| **最低版本** | Ubuntu 20.04 LTS / CentOS 8+ |
| **推荐版本** | Ubuntu 22.04 LTS |
| **架构** | x64 / ARM64 |
| **Python** | 3.9+ |
| **显示协议** | X11 (推荐) / Wayland (有限支持) |
| **窗口系统** | X11 / Wayland / Mir |
| **桌面环境** | GNOME / KDE / XFCE / i3 |
| **管理员权限** | 截图不需要, X11 输入需要 |
| **Wayland 限制** | 全局输入受限, 需 `wlr-protocols` |

## 2. 2 大显示协议

### 2.1 X11 (推荐, 完整支持)

**优势**: 成熟, 工具链完整, 全局输入/截图
**代表工具**: xdotool, xwd, ImageMagick, scrot
**GAF 状态**: ✅ 完整支持

### 2.2 Wayland (有限支持)

**优势**: 更安全, 现代
**限制**: 设计上**不允许**全局键盘/鼠标监听 (需 compositor 权限)
**代表工具**: grim, slurp, wtype, wl-clipboard
**GAF 状态**: 🟡 截图支持, 输入受限

## 3. 截图 4 种工具

### 3.1 grim (Wayland 推荐)

**协议**: Wayland
**安装**: `sudo apt install grim`
**用法**:
```bash
# 全屏
grim screenshot.png

# 窗口
grim -g "$(swaymsg -t get_tree | jq -r '.. | select(.pid? and .focused?) | .rect | "\(.x),\(.y) \(.width)x\(.height)"' | head -1)" window.png
```

### 3.2 scrot (X11 通用)

**协议**: X11
**安装**: `sudo apt install scrot`
**用法**:
```bash
scrot screenshot.png
scrot -d 5 delay.png  # 5 秒延迟
```

### 3.3 maim (X11, 更快)

**协议**: X11
**安装**: `sudo apt install maim`
**用法**:
```bash
maim screenshot.png
maim -s region.png  # 选区
```

### 3.4 ImageMagick import (X11 兜底)

**协议**: X11
**安装**: `sudo apt install imagemagick`
**用法**:
```bash
import -window root screenshot.png
```

## 4. 输入 3 种工具

### 4.1 xdotool (X11, 推荐)

**协议**: X11
**安装**: `sudo apt install xdotool`
**用法**:
```bash
# 模拟键盘
xdotool key ctrl+c
xdotool type "hello world"

# 模拟鼠标
xdotool mousemove 100 200
xdotool click 1  # 左键
xdotool click 3  # 右键

# 查找窗口
xdotool search --name "BD2" window_id
```

### 4.2 wtype (Wayland)

**协议**: Wayland
**安装**: `sudo apt install wtype`
**限制**: 仅 wlroots-based compositor (Sway/Hyprland)
**用法**:
```bash
wtype -k ctrl+c
wtype "hello world"
```

### 4.3 ydotool (通用, 需 daemon)

**协议**: X11 + Wayland (通过 uinput)
**安装**: `sudo apt install ydotool`
**用法**:
```bash
ydotool key 29:1 29:0  # 按下/释放 keycode 29 (Ctrl)
ydotool mousemove 100 200
```

## 5. 窗口管理

### 5.1 X11 窗口

```python
# window discovery module (已重构)
import subprocess

def find_x11_window_by_name(name: str) -> int:
    """通过 xdotool 查找 X11 窗口 ID"""
    result = subprocess.run(
        ['xdotool', 'search', '--name', name],
        capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        return int(result.stdout.strip().split('\n')[0])
    return 0
```

### 5.2 Wayland 窗口

Wayland 设计上**不允许**查询其他应用窗口, 需 compositor 扩展:
- Sway: `swaymsg -t get_tree`
- GNOME: 需 `gnome-shell-extension` (复杂)
- KDE: KWin scripts

## 6. GAF 截图抽象

```python
# backend/device_bridge/platforms/linux/screenshot.py
import subprocess
import shutil

class LinuxScreenshot:
    def capture(self) -> bytes:
        if shutil.which('grim'):
            return self._capture_grim()  # Wayland 优先
        elif shutil.which('maim'):
            return self._capture_maim()  # X11 快速
        elif shutil.which('scrot'):
            return self._capture_scrot()
        else:
            raise RuntimeError("No screenshot tool available")
```

## 7. 5 个 AI 易错点

### 7.1 ❌ 假设 X11 可用 (N63)

**错误**: 默认用 xdotool, 不检查 Wayland
**后果**: Wayland 系统上 xdotool 不可用
**正确**: `echo $XDG_SESSION_TYPE` 检测, 选 grim/wtype 或 xdotool

### 7.2 ❌ 不检查 Wayland 权限 (N64)

**错误**: Wayland 下用 wtype 没权限
**后果**: 静默失败
**正确**: 检查 compositor 是否支持 (sway/hyprland 是, gnome 不支持)

### 7.3 ❌ sudo 运行 xdotool (N65)

**错误**: `sudo xdotool ...` 找 root 用户窗口
**后果**: 找不到普通用户窗口
**正确**: 用 `DISPLAY=:0` 环境变量指定显示

### 7.4 ❌ 截图包含鼠标光标 (N66)

**错误**: grim/scrot 包含鼠标光标
**后果**: 模板匹配受光标干扰
**正确**: grim 加 `-c` (hide cursor), scrot 用 `--disable-cursor`

### 7.5 ❌ 桌面环境假设 (N67)

**错误**: 默认假设 GNOME 快捷键
**后果**: KDE/XFCE 快捷键不同
**正确**: 用 xdotool 显式发键, 不依赖 DE 快捷键

## 8. 速查表

| 场景 | 截图 | 输入 | 备注 |
|------|------|------|------|
| Ubuntu 22.04 + X11 | maim | xdotool | 完整支持 |
| Fedora 39 + Wayland | grim | wtype | wlroots 必要 |
| Manjaro KDE | spectacle | xdotool | 需 `xwayland` |
| Raspberry Pi OS | scrot | xdotool | 性能一般 |
| 远程 SSH + X11 | maim | xdotool | 需 `xhost +` |

## 9. 相关文件

- `backend/device_bridge/platforms/linux/screenshot.py` - 截图抽象
- `backend/device_bridge/platforms/linux/input.py` - 输入抽象
- `backend/device_bridge/platforms/linux/discovery.py` - 设备发现
- `backend/device_bridge/platforms/linux/screenshot.py` - 后端平台

## 10. 反思 (Reflection)

- **Linux 平台碎片化严重**: 发行版/DE/协议 多种组合
- **X11 仍是主力**: Wayland 兼容性需 compositor 支持
- **Wayland 全局输入受限**: 设计上为安全, GAF 部分功能受影响
- **3 步检测**: `$XDG_SESSION_TYPE` → 选工具 → 验证可用
- **相关**: windows.md / macos.md / android.md / ios.md
