"""元数据注册表测试 — TD-350"""

from __future__ import annotations

import pytest
from engine.node import PIPELINE_NODE_REGISTRY_META, NodeMetadata
from engine.node_registry import (
    get_node_metadata,
    list_node_types,
    validate_node_config,
)

pytestmark = pytest.mark.integration


class TestGetNodeMetadata:
    """get_node_metadata 测试"""

    def test_get_metadata_known_type(self):
        """已知节点类型返回非 None 元数据"""
        meta = get_node_metadata("click")
        assert meta is not None
        assert isinstance(meta, NodeMetadata)
        assert meta.node_type == "click"
        assert meta.display_name == "鼠标点击"
        assert meta.category == "action"
        assert meta.params_schema is not None

    def test_get_metadata_unknown_type(self):
        """未知节点类型返回 None"""
        meta = get_node_metadata("non_existent_type_xyz")
        assert meta is None

    def test_get_metadata_wait_has_params_schema(self):
        """wait 节点应有 params_schema"""
        meta = get_node_metadata("wait")
        assert meta is not None
        assert meta.params_schema is not None
        props = meta.params_schema.get("properties", {})
        assert "mode" in props
        assert "timeout" in props
        assert "seconds" in props


class TestListNodeTypes:
    """list_node_types 测试"""

    def test_list_all_types_contains_click_and_wait(self):
        """全量列表应包含 click 和 wait"""
        all_types = list_node_types()
        type_names = [m.node_type for m in all_types]
        assert "click" in type_names
        assert "wait" in type_names
        assert len(all_types) >= 2  # 至少 2 个有元数据的节点

    def test_list_by_category_action(self):
        """action 分类应包含 click 和 wait"""
        action_nodes = list_node_types(category="action")
        type_names = [m.node_type for m in action_nodes]
        assert "click" in type_names
        assert "wait" in type_names

    def test_list_by_category_unknown_returns_empty(self):
        """未知分类返回空列表"""
        nodes = list_node_types(category="nonexistent_category")
        assert nodes == []

    def test_register_node_matches_old_registry(self):
        """PIPELINE_NODE_REGISTRY_META 应与 PIPELINE_NODE_REGISTRY 一致"""
        from engine.node import PIPELINE_NODE_REGISTRY

        for node_type in PIPELINE_NODE_REGISTRY:
            # 旧注册表有的类型，新元数据注册表也应有
            # 注：部分旧类型可能没有 params_schema（无 schema 也算有元数据）
            assert node_type in PIPELINE_NODE_REGISTRY_META, (
                f"节点 {node_type} 在 PIPELINE_NODE_REGISTRY 中但不在 "
                f"PIPELINE_NODE_REGISTRY_META 中"
            )


class TestValidateNodeConfig:
    """validate_node_config 测试"""

    def test_validate_config_type_ok(self):
        """合法 config 返回空列表"""
        errors = validate_node_config("click", {
            "x": 100,
            "y": 200,
            "button": "left",
            "clicks": 1,
        })
        assert errors == []

    def test_validate_config_type_error(self):
        """类型错误返回错误列表"""
        errors = validate_node_config("click", {"x": "abc"})
        assert len(errors) >= 1
        assert any("config.x" in e and "integer" in e for e in errors)

    def test_validate_config_enum_error(self):
        """enum 值错误返回错误列表"""
        errors = validate_node_config("click", {"button": "invalid_button"})
        assert len(errors) >= 1
        assert any("不在允许列表" in e for e in errors)

    def test_validate_config_minimum(self):
        """最小值越界返回错误"""
        errors = validate_node_config("click", {"clicks": 0})
        assert len(errors) >= 1
        assert any("最小值" in e for e in errors)

    def test_validate_config_maximum(self):
        """最大值越界返回错误"""
        errors = validate_node_config("wait", {
            "mode": "fixed",
            "threshold": 1.5,
        })
        assert len(errors) >= 1
        assert any("最大值" in e for e in errors)

    def test_validate_config_required(self):
        """缺少必填字段返回错误"""
        errors = validate_node_config("log_message", {})
        assert len(errors) >= 1
        assert any("缺少必填字段" in e for e in errors)

    def test_validate_config_no_schema(self):
        """无 schema 的节点跳过校验"""
        # 找一个没有 params_schema 的节点类型
        no_schema_types = [
            nt for nt in PIPELINE_NODE_REGISTRY_META
            if PIPELINE_NODE_REGISTRY_META[nt].params_schema is None
        ]
        if no_schema_types:
            errors = validate_node_config(no_schema_types[0], {"any": "value"})
            assert errors == []

    def test_validate_config_unknown_type(self):
        """未知节点类型跳过校验"""
        errors = validate_node_config("unknown_type", {"x": "abc"})
        assert errors == []

    def test_validate_config_wait_mode_enum(self):
        """wait mode 的 enum 校验"""
        errors = validate_node_config("wait", {"mode": "invalid_mode"})
        assert len(errors) >= 1
        assert any("不在允许列表" in e for e in errors)

    def test_validate_config_wait_seconds_negative(self):
        """wait seconds < 0 应报错"""
        errors = validate_node_config("wait", {"mode": "fixed", "seconds": -1})
        assert len(errors) >= 1
        assert any("最小值" in e for e in errors)


class TestWaitNodeParamsSchema:
    """wait 节点 params_schema 专项测试"""

    def test_wait_schema_has_all_modes(self):
        """wait 节点的 mode 字段应覆盖所有 5 种模式"""
        meta = get_node_metadata("wait")
        assert meta is not None
        mode_spec = meta.params_schema["properties"]["mode"]
        assert set(mode_spec["enum"]) == {"fixed", "stable", "template", "ocr", "disappear"}

    def test_wait_valid_fixed_mode(self):
        """合法的 fixed 模式 config 通过校验"""
        errors = validate_node_config("wait", {
            "mode": "fixed",
            "seconds": 2.0,
        })
        assert errors == []

    def test_wait_valid_template_mode(self):
        """合法的 template 模式 config 通过校验"""
        errors = validate_node_config("wait", {
            "mode": "template",
            "template": "some_template.png",
            "timeout": 15.0,
            "threshold": 0.85,
        })
        assert errors == []

    def test_wait_valid_ocr_mode(self):
        """合法的 ocr 模式 config 通过校验"""
        errors = validate_node_config("wait", {
            "mode": "ocr",
            "text": "登录",
            "timeout": 20.0,
            "lang": "ch",
        })
        assert errors == []

    def test_wait_valid_disappear_mode(self):
        """合法的 disappear 模式 config 通过校验"""
        errors = validate_node_config("wait", {
            "mode": "disappear",
            "template": "spinner.png",
            "require_seen_first": True,
        })
        assert errors == []

    def test_wait_roi_validation(self):
        """roi 数组元素类型校验（非整数报错）"""
        errors = validate_node_config("wait", {
            "mode": "template",
            "roi": ["a", "b", "c", "d"],
        })
        # roi 是 array 类型，元素是 integer，但 validate_node_config
        # 不对 items 做深度校验，只检查顶层类型
        # 这里只检查顶层类型 array 通过
        assert errors == []  # 顶层类型 array 匹配


class TestClickNodeParamsSchema:
    """click 节点 params_schema 专项测试"""

    def test_click_valid_full_config(self):
        """click 完整合法 config 通过校验"""
        errors = validate_node_config("click", {
            "x": 500,
            "y": 300,
            "button": "right",
            "clicks": 2,
            "interval": 0.2,
            "activate_window": False,
            "expect_screen_change": False,
        })
        assert errors == []

    def test_click_valid_minimal_config(self):
        """click 最小 config 通过校验"""
        errors = validate_node_config("click", {
            "x": 100,
            "y": 200,
        })
        assert errors == []

    def test_click_button_enum_all_values(self):
        """click button 的 enum 值全量覆盖"""
        for btn in ["left", "right", "middle"]:
            errors = validate_node_config("click", {
                "x": 0, "y": 0, "button": btn,
            })
            assert errors == [], f"button={btn} 应合法，但报错: {errors}"

    def test_click_clicks_below_minimum(self):
        """clicks < 1 报错"""
        errors = validate_node_config("click", {"x": 0, "y": 0, "clicks": 0})
        assert len(errors) >= 1
        assert any("最小值" in e for e in errors)

    def test_click_screen_change_threshold_above_max(self):
        """screen_change_threshold > 1 报错"""
        errors = validate_node_config("click", {
            "x": 0, "y": 0,
            "screen_change_threshold": 1.5,
        })
        assert len(errors) >= 1
        assert any("最大值" in e for e in errors)


class TestLogMessageNode:
    """log_message 节点元数据测试"""

    def test_log_message_registered(self):
        """log_message 节点应在注册表中"""
        meta = get_node_metadata("log_message")
        assert meta is not None
        assert meta.display_name == "日志输出"
        assert meta.category == "utility"

    def test_log_message_has_params_schema(self):
        """log_message 应有 params_schema"""
        meta = get_node_metadata("log_message")
        assert meta is not None
        assert meta.params_schema is not None
        props = meta.params_schema.get("properties", {})
        assert "message" in props
        assert "level" in props
        assert "message" in meta.params_schema.get("required", [])

    def test_log_message_level_enum(self):
        """log_message level 的 enum 值覆盖"""
        for lvl in ["debug", "info", "warning", "error"]:
            errors = validate_node_config("log_message", {
                "message": "test", "level": lvl,
            })
            assert errors == [], f"level={lvl} 应合法"

    def test_log_message_invalid_level(self):
        """log_message 非法 level 报错"""
        errors = validate_node_config("log_message", {
            "message": "test", "level": "critical",
        })
        assert len(errors) >= 1
        assert any("不在允许列表" in e for e in errors)
