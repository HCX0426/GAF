---
date: 2026-07-06
symptom: [ldopengl, ctypes, singleton, hot-loop, access-violation, td-011, free-library]
solution: Cache ctypes.CDLL as module-level singleton to avoid repeated LoadLibrary/FreeLibrary in screenshot hot loops (TD-011 fix).
diff_keywords: ["ldopengl", "screenshot", "ctypes", "singleton", "hot-loop", "access-violation", "td-011", "free-library"]
related_files:
  - agent/src/platforms/windows/ldopengl.py
  - agent/src/platforms/windows/screenshot.py
created_by: AI
level: L1
n_id: N146
topic: agent-platform
---


# N146 — ctypes.CDLL 热循环必须模块级单例缓存（TD-011 LDOpenGL ACCESS_VIOLATION）

> **级别**: L1 可复用经验（架构反模式 + Y/N 检查清单价值）
> **分类**: 架构反模式 — 原生资源句柄热循环泄漏
> **来源**: TD-011 修复（commit `-`）
> **登记**: 2026-07-06
> **状态**: ✅ FIXED

## 触发原话

agent 运行 ~1-2 小时后崩溃，exit code -1073740771 (0xC0000005 ACCESS_VIOLATION)。日志显示 `ldopengl64.dll v3 API loaded` 每秒重复一次。根因是 `LDOpenGLCapture` 实例未被缓存为模块级单例，每次截图创建新实例 → 重复 `ctypes.CDLL(dll_path)` (LoadLibrary) → 实例 GC 时 FreeLibrary → 反复 load/unload → IScreenShotClass vtable 指针访问已释放内存 → ACCESS_VIOLATION。

## 根因分析

### 反模式：热循环内构造 ctypes.CDLL 实例

```python
# ❌ 反模式：每次截图创建新实例
@retry_screenshot()
def _capture_ldopengl(self) -> np.ndarray | None:
    from platforms.windows.ldopengl import LDOpenGLCapture
    capture = LDOpenGLCapture()  # 每次 new → LoadLibrary
    # ... 截图 ...
    return image
    # 方法返回 → capture 被 GC → CDLL.__del__ → FreeLibrary
```

`ctypes.CDLL(path)` 内部调用 `LoadLibrary`（Windows）或 `dlopen`（Linux），递增 DLL 引用计数。当 `CDLL` wrapper 被 GC 时，引用计数递减（`FreeLibrary`/`dlclose`）。

### 崩溃链路

1. 每秒 1 次截图 → 每秒 1 次 `LDOpenGLCapture()` → 每秒 1 次 `ctypes.CDLL(dll_path)` (LoadLibrary)
2. 方法返回 → 实例 GC → `self._dll` (CDLL) 释放 → FreeLibrary
3. 反复 LoadLibrary/FreeLibrary 循环（~3600 次/小时）
4. DLL 内部状态在 unload/reload 之间不稳定 → IScreenShotClass vtable 指针指向已释放内存
5. v3 capture 的 `cap_fn(vtable[1])` 调用 → ACCESS_VIOLATION (0xC0000005)

### 为什么 vtable 指针会失效

- `CreateScreenShotInstance(index, pid)` 返回堆分配对象，前 8 字节存 vtable 指针
- vtable 指向 DLL 内的函数地址
- 当 DLL 被 FreeLibrary 卸载后再 LoadLibrary 重新加载，函数地址可能变化
- 如果 vtable 缓存了旧地址 → 调用时访问已释放内存 → ACCESS_VIOLATION

## 修复方案

### 模块级单例 + 双重检查锁

```python
# ✅ 正确模式：模块级单例
_LDOPENGL_LOCK = threading.Lock()
_LDOPENGL_CAPTURE_INSTANCE: Optional[LDOpenGLCapture] = None

def get_ldopengl_capture() -> LDOpenGLCapture:
    """Return the process-wide LDOpenGLCapture singleton."""
    global _LDOPENGL_CAPTURE_INSTANCE
    if _LDOPENGL_CAPTURE_INSTANCE is None:
        with _LDOPENGL_LOCK:
            if _LDOPENGL_CAPTURE_INSTANCE is None:
                _LDOPENGL_CAPTURE_INSTANCE = LDOpenGLCapture()
    return _LDOPENGL_CAPTURE_INSTANCE
```

调用方改用工厂函数：
```python
# ✅ 正确调用
capture = get_ldopengl_capture()  # 单例，DLL 只加载一次
```

### 为什么双重检查锁

- A2 并行截图（ThreadPoolExecutor max_workers=4）下多线程可能同时首次调用
- 双重检查锁确保只创建一个实例，且无锁开销（首次后）

## 验证

1. **单元测试**：`agent/tests/test_ldopengl.py` 73/73 PASS（66 既有 + 7 单例回归）
2. **单例验证**：`临时验证脚本 (已删除)` 6/6 PASS（api_version 在 5 次 is_available() 后稳定为 3）
3. **端到端验证**：`临时验证脚本 (已删除)` 5/5 真实 LDPlayer 截图 PASS
   - "ldopengl64.dll v3 API loaded" 日志只出现 **1 次**（修复前每秒 1 次）
   - api_version=3 稳定，5 次截图不再 reload DLL

## Y/N 检查清单

| # | 检查项 | Y/N | 说明 |
|:-:|--------|:---:|------|
| 1 | 热循环（每秒/每帧调用）内是否构造 `ctypes.CDLL(path)` 实例？ | Y=有风险 | 必须改为模块级单例 |
| 2 | 热循环内是否 `new` 包含 native 句柄的对象（CDLL/COM/Win32 handle）？ | Y=有风险 | 句柄必须缓存为单例 |
| 3 | native 对象方法是否访问 vtable/函数指针？ | Y=有风险 | DLL 卸载后 vtable 失效 → ACCESS_VIOLATION |
| 4 | 是否有 `LoadLibrary`/`dlopen` 在循环内重复调用？ | Y=有风险 | 必须移到单例初始化 |
| 5 | 单例工厂是否使用双重检查锁？ | N=线程不安全 | 必须加 `threading.Lock` |
| 6 | 测试是否验证 api_version/state 在多次调用后稳定？ | N=缺失 | 必须加回归测试 |

## 适用范围

- **所有 ctypes.CDLL 调用**：在热循环（截图/输入/轮询）中必须用模块级单例
- **所有 Win32 COM 对象**：`CoCreateInstance` 在热循环内必须缓存
- **所有 ADB/IPCHandle**：`subprocess.Popen`/`CreateFile` 句柄在热循环内必须复用
- **不适用**：一次性初始化（如启动时加载配置）不需要单例

## 关联

- **TD-011**: tech-debt/README.md — LDOpenGLCapture 单例缓存
- **C-015**: completed-features.md — TD-011 修复完成
- **N141**: 截图方法 benchmark 盲区 — 相关的截图方法选择教训
- **commit**: `-` (代码) + `-` (文档)
