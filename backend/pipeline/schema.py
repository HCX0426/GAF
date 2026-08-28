"""
Pipeline graph_data 的 JSON Schema 定义（Draft-07）
用于保存和 validate 时的结构校验
"""

# ALL_NODE_TYPES must cover the union of frontend editor (PipelineNodeType,
# frontend/src/types/models/pipeline.ts) and agent registry (@register_node,
# agent/src/engine/nodes/*.py) — cross-layer contract guarded by
# scripts/tests/test_pipeline_node_contract.py (s42).
#
# Deprecated BD2-AUTO legacy types (no frontend/agent support, kept for
# backward-compat of persisted pipelines; still consumed by
# validators.py field mapping + estimator.py duration table):
ALL_NODE_TYPES = [
    'click', 'swipe', 'key_press', 'text_input', 'long_press',
    'direct_hit', 'multi_swipe', 'multi_scroll', 'multi_touch', 'wheel',
    'template_match', 'template_match_any',
    'ocr', 'color_detect', 'feature_match', 'neural_network',
    'and_match', 'or_match', 'custom_match',
    'wait', 'branch', 'loop', 'random_delay', 'goto', 'sub_pipeline',
    'swipe_until', 'jump_back', 'wait_freezes', 'next', 'stop', 'anchor',
    'notify', 'device_control', 'monitor', 'start_app', 'stop_app',
    'sort_select', 'roi_resolver', 'nn_classifier', 'nn_regressor',
    'python_call', 'log_message',
    # --- UIAutomation 语义层 (spec-2026-08-26 P2, agent @register_node 同步) ---
    'uia_set_value', 'uia_invoke', 'uia_get_state', 'uia_get_window_title',
    'uia_select', 'uia_scroll',
    # --- deprecated legacy (BD2-AUTO, kept for backward-compat) ---
    'login_account', 'switch_account',
    'switch_resource', 'captcha_detect',
]

PIPELINE_GRAPH_SCHEMA = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'type': 'object',
    'required': ['nodes'],
    'properties': {
        'nodes': {
            'type': 'array',
            'items': {
                'type': 'object',
                'required': ['id'],
                'oneOf': [
                    # canvas schema (React Flow)
                    {
                        'type': 'object',
                        'required': ['id', 'type', 'position', 'data'],
                        'properties': {
                            'id': {'type': 'string'},
                            'type': {'type': 'string', 'enum': ALL_NODE_TYPES},
                            'position': {
                                'type': 'object',
                                'required': ['x', 'y'],
                                'properties': {
                                    'x': {'type': 'number'},
                                    'y': {'type': 'number'},
                                },
                            },
                            'data': {'type': 'object'},
                        },
                    },
                    # nested schema (agent / template.json)
                    {
                        'type': 'object',
                        'required': ['id', 'node_type', 'config'],
                        'properties': {
                            'id': {'type': 'string'},
                            'name': {'type': 'string'},
                            'node_type': {'type': 'string', 'enum': ALL_NODE_TYPES},
                            'config': {'type': 'object'},
                            # Task 3.4 (P2-4): retry/fallback 内部字段校验。
                            # 原先只校验 type=object, 不校验内部字段, 导致
                            # max_retries="3" (str) / base_delay=-1 (负数) 等
                            # 非法值能通过 schema 校验, agent 执行时才报错。
                            'retry': {
                                'type': 'object',
                                'properties': {
                                    'max_retries': {'type': 'integer', 'minimum': 0},
                                    'base_delay': {'type': 'number', 'minimum': 0},
                                },
                                'additionalProperties': False,
                            },
                            'fallback': {
                                'type': 'object',
                                'properties': {
                                    'action': {'type': 'string'},
                                    'target_node_id': {'type': 'string'},
                                },
                                'additionalProperties': False,
                            },
                            'next_node_id': {'type': 'string'},
                        },
                    },
                ],
            },
        },
        'edges': {
            'type': 'array',
            'items': {
                'type': 'object',
                'required': ['id', 'source', 'target'],
                'properties': {
                    'id': {'type': 'string'},
                    'source': {'type': 'string'},
                    'target': {'type': 'string'},
                    'sourceHandle': {'type': 'string'},
                    'targetHandle': {'type': 'string'},
                },
            },
        },
        'viewport': {
            'type': 'object',
            'properties': {
                'x': {'type': 'number'},
                'y': {'type': 'number'},
                'zoom': {'type': 'number'},
            },
        },
    },
}
