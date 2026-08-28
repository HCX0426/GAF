import logging

from django.utils import timezone

from protocol.broadcast import async_broadcast_to_dashboard
from protocol.constants import FrontendEventType

logger = logging.getLogger(__name__)


class LogService:
    """日志服务，支持 WebSocket 实时推送和数据库持久化"""

    @staticmethod
    async def push_log_to_client(execution_id, level, message):
        """通过 WebSocket 推送日志到 dashboard group。

        spec-29a #30: group renamed from legacy "clients" to DASHBOARD_GROUP;
        event type renamed from "task.log" (no matching FrontendConsumer
        handler) to FrontendEventType.EXECUTION_LOG so FrontendConsumer
        .execution_log can actually receive and forward these messages.

        Args:
            execution_id: 任务执行记录 ID
            level: 日志级别 (INFO/WARNING/ERROR/DEBUG)
            message: 日志消息内容
        """
        await async_broadcast_to_dashboard(
            FrontendEventType.EXECUTION_LOG,
            {
                "execution_id": str(execution_id),
                "level": level,
                "message": message,
                "timestamp": timezone.now().isoformat(),
            },
        )

    @staticmethod
    def push_log_sync(execution_id, level, message):
        """同步方式推送日志到 Client（适用于非异步上下文调用）。

        Args:
            execution_id: 任务执行记录 ID
            level: 日志级别
            message: 日志消息内容
        """
        from asgiref.sync import async_to_sync

        async_to_sync(LogService.push_log_to_client)(execution_id, level, message)

    @staticmethod
    def append_execution_log(execution_id, level, message):
        """追加日志到 TaskExecution.log 字段，同时推送到客户端。

        Args:
            execution_id: 任务执行记录 ID
            level: 日志级别
            message: 日志消息内容
        """
        from tasks.models import TaskExecution

        try:
            execution = TaskExecution.objects.get(id=execution_id)
        except TaskExecution.DoesNotExist:
            logger.error("TaskExecution %s 不存在，无法追加日志", execution_id)
            return

        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}\n"
        execution.log = (execution.log or "") + log_line
        execution.save(update_fields=["log"])

        LogService.push_log_sync(execution_id, level, message)

    @staticmethod
    def get_execution_logs(execution_id, level=None, limit=1000):
        """获取任务执行日志，支持按级别过滤。

        Args:
            execution_id: 任务执行记录 ID
            level: 可选的日志级别过滤
            limit: 返回的最大日志行数

        Returns:
            str: 过滤后的日志文本
        """
        from tasks.models import TaskExecution

        try:
            execution = TaskExecution.objects.get(id=execution_id)
        except TaskExecution.DoesNotExist:
            return ""

        raw_log = execution.log or ""
        if not raw_log:
            return ""

        lines = raw_log.strip().split("\n")
        if level:
            lines = [line for line in lines if f"[{level}]" in line]

        return "\n".join(lines[-limit:])
