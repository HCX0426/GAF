---
maintainer: derived-manual
source: worker/src/core/retry_decorator.py, worker/src/core/recovery.py, backend/scheduler/recovery_engine.py
load_when:
- 新功能 (错误处理)
- Bug修复 (重试/降级)
- 调试任务失败
priority: high
symptom:
- kb:error:recovery
- retry-strategy
- fallback
- 降级策略
- 重试机制
solution: 3 层降级 (retry → fallback → manual) + 5 种错误分类 + 4 步兜底流程
related_files:
- worker/src/core/retry_decorator.py
- worker/src/core/recovery.py
- worker/src/core/recovery.py
- backend/scheduler/recovery_engine.py
- .ai-memory/knowledge/task-lifecycle.md
- .ai-memory/meta/auto-kb/error-codes.md
created_by: AI
generated: 2026-06-16
auto_updated: 2026-06-16
last_manual_edit: 2026-07-20
---
# Error Recovery (错误恢复) - AI 速查

> **适用场景**: AI 写错误处理 / 调试任务失败 / 设计降级策略
> **核心模式**: 3 层降级 (retry → fallback → manual)

## 1. 3 层降级模型

```
[ERROR 发生]
    │
    ▼
[Layer 1: Retry]     ← 自动重试, 指数退避
    │ 失败
    ▼
[Layer 2: Fallback]  ← 降级到次优方案
    │ 失败
    ▼
[Layer 3: Manual]    ← 人工介入 (通知管理员)
```

### 1.1 Layer 1: Retry (重试)

**触发**: 临时性错误 (网络抖动, 设备忙)
**实现**: `worker/src/core/retry_decorator.py` 的 `@with_retry` 装饰器
**配置**:
```python
@with_retry(
    max_attempts=3,         # 最多 3 次
    backoff='exponential',  # 指数退避
    initial_delay=1.0,      # 初始 1s
    max_delay=10.0,         # 最大 10s
    retry_on=[TimeoutError, ConnectionError]  # 仅重试这些
)
def screenshot_device(device_id: str) -> bytes:
    ...
```

**易错点**:
- ❌ 重试所有错误 (包括 `ValueError` 等永久性错误) → 必须白名单 `retry_on`
- ❌ 退避时间固定 (1s, 1s, 1s) → 必须指数或随机, 否则雪崩
- ❌ 不区分 `Exception` 类型 → 必须 catch specific exception

### 1.2 Layer 2: Fallback (降级)

**触发**: 重试仍失败, 但有次优方案
**实现**: `worker/src/core/recovery.py` (原 chain.py DegradationChain 已移除, 降级逻辑并入 retry_decorator/recovery)
**例子**:
- 截图: `WGC → DXGI → BitBlt → PrintWindow` (高性能 → 低性能)
- OCR: `PaddleOCR → RapidOCR → 字符串匹配` (高精度 → 低精度)
- 输入: `PostMessage → SendInput → pyautogui` (精准 → 兜底)

**代码模式**:
```python
from worker.src.core.chain import DegradationChain

chain = DegradationChain([
    ('wgc_screenshot', WGCScreenshot()),
    ('dxgi_screenshot', DXGIScreenshot()),
    ('bitblt_screenshot', BitBltScreenshot()),
])

result = chain.execute(device_id)
# 自动尝试 wgc → dxgi → bitblt, 直到成功
```

**易错点**:
- ❌ 降级链不记录实际使用的方法 → 必须 `chain.used_method` 日志
- ❌ 所有方法都失败时返回 None → 必须抛 `AllFallbacksFailedError`
- ❌ 降级链太长 (> 5 个) → 性能差, 应拆分

### 1.3 Layer 3: Manual (人工介入)

**触发**: 重试 + 降级都失败, 永久性错误
**实现**: `backend/notifications/tasks.py` 的 `send_alert()`
**触发条件**:
- 重试耗尽 (`retry_count >= max_retries`)
- 降级链全失败 (`AllFallbacksFailedError`)
- 数据错误 (`IntegrityError`, `ValidationError`)
- 安全错误 (`PermissionError`)

**代码模式**:
```python
try:
    result = chain.execute(device_id)
except AllFallbacksFailedError as e:
    # 1. 记录到 TaskExecution
    task_execution.mark_failed(reason=str(e))
    # 2. 通知管理员
    send_alert(
        level='P0',
        message=f'Device {device_id} all fallbacks failed',
        task_id=task_id,
    )
    # 3. 释放资源
    device_pool.release(device_id)
    # 4. 标任务 FAILED
    task.fail(reason=str(e))
```

## 2. 5 种错误分类

| 类别 | 例子 | 重试? | 降级? | 通知? |
|------|------|:----:|:----:|:----:|
| **临时性** (transient) | `TimeoutError`, `ConnectionError` | ✅ | ✅ | ❌ |
| **资源性** (resource) | `DeviceBusyError`, `OutOfMemoryError` | ✅ | ✅ | ⚠️ 重试 3 次后 |
| **数据性** (data) | `ValidationError`, `IntegrityError` | ❌ | ❌ | ✅ |
| **逻辑性** (logic) | `PipelineNodeError`, `ConfigError` | ❌ | ❌ | ✅ |
| **安全** (security) | `PermissionError`, `AuthError` | ❌ | ❌ | ✅ P0 |

## 3. 4 步兜底流程

```
[Step 1] 分类错误 (transient/resource/data/logic/security)
    │
[Step 2] 选择策略
    │   transient/resource → retry + fallback
    │   data/logic/security → manual 介入
    │
[Step 3] 执行策略
    │   retry: 指数退避, 记录 attempt
    │   fallback: 降级链, 记录 used_method
    │   manual: 通知 + 释放资源
    │
[Step 4] 记录证据
    - TaskExecution.last_error
    - TaskExecution.attempt_count
    - .ai-memory/evidence/active/YYYY-MM-DD-<task>/
```

## 4. AI 易错点 (5 条)

### 4.1 ❌ catch 所有 Exception 后吞掉 (N67)

**错误**:
```python
try:
    screenshot_device(device_id)
except Exception:
    pass  # ❌ 吞错, 任务永远 SUCCESS 但没截图
```
**正确**: 必须记录 + 至少 mark_failed

### 4.2 ❌ 重试次数无限 (N68)

**错误**: `while True: try_screenshot()` → 永久卡住
**正确**: `max_attempts=3` + 超过后 throw + manual

### 4.3 ❌ 降级链不测 last resort (N69)

**错误**: 写 `WGC → DXGI → BitBlt`, 但没测 BitBlt 在新 Windows 是否真能用
**正确**: 每个降级节点必须有 1 个测试用例 (`test_*.py`)

### 4.4 ❌ 通知用同步调用 (N70)

**错误**: `send_alert()` 同步调用, 阻塞任务执行
**正确**: 用 Celery 异步 `send_alert.delay(...)`

### 4.5 ❌ 错误信息不含上下文 (N71)

**错误**: `raise ValueError('invalid input')`
**正确**: `raise ValueError(f'invalid input: device_id={device_id}, expected UUID')`

## 5. 速查表

| 错误类型 | 是否重试 | 是否降级 | 通知级别 |
|----------|:--------:|:--------:|:--------:|
| `TimeoutError` | ✅ | ✅ | ❌ |
| `ConnectionError` | ✅ | ✅ | ❌ |
| `DeviceBusyError` | ✅ | ✅ | ⚠️ |
| `ValidationError` | ❌ | ❌ | P1 |
| `IntegrityError` | ❌ | ❌ | P1 |
| `PermissionError` | ❌ | ❌ | P0 |

## 6. 反思 (Reflection)

- **3 层降级是默认模式**: retry → fallback → manual, 不要跳层
- **错误分类决定策略**: 临时性可重试, 数据性不可重试
- **证据必须留痕**: 3 步 evidence (problem/solution/verification) 必填
- **相关**: task-lifecycle.md / error-codes.md / pipeline-nodes.md / orchestrator
