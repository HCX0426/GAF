"""Tracing app tests (middleware + log handler + logentry filter)

合并说明: 原 test_middleware.py + test_log_handler.py + test_logentry_filter.py
三者同属 tracing app，测试 trace_id 全链路（生成→传播→落盘→查询），合并后减少文件碎片。
"""
import logging
import os
import tempfile
import uuid
from datetime import datetime

from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory
from gaf_core.models import LogEntry
from gaf_core.tracing.context import current_execution_id, current_trace_id
from gaf_core.tracing.middleware import TracingMiddleware

# ===========================================================================
# TracingMiddleware (原 test_middleware.py)
# ===========================================================================


class TracingMiddlewareTest(TestCase):
    """TracingMiddleware: trace_id generation + contextvar propagation."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_middleware_sets_trace_id_contextvar(self):
        """During a request, current_trace_id contextvar holds the trace_id."""
        captured = {}

        def get_response(request):
            # Inside the request scope — contextvar should be set.
            captured['trace_id'] = current_trace_id.get()
            return HttpResponse('ok')

        request = self.factory.get('/api/sample/')
        middleware = TracingMiddleware(get_response)
        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'ok')
        self.assertIsNotNone(captured['trace_id'])
        # The contextvar value should match the X-Trace-Id response header.
        self.assertEqual(response['X-Trace-Id'], captured['trace_id'])
        # After the request completes, the contextvar must be reset to None
        # so it does not leak into subsequent requests on the same thread.
        self.assertIsNone(current_trace_id.get())

    def test_middleware_resets_contextvar_on_exception(self):
        """If the view raises, the contextvar is still reset (try/finally)."""

        def get_response(request):
            raise RuntimeError('view exploded')

        request = self.factory.get('/api/sample/')
        middleware = TracingMiddleware(get_response)

        with self.assertRaises(RuntimeError):
            middleware(request)

        # Contextvar must be reset even when the view raised.
        self.assertIsNone(current_trace_id.get())

    def test_middleware_honors_client_trace_id_header(self):
        """X-Trace-Id request header is echoed back (client-supplied trace_id)."""
        client_trace_id = 'client-supplied-12345'

        def get_response(request):
            return HttpResponse('ok')

        request = self.factory.get('/api/sample/', HTTP_X_TRACE_ID=client_trace_id)
        response = TracingMiddleware(get_response)(request)

        self.assertEqual(response['X-Trace-Id'], client_trace_id)


class TracingMiddlewareUuidFormatTest(TestCase):
    """B3-2 (spec 2026-07-30-debug-directory-restructure): trace_id 格式统一为完整 UUID.

    此前 middleware 用 ``str(uuid.uuid4())[:16]`` 截断为 16 字符, 与
    ``MessageFrameSerializer.trace_id = UUIDField(format="hex_verbose")``
    要求的完整 UUID 格式不兼容, 会导致 WS 帧 schema 校验失败. 改为
    ``str(uuid.uuid4())`` (36 字符, 含 4 个 dash) 与 WS 帧 schema 对齐,
    也与 serialize_frame 中 ``str(trace_id or uuid.uuid4())`` 的格式一致.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def test_middleware_generates_full_uuid_when_no_header(self):
        """无 X-Trace-Id header 时, 默认生成的 trace_id 是完整 UUID (36 字符)."""
        def get_response(request):
            return HttpResponse('ok')

        request = self.factory.get('/api/sample/')
        response = TracingMiddleware(get_response)(request)

        trace_id = response['X-Trace-Id']
        # 完整 UUID = 32 hex + 4 dashes = 36 字符
        self.assertEqual(len(trace_id), 36)
        # 应能通过 uuid.UUID() 解析
        uuid.UUID(trace_id)

    def test_middleware_trace_id_compatible_with_frame_schema(self):
        """生成的 trace_id 能通过 MessageFrameSerializer 的 UUIDField 校验."""
        from datetime import UTC, datetime

        from protocol.constants import MessageType
        from protocol.serializers import MessageFrameSerializer

        def get_response(request):
            return HttpResponse('ok')

        request = self.factory.get('/api/sample/')
        response = TracingMiddleware(get_response)(request)

        trace_id = response['X-Trace-Id']
        # 用该 trace_id 构造一个 WS 帧, 验证 schema 校验通过
        frame_data = {
            "trace_id": trace_id,
            "type": MessageType.AGENT_HEARTBEAT,
            "seq": 1,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "payload": {},
        }
        serializer = MessageFrameSerializer(data=frame_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_middleware_does_not_truncate_trace_id(self):
        """生成的 trace_id 不应是 16 字符截断格式 (回归保护)."""
        def get_response(request):
            return HttpResponse('ok')

        request = self.factory.get('/api/sample/')
        response = TracingMiddleware(get_response)(request)

        trace_id = response['X-Trace-Id']
        # 旧格式 str(uuid.uuid4())[:16] 是 16 字符无 dash, 必须不是这种
        self.assertNotEqual(len(trace_id), 16)
        self.assertIn("-", trace_id)


# ===========================================================================
# FileLogHandlerTraceIdTest (原 test_log_handler.py)
# ===========================================================================


class FileLogHandlerTraceIdTest(TestCase):
    """FileLogHandler: trace_id lands in run.log file, not LogEntry table."""

    def setUp(self):
        # Use an isolated temp dir so emitted logs don't pollute the
        # real <DEBUG_DIR>/ during tests.
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmpdir = self._tmpdir.name
        # Fixed timestamp so build_execution_debug_dir generates a deterministic
        # path (date=20260728, time=153000) for assertions.
        self._fixed_time = datetime(2026, 7, 28, 15, 30, 0)

    def _precreate_exec_dir(self, execution_id: str, task_name: str = "TestTask") -> str:
        """Pre-create the per-execution dir like dispatch_task would.

        FileLogHandler._resolve_exec_log_dir() calls find_exec_dir_by_id()
        to reverse-lookup the exec dir from execution_id. Without pre-creation
        the handler falls back to _global/run.log, which would not test the
        nested-format integration.
        """
        from gaf_core.debug_path import build_execution_debug_dir
        exec_dir = build_execution_debug_dir(
            self.tmpdir, execution_id, task_name, start_time=self._fixed_time,
        )
        os.makedirs(exec_dir, exist_ok=True)
        return exec_dir

    def _make_handler(self):
        """Build a FileLogHandler pointed at the test tmpdir."""
        from gaf_core.handlers import FileLogHandler
        return FileLogHandler(debug_dir=self.tmpdir)

    def test_log_line_receives_trace_id(self):
        """A WARNING log emitted with the contextvar set gets that trace_id."""
        test_trace_id = 'trace-abc-123'
        exec_dir = self._precreate_exec_dir('exec-test-trace', 'TraceTestTask')
        token_trace = current_trace_id.set(test_trace_id)
        token_exec = current_execution_id.set('exec-test-trace')
        try:
            handler = self._make_handler()
            logger = logging.getLogger('tracing.tests.test_logentry_receives_trace_id')
            logger.handlers = [handler]
            logger.setLevel(logging.WARNING)
            logger.warning('test warning for trace_id propagation')
            handler.close()
        finally:
            current_execution_id.reset(token_exec)
            current_trace_id.reset(token_trace)

        # N194 嵌套结构: <tmpdir>/<YYYYMMDD>/<task_name>/<HHMMSS_suffix>/run.log
        log_path = os.path.join(exec_dir, 'run.log')
        self.assertTrue(os.path.exists(log_path),
                        f"run.log not found at {log_path}; tmpdir contents: {os.listdir(self.tmpdir)}")
        with open(log_path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('trace-abc-123', content)
        self.assertIn('test warning for trace_id propagation', content)

    def test_log_line_trace_id_absent_without_context(self):
        """Outside a request scope, the log line has no trace_id placeholder."""
        # Make sure trace_id is None
        self.assertIsNone(current_trace_id.get())
        exec_dir = self._precreate_exec_dir('exec-test-no-trace', 'NoTraceTask')
        token_exec = current_execution_id.set('exec-test-no-trace')
        try:
            handler = self._make_handler()
            logger = logging.getLogger('tracing.tests.test_logentry_trace_id_none')
            logger.handlers = [handler]
            logger.setLevel(logging.WARNING)
            logger.warning('test warning without trace context')
            handler.close()
        finally:
            current_execution_id.reset(token_exec)

        log_path = os.path.join(exec_dir, 'run.log')
        self.assertTrue(os.path.exists(log_path),
                        f"run.log not found at {log_path}; tmpdir contents: {os.listdir(self.tmpdir)}")
        with open(log_path, encoding='utf-8') as f:
            content = f.read()
        # No trace_id placeholder should appear in the line.
        self.assertNotIn('[trace_id=', content)
        self.assertIn('test warning without trace context', content)

    def test_full_request_log_chain(self):
        """End-to-end: HTTP request → contextvar → run.log line with trace_id.

        spec §2.2: TraceSpan DB write was removed; the chain now ends at
        the log file, not the table. The trace_id in run.log must match
        the X-Trace-Id response header.
        """
        captured_trace_id = {}
        factory = RequestFactory()
        exec_dir = self._precreate_exec_dir('exec-test-chain', 'ChainTestTask')
        handler = self._make_handler()
        token_exec = current_execution_id.set('exec-test-chain')

        def get_response(request):
            # While the contextvar is set, emit a WARNING log. The
            # FileLogHandler will stamp the log line with this trace_id.
            captured_trace_id['value'] = current_trace_id.get()
            logger = logging.getLogger('tracing.tests.test_full_request_log_chain')
            logger.handlers = [handler]
            logger.setLevel(logging.WARNING)
            logger.warning('chained log inside request')
            return HttpResponse('ok')

        try:
            request = factory.get('/api/chained/')
            response = TracingMiddleware(get_response)(request)
        finally:
            current_execution_id.reset(token_exec)
            handler.close()

        trace_id = response['X-Trace-Id']
        self.assertEqual(captured_trace_id['value'], trace_id)

        # Log line must exist in the per-execution run.log and carry
        # the SAME trace_id — this is the chain-closing assertion
        # (request trace_id ↔ log line trace_id).
        log_path = os.path.join(exec_dir, 'run.log')
        self.assertTrue(os.path.exists(log_path),
                        f"run.log not found at {log_path}; tmpdir contents: {os.listdir(self.tmpdir)}")
        with open(log_path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn(trace_id, content)
        self.assertIn('chained log inside request', content)


# ===========================================================================
# LogEntryTraceIdFilterTest (原 test_logentry_filter.py)
# ===========================================================================


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _get_results(resp):
    """适配信封 + 分页。先解信封, 再取分页 results 字段。"""
    data = _unwrap(resp)
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


class LogEntryTraceIdFilterTest(TestCase):
    """LogEntry list API (?trace_id=) and filter integration."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        LogEntry.objects.all().delete()

    def test_logentry_list_filter_by_trace_id(self):
        """GET /api/v2/logs/?trace_id= returns only matching entries."""
        LogEntry.objects.create(
            level='WARNING', source='test.source', message='entry-A',
            trace_id='trace-filter-1',
        )
        LogEntry.objects.create(
            level='WARNING', source='test.source', message='entry-B',
            trace_id='trace-filter-2',
        )
        LogEntry.objects.create(
            level='WARNING', source='test.source', message='entry-C',
            trace_id=None,
        )

        response = self.client.get('/api/v2/logs/?trace_id=trace-filter-1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['message'], 'entry-A')
        self.assertEqual(results[0]['trace_id'], 'trace-filter-1')

    def test_logentry_serializer_exposes_trace_id(self):
        """LogEntrySerializer includes trace_id in the response payload."""
        LogEntry.objects.create(
            level='WARNING', source='test.source', message='serialized-entry',
            trace_id='trace-serial',
        )
        response = self.client.get('/api/v2/logs/?trace_id=trace-serial')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_get_results(response)[0]['trace_id'], 'trace-serial')
