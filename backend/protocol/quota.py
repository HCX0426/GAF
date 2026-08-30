"""Agent 资源配额校验模块：检查 Agent 是否超出资源配额，决定是否允许分配新任务。"""

import logging

logger = logging.getLogger(__name__)

DEFAULT_CPU_THRESHOLD = 80.0
DEFAULT_MEMORY_THRESHOLD = 85.0
DEFAULT_MAX_CONCURRENT_TASKS = 5


def check_agent_quota(agent_session) -> tuple[bool, str]:
    """检查 Agent 是否超出资源配额，决定是否允许分配新任务。

    从 WorkerSession.resource_quota 读取配置，检查 CPU/内存/并发任务数是否超限。
    若 resource_quota 未配置相关字段，使用默认阈值。

    Args:
        agent_session: WorkerSession 实例，需包含 resource_quota、cpu_usage、
                       memory_usage 等字段

    Returns:
        Tuple[bool, str]: (是否允许分配新任务, 原因说明)
    """
    if agent_session is None:
        return False, "WorkerSession 不存在"

    quota = agent_session.resource_quota or {}
    cpu_threshold = quota.get("cpu_threshold", DEFAULT_CPU_THRESHOLD)
    memory_threshold = quota.get("memory_threshold", DEFAULT_MEMORY_THRESHOLD)
    max_concurrent = quota.get("max_concurrent_tasks", DEFAULT_MAX_CONCURRENT_TASKS)

    cpu_usage = agent_session.cpu_usage
    memory_usage = agent_session.memory_usage

    if cpu_usage is not None and cpu_usage >= cpu_threshold:
        reason = f"CPU 使用率 {cpu_usage:.1f}% 超过阈值 {cpu_threshold:.1f}%"
        logger.warning(
            "Agent 配额校验不通过: session_id=%s, %s",
            agent_session.agent_id, reason,
        )
        return False, reason

    if memory_usage is not None and memory_usage >= memory_threshold:
        reason = f"内存使用率 {memory_usage:.1f}% 超过阈值 {memory_threshold:.1f}%"
        logger.warning(
            "Agent 配额校验不通过: session_id=%s, %s",
            agent_session.agent_id, reason,
        )
        return False, reason

    current_tasks = agent_session.capabilities.get("active_tasks", 0)
    if current_tasks >= max_concurrent:
        reason = f"并发任务数 {current_tasks} 已达到上限 {max_concurrent}"
        logger.warning(
            "Agent 配额校验不通过: session_id=%s, %s",
            agent_session.agent_id, reason,
        )
        return False, reason

    return True, "配额校验通过"
