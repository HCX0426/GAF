"""Tests for pipeline.views (API layer).

Covers: Pipeline CRUD, snapshots, restore, validate, estimate-time,
TaskChain CRUD, Recording CRUD + convert-to-pipeline, ChainNode operations.

URL prefix: /api/v2/pipeline/
Global pagination is ON (PageNumberPagination, PAGE_SIZE=20), so list
responses are dicts with 'count', 'next', 'previous', 'results'.
"""

from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from gaf_core.utils.tokens import hash_token
from rest_framework import status
from rest_framework.test import APIClient
from workers.models import Worker

from accounts.models import User
from pipeline.models import (
    Pipeline,
    PipelineSnapshot,
    Recording,
    TaskChain,
    TaskChainNode,
)
from tasks.models import Task, TaskExecution

# A valid graph_data that passes PIPELINE_GRAPH_SCHEMA validation.
VALID_GRAPH = {
    'nodes': [
        {'id': 'n1', 'type': 'click', 'position': {'x': 0, 'y': 0},
         'data': {'x': 100, 'y': 200}},
    ],
    'edges': [],
}

VALID_GRAPH_2 = {
    'nodes': [
        {'id': 'n1', 'type': 'click', 'position': {'x': 0, 'y': 0},
         'data': {'x': 10, 'y': 20}},
        {'id': 'n2', 'type': 'swipe', 'position': {'x': 100, 'y': 100},
         'data': {'x1': 1, 'y1': 2, 'x2': 3, 'y2': 4}},
    ],
    'edges': [
        {'id': 'e1', 'source': 'n1', 'target': 'n2'},
    ],
}

PIPELINE_URL = '/api/v2/pipeline/pipelines/'
TASK_CHAIN_URL = '/api/v2/pipeline/task-chains/'
RECORDING_URL = '/api/v2/pipeline/recordings/'
CHAIN_NODES_URL = '/api/v2/pipeline/chain-nodes/'


def _login(client, username, password):
    """Login and set Bearer token on client. Returns the response.

    Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径。
    unified_response 信封返回 `{code, data: {access, ...}, message}`,
    但旧代码直接取 `resp.data['access']` 顶层,导致 30+ 测试在 setUp 失败。
    现优先取 `resp.data['data']['access']`,降级到 `resp.data['access']` 兼容裸响应。
    """
    resp = client.post('/api/v2/accounts/auth/login/', {
        'username': username, 'password': password,
    }, format='json')
    assert resp.status_code == 200, f'Login failed: {resp.status_code} {resp.data}'
    assert isinstance(resp.data, dict), f'Login resp not dict: {resp.data}'
    # 优先 unified_response 信封 (data.access),降级到裸响应 (access)
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
    支持 data 字段为 dict (单对象/分页) 或 list (无分页列表)。
    用 code+message+data 三键同时存在判断,避免误判业务 dict 字段名 'data'。
    """
    data = resp.data
    # unified_response 信封: {code, message, data: <实际数据>}
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _get_results(resp):
    """Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封 + 分页。
    先解信封, 再取分页 results 字段。
    """
    data = _unwrap(resp)
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


class PipelineCRUDTests(TestCase):
    """Pipeline ViewSet CRUD: list, create, retrieve, update, destroy."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='pipe_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_user(
            username='pipe_op', password='OpPass123!', role=User.Role.OPERATOR,
        )
        _login(self.client, 'pipe_admin', 'AdminPass123!')

    def test_list_empty(self):
        resp = self.client.get(PIPELINE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_get_results(resp)), 0)

    def test_create_pipeline(self):
        resp = self.client.post(PIPELINE_URL, {
            'name': 'API Pipeline',
            'description': 'via API',
            'graph_data': VALID_GRAPH,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        unwrapped = _unwrap(resp)
        self.assertEqual(unwrapped['name'], 'API Pipeline')
        self.assertEqual(unwrapped['version'], 1)
        self.assertEqual(unwrapped['user'], self.admin.id)

    def test_create_pipeline_sets_user_automatically(self):
        """perform_create binds current user; 'user' is read-only."""
        resp = self.client.post(PIPELINE_URL, {
            'name': 'Auto User',
            'graph_data': VALID_GRAPH,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        pipe = Pipeline.objects.get(pk=_unwrap(resp)['id'])
        self.assertEqual(pipe.user, self.admin)

    def test_retrieve_pipeline(self):
        pipe = Pipeline.objects.create(
            name='Retrieve Me', user=self.admin, graph_data=VALID_GRAPH,
        )
        resp = self.client.get(f'{PIPELINE_URL}{pipe.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        unwrapped = _unwrap(resp)
        self.assertEqual(unwrapped['name'], 'Retrieve Me')
        self.assertIn('graph_data', unwrapped)

    def test_list_uses_list_serializer(self):
        """List serializer omits graph_data."""
        Pipeline.objects.create(name='List Item', user=self.admin, graph_data=VALID_GRAPH)
        resp = self.client.get(PIPELINE_URL)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertNotIn('graph_data', results[0])
        self.assertIn('name', results[0])

    def test_update_pipeline_increments_version(self):
        pipe = Pipeline.objects.create(
            name='Update Me', user=self.admin, graph_data=VALID_GRAPH, version=1,
        )
        resp = self.client.put(f'{PIPELINE_URL}{pipe.id}/', {
            'name': 'Updated',
            'description': 'updated desc',
            'graph_data': VALID_GRAPH_2,
            'is_template': False,
            'estimated_duration_ms': 0,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        self.assertEqual(_unwrap(resp)['version'], 2)
        pipe.refresh_from_db()
        self.assertEqual(pipe.version, 2)
        self.assertEqual(pipe.name, 'Updated')

    def test_update_creates_snapshot(self):
        pipe = Pipeline.objects.create(
            name='Snap Test', user=self.admin, graph_data=VALID_GRAPH, version=1,
        )
        self.client.put(f'{PIPELINE_URL}{pipe.id}/', {
            'name': 'Snap Test',
            'description': '',
            'graph_data': VALID_GRAPH_2,
            'is_template': False,
            'estimated_duration_ms': 0,
        }, format='json')
        self.assertEqual(pipe.snapshots.count(), 1)
        snap = pipe.snapshots.first()
        self.assertEqual(snap.version, 1)
        self.assertIn('节点数', snap.change_summary)

    def test_partial_update_pipeline(self):
        pipe = Pipeline.objects.create(
            name='Patch Me', user=self.admin, graph_data=VALID_GRAPH,
        )
        resp = self.client.patch(f'{PIPELINE_URL}{pipe.id}/', {
            'name': 'Patched Name',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pipe.refresh_from_db()
        self.assertEqual(pipe.name, 'Patched Name')

    def test_destroy_pipeline(self):
        pipe = Pipeline.objects.create(
            name='Delete Me', user=self.admin, graph_data=VALID_GRAPH,
        )
        resp = self.client.delete(f'{PIPELINE_URL}{pipe.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Pipeline.objects.filter(id=pipe.id).exists())

    def test_search_filter(self):
        Pipeline.objects.create(name='Alpha', user=self.admin, graph_data=VALID_GRAPH)
        Pipeline.objects.create(name='Beta', user=self.admin, graph_data=VALID_GRAPH)
        resp = self.client.get(f'{PIPELINE_URL}?search=Alpha')
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Alpha')

    def test_is_template_filter(self):
        Pipeline.objects.create(name='T1', user=self.admin, graph_data=VALID_GRAPH, is_template=True)
        Pipeline.objects.create(name='T2', user=self.admin, graph_data=VALID_GRAPH, is_template=False)
        resp = self.client.get(f'{PIPELINE_URL}?is_template=true')
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'T1')

    def test_invalid_graph_data_rejected(self):
        """graph_data missing required schema fields -> 400."""
        resp = self.client.post(PIPELINE_URL, {
            'name': 'Bad Graph',
            'graph_data': {'nodes': [{'id': 'n1'}]},  # missing type, position, data
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class PipelineSnapshotActionTests(TestCase):
    """Pipeline snapshots/, snapshots/{version}/, restore/{version}/ actions."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='snap_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'snap_admin', 'AdminPass123!')
        self.pipe = Pipeline.objects.create(
            name='Snap Pipe', user=self.admin, graph_data=VALID_GRAPH, version=1,
        )
        PipelineSnapshot.objects.create(
            pipeline=self.pipe, version=1, graph_data=VALID_GRAPH, change_summary='v1',
        )

    def test_list_snapshots(self):
        resp = self.client.get(f'{PIPELINE_URL}{self.pipe.id}/snapshots/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 7.3 (N192 B1): unified_response 信封后, list 在 resp.data['data'].
        snapshots = _unwrap(resp)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]['version'], 1)

    def test_get_snapshot_detail(self):
        resp = self.client.get(f'{PIPELINE_URL}{self.pipe.id}/snapshots/1/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        unwrapped = _unwrap(resp)
        self.assertEqual(unwrapped['version'], 1)
        self.assertEqual(unwrapped['change_summary'], 'v1')

    def test_get_snapshot_not_found(self):
        resp = self.client.get(f'{PIPELINE_URL}{self.pipe.id}/snapshots/999/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_restore_pipeline(self):
        """Restore creates a new snapshot and increments version."""
        original_version = self.pipe.version
        resp = self.client.post(f'{PIPELINE_URL}{self.pipe.id}/restore/1/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.pipe.refresh_from_db()
        self.assertEqual(self.pipe.version, original_version + 1)
        # A new snapshot was created for the pre-restore state
        self.assertEqual(self.pipe.snapshots.count(), 2)

    def test_restore_not_found(self):
        resp = self.client.post(f'{PIPELINE_URL}{self.pipe.id}/restore/999/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class PipelineValidateEstimateTests(TestCase):
    """PipelineValidateView and PipelineEstimateTimeView (APIView POST).

    ✅ FIXED (TD-074, commit 0c435e39): explicit path() entries for
    'pipelines/validate/' and 'pipelines/estimate-time/' are declared
    BEFORE include(router.urls) in urls.py, so they match first and
    bypass DefaultRouter's pipelines/<pk>/ detail route. 4 tests pass.
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='val_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'val_admin', 'AdminPass123!')

    def test_validate_endpoint(self):
        resp = self.client.post(f'{PIPELINE_URL}validate/', {
            'graph_data': VALID_GRAPH,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        unwrapped = _unwrap(resp)
        self.assertIn('results', unwrapped)
        self.assertIsInstance(unwrapped['results'], list)
        self.assertGreater(len(unwrapped['results']), 0)

    def test_validate_empty_graph(self):
        resp = self.client.post(f'{PIPELINE_URL}validate/', {
            'graph_data': {'nodes': [], 'edges': []},
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        ee = [r for r in _unwrap(resp)['results'] if r['check'] == 'entry_exit']
        self.assertEqual(ee[0]['status'], 'fail')

    def test_estimate_time_endpoint(self):
        resp = self.client.post(f'{PIPELINE_URL}estimate-time/', {
            'graph_data': VALID_GRAPH,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        unwrapped = _unwrap(resp)
        self.assertIn('total_ms', unwrapped)
        self.assertIn('breakdown', unwrapped)

    def test_estimate_time_empty_graph(self):
        resp = self.client.post(f'{PIPELINE_URL}estimate-time/', {
            'graph_data': {},
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        self.assertEqual(_unwrap(resp)['total_ms'], 0)


class PipelinePermissionTests(TestCase):
    """Role-based permissions: viewer read-only, operator can write, admin full."""

    def setUp(self):
        self.client = APIClient()
        self.viewer = User.objects.create_user(
            username='pipe_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        self.operator = User.objects.create_user(
            username='pipe_op2', password='OpPass123!', role=User.Role.OPERATOR,
        )
        self.admin = User.objects.create_user(
            username='pipe_admin2', password='AdminPass123!', role=User.Role.ADMIN,
        )

    def test_viewer_can_list_pipelines(self):
        _login(self.client, 'pipe_viewer', 'ViewerPass123!')
        resp = self.client.get(PIPELINE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_viewer_can_retrieve_pipeline(self):
        # Viewer can only retrieve their own pipelines (queryset filters by user).
        pipe = Pipeline.objects.create(
            name='Viewer Own', user=self.viewer, graph_data=VALID_GRAPH,
        )
        _login(self.client, 'pipe_viewer', 'ViewerPass123!')
        resp = self.client.get(f'{PIPELINE_URL}{pipe.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_pipeline(self):
        _login(self.client, 'pipe_viewer', 'ViewerPass123!')
        resp = self.client.post(PIPELINE_URL, {
            'name': 'Denied', 'graph_data': VALID_GRAPH,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_update_pipeline(self):
        pipe = Pipeline.objects.create(
            name='Viewer Update', user=self.admin, graph_data=VALID_GRAPH,
        )
        _login(self.client, 'pipe_viewer', 'ViewerPass123!')
        resp = self.client.patch(f'{PIPELINE_URL}{pipe.id}/', {'name': 'Hacked'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_destroy_pipeline(self):
        pipe = Pipeline.objects.create(
            name='Viewer Delete', user=self.admin, graph_data=VALID_GRAPH,
        )
        _login(self.client, 'pipe_viewer', 'ViewerPass123!')
        resp = self.client.delete(f'{PIPELINE_URL}{pipe.id}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_restore_pipeline(self):
        pipe = Pipeline.objects.create(
            name='Viewer Restore', user=self.admin, graph_data=VALID_GRAPH,
        )
        PipelineSnapshot.objects.create(
            pipeline=pipe, version=1, graph_data=VALID_GRAPH,
        )
        _login(self.client, 'pipe_viewer', 'ViewerPass123!')
        resp = self.client.post(f'{PIPELINE_URL}{pipe.id}/restore/1/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_operator_can_create_pipeline(self):
        _login(self.client, 'pipe_op2', 'OpPass123!')
        resp = self.client.post(PIPELINE_URL, {
            'name': 'Op Created', 'graph_data': VALID_GRAPH,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_operator_can_update_pipeline(self):
        pipe = Pipeline.objects.create(
            name='Op Update', user=self.operator, graph_data=VALID_GRAPH,
        )
        _login(self.client, 'pipe_op2', 'OpPass123!')
        resp = self.client.patch(f'{PIPELINE_URL}{pipe.id}/', {'name': 'Op Updated'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_operator_can_destroy_own_pipeline(self):
        pipe = Pipeline.objects.create(
            name='Op Delete', user=self.operator, graph_data=VALID_GRAPH,
        )
        _login(self.client, 'pipe_op2', 'OpPass123!')
        resp = self.client.delete(f'{PIPELINE_URL}{pipe.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_admin_sees_all_pipelines(self):
        Pipeline.objects.create(name='Admin Sees', user=self.operator, graph_data=VALID_GRAPH)
        _login(self.client, 'pipe_admin2', 'AdminPass123!')
        resp = self.client.get(PIPELINE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(_get_results(resp)), 1)

    def test_operator_only_sees_own_pipelines(self):
        Pipeline.objects.create(name='Op Pipe', user=self.operator, graph_data=VALID_GRAPH)
        Pipeline.objects.create(name='Admin Pipe', user=self.admin, graph_data=VALID_GRAPH)
        _login(self.client, 'pipe_op2', 'OpPass123!')
        resp = self.client.get(PIPELINE_URL)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Op Pipe')

    def test_unauthenticated_denied(self):
        resp = self.client.get(PIPELINE_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class PipelineExecuteTests(TestCase):
    """Pipeline execute action: requires online agent, creates TaskExecution."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='exec_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'exec_admin', 'AdminPass123!')
        self.pipe = Pipeline.objects.create(
            name='Exec Pipe', user=self.admin, graph_data=VALID_GRAPH,
        )
        self.agent = Worker.objects.create(
            agent_id='exec-agent-001', hostname='exec-host', status=Worker.Status.IDLE,
        )

    @mock.patch('tasks.tasks.dispatch_task')
    def test_execute_success(self, mock_dispatch):
        resp = self.client.post(f'{PIPELINE_URL}{self.pipe.id}/execute/', {
            'agent_id': 'exec-agent-001',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # spec-2026-08-02-backend-execution-unification: 响应改为 dispatch_task 格式
        # UnifiedResponseMiddleware 包装为 {code, message, data}，业务数据在 data 内层
        inner = resp.data['data']
        self.assertEqual(inner['status'], 'dispatched')
        self.assertIn('execution_id', inner)
        self.assertIn('pipeline_id', inner)
        self.assertIn('agent_id', inner)
        mock_dispatch.delay.assert_called_once()
        # TaskExecution was created
        execution = TaskExecution.objects.get(pk=inner['execution_id'])
        self.assertEqual(execution.pipeline, self.pipe)
        self.assertEqual(execution.status, TaskExecution.Status.PENDING)

    def test_execute_no_online_agent(self):
        Worker.objects.filter(agent_id='exec-agent-001').update(status=Worker.Status.OFFLINE)
        resp = self.client.post(f'{PIPELINE_URL}{self.pipe.id}/execute/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('tasks.tasks.dispatch_task.delay', side_effect=Exception('dispatch failed'))
    def test_execute_dispatch_failure_returns_500(self, mock_delay):
        """dispatch_task.delay 失败时 view 返回 500，execution 仍为 PENDING。"""
        resp = self.client.post(f'{PIPELINE_URL}{self.pipe.id}/execute/', {
            'agent_id': 'exec-agent-001',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        # Execution was created before the dispatch call, so it's still PENDING
        execution = TaskExecution.objects.filter(pipeline=self.pipe).first()
        self.assertIsNotNone(execution)
        self.assertEqual(execution.status, TaskExecution.Status.PENDING)

    def test_viewer_cannot_execute(self):
        User.objects.create_user(
            username='exec_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        _login(self.client, 'exec_viewer', 'ViewerPass123!')
        resp = self.client.post(f'{PIPELINE_URL}{self.pipe.id}/execute/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TaskChainCRUDTests(TestCase):
    """TaskChain ViewSet CRUD.

    TD-078: TaskChainViewSet now overrides get_permissions so viewer can read
    (list/retrieve) while operator+ is required for writes. This is consistent
    with PipelineViewSet and RecordingViewSet.
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='chain_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_user(
            username='chain_op', password='OpPass123!', role=User.Role.OPERATOR,
        )
        _login(self.client, 'chain_admin', 'AdminPass123!')

    def test_create_task_chain(self):
        resp = self.client.post(TASK_CHAIN_URL, {
            'name': 'API Chain',
            'description': 'via API',
            'dag_data': {},
            'is_enabled': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        unwrapped = _unwrap(resp)
        self.assertEqual(unwrapped['name'], 'API Chain')
        self.assertEqual(unwrapped['created_by'], self.admin.id)

    def test_list_task_chains(self):
        TaskChain.objects.create(name='Chain 1', created_by=self.admin)
        TaskChain.objects.create(name='Chain 2', created_by=self.admin)
        resp = self.client.get(TASK_CHAIN_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_get_results(resp)), 2)

    def test_retrieve_task_chain(self):
        chain = TaskChain.objects.create(name='Retrieve Chain', created_by=self.admin)
        resp = self.client.get(f'{TASK_CHAIN_URL}{chain.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        self.assertEqual(_unwrap(resp)['name'], 'Retrieve Chain')

    def test_update_task_chain(self):
        chain = TaskChain.objects.create(name='Update Chain', created_by=self.admin)
        resp = self.client.patch(f'{TASK_CHAIN_URL}{chain.id}/', {
            'name': 'Updated Chain',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        chain.refresh_from_db()
        self.assertEqual(chain.name, 'Updated Chain')

    def test_destroy_task_chain(self):
        chain = TaskChain.objects.create(name='Delete Chain', created_by=self.admin)
        resp = self.client.delete(f'{TASK_CHAIN_URL}{chain.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TaskChain.objects.filter(id=chain.id).exists())

    def test_admin_sees_all_chains(self):
        TaskChain.objects.create(name='Op Chain', created_by=self.operator)
        resp = self.client.get(TASK_CHAIN_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(_get_results(resp)), 1)

    def test_operator_only_sees_own_chains(self):
        TaskChain.objects.create(name='Op Chain', created_by=self.operator)
        TaskChain.objects.create(name='Admin Chain', created_by=self.admin)
        _login(self.client, 'chain_op', 'OpPass123!')
        resp = self.client.get(TASK_CHAIN_URL)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Op Chain')

    def test_viewer_can_list_task_chains(self):
        # TD-078: viewer can now read (list/retrieve) task chains, consistent
        # with PipelineViewSet and RecordingViewSet (was 403 when all actions
        # required 'execute').
        User.objects.create_user(
            username='chain_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        _login(self.client, 'chain_viewer', 'ViewerPass123!')
        resp = self.client.get(TASK_CHAIN_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_task_chain(self):
        # TD-078: viewer still cannot write (create/update/destroy requires 'execute').
        User.objects.create_user(
            username='chain_viewer2', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        _login(self.client, 'chain_viewer2', 'ViewerPass123!')
        resp = self.client.post(TASK_CHAIN_URL, {
            'name': 'Viewer Chain',
            'dag_data': {},
            'is_enabled': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_node_count_in_response(self):
        chain = TaskChain.objects.create(name='Count Chain', created_by=self.admin)
        task = Task.objects.create(name='Count Task')
        TaskChainNode.objects.create(chain=chain, task=task, order=1)
        TaskChainNode.objects.create(chain=chain, task=task, order=2)
        resp = self.client.get(f'{TASK_CHAIN_URL}{chain.id}/')
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        self.assertEqual(_unwrap(resp)['node_count'], 2)


class RecordingCRUDTests(TestCase):
    """Recording ViewSet CRUD + permissions."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='rec_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_user(
            username='rec_op', password='OpPass123!', role=User.Role.OPERATOR,
        )
        self.viewer = User.objects.create_user(
            username='rec_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        _login(self.client, 'rec_admin', 'AdminPass123!')

    def test_create_recording(self):
        resp = self.client.post(RECORDING_URL, {
            'name': 'API Recording',
            'recording_data': {'events': []},
            'duration': 10.5,
            'screenshot_count': 5,
            'resolution': '1920x1080',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        self.assertEqual(_unwrap(resp)['name'], 'API Recording')

    def test_list_recordings(self):
        Recording.objects.create(name='Rec 1', user=self.admin)
        Recording.objects.create(name='Rec 2', user=self.admin)
        resp = self.client.get(RECORDING_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_get_results(resp)), 2)

    def test_retrieve_recording(self):
        rec = Recording.objects.create(name='Retrieve Rec', user=self.admin)
        resp = self.client.get(f'{RECORDING_URL}{rec.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        self.assertEqual(_unwrap(resp)['name'], 'Retrieve Rec')

    def test_update_recording(self):
        rec = Recording.objects.create(name='Update Rec', user=self.admin)
        resp = self.client.patch(f'{RECORDING_URL}{rec.id}/', {
            'name': 'Updated Rec',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rec.refresh_from_db()
        self.assertEqual(rec.name, 'Updated Rec')

    def test_destroy_recording(self):
        rec = Recording.objects.create(name='Delete Rec', user=self.admin)
        resp = self.client.delete(f'{RECORDING_URL}{rec.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Recording.objects.filter(id=rec.id).exists())

    def test_user_only_sees_own_recordings(self):
        """Recording queryset filters by current user (not admin-override)."""
        Recording.objects.create(name='Admin Rec', user=self.admin)
        Recording.objects.create(name='Op Rec', user=self.operator)
        _login(self.client, 'rec_op', 'OpPass123!')
        resp = self.client.get(RECORDING_URL)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Op Rec')

    def test_viewer_can_list_recordings(self):
        Recording.objects.create(name='Viewer Rec', user=self.viewer)
        _login(self.client, 'rec_viewer', 'ViewerPass123!')
        resp = self.client.get(RECORDING_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_recording(self):
        _login(self.client, 'rec_viewer', 'ViewerPass123!')
        resp = self.client.post(RECORDING_URL, {'name': 'Denied'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_uses_list_serializer(self):
        """List serializer includes event_count, omits recording_data."""
        Recording.objects.create(
            name='List Rec', user=self.admin,
            recording_data={'events': [{'event_type': 'click'}, {'event_type': 'key'}]},
        )
        resp = self.client.get(RECORDING_URL)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertNotIn('recording_data', results[0])
        self.assertEqual(results[0]['event_count'], 2)


class RecordingScreenshotTests(TestCase):
    """Recording screenshot upload/serve (s45: real screenshot closure)."""

    def setUp(self):
        import tempfile

        from django.conf import settings
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='shot_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        self.other = User.objects.create_user(
            username='shot_other', password='OtherPass123!', role=User.Role.VIEWER,
        )
        self._media_root = settings.MEDIA_ROOT
        self._tmp_media = tempfile.mkdtemp()
        settings.MEDIA_ROOT = self._tmp_media
        self.recording = Recording.objects.create(
            name='Shot Rec', user=self.admin,
            recording_data={'events': [
                {'event_type': 'click', 'timestamp': 0.0, 'screenshot_path': 'local.png'},
                {'event_type': 'screenshot', 'timestamp': 1.0, 'screenshot_path': 'local.png'},
            ]},
        )
        self.agent = Worker.objects.create(
            agent_id='shot-agent-001', hostname='shot-agent',
            agent_token_hash=hash_token('shot-agent-token-1234'),
        )
        self.png = b'\x89PNG\r\n\x1a\n' + b'x' * 64

    def tearDown(self):
        import shutil

        from django.conf import settings
        settings.MEDIA_ROOT = self._media_root
        shutil.rmtree(self._tmp_media, ignore_errors=True)

    def _upload(self, event_index=1):
        return self.client.post(
            f'{RECORDING_URL}{self.recording.pk}/screenshots/',
            {'event_index': str(event_index), 'file': SimpleUploadedFile('shot.png', self.png)},
            format='multipart',
        )

    def test_upload_by_owner(self):
        _login(self.client, 'shot_admin', 'AdminPass123!')
        resp = self._upload()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = _unwrap(resp)
        self.assertIn(f'/media/screenshots/recordings/{self.recording.pk}/1.png', body['url'])
        self.recording.refresh_from_db()
        self.assertEqual(
            self.recording.recording_data['events'][1]['screenshot_url'],
            f'/media/screenshots/recordings/{self.recording.pk}/1.png',
        )

    def test_upload_by_agent_token(self):
        resp = self.client.post(
            f'{RECORDING_URL}{self.recording.pk}/screenshots/',
            {'event_index': '1', 'file': SimpleUploadedFile('shot.png', self.png)},
            format='multipart',
            HTTP_AUTHORIZATION='Token shot-agent-token-1234',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_upload_unauthorized(self):
        resp = self._upload()
        # DRF: no successful authenticator -> 401 (WWW-Authenticate challenge)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_upload_non_owner_forbidden(self):
        _login(self.client, 'shot_other', 'OtherPass123!')
        resp = self._upload()
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_upload_bad_event_index(self):
        _login(self.client, 'shot_admin', 'AdminPass123!')
        resp = self._upload(event_index=99)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_missing_file(self):
        _login(self.client, 'shot_admin', 'AdminPass123!')
        resp = self.client.post(
            f'{RECORDING_URL}{self.recording.pk}/screenshots/',
            {'event_index': '1'}, format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_download_by_owner(self):
        _login(self.client, 'shot_admin', 'AdminPass123!')
        self._upload()
        resp = self.client.get(f'{RECORDING_URL}{self.recording.pk}/screenshots/1.png/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'image/png')
        body = b''.join(resp.streaming_content)
        self.assertTrue(body.startswith(b'\x89PNG'))

    def test_download_non_owner_not_found(self):
        _login(self.client, 'shot_other', 'OtherPass123!')
        _login(self.client, 'shot_admin', 'AdminPass123!')
        self._upload()
        _login(self.client, 'shot_other', 'OtherPass123!')
        resp = self.client.get(f'{RECORDING_URL}{self.recording.pk}/screenshots/1.png')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_download_missing_file(self):
        _login(self.client, 'shot_admin', 'AdminPass123!')
        resp = self.client.get(f'{RECORDING_URL}{self.recording.pk}/screenshots/9.png')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class RecordingConvertTests(TestCase):
    """Recording convert-to-pipeline action."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='conv_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'conv_admin', 'AdminPass123!')

    def test_convert_with_existing_pipeline_json(self):
        """If pipeline_json already has nodes, use it directly."""
        rec = Recording.objects.create(
            name='Has Pipeline', user=self.admin,
            pipeline_json=VALID_GRAPH,
        )
        resp = self.client.post(f'{RECORDING_URL}{rec.id}/convert-to-pipeline/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        unwrapped = _unwrap(resp)
        self.assertIn('graph_data', unwrapped)
        pipe = Pipeline.objects.get(pk=unwrapped['id'])
        self.assertEqual(pipe.user, self.admin)

    def test_convert_from_recording_data(self):
        """Convert from recording_data events on the fly."""
        rec = Recording.objects.create(
            name='From Events', user=self.admin,
            recording_data={'events': [
                {'event_type': 'click', 'x': 10, 'y': 20, 'timestamp': 0},
            ]},
        )
        resp = self.client.post(f'{RECORDING_URL}{rec.id}/convert-to-pipeline/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rec.refresh_from_db()
        # pipeline_json was cached
        self.assertTrue(rec.pipeline_json.get('nodes'))

    def test_convert_empty_recording_fails(self):
        """No pipeline_json and no events -> 400."""
        rec = Recording.objects.create(name='Empty', user=self.admin)
        resp = self.client.post(f'{RECORDING_URL}{rec.id}/convert-to-pipeline/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_convert_with_empty_events_fails(self):
        rec = Recording.objects.create(
            name='Empty Events', user=self.admin,
            recording_data={'events': []},
        )
        resp = self.client.post(f'{RECORDING_URL}{rec.id}/convert-to-pipeline/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_viewer_can_convert(self):
        """convert_to_pipeline requires 'view' permission (not in write list)."""
        viewer = User.objects.create_user(
            username='conv_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        rec = Recording.objects.create(
            name='Viewer Conv', user=viewer,
            pipeline_json=VALID_GRAPH,
        )
        _login(self.client, 'conv_viewer', 'ViewerPass123!')
        resp = self.client.post(f'{RECORDING_URL}{rec.id}/convert-to-pipeline/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class ChainNodeTests(TestCase):
    """TaskChainNodeView: GET list, POST create, DELETE, check-circular."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='node_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'node_admin', 'AdminPass123!')
        self.chain = TaskChain.objects.create(name='Node Chain', created_by=self.admin)
        self.task = Task.objects.create(name='Node Task')

    def test_get_chain_nodes(self):
        TaskChainNode.objects.create(chain=self.chain, task=self.task, order=1)
        TaskChainNode.objects.create(chain=self.chain, task=self.task, order=2)
        resp = self.client.get(CHAIN_NODES_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 7.3 (N192 B1): unified_response 信封后, list 在 resp.data['data'].
        nodes = _unwrap(resp)
        self.assertEqual(len(nodes), 2)

    def test_get_chain_nodes_filter_by_chain(self):
        chain2 = TaskChain.objects.create(name='Other Chain', created_by=self.admin)
        TaskChainNode.objects.create(chain=self.chain, task=self.task, order=1)
        TaskChainNode.objects.create(chain=chain2, task=self.task, order=1)
        resp = self.client.get(f'{CHAIN_NODES_URL}?chain_id={self.chain.id}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 7.3 (N192 B1): unified_response 信封后, list 在 resp.data['data'].
        nodes = _unwrap(resp)
        self.assertEqual(len(nodes), 1)

    def test_get_chain_nodes_filter_by_task(self):
        task2 = Task.objects.create(name='Other Task')
        TaskChainNode.objects.create(chain=self.chain, task=self.task, order=1)
        TaskChainNode.objects.create(chain=self.chain, task=task2, order=2)
        resp = self.client.get(f'{CHAIN_NODES_URL}?task_id={self.task.id}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 7.3 (N192 B1): unified_response 信封后, list 在 resp.data['data'].
        nodes = _unwrap(resp)
        self.assertEqual(len(nodes), 1)

    def test_create_chain_node(self):
        resp = self.client.post(CHAIN_NODES_URL, {
            'chain': self.chain.id,
            'task': self.task.id,
            'order': 1,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        self.assertEqual(_unwrap(resp)['order'], 1)

    def test_create_chain_node_invalid(self):
        """Missing required 'order' field -> 400."""
        resp = self.client.post(CHAIN_NODES_URL, {
            'chain': self.chain.id,
            'task': self.task.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_chain_node(self):
        node = TaskChainNode.objects.create(chain=self.chain, task=self.task, order=1)
        resp = self.client.delete(f'{CHAIN_NODES_URL}{node.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(TaskChainNode.objects.filter(id=node.id).exists())

    def test_delete_nonexistent_node(self):
        resp = self.client.delete(f'{CHAIN_NODES_URL}99999/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_check_circular_no_cycle(self):
        """Linear A -> B -> C: no cycle."""
        node_a = TaskChainNode.objects.create(chain=self.chain, task=self.task, order=1)
        node_b = TaskChainNode.objects.create(
            chain=self.chain, task=self.task, parent=node_a, order=2,
        )
        TaskChainNode.objects.create(
            chain=self.chain, task=self.task, parent=node_b, order=3,
        )
        resp = self.client.post(f'{CHAIN_NODES_URL}check-circular/', {
            'chain_id': self.chain.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        self.assertFalse(_unwrap(resp)['has_cycle'])

    def test_check_circular_with_cycle(self):
        """A -> B -> A: cycle detected."""
        node_a = TaskChainNode.objects.create(chain=self.chain, task=self.task, order=1)
        node_b = TaskChainNode.objects.create(
            chain=self.chain, task=self.task, parent=node_a, order=2,
        )
        node_a.parent = node_b
        node_a.save()
        resp = self.client.post(f'{CHAIN_NODES_URL}check-circular/', {
            'chain_id': self.chain.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        self.assertTrue(_unwrap(resp)['has_cycle'])

    def test_check_circular_via_action_param(self):
        """check-circular can also be triggered via action=check_circular."""
        TaskChainNode.objects.create(chain=self.chain, task=self.task, order=1)
        resp = self.client.post(CHAIN_NODES_URL, {
            'action': 'check_circular',
            'chain_id': self.chain.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 followup (P0-12, 2026-07-28): 适配 unified_response 信封
        self.assertFalse(_unwrap(resp)['has_cycle'])

    def test_viewer_can_get_nodes(self):
        User.objects.create_user(
            username='node_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        _login(self.client, 'node_viewer', 'ViewerPass123!')
        resp = self.client.get(CHAIN_NODES_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_node(self):
        User.objects.create_user(
            username='node_viewer2', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        _login(self.client, 'node_viewer2', 'ViewerPass123!')
        resp = self.client.post(CHAIN_NODES_URL, {
            'chain': self.chain.id, 'task': self.task.id, 'order': 1,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class URLRoutingTests(TestCase):
    """Verify all URL routes in urls.py are accessible."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='url_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'url_admin', 'AdminPass123!')

    def test_pipelines_list_route(self):
        resp = self.client.get(PIPELINE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_pipeline_validate_route(self):
        resp = self.client.post(f'{PIPELINE_URL}validate/', {'graph_data': {}}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_pipeline_estimate_time_route(self):
        resp = self.client.post(f'{PIPELINE_URL}estimate-time/', {'graph_data': {}}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_task_chains_list_route(self):
        resp = self.client.get(TASK_CHAIN_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_recordings_list_route(self):
        resp = self.client.get(RECORDING_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_chain_nodes_list_route(self):
        resp = self.client.get(CHAIN_NODES_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_chain_nodes_check_circular_route(self):
        resp = self.client.post(f'{CHAIN_NODES_URL}check-circular/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
