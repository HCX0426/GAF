# Merged from test_recording_converter.py, test_routine_converter.py - 2026-08-04

"""Tests for pipeline.recording_converter (pure logic, no DB).

convert_recording_to_pipeline transforms recording event data into a
Pipeline JSON dict with 'name', 'nodes', 'edges'.

Helper functions:
- _merge_nearby_clicks: deduplicate clicks within 5px and 1s.
- _remove_redundant_screenshots: drop consecutive screenshots.

Output keys conform to PIPELINE_GRAPH_SCHEMA:
- nodes use 'type' (not 'node_type')
- edges use 'source'/'target' (not 'from'/'to')
- 'long_press' is in ALL_NODE_TYPES
- empty events still apply name fallback (recording_data['name'] / '录制导入')
"""

# Module-level imports for the routine-converter section (merged file, 2026-08-04).
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from gamestate.models import GameProfile
from pipeline.models import TaskChain, TaskChainNode
from pipeline.recording_converter import (
    _merge_nearby_clicks,
    _remove_redundant_screenshots,
    convert_recording_to_pipeline,
)
from pipeline.services import (
    RoutineImportError,
    convert_routine_to_chain,
)


class MergeNearbyClicksTests(TestCase):
    """_merge_nearby_clicks: deduplicate clicks at same position within 1s."""

    def test_empty_events(self):
        self.assertEqual(_merge_nearby_clicks([]), [])

    def test_no_clicks_pass_through(self):
        events = [{'event_type': 'key', 'key': 'a', 'timestamp': 0}]
        result = _merge_nearby_clicks(events)
        self.assertEqual(len(result), 1)

    def test_duplicate_click_merged(self):
        """Same position, within 1s -> second click dropped."""
        events = [
            {'event_type': 'click', 'x': 100, 'y': 200, 'timestamp': 1.0},
            {'event_type': 'click', 'x': 100, 'y': 200, 'timestamp': 1.5},
        ]
        result = _merge_nearby_clicks(events)
        self.assertEqual(len(result), 1)

    def test_far_apart_clicks_kept(self):
        """Different position -> both kept."""
        events = [
            {'event_type': 'click', 'x': 100, 'y': 200, 'timestamp': 1.0},
            {'event_type': 'click', 'x': 500, 'y': 600, 'timestamp': 1.5},
        ]
        result = _merge_nearby_clicks(events)
        self.assertEqual(len(result), 2)

    def test_clicks_far_apart_in_time_kept(self):
        """Same position, >1s apart -> both kept."""
        events = [
            {'event_type': 'click', 'x': 100, 'y': 200, 'timestamp': 1.0},
            {'event_type': 'click', 'x': 100, 'y': 200, 'timestamp': 2.5},
        ]
        result = _merge_nearby_clicks(events)
        self.assertEqual(len(result), 2)

    def test_boundary_5px_merged(self):
        """dx=5, dy=5 is within threshold -> merged."""
        events = [
            {'event_type': 'click', 'x': 100, 'y': 200, 'timestamp': 1.0},
            {'event_type': 'click', 'x': 105, 'y': 205, 'timestamp': 1.5},
        ]
        result = _merge_nearby_clicks(events)
        self.assertEqual(len(result), 1)

    def test_boundary_6px_kept(self):
        """dx=6 exceeds threshold -> kept."""
        events = [
            {'event_type': 'click', 'x': 100, 'y': 200, 'timestamp': 1.0},
            {'event_type': 'click', 'x': 106, 'y': 200, 'timestamp': 1.5},
        ]
        result = _merge_nearby_clicks(events)
        self.assertEqual(len(result), 2)

    def test_non_click_between_clicks_resets_merge(self):
        """A non-click event between two clicks breaks the merge chain."""
        events = [
            {'event_type': 'click', 'x': 100, 'y': 200, 'timestamp': 1.0},
            {'event_type': 'key', 'key': 'a', 'timestamp': 1.2},
            {'event_type': 'click', 'x': 100, 'y': 200, 'timestamp': 1.5},
        ]
        result = _merge_nearby_clicks(events)
        self.assertEqual(len(result), 3)


class RemoveRedundantScreenshotsTests(TestCase):
    """_remove_redundant_screenshots: drop consecutive screenshots."""

    def test_empty(self):
        self.assertEqual(_remove_redundant_screenshots([]), [])

    def test_consecutive_screenshots_collapsed(self):
        events = [
            {'event_type': 'screenshot'},
            {'event_type': 'screenshot'},
            {'event_type': 'screenshot'},
        ]
        result = _remove_redundant_screenshots(events)
        self.assertEqual(len(result), 1)

    def test_non_consecutive_kept(self):
        events = [
            {'event_type': 'screenshot'},
            {'event_type': 'click', 'x': 1, 'y': 2},
            {'event_type': 'screenshot'},
        ]
        result = _remove_redundant_screenshots(events)
        self.assertEqual(len(result), 3)

    def test_no_screenshots_pass_through(self):
        events = [{'event_type': 'click', 'x': 1, 'y': 2}]
        result = _remove_redundant_screenshots(events)
        self.assertEqual(len(result), 1)


class ConvertClickEventsTests(TestCase):
    """Click event -> click node + auto-inserted wait node."""

    def test_single_click_produces_two_nodes(self):
        data = {'events': [{'event_type': 'click', 'x': 100, 'y': 200, 'timestamp': 0}]}
        result = convert_recording_to_pipeline(data, 'test')
        self.assertEqual(result['name'], 'test')
        # click node + auto wait node
        self.assertEqual(len(result['nodes']), 2)
        self.assertEqual(result['nodes'][0]['id'], 'click_0')
        self.assertEqual(result['nodes'][1]['id'], 'wait_1')
        # edge: click_0 -> wait_1
        self.assertEqual(len(result['edges']), 1)

    def test_click_node_data_contains_coords(self):
        data = {'events': [{'event_type': 'click', 'x': 42, 'y': 99, 'timestamp': 0}]}
        result = convert_recording_to_pipeline(data)
        click_node = result['nodes'][0]
        config = click_node['data']['config']
        self.assertEqual(config['x'], 42)
        self.assertEqual(config['y'], 99)

    def test_click_defaults_button_to_left(self):
        data = {'events': [{'event_type': 'click', 'x': 10, 'y': 20, 'timestamp': 0}]}
        result = convert_recording_to_pipeline(data)
        config = result['nodes'][0]['data']['config']
        self.assertEqual(config['button'], 'left')

    def test_two_clicks_produce_chain(self):
        data = {
            'events': [
                {'event_type': 'click', 'x': 10, 'y': 20, 'timestamp': 0},
                {'event_type': 'click', 'x': 500, 'y': 600, 'timestamp': 2.0},
            ]
        }
        result = convert_recording_to_pipeline(data)
        # click_0, wait_1, click_2, wait_3 = 4 nodes
        self.assertEqual(len(result['nodes']), 4)
        # edges: click_0->wait_1, wait_1->click_2, click_2->wait_3 = 3 edges
        self.assertEqual(len(result['edges']), 3)

    def test_click_uses_type_key(self):
        # TD-075: converter emits 'type' (matches PIPELINE_GRAPH_SCHEMA).
        data = {'events': [{'event_type': 'click', 'x': 10, 'y': 20, 'timestamp': 0}]}
        result = convert_recording_to_pipeline(data)
        self.assertIn('type', result['nodes'][0])
        self.assertNotIn('node_type', result['nodes'][0])

    def test_edges_use_source_target_keys(self):
        # TD-075: converter emits 'source'/'target' (matches schema).
        data = {'events': [{'event_type': 'click', 'x': 10, 'y': 20, 'timestamp': 0}]}
        result = convert_recording_to_pipeline(data)
        edge = result['edges'][0]
        self.assertIn('source', edge)
        self.assertIn('target', edge)
        self.assertNotIn('from', edge)
        self.assertNotIn('to', edge)


class ConvertKeyEventsTests(TestCase):
    """Key event -> key_press node."""

    def test_single_key_event(self):
        data = {'events': [{'event_type': 'key', 'key': 'Enter', 'timestamp': 0}]}
        result = convert_recording_to_pipeline(data)
        self.assertEqual(len(result['nodes']), 1)
        self.assertEqual(result['nodes'][0]['id'], 'key_0')
        self.assertEqual(result['nodes'][0]['type'], 'key_press')
        self.assertEqual(result['nodes'][0]['data']['config']['key'], 'Enter')

    def test_key_event_chains(self):
        data = {
            'events': [
                {'event_type': 'key', 'key': 'a', 'timestamp': 0},
                {'event_type': 'key', 'key': 'b', 'timestamp': 1},
            ]
        }
        result = convert_recording_to_pipeline(data)
        self.assertEqual(len(result['nodes']), 2)
        self.assertEqual(len(result['edges']), 1)


class ConvertWaitEventsTests(TestCase):
    """Wait event -> wait node (only if duration >= 0.3s)."""

    def test_wait_above_threshold(self):
        data = {'events': [{'event_type': 'wait', 'duration': 1.5}]}
        result = convert_recording_to_pipeline(data)
        self.assertEqual(len(result['nodes']), 1)
        self.assertEqual(result['nodes'][0]['type'], 'wait')

    def test_wait_below_threshold_skipped(self):
        data = {'events': [{'event_type': 'wait', 'duration': 0.2}]}
        result = convert_recording_to_pipeline(data)
        self.assertEqual(len(result['nodes']), 0)

    def test_wait_default_duration_zero_skipped(self):
        data = {'events': [{'event_type': 'wait'}]}
        result = convert_recording_to_pipeline(data)
        self.assertEqual(len(result['nodes']), 0)


class ConvertSwipeEventsTests(TestCase):
    """Swipe event -> swipe node with x1/y1/x2/y2."""

    def test_swipe_with_explicit_coords(self):
        data = {
            'events': [
                {'event_type': 'swipe', 'x1': 100, 'y1': 200,
                 'x2': 300, 'y2': 400, 'duration': 500, 'timestamp': 0},
            ]
        }
        result = convert_recording_to_pipeline(data)
        self.assertEqual(len(result['nodes']), 1)
        node = result['nodes'][0]
        self.assertEqual(node['type'], 'swipe')
        config = node['data']['config']
        self.assertEqual(config['x1'], 100)
        self.assertEqual(config['y1'], 200)
        self.assertEqual(config['x2'], 300)
        self.assertEqual(config['y2'], 400)
        self.assertEqual(config['duration'], 500)
        self.assertEqual(config['steps'], 10)

    def test_swipe_fallback_coords(self):
        """Swipe without x1/y1 falls back to x/y; without x2/y2 to end_x/end_y."""
        data = {
            'events': [
                {'event_type': 'swipe', 'x': 10, 'y': 20,
                 'end_x': 30, 'end_y': 40, 'duration_ms': 300},
            ]
        }
        result = convert_recording_to_pipeline(data)
        config = result['nodes'][0]['data']['config']
        self.assertEqual(config['x1'], 10)
        self.assertEqual(config['y1'], 20)
        self.assertEqual(config['x2'], 30)
        self.assertEqual(config['y2'], 40)


class ConvertLongPressEventsTests(TestCase):
    """Long press event -> long_press node.

    TD-076: 'long_press' is now in schema.ALL_NODE_TYPES, so converted
    pipelines pass PipelineSerializer validation.
    """

    def test_long_press_event(self):
        data = {
            'events': [
                {'event_type': 'long_press', 'x': 50, 'y': 60, 'duration': 800},
            ]
        }
        result = convert_recording_to_pipeline(data)
        self.assertEqual(len(result['nodes']), 1)
        node = result['nodes'][0]
        self.assertEqual(node['type'], 'long_press')
        config = node['data']['config']
        self.assertEqual(config['x'], 50)
        self.assertEqual(config['y'], 60)
        self.assertEqual(config['duration_ms'], 800)

    def test_long_press_fallback_duration(self):
        data = {'events': [{'event_type': 'long_press', 'x': 1, 'y': 2}]}
        result = convert_recording_to_pipeline(data)
        config = result['nodes'][0]['data']['config']
        self.assertEqual(config['duration_ms'], 1000)


class ConvertTextInputEventsTests(TestCase):
    """Text input event -> text_input node."""

    def test_text_input_event(self):
        data = {'events': [{'event_type': 'text_input', 'text': 'hello'}]}
        result = convert_recording_to_pipeline(data)
        self.assertEqual(len(result['nodes']), 1)
        node = result['nodes'][0]
        self.assertEqual(node['type'], 'text_input')
        self.assertEqual(node['data']['config']['text'], 'hello')

    def test_long_text_truncated_in_label(self):
        long_text = 'x' * 50
        data = {'events': [{'event_type': 'text_input', 'text': long_text}]}
        result = convert_recording_to_pipeline(data)
        label = result['nodes'][0]['data']['label']
        self.assertIn('…', label)
        # Full text still stored in config
        self.assertEqual(result['nodes'][0]['data']['config']['text'], long_text)


class ConvertEdgeCasesTests(TestCase):
    """Edge cases: empty data, unknown events, name fallback."""

    def test_no_events_key(self):
        result = convert_recording_to_pipeline({})
        self.assertEqual(result['nodes'], [])
        self.assertEqual(result['edges'], [])

    def test_empty_events_list(self):
        result = convert_recording_to_pipeline({'events': []})
        self.assertEqual(result['nodes'], [])
        self.assertEqual(result['edges'], [])

    def test_unknown_event_type_skipped(self):
        data = {'events': [{'event_type': 'mystery', 'x': 1}]}
        result = convert_recording_to_pipeline(data)
        self.assertEqual(len(result['nodes']), 0)

    def test_default_name_fallback(self):
        """No pipeline_name -> falls back to recording_data['name']."""
        data = {
            'events': [{'event_type': 'click', 'x': 10, 'y': 20, 'timestamp': 0}],
            'name': 'My Recording',
        }
        result = convert_recording_to_pipeline(data)
        self.assertEqual(result['name'], 'My Recording')

    def test_default_name_empty_fallback(self):
        """No name anywhere -> falls back to '录制导入'."""
        data = {
            'events': [{'event_type': 'click', 'x': 10, 'y': 20, 'timestamp': 0}],
        }
        result = convert_recording_to_pipeline(data)
        self.assertEqual(result['name'], '录制导入')

    def test_empty_events_name_applies_fallback(self):
        # TD-077: early return for empty events must still apply the
        # recording_data['name'] / '录制导入' fallback (was pipeline_name only).
        data = {'events': [], 'name': 'My Recording'}
        result = convert_recording_to_pipeline(data)
        self.assertEqual(result['name'], 'My Recording')

    def test_empty_events_name_fallback_to_default(self):
        # TD-077: no name anywhere -> '录制导入' fallback applies even for empty events.
        data = {'events': []}
        result = convert_recording_to_pipeline(data)
        self.assertEqual(result['name'], '录制导入')

    def test_screenshot_events_filtered_out(self):
        """Screenshots are not converted to nodes; consecutive ones removed."""
        data = {
            'events': [
                {'event_type': 'screenshot'},
                {'event_type': 'screenshot'},
            ]
        }
        result = convert_recording_to_pipeline(data)
        self.assertEqual(len(result['nodes']), 0)

    def test_mixed_events_produce_correct_chain(self):
        data = {
            'events': [
                {'event_type': 'click', 'x': 10, 'y': 20, 'timestamp': 0},
                {'event_type': 'key', 'key': 'a', 'timestamp': 1},
                {'event_type': 'wait', 'duration': 1.0},
            ]
        }
        result = convert_recording_to_pipeline(data)
        # click_0 + wait_1 (auto) + key_2 + wait_3
        self.assertEqual(len(result['nodes']), 4)
        # edges: click_0->wait_1, wait_1->key_2, key_2->wait_3
        self.assertEqual(len(result['edges']), 3)


"""Tests for routine.json → TaskChain converter (TD-110 Phase 3, TD-113).

Covers:
    - convert_routine_to_chain service function (TD-113: reads
      GameProfile.routine_path, not a positional arg)
    - import_routine management command (TD-113: --game-profile only,
      no positional routine_path)
    - POST /api/v2/pipeline/task-chains/import_routine/ API (TD-113:
      request body has only game_profile_id)

Tests use the real BD2 routine.json fixture (8 pipeline nodes) to ensure
the converter works against the production resource file. Pipelines must
exist in DB before conversion — the converter resolves them by name.
"""

# Pipeline names defined in the BD2 routine fixture (8 entries, in order).
BD2_PIPELINE_NAMES = [
    'daily_missions',
    'get_email',
    'sweep_daily',
    'get_pvp',
    'get_restaurant',
    'lucky_draw',
    'map_collection',
    'intensive_decomposition',
]

# Track temp fixture files for cleanup
_BD2_ROUTINE_TEMP_FILES: list[str] = []


def _create_bd2_routine_fixture() -> str:
    """Create a temp routine.json fixture with the 8 BD2 pipeline names.

    (routine.json was deleted during resource pack restructuring;
    now created as temp fixture for tests.)
    """
    tasks = []
    for i, name in enumerate(BD2_PIPELINE_NAMES):
        condition = {'on_failure': 'abort'} if i == 0 else {'on_failure': 'skip'}
        tasks.append({'pipeline': name, 'order': i + 1, 'condition': condition})
    content = {
        'name': 'BD2 Daily Routine',
        'description': 'BrownDust II daily routine',
        'tasks': tasks,
    }
    tmp_name = tempfile.mktemp(suffix='.json')
    with open(tmp_name, 'w', encoding='utf-8') as f:
        json.dump(content, f)
    _BD2_ROUTINE_TEMP_FILES.append(tmp_name)
    return tmp_name


def _cleanup_bd2_routine_fixtures() -> None:
    """Clean up all temp fixture files created by _create_bd2_routine_fixture."""
    import contextlib

    for path in _BD2_ROUTINE_TEMP_FILES:
        with contextlib.suppress(OSError):
            os.unlink(path)
    _BD2_ROUTINE_TEMP_FILES.clear()

TASK_CHAIN_URL = '/api/v2/pipeline/task-chains/'


def _login(client, username, password):
    # Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
    resp = client.post('/api/v2/accounts/auth/login/', {
        'username': username, 'password': password,
    }, format='json')
    assert resp.status_code == 200, f'Login failed: {resp.status_code} {resp.data}'
    assert isinstance(resp.data, dict), f'Login resp not dict: {resp.data}'
    if isinstance(resp.data.get('data'), dict) and 'access' in resp.data['data']:
        token = resp.data['data']['access']
    elif 'access' in resp.data:
        token = resp.data['access']
    else:
        raise AssertionError(f'Login resp missing access token: {resp.data}')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return resp


def _unwrap(resp):
    """Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封。
    优先取 resp.data['data'],降级到 resp.data 兼容裸响应。
    用 code+message+data 三键同时存在判断,避免误判业务 dict 字段名 'data'。
    """
    data = resp.data
    # unified_response 信封: {code, message, data: <实际数据>}
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _get_error_message(resp):
    """Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 错误信封。
    unified_response 用 'message' 字段, 旧裸响应用 'error' 字段。
    优先取 data['message'], 降级到 data['error'], 兼容裸响应。
    """
    data = resp.data
    # 先解 unified_response 信封 (但错误响应可能 data 是字符串/None, 不强行解)
    if isinstance(data, dict) and 'code' in data and 'message' in data:
        # unified_response 错误: {code: non-zero, message: '...', data: null/details}
        return data.get('message') or data.get('error') or ''
    # 旧裸响应: {'error': '...', ...} 或 {'detail': '...', ...}
    return data.get('message') or data.get('error') or data.get('detail') or ''


def _create_bd2_pipelines(user):
    """Create 8 Pipeline rows matching the BD2 routine.json names."""
    from pipeline.models import Pipeline
    return {
        name: Pipeline.objects.create(
            name=name,
            graph_data={'nodes': [], 'edges': []},
            user=user,
        )
        for name in BD2_PIPELINE_NAMES
    }


class ConvertRoutineToChainTests(TestCase):
    """convert_routine_to_chain service — core conversion logic."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='routine_user', password='Pass123!',
        )
        # TD-113: routine_path is now a GameProfile field
        # Create temp fixture (routine.json was deleted during resource pack restructure)
        self.profile = GameProfile.objects.create(
            game_name='BrownDust-II',
            routine_path=_create_bd2_routine_fixture(),
        )
        _create_bd2_pipelines(self.user)

    def test_convert_routine_creates_chain_with_8_pipeline_nodes(self):
        """BD2 routine.json converts to a chain with 8 PIPELINE nodes."""
        chain = convert_routine_to_chain(
            game_profile=self.profile,
            user=self.user,
        )
        self.assertEqual(chain.name, 'BD2 Daily Routine')
        self.assertEqual(chain.game_profile_id, self.profile.id)
        self.assertEqual(chain.created_by, self.user)

        nodes = list(chain.chain_nodes.order_by('order'))
        self.assertEqual(len(nodes), 8)
        for node, expected_name in zip(nodes, BD2_PIPELINE_NAMES, strict=True):
            self.assertEqual(node.node_type, TaskChainNode.NodeType.PIPELINE)
            self.assertIsNotNone(node.pipeline_id)
            self.assertEqual(node.pipeline.name, expected_name)
            self.assertIsNone(node.task_id)

        # Order field preserved from routine.json (1..8)
        self.assertEqual([n.order for n in nodes], [1, 2, 3, 4, 5, 6, 7, 8])

        # Condition propagated (first node abort on failure, rest skip)
        self.assertEqual(nodes[0].condition, {'on_failure': 'abort'})
        self.assertEqual(nodes[1].condition, {'on_failure': 'skip'})

    def test_convert_routine_pipeline_not_found_raises(self):
        """Missing Pipeline name in DB → RoutineImportError."""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8',
        ) as f:
            json.dump({
                'name': 'Broken Routine',
                'description': '',
                'tasks': [
                    {'pipeline': 'nonexistent_pipeline', 'order': 1, 'condition': {}},
                ],
            }, f)
            tmp_path = f.name

        # TD-113: point GameProfile at the temp routine file
        self.profile.routine_path = tmp_path
        self.profile.save(update_fields=['routine_path'])

        try:
            with self.assertRaises(RoutineImportError) as ctx:
                convert_routine_to_chain(
                    game_profile=self.profile,
                    user=self.user,
                )
            self.assertIn('nonexistent_pipeline', str(ctx.exception))
        finally:
            os.unlink(tmp_path)

    def test_convert_routine_sets_is_default_true(self):
        """routine.json imports are marked is_default=True (spec §2.7.5)."""
        chain = convert_routine_to_chain(
            game_profile=self.profile,
            user=self.user,
        )
        self.assertTrue(chain.is_default)

    def test_convert_routine_idempotent(self):
        """Re-importing the same routine replaces nodes, reuses chain."""
        chain1 = convert_routine_to_chain(
            game_profile=self.profile,
            user=self.user,
        )
        original_id = chain1.id
        self.assertEqual(TaskChain.objects.count(), 1)
        self.assertEqual(TaskChainNode.objects.count(), 8)

        # Mutate one node's condition to verify it gets replaced
        first_node = chain1.chain_nodes.first()
        first_node.condition = {'on_failure': 'abort', 'extra': 'stale'}
        first_node.save(update_fields=['condition'])

        # Re-import — should reuse chain1 and rebuild nodes from scratch
        chain2 = convert_routine_to_chain(
            game_profile=self.profile,
            user=self.user,
        )
        self.assertEqual(chain2.id, original_id)
        self.assertEqual(TaskChain.objects.count(), 1)
        self.assertEqual(TaskChainNode.objects.count(), 8)

        # The stale mutation must be gone — node replaced with routine data
        refreshed = TaskChainNode.objects.get(
            chain=chain2, order=first_node.order,
        )
        self.assertNotIn('extra', refreshed.condition)

    def test_convert_routine_empty_routine_path_raises(self):
        """TD-113: empty routine_path → RoutineImportError."""
        self.profile.routine_path = ''
        self.profile.save(update_fields=['routine_path'])
        with self.assertRaises(RoutineImportError) as ctx:
            convert_routine_to_chain(game_profile=self.profile, user=self.user)
        self.assertIn('no routine_path', str(ctx.exception))

    def test_convert_routine_multi_profile_different_paths(self):
        """TD-113: two GameProfiles can point at different routine.json files.

        Creates a second GameProfile with a temp routine.json (different
        name + single task) and verifies both coexist without collision.
        """
        # Create a second routine file with a different chain name
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8',
        ) as f:
            json.dump({
                'name': 'Alt Routine',
                'description': 'alt profile routine',
                'tasks': [
                    {'pipeline': 'daily_missions', 'order': 1, 'condition': {}},
                ],
            }, f)
            alt_path = f.name
        try:
            alt_profile = GameProfile.objects.create(
                game_name='AltGame',
                routine_path=alt_path,
            )
            chain1 = convert_routine_to_chain(
                game_profile=self.profile, user=self.user,
            )
            chain2 = convert_routine_to_chain(
                game_profile=alt_profile, user=self.user,
            )
            self.assertNotEqual(chain1.id, chain2.id)
            self.assertEqual(chain1.name, 'BD2 Daily Routine')
            self.assertEqual(chain2.name, 'Alt Routine')
            self.assertEqual(chain1.chain_nodes.count(), 8)
            self.assertEqual(chain2.chain_nodes.count(), 1)
        finally:
            os.unlink(alt_path)


class ConvertRoutineErrorPathTests(TestCase):
    """convert_routine_to_chain error handling — malformed inputs."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='err_user', password='Pass123!',
        )
        self.profile = GameProfile.objects.create(
            game_name='ErrGame',
            routine_path='/no/such/routine.json',  # will be overridden per test
        )

    def test_missing_routine_file_raises(self):
        """Non-existent routine_path → RoutineImportError."""
        self.profile.routine_path = '/no/such/routine.json'
        self.profile.save(update_fields=['routine_path'])
        with self.assertRaises(RoutineImportError) as ctx:
            convert_routine_to_chain(
                game_profile=self.profile,
                user=self.user,
            )
        self.assertIn('not found', str(ctx.exception))

    def test_invalid_json_raises(self):
        """Malformed JSON → RoutineImportError."""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8',
        ) as f:
            f.write('{ not valid json')
            tmp_path = f.name
        self.profile.routine_path = tmp_path
        self.profile.save(update_fields=['routine_path'])
        try:
            with self.assertRaises(RoutineImportError) as ctx:
                convert_routine_to_chain(
                    game_profile=self.profile,
                    user=self.user,
                )
            self.assertIn('invalid JSON', str(ctx.exception))
        finally:
            os.unlink(tmp_path)

    def test_ambiguous_pipeline_name_raises(self):
        """Two Pipelines with same name → RoutineImportError (refuse to guess)."""
        from pipeline.models import Pipeline
        Pipeline.objects.create(
            name='dup', graph_data={'nodes': [], 'edges': []}, user=self.user,
        )
        Pipeline.objects.create(
            name='dup', graph_data={'nodes': [], 'edges': []}, user=self.user,
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8',
        ) as f:
            json.dump({
                'name': 'Ambiguous Routine',
                'tasks': [
                    {'pipeline': 'dup', 'order': 1, 'condition': {}},
                ],
            }, f)
            tmp_path = f.name
        self.profile.routine_path = tmp_path
        self.profile.save(update_fields=['routine_path'])
        try:
            with self.assertRaises(RoutineImportError) as ctx:
                convert_routine_to_chain(
                    game_profile=self.profile,
                    user=self.user,
                )
            self.assertIn('matches 2', str(ctx.exception))
        finally:
            os.unlink(tmp_path)


class ImportRoutineManagementCommandTests(TestCase):
    """`manage.py import_routine` — Django management command (TD-113)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='cmd_user', password='Pass123!',
        )
        self.profile = GameProfile.objects.create(
            game_name='CmdGame',
            routine_path=_create_bd2_routine_fixture(),
        )
        _create_bd2_pipelines(self.user)

    def test_management_command_creates_chain(self):
        """Command imports BD2 routine.json → 8-node TaskChain."""
        out = StringIO()
        call_command(
            'import_routine',
            '--game-profile', str(self.profile.id),
            '--user', self.user.username,
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn('Successfully imported routine', output)
        self.assertIn('BD2 Daily Routine', output)
        self.assertIn('nodes=8', output)

        chain = TaskChain.objects.get(name='BD2 Daily Routine')
        self.assertEqual(chain.chain_nodes.count(), 8)
        self.assertTrue(chain.is_default)
        self.assertEqual(chain.created_by, self.user)

    def test_management_command_unknown_user_raises(self):
        """Unknown username → CommandError."""
        from django.core.management import CommandError
        with self.assertRaises(CommandError) as ctx:
            call_command(
                'import_routine',
                '--game-profile', str(self.profile.id),
                '--user', 'no_such_user',
            )
        self.assertIn('not found', str(ctx.exception))

    def test_management_command_missing_pipeline_raises(self):
        """If DB has no matching Pipelines → CommandError."""
        from pipeline.models import Pipeline
        Pipeline.objects.all().delete()
        from django.core.management import CommandError
        with self.assertRaises(CommandError):
            call_command(
                'import_routine',
                '--game-profile', str(self.profile.id),
            )

    def test_management_command_empty_routine_path_raises(self):
        """TD-113: GameProfile with empty routine_path → CommandError."""
        from django.core.management import CommandError
        self.profile.routine_path = ''
        self.profile.save(update_fields=['routine_path'])
        with self.assertRaises(CommandError) as ctx:
            call_command(
                'import_routine',
                '--game-profile', str(self.profile.id),
            )
        self.assertIn('no routine_path', str(ctx.exception))


class ImportRoutineAPITests(TestCase):
    """POST /api/v2/pipeline/task-chains/import_routine/ — REST API (TD-113)."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='api_admin', password='AdminPass123!',
            role=User.Role.ADMIN,
        )
        self.profile = GameProfile.objects.create(
            game_name='ApiGame',
            routine_path=_create_bd2_routine_fixture(),
        )
        _create_bd2_pipelines(self.admin)
        _login(self.client, 'api_admin', 'AdminPass123!')

    def test_api_import_routine_creates_chain(self):
        """API POST creates a TaskChain with 8 PIPELINE nodes."""
        resp = self.client.post(
            f'{TASK_CHAIN_URL}import_routine/',
            {'game_profile_id': self.profile.id},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        unwrapped = _unwrap(resp)
        self.assertEqual(unwrapped['name'], 'BD2 Daily Routine')
        self.assertTrue(unwrapped['is_default'])

        chain = TaskChain.objects.get(pk=unwrapped['id'])
        self.assertEqual(chain.chain_nodes.count(), 8)
        self.assertEqual(chain.game_profile_id, self.profile.id)

    def test_api_import_routine_missing_profile_returns_400(self):
        """Missing game_profile_id → 400."""
        resp = self.client.post(
            f'{TASK_CHAIN_URL}import_routine/',
            {},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封 (message 替代 error)
        self.assertIn('game_profile_id', _get_error_message(resp))

    def test_api_import_routine_empty_path_returns_400(self):
        """TD-113: GameProfile with empty routine_path → 400."""
        self.profile.routine_path = ''
        self.profile.save(update_fields=['routine_path'])
        resp = self.client.post(
            f'{TASK_CHAIN_URL}import_routine/',
            {'game_profile_id': self.profile.id},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封 (message 替代 error)
        self.assertIn('no routine_path', _get_error_message(resp))

    def test_api_import_routine_nonexistent_profile_returns_404(self):
        """TD-113: unknown game_profile_id → 404 (get_object_or_404)."""
        resp = self.client.post(
            f'{TASK_CHAIN_URL}import_routine/',
            {'game_profile_id': 999999},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
