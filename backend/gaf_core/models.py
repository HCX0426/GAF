"""Core shared models for the GAF Django backend.

.. deprecated:: spec §2.2 (2026-07-25)
    ``LogEntry`` is no longer written to — the DB write was removed in
    favor of file-based archiving. F12 (2026-07-31): 表已为真只读,
    ``cleanup_old_logs`` 定时任务已删除, 所有写入/删除路径已移除.
    The physical table is preserved for historical read-only queries;
    new code must not write to it. The ``/api/v2/logs/`` API may still
    read legacy rows.

Specialized log models (AuditLog, RecoveryLog, MessageFrameLog,
LLMUsageLog, CrashReport) remain in their respective apps; LogEntry did
NOT replace them and continues to be the generic application-log
persistence layer for legacy data only.
"""
import hashlib

from django.db import models
from django.utils import timezone


class LogEntry(models.Model):
    """Unified log entry — persists logger records from all backend apps.

    .. deprecated:: spec §2.2 (2026-07-25)
        No longer written to by ``FileLogHandler``. The table is kept
        read-only for historical queries. New log data lives in
        ``<debug_dir>/logs/<execution_id>/run.log`` via ``FileLogHandler``.

    Historically written by ``gaf_core.handlers.DatabaseLogHandler``.
    Read-only via the ``/api/v2/logs/`` API. Not a replacement for
    specialized log models (AuditLog, RecoveryLog, etc.) — those retain
    business semantics. LogEntry is the generic application-log
    persistence layer (legacy / read-only).
    """

    LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]

    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='Timestamp',
        help_text='When the log record was created.',
    )
    level = models.CharField(
        max_length=10,
        choices=LEVEL_CHOICES,
        db_index=True,
        verbose_name='Level',
        help_text='Log severity level.',
    )
    source = models.CharField(
        max_length=200,
        db_index=True,
        verbose_name='Source',
        help_text='Logger name (e.g. "tasks.views", "protocol.consumers").',
    )
    message = models.TextField(
        verbose_name='Message',
        help_text='Log message text.',
    )
    traceback = models.TextField(
        blank=True,
        default='',
        verbose_name='Traceback',
        help_text='Exception traceback, if the log record included exc_info.',
    )
    task_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Task ID',
        help_text='Associated task ID, if applicable.',
    )
    agent_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Agent ID',
        help_text='Associated agent ID, if applicable.',
    )
    device_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Device ID',
        help_text='Associated device ID, if applicable.',
    )
    trace_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Trace ID',
        help_text=(
            'Tracing trace_id for request correlation '
            '(from TracingMiddleware contextvar)'
        ),
    )
    fingerprint = models.CharField(
        max_length=64,
        default='',
        db_index=True,
        verbose_name='Fingerprint',
        help_text=(
            'SHA-256 hash of (source + level + message[:200]) for dedup. '
            'Empty for legacy rows created before this field was added.'
        ),
    )
    occurrence_count = models.IntegerField(
        default=1,
        verbose_name='Occurrence Count',
        help_text='How many times this exact log was emitted within the dedup window.',
    )
    first_seen = models.DateTimeField(
        default=timezone.now,
        verbose_name='First Seen',
        help_text='When this log was first recorded (same as timestamp for new rows).',
    )
    last_seen = models.DateTimeField(
        auto_now=True,
        verbose_name='Last Seen',
        help_text='When this log was last seen (updated on each dedup merge).',
    )

    class Meta:
        db_table = 'core_log_entry'
        ordering = ['-last_seen']
        indexes = [
            models.Index(fields=['-last_seen']),
            models.Index(fields=['level']),
            models.Index(fields=['source']),
            models.Index(fields=['trace_id']),
            models.Index(fields=['fingerprint']),
        ]
        verbose_name = 'Log Entry'
        verbose_name_plural = 'Log Entries'

    def __str__(self):
        return f'[{self.level}] {self.source}: {self.message[:80]}'

    @staticmethod
    def compute_fingerprint(source: str, level: str, message: str) -> str:
        """Compute a dedup fingerprint for a log record.

        Truncates message to 200 chars to group near-identical messages
        that differ only in trailing context (e.g. timestamps in message).
        """
        raw = f'{source}|{level}|{message[:200]}'
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]
