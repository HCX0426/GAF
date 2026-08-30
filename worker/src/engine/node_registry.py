"""节点元数据注册表查询接口

提供基于 PIPELINE_NODE_REGISTRY_META 的元数据查询和参数校验函数。
"""

from __future__ import annotations

from typing import Any

from engine.node import PIPELINE_NODE_REGISTRY_META, NodeMetadata


def get_node_metadata(node_type: str) -> NodeMetadata | None:
    """获取单个节点元数据

    Args:
        node_type: 节点类型标识

    Returns:
        NodeMetadata 或 None（未知类型）
    """
    return PIPELINE_NODE_REGISTRY_META.get(node_type)


def list_node_types(category: str | None = None) -> list[NodeMetadata]:
    """列出所有节点类型，可按 category 过滤

    Args:
        category: 分类过滤，None 返回全部

    Returns:
        节点元数据列表
    """
    if category is None:
        return list(PIPELINE_NODE_REGISTRY_META.values())
    return [m for m in PIPELINE_NODE_REGISTRY_META.values() if m.category == category]


def _check_type(value: Any, expected_type: str | list[str]) -> bool:
    """检查值类型是否匹配 JSON Schema 类型描述

    Args:
        value: 要检查的值
        expected_type: JSON Schema 类型字符串或字符串列表

    Returns:
        类型是否匹配
    """
    # 支持联合类型如 ["string", "object", "null"]
    if isinstance(expected_type, list):
        return any(_check_type_single(value, t) for t in expected_type)
    return _check_type_single(value, expected_type)


def _check_type_single(value: Any, expected_type: str) -> bool:
    """单类型检查"""
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
        "null": type(None),
    }
    py_type = type_map.get(expected_type)
    if py_type is None:
        return True  # 未知类型不阻断
    if isinstance(py_type, tuple):
        return isinstance(value, py_type)
    return isinstance(value, py_type)


def validate_node_config(node_type: str, config: dict[str, Any]) -> list[str]:
    """基于 params_schema 校验节点 config

    Args:
        node_type: 节点类型标识
        config: 节点配置字典

    Returns:
        错误消息列表，空列表表示校验通过
    """
    meta = get_node_metadata(node_type)
    if meta is None or meta.params_schema is None:
        return []  # 无 schema 的节点跳过校验

    errors: list[str] = []
    props = meta.params_schema.get("properties", {})
    required_fields = meta.params_schema.get("required", [])

    for key, spec in props.items():
        if key in config:
            value = config[key]
            expected_type = spec.get("type")
            if expected_type is not None:
                type_ok = _check_type(value, expected_type)
                if not type_ok:
                    errors.append(
                        f"config.{key}: 期望类型 {expected_type}, "
                        f"实际 {type(value).__name__}"
                    )
            # enum 检查
            enum_values = spec.get("enum")
            if enum_values is not None and value not in enum_values:
                errors.append(
                    f"config.{key}: 值 {value!r} 不在允许列表 {enum_values}"
                )
            # minimum/maximum 检查（仅数值类型）
            if isinstance(value, (int, float)):
                minimum = spec.get("minimum")
                maximum = spec.get("maximum")
                if minimum is not None and value < minimum:
                    errors.append(
                        f"config.{key}: {value} < 最小值 {minimum}"
                    )
                if maximum is not None and value > maximum:
                    errors.append(
                        f"config.{key}: {value} > 最大值 {maximum}"
                    )
        else:
            # 检查 required 字段
            if key in required_fields:
                errors.append(f"config.{key}: 缺少必填字段")

    return errors
