---
spec: 2026-08-08-td353-pipeline-ghost-click
title: PipelineEngine 超时后"幽灵点击"修复 (TD-353)
status: active
created: 2026-08-08
estimated_effort: 1 day
risk: medium
---

# PipelineEngine 超时后"幽灵点击"修复 (TD-353)

## 1. 问题

`PipelineEngine.execute()` 用 `ThreadPoolExecutor.submit()` + `future.result(timeout=...)` 实现步级超时。Python 线程无法强制杀死，超时后节点对应的后台线程仍在继续运行（如 `device.click()`、`device.swipe()` 等 IO 操作）。

**后果**:
- 用户看到失败提示，但设备实际被操作（"幽灵点击"）
- 超时后下一个节点继续执行，与后台残留线程竞争设备状态
- 超时节点若有重试循环（retry/repeat），循环内仍在执行设备操作

## 2. 方案

采用方案 C（折中）: 超时后置位 `_step_cancel_event` 标志位，后台线程在关键检查点主动退出。

### 2.1 新增 `_step_cancel_event`

在 `PipelineEngine` 中新增 `_step_cancel_event = threading.Event()`, 与 `_cancel_event` 分离:
- `_cancel_event`: 用户显式取消 pipeline（pipeline 级）
- `_step_cancel_event`: 步骤超时（步骤级，仅影响当前后台线程，不终止 pipeline）

### 2.2 超时处理修改

`execute()` 中 `TimeoutError` 分支:

```
1. 设置 _step_cancel_event
2. 提交 sentinel 到 executor，等待前台线程完成
3. 等待 3s 让后台线程检测到 _step_cancel_event 并退出
4. 清除 _step_cancel_event（允许后续步骤正常执行）
5. 返回 fail_result（与现有行为一致）
```

### 2.3 后台线程检查点

`_execute_node_step()` 中检测 `_step_cancel_event` 的位置:

| 检查点 | 位置 | 说明 |
|--------|------|------|
| repeat 循环 | `_execute_node_step` 内 repeat 迭代 | 重复节点操作间检查 |
| retry 循环 | `_handle_node_retry` 内每次重试前 | 重试间检查 |
| pre_delay | `_safe_delay` | 延迟等待期间检查 |
| post_delay | `_safe_delay` | 延迟等待期间检查 |

### 2.4 `_safe_delay` 改造

原实现使用 `Event.wait()` 只检查 `_cancel_event`。改为循环 + 短 sleep 同时检查 `_cancel_event` 和 `_step_cancel_event`，每 100ms 轮询一次。

## 3. 验证标准

1. 手动验证: 模拟一个 timeout 节点（如 `time.sleep(10)` 配 timeout=2），确认后台线程在 3s 内退出
2. 单元测试: 新增测试覆盖超时场景，断言后台线程退出
3. 回归测试: 现有 pipeline 测试全部通过，无新超时行为变更

## 4. 关联文件

- `agent/src/engine/pipeline_engine.py`（主修改）
- `agent/src/engine/nodes/`（非必须，但可复查节点实现是否含重试循环）