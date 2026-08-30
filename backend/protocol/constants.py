"""协议常量定义：消息类型枚举与帧 JSON Schema。"""


class MessageType:
    """WebSocket 消息帧支持的消息类型枚举。

    17 种类型 = 16 当前协议 + 1 legacy back-compat (TASK_ASSIGN).

    Direction 说明:
      - AGENT_TO_SERVER: Agent 发送给服务端（上行）
      - SERVER_TO_AGENT: 服务端发送给 Agent（下行）
    """

    AGENT_REGISTER = "agent.register"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_STATUS = "agent.status"

    TASK_DISPATCH = "task.dispatch"
    TASK_PROGRESS = "task.progress"
    TASK_CANCEL = "task.cancel"
    TASK_RESULT = "task.result"

    # Pipeline execution path (PipelineViewSet.execute → Agent). Distinct from
    # TASK_DISPATCH which carries a single task_definition; PIPELINE_EXECUTE
    # carries a full graph_data DAG consumed by PipelineEngine.
    PIPELINE_EXECUTE = "pipeline.execute"

    SCREENSHOT_FRAME = "screenshot.frame"
    SCREENSHOT_CONTROL = "screenshot.control"

    DEVICE_ACTION = "device.action"
    DEVICE_ACTION_RESULT = "device.action_result"
    # Agent → Server: sync discovered local devices so the server can
    # create/associate Device records without manual registration. Sent by
    # agent client/connection.py:_sync_devices right after agent.register.
    DEVICE_SYNC = "device.sync"

    # Server → Agent: device recovery command (restart_app / relogin /
    # notify_only / restart_emulator / reconnect_adb / switch_backup),
    # dispatched by scheduler/recovery_engine._action_device_command via
    # channel group_send. S2 (2026-08-16): consumer.device_command
    # forwards it to the agent as a WS frame — without this routing method
    # Channels silently drops the group_send and the recovery action
    # reports success while the agent never receives the command.
    DEVICE_COMMAND = "device.command"

    EVENT_ALERT = "event.alert"
    EVENT_ACK = "event.ack"

    # Server → Agent: hot-update monitor rules without restarting the agent.
    # Triggered by MonitorRuleViewSet.push_to_agent action; consumed by
    # MessageHandler.handle_monitor_rule_update which forwards to
    # MonitorManager.update_rules(). Without this channel the agent only
    # loads rules at startup from local ResourcePack and ignores DB edits.
    MONITOR_RULE_UPDATE = "monitor.rule.update"

    # ---- LLM call via WebSocket RPC (Task 2.1, 2026-08-08) ----
    # Agent → Server: agent delegates LLM calls to the backend via WS RPC
    # so it can benefit from the 4-level fallback chain (LLMRouter) without
    # needing its own HTTP client or provider config. The backend processes
    # the request through LLMRouter and returns the result via LLM_RESULT.
    LLM_CALL = "llm.call"
    LLM_RESULT = "llm.result"

    # ---- Compression negotiation (spec-42, TD-287) ----
    # Agent → Server: agent sends "hello" right after WS connect to advertise
    # supported compression algorithms + threshold. Server responds with
    # "hello.ack" confirming the chosen algorithm (or enabled=False to
    # decline). After successful negotiation both sides switch large frames
    # (>= threshold bytes) to MessageCompressor.compress() wire format.
    # Legacy agents/backends that don't send/ack hello fall back to JSON
    # text_data (backward compat).
    HELLO = "hello"
    HELLO_ACK = "hello.ack"

    # ---- Legacy back-compat (TD-208 修复 2026-07-18, spec-29c 2026-07-19 partial cleanup) ----
    # Only TASK_ASSIGN remains as a back-compat alias; backend senders
    # (tasks/tasks.py + pipeline/tasks.py) still send "task.assign" type via
    # group_send and protocol WorkerConsumer.task_assign handler forwards it
    # to the agent. worker/src/client/connection.py handler_map accepts
    # "task.assign" as alias for "task.dispatch".
    # AGENT_CONNECTED / AGENT_REGISTERED / ERROR were removed in spec-29c
    # (legacy agents/consumers.py at /ws/agents/ deleted; no sender remained).
    TASK_ASSIGN = "task.assign"  # legacy alias for TASK_DISPATCH

    @classmethod
    def all_types(cls):
        """返回所有消息类型字符串列表。

        Returns:
            list[str]: 全部 19 种消息类型 (16 当前协议 + 2 compression negotiation + 1 legacy TASK_ASSIGN)
        """
        return [
            cls.AGENT_REGISTER,
            cls.AGENT_HEARTBEAT,
            cls.AGENT_STATUS,
            cls.TASK_DISPATCH,
            cls.TASK_PROGRESS,
            cls.TASK_CANCEL,
            cls.TASK_RESULT,
            cls.PIPELINE_EXECUTE,
            cls.SCREENSHOT_FRAME,
            cls.SCREENSHOT_CONTROL,
            cls.DEVICE_ACTION,
            cls.DEVICE_ACTION_RESULT,
            cls.DEVICE_SYNC,
            cls.DEVICE_COMMAND,
            cls.EVENT_ALERT,
            cls.EVENT_ACK,
            cls.MONITOR_RULE_UPDATE,
            # LLM WebSocket RPC (Task 2.1)
            cls.LLM_CALL,
            cls.LLM_RESULT,
            # Compression negotiation (spec-42, TD-287)
            cls.HELLO,
            cls.HELLO_ACK,
            # Legacy back-compat (TD-208)
            cls.TASK_ASSIGN,
        ]

    @classmethod
    def agent_to_server_types(cls):
        """返回 Agent→Server 上行消息类型。

        Returns:
            list[str]: 上行消息类型
        """
        return [
            cls.AGENT_REGISTER,
            cls.AGENT_HEARTBEAT,
            cls.TASK_PROGRESS,
            cls.TASK_RESULT,
            cls.SCREENSHOT_FRAME,
            cls.DEVICE_ACTION_RESULT,
            cls.DEVICE_SYNC,
            cls.EVENT_ALERT,
            # LLM WebSocket RPC (Task 2.1)
            cls.LLM_CALL,
            # Compression negotiation (spec-42, TD-287)
            cls.HELLO,
        ]

    @classmethod
    def server_to_agent_types(cls):
        """返回 Server→Agent 下行消息类型。

        Returns:
            list[str]: 下行消息类型 (含 1 个 legacy TASK_ASSIGN, TD-208)
        """
        return [
            cls.AGENT_STATUS,
            cls.TASK_DISPATCH,
            cls.TASK_CANCEL,
            cls.PIPELINE_EXECUTE,
            cls.SCREENSHOT_CONTROL,
            cls.DEVICE_ACTION,
            cls.DEVICE_COMMAND,
            cls.EVENT_ACK,
            cls.MONITOR_RULE_UPDATE,
            # LLM WebSocket RPC (Task 2.1)
            cls.LLM_RESULT,
            # Compression negotiation (spec-42, TD-287)
            cls.HELLO_ACK,
            # Legacy back-compat (TD-208)
            cls.TASK_ASSIGN,
        ]


MESSAGE_FRAME_SCHEMA = {
    "type": "object",
    "required": ["trace_id", "type", "seq", "timestamp", "payload"],
    "properties": {
        "trace_id": {
            "type": "string",
            "description": "UUID v4 格式的追踪 ID，用于全链路日志关联",
        },
        "type": {
            "type": "string",
            "enum": MessageType.all_types(),
            "description": "消息类型，取值来自 MessageType 枚举",
        },
        "seq": {
            "type": "integer",
            "minimum": 1,
            "description": "消息序号，连接内单调递增",
        },
        "timestamp": {
            "type": "string",
            "format": "date-time",
            "description": "ISO 8601 格式的 UTC 时间戳",
        },
        "payload": {
            "type": "object",
            "description": "消息负载，结构由 type 决定",
        },
    },
    "additionalProperties": False,
}

MESSAGE_TYPE_DIRECTION_MAP = {
    **dict.fromkeys(MessageType.agent_to_server_types(), "agent_to_server"),
    **dict.fromkeys(MessageType.server_to_agent_types(), "server_to_agent"),
}


class FrontendEventType:
    """Frontend WebSocket event types broadcast via channels group_send.

    Single source of truth for event names consumed by frontend WS_EVENT
    (frontend/src/types/ws-events.ts). Distinct from MessageType which covers
    Agent ↔ Server protocol frame types.

    TD-201/202 修复 (2026-07-18): 命名归一化 — device_status → device.status
    (与 device.updated/metrics_updated/registered/capabilities_updated 一致用点号分隔).
    """

    # Agent broadcasts
    AGENT_HEARTBEAT = "agent_heartbeat"
    AGENT_STATUS = "agent_status"

    # Task / execution stream
    EXECUTION_LOG = "execution_log"
    EXECUTION_STEP_UPDATE = "execution_step_update"

    # Screenshot stream
    SCREENSHOT_FRAME = "screenshot_frame"
    SCREENSHOT_STREAM_CONTROL = "screenshot_stream_control"

    # Connection state
    CONNECTED = "connected"

    # Device broadcasts (TD-201 修复: device_status → device.status)
    DEVICE_STATUS = "device.status"
    DEVICE_UPDATED = "device.updated"
    DEVICE_METRICS_UPDATED = "device.metrics_updated"
    DEVICE_REGISTERED = "device.registered"
    DEVICE_CAPABILITIES_UPDATED = "device.capabilities_updated"

    # Log stream
    LOG_ENTRY = "log.entry"

    # Notification stream (spec-59-E / TD-297: single source of truth for
    # notifications/consumers.py broadcast events; previously hardcoded as
    # string literals "notification" / "connected" in consumers.py).
    NOTIFICATION = "notification"


# spec-29a #30: single source of truth for the dashboard broadcast group name.
# Backend senders (agents/signals.py, agents/views.py, accounts/services.py)
# import this constant instead of hard-coding "clients"/"dashboard" strings.
# FrontendConsumer joins this group so browser clients connected to /ws/dashboard/
# receive device.* / agent.* / execution_log broadcasts.
DASHBOARD_GROUP = "dashboard"

# Channel group name for real-time log streaming to the LogCenterPage frontend.
# DatabaseLogHandler broadcasts new LogEntry records to this group; LogStreamConsumer
# (mounted at /ws/logs/) joins it and echoes entries to browser subscribers.
LOGS_GROUP = "logs"

