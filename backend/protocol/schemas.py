"""协议 JSON Schema 定义：任务分发/进度/结果/取消 及 任务状态机。"""

from enum import StrEnum


class TaskState(StrEnum):
    """任务执行状态机枚举。

    状态流转路径：
      pending → dispatched → running → completed
                                     → failed
                                     → cancelled
    """

    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def terminal_states(cls):
        """返回终止状态集合。

        Returns:
            set[TaskState]: 终止状态
        """
        return {cls.COMPLETED, cls.FAILED, cls.CANCELLED}

    @classmethod
    def active_states(cls):
        """返回活跃状态集合。

        Returns:
            set[TaskState]: 活跃状态
        """
        return {cls.PENDING, cls.DISPATCHED, cls.RUNNING}

    @classmethod
    def valid_transitions(cls):
        """返回合法状态转移映射。

        Returns:
            dict[str, set[str]]: 源状态 → 允许的目标状态集合
        """
        return {
            cls.PENDING: {cls.DISPATCHED, cls.CANCELLED},
            cls.DISPATCHED: {cls.RUNNING, cls.CANCELLED, cls.FAILED},
            cls.RUNNING: {cls.COMPLETED, cls.FAILED, cls.CANCELLED},
        }

    @classmethod
    def can_transition(cls, from_state, to_state):
        """检查状态转移是否合法。

        Args:
            from_state: 源状态
            to_state: 目标状态

        Returns:
            bool: 是否允许转移
        """
        transitions = cls.valid_transitions()
        return to_state in transitions.get(from_state, set())


TASK_DISPATCH_SCHEMA = {
    "type": "object",
    "required": ["execution_id", "task_id", "pipeline"],
    "properties": {
        "execution_id": {
            "type": "string",
            "description": "执行实例 ID（UUID v4）",
        },
        "task_id": {
            "type": "string",
            "description": "任务定义 ID",
        },
        "pipeline": {
            "type": "array",
            "description": "管道步骤定义列表",
            "items": {
                "type": "object",
                "required": ["step_index", "step_name", "step_type"],
                "properties": {
                    "step_index": {"type": "integer", "minimum": 0},
                    "step_name": {"type": "string"},
                    "step_type": {"type": "string"},
                    "action": {"type": "string"},
                    "params": {"type": "object"},
                    "retry_count": {"type": "integer", "default": 0},
                    "timeout_ms": {"type": "integer"},
                },
            },
        },
        "options": {
            "type": "object",
            "description": "任务执行选项",
            "properties": {
                "max_retries": {"type": "integer", "default": 3},
                "timeout_seconds": {"type": "integer", "default": 300},
                "screenshot_on_error": {"type": "boolean", "default": True},
                "continue_on_error": {"type": "boolean", "default": False},
            },
        },
        "game_account": {
            "type": "object",
            "description": "游戏账户信息",
            "properties": {
                "account_id": {"type": "string"},
                "username": {"type": "string"},
                "server": {"type": "string"},
            },
        },
        "device_constraints": {
            "type": "object",
            "description": "设备约束条件",
            "properties": {
                "os": {"type": "string"},
                "resolution": {"type": "string"},
                "min_memory_gb": {"type": "number"},
            },
        },
    },
    "additionalProperties": False,
}


TASK_PROGRESS_SCHEMA = {
    "type": "object",
    "required": ["execution_id", "step_index", "status"],
    "properties": {
        "execution_id": {
            "type": "string",
            "description": "执行实例 ID",
        },
        "step_index": {
            "type": "integer",
            "minimum": 0,
            "description": "当前步骤序号",
        },
        "status": {
            "type": "string",
            "enum": ["pending", "running", "success", "failed", "skipped"],
            "description": "步骤执行状态",
        },
        "step_name": {
            "type": "string",
            "description": "步骤名称（pipeline 节点 ID 或 task 步骤名）",
        },
        "screenshot": {
            "type": "string",
            "description": "步骤截图（base64 或路径）",
        },
        "duration_ms": {
            "type": "integer",
            "minimum": 0,
            "description": "步骤耗时（毫秒）",
        },
        "message": {
            "type": "string",
            "description": "步骤描述或错误消息",
        },
        "error_msg": {
            "type": "string",
            "description": "步骤失败原因（status=failed 时填充，用于 ExecutionStep.error_message）",
        },
        "elapsed_time": {
            "type": "number",
            "minimum": 0,
            "description": "步骤耗时（秒，浮点数，用于 ExecutionStep.duration）",
        },
    },
    "additionalProperties": False,
}


TASK_RESULT_SCHEMA = {
    "type": "object",
    "required": ["execution_id", "status", "steps_completed", "total_steps"],
    "properties": {
        "execution_id": {
            "type": "string",
            "description": "执行实例 ID",
        },
        "status": {
            "type": "string",
            "enum": ["completed", "failed", "cancelled"],
            "description": "任务最终状态",
        },
        "steps_completed": {
            "type": "integer",
            "minimum": 0,
            "description": "已完成步骤数",
        },
        "total_steps": {
            "type": "integer",
            "minimum": 1,
            "description": "总步骤数",
        },
        "error": {
            "type": "object",
            "description": "错误详情（任务失败时）",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "step_index": {"type": "integer"},
                "screenshot": {"type": "string"},
            },
        },
        "result_data": {
            "type": "object",
            "description": "任务执行结果数据",
        },
        "duration_ms": {
            "type": "integer",
            "minimum": 0,
            "description": "任务总耗时（毫秒）",
        },
    },
    "additionalProperties": False,
}


TASK_CANCEL_SCHEMA = {
    "type": "object",
    "required": ["execution_id"],
    "properties": {
        "execution_id": {
            "type": "string",
            "description": "要取消的执行实例 ID",
        },
        "reason": {
            "type": "string",
            "description": "取消原因",
        },
        "force": {
            "type": "boolean",
            "default": False,
            "description": "是否强制终止",
        },
    },
    "additionalProperties": False,
}


AGENT_REGISTER_PAYLOAD_SCHEMA = {
    "type": "object",
    "required": ["agent_id"],
    "properties": {
        "agent_id": {
            "type": "string",
            "description": "Agent 唯一标识",
        },
        "hostname": {
            "type": "string",
            "description": "主机名",
        },
        "ip_address": {
            "type": "string",
            "description": "IP 地址",
        },
        "os_info": {
            "type": "string",
            "description": "操作系统信息",
        },
        "version": {
            "type": "string",
            "description": "Agent 版本号",
        },
        "capabilities": {
            "type": "object",
            "description": "Agent 能力声明",
            "properties": {
                "screenshot_methods": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "支持的截图方式",
                },
                "input_methods": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "支持的输入方式",
                },
                "recognition_engines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "支持的识别引擎",
                },
            },
        },
        "resource_quota": {
            "type": "object",
            "description": "资源配额申请",
            "properties": {
                "max_concurrent_tasks": {"type": "integer", "default": 1},
                "max_memory_mb": {"type": "integer"},
                "max_cpu_cores": {"type": "number"},
            },
        },
    },
    "additionalProperties": False,
}


AGENT_HEARTBEAT_PAYLOAD_SCHEMA = {
    "type": "object",
    "required": [],
    "properties": {
        "agent_id": {
            "type": "string",
            "description": "Agent 唯一标识",
        },
        "resource_stats": {
            "type": "object",
            "description": "当前资源使用统计",
            "properties": {
                "cpu_percent": {"type": "number"},
                "memory_used_mb": {"type": "number"},
                "memory_total_mb": {"type": "number"},
                "disk_used_gb": {"type": "number"},
                "active_tasks": {"type": "integer"},
            },
        },
        "status": {
            "type": "string",
            "enum": ["idle", "busy", "online"],
            "description": "Agent 当前状态",
        },
    },
    "additionalProperties": False,
}
