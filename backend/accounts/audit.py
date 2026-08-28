"""
审计日志工具 — 与 accounts.AuditLog 模型同 app。

历史上此模块位于 tasks/audit.py，因 AuditLog 模型从 tasks 迁到 accounts
（R37-P3 Stage 7 Task 20a，2026-07-08），本文件随之迁移以保持模型与写入
逻辑同 app。

注意：log_audit 当前无调用方（0 行 AuditLog 数据），属于预留的审计写入
入口。后续接入审计日志时请直接调用此函数，无需跨 app import。
"""
import logging

from .models import AuditLog

logger = logging.getLogger(__name__)


def log_audit(user, action: str, resource_type: str, resource_id: str = '', details: dict = None, ip_address: str = None):
    """记录审计日志（非阻塞）"""
    try:
        AuditLog.objects.create(
            user=user if user and user.is_authenticated else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            details=details or {},
            ip_address=ip_address,
        )
    except Exception as e:
        logger.warning(f"审计日志写入失败: {e}")
