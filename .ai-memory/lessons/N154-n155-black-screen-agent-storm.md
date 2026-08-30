---
date: 2026-07-11
symptom: [black-screen, adb-crash, gpu-tdr, heartbeat-storm, ctypes-hot-loop, n146-backend-gap, autoreload-storm, agent-stacking, duplicate-terminal, dev-server, n154-recurrence]
solution: 黑屏家族合并 (N154+N155)。后台心跳循环 >= 30s; 危险操作默认禁用 (opt-in); N146 单例修复必须覆盖 ALL 代码路径 (agent + backend); ADB 优先用模拟器自带; 不重复启动 dev server 终端 (runserver/npm run dev); backend .py 编辑不需要确认 (代码防护 _kill_stale_agent_processes + GAF_AUTO_START_AGENT=0 默认)。
diff_keywords: ["apps", "views", "base", "adb", "screenshot", "_adb_screenshot", "health", "checker", "health_checker", "manager", "project", "rules"]
related_files:
  - backend/workers/apps.py
  - backend/workers/views.py
  - backend/config/settings/base.py
  - backend/device_bridge/platforms/windows/_adb_screenshot.py
  - agent/src/devices/health_checker.py
  - agent/src/monitor/manager.py
  - .trae/rules/project_rules.md
created_by: AI
merged_n_ids: [N154, N155]
level: L1
n_id: N154
topic: platform-env
---


# N154 + N155 — 黑屏家族：ADB subprocess storm + autoreload agent 叠加

## 家族合并说明

本文件合并 N154（ADB subprocess storm + N146 backend gap → 黑屏）和 N155（backend 代码修改触发 autoreload 风暴 → 黑屏，N154 同日复发）。两者同属"黑屏"根因家族：
- **N154** 是**首次黑屏**：心跳循环 2s + agent 自启动 + N146 backend 端未修复 → ADB 风暴 → GPU TDR
- **N155** 是**同日复发**：AI 连续修改 backend .py → autoreload 多次 → agent 进程叠加 → MonitorManager 5s 截图 → ADB 风暴 → 黑屏

N155 修订后明确：backend .py 编辑不需要确认（代码防护已到位），真正需要确认的是"不重复启动 dev server 终端"。

---

## N154: ADB subprocess storm + N146 backend gap → black screen

> **级别**: L1 可复用经验（架构反模式 + Y/N 检查清单价值）
> **分类**: 架构反模式 — 后台循环频率失控 + 教训修复未覆盖全代码树
> **来源**: 2026-07-11 黑屏事件（用户强制重启）
> **登记**: 2026-07-11
> **状态**: ✅ FIXED (commit `-`)

### 触发原话

"我去，刚才你干了什么。adb程序一直报错窗口，然后整个屏幕都黑屏了，我强制重启了，先找下原因"

### 事件概述

用户在开发过程中遭遇黑屏，需要强制重启。根因是后端 `runserver` 启动后自动触发了三个叠加的后台操作：

1. **设备心跳循环**（每 2 秒）：遍历所有 Device，对每个 EMULATOR 类型设备调用 `adb devices` 子进程
2. **Agent 自动启动**：通过 `ShellExecuteW('runas')` 以管理员权限启动 agent 子进程
3. **Agent 自身的健康检查**（每 5 秒）：又一层 `adb devices` 轮询

三重叠加导致：
- `adb.exe` 反复崩溃（系统 PATH 的 adb 与 LDPlayer 的 adbd 版本不兼容）→ "一直报错窗口"
- 如果任何截图操作被触发，backend 端的 `_capture_by_ld_opengl` 每次创建新 `LDOpenGLCapture()` → 反复 LoadLibrary/FreeLibrary `ldopengl64.dll` → vtable 失效 → `ACCESS_VIOLATION (0xC0000005)` → GPU 驱动 TDR → **黑屏**

### 根因分析

#### 反模式 1：后台循环频率失控

`_device_heartbeat_loop` 每 2 秒运行一次，每次遍历所有设备。如果数据库中有 N 个 emulator 设备，每 2 秒就会启动 N 次 `adb devices` 子进程。

```python
# ❌ 反模式：2 秒间隔 + 每设备独立 subprocess
while not _heartbeat_stop_event.is_set():
    for device in devices:
        checker._check_single_device(device)  # 每次 → subprocess.run([adb, "devices"])
    for _ in range(4):
        time.sleep(0.5)  # 总共 2 秒
```

#### 反模式 2：危险操作默认启用

Agent 自动启动通过 `ShellExecuteW('runas')` 请求管理员权限，这会在每次 `runserver` 时触发。agent 子进程启动后又会自动发现设备、启动健康检查线程，与后端心跳循环叠加。

```python
# ❌ 反模式：always-on，不区分开发/生产环境
def ready(self):
    if os.environ.get('GAF_SKIP_AUTO_AGENT') == '1':
        return  # 唯一的关闭方式是环境变量
    # ... 自动启动 agent ...
```

#### 反模式 3：N146 教训只修了一半

N146 教训（2026-07-06）记录了 `ctypes.CDLL` 热循环单例缓存的必要性，**但只在 agent 端修复了**。backend 端的 `_adb_screenshot.py` 中 `_capture_by_ld_opengl` 仍然每次创建新实例：

```python
# ❌ backend 端反模式（N146 未覆盖）
def _capture_by_ld_opengl(serial, adb):
    capturer = LDOpenGLCapture()  # 每次 new → LoadLibrary
    result = capturer.capture(index=index)
    # 方法返回 → capturer GC → FreeLibrary → vtable 失效
```

### 修复方案

#### 1. 心跳间隔：2s → 30s（可配置）

```python
# ✅ 修复：可配置间隔，默认 30s
GAF_HEARTBEAT_INTERVAL = int(os.getenv("GAF_HEARTBEAT_INTERVAL", "30"))

# _device_heartbeat_loop 中
interval = getattr(django_settings, 'GAF_HEARTBEAT_INTERVAL', 30)
for _ in range(interval):
    if _heartbeat_stop_event.is_set():
        break
    time.sleep(1)
```

#### 2. Agent 自启动：默认禁用

```python
# ✅ 修复：默认禁用，需要显式启用
GAF_AUTO_START_AGENT = os.getenv("GAF_AUTO_START_AGENT", "0").lower() in ("true", "1", "yes")

# ready() 中
auto_start = getattr(django_settings, 'GAF_AUTO_START_AGENT', False)
if not auto_start:
    logger.info('Agent auto-start disabled (set GAF_AUTO_START_AGENT=1 to enable).')
    return
```

#### 3. N146 单例修复（backend 端）

```python
# ✅ 修复：模块级单例 + 双重检查锁
_LDOPENGL_LOCK = threading.Lock()
_LDOPENGL_CAPTURE_INSTANCE: object | None = None

def _get_ldopengl_capture():
    global _LDOPENGL_CAPTURE_INSTANCE
    if _LDOPENGL_CAPTURE_INSTANCE is None:
        with _LDOPENGL_LOCK:
            if _LDOPENGL_CAPTURE_INSTANCE is None:
                from device_bridge.platforms.windows.ld_opengl import LDOpenGLCapture
                _LDOPENGL_CAPTURE_INSTANCE = LDOpenGLCapture()
    return _LDOPENGL_CAPTURE_INSTANCE

def _capture_by_ld_opengl(serial, adb):
    capturer = _get_ldopengl_capture()  # 单例，DLL 只加载一次
    result = capturer.capture(index=index)
```

#### 4. ADB 路径优先用模拟器自带

```python
# ✅ 修复：优先用模拟器自带的 adb.exe（协议兼容）
candidates = [
    r"D:\game\leidian\LDPlayer14\adb.exe",
    r"E:\game\leidian\LDPlayer14\adb.exe",
    # ... 其他模拟器路径 ...
]
# 系统 PATH 作为 fallback
```

#### 5. adb devices 输出缓存

```python
# ✅ 修复：10 秒缓存，避免 N 个设备 N 次 subprocess
_ADB_DEVICES_CACHE_TTL = 10.0

@classmethod
def _get_adb_devices_output(cls, adb_exe):
    if cls._adb_devices_cache and (now - cls._adb_devices_cache_time) < cls._ADB_DEVICES_CACHE_TTL:
        return cls._adb_devices_cache
    proc = subprocess.run([adb_exe, "devices", "-l"], ...)
    cls._adb_devices_cache = proc.stdout.strip()
    return cls._adb_devices_cache
```

### Y/N 检查清单

| # | 检查项 | Y/N | 说明 |
|:-:|--------|:---:|------|
| 1 | 后台循环（心跳/轮询）间隔是否 >= 30 秒？ | N=有风险 | 短间隔导致 subprocess 风暴 |
| 2 | 危险操作（admin 提权/子进程启动）是否默认禁用？ | N=有风险 | 开发环境应 opt-in 而非 opt-out |
| 3 | N146 单例修复是否覆盖了 ALL 代码路径（agent + backend）？ | N=有风险 | 教训修复只改一侧 = 另一侧仍有 bug |
| 4 | ADB 路径是否优先用模拟器自带的 adb.exe？ | N=有风险 | 版本不匹配导致 adb.exe 崩溃 |
| 5 | 心跳循环中是否对每个设备独立启动 subprocess？ | Y=有风险 | 应缓存共享结果 |
| 6 | 教训修复时是否 grep 了 ALL 代码树（backend + agent + frontend）？ | N=有风险 | N129 审计 3 棵代码树原则 |

### 适用范围

- **所有后台循环**：心跳/轮询/健康检查间隔必须 >= 30 秒（除非有明确理由更短）
- **所有危险操作**：admin 提权、子进程启动、DLL 加载必须默认禁用
- **所有 N## 教训修复**：必须 grep 全代码树确认 ALL 代码路径已覆盖
- **所有 ADB 调用**：必须优先用模拟器自带的 adb.exe

### 关联

- **N146**: ctypes.CDLL 热循环单例缓存 — 本事件发现 backend 端未修复
- **N129**: 审计 3 棵代码树 — 教训修复也应覆盖 3 棵树
- **commit**: `-`

### 复发记录

#### Recurrence 1 — 2026-07-11 (同日复发)

> **触发原话**: "刚才电脑又黑屏了，我又重启了，是你造成的吗"

**根因**: N154 修复时**遗漏了 MonitorManager 的 5s 截图间隔**。虽然心跳和 health_checker 都改到了 30s，但 `agent/src/monitor/manager.py` 的 `DEFAULT_CHECK_INTERVAL = 5.0` 没有改。

**触发链**:
1. AI 修改了 ~10 个 backend 文件 → Django autoreload **多次重启**
2. 每次 autoreload 触发 `ready()` → `_start_agent_process()` → 启动新 agent（admin 提权）
3. admin 提权的 agent **PID 不可追踪**，旧的不会被杀 → **多个 agent 进程同时运行**
4. 每个 agent 的 `MonitorManager` 每 **5 秒**截图一次
5. N 个 agent × 5s 间隔 = ADB subprocess 风暴 → GPU TDR → 黑屏

**修复**:
- `MonitorManager.DEFAULT_CHECK_INTERVAL`: 5.0 → 30.0
- `GAF_AUTO_START_AGENT` 默认值再次改回 `"0"`（开发时需要显式 `=1` 启用）

**教训补充**: N154 Y/N 检查清单第 1 项"后台循环间隔 >= 30 秒"必须包含 **MonitorManager**，不只是心跳和 health_checker。修复教训时必须 grep **所有** `while` / `time.sleep` / `threading.Timer` / `check_interval` 模式，不能只改显眼的。

---

## N155: Don't start duplicate dev server terminals (black screen prevention)

> **级别**: L1 可复用经验（Y/N 检查清单 + 影响 AI 全局行为）
> **分类**: AI 行为约束 — 终端管理（N109 安全边界）
> **来源**: 2026-07-11 N154 同日复发（用户第二次黑屏重启）
> **登记**: 2026-07-11
> **修订**: 2026-07-11 — 用户澄清"backend 文件修改不用我确认，我之前只是让你确认终端是否重复启动导致黑屏而已"
> **状态**: ✅ FIXED (commit `-` 代码防护 + 本教训行为约束)

### 触发原话

#### 初版（2026-07-11）
"怎么防止这种黑屏问题才是关键，代码修改要重启终端的这种，必须先确认吧？别留下这个暂缓的了"

#### 修订（2026-07-11 同日）
"backend 文件修改不用我确认，我之前只是让你确认终端是否重复启动导致黑屏而已"

### 事件概述

N154 修复后**同日复发**：AI 在一轮工作中连续修改了 ~10 个 backend 文件，每次 Edit 触发 Django autoreload，每次 autoreload 调用 `ready()` → `_start_agent_process()` → 启动新 agent（admin 提权，PID 不可追踪，旧 agent 不被杀）→ **N 个 agent 叠加** × MonitorManager 5s 截图 = ADB 风暴 → GPU TDR → **黑屏**。

### 修订原因

初版 N155 将约束写为"修改 backend .py 前必须确认"，范围过宽。用户明确澄清：

1. **backend .py 编辑不需要确认** — 代码防护已到位（`_kill_stale_agent_processes()` + `GAF_AUTO_START_AGENT=0` 默认），autoreload 安全
2. **真正需要确认的是"启动新终端"** — 重复启动 `runserver` 或 `npm run dev` 终端会导致端口冲突 / 进程叠加 / 黑屏
3. **N109 自决权不被削弱** — AI 仍可自由编辑 backend 代码，不受额外确认限制

### 根因分析

#### 黑屏的两个路径

| 路径 | 根因 | 修复 | 是否还需要 AI 确认 |
|------|------|------|:------------------:|
| **A. 重复启动终端** | AI 启动第二个 `runserver` 终端 → 端口冲突 / 两个 Django 进程各自启动 agent → agent 叠加 | AI 行为约束：不重复启动终端 | ✅ 是 |
| **B. autoreload 级联** | dev server 运行时 Edit backend .py → autoreload → ready() → 重启 agent → 旧 agent 不被杀 → 叠加 | 代码防护：`_kill_stale_agent_processes()` + `GAF_AUTO_START_AGENT=0` 默认 | ❌ 否（代码已防） |

#### 为什么 backend 编辑不再需要确认

commit `-` 的三层防护让 autoreload 安全：

1. **`_kill_stale_agent_processes()`** — autoreload 前主动杀旧 agent，防止叠加
2. **指数退避 + 崩溃循环检测** — agent 频繁崩溃时自动停止重启
3. **`GAF_AUTO_START_AGENT=0` 默认** — 默认不自动启动 agent，autoreload 只是重启 Django，不启动新 agent

因此 AI 可以自由编辑 backend .py 文件，不需要每次都问用户"我可以改吗"。

### 修复

#### 行为约束（本教训核心 — 修订版）

**AI 在启动新终端前，必须**：

1. **检查**：是否已有同类型终端在运行（`runserver` / `npm run dev`）
2. **不重复启动**：如果已有 `runserver` 在运行，不启动第二个
3. **确认**：如果确实需要重启终端（例如代码改动导致 server 崩溃），告知用户并确认

**AI 编辑 backend .py 文件时，不需要确认**：
- 代码防护已到位（`_kill_stale_agent_processes()` + `GAF_AUTO_START_AGENT=0`）
- autoreload 只是重启 Django 进程，不会导致 agent 叠加
- N109/N113/N115/N127 自决权不受影响

#### 代码防护（commit `-`，已实现）

1. `_kill_stale_agent_processes()` — autoreload 前杀旧 agent
2. 指数退避 + 崩溃循环检测 — 防止 agent 风暴
3. `GAF_AUTO_START_AGENT=0` 默认禁用

### Y/N 检查清单（修订版）

| # | 检查项 | Y/N | 说明 |
|:-:|--------|:---:|------|
| 1 | 要启动新的 `runserver` 终端？ | | Y=检查是否已有在运行 |
| 2 | 要启动新的 `npm run dev` 终端？ | | Y=检查是否已有在运行 |
| 3 | 已有同类型终端在运行？ | | Y=不重复启动，复用现有 |
| 4 | 需要重启终端（server 崩溃）？ | | Y=告知用户并确认 |
| 5 | 编辑 backend .py 文件？ | | Y=**不需要确认**（代码防护已到位）|

### 适用范围

- **需要确认**：启动新的 `runserver` / `npm run dev` / `celery worker` 终端
- **不需要确认**：编辑 backend .py / frontend .ts / .md / 测试文件 / agent/ 目录文件

### 关联

- **N154**: ADB subprocess storm → 黑屏 — 本教训是其复发根因的**行为层**修复
- **N109**: AI 决策自决 — 本教训是 N109 安全边界的**终端管理**约束（非 backend 编辑约束）
- **commit**: `-`（代码防护）+ 本教训（行为约束）

### 复发记录

- 2026-07-11: 用户澄清 N155 范围过宽，收窄为"不重复启动终端"
