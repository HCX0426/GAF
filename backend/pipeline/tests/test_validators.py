# Merged from test_validators.py, test_validators_nested.py - 2026-08-04

"""Tests for pipeline.validators.PipelineValidator (pure logic, no DB needed).

The validator inspects a React Flow graph_data dict and returns a list of
CheckItem dicts with 'check', 'status', 'message', 'node_id', 'suggestion'.

_status values: 'pass', 'fail', 'warn'.
"""

import json
from pathlib import Path

from django.test import TestCase

from pipeline.validators import CheckItem, PipelineValidator, _dict_to_check


class CheckItemDataclassTests(TestCase):
    """CheckItem dataclass and _dict_to_check helper."""

    def test_check_item_defaults(self):
        item = CheckItem(check='c', status='pass', message='m')
        self.assertIsNone(item.node_id)
        self.assertEqual(item.suggestion, '')

    def test_dict_to_check_keys(self):
        item = CheckItem(check='c', status='pass', message='m', node_id='n1', suggestion='s')
        d = _dict_to_check(item)
        self.assertEqual(d['check'], 'c')
        self.assertEqual(d['status'], 'pass')
        self.assertEqual(d['message'], 'm')
        self.assertEqual(d['node_id'], 'n1')
        self.assertEqual(d['suggestion'], 's')


class RequiredFieldsTests(TestCase):
    """_check_required_fields: per-node-type required data fields."""

    def setUp(self):
        self.validator = PipelineValidator()

    def test_click_node_with_required_fields_passes(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'click', 'data': {'x': 100, 'y': 200}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        req_results = [r for r in results if r['check'] == 'required_fields']
        self.assertEqual(len(req_results), 1)
        self.assertEqual(req_results[0]['status'], 'pass')

    def test_click_node_missing_fields_fails(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'click', 'data': {}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        req = [r for r in results if r['check'] == 'required_fields'][0]
        self.assertEqual(req['status'], 'fail')
        self.assertIn('x', req['message'])
        self.assertIn('y', req['message'])
        self.assertEqual(req['suggestion'], '请在属性面板中填写对应字段')

    def test_swipe_node_requires_four_coords(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'swipe', 'data': {'x1': 1, 'y1': 2}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        req = [r for r in results if r['check'] == 'required_fields'][0]
        self.assertEqual(req['status'], 'fail')
        self.assertIn('x2', req['message'])
        self.assertIn('y2', req['message'])

    def test_unknown_node_type_no_required_fields(self):
        """Unknown node types default to empty required list -> pass."""
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'totally_unknown', 'data': {}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        req = [r for r in results if r['check'] == 'required_fields'][0]
        self.assertEqual(req['status'], 'pass')

    def test_node_with_null_data(self):
        """node.data = None should not crash; treated as empty dict."""
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'click', 'data': None},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        req = [r for r in results if r['check'] == 'required_fields'][0]
        self.assertEqual(req['status'], 'fail')

    def test_template_match_any_requires_templates_and_threshold(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'template_match_any',
                 'data': {'templates': ['t1'], 'threshold': 0.8}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        req = [r for r in results if r['check'] == 'required_fields'][0]
        self.assertEqual(req['status'], 'pass')


class TemplateRefsTests(TestCase):
    """_check_template_refs: template_id presence on template_match nodes.

    Task 4.2 (P0-3, 2026-07-28): canonical 字段名归一化为 `template_id`.
    兼容历史字段 templateId (canvas) / template (legacy agent nested).
    """

    def setUp(self):
        self.validator = PipelineValidator()

    def test_template_match_with_canonical_template_id_passes(self):
        """Task 4.2: canonical 字段 template_id 应通过校验."""
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'template_match',
                 'data': {'template_id': 'tpl-1', 'threshold': 0.8}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        tpl = [r for r in results if r['check'] == 'template_refs'][0]
        self.assertEqual(tpl['status'], 'pass')

    def test_template_match_with_legacy_template_id_passes(self):
        """Task 4.2: 兼容 canvas schema 的 templateId (camelCase) 字段."""
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'template_match',
                 'data': {'templateId': 'tpl-1', 'threshold': 0.8}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        tpl = [r for r in results if r['check'] == 'template_refs'][0]
        self.assertEqual(tpl['status'], 'pass')

    def test_template_match_with_legacy_template_field_passes(self):
        """Task 4.2: 兼容 agent nested schema 的 template 字段 (无 Id 后缀)."""
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'template_match',
                 'data': {'template': 'tpl-1', 'threshold': 0.8}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        tpl = [r for r in results if r['check'] == 'template_refs'][0]
        self.assertEqual(tpl['status'], 'pass')

    def test_template_match_without_template_id_fails(self):
        """Task 3.3 (P2-3): template_id 留空从 warn 升级为 fail。

        原因: backend validate 通过但 agent 执行时失败, 与 N192 B5
        「校验前置」原则相悖。新 suggestion 引导用户填模板 ID 或 base64。

        Task 4.2 (P0-3): 错误消息字段名改为 canonical `template_id`.
        """
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'template_match',
                 'data': {'threshold': 0.8}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        tpl = [r for r in results if r['check'] == 'template_refs'][0]
        self.assertEqual(tpl['status'], 'fail')
        self.assertIn('template_id', tpl['message'])
        self.assertEqual(
            tpl['suggestion'],
            '请在资源包中选择一个模板,或填写 base64 编码的模板图像',
        )

    def test_non_template_node_not_checked(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'click', 'data': {'x': 1, 'y': 2}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        self.assertEqual(len([r for r in results if r['check'] == 'template_refs']), 0)


class PipelineRefsTests(TestCase):
    """_check_pipeline_refs: sub_pipeline pipelineId existence check (DB-backed)."""

    def setUp(self):
        self.validator = PipelineValidator()
        from accounts.models import User
        from pipeline.models import Pipeline
        self.user = User.objects.create_user(username='val_user', password='Pass123!')
        self.real_pipeline = Pipeline.objects.create(
            name='Real Pipeline', user=self.user, graph_data={'nodes': [], 'edges': []},
        )

    def test_sub_pipeline_with_existing_pipeline_passes(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'sub_pipeline',
                 'data': {'pipelineId': str(self.real_pipeline.id)}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        pref = [r for r in results if r['check'] == 'pipeline_refs'][0]
        self.assertEqual(pref['status'], 'pass')

    def test_sub_pipeline_with_nonexistent_pipeline_fails(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'sub_pipeline',
                 'data': {'pipelineId': '999999'}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        pref = [r for r in results if r['check'] == 'pipeline_refs'][0]
        self.assertEqual(pref['status'], 'fail')
        self.assertIn('不存在', pref['message'])

    def test_sub_pipeline_without_pipeline_id_warns(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'sub_pipeline', 'data': {}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        pref = [r for r in results if r['check'] == 'pipeline_refs'][0]
        self.assertEqual(pref['status'], 'warn')

    # Task 4.37 (P0-9, 2026-07-28): canonical snake_case `pipeline_id` 也要被识别
    # 之前 _check_pipeline_refs 只读 `pipelineId` (legacy camelCase),
    # 前端 NodePropertyPanel 写 `pipeline_id` 时校验失效。
    def test_sub_pipeline_with_canonical_pipeline_id_passes(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'sub_pipeline',
                 'data': {'pipeline_id': str(self.real_pipeline.id)}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        pref = [r for r in results if r['check'] == 'pipeline_refs'][0]
        self.assertEqual(pref['status'], 'pass')

    def test_sub_pipeline_with_canonical_pipeline_id_nonexistent_fails(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'sub_pipeline',
                 'data': {'pipeline_id': '999999'}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        pref = [r for r in results if r['check'] == 'pipeline_refs'][0]
        self.assertEqual(pref['status'], 'fail')
        self.assertIn('不存在', pref['message'])


class ConnectivityTests(TestCase):
    """_check_connectivity: isolated node detection."""

    def setUp(self):
        self.validator = PipelineValidator()

    def test_single_node_not_flagged_as_isolated(self):
        """A single-node pipeline should not be flagged as isolated."""
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'click', 'data': {'x': 1, 'y': 2}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        conn = [r for r in results if r['check'] == 'connectivity']
        self.assertEqual(len(conn), 1)
        self.assertEqual(conn[0]['status'], 'pass')

    def test_isolated_node_warns_when_multiple_nodes(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'click', 'data': {'x': 1, 'y': 2}},
                {'id': 'n2', 'type': 'click', 'data': {'x': 3, 'y': 4}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        conn = [r for r in results if r['check'] == 'connectivity']
        self.assertTrue(all(r['status'] == 'warn' for r in conn))

    def test_connected_nodes_pass(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'click', 'data': {'x': 1, 'y': 2}},
                {'id': 'n2', 'type': 'click', 'data': {'x': 3, 'y': 4}},
            ],
            'edges': [
                {'id': 'e1', 'source': 'n1', 'target': 'n2'},
            ],
        }
        results = self.validator.validate(graph)
        conn = [r for r in results if r['check'] == 'connectivity']
        self.assertTrue(all(r['status'] == 'pass' for r in conn))


class EntryExitTests(TestCase):
    """_check_entry_exit: minimum node count check."""

    def setUp(self):
        self.validator = PipelineValidator()

    def test_empty_pipeline_fails(self):
        results = self.validator.validate({'nodes': [], 'edges': []})
        ee = [r for r in results if r['check'] == 'entry_exit'][0]
        self.assertEqual(ee['status'], 'fail')
        self.assertIn('空', ee['message'])

    def test_non_empty_pipeline_passes(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'click', 'data': {'x': 1, 'y': 2}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        ee = [r for r in results if r['check'] == 'entry_exit'][0]
        self.assertEqual(ee['status'], 'pass')
        self.assertIn('1', ee['message'])


class ValidateIntegrationTests(TestCase):
    """Full validate() integration: all check categories run together."""

    def setUp(self):
        self.validator = PipelineValidator()

    def test_empty_graph_data(self):
        """Empty dict -> no nodes -> entry_exit fail, no required_fields."""
        results = self.validator.validate({})
        self.assertIsInstance(results, list)
        ee = [r for r in results if r['check'] == 'entry_exit']
        self.assertEqual(len(ee), 1)
        self.assertEqual(ee[0]['status'], 'fail')

    def test_all_check_categories_present_for_rich_graph(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'click', 'data': {'x': 1, 'y': 2}},
                {'id': 'n2', 'type': 'template_match',
                 'data': {'template_id': 't1', 'threshold': 0.8}},
                {'id': 'n3', 'type': 'sub_pipeline', 'data': {}},
            ],
            'edges': [
                {'id': 'e1', 'source': 'n1', 'target': 'n2'},
                {'id': 'e2', 'source': 'n2', 'target': 'n3'},
            ],
        }
        results = self.validator.validate(graph)
        checks = {r['check'] for r in results}
        self.assertIn('required_fields', checks)
        self.assertIn('template_refs', checks)
        self.assertIn('pipeline_refs', checks)
        self.assertIn('connectivity', checks)
        self.assertIn('entry_exit', checks)

    def test_result_dict_has_all_fields(self):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'click', 'data': {'x': 1, 'y': 2}},
            ],
            'edges': [],
        }
        results = self.validator.validate(graph)
        for r in results:
            self.assertIn('check', r)
            self.assertIn('status', r)
            self.assertIn('message', r)
            self.assertIn('node_id', r)
            self.assertIn('suggestion', r)


"""Tests for nested schema support (node_type/config) in PipelineValidator.

N192 B4 P0: template.json uses nested schema ({node_type, config, retry, fallback}),
but validator originally only supported canvas schema ({type, position, data}).
These tests verify validator now supports both.
"""


class NestedSchemaRequiredFieldsTests(TestCase):
    """_check_required_fields should support nested schema ({node_type, config})."""

    def setUp(self):
        self.validator = PipelineValidator()

    def test_validate_nested_schema_template_match(self):
        """nested schema (node_type/config) should pass template_match required fields.

        Task 4.2 (P0-3): canonical 字段名 = template_id (snake_case).
        """
        graph_data = {
            "nodes": [
                {
                    "id": "step_1",
                    "name": "步骤1",
                    "node_type": "template_match",
                    "config": {
                        "template_id": "tpl_001",
                        "threshold": 0.8,
                    },
                }
            ],
            "edges": [],
        }
        results = self.validator.validate(graph_data)
        step1_required = [r for r in results if r["check"] == "required_fields" and r["node_id"] == "step_1"]
        assert len(step1_required) == 1
        assert step1_required[0]["status"] == "pass"

    def test_validate_nested_schema_missing_fields(self):
        """nested schema missing fields should fail with node_id.

        Task 4.2 (P0-3): template_id 和 threshold 都缺失 → 至少 1 个 fail.
        """
        graph_data = {
            "nodes": [
                {
                    "id": "step_1",
                    "node_type": "template_match",
                    "config": {},  # missing template_id and threshold
                }
            ],
            "edges": [],
        }
        results = self.validator.validate(graph_data)
        fails = [r for r in results if r["status"] == "fail"]
        assert len(fails) >= 1
        # all fails should reference step_1 (when node_id is set)
        for r in fails:
            if r.get("node_id"):
                assert r["node_id"] == "step_1"

    def test_validate_nested_schema_click_node(self):
        """nested schema click node with x/y should pass."""
        graph_data = {
            "nodes": [
                {
                    "id": "n1",
                    "node_type": "click",
                    "config": {"x": 100, "y": 200},
                }
            ],
            "edges": [],
        }
        results = self.validator.validate(graph_data)
        req = [r for r in results if r["check"] == "required_fields"][0]
        assert req["status"] == "pass"


class NestedSchemaTemplateRefsTests(TestCase):
    """_check_template_refs should read template_id from nested config.

    Task 4.2 (P0-3): canonical 字段名 = template_id (snake_case).
    """

    def setUp(self):
        self.validator = PipelineValidator()

    def test_nested_template_match_with_template_id_passes(self):
        """Task 4.2: canonical 字段 template_id 在 nested schema 中应通过 template_refs."""
        graph_data = {
            "nodes": [
                {"id": "n1", "node_type": "template_match",
                 "config": {"template_id": "tpl-1", "threshold": 0.8}},
            ],
            "edges": [],
        }
        results = self.validator.validate(graph_data)
        tpl = [r for r in results if r["check"] == "template_refs"][0]
        assert tpl["status"] == "pass"

    def test_nested_template_match_without_template_id_fails(self):
        """Task 3.3 (P2-3): templateId 留空从 warn 升级为 fail。

        原因: 用户照着模板改后若不填 templateId, backend validate 通过
        但执行时 agent 会失败 — 与 N192 B5「校验前置」原则相悖。
        """
        graph_data = {
            "nodes": [
                {"id": "n1", "node_type": "template_match",
                 "config": {"threshold": 0.8}},
            ],
            "edges": [],
        }
        results = self.validator.validate(graph_data)
        tpl = [r for r in results if r["check"] == "template_refs"][0]
        assert tpl["status"] == "fail"


class TemplateJsonIntegrationTests(TestCase):
    """resources/default/custom_tasks/template.json should pass validation.

    Task 4.2 + Task 4.3 (P0-3 + P1-8, 2026-07-28): template_id 占位符改为 null,
    让 validator 拦截未填模板的模板任务 — 这是设计本意, 用户照着模板改时
    必须填 template_id 才能通过校验。所以模板本身预期 2 个 fail:
    - required_fields: template_id=null → 缺少必填字段
    - template_refs: template_id=null → 必须配置 template_id
    其他检查 (connectivity / entry_exit) 应 pass。
    """

    def test_validate_default_template_json_runs(self):
        template_path = Path("resources/default/custom_tasks/template.json")
        if not template_path.exists():
            self.skipTest(f"template not found: {template_path}")
        template = json.loads(template_path.read_text(encoding="utf-8"))
        graph_data = {"nodes": template.get("nodes", []), "edges": []}
        validator = PipelineValidator()
        results = validator.validate(graph_data)
        fails = [r for r in results if r["status"] == "fail"]
        # Task 4.3: template_id=null 应导致 2 个 fail (required_fields + template_refs)
        assert len(fails) == 2, f"期望 2 个 fail, 实际: {fails}"
        fail_checks = {r["check"] for r in fails}
        assert fail_checks == {"required_fields", "template_refs"}
        for r in fails:
            assert "template_id" in r["message"], f"消息应含 template_id: {r['message']}"

    def test_validate_browndust_template_json_runs(self):
        template_path = Path("resources/BrownDust-II/custom_tasks/template.json")
        if not template_path.exists():
            self.skipTest(f"template not found: {template_path}")
        template = json.loads(template_path.read_text(encoding="utf-8"))
        graph_data = {"nodes": template.get("nodes", []), "edges": []}
        validator = PipelineValidator()
        results = validator.validate(graph_data)
        fails = [r for r in results if r["status"] == "fail"]
        # Task 4.3: template_id=null 应导致 2 个 fail (required_fields + template_refs)
        assert len(fails) == 2, f"期望 2 个 fail, 实际: {fails}"
        fail_checks = {r["check"] for r in fails}
        assert fail_checks == {"required_fields", "template_refs"}
        for r in fails:
            assert "template_id" in r["message"], f"消息应含 template_id: {r['message']}"


class CanvasSchemaBackwardCompatTests(TestCase):
    """Existing canvas schema ({type, position, data}) should still work."""

    def setUp(self):
        self.validator = PipelineValidator()

    def test_canvas_schema_still_passes(self):
        graph_data = {
            "nodes": [
                {"id": "n1", "type": "click", "position": {"x": 0, "y": 0},
                 "data": {"x": 1, "y": 2}},
            ],
            "edges": [],
        }
        results = self.validator.validate(graph_data)
        req = [r for r in results if r["check"] == "required_fields"][0]
        assert req["status"] == "pass"
