"""Serializers for the core app."""
from rest_framework import serializers

from gaf_core.models import LogEntry


class LogEntrySerializer(serializers.ModelSerializer):
    """Serializer for LogEntry — read-only API.

    All fields are read-only because LogEntry records are created by
    DatabaseLogHandler, not by API clients.
    """

    class Meta:
        model = LogEntry
        fields = [
            'id', 'timestamp', 'level', 'source', 'message',
            'traceback', 'task_id', 'agent_id', 'device_id', 'trace_id',
        ]
        read_only_fields = fields
