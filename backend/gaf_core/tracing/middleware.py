"""Tracing middleware (migrated from tracing app to gaf_core).

Generates a trace_id for every HTTP request and propagates it through
a contextvar (``gaf_core.tracing.context.current_trace_id``) so that
``FileLogHandler`` can stamp each log line with the same trace_id
without coupling to the request object.

The legacy ``TraceSpan`` DB write has been removed (spec §2.2 — table
kept read-only for historical queries). The trace chain is now:

    HTTP request → contextvar → log line in run.log

The ``X-Trace-Id`` response header is preserved so clients can still
correlate requests with log lines.
"""

import uuid

from gaf_core.tracing.context import current_trace_id


class TracingMiddleware:
    """Auto-generate trace_id for each HTTP request and propagate via contextvar."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        trace_id = request.headers.get('X-Trace-Id', str(uuid.uuid4()))
        request.trace_id = trace_id

        token = current_trace_id.set(trace_id)

        try:
            response = self.get_response(request)
        finally:
            current_trace_id.reset(token)

        response['X-Trace-Id'] = trace_id
        return response
