---
spec_id: spec-2026-07-25-logging-pipeline-hardening
title: 日志与 Pipeline 加固设计规格
status: completed
created: 2026-07-25
last_updated: 2026-07-26
completed: 2026-07-26
owner: AI
priority: P1
related_tds: []
related_lessons:
  - N190-n105-loop-and-powershell-heredoc-l0-gap
scope:
  - agent/src/engine/engine.py
  - agent/src/engine/nodes/click.py
  - agent/src/engine/context.py
  - agent/src/core/result.py
  - agent/src/core/wait_freezes.py
  - agent/src/core/orchestrator.py
  - agent/src/core/interface_recovery.py
  - agent/src/utils/structured_logger.py
  - agent/src/utils/debug_image_saver.py
  - backend/gaf_core/handlers.py
  - backend/gaf_core/tasks.py
  - backend/gaf_ai/agent/tools.py
  - backend/gaf_ai/llm_router.py
  - backend/gaf_ai/views_anomaly.py
  - backend/gaf_ai/tasks.py
  - backend/debug/services.py
estimated_loc: 800
actual_loc: 850
commit: '- (阶段 1-4 全部完成, 含 N190 数据流断点修复)'
---

# 日志与 Pipeline 加固设计规格

**关联调查**: 见对话上下文中的 4 份调查报告（结构化日志 / Pipeline 任务结构 / 点击-导航竞态 / AI 诊断盲区）

> **架构现状校准 (2026-07-25)**:
> 本规格已基于真实代码校准所有文件路径和行号。关键现状：
> - `extract_result_fields` ([structured_logger.py:264-321](file:///d:/code/GAF/agent/src/utils/structured_logger.py)) 当前**只处理 TEMPLATE_MATCH 一种节点**，`click`/`ocr`/`wait`/`swipe_until` 分支均不存在（待新增）
> - `engine.py` 失败分支 (L475 `if not continue_on_error`) 当前**只 return PipelineResult(success=False)**，未调用任何恢复服务
> - `core/interface_recovery.py` 的 `InterfaceRecoveryManager` (L200 `recover()`) 是**孤立模块，未接入 engine**（需新增接入）
> - `engine.py` 的 `log_node_event` 调用 (L439-457) 当前传 16 个参数，**未传** `variables_snapshot`/`previous_node_id`/`error_code`/`raw_screenshot_path`（待新增）
> - `AutoResult` ([result.py:8](file:///d:/code/GAF/agent/src/core/result.py)) 当前**无** `node_id`/`node_type`/`error_code` 字段（待新增）
> - `orchestrator.py` 的 `_llm_diagnose_pipeline_failure` 在 **L956**（非原规格误标的 1213-1221）
> - `WaitFreezes` 已有 `wait_for_change` (L125) 和 `_compare_frames` (L172)，可复用
> - `orchestrator.py` 已有 `_run_verify` (L361)，支持 chain 模式的 6 种验证类型，可抽出复用

---

## 1. 背景与目标

### 1.1 问题陈述

对 GAF 项目的日志体系、Pipeline 任务结构、点击-导航竞态防护、AI 诊断能力进行了 4 路并行调查，发现以下结构性缺陷：

1. **日志归一化不完整**：普通 `click` 节点坐标完全丢失；OCR 文本不入 JSONL；`variables_snapshot` 字段存在但 engine 不传值；缺 `previous_node_id` / `error_code` 字段。
2. **Pipeline 任务结构有断点**：chain 模式有 `pre_verify`/`post_verify` 但 pipeline 模式没有；`ClickNode` 自身零验证（fire-and-forget）；`AutoResult` 不携带 `node_id`/`node_type`，即时诊断丢失节点类型。
3. **点击-导航竞态防护不闭合**：`wait_for_change` 已实现但零调用；`SafePointChecker` 只管取消不管状态；`interface_recovery` 完全反应式；恢复路径无"换路径"策略。
4. **AI 诊断盲区大**：ReAct Agent 4 个内置工具与 `ContextCollector` 解耦，拿不到截图二进制；`AutoResult` 丢失节点类型；异常检测不闭环；Agent 端即时诊断看不到 JSONL 内容。
5. **数据库承载了非持久化数据**：`LogEntry` 和 `TraceSpan` 表存储了临时性日志/追踪数据，应该改为文件归档。

### 1.2 设计目标

- **G1**: 让 AI 能完整追踪 bug，从 JSONL 日志就能定位到 node_id + 错误码 + 上下文
- **G2**: 修复点击-导航竞态漏洞，点击后默认轻量防护，关键节点可配置强验证
- **G3**: 数据库只保留持久化数据（任务/步骤状态），日志/追踪改为文件归档
- **G4**: AI 诊断盲区收窄——补全文字上下文（OCR 文本/变量快照）+ 增加视觉工具（看截图原图）
- **G5**: 截图双保留——识别类节点保留原图（AI 看）+ 标注图（用户看），同文件名跨目录关联

### 1.3 非目标

- 不重写整个 pipeline 引擎，只做有针对性加固
- 不引入新的依赖（除非必要），优先复用已有实现（如 `wait_for_change`）
- 不改 `TaskExecution` / `TaskStep` 表结构（仅废弃 `LogEntry` / `TraceSpan` 的写入）

---

## 2. 数据库边界（最小保留策略）

### 2.1 保留的表

| 表 | 用途 | 字段调整 |
|---|---|---|
| `TaskExecution` | 任务最终状态/结果 | `execution_snapshot` JSON 中保留 `archive_path` + `structured_log_path` 两个路径字段（字段结构本身不变） |
| `TaskStep` | 步骤状态/截图路径/错误 | 保持现状，`screenshot_path` 字段保留（指向标注图） |

### 2.2 废弃的表

| 表 | 替代方案 | 迁移策略 |
|---|---|---|
| `LogEntry` | 改为文件日志 `<debug_dir>/logs/<execution_id>/run.log` | `gaf_core/handlers.py` 的 `DatabaseLogHandler` 改为 `FileLogHandler`；现有数据保留只读，新数据不写入 |
| `TraceSpan` | 改为 JSONL 文件中的 span 字段 | `tracing/middleware.py` 不再写 DB，只把 `trace_id` 通过 HTTP header 传递并写入 JSONL |

### 2.3 受影响模块

| 模块 | 改动 |
|---|---|
| `backend/gaf_core/handlers.py` | `DatabaseLogHandler` → `FileLogHandler`，按 `execution_id` 归档 |
| `backend/tracing/middleware.py` | 移除 DB 写入，仅注入 `trace_id` 到 contextvar |
| `backend/tracing/models.py` | 模型标记为 deprecated（保留只读），新代码不写入 |
| `backend/gaf_ai/views_anomaly.py` | 异常检测改为扫 JSONL 文件而非查 `LogEntry` 表 |
| `backend/debug/services.py` | `LogPackService.pack_logs` 适配新目录结构 |

---

## 3. 日志归一化补全

### 3.1 JSONL Schema 增强

为 `extract_result_fields` 补全缺失分支（[structured_logger.py:264-321](file:///d:/code/GAF/agent/src/utils/structured_logger.py)，当前**只处理 TEMPLATE_MATCH 一种节点**，其他分支均不存在）：

#### 3.1.1 `click` 分支（新增）

```python
elif node_type == "click":
    cx = result_data.get("x")
    cy = result_data.get("y")
    if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
        out["match_location"] = {"x": int(cx), "y": int(cy)}
    for key in ("button", "clicks", "interval", "coord_type", "normalization_applied"):
        val = result_data.get(key)
        if val is not None:
            out[key] = val
    x_in = result_data.get("x_in")
    y_in = result_data.get("y_in")
    if isinstance(x_in, (int, float)) and isinstance(y_in, (int, float)):
        out["click_input"] = {"x": int(x_in), "y": int(y_in)}
    # 新增竞态防护结果字段
    if "expect_screen_change" in result_data:
        out["expect_screen_change"] = result_data["expect_screen_change"]
    if "screen_change_outcome" in result_data:
        out["screen_change_outcome"] = result_data["screen_change_outcome"]
```

#### 3.1.2 `ocr` 分支（增强）

```python
elif node_type == "ocr":
    texts = result_data.get("texts", [])
    # 提取前 10 条文本（超出截断）
    out["texts"] = [t[:200] for t in texts[:10]]
    out["text_count"] = len(texts)
    confidences = result_data.get("confidences", [])
    if confidences:
        out["confidences_top10"] = [round(float(c), 4) for c in confidences[:10]]
    boxes = result_data.get("boxes", [])
    if boxes:
        out["boxes_top10"] = [[int(v) for v in b[:4]] for b in boxes[:10]]
    # expected_text 用于失败诊断
    expected = result_data.get("expected_text")
    if expected:
        out["expected_text"] = expected[:200]
```

#### 3.1.3 `wait` 分支（增强）

```python
elif node_type == "wait":
    for key in ("mode", "max_wait"):
        val = result_data.get(key)
        if val is not None:
            out[key] = val
    check_history = result_data.get("check_history", [])
    if check_history:
        # 最近 3 次失败的精简快照
        out["check_history"] = [
            {
                "check_index": h.get("check_index"),
                "elapsed_s": round(h.get("elapsed_s", 0), 3),
                "confidence": round(h.get("confidence", 0), 4) if h.get("confidence") else None,
                "screenshot": h.get("screenshot"),
            }
            for h in check_history[-3:]
        ]
```

#### 3.1.4 `swipe_until` 分支（增强）

```python
elif node_type == "swipe_until":
    for key in ("attempts", "swipes_performed"):
        val = result_data.get(key)
        if val is not None:
            out[key] = val
```

### 3.2 跨步骤关联字段（所有节点）

在 `log_node_event` 的 payload 中新增三个字段：

| 字段 | 类型 | 来源 | 用途 |
|---|---|---|---|
| `previous_node_id` | str | engine 维护上一节点 ID | 恢复/跳过场景下追踪步骤顺序 |
| `previous_node_type` | str | engine 维护上一节点类型 | 识别"前一步是 click 导致的竞态" |
| `inter_node_gap_ms` | int | engine 计算上一节点结束到本节点开始的间隔 | 识别竞态的关键指标 |

实现位置：[engine.py:439-457](file:///d:/code/GAF/agent/src/engine/engine.py) 的 `log_node_event` 调用处（在 `_execute_node_step` L564 内），从 `self._previous_node_chain` 取上一节点信息，计算时间差。当前调用传 16 个参数，需新增 3 个跨步骤关联字段。

### 3.3 variables_snapshot 实际传值

[engine.py:439-457](file:///d:/code/GAF/agent/src/engine/engine.py) 调用 `log_node_event` 时实际传入 `variables_snapshot`（当前未传，待新增）：

```python
# 白名单过滤控制变量，避免泄露过多内部状态
_vars_snapshot = {}
for key, value in self._context.variables.items():
    # 跳过内部协议变量（下划线前缀）
    if key.startswith("_"):
        continue
    # 跳过大对象（如截图二进制）
    if isinstance(value, (bytes, np.ndarray)):
        continue
    try:
        # 尝试 JSON 序列化，过滤不可序列化的
        json.dumps(value, default=str)
        _vars_snapshot[key] = value
    except (TypeError, ValueError):
        continue
# 限制总大小
if len(str(_vars_snapshot)) > 2000:
    _vars_snapshot = {"_truncated": True, "_keys": list(_vars_snapshot.keys())}

self._structured_logger.log_node_event(
    ...
    variables_snapshot=_vars_snapshot if _vars_snapshot else None,
)
```

### 3.4 error_code 接入

#### 3.4.1 新增枚举

[backend/gaf_core/error_codes.py](file:///d:/code/GAF/backend/gaf_core/error_codes.py) 增加节点级错误码枚举：

```python
class NodeErrorCode(str, Enum):
    TIMEOUT = "TIMEOUT"
    NO_MATCH = "NO_MATCH"                    # 模板/特征匹配失败
    LOW_CONFIDENCE = "LOW_CONFIDENCE"        # 置信度低于阈值
    DEVICE_ERROR = "DEVICE_ERROR"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    SCREEN_UNCHANGED = "SCREEN_UNCHANGED"    # 点击后画面未变化（竞态）
    OCR_NO_TEXT = "OCR_NO_TEXT"
    OCR_NO_EXPECTED = "OCR_NO_EXPECTED"      # OCR 没识别到预期文字
    POST_VERIFY_FAILED = "POST_VERIFY_FAILED"
    TRANSIENT_RETRY_EXHAUSTED = "TRANSIENT_RETRY_EXHAUSTED"
    UNKNOWN = "UNKNOWN"
```

#### 3.4.2 节点填充 error_code

`AutoResult` 增加 `error_code` 字段（[result.py:7-24](file:///d:/code/GAF/agent/src/core/result.py)）：

```python
@dataclass
class AutoResult:
    success: bool
    data: Any = None
    error_msg: str = ""
    error_code: str = ""           # 新增：NodeErrorCode 枚举值
    elapsed_time: float = 0.0
    is_interrupted: bool = False
    retry_count: int = 0
    node_id: str = ""              # 新增：填充节点 ID
    node_type: str = ""            # 新增：填充节点类型
```

各节点在 `fail_result(...)` 调用处传入对应 `error_code`。`fail_result` 工厂函数同步增加 `error_code` 参数。

#### 3.4.3 JSONL 记录

`log_node_event` 在 payload 中加入 `error_code` 字段（仅在 `success=False` 时非空）。

---

## 4. 点击-导航竞态修复（混合策略）

### 4.1 设计原则

- **默认轻量防护**：ClickNode 默认等待画面变化（最长 2s），变化则立即继续；2s 内没变化只记 warning 不 fail（兼容"点击选中"场景）
- **可选强验证**：支持 `post_verify` 配置，配置了则等画面变化 + 跑 verify，失败则 fail
- **可关闭**：`expect_screen_change: false` 完全关闭默认防护（长按/纯选中场景）

### 4.2 wait_for_change 接入

#### 4.2.1 新增轻量变体

[wait_freezes.py:125-170](file:///d:/code/GAF/agent/src/core/wait_freezes.py) 现有 `wait_for_change` 保留，新增 `wait_for_change_lightweight` 变体：

```python
class ScreenChangeOutcome(str, Enum):
    CHANGED = "CHANGED"            # 画面变化，可继续
    UNCHANGED = "UNCHANGED"        # 2s 内无变化（疑似竞态）
    TIMEOUT = "TIMEOUT"            # 等待超时（设备异常）
    SKIPPED = "SKIPPED"            # 跳过检测（配置关闭或无截图函数）

def wait_for_change_lightweight(
    self,
    capture_fn,
    timeout: float = 2.0,
    change_threshold: float = 0.01,
    poll_interval: float = 0.1,
) -> ScreenChangeOutcome:
    """轻量画面变化检测，不抛异常，返回枚举结果。

    与 wait_for_change 的区别：
    - 超时返回 UNCHANGED 而非 False（语义更清晰）
    - 默认 2s 超时（而非 30s）
    - 默认 0.1s 轮询（更快响应）
    - 不记录 INFO 日志（避免日志噪声）
    """
    try:
        baseline = capture_fn()
        if baseline is None or baseline.size == 0:
            return ScreenChangeOutcome.SKIPPED
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            frame = capture_fn()
            if frame is None or frame.size == 0:
                continue
            sim = self._compare_frames(baseline, frame)
            if (1.0 - sim) >= change_threshold:
                return ScreenChangeOutcome.CHANGED
            time.sleep(poll_interval)
        return ScreenChangeOutcome.UNCHANGED
    except Exception:
        return ScreenChangeOutcome.SKIPPED
```

#### 4.2.2 ClickNode 集成

[click.py:106-198](file:///d:/code/GAF/agent/src/engine/nodes/click.py) 的 `execute()` 末尾，success 返回前插入：

```python
# 默认轻量防护（除非显式关闭）
expect_change = self.config.get("expect_screen_change", True)
screen_change_outcome = ScreenChangeOutcome.SKIPPED
if expect_change and self._wait_freezes is not None and self._capture_fn is not None:
    screen_change_outcome = self._wait_freezes.wait_for_change_lightweight(
        capture_fn=self._capture_fn,
        timeout=self.config.get("screen_change_timeout", 2.0),
    )
    # UNCHANGED 记 warning 但不 fail（兼容选中场景）
    if screen_change_outcome == ScreenChangeOutcome.UNCHANGED:
        logger.warning(
            "ClickNode %s: screen unchanged after %.1fs (possible race condition)",
            self.id, self.config.get("screen_change_timeout", 2.0),
        )

result_data = {
    "x": x, "y": y, "button": button,
    "clicks": actual_clicks, "interval": interval,
    "expect_screen_change": expect_change,
    "screen_change_outcome": screen_change_outcome.value,
}
```

#### 4.2.3 依赖注入

ClickNode 需要访问 `WaitFreezes` 实例和 `capture_fn`。通过 `PipelineContext` 注入：

- [context.py](file:///d:/code/GAF/agent/src/engine/context.py) 增加 `wait_freezes` 和 `capture_fn` 属性
- [engine.py](file:///d:/code/GAF/agent/src/engine/engine.py) 初始化时注入（与 `recovery_manager` 同级）

### 4.3 post_verify 强验证（Pipeline 节点通用）

#### 4.3.1 抽出独立模块

将 [orchestrator.py:361](file:///d:/code/GAF/agent/src/core/orchestrator.py) 的 `_run_verify`（当前在 chain 模式 L305/L324 被调用）抽出为独立模块 `agent/src/core/verify.py`：

```python
class Verifier:
    """Pipeline 节点后置验证器，复用 chain 模式的 6 种验证类型。"""

    SUPPORTED_TYPES = {"template", "color", "exist", "disappear", "text", "custom_verify"}

    def __init__(self, template_match_fn, ocr_fn, color_pick_fn, custom_verify_fn=None):
        ...

    def verify(self, verify_config: dict, context: PipelineContext) -> AutoResult:
        verify_type = verify_config.get("type")
        if verify_type not in self.SUPPORTED_TYPES:
            return fail_result(error_code="UNKNOWN_VERIFY_TYPE", error_msg=...)
        handler = getattr(self, f"_verify_{verify_type}")
        return handler(verify_config, context)
```

#### 4.3.2 PipelineEngine 集成

[engine.py:564](file:///d:/code/GAF/agent/src/engine/engine.py) 的 `_execute_node_step` 末尾（节点成功返回后，L439 log_node_event 调用之前），节点成功后调用 post_verify：

```python
# 节点执行成功后，检查 post_verify 配置
post_verify = node.config.get("post_verify")
if post_verify and result.success:
    verify_result = self._verifier.verify(post_verify, self._context)
    if verify_result.failed:
        result = AutoResult(
            success=False,
            error_msg=f"后置验证失败: {verify_result.error_msg}",
            error_code="POST_VERIFY_FAILED",
            elapsed_time=result.elapsed_time,
            node_id=node.id,
            node_type=node.node_type,
        )
```

### 4.4 恢复路径策略增强

#### 4.4.1 换路径策略

[interface_recovery.py:200](file:///d:/code/GAF/agent/src/core/interface_recovery.py) 的 `recover()` 方法（当前 find_path 在 L403，无 exclude_edges 参数）增加第二次尝试时换路径：

```python
def recover(self, expected_state, pipeline_name, node_id, node_config, execution_context, attempt=1):
    ...
    path = self.find_path(current_state, expected_state)
    if path is None:
        if attempt == 1:
            # 第一次失败，尝试 BFS 找备选路径（排除已用边）
            path = self.find_path(current_state, expected_state, exclude_edges=self._used_edges)
        if path is None:
            return RecoveryOutcome.RECOVERY_FAILED
    ...
    outcome = self._execute_path(path, ...)
    if outcome == RecoveryOutcome.RECOVERY_FAILED and attempt == 1:
        # 标记已用边，递归尝试第二次
        self._used_edges.update(self._path_to_edges(path))
        return self.recover(expected_state, pipeline_name, node_id, node_config, execution_context, attempt=2)
    return outcome
```

#### 4.4.2 配置化 transient 参数

[interface_recovery.py:129-130](file:///d:/code/GAF/agent/src/core/interface_recovery.py) 的硬编码改为从 `recover()` 方法的 `node_config` 参数读取（`__init__` 时机拿不到 node_config）：

```python
# 原硬编码（L129-130，删除）：
# self._transient_wait_s = 1.5
# self._transient_max_retries = 2

# recover() 方法签名不变，从 node_config 取值：
def recover(self, expected_state, pipeline_name, node_id, node_config, execution_context, attempt=1):
    transient_wait_s = node_config.get("transient_wait_s", 1.5)
    transient_max_retries = node_config.get("transient_max_retries", 2)
    # ... 后续逻辑使用这两个局部变量
```

> **⚠️ 前置任务（新增接入）**: `node_config` 需要 engine.py 在失败分支调用 `recover()` 时传入。**当前 engine.py 完全未调用 `recover()`**（`InterfaceRecoveryManager` 是孤立模块）。需在 engine.py 的失败分支（L475 `if not continue_on_error:` 块内）新增 recover() 调用，传入 `node.config` dict。这是 §4.4 增强的前置依赖。

---

## 5. AutoResult 携带节点元数据

### 5.1 字段扩展

[result.py:8](file:///d:/code/GAF/agent/src/core/result.py) 的 `AutoResult`（当前无 node_id/node_type/error_code 字段）增加可选字段：

```python
@dataclass
class AutoResult:
    success: bool
    data: Any = None
    error_msg: str = ""
    error_code: str = ""
    elapsed_time: float = 0.0
    is_interrupted: bool = False
    retry_count: int = 0
    node_id: str = ""
    node_type: str = ""

    @property
    def failed(self) -> bool:
        return not self.success
```

### 5.2 节点基类自动填充

[node.py](file:///d:/code/GAF/agent/src/engine/node.py) 的 `PipelineNode.execute` 包装器（或 engine 调用处）自动填充：

```python
# engine.py:_execute_node_step 中，节点 execute 返回后
if not result.node_id:
    result.node_id = node.id
if not result.node_type:
    result.node_type = node.node_type
```

### 5.3 即时诊断受益

[orchestrator.py:956](file:///d:/code/GAF/agent/src/core/orchestrator.py) 的 `_llm_diagnose_pipeline_failure`（当前 L990-1009 用 `first_failed_step_error` 字符串拼接，无结构化 node_id/node_type/error_code）改为携带完整元数据：

```python
# 找到第一个失败的步骤，携带完整元数据
failed_step = next((r for r in step_results if r.failed), None)
if failed_step:
    error_context = {
        "node_id": failed_step.node_id,
        "node_type": failed_step.node_type,        # 真实节点类型，不再是 "pipeline"
        "error_msg": failed_step.error_msg,
        "error_code": failed_step.error_code,
        "structured_log_path": structured_log_path,
        "structured_log_content": self._read_structured_log(structured_log_path),  # 新增：读文件内容
    }
```

---

## 6. 截图双保留方案

### 6.1 目录结构

```
<debug_dir>/screenshots/
  raw/                          # 原图（给 AI 看，JPEG q=85 压缩）
    step03_143025_ocr.jpg
    step05_143038_template_match.jpg
  annotated/                    # 标注图（给用户看，PNG 无损）
    step03_143025_ocr.png
    step05_143038_template_match.png
```

**关联方式**：同目录下完全相同的文件名（仅扩展名不同），靠目录区分用途。

### 6.2 差异化保留策略

| 节点类型 | 原图 (raw/) | 标注图 (annotated/) | 理由 |
|---|---|---|---|
| `ocr` | ✅ JPEG q85 | ✅ PNG | OCR 漏识别时需 AI 看真实画面 |
| `template_match` | ✅ JPEG q85 | ✅ PNG | 模板匹配失败可能是 UI 错位 |
| `feature_match` | ✅ JPEG q85 | ✅ PNG | 同上 |
| `color_detect` | ✅ JPEG q85 | ✅ PNG | 颜色判断失败需原图验证 |
| `click` | ❌ | ✅ PNG | 标注图（红色叉+坐标）已包含全部诊断信息 |
| `swipe` | ❌ | ✅ PNG | 标注图（箭头）已表达完整动作 |
| `key_press` | ❌ | ✅ PNG | 标注图够用 |
| `wait` | ❌ | ✅ PNG | wait 失败时截图本就是验证目标 |

### 6.3 格式选择

- **原图用 JPEG (q=85)**：1920×1080 约 200-400KB（PNG 是 2-5MB），存储成本压缩到 1/10
- **标注图用 PNG**：保留无损质量，红框/文字边缘清晰

### 6.4 DebugImageSaver 改造

[debug_image_saver.py](file:///d:/code/GAF/agent/src/utils/debug_image_saver.py) 的 `save_template_debug` / `save_ocr_debug` / `save_action_debug` 方法增加原图保存逻辑：

```python
def save_ocr_debug(self, screen, ...):
    # 1. 保存原图（仅识别类节点）
    raw_path = None
    if self._should_save_raw(node_type="ocr"):
        raw_path = self._save_raw_image(screen, node_id, step_index, execution_id)
    
    # 2. 保存标注图（现有逻辑）
    debug_img = screen.copy()
    # ... 绘制标注 ...
    annotated_path = self._save_annotated(debug_img, ...)
    
    return annotated_path  # 返回标注图路径（向后兼容）

def _save_raw_image(self, screen, node_id, step_index, execution_id):
    """保存原图为 JPEG q=85 到 raw/ 目录"""
    raw_dir = os.path.join(self.debug_dir, "screenshots", "raw")
    os.makedirs(raw_dir, exist_ok=True)
    fname = self._build_filename(node_type="ocr", ..., ext=".jpg")
    raw_path = os.path.join(raw_dir, fname)
    ok, buf = cv2.imencode(".jpg", screen, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if ok:
        buf.tofile(raw_path)
    return raw_path
```

### 6.5 JSONL 字段关联

`log_node_event` 增加 `raw_screenshot_path` 字段：

```python
{
  "screenshot_path": "screenshots/annotated/step03_143025_ocr.png",     # 标注图（人看）
  "raw_screenshot_path": "screenshots/raw/step03_143025_ocr.jpg",       # 原图（AI 看）
}
```

---

## 7. AI 诊断盲区修复

### 7.1 OCR 文本进 JSONL

见 §3.1.2，`ocr` 分支提取 `texts` 前 10 条。

### 7.2 ReAct Agent 视觉工具

#### 7.2.1 新增工具

[backend/gaf_ai/agent/tools.py](file:///d:/code/GAF/backend/gaf_ai/agent/tools.py) 增加 `get_screenshot_base64` 工具：

```python
@tool
def get_screenshot_base64(execution_id: str, step_index: int = None, raw: bool = True) -> dict:
    """获取指定执行/步骤的截图 base64 编码。

    Args:
        execution_id: 任务执行 ID
        step_index: 步骤索引（可选，不传则返回失败步骤的截图）
        raw: True 返回原图（JPEG），False 返回标注图（PNG）

    Returns:
        {"base64": str, "format": "jpeg"|"png", "path": str, "size_bytes": int}
    """
    # 1. 查 TaskStep 拿 screenshot_path（标注图）
    # 2. 如果 raw=True，从 JSONL 读取 raw_screenshot_path
    # 3. 读取文件，base64 编码返回
```

#### 7.2.2 LLM 路由

[backend/gaf_ai/llm_router.py](file:///d:/code/GAF/backend/gaf_ai/llm_router.py) 根据模型能力决定是否暴露视觉工具：

```python
def get_tools_for_model(model: str) -> list:
    if model in VISION_CAPABLE_MODELS:  # ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", ...]
        return [get_execution_detail, get_execution_steps, search_similar_errors,
                get_task_config, get_screenshot_base64, get_structured_log]
    return [get_execution_detail, get_execution_steps, search_similar_errors,
            get_task_config, get_structured_log]
```

### 7.3 JSONL 内容接入 ReAct Agent

#### 7.3.1 新增工具

```python
@tool
def get_structured_log(execution_id: str) -> dict:
    """获取指定执行的结构化 JSONL 日志摘要。

    Returns:
        {
            "total_steps": int,
            "failed_steps": [{"step_index", "node_id", "node_type", "error_code", "error_msg"}],
            "successful_summary": "step0 ✅ ... step1 ✅ ...",  # 单行摘要
            "failed_detail": "step5 ❌ template_match (score=0.42, threshold=0.80, ...)",
            "raw_log_path": str,
        }
    """
    # 1. 从 TaskExecution.execution_snapshot 读 structured_log_path
    # 2. 读取 JSONL 文件
    # 3. 解析为摘要结构
```

#### 7.3.2 替代 SQL fallback

`search_similar_errors` 的 SQL fallback（[tools.py:195-224](file:///d:/code/GAF/backend/gaf_ai/agent/tools.py)）改为扫历史 JSONL 文件。

> **数据流路径 (2026-07-26 修正)**: 原设计 `glob <DEBUG_ARCHIVE_DIR>/**/structured.jsonl`
> 与实际 JSONL 写入路径 (`<DEBUG_DIR>/structured/<exec_id>.jsonl`) 不一致,
> 导致 fallback 永远扫不到文件。修正后改为查 DB 拿路径再读文件,
> 与同模块 `gaf_ai.views_anomaly._extract_patterns_from_jsonl` 的数据流对齐:
> `TaskExecution.execution_snapshot['structured_log_path']` → `open(path)` → 解析 JSONL。

```python
def _search_similar_errors_via_jsonl(
    error_text: str,
    top_k: int = 5,
    similarity_threshold: float = 0.5,
    days: int = 30,
    max_executions: int = 200,  # 防止 30 天千次失败 × 千行 JSONL = 百万次比对
    executions: Iterable = None,  # 可选: 已有 queryset 时传入, 跳过 DB 查询
) -> list[dict]:
    """查 failed executions 的 structured_log_path → 读 JSONL → 按 error_msg 相似度排序.

    默认查最近 N 天 status=FAILED 的 TaskExecution, 最多 max_executions 条.
    跳过: 无 structured_log_path / 文件不存在 / 单行 JSON 解析失败 (best-effort).
    execution_id 始终返回 TaskExecution.pk (int), 不暴露 JSONL 里的 agent UUID12
    (调用方如 get_execution_detail 期望 int pk).
    """
    from tasks.models import TaskExecution

    if executions is None:
        cutoff = timezone.now() - timedelta(days=days)
        executions = TaskExecution.objects.filter(
            status=TaskExecution.Status.FAILED,
            started_at__gte=cutoff,
        ).order_by('-started_at')[:max_executions]

    candidates: list[tuple[float, dict]] = []
    for ex in executions:
        snapshot = ex.execution_snapshot if isinstance(ex.execution_snapshot, dict) else {}
        jsonl_path = snapshot.get('structured_log_path', '')
        if not jsonl_path or not os.path.isfile(jsonl_path):
            continue
        try:
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    evt = json.loads(line.strip())  # 解析失败静默跳过
                    if evt.get('success') is not False:
                        continue
                    msg = evt.get('error_msg', '')
                    if not msg:
                        continue
                    sim = text_similarity(error_text, msg)
                    if sim > similarity_threshold:
                        candidates.append((sim, {
                            'execution_id': ex.id,  # TaskExecution.pk (int)
                            'error': msg, 'similarity': round(sim, 3),
                            'jsonl_path': jsonl_path,  # ... 其余字段
                        }))
        except (OSError, UnicodeDecodeError):
            continue  # 单文件失败不阻塞整次扫描

    candidates.sort(key=lambda x: -x[0])
    return [c[1] for c in candidates[:top_k]]
```

### 7.4 异常检测闭环

#### 7.4.1 改为扫 JSONL

[views_anomaly.py:115-145](file:///d:/code/GAF/backend/gaf_ai/views_anomaly.py) 的 `_extract_patterns` 改为扫 JSONL：

```python
def _extract_patterns_from_jsonl(days: int = 7) -> list:
    """从历史 JSONL 文件提取失败模式"""
    cutoff = timezone.now() - timedelta(days=days)
    patterns = Counter()
    for exec in TaskExecution.objects.filter(
        status=TaskExecution.Status.FAILED,
        started_at__gte=cutoff,
    ).exclude(execution_snapshot__structured_log_path__isnull=True):
        log_path = exec.execution_snapshot.get("structured_log_path")
        if not log_path or not os.path.exists(log_path):
            continue
        for line in read_jsonl(log_path):
            if line.get("success") is False:
                normalized = _normalize_error(line.get("error_msg", ""))
                patterns[normalized] += 1
    return patterns
```

#### 7.4.2 定时任务

[backend/gaf_ai/tasks.py](file:///d:/code/GAF/backend/gaf_ai/tasks.py) 增加 Celery beat 定时任务：

```python
@shared_task
def daily_anomaly_scan():
    """每天凌晨扫描最近 24h 失败的执行，触发异常检测"""
    patterns = _extract_patterns_from_jsonl(days=1)
    if not patterns:
        return
    report_path = write_anomaly_report(patterns, date=timezone.now().date())
    # 通过通知系统推送
    notify_anomaly_detected.delay(report_path=report_path, pattern_count=len(patterns))
```

[backend/tasks/beat.py](file:///d:/code/GAF/backend/tasks/beat.py) 注册：

```python
crontab(hour=2, minute=0),  # 每天凌晨 2 点
```

### 7.5 Agent 端即时诊断增强

[orchestrator.py:_llm_diagnose_pipeline_failure](file:///d:/code/GAF/agent/src/core/orchestrator.py) 实际读取 JSONL 内容：

```python
def _llm_diagnose_pipeline_failure(self, result, structured_log_path, ...):
    # 新增：读取 JSONL 内容（不再只传路径）
    structured_log_content = ""
    if structured_log_path and os.path.exists(structured_log_path):
        with open(structured_log_path, "r", encoding="utf-8") as f:
            structured_log_content = f.read()[-8000:]  # 截断到最后 8000 字符

    error_context = {
        "node_id": failed_step.node_id,
        "node_type": failed_step.node_type,
        "error_msg": failed_step.error_msg,
        "error_code": failed_step.error_code,
        "structured_log_path": structured_log_path,
        "structured_log_content": structured_log_content,  # 新增
        "diagnosis_path": diagnosis_path,  # 新增：diagnosis.md 路径
    }
    return self._llm_client.diagnose_failure(error_context)
```

---

## 8. 文档归档机制

### 8.1 目录结构

```
<debug_dir>/
  logs/
    <execution_id>/
      run.log              # 文本日志（原 DatabaseLogHandler 输出）
      structured.jsonl     # 结构化 JSONL
      diagnosis.md         # 失败诊断报告
      timeline.md          # 时间线
      score_curve.png      # 置信度曲线
      screenshots/
        raw/               # 原图（JPEG，AI 看）
        annotated/         # 标注图（PNG，用户看）
      recovery_archive/    # 界面恢复存档
  anomaly_reports/
    YYYY-MM-DD.md          # 每日异常模式报告
  archives/                # 归档压缩包（保留 30 天）
    <execution_id>.tar.gz
```

### 8.2 归档策略

任务执行完成后，整个 `<execution_id>/` 目录打包为 `.tar.gz` 归档到 `archives/`：

```python
# backend/debug/services.py
def pack_logs(self, execution_id: str) -> str:
    """打包执行日志目录为 tar.gz"""
    src_dir = os.path.join(self.debug_dir, "logs", execution_id)
    archive_path = os.path.join(self.debug_dir, "archives", f"{execution_id}.tar.gz")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_dir, arcname=execution_id)
    # 更新 TaskExecution.execution_snapshot
    TaskExecution.objects.filter(id=execution_id).update(
        execution_snapshot__archive_path=archive_path
    )
    return archive_path
```

### 8.3 清理策略

Celery beat 定时任务清理 30 天前的归档：

```python
@shared_task
def cleanup_old_archives():
    """清理 30 天前的归档文件"""
    archive_dir = settings.DEBUG_ARCHIVE_DIR
    cutoff = timezone.now() - timedelta(days=30)
    for archive in Path(archive_dir).glob("*.tar.gz"):
        if archive.stat().st_mtime < cutoff.timestamp():
            archive.unlink()
```

---

## 9. 实施优先级

按"投入产出比"排序，分 4 个阶段：

### 阶段 1：竞态修复 + 日志补全（最高优先级）

| 任务 | 文件 | 工作量 |
|---|---|---|
| 实现 `wait_for_change_lightweight` | `agent/src/core/wait_freezes.py` | 小 |
| ClickNode 集成默认防护 | `agent/src/engine/nodes/click.py` | 中 |
| `extract_result_fields` 补 `click` 分支 | `agent/src/utils/structured_logger.py` | 小 |
| `extract_result_fields` 增强 `ocr` 分支 | 同上 | 小 |
| engine 传 `variables_snapshot` | `agent/src/engine/engine.py` | 小 |
| 跨步骤关联字段（previous_node_id 等） | 同上 | 中 |
| `AutoResult` 增加 node_id/node_type/error_code | `agent/src/core/result.py` | 小 |

### 阶段 2：截图双保留 + 视觉工具

| 任务 | 文件 | 工作量 |
|---|---|---|
| `DebugImageSaver` 增加原图保存 | `agent/src/utils/debug_image_saver.py` | 中 |
| JSONL 增加 `raw_screenshot_path` 字段 | `agent/src/utils/structured_logger.py` | 小 |
| `get_screenshot_base64` 工具 | `backend/gaf_ai/agent/tools.py` | 中 |
| `get_structured_log` 工具 | 同上 | 中 |
| LLM 路由按模型能力暴露工具 | `backend/gaf_ai/llm_router.py` | 小 |

### 阶段 3：post_verify + 恢复增强

| 任务 | 文件 | 工作量 |
|---|---|---|
| 抽出 `core/verify.py` 模块 | `agent/src/core/verify.py`（新建） | 中 |
| PipelineEngine 集成 post_verify | `agent/src/engine/engine.py` | 中 |
| `interface_recovery` 换路径策略 | `agent/src/core/interface_recovery.py` | 中 |
| transient 参数配置化 | 同上 | 小 |

### 阶段 4：数据库边界 + 异常检测闭环

| 任务 | 文件 | 工作量 |
|---|---|---|
| `DatabaseLogHandler` → `FileLogHandler` | `backend/gaf_core/handlers.py` | 中 |
| `tracing/middleware.py` 移除 DB 写入 | `backend/tracing/middleware.py` | 小 |
| 异常检测改扫 JSONL | `backend/gaf_ai/views_anomaly.py` | 中 |
| 定时任务（daily_anomaly_scan + cleanup） | `backend/gaf_ai/tasks.py` | 小 |
| Agent 端即时诊断读 JSONL 内容 | `agent/src/core/orchestrator.py` | 小 |
| `search_similar_errors` 改扫 JSONL | `backend/gaf_ai/agent/tools.py` | 中 |

---

## 10. 测试策略

### 10.1 单元测试

- `wait_for_change_lightweight`：CHANGED/UNCHANGED/TIMEOUT/SKIPPED 四种返回
- `extract_result_fields` 的 `click` / `ocr` / `wait` / `swipe_until` 新分支（含 OCR `texts` 截断到前 10 条 + 每条 200 字符的边界测试）
- `AutoResult` 的 node_id/node_type/error_code 字段填充
- `Verifier.verify` 的 6 种验证类型
- `DebugImageSaver._save_raw_image` 的 JPEG 压缩（验证 q=85 + 文件名与 annotated/ 一致）

### 10.2 集成测试

- 端到端 pipeline：click 节点后画面未变化 → JSONL 记录 `screen_change_outcome=UNCHANGED` + warning
- 端到端 pipeline：click 节点配置 `post_verify` → 验证失败 → result.failed=True + error_code=POST_VERIFY_FAILED
- 截图双保留：识别类节点生成 raw/ + annotated/ 两张图，文件名一致
- AI 诊断：ReAct Agent 调用 `get_screenshot_base64` 返回有效 base64

### 10.3 回归测试

- 现有 pipeline（如 `daily_sign_in.yaml`、`stage_battle.yaml`）行为不变
- 现有 JSONL 测试（`test_structured_logger.py`）通过
- 现有 `DatabaseLogHandler` 测试改为 `FileLogHandler` 后通过

---

## 11. 风险与缓解

| 风险 | 缓解措施 |
|---|---|
| `wait_for_change_lightweight` 在慢设备上误报 UNCHANGED | 默认 2s 超时可配置；UNCHANGED 只记 warning 不 fail |
| `variables_snapshot` 序列化大对象阻塞 pipeline | 白名单过滤 + 2000 字符截断 + try/except 兜底 |
| 截图双保留导致存储成本上升 | 仅识别类节点保留原图；JPEG q85 压缩；30 天清理 |
| 废弃 `LogEntry` 表影响现有异常检测 | 阶段 4 同步改造异常检测为扫 JSONL |
| `interface_recovery` 换路径策略可能死循环 | `attempt` 参数限制最多 2 次；`_used_edges` 防止重复路径 |
| 视觉工具消耗大量 token | LLM 路由按模型能力暴露；默认不调用，LLM 主动判断需要时才调 |

---

## 12. 验收标准

### 12.1 日志归一化

- [x] 普通 click 节点的 `x/y/button/clicks` 出现在 JSONL 中
- [x] OCR 节点的 `texts` 前 10 条出现在 JSONL 中
- [x] 所有节点的 JSONL 包含 `previous_node_id` / `previous_node_type` / `inter_node_gap_ms`
- [x] 失败节点的 JSONL 包含 `error_code` 字段
- [x] `variables_snapshot` 字段实际有值（非 null）

### 12.2 竞态修复

- [x] ClickNode 默认调用 `wait_for_change_lightweight`
- [x] 画面变化时立即返回（< 200ms）
- [x] 画面未变化时记 warning，但不 fail
- [x] `expect_screen_change: false` 可关闭默认防护
- [x] `post_verify` 配置存在时执行强验证

### 12.3 截图双保留

- [x] `ocr` / `template_match` / `feature_match` / `color_detect` 节点生成 raw/ + annotated/ 两张图
- [x] `click` / `swipe` / `key_press` / `wait` 节点只生成 annotated/
- [x] raw/ 目录图片为 JPEG 格式
- [x] JSONL 同时记录 `screenshot_path` 和 `raw_screenshot_path`

### 12.4 AI 诊断

- [x] ReAct Agent 可调用 `get_screenshot_base64` 工具
- [x] ReAct Agent 可调用 `get_structured_log` 工具
- [x] Agent 端即时诊断的 `error_context` 包含 `structured_log_content`（非空）
- [x] 异常检测改为扫 JSONL 文件，不再查 `LogEntry` 表
- [x] 每天 2 点定时扫描异常模式

### 12.5 数据库边界

- [x] `LogEntry` 表不再有新数据写入
- [x] `TraceSpan` 表不再有新数据写入
- [x] `TaskExecution.execution_snapshot` 包含 `archive_path`
- [x] 任务完成后生成 `<execution_id>.tar.gz` 归档
- [x] 30 天前的归档自动清理

---

## 13. 后续工作（非本规格范围）

- SSIMChecker 接入 ScreenshotManager 热路径（提升画面变化检测精度）
- RAG 索引历史执行的步骤链（不只是代码文档）
- TraceSpan 真正的父子 span 嵌套（OpenTelemetry 风格）
- 视觉 LLM 自动诊断（无需用户主动调用 ReAct Agent）
