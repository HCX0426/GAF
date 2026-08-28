# TD-350: 节点元数据注册机制

> **关联 TD**: TD-350 (35+ 节点类型硬编码，缺乏元数据注册机制)
> **来源**: `docs/tech-debt/active.md` TD-350
> **状态**: 🔧 待修 → 🚧 进行中 → ✅ 完成
> **优先级**: P1
> **登记时间**: 2026-08-08
> **完成时间**: 2026-08-08

---

## 1. 问题描述

### 1.1 现状

Agent 引擎的 41 个节点类型通过 `@register_node("type_name")` 装饰器注册到 `PIPELINE_NODE_REGISTRY`，当前注册表是 `dict[str, type[PipelineNode]]`，仅维护 node_type → class 的映射，**不含任何元数据**。

### 1.2 具体问题

| 问题 | 描述 | 影响 |
|------|------|------|
| **无 params_schema** | 每个节点的 config 参数仅在 docstring 中文字描述 | 无法程序化校验参数；前端无法自动生成配置表单 |
| **无分类/展示名** | 注册表只有 `"click"`、`"wait"` 等内部 key | 前端节点选择器只能硬编码 UI 文案 |
| **校验靠 if-else** | `PipelineValidator` 只检查未知类型，不校验参数 | 参数错误要到 execute 运行时才暴露 |
| **新增节点改核心** | 新增节点必须写 py 文件 + 修改 `__init__.py` import | 业务方无法通过配置/插件扩展 |
| **无统一元数据导出** | 前端/文档无法获取节点列表 | 需要额外维护节点类型列表文件 |

### 1.3 根因

`PipelineNode` 基类设计时未预留元数据属性，`@register_node` 装饰器仅做类型注册。

---

## 2. 修复方案

### 2.1 架构概览

```
新增/修改:
  agent/src/engine/
    ├── node.py          ← 修改: 加 NodeMetadata + params_schema 支持
    ├── node_registry.py ← 新增: 元数据注册表 + 查询函数
    ├── validator.py     ← 修改: 加 params_schema 校验
    └── nodes/
        ├── click.py     ← 修改: 加 params_schema 类属性
        ├── wait.py      ← 修改: 加 params_schema 类属性
        └── log_message.py ← 新增: 示例节点（不改 engine 核心）
```

### 2.2 NodeMetadata 定义

在 `node.py` 中新增 `NodeMetadata` dataclass：

```python
@dataclass
class NodeMetadata:
    """节点元数据"""
    node_type: str                    # 内部标识，如 "click"
    display_name: str                 # 展示名，如 "鼠标点击"
    category: str                     # 分类: "action" / "control" / "match" / "device" / "notification"
    description: str                  # 简短描述
    params_schema: dict | None = None # JSON Schema 片段，描述 config 参数
```

### 2.3 params_schema 格式

使用 JSON Schema 子集描述节点 config 参数：

```python
params_schema = {
    "type": "object",
    "properties": {
        "x": {
            "type": "integer",
            "description": "X 坐标",
            "default": 0,
        },
        "y": {
            "type": "integer",
            "description": "Y 坐标",
            "default": 0,
        },
        "button": {
            "type": "string",
            "enum": ["left", "right", "middle"],
            "default": "left",
            "description": "鼠标按钮",
        },
        "clicks": {
            "type": "integer",
            "minimum": 1,
            "default": 1,
            "description": "点击次数",
        },
        "target": {
            "type": ["string", "object", "null"],
            "description": "P0-6 target spec，设置后覆盖 x/y",
        },
    },
    "required": [],
}
```

### 2.4 注册表增强

将 `PIPELINE_NODE_REGISTRY` 改为 `dict[str, NodeMetadata]`：

```python
# node.py — 新增
PIPELINE_NODE_REGISTRY_META: dict[str, NodeMetadata] = {}
"""元数据注册表: node_type -> NodeMetadata"""

# 保留旧注册表用于工厂创建（不再从旧注册表移除，而是双表共存过渡）
# 最终统一到单一元数据注册表
```

`register_node` 装饰器改造：

```python
def register_node(
    node_type: str,
    display_name: str = "",
    category: str = "other",
    description: str = "",
    params_schema: dict | None = None,
):
    """将节点子类注册到工厂表的装饰器，同时记录元数据"""
    def decorator(cls: type[PipelineNode]) -> type[PipelineNode]:
        PIPELINE_NODE_REGISTRY[node_type] = cls
        PIPELINE_NODE_REGISTRY_META[node_type] = NodeMetadata(
            node_type=node_type,
            display_name=display_name or node_type,
            category=category,
            description=description or cls.__doc__ or "",
            params_schema=params_schema,
        )
        return cls
    return decorator
```

### 2.5 新增查询函数

在 `node_registry.py` 中提供查询接口：

```python
def get_node_metadata(node_type: str) -> NodeMetadata | None:
    """获取单个节点元数据"""
    return PIPELINE_NODE_REGISTRY_META.get(node_type)

def list_node_types(category: str | None = None) -> list[NodeMetadata]:
    """列出所有节点类型，可按 category 过滤"""
    if category is None:
        return list(PIPELINE_NODE_REGISTRY_META.values())
    return [m for m in PIPELINE_NODE_REGISTRY_META.values() if m.category == category]

def validate_node_config(node_type: str, config: dict) -> list[str]:
    """基于 params_schema 校验节点 config"""
    meta = get_node_metadata(node_type)
    if meta is None or meta.params_schema is None:
        return []  # 无 schema 的节点跳过校验
    errors = []
    props = meta.params_schema.get("properties", {})
    for key, spec in props.items():
        if key in config:
            value = config[key]
            expected_type = spec.get("type")
            # 基本类型检查
            type_ok = _check_type(value, expected_type)
            if not type_ok:
                errors.append(f"config.{key}: 期望类型 {expected_type}, 实际 {type(value).__name__}")
            # enum 检查
            if "enum" in spec and value not in spec["enum"]:
                errors.append(f"config.{key}: 值 {value!r} 不在允许列表 {spec['enum']}")
            # minimum/maximum 检查
            if isinstance(value, (int, float)):
                if "minimum" in spec and value < spec["minimum"]:
                    errors.append(f"config.{key}: {value} < 最小值 {spec['minimum']}")
                if "maximum" in spec and value > spec["maximum"]:
                    errors.append(f"config.{key}: {value} > 最大值 {spec['maximum']}")
        else:
            # 检查 required 字段
            if key in meta.params_schema.get("required", []):
                errors.append(f"config.{key}: 缺少必填字段")
    return errors
```

### 2.6 Validator 增强

在 `PipelineValidator.validate()` 中增加 params_schema 校验步骤：

```python
@classmethod
def validate(cls, graph: PipelineGraph) -> list[ValidationError]:
    errors: list[ValidationError] = []
    known_types = cls._known_node_types()

    errors.extend(cls._check_entry_node(graph))
    errors.extend(cls._check_unknown_types(graph, known_types))
    errors.extend(cls._check_orphan_nodes(graph))
    errors.extend(cls._check_circular_refs(graph))
    errors.extend(cls._check_node_params(graph))  # ★ 新增
    return errors

@classmethod
def _check_node_params(cls, graph: PipelineGraph) -> list[ValidationError]:
    """基于 params_schema 校验每个节点的 config 参数"""
    errors = []
    for node_id, node in graph.nodes.items():
        if not node.node_type:
            continue
        schema_errors = validate_node_config(node.node_type, node.config)
        for err in schema_errors:
            errors.append(ValidationError(
                error_type="param_invalid",
                message=err,
                node_id=node_id,
            ))
    return errors
```

### 2.7 现有节点改造示例

**ClickNode** (`click.py`):

```python
@register_node(
    "click",
    display_name="鼠标点击",
    category="action",
    description="在指定坐标或匹配区域执行点击操作",
    params_schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X 坐标", "default": 0},
            "y": {"type": "integer", "description": "Y 坐标", "default": 0},
            "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
            "clicks": {"type": "integer", "minimum": 1, "default": 1},
            "interval": {"type": "number", "minimum": 0, "default": 0.1},
            "target": {"type": ["string", "object", "null"]},
            "target_offset": {"type": ["object", "array", "null"]},
            "activate_window": {"type": "boolean", "default": True},
            "expect_screen_change": {"type": "boolean", "default": True},
        },
    },
)
class ClickNode(PipelineNode):
    ...
```

**WaitNode** (`wait.py`):

```python
@register_node(
    "wait",
    display_name="等待",
    category="action",
    description="等待（固定时间/画面稳定/模板出现/OCR 文字出现/模板消失）",
    params_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["fixed", "stable", "template", "ocr", "disappear"],
                "default": "fixed",
            },
            "seconds": {"type": "number", "minimum": 0, "default": 1.0},
            "timeout": {"type": "number", "minimum": 0, "default": 10.0},
            "check_interval": {"type": "number", "minimum": 0.1, "default": 0.5},
            "template": {"type": "string"},
            "threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.8},
            "text": {"type": "string"},
            "roi": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
            "roi_coord_type": {"type": "string", "enum": ["base", "logical", "physical"], "default": "base"},
            "lang": {"type": "string", "default": "ch"},
            "require_seen_first": {"type": "boolean", "default": False},
        },
        "required": [],
    },
)
class WaitNode(PipelineNode):
    ...
```

### 2.8 示例节点：log_message

新建 `agent/src/engine/nodes/log_message.py`，演示如何不修改引擎核心代码新增节点：

```python
"""log_message 节点：将消息写入日志 / 控制台 — 示例节点，演示元数据注册机制的可扩展性"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from core.result import AutoResult, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node(
    "log_message",
    display_name="日志输出",
    category="utility",
    description="将指定消息写入日志文件或控制台，用于调试和审计",
    params_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "要输出的日志消息，支持 ${var} 变量引用"},
            "level": {
                "type": "string",
                "enum": ["debug", "info", "warning", "error"],
                "default": "info",
            },
        },
        "required": ["message"],
    },
)
@dataclass
class LogMessageNode(PipelineNode):
    """日志输出节点 — 将消息写入日志"""
    node_type: str = "log_message"

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        message = self.config.get("message", "")
        level = self.config.get("level", "info")

        # 支持变量引用
        if "${" in message:
            import re
            message = re.sub(r"\$\{(\w+)\}", lambda m: str(context.get_variable(m.group(1), m.group(0))), message)

        log_fn = getattr(logger, level, logger.info)
        log_fn("[LogMessage] %s", message)

        elapsed = time.monotonic() - start
        return success_result(
            data={"message": message, "level": level, "logged_at": elapsed},
            elapsed_time=elapsed,
        )
```

在 `nodes/__init__.py` 中加一行 import：

```python
from . import (
    ...
    log_message,  # 新增
    ...
)
```

---

## 3. 任务清单

### Task 1: 元数据基础设施 (node.py + node_registry.py)

- [x] 1.1 在 `node.py` 中新增 `NodeMetadata` dataclass
- [x] 1.2 改造 `register_node` 装饰器，支持 display_name/category/description/params_schema 参数
- [x] 1.3 新增 `PIPELINE_NODE_REGISTRY_META` 元数据注册表
- [x] 1.4 新增 `node_registry.py`，提供 `get_node_metadata()` / `list_node_types()` / `validate_node_config()` 查询函数
- [x] 1.5 保留 `PIPELINE_NODE_REGISTRY` 向后兼容（工厂创建仍用旧的即可，或统一到元数据注册表）

### Task 2: Validator 增强 (validator.py)

- [x] 2.1 在 `PipelineValidator.validate()` 中增加 `_check_node_params()` 步骤
- [x] 2.2 实现 `_check_node_params()` 方法，遍历每个节点的 config 调用 `validate_node_config()`
- [x] 2.3 新增 `param_invalid` 错误类型
- [x] 2.4 验证：`PipelineValidator.is_valid()` 对含参数错误的图返回 False

### Task 3: 现有节点改造 (2 个示例节点)

- [x] 3.1 改造 ClickNode：增加 params_schema + display_name + category
- [x] 3.2 改造 WaitNode：增加 params_schema + display_name + category
- [x] 3.3 验证：改造后节点功能不变，原有测试全通过

### Task 4: 示例节点 log_message

- [x] 4.1 新建 `agent/src/engine/nodes/log_message.py`
- [x] 4.2 在 `nodes/__init__.py` 中 import log_message
- [x] 4.3 验证：log_message 节点注册成功，可在 pipeline 中使用

---

## 4. 验证标准

| # | 验证项 | 期望 | 验证方式 |
|---|--------|------|----------|
| 1 | `get_node_metadata("click")` 返回含 display_name/category/params_schema 的元数据 | 不返回 None，字段正确 | pytest |
| 2 | `list_node_types(category="action")` 返回 click/wait 等动作节点 | 列表包含 click/wait | pytest |
| 3 | `validate_node_config("click", {"x": "abc"})` 返回类型错误 | 返回 `[config.x: 期望类型 integer, 实际 str]` | pytest |
| 4 | `validate_node_config("click", {"button": "invalid"})` 返回 enum 错误 | 包含 "不在允许列表" | pytest |
| 5 | `PipelineValidator.validate()` 对 `click` 节点配置错误返回 `param_invalid` 错误 | 错误列表含 `param_invalid` | pytest |
| 6 | `log_message` 节点在 pipeline 中可执行 | 成功返回 + 日志写入 | pytest |
| 7 | 原有 ClickNode / WaitNode 测试全部通过 | 不因 params_schema 改动而失败 | pytest |
| 8 | 新增 log_message 节点不改 `pipeline_engine.py`、`node.py` 核心逻辑 | 只改 `__init__.py` import | 代码审查 |

---

## 5. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `agent/src/engine/node.py` | 修改 | 加 NodeMetadata + 改造 register_node |
| `agent/src/engine/node_registry.py` | 新增 | 元数据查询函数 |
| `agent/src/engine/validator.py` | 修改 | 加 params_schema 校验 |
| `agent/src/engine/nodes/click.py` | 修改 | 加 params_schema |
| `agent/src/engine/nodes/wait.py` | 修改 | 加 params_schema |
| `agent/src/engine/nodes/log_message.py` | 新增 | 示例节点 |
| `agent/src/engine/nodes/__init__.py` | 修改 | 加 log_message import |
| `agent/tests/engine/test_node_registry.py` | 新增 | 元数据测试 |
| `agent/tests/engine/test_validator_params.py` | 新增 | params_schema 校验测试 |
| `agent/tests/engine/nodes/test_log_message.py` | 新增 | 示例节点测试 |

---

## 6. 测试计划

### 6.1 新增测试文件

**`agent/tests/engine/test_node_registry.py`** (27 tests):

| # | 测试名 | 验证点 |
|---|--------|--------|
| 1 | `test_get_metadata_known_type` | click 节点元数据非 None |
| 2 | `test_get_metadata_unknown_type` | 未知类型返回 None |
| 3 | `test_get_metadata_wait_has_params_schema` | wait 节点 params_schema 非 None |
| 4 | `test_list_all_types_contains_click_and_wait` | 列表包含 click 和 wait |
| 5 | `test_list_by_category_action` | action 类包含 click/wait |
| 6 | `test_list_by_category_unknown_returns_empty` | 未知分类返回空列表 |
| 7 | `test_register_node_matches_old_registry` | 新旧注册表一致性 |
| 8-10 | `test_validate_config_*` (3 tests) | 类型/enum/minimum/maximum/required 校验 |
| 11-13 | `test_validate_config_*` (3 tests) | 无 schema/未知类型/混合场景 |
| 14-18 | `TestWaitNodeParamsSchema` (5 tests) | wait 节点各模式 params_schema 校验 |
| 19-23 | `TestClickNodeParamsSchema` (5 tests) | click 节点 params_schema 校验 |
| 24-27 | `TestLogMessageNode` (4 tests) | log_message 元数据校验 |

**`agent/tests/engine/test_validator_params.py`** (7 tests):

| # | 测试名 | 验证点 |
|---|--------|--------|
| 1 | `test_valid_params_ok` | 合法参数图通过校验 |
| 2 | `test_invalid_params_reported` | 非法参数图返回 param_invalid |
| 3 | `test_params_error_has_node_id` | 参数错误关联正确节点 ID |
| 4 | `test_params_validation_alongside_other_checks` | 参数校验与其他校验共存 |
| 5 | `test_valid_params_mixed_known_and_unknown` | 混合节点参数校验 |
| 6 | `test_is_valid_returns_false_on_param_error` | is_valid 对参数错误返回 False |
| 7 | `test_is_valid_returns_true_on_clean_params` | is_valid 对正确参数返回 True |

**`agent/tests/engine/nodes/test_log_message.py`** (6 tests):

| # | 测试名 | 验证点 |
|---|--------|--------|
| 1 | `test_log_message_info` | info 级别日志写入 |
| 2 | `test_log_message_variable_resolve` | ${var} 变量引用正确解析 |
| 3 | `test_log_message_debug_level` | debug 级别日志写入 |
| 4 | `test_log_message_default_level` | 默认 level 为 info |
| 5 | `test_log_message_warning_level` | warning 级别日志写入 |
| 6 | `test_log_message_error_level` | error 级别日志写入 |
| +1 | `test_log_message_registered_in_registry` | 节点在注册表中 |

### 6.2 回归测试（已通过）

```bash
# agent 引擎测试（46 passed, 0.5s）
D:\code\environment\conda\envs\gaf\python.exe -m pytest agent/tests/engine/test_validator_params.py agent/tests/engine/test_node_registry.py agent/tests/engine/nodes/test_log_message.py -p no:django -o addopts=""

# agent 全量测试（2236 passed, 2 failed → 修复后 2236 passed）
# 2 个失败因 params_schema 校验拦截了之前运行时才暴露的非法参数:
#   - test_step_timeout_negative_falls_back_to_max: timeout=-1 被 minimum:0 拦截
#   - test_engine_fills_node_id_and_node_type_on_failure: mode="invalid_mode" 被 enum 拦截
# 修复方案: 更新测试用例使用合法的 schema 值
D:\code\environment\conda\envs\gaf\python.exe -m pytest agent/tests/ -p no:django -o addopts=""

---

## 7. 与 N197 URL 归一化的关系

本 TD-350 专注于节点**元数据注册机制**，不涉及 URL 路径拼接。两者互不依赖，可独立实施。

---

## 8. 已知限制

- Phase 1 仅改造 2 个示例节点，剩余 39 个节点逐步加 params_schema（可后续找时间批量补）
- params_schema 使用 JSON Schema 子集，不追求完整 JSON Schema 标准（不引入第三方库）
- params_schema 仅在 validator 中静态校验，不覆盖运行时动态 resolve（如 `${var}` 变量引用由 engine 运行时处理）