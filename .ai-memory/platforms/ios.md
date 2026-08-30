---
maintainer: manual
source: Apple iOS 自动化限制 + libimobiledevice + WebDriverAgent
load_when:
- 新功能 (iOS 设备)
- 调研 iOS 自动化方案
- 平台选型
priority: low
symptom:
- kb:platform:ios
- ios-automation
- 越狱
- WebDriverAgent
solution: 3 自动化方案 (WebDriverAgent/libimobiledevice/Mac Xcode) + 4 限制 + 2 推荐 (实际多走模拟器)
related_files:
- worker/src/devices/adb/device.py
- backend/device_bridge/platforms/windows/_adb_input.py
created_by: AI
generated: 2026-06-16
last_manual_edit: 2026-06-16
---
# iOS Platform (iOS 设备) - GAF 速查

> **适用场景**: AI 调研 iOS 自动化方案 / 平台选型决策
> **GAF 状态**: 🔧 弱支持 (技术限制 + 道德风险)
> **核心结论**: iOS 自动化受限, 实际场景多走 iOS 模拟器 (macOS) 或转向 Android 设备

## 1. 平台特性

| 项 | 内容 |
|----|------|
| **最低版本** | iOS 13+ (WebDriverAgent 支持) |
| **推荐版本** | iOS 15+ |
| **架构** | arm64 (真机) / x86_64 + arm64 (模拟器) |
| **截图 API** | `xcrun simctl io ... screenshot` (模拟器) |
| **输入 API** | `xcrun simctl io ... tap` (模拟器) |
| **真机输入** | ❌ 需越狱 + 私有 API |
| **App Store** | ❌ 沙盒限制, 无法自动化 |
| **企业证书** | 🟡 灰色地带, 90 天过期 |
| **越狱** | ❌ 风险高, 仅老设备 |

## 2. 3 大自动化方案

### 2.1 方案 A: iOS 模拟器 (推荐, 走 macOS)

**优势**: 官方支持, 无需越狱, 完整 API
**限制**: 仅 macOS 主机, 性能一般
**工具链**: Xcode + iOS Simulator + simctl

**截图**:
```bash
# 列出已安装模拟器
xcrun simctl list devices

# 启动模拟器
xcrun simctl boot "iPhone 15"

# 截屏
xcrun simctl io booted screenshot screenshot.png
```

**点击**:
```bash
# 启动 app
xcrun simctl launch booted com.example.app

# 截屏
xcrun simctl io booted screenshot screenshot.png

# 注意: simctl 没有官方 tap 命令, 需用其他方法
# 方案 1: AppleScript + Simulator app
# 方案 2: xcode-build-server + xcuitest
# 方案 3: WebDriverAgent (WDA)
```

**GAF 状态**: 🔧 待实现, 与 macOS 平台集成

### 2.2 方案 B: WebDriverAgent (WDA) - 真机/越狱

**来源**: Facebook 开源, Appium 用它
**原理**: 在手机上装一个 WebDriver 兼容 agent app
**限制**:
- 真机: 需企业证书或开发者签名
- 越狱: 风险高, 不推荐
- App Store: ❌ 不能上架

**截图**:
```bash
# WDA 默认端口 8100
curl http://localhost:8100/session
curl http://localhost:8100/session/<session_id>/screenshot
```

**点击**:
```bash
curl -X POST http://localhost:8100/session/<session_id>/wda/tap \
  -H "Content-Type: application/json" \
  -d '{"x": 100, "y": 200}'
```

**GAF 状态**: ❌ 未实现, 复杂度高

### 2.3 方案 C: libimobiledevice (C 库) - 真机底层

**原理**: 与 iOS 设备通信, 绕过 iTunes
**用途**: 文件传输, 应用安装, 截图
**限制**: 不能直接发送触摸事件, 需配合 WebDriverAgent

**安装**:
```bash
# macOS
brew install libimobiledevice

# Linux
sudo apt install libimobiledevice-utils
```

**截图**:
```bash
idevicescreenshot screenshot.png
```

**应用安装**:
```bash
ideviceinstaller -i app.ipa
```

**GAF 状态**: ❌ 未实现

## 3. 4 大限制

### 3.1 沙盒限制 (App Store)

**问题**: App Store 应用沙盒, 不能被其他 app 自动化
**影响**: 用户装的 BD2 (App Store 版) 无法被 GAF 控制
**解决**: 用企业证书重签 + 模拟器, 但违反 Apple 政策

### 3.2 企业证书过期 (90 天)

**问题**: 企业证书 90 天过期, 需重新签名
**影响**: 真机自动化断续, 不可持续
**解决**: 用开发者个人证书 ($99/年), 但限制 3 设备

### 3.3 越狱风险

**问题**: 越狱后系统不稳定, 安全风险高
**影响**: 自动化脚本可能在越狱版本失效
**解决**: 仅 iOS 14 及以下可越狱, 不推荐

### 3.4 App Store 政策

**问题**: Apple 明确禁止自动化控制其他 app
**影响**: 商业化 GAF for iOS 有法律风险
**解决**: GAF for iOS 限定个人使用 / 模拟器

## 4. GAF 推荐策略 (3 选项)

### 4.1 选项 A: 走 iOS 模拟器 (✅ 推荐)

**适用**: 开发调试, 模板测试
**实现**:
- macOS 主机 + Xcode + iOS Simulator
- `xcrun simctl` 命令封装为 GAF device
- 截图 + 模板匹配, 与 Android 一致
**优势**: 官方支持, 无风险
**限制**: 需 macOS, 性能一般

### 4.2 选项 B: 走 macOS Catalyst (🟡 中等)

**适用**: 同一 app 跑 macOS 和 iPad
**实现**: Catalyst app, 然后用 macOS 截图/输入
**优势**: 一次开发, 多平台
**限制**: 仅 Catalyst app, 主流游戏不支持

### 4.3 选项 C: 真机 + 企业证书 (❌ 不推荐)

**适用**: 内部测试
**实现**: WebDriverAgent + 企业证书
**优势**: 真机性能
**限制**: 90 天过期, 政策风险

## 5. BD2 玩家实际场景 (80%)

**观察**: 80%+ BD2 玩家在 Android 设备/iOS 模拟器, 纯 iOS 真机自动化罕见
**原因**:
- iOS 自动化成本高 (需 macOS + Xcode)
- App Store 限制
- 企业证书 90 天过期

**GAF 建议**:
- **Android 真机/模拟器** (主力, 80% 玩家)
- **iOS 模拟器** (macOS 开发者)
- **iOS 真机** (不推荐, 复杂度过高)

## 6. 3 个 AI 易错点

### 6.1 ❌ 假设 iOS = iOS 模拟器 (N77)

**错误**: 写代码默认是模拟器, 实际是真机
**后果**: 真机上失败
**正确**: 显式区分 `device_type=real|simulator`

### 6.2 ❌ 用 App Store 政策做自动化 (N78)

**错误**: 假设可以自动化 App Store 应用
**后果**: 政策风险, 上架被拒
**正确**: 限定 iOS 模拟器 / Catalyst

### 6.3 ❌ 假设企业证书永久 (N79)

**错误**: 写代码假设企业证书一直在
**后果**: 90 天后全失效
**正确**: 加证书过期检测 + 重新签名流程

## 7. 速查表

| 场景 | 推荐方案 | 备注 |
|------|----------|------|
| 开发调试 | iOS Simulator + simctl | macOS 必需 |
| 模板测试 | iOS Simulator | 1284x2778 (iPhone 15 Pro Max) |
| 真机自动化 | WebDriverAgent | 需企业证书 |
| 性能基准 | iOS Simulator | Apple Silicon 性能好 |
| 商业化 | ❌ 政策风险 | 限定内部使用 |
| BD2 玩家 | Android 80% / iOS 模拟器 20% | 实际分布 |

## 8. 相关文件

- `worker/src/devices/adb/device.py` - 参考 ADB 模式设计 iOS 设备
- `backend/device_bridge/platforms/windows/_adb_input.py` - 跨平台参考
- (待) `worker/src/devices/ios/device.py` - iOS 设备 (未实现)

## 9. 反思 (Reflection)

- **iOS 自动化是高门槛**: macOS + Xcode + 企业证书 / 越狱
- **GAF 主力是 Android**: 80% 玩家, 自动化成熟
- **iOS 模拟器是妥协方案**: 满足开发调试需求
- **企业证书 90 天过期**: 真机自动化不可持续
- **3 选项中 A (模拟器) 是最佳**: 官方支持 + 无政策风险
- **相关**: windows.md / linux.md / macos.md / android.md
