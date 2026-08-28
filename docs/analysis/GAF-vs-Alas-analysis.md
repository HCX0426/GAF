---
summary: GAF vs AzurLaneAutoScript (Alas) 对比分析
applies_to: ['architecture', 'design']
key_decisions:
  - 对比概述
last_updated: 2026-08-17 (s30 确认仍有效)
---

# GAF vs AzurLaneAutoScript (Alas) 对比分析

> 版本：3.0 | 日期：2026-05-23

## 对比概述

| 维度 | GAF | Alas |
|------|-----|------|
| **定位** | 通用游戏自动化框架（Game Automation Framework） | 碧蓝航线专用自动化脚本 |
| **架构** | Agent-Server-Client 三层架构 | Device + Config + Task 三层 |
| **语言** | Python (Django) + React/TypeScript | Python |
| **目标** | 多游戏、多设备、分布式自动化 | 碧蓝航线 7×24 小时稳定运行 |
| **Web UI** | React + Ant Design | FastAPI + Vue.js |
| **LLM 集成** | 内置（DeepSeek/OpenAI/本地模型） | ❌ |
| **设备支持** | Windows 窗口 + 多模拟器 + Android | 仅模拟器（通过 ADB） |
| **任务定义** | JSON/YAML 可序列化定义 | Python 函数式 |

**Alas 核心可借鉴点**：ADB 截图（10种方式最全 + 连接池 + 基准测试）、模拟器管理（5种自动发现 + 生命周期管理）、7×24异常恢复（5层渐进式策略）、YAML→GUI 自动生成、配置版本迁移机制。

---

以下为 Alas 深度源码分析原文：

# AzurLaneAutoScript (Alas) 深度源码分析

## 一、项目概览

| 属性 | 说明 |
|------|------|
| 语言 | Python |
| 许可证 | MIT |
| 目标 | 碧蓝航线自动化，7×24 小时稳定运行 |
| 核心架构 | **Device + Config + Task** 三层 |

Alas 是一个面向碧蓝航线（Azur Lane）的全自动化脚本框架，其设计目标是在无人值守条件下实现 7×24 小时持续运行。项目采用三层架构：

- **Device 层**：负责与模拟器/设备的底层交互，包括截图、点击、滑动等操作
- **Config 层**：管理所有配置项，支持 YAML 定义、GUI 自动生成、版本迁移
- **Task 层**：基于 Device 和 Config 实现具体游戏任务的业务逻辑

---

## 二、设备控制层 (module/device)

设备控制层是 Alas 最核心也最复杂的模块，它抽象了多种截图和输入方式，并通过降级链机制保证在不同环境下的兼容性和性能。

### 2.1 截图方法降级链

Alas 支持 **10 种截图方式**，按性能从高到低排列：

| 序号 | 方法 | 实现原理 | 性能 |
|------|------|----------|------|
| 1 | **NemuIpc** | MuMu12 共享内存 IPC | ★★★★★ |
| 2 | **scrcpy** | H.264 视频流解码 | ★★★★ |
| 3 | **DroidCast_raw** | HTTP 获取原始像素数据 | ★★★★ |
| 4 | **DroidCast** | HTTP 获取 PNG 截图 | ★★★ |
| 5 | **uiautomator2** | uiautomator2 框架截图 | ★★ |
| 6 | **aScreenCap** | ADB shell screencap 压缩传输 | ★★ |
| 7 | **aScreenCap_nc** | aScreenCap + netcat 传输（绕过 ADB 编码开销） | ★★+ |
| 8 | **ADB (screencap)** | ADB shell screencap 原始传输 | ★ |
| 9 | **ADB_nc** | ADB screencap + netcat 传输（绕过 ADB 编码开销） | ★+ |
| 10 | **LDOpenGL** | 雷电模拟器 OpenGL 截图 | ★★★ |

**核心实现细节：**

- `Device.screenshot_methods` 字典将配置字符串映射到具体方法类：

```python
self.screenshot_methods = {
    'auto': ScreenshotAuto,
    'nemu_ipc': NemuIpc,
    'scrcpy': AdbScrcpy,
    'droidcast_raw': DroidCastRaw,
    'droidcast': DroidCast,
    'uiautomator2': Uiautomator2,
    'ascreencap': AScreenCap,
    'ascreencap_nc': AScreenCapNc,
    'adb': Adb,
    'adb_nc': AdbNc,
    'ldopengl': LDOpenGL,
}
```

- `method_check()` 方法检查截图方法与输入方法的组合合法性，某些组合可能不兼容（如 NemuIpc 截图 + ADB 输入）
- 内置基准测试（benchmark），自动选择当前环境下最快的截图方法
- 降级链机制：当首选方法失败时，自动尝试次优方法

### 2.2 输入方法降级链

Alas 支持 **6 种输入方式**：

| 序号 | 方法 | 实现原理 | 精度 |
|------|------|----------|------|
| 1 | **MaaTouch** | MaaFramework 触控注入 | ★★★★★ |
| 2 | **minitouch** | minitouch Android 工具 | ★★★★ |
| 3 | **NemuIpc** | MuMu12 共享内存 IPC 触控（nemu_input_event_touch_down/up） | ★★★★ |
| 4 | **uiautomator2** | uiautomator2 框架输入 | ★★★ |
| 5 | **Hermit** | Hermit 输入法 | ★★ |
| 6 | **ADB (input)** | ADB shell input 命令 | ★ |

**核心实现细节：**

- `Device.click_methods` 字典映射配置字符串到方法类：

```python
self.click_methods = {
    'maatouch': MaaTouch,
    'minitouch': Minitouch,
    'nemu_ipc': NemuIpcInput,
    'uiautomator2': Uiautomator2,
    'hermit': Hermit,
    'adb': AdbInput,
}
```

- 输入方法与截图方法**独立选择**，用户可以自由组合
- 每种输入方法都实现了统一的 `click()`, `swipe()`, `press()` 接口
- 降级链：当高精度方法不可用时，自动回退到低精度方法

### 2.3 NemuIpc 实现

NemuIpc 是 Alas 中性能最高的截图方式，利用 MuMu12 模拟器的共享内存 IPC 机制：

**底层调用链：**

```
Python → ctypes → external_renderer_ipc.dll → MuMu12 共享内存
```

**serial_to_id 映射逻辑：**

NemuIpc 需要将 ADB serial（如 `127.0.0.1:16384`）映射为 MuMu 实例 ID，映射规则如下：

- 端口起始值：16384
- 每个实例间隔：32 个端口
- 计算公式：`instance_id = (port - 16384) // 32`

```python
def serial_to_id(serial: str) -> int:
    """将 ADB serial 映射为 MuMu 实例 ID"""
    port = int(serial.split(':')[1])
    return (port - 16384) // 32
```

**核心 API：**

| API 函数 | 功能 |
|----------|------|
| `nemu_connect` | 建立与 MuMu 实例的 IPC 连接 |
| `nemu_capture_display` | 从共享内存获取截图数据 |
| `nemu_input_event_touch_down` | 模拟触摸按下 |
| `nemu_input_event_touch_up` | 模拟触摸抬起 |

**stderr 捕获版本不兼容检测：**

调用 `nemu_connect` 时会捕获 stderr 输出，检测 DLL 版本是否兼容。不兼容时 stderr 中会包含特定错误码：

| 错误码 | 含义 |
|--------|------|
| 1783 | Stub 接收了错误数据（DLL 版本过旧） |
| 1745 | 存根收到了错误数据 |
| 1722 | RPC 服务器不可用 |
| 1726 | 远程过程调用失败 |

```python
def _check_compatibility(stderr_output: str) -> bool:
    """检测 DLL 版本是否兼容"""
    incompatible_codes = ['1783', '1745', '1722', '1726']
    for code in incompatible_codes:
        if code in stderr_output:
            return False
    return True
```

**连接池机制：**

- 使用 `WorkerPool` 管理连接，8 个工作线程，10 秒空闲超时
- Job 超时杀线程：通过 `ctypes.PyThreadState_SetAsyncExc` 向目标线程注入异常
- **0.5 秒超时杀线程**：截图操作设置 0.5 秒超时，超时后立即杀线程防止阻塞
- 线程安全的任务提交和结果获取

**关键代码流程：**

```python
# 连接建立
connection = nemu_connect(instance_id, display_id)

# 截图获取
width, height, data = nemu_capture_display(connection, ...)

# 触摸输入
nemu_input_event_touch_down(connection, x, y)
nemu_input_event_touch_up(connection)
```

### 2.4 scrcpy 实现

scrcpy 方式通过独立子进程 + H.264 视频流解码实现截图和输入：

**架构：**

```
Python → python-scrcpy 库 → scrcpy server (设备端) → H.264 视频流
```

**核心特性：**

- 使用 `python-scrcpy` 库封装 scrcpy 协议
- 独立子进程运行 scrcpy server，避免阻塞主线程
- H.264 视频流实时解码，获取当前帧作为截图
- 支持 `click()`, `swipe()`, `press()` 操作
- 视频流持续推送，截图延迟极低

**优势与局限：**

- 优势：截图延迟低，兼容性好
- 局限：需要部署 scrcpy server 到设备，首次连接有初始化开销

### 2.5 DroidCast 实现

DroidCast 通过 HTTP 服务获取截图，支持两种模式：

| 模式 | 数据格式 | 性能 |
|------|----------|------|
| **DroidCast_raw** | 原始像素数据 (RGBA) | 高 |
| **DroidCast** | PNG 图片 + lz4 压缩 | 中 |

**自动部署流程：**

1. 检测设备是否已安装 DroidCast APK
2. 若未安装，通过 ADB 推送 APK 并安装
3. 启动 DroidCast 服务（HTTP 服务器）
4. 通过 HTTP GET 请求获取截图

**核心请求：**

```python
# DroidCast_raw 模式
response = requests.get(f'http://127.0.0.1:{port}/screenshot?format=raw')
image = np.frombuffer(response.content, dtype=np.uint8).reshape(height, width, 4)

# DroidCast 模式
response = requests.get(f'http://127.0.0.1:{port}/screenshot')
image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
```

### 2.6 模拟器管理 (module/device/platform)

Alas 支持 **5 种途径**自动发现和管理模拟器实例：

| 途径 | 具体实现 | 适用模拟器 |
|------|----------|-----------|
| MuiCache 注册表 | 读取 `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\MuiCache` 中的模拟器路径 | MuMu、BlueStacks |
| UserAssist 注册表（ROT13 解码） | 读取 `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist` 下的 ROT13 编码条目并解码 | 所有模拟器 |
| 安装路径注册表 | 读取模拟器在注册表中写入的安装路径键值 | LDPlayer、MuMu |
| 卸载注册表 | 读取 `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` 下的卸载信息 | 所有模拟器 |
| 运行中进程扫描 | 扫描系统进程列表，匹配已知模拟器进程名 | 所有模拟器 |

**支持模拟器（8 类）：**

| 模拟器 | 版本 | 进程标识 |
|--------|------|----------|
| NoxPlayer | 32 位 / 64 位 | Nox.exe / Nox64.exe |
| BlueStacks | 4 / 5 | BlueStacks.exe / HD-Player.exe |
| LDPlayer | 3 / 4 / 9 / 14 | dnplayer.exe / ldconsole.exe |
| MuMu | 6 / X / 12 | NemuPlayer.exe / MuMuPlayer.exe |
| MEmuPlayer | - | MEmu.exe / MEmuConsole.exe |

**实例发现逻辑：**

| 模拟器 | 发现方式 | 具体实现 |
|--------|----------|----------|
| Nox | 解析 vbox 文件 | 扫描 `Nox/bin/BignoxVMS/` 目录，解析 `*.vbox` 获取 `hostport` |
| BlueStacks 5 | 读 bluestacks.conf | 解析 `{安装路径}/bluestacks.conf`，提取 `bst.instance.*.status.adb_port` |
| LDPlayer | 端口公式 | ADB 端口 = `index * 2 + 5555`，通过 `ldconsole list` 获取实例索引 |
| MuMu 12 | 解析 .nemu vbox 文件 | 扫描 `MuMu/Shell/MuMuPlayerGlobal-12.0/vms/` 目录，解析 `*.nemu` 获取 ADB 端口 |

**ADB 端口发现：**

- 解析 `*.vbox` 配置文件，提取 `hostport` 字段获取 ADB 端口
- 支持 `ADB forward` 和 `ADB reverse` 两种端口映射方式
- 自动处理端口冲突和重映射

**模拟器生命周期管理：**

```python
# 启动模拟器
emulator.start()

# 多实例管理
instances = emulator.list_instances()

# 等待模拟器就绪
emulator.wait_until_boot()
```

### 2.7 截图连接池 (pool.py)

截图连接池是 Alas 设备层的核心基础设施，解决了频繁截图时的连接管理和超时问题：

**WorkerPool 设计：**

| 参数 | 值 | 说明 |
|------|-----|------|
| 工作线程数 | 8 | 并发处理截图请求 |
| 空闲超时 | 10 秒 | 线程空闲后自动释放资源 |
| Job 超时 | 可配置 | 防止截图操作永久阻塞 |

**Outcome 模式：**

每个 Job 的结果使用 Outcome 封装，类似 Rust 的 Result 类型：

```python
class Outcome:
    """任务执行结果封装"""
    Value = 'Value'   # 正常结果
    Error = 'Error'   # 异常结果

class Job:
    def __init__(self, func, *args, **kwargs):
        self._result = None
        self._outcome = None
        self._event = threading.Event()

    def get(self, timeout=None):
        """获取结果，超时抛出 TimeoutError"""
        if not self._event.wait(timeout):
            raise TimeoutError
        if self._outcome == Outcome.Error:
            raise self._result
        return self._result
```

**池满处理（notify_worker / notify_pool 双 Lock）：**

当连接池已满时，使用双锁机制协调生产者和消费者：

```python
class WorkerPool:
    def __init__(self, size=8):
        self._pool = queue.Queue(maxsize=size)
        self._notify_worker = threading.Lock()  # 通知工作线程
        self._notify_pool = threading.Lock()    # 通知连接池
        self._workers = []

    def _handle_pool_full(self):
        """池满时等待空闲连接"""
        with self._notify_pool:
            self._notify_worker.acquire()
            try:
                self._notify_worker.release()
            except RuntimeError:
                pass
```

**高级 API：**

| API | 说明 |
|-----|------|
| `wait_jobs(jobs)` | 等待所有 Job 完成，返回结果列表 |
| `gather_jobs(jobs)` | 收集所有 Job 的结果，异常以 Outcome.Error 返回 |
| `thread_map(func, iterable)` | 对可迭代对象的每个元素并行执行 func |
| `thread_starmap(func, iterable)` | 同 thread_map，但解包参数 |
| `thread_funcmap(func_map, args)` | 按函数映射分发任务，每个参数对应不同的处理函数 |

**超时杀线程机制：**

```python
import ctypes

def _kill_thread(thread):
    """通过向目标线程注入异常来终止线程"""
    thread_id = thread.ident
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thread_id),
        ctypes.py_object(SystemExit)
    )
    if res == 0:
        raise ValueError("Invalid thread ID")
    elif res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(thread_id),
            None
        )
        raise SystemError("PyThreadState_SetAsyncExc failed")
```

**线程安全保证：**

- 使用 `queue.Queue` 实现任务提交和结果获取
- 每个 Job 包含 `event` (threading.Event) 用于结果通知
- Worker 循环从队列取任务，执行后设置结果和事件

---

## 三、配置系统 (module/config)

Alas 的配置系统是其最精巧的设计之一，实现了从 YAML 定义到 GUI 界面的全自动生成。

### 3.1 YAML 到 GUI 自动生成

配置系统的核心流程：

```
task.yaml + argument.yaml + override.yaml + default.yaml → args.json → config_generated.py + i18n/*.json + menu.json + deploy template
```

**各文件职责：**

| 文件 | 职责 | 示例 |
|------|------|------|
| `task.yaml` | 定义任务特定参数 | `Commission_Task: {type: check, value: true}` |
| `argument.yaml` | 定义参数类型、范围、选项 | `Emulator_Serial: {type: input, value: "auto"}` |
| `override.yaml` | 覆盖默认值 | 修改特定任务的默认参数 |
| `default.yaml` | 默认配置 | 所有参数的默认值汇总 |
| `args.json` | 中间格式 | YAML 解析后的 JSON 表示 |
| `config_generated.py` | 生成的 Python 配置类 | 可被代码直接引用的配置类 |
| `i18n/*.json` | 国际化翻译 | 中英文翻译文件 |
| `menu.json` | GUI 菜单结构 | 左侧导航栏的层级结构 |
| deploy template | 部署配置模板 | 生成 deploy.yaml 等部署文件 |

**ConfigGenerator 与 ConfigUpdater 职责：**

| 组件 | 职责 |
|------|------|
| `ConfigGenerator` | 首次生成：解析所有 YAML 源文件，合并生成 `args.json`，再从 `args.json` 生成 `config_generated.py`、`menu.json`、`i18n/*.json`、deploy template |
| `ConfigUpdater` | 增量更新：检测 YAML 源文件变更，仅重新生成受影响的部分，避免全量重建 |

**redirection 重定向机制：**

配置项支持重定向，允许一个配置组的值动态指向另一个配置组：

```python
# 当用户切换任务时，重定向机制自动将配置指向对应任务的参数组
@property
def redirection(self):
    """配置重定向，将当前任务参数映射到实际配置组"""
    task = self.Scheduler_Command
    return getattr(self, f'{task}_Arguments', {})
```

**save_callback 回调：**

配置保存时支持回调函数，用于在保存后执行额外逻辑：

```python
def save_callback(func):
    """配置保存后的回调装饰器"""
    def wrapper(self, *args, **kwargs):
        result = func(self, *args, **kwargs)
        self._run_save_callbacks()
        return result
    return wrapper
```

**argument.yaml 参数类型：**

```yaml
# 输入框
Emulator_Serial:
  type: input
  value: "auto"

# 下拉选择
ScreenshotMethod:
  type: select
  option: [auto, nemu_ipc, scrcpy, droidcast_raw, droidcast, uiautomator2, ascreencap, adb]
  value: auto

# 复选框
Commission_Task:
  type: checkbox
  value: true

# 滑块
Emulator_ScreenshotDeduction:
  type: slider
  min: 0
  max: 300
  value: 0

# 颜色选择器
MapGridLineColor:
  type: color
  value: "#000000"
```

**code_generator.py 生成逻辑：**

1. 解析 `argument.yaml`，构建参数树
2. 合并 `task.yaml` 和 `override.yaml` 的覆盖
3. 生成 `args.json` 中间格式
4. 从 `args.json` 生成 `config_generated.py`（Python 配置类）
5. 生成 `menu.json`（GUI 菜单结构）
6. 生成 `i18n/*.json`（国际化翻译）

### 3.2 配置更新机制

**config_updater.py — 版本迁移：**

- 当配置格式发生变更时，自动将旧版本配置迁移到新版本
- 迁移函数按版本号顺序执行，确保兼容性
- 支持字段重命名、类型变更、默认值更新等操作

```python
def update_config(config, old_version, new_version):
    """将配置从 old_version 迁移到 new_version"""
    for version in range(old_version + 1, new_version + 1):
        migrator = MIGRATIONS.get(version)
        if migrator:
            config = migrator(config)
    return config
```

**deep.py — 深度合并配置：**

- 递归合并两个字典，保留旧配置中未变更的值
- 新增字段使用默认值
- 删除的字段自动清理

```python
def deep_merge(old_dict, new_dict):
    """深度合并两个字典，new_dict 优先"""
    result = old_dict.copy()
    for key, value in new_dict.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
```

**watcher.py — 文件监控自动重载：**

- 极简实现，仅 **33 行**代码
- 使用 `os.stat().st_mtime` 检测文件修改时间，不依赖 watchdog 库
- 轮询方式检测配置文件变化，自动重新加载配置
- 防抖机制：短时间内多次变更只触发一次重载

```python
import os

class FileWatcher:
    """极简文件监控，基于 mtime 检测变化"""
    def __init__(self, filepath):
        self.filepath = filepath
        self._last_mtime = os.stat(filepath).st_mtime

    def modified(self):
        """检测文件是否被修改"""
        current_mtime = os.stat(self.filepath).st_mtime
        if current_mtime != self._last_mtime:
            self._last_mtime = current_mtime
            return True
        return False
```

---

## 四、基础模块 (module/base)

基础模块提供了所有上层模块共用的工具类和装饰器。

### 4.1 模板匹配 (template.py)

基于 OpenCV 的模板匹配系统，是 Alas 图像识别的核心：

**Button 类：**

```python
class Button:
    """封装模板图片 + ROI 区域的按钮对象"""
    def __init__(self, file, area, search, color, button):
        self.file = file          # 模板图片路径
        self.area = area          # ROI 区域 (x1, y1, x2, y2)
        self.search = search      # 搜索区域
        self.color = color        # 颜色阈值
        self.button = button      # 点击位置
        self.image = load_image(file)  # 预加载模板图片
```

**匹配流程：**

1. 在搜索区域内使用 `cv2.matchTemplate` 进行模板匹配
2. 计算匹配度，与阈值比较
3. 支持多阈值：不同按钮可设置不同匹配阈值
4. 返回匹配位置和置信度

### 4.2 重试装饰器 (retry.py)

提供灵活的重试机制，用于处理网络波动、模拟器卡顿等瞬时错误：

```python
@retry(retries=3, delay=1, exception=(ConnectionError, TimeoutError))
def some_operation():
    """带重试的操作"""
    pass
```

**参数说明：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `retries` | int | 最大重试次数 |
| `delay` | float | 重试间隔（秒） |
| `exception` | tuple | 需要重试的异常类型 |

### 4.3 计时器 (timer.py)

Timer 类提供超时检测和周期触发功能：

```python
class Timer:
    """计时器，用于超时检测和周期触发"""

    def __init__(self, limit):
        self.limit = limit
        self.start = time.time()

    def reached(self):
        """是否已超时"""
        return time.time() - self.start > self.limit

    def reset(self):
        """重置计时器"""
        self.start = time.time()

    def wait(self):
        """等待直到超时"""
        remaining = self.limit - (time.time() - self.start)
        if remaining > 0:
            time.sleep(remaining)
        self.reset()
```

### 4.4 异常恢复策略

Alas 的异常恢复策略是其能实现 7×24 小时稳定运行的关键：

**卡顿检测 — stuck_timer：**

- 短卡顿：60 秒无进展触发恢复
- 长卡顿：180 秒无进展触发更激进的恢复
- 通过检测游戏画面是否持续停留在同一状态判断

**点击记录 — click_record：**

- 使用 `collections.deque(maxlen=15)` 记录最近 15 次点击位置
- 检测是否陷入重复点击循环（同一区域反复点击）
- 若检测到循环，切换策略或执行恢复操作

**统一异常恢复模式：**

每个模块自定义 `retry` 装饰器，按异常类型匹配对应的恢复函数：

| 异常类型 | 恢复函数 | 说明 |
|----------|----------|------|
| `RequestHumanTakeover` | 立即终止 | 不可恢复错误，直接停止任务 |
| `ConnectionResetError` | `adb_reconnect` | ADB 连接断开，重新连接 |
| `AdbError` | `adb_reconnect` / `adb_start_server` | ADB 命令失败，尝试重连或重启 ADB 服务 |
| 模块特定错误 | 对应 `init` 函数 | 如截图方法失败→重新初始化截图，模拟器断连→重启模拟器 |

**重试耗尽处理：**

当所有重试次数耗尽后，抛出 `RequestHumanTakeover` 异常，触发人工接管流程：

```python
def retry_wrapper(func):
    """模块自定义 retry 装饰器"""
    def wrapper(self, *args, **kwargs):
        for attempt in range(self.retry_count):
            try:
                return func(self, *args, **kwargs)
            except RequestHumanTakeover:
                raise
            except ConnectionResetError:
                self.adb_reconnect()
            except AdbError:
                self.adb_reconnect()
                self.adb_start_server()
            except Exception as e:
                handler = self.exception_handlers.get(type(e))
                if handler:
                    handler()
                else:
                    raise
        raise RequestHumanTakeover
    return wrapper
```

**RequestHumanTakeover — 最终降级：**

```python
class RequestHumanTakeover(Exception):
    """请求人工接管，所有自动恢复策略均已失败"""
    pass
```

当触发此异常时，Alas 会：
1. 停止当前任务
2. 通过配置的通知渠道（Discord/Webhook）发送告警
3. 等待人工干预后恢复运行

---

## 五、Web UI (module/webui)

Alas 提供了基于 FastAPI + Vue.js 的 Web 管理界面：

**技术栈：**

| 组件 | 技术 |
|------|------|
| 后端 | FastAPI |
| 前端 | Vue.js |
| 通信 | REST API + WebSocket |
| 部署 | Uvicorn ASGI 服务器 |

**核心功能：**

1. **配置界面自动生成**：基于 `menu.json` 和 `args.json` 自动生成配置表单
2. **任务管理**：启动/停止/调度自动化任务
3. **日志查看**：实时查看运行日志
4. **远程访问**：支持通过浏览器远程控制
5. **Discord Presence 集成**：在 Discord 显示当前运行状态

**配置界面生成流程：**

```
menu.json → Vue.js 动态组件 → 配置表单
args.json → 参数类型/范围/选项 → 输入控件
i18n/*.json → 多语言翻译
```

---

## 六、GAF 可借鉴点

以下是 Alas 中值得 GAF 项目借鉴的核心设计：

| # | 课题 | 当前状态 | 说明 |
|---|------|---------|------|
| 1 | 截图连接池（WorkerPool + 超时杀线程） | ✅ 已实现 | GAF已有FramePool+超时杀线程机制 |
| 2 | 模拟器自动发现（5种注册表/进程扫描） | ✅ 已实现 | `emulator_discovery.py` — 注册表+进程+路径扫描 |
| 3 | YAML→GUI 自动生成机制 | ❌ 未实现 | 配置定义与界面代码解耦，新增配置项无需修改前端 |
| 4 | 7×24 异常恢复策略（5层） | ✅ 已实现 | `recovery.py` — 5层渐进式策略，缺模拟器重启/人工接管 |
| 5 | 配置版本迁移机制 | ❌ 未实现 | 配置格式变更时的平滑升级 |
| 6 | ADB 端口映射（forward/reverse） | ✅ 已实现 | ADB设备完整支持，端口映射已集成 |

> **GAF 已超越 Alas 的能力：**
>
> | 能力 | GAF | Alas |
> |------|-----|------|
> | **Windows 截图 (WGC/GDI)** | ✅ 4种+竞速 | ❌ 纯ADB |
> | **Pipeline 图执行引擎** | ✅ 16节点+校验器 | ❌ 函数式 |
> | **ChainManager 链式执行** | ✅ | ❌ |
> | **ONNX 推理 (YOLOv8)** | ✅ DirectML/CUDA | ❌ |
> | **AI 分割 (SAM/U²-Net)** | ✅ | ❌ |
> | **录制回放系统** | ✅ | ❌ |
> | **脚本 DSL** | ✅ | ❌ |
> | **设备插件系统** | ✅ | ❌ |
> | **LLM 集成** | ✅ DeepSeek/OpenAI | ❌ |
> | **多用户 Web UI** | ✅ Django+React | ✅ FastAPI+Vue |
> | **7×24 无人值守** | ❌ | ✅ 成熟稳定 |

---

## 七、跨平台兼容性分析

Alas 是 **Windows-only** 项目，大量依赖 Windows 注册表和 Win32 API，跨平台迁移需重点关注平台绑定代码的替换。

### 7.1 Windows 绑定分析

| 绑定类型 | 具体依赖 | 跨平台可用 |
|---------|---------|-----------|
| 模拟器发现 — MuiCache | `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\MuiCache` | ❌ 仅 Windows |
| 模拟器发现 — UserAssist | `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist` | ❌ 仅 Windows |
| 模拟器发现 — 安装路径 | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` | ❌ 仅 Windows |
| 模拟器发现 — 卸载注册表 | `HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall` | ❌ 仅 Windows |
| 模拟器发现 — 进程扫描 | `psutil.process_iter()` | ✅ 跨平台 |
| NemuIpc | `external_renderer_ipc.dll`（MuMu 截图加速） | ❌ 仅 Windows |
| LDOpenGL | `ldopengl64.dll`（雷电 OpenGL 截图） | ❌ 仅 Windows |

模拟器发现的5种途径中，**4种仅 Windows 可用**（MuiCache、UserAssist、安装路径、卸载注册表），仅进程扫描跨平台。

### 7.2 macOS/Linux 替代发现方案

| 平台 | 替代方案 | 说明 |
|------|---------|------|
| macOS | 进程扫描 + ADB devices + `~/Applications` 目录扫描 | macOS 应用通常安装在 `/Applications` 或 `~/Applications` |
| Linux | 进程扫描 + ADB devices + `/opt` + `/usr/local` 目录扫描 | Linux 模拟器多为解压安装，分布在 `/opt` 或用户目录 |
| 通用 | ADB `devices` 命令 | 最可靠的跨平台发现方式，直接检测已连接的模拟器 |

### 7.3 跨平台通用模块

| 模块 | 说明 | 跨平台 |
|------|------|--------|
| ADB 截图 | scrcpy / DroidCast / ADB screencap | ✅ 完全跨平台 |
| ADB 输入 | MaaTouch / minitouch / ADB input | ✅ 完全跨平台 |
| 连接池 | `WorkerPool`（线程池 + 超时杀线程） | ✅ 纯 Python |
| 异常恢复 | 5层渐进式策略 | ✅ 纯 Python |
| 配置系统 | YAML 定义 → GUI 自动生成 | ✅ 纯 Python |
| 任务调度 | 函数式任务链 | ✅ 纯 Python |

ADB 截图/输入方式**完全跨平台通用**，且连接池、异常恢复、配置系统均为纯 Python 实现，天然跨平台。

### 7.4 对 GAF 的启示

| # | 启示 | 说明 |
|---|------|------|
| 1 | 模拟器发现封装为平台插件 | 将 Alas 的 Windows 注册表扫描封装为 `WindowsEmulatorDiscovery` 插件，macOS/Linux 实现对应的 `MacOSEmulatorDiscovery` / `LinuxEmulatorDiscovery` 插件 |
| 2 | ADB 作为跨平台基准 | ADB 截图/输入是唯一完全跨平台的方案，应作为 GAF 的基准实现，平台特有加速方案（NemuIpc/LDOpenGL）作为可选增强 |
| 3 | 纯 Python 模块直接复用 | Alas 的连接池、异常恢复、配置系统等纯 Python 模块可直接参考，无需平台适配 |
| 4 | NemuIpc/LDOpenGL 降级处理 | Windows 特有的截图加速方案在 macOS/Linux 上不可用，GAF 需设计降级链：平台加速 → ADB screencap |