---
maintainer: manual
source: agent/src/devices/adb/, Android Debug Bridge docs
load_when:
- 新功能 (Android 设备)
- 调试 ADB 截图/输入
- 模拟器支持
priority: high
symptom:
- kb:platform:android
- adb
- 模拟器
- 真机
solution: 4 ADB 命令 (screencap/input) + 5 模拟器 (LDPlayer/BlueStacks/Nox/MuMu/Android Studio) + 4 易错点
related_files:
- agent/src/devices/adb/device.py
- agent/src/devices/adb/pool.py
- agent/src/devices/emulator_discovery.py
- backend/device_bridge/discovery/emulator.py
created_by: AI
generated: 2026-06-16
last_manual_edit: 2026-06-16
---
# Android Platform (Android 设备) - GAF 速查

> **适用场景**: AI 写 Android 设备控制 / 模拟器支持 / 真机调试
> **GAF 状态**: ✅ 完整支持, 主力移动平台
> **核心**: ADB (Android Debug Bridge) + 模拟器透传

## 1. 平台特性

| 项 | 内容 |
|----|------|
| **最低版本** | Android 5.0 Lollipop (API 21) |
| **推荐版本** | Android 10+ (API 29+) |
| **架构** | arm64-v8a / armeabi-v7a / x86 / x86_64 |
| **ADB 版本** | 1.0.41+ (推荐 35+) |
| **截图 API** | `adb shell screencap` |
| **输入 API** | `adb shell input` |
| **分辨率** | 720x1280 / 1080x1920 / 1440x3200 |
| **DPI** | 160-640 dpi (mdpi-xxxhdpi) |
| **特殊权限** | USB 调试 (真机) / 模拟器端口 |

## 2. 4 个核心 ADB 命令

### 2.1 截图 (screencap)

```bash
# 截屏到设备
adb shell screencap -p /sdcard/screen.png

# 拉取到本地
adb pull /sdcard/screen.png ./screenshot.png

# 一行命令 (用 exec-out, 避免文件)
adb exec-out screencap -p > screenshot.png
```

**GAF 实现**:
```python
# agent/src/devices/adb/device.py
import subprocess

def screenshot(serial: str) -> bytes:
    """ADB 截图, 返回 PNG bytes"""
    result = subprocess.run(
        ['adb', '-s', serial, 'exec-out', 'screencap', '-p'],
        capture_output=True
    )
    return result.stdout
```

### 2.2 触控 (input tap/swipe)

```bash
# 点击
adb shell input tap 500 1000

# 滑动 (x1 y1 x2 y2 duration_ms)
adb shell input swipe 100 1000 100 200 500

# 长按 (duration_ms > 500)
adb shell input swipe 500 1000 500 1000 1000

# 文本输入 (注意: 不支持中文, 需用 ADBKeyboard)
adb shell input text "hello"
```

**GAF 实现**:
```python
def tap(serial: str, x: int, y: int):
    subprocess.run(['adb', '-s', serial, 'shell', 'input', 'tap', str(x), str(y)])

def swipe(serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
    subprocess.run(['adb', '-s', serial, 'shell', 'input', 'swipe',
                    str(x1), str(y1), str(x2), str(y2), str(duration_ms)])
```

### 2.3 按键 (input keyevent)

```bash
# Home 键
adb shell input keyevent KEYCODE_HOME

# 返回键
adb shell input keyevent KEYCODE_BACK

# 音量+/-
adb shell input keyevent KEYCODE_VOLUME_UP
adb shell input keyevent KEYCODE_VOLUME_DOWN

# 电源键
adb shell input keyevent KEYCODE_POWER
```

**常用 keycode**:
| Keycode | 值 | 含义 |
|---------|-----|------|
| KEYCODE_HOME | 3 | Home |
| KEYCODE_BACK | 4 | 返回 |
| KEYCODE_VOLUME_UP | 24 | 音量+ |
| KEYCODE_VOLUME_DOWN | 25 | 音量- |
| KEYCODE_POWER | 26 | 电源 |
| KEYCODE_MENU | 82 | 菜单 |
| KEYCODE_SEARCH | 84 | 搜索 |

### 2.4 设备列表 (adb devices)

```bash
# 列出所有设备
adb devices

# 输出格式:
# List of devices attached
# emulator-5554   device
# 127.0.0.1:5555  device
# <serial>        device
```

**GAF 实现**:
```python
def list_adb_devices() -> list:
    """列出所有 ADB 设备"""
    result = subprocess.run(['adb', 'devices'], capture_output=True, text=True)
    devices = []
    for line in result.stdout.splitlines()[1:]:  # 跳过 header
        if '\t' in line:
            serial, state = line.split('\t')
            if state == 'device':
                devices.append(serial)
    return devices
```

## 3. 5 大模拟器

| 模拟器 | 平台 | 默认端口 | 特点 | GAF 适配 |
|--------|------|----------|------|:--------:|
| **LDPlayer** | Win | 5555+ | 中文, 性能好 | ⭐⭐⭐⭐⭐ |
| **BlueStacks 5** | Win/Mac | 5555 | 老牌, 资源多 | ⭐⭐⭐⭐ |
| **NoxPlayer** | Win/Mac | 62001 | 轻量 | ⭐⭐⭐ |
| **MuMu Player** | Win | 7555 | 网易, 简洁 | ⭐⭐⭐ |
| **Android Studio AVD** | 全平台 | 5554 | 官方, 调试 | ⭐⭐⭐⭐ |

### 3.1 LDPlayer (主力, 80% BD2 用户)

**特点**: 中文界面, BD2 性能优化, 多开
**ADB 连接**: `adb connect 127.0.0.1:5555` (端口 5555+)
**Serial 格式**: `127.0.0.1:5555` 或 `emulator-5554` (可能不同)
**注意**: 多开时端口递增 (5555, 5556, 5557, ...)

**GAF 自动发现**:
```python
# agent/src/devices/emulator_discovery.py
import socket
import subprocess

def discover_ldplayer_instances() -> list:
    """扫描 LDPlayer 端口 (5555-5605)"""
    instances = []
    for port in range(5555, 5605):
        if is_port_open('127.0.0.1', port):
            instances.append(f'127.0.0.1:{port}')
    return instances

def is_port_open(host: str, port: int) -> bool:
    """检查端口是否开放"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect((host, port))
        sock.close()
        return True
    except:
        return False
```

### 3.2 BlueStacks

**特点**: 老牌, 跨平台, 多语言
**ADB 连接**: `adb connect 127.0.0.1:5555`
**注意**: BlueStacks 5+ 默认开 ADB, 旧版需手动开

### 3.3 Android Studio AVD

**特点**: 官方, 调试友好
**ADB 连接**: `adb connect <avd_name>-<port>` 或自动
**Serial 格式**: `emulator-5554` (固定)

## 4. 真机 (USB 调试)

### 4.1 启用 USB 调试

```
[Step 1] 设置 → 关于手机 → 连续点击 "版本号" 7 次 → 开启"开发者选项"
[Step 2] 开发者选项 → 打开 "USB 调试"
[Step 3] 用 USB 连接电脑
[Step 4] 手机弹窗 "允许 USB 调试" → 勾选 "始终允许" → 确定
```

### 4.2 验证连接

```bash
adb devices
# 应看到 <serial>    device
```

### 4.3 常见问题

| 问题 | 解决 |
|------|------|
| device unauthorized | 重新插拔 USB, 重新授权 |
| device offline | `adb kill-server && adb start-server` |
| 多设备时命令错乱 | `adb -s <serial> ...` 显式指定 |
| 无线 ADB | `adb tcpip 5555` + `adb connect <ip>:5555` |

## 5. 4 个 AI 易错点

### 5.1 ❌ 假设 serial 格式 (N10)

**错误**: 默认 serial = `emulator-5554` 或 `127.0.0.1:5555`
**后果**: 找不到 LDPlayer 实例
**正确**: 用 `adb devices` 动态获取, 不假设格式

### 5.2 ❌ 多设备命令错乱 (N73)

**错误**: `adb shell input tap 100 100` 多设备时
**后果**: 不知道操作哪个设备
**正确**: `adb -s <serial> shell input tap 100 100` 显式指定

### 5.3 ❌ 中文 input 失败 (N74)

**错误**: `adb shell input text "你好"`
**后果**: 中文乱码或失败
**正确**: 安装 `ADBKeyboard.apk`, 切换输入法后用 `input text` 发送 base64

### 5.4 ❌ 截图被状态栏干扰 (N75)

**错误**: 截图含状态栏, 坐标偏移
**后果**: 模板匹配失败
**正确**: 状态栏高度通常 24-72px, `effective_y = click_y - status_bar_height`

## 6. 速查表

| 场景 | ADB 命令 | 备注 |
|------|----------|------|
| 截屏 | `adb exec-out screencap -p` | exec-out 避免文件 |
| 点击 | `adb shell input tap X Y` | 屏幕坐标 |
| 滑动 | `adb shell input swipe X1 Y1 X2 Y2 MS` | duration_ms |
| 按键 | `adb shell input keyevent KEYCODE_X` | 整型 keycode |
| 文本 | `adb shell input text "..."` | 不支持中文 |
| 唤醒屏幕 | `adb shell input keyevent KEYCODE_WAKEUP` | 26 |
| 滑动解锁 | `adb shell input swipe 500 1500 500 500 300` | 上滑解锁 |

## 7. 相关文件

- `agent/src/devices/adb/device.py` - ADB 设备控制
- `agent/src/devices/adb/pool.py` - 设备池管理
- `agent/src/devices/emulator_discovery.py` - 模拟器自动发现
- `backend/device_bridge/discovery/emulator.py` - 后端模拟器发现
- `agent/src/devices/window_discovery.py` - 窗口发现

## 8. 反思 (Reflection)

- **ADB 是 GAF 移动端核心**: 80% 移动端控制走 ADB
- **LDPlayer 是 BD2 主力**: 中文用户多, 性能好
- **多设备是常态**: 玩家多开, GAF 必须显式 serial
- **中文输入是难点**: 需 ADBKeyboard 插件
- **4 易错点都是"假设"**: serial 格式/单设备/英文/无状态栏
- **相关**: windows.md / linux.md / macos.md / ios.md
