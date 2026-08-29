"""WebSocket Consumer：Agent 连接路由，消息帧解析与分发。"""

import asyncio
import contextlib
import json
import logging
import os
import time
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone as django_timezone
from gaf_core.mixins.auth import JWTAuthMixin
from gaf_core.tracing.context import current_trace_id

# TD-259 #29: cross-app model imports (agents.models.Agent/Device,
# tasks.models.ExecutionStep/TaskExecution, agents.game_binding) moved
# into protocol.services.* function bodies (inline imports). Consumers
# now delegate to service functions; see protocol/services.py.
from protocol.broadcast import async_broadcast_to_dashboard
from protocol.constants import DASHBOARD_GROUP, LOGS_GROUP, FrontendEventType, MessageType
from protocol.message_compressor import (
    COMPRESSION_ALGORITHM_MSGPACK_ZLIB,
    HelloFrameError,
    MessageCompressor,
    MessageCompressorError,
    build_hello_ack_frame,
    parse_hello_capabilities,
)
from protocol.models import AgentSession
from protocol.quota import check_agent_quota
from protocol.serializers import build_error_frame, deserialize_frame, serialize_frame
from protocol.services import (
    lookup_device_id_by_agent,
    map_db_device_ids_to_agent_strings,
    register_agent_device,
    set_agent_offline,
    update_agent_heartbeat,
    update_or_create_agent_with_session,
    update_task_execution_result,
    upsert_execution_step,
)

logger = logging.getLogger(__name__)

# spec 2026-08-29-logging-system-consolidation P1-1: 消息帧日志开关.
# 记录 agent↔backend 每帧 (inbound/outbound) 到 MessageFrameLog, 供日志中心
# "消息帧日志" tab + AI 调试回溯. 高帧率截图场景可设 0 关闭.
PROTOCOL_FRAME_LOG_ENABLED = os.getenv("PROTOCOL_FRAME_LOG_ENABLED", "1") == "1"
# 截图/大 payload 帧: 只记元信息不存 body (防表膨胀)
_FRAME_LOG_SKIP_BODY_TYPES = {"screenshot.frame", "screenshot.control", "device.action_result", "device.action"}
_FRAME_LOG_MAX_PAYLOAD_CHARS = 2048


HEARTBEAT_WARNING_SECONDS = 15
HEARTBEAT_OFFLINE_SECONDS = 30
HEARTBEAT_CHECK_INTERVAL = 10

# DASHBOARD_GROUP and LOGS_GROUP now live in protocol.constants (spec-29a #30)
# so backend senders (agents/signals.py, agents/views.py, accounts/services.py)
# can import them without pulling in this consumer module (avoids circular import).


# TD-259 #22: process-local cache for _map_agent_device_id (called per
# screenshot frame at ~30 FPS). Keyed by (agent_id, agent_device_id,
# device_name, device_type, window_handle). Invalidated wholesale on any
# Device post_save / post_delete (see agents/signals.py). Read-mostly dict;
# the check-then-set race is benign (worst case = duplicate DB lookup with
# identical result).
_AGENT_DEVICE_ID_CACHE: dict[tuple, int | None] = {}


def clear_agent_device_id_cache() -> None:
    """Clear the agent_device_id -> Device.id mapping cache.

    Invoked by ``agents.signals`` on Device post_save / post_delete so that
    stale mappings do not persist after device configuration changes.
    """
    _AGENT_DEVICE_ID_CACHE.clear()


def _normalize_frame_payload(message_type: str, frame: dict) -> dict:
    """收起/截断帧 payload 生成日志体 (纯函数, 便于单测).

    - 截图/大 payload 帧: 只记元信息不存 body (防表膨胀)
    - 普通帧: payload 超过 _FRAME_LOG_MAX_PAYLOAD_CHARS 截断为 preview
    """
    if message_type in _FRAME_LOG_SKIP_BODY_TYPES:
        return {"_skipped": True, "message_type": message_type}
    payload = dict(frame)
    rendered = json.dumps(payload, ensure_ascii=False, default=str)
    if len(rendered) > _FRAME_LOG_MAX_PAYLOAD_CHARS:
        payload = {"_truncated": True, "preview": rendered[: _FRAME_LOG_MAX_PAYLOAD_CHARS]}
    return payload


class AgentConsumer(AsyncWebsocketConsumer):
    """Agent WebSocket 连接消费者（异步），解析消息帧并按类型分发到对应处理器。

    连接生命周期：
      connect → 接收消息帧 → 类型路由 → stub handler (echo/log) → disconnect
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_id = None
        self._agent_pk = None
        self._agent_session_id = None
        self._seq = 0
        self._last_heartbeat = None
        self._heartbeat_task = None
        # spec-42 compression negotiation state. Stays False for legacy
        # agents that never send a Hello frame — they keep using JSON
        # text_data end-to-end. Switched to True only after the agent
        # advertises a supported algorithm and we acknowledge it.
        self._compression_negotiated = False
        self._compressor: MessageCompressor | None = None

    async def connect(self):
        """接受 Agent WebSocket 连接，初始化连接状态并启动心跳检测任务。"""
        # Defense-in-depth: TokenAuthMiddleware should have set scope['agent'].
        # Reject if missing (e.g. middleware bypassed or path mismatch).
        agent = self.scope.get("agent")
        if not agent:
            logger.warning("Agent WebSocket rejected: no agent in scope (auth middleware bypassed?)")
            await self.close(code=4003)
            return

        # Bind agent_id from the authenticated scope immediately. The middleware
        # already validated the token and resolved the Agent record, so the id
        # is trustworthy. Previously connect() did NOT set self.agent_id here —
        # it waited for _handle_agent_register to read agent_id from the
        # register payload, but the agent never sends agent_id in that payload.
        # As a result registration failed ("Agent 注册缺少 agent_id"),
        # group_add never ran, and group_send messages (pipeline.execute /
        # task.dispatch) were silently dropped — Pipeline execution stayed
        # "pending" forever.
        self.agent_id = str(agent.agent_id)
        # Cache the Agent row's PK (integer) for LogEntry.agent_id FK writes.
        # self.agent_id above is the human-readable Agent.agent_id string
        # (e.g. "agent-001"); LogEntry.agent_id is an IntegerField storing
        # the Agent.id PK, so we keep both.
        self._agent_pk = agent.pk

        await self.accept()
        logger.info(
            "Agent WebSocket 连接已建立: channel=%s, agent_id=%s",
            self.channel_name,
            self.agent_id,
        )

        # Join the agent's channel group immediately so group_send messages
        # reach this consumer even before the agent.register frame arrives.
        # _handle_agent_register calls group_add again (idempotent in Channels).
        await self.channel_layer.group_add(f"agent_{self.agent_id}", self.channel_name)

        # spec P4: CAS 抢占 active_channel — 新连接接管 agent 所有权.
        # 旧的僵尸连接 channel 与 active_channel 不匹配 → 其 heartbeat/offline
        # 写入全部被 service 层校验拦截, 无法再污染 Agent 状态.
        claimed = await self._db_claim_active_channel()
        if not claimed:
            logger.warning(
                "Agent active_channel CAS 抢占失败 (可能已有更新连接): agent_id=%s channel=%s",
                self.agent_id, self.channel_name,
            )
            await self.close(code=4003)
            return

        self._heartbeat_task = asyncio.create_task(self._heartbeat_checker())

        ack_frame = serialize_frame(
            msg_type=MessageType.AGENT_STATUS,
            payload={"status": "connected", "message": "连接已建立"},
        )
        await self.send(text_data=ack_frame)

    async def disconnect(self, close_code):
        """Agent 断开连接时取消心跳检测、离开 Channel Group 并标记 Agent 离线。

        Args:
            close_code: WebSocket 关闭码
        """
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None

        if self.agent_id:
            await self.channel_layer.group_discard(f"agent_{self.agent_id}", self.channel_name)
            await self._db_set_agent_offline(self.agent_id)

        logger.info(
            "Agent WebSocket 连接断开: channel=%s, code=%s, agent_id=%s",
            self.channel_name,
            close_code,
            self.agent_id,
        )

    async def receive(self, text_data=None, bytes_data=None):
        """接收 Agent 消息帧，解析并路由到对应处理器。

        支持两种 wire 路径 (spec-42):
        - JSON text_data: 旧路径 / fallback / Hello/Hello.ack 协商帧本身
        - compressed bytes_data: 协商成功后, 大帧走 MessageCompressor envelope

        Args:
            text_data: JSON 文本消息 (legacy / fallback / negotiation frames)
            bytes_data: 压缩二进制消息 (post-negotiation)
        """
        # Path 1: compressed bytes_data (only meaningful post-negotiation).
        if (
            bytes_data is not None
            and self._compression_negotiated
            and self._compressor is not None
        ):
            try:
                frame_dict = self._compressor.decompress(bytes_data)
            except MessageCompressorError as e:
                logger.warning("压缩帧 decompress 失败: %s", e)
                error_frame = build_error_frame(f"压缩帧解析失败: {e}")
                await self.send(text_data=error_frame)
                return
            try:
                # Re-validate the decompressed dict through the same DRF
                # schema used for text_data frames — agent is authenticated
                # but a corrupted wire byte could still produce a malformed
                # dict, and the downstream handler dispatch assumes a
                # validated frame (frame["type"], frame["trace_id"]).
                frame = deserialize_frame(frame_dict)
            except Exception as e:
                logger.warning("压缩帧 schema 校验失败: %s", e)
                error_frame = build_error_frame(f"压缩帧 schema 校验失败: {e}")
                await self.send(text_data=error_frame)
                return
        # Path 2: JSON text_data (legacy / fallback / negotiation frames).
        elif text_data is not None:
            try:
                frame = deserialize_frame(text_data)
            except Exception as e:
                logger.warning("消息帧解析失败: %s", str(e))
                error_frame = build_error_frame(f"消息帧解析失败: {str(e)}")
                await self.send(text_data=error_frame)
                return
        else:
            # Both None — ignore (mirrors legacy `if text_data is None: return`).
            return

        self._seq = max(self._seq, frame.get("seq", 0))

        # spec 2026-08-29-logging-system-consolidation P1-1: 记录 inbound 帧
        if PROTOCOL_FRAME_LOG_ENABLED:
            await self._log_frame(frame["type"], "inbound", frame)

        msg_type = frame["type"]

        # 性能计量: 计算 WebSocket 消息端到端延迟 (仅开发模式).
        sent_at = frame.get("sent_at")
        if sent_at is not None:
            try:
                from gaf_core.perf_monitor import PerformanceMonitor

                _mon = PerformanceMonitor.get_instance()
                if _mon.is_development:
                    _latency_ms = (time.time() - sent_at) * 1000.0
                    _mon.record(
                        "ws.message.e2e_latency", _latency_ms,
                        {"msg_type": msg_type},
                    )
            except Exception:
                pass  # Best-effort: never block message processing for perf.

        handler = self._get_handler(msg_type)

        try:
            await handler(frame)
        except Exception:
            logger.exception("消息处理器异常: type=%s", msg_type)
            error_frame = build_error_frame(f"消息处理异常: {msg_type}", trace_id=str(frame.get("trace_id", "")))
            await self.send(text_data=error_frame)

    def _get_handler(self, msg_type):
        """根据消息类型返回对应的 async handler。

        Args:
            msg_type: 消息类型字符串

        Returns:
            callable: 异步处理器函数
        """
        handler_map = {
            MessageType.AGENT_REGISTER: self._handle_agent_register,
            MessageType.AGENT_HEARTBEAT: self._handle_agent_heartbeat,
            MessageType.AGENT_STATUS: self._handle_agent_status,
            MessageType.TASK_DISPATCH: self._handle_task_dispatch,
            MessageType.TASK_PROGRESS: self._handle_task_progress,
            MessageType.TASK_CANCEL: self._handle_task_cancel,
            MessageType.TASK_RESULT: self._handle_task_result,
            MessageType.SCREENSHOT_FRAME: self._handle_screenshot_frame,
            MessageType.SCREENSHOT_CONTROL: self._handle_screenshot_control,
            MessageType.DEVICE_ACTION: self._handle_device_action,
            MessageType.DEVICE_ACTION_RESULT: self._handle_device_action_result,
            MessageType.DEVICE_SYNC: self._handle_device_sync,
            MessageType.EVENT_ALERT: self._handle_event_alert,
            MessageType.EVENT_ACK: self._handle_event_ack,
            # spec-42 compression negotiation (agent → server).
            MessageType.HELLO: self._handle_hello,
            # Task 2.1: LLM call via WebSocket RPC (agent → server).
            MessageType.LLM_CALL: self._handle_llm_call,
        }
        return handler_map.get(msg_type, self._handle_unknown)

    async def _handle_agent_register(self, frame):
        """处理 Agent 注册消息：创建/更新 Agent 与 AgentSession 记录，声明能力，分配资源配额。
        注册成功后加入 agent_{id} Channel group 以接收 Celery 下发的任务。

        Args:
            frame: 已校验的消息帧，payload 包含 agent_id / hostname / capabilities 等
        """
        payload = frame.get("payload", {})
        self.agent_id = payload.get("agent_id", self.agent_id)

        if not self.agent_id:
            error_frame = build_error_frame("Agent 注册缺少 agent_id", trace_id=frame["trace_id"])
            await self.send(text_data=error_frame)
            return

        session_id = await self._db_create_or_update_agent(payload)
        self._agent_session_id = session_id
        self._last_heartbeat = time.time()

        await self.channel_layer.group_add(f"agent_{self.agent_id}", self.channel_name)
        logger.info(
            "Agent 注册成功: agent_id=%s, hostname=%s, trace_id=%s (已加入组 agent_%s)",
            self.agent_id,
            payload.get("hostname", ""),
            frame["trace_id"],
            self.agent_id,
        )

        ack = serialize_frame(
            msg_type=MessageType.AGENT_STATUS,
            payload={
                "status": "registered",
                "agent_id": self.agent_id,
                "message": "Agent 注册成功",
            },
        )
        await self.send(text_data=ack)

    async def _handle_agent_heartbeat(self, frame):
        """处理 Agent 心跳消息：更新心跳时间、资源统计及 AgentSession 资源字段。

        Args:
            frame: 已校验的消息帧，payload 包含 stats / status 等
        """
        payload = frame.get("payload", {})
        stats = payload.get("stats", {})

        if self.agent_id:
            await self._db_update_heartbeat(self.agent_id, payload)

        if self._agent_session_id:
            await self._db_update_agent_session_resource(self._agent_session_id, stats)

        self._last_heartbeat = time.time()

        cpu = stats.get("cpu", 0)
        memory = stats.get("memory", 0)
        fps = stats.get("fps", 0)
        logger.debug(
            "Agent 心跳: agent_id=%s, trace_id=%s, cpu=%.1f%%, mem=%.1f%%, fps=%.1f",
            self.agent_id,
            frame["trace_id"],
            cpu,
            memory,
            fps,
        )

        ack = serialize_frame(
            msg_type=MessageType.EVENT_ACK,
            payload={"ack_type": MessageType.AGENT_HEARTBEAT},
        )
        await self.send(text_data=ack)

        await async_broadcast_to_dashboard(
            FrontendEventType.AGENT_HEARTBEAT,
            {
                "agent_id": self.agent_id,
                "stats": {
                    "cpu": stats.get("cpu", 0),
                    "memory": stats.get("memory", 0),
                    "fps": stats.get("fps", 0),
                },
                "status": payload.get("status", "idle"),
                "timestamp": django_timezone.now().isoformat(),
            },
        )

    async def _handle_agent_status(self, frame):
        """处理 Agent 状态变更消息：广播到 dashboard 组前端可以实时更新"""
        payload = frame.get("payload", {})
        logger.info("Agent 状态消息: agent_id=%s, trace_id=%s", self.agent_id, frame["trace_id"])

        if self.agent_id:
            status = payload.get("status", "idle")
            await async_broadcast_to_dashboard(
                FrontendEventType.AGENT_STATUS,
                {
                    "agent_id": self.agent_id,
                    "status": status,
                    "timestamp": django_timezone.now().isoformat(),
                },
            )

    async def _handle_task_dispatch(self, frame):
        """处理任务分发消息（Server→Agent 下行）：校验资源配额后确认接收任务。

        Args:
            frame: 已校验的消息帧，payload 包含 execution_id / task_id / pipeline
        """
        payload = frame.get("payload", {})
        execution_id = payload.get("execution_id", "")

        if self._agent_session_id:
            session = await self._db_get_agent_session(self._agent_session_id)
            allowed, reason = check_agent_quota(session)
            if not allowed:
                logger.warning(
                    "任务分发被配额校验拒绝: agent_id=%s, execution_id=%s, reason=%s",
                    self.agent_id,
                    execution_id,
                    reason,
                )
                error_frame = build_error_frame(f"资源配额不足: {reason}", trace_id=frame["trace_id"])
                await self.send(text_data=error_frame)
                return

        logger.info(
            "任务分发: agent_id=%s, execution_id=%s, trace_id=%s",
            self.agent_id,
            execution_id,
            frame["trace_id"],
        )
        ack = serialize_frame(
            msg_type=MessageType.EVENT_ACK,
            payload={"ack_type": MessageType.TASK_DISPATCH, "execution_id": execution_id},
        )
        await self.send(text_data=ack)

    async def _handle_task_progress(self, frame):
        """处理任务进度消息（Agent→Server 上行）：记录步骤进度并推送到前端。

        P-010 Phase 2: when the payload carries step_index (pipeline mode),
        persist an ExecutionStep row so step-level failures become visible
        to the recovery engine via the post_save signal wired in Phase 3.
        Non-step progress frames (status=running without step_index) are
        treated as task-level heartbeats and skip ExecutionStep persistence.

        Args:
            frame: 已校验的消息帧，payload 包含 execution_id / step_index / status / message
        """
        payload = frame.get("payload", {})
        execution_id = payload.get("execution_id", "")
        status = payload.get("status", "")
        message = payload.get("message", "")
        step_index = payload.get("step_index")
        logger.info(
            "任务进度: agent_id=%s, execution_id=%s, step=%s, status=%s, trace_id=%s",
            self.agent_id,
            execution_id,
            step_index,
            status,
            frame["trace_id"],
        )

        # P-010 Phase 2: persist ExecutionStep when the agent sends a
        # step-level progress frame (pipeline mode). Step frames always
        # carry step_index + step_name; without step_index this is a
        # task-level heartbeat and we skip persistence.
        if step_index is not None:
            await self._persist_execution_step(payload)

        # Forward agent progress as a frontend execution_log event so the
        # ExecutionMonitorPanel log terminal shows real-time agent activity.
        # Include status/reason so the frontend can show a paused indicator
        # when the window background monitor pauses the pipeline.
        log_level = "OK" if status in ("running", "completed", "success") else "INFO"
        log_payload = {
            "execution_id": execution_id,
            "timestamp": django_timezone.now().isoformat(),
            "level": log_level,
            "source": "agent",
            "message": message or f"[task.progress] status={status}",
            "status": status,
        }
        reason = payload.get("reason", "")
        if reason:
            log_payload["reason"] = reason
        await async_broadcast_to_dashboard(
            FrontendEventType.EXECUTION_LOG,
            log_payload,
        )

    @database_sync_to_async
    def _persist_execution_step(self, payload: dict[str, Any]) -> None:
        """Persist or update an ExecutionStep row from a task.progress payload.

        Delegates to ``protocol.services.upsert_execution_step``
        (TD-259 #29: cross-app TaskExecution/ExecutionStep model imports
        isolated in service).

        P-010 Phase 2: mirrors the legacy ``agents/consumers.py`` pattern of
        ``ExecutionStep.objects.update_or_create(task_result, step_index)``
        so re-sends (retry) upsert instead of duplicating. Maps the new
        schema fields (step_name/error_msg/elapsed_time) to the model.

        Non-fatal: any DB error is logged and swallowed so a bad payload
        never crashes the WebSocket consumer.
        """
        upsert_execution_step(payload)

    async def _handle_task_cancel(self, frame):
        """处理任务取消消息（Server→Agent 下行或 Agent 确认取消）。

        Args:
            frame: 已校验的消息帧，payload 包含 execution_id / reason
        """
        payload = frame.get("payload", {})
        execution_id = payload.get("execution_id", "")
        logger.info(
            "任务取消: agent_id=%s, execution_id=%s, reason=%s, trace_id=%s",
            self.agent_id,
            execution_id,
            payload.get("reason", ""),
            frame["trace_id"],
        )
        ack = serialize_frame(
            msg_type=MessageType.EVENT_ACK,
            payload={"ack_type": MessageType.TASK_CANCEL, "execution_id": execution_id},
        )
        await self.send(text_data=ack)

    async def _handle_task_result(self, frame):
        """处理任务执行结果消息（Agent→Server 上行）：更新 TaskExecution 状态并发送 ACK。

        Args:
            frame: 已校验的消息帧，payload 包含 execution_id / success / data / elapsed_time / error_msg / error_code
        """
        payload = frame.get("payload", {})
        execution_id = payload.get("execution_id", "")
        success = bool(payload.get("success", False))
        elapsed_time = payload.get("elapsed_time", 0)
        error_msg = payload.get("error_msg", "")
        error_code = payload.get("error_code", "") or ""
        result_data = payload.get("data", {}) or {}
        # N190 (2026-07-26): agent 在 task.result payload 顶层携带
        # structured_log_path (agent 本地 <debug_dir>/structured/<exec_id>.jsonl)。
        # 写入 execution_snapshot.structured_log_path, 供 AI 工具
        # (_search_similar_errors_via_jsonl / get_structured_log) 和
        # pack_execution_logs 读取。
        structured_log_path = payload.get("structured_log_path", "") or ""

        logger.info(
            "任务结果: agent_id=%s, execution_id=%s, success=%s, elapsed=%ss, error_code=%s, trace_id=%s, structured_log=%s",
            self.agent_id,
            execution_id,
            success,
            elapsed_time,
            error_code or "<none>",
            frame["trace_id"],
            structured_log_path or "<none>",
        )

        # Update TaskExecution record (N145 L1 fix: previously only ACK was sent,
        # leaving execution status stuck at "pending" forever).
        if execution_id:
            await self._db_update_execution_result(
                execution_id=execution_id,
                success=success,
                elapsed_time=elapsed_time,
                error_msg=error_msg,
                result_data=result_data,
                structured_log_path=structured_log_path,
                error_code=error_code,
            )
            # TD-267 fix: release ConcurrencyController slot + restore
            # Device.status to ONLINE. The wiring was lost in spec-29c
            # (commit 8f184734) when the legacy agents/consumers.py:AgentConsumer
            # was deleted. Without these calls, slots leak (agent eventually
            # permanently "full") and Device.status stays BUSY forever.
            await self._release_resources_for_execution(execution_id, payload)

        # Forward the final result to the frontend execution log so users can see
        # why a task failed directly in the ExecutionMonitorPanel.
        log_level = "OK" if success else "ERROR"
        log_message = f"[task.result] execution={execution_id} success={success}"
        if error_msg:
            log_message += f" error={error_msg}"
        await async_broadcast_to_dashboard(
            FrontendEventType.EXECUTION_LOG,
            {
                "execution_id": execution_id,
                "timestamp": django_timezone.now().isoformat(),
                "level": log_level,
                "message": log_message,
                "trace_id": frame.get("trace_id", ""),
            },
        )

        ack = serialize_frame(
            msg_type=MessageType.EVENT_ACK,
            payload={
                "ack_type": MessageType.TASK_RESULT,
                "execution_id": execution_id,
            },
        )
        await self.send(text_data=ack)

    @database_sync_to_async
    def _db_update_execution_result(self, *, execution_id, success, elapsed_time, error_msg, result_data, structured_log_path="", error_code=""):
        """Sync ORM update wrapped for async consumer (N145 L1 fix).

        Delegates to ``protocol.services.update_task_execution_result``
        (TD-259 #29: cross-app TaskExecution model import isolated in
        service; chain advancement ``transaction.on_commit`` also moved
        into the service so the consumer no longer touches
        ``tasks.models`` or ``pipeline.tasks`` directly).

        Args:
            execution_id: TaskExecution pk (string or int from agent payload)
            success: bool — agent's success flag
            elapsed_time: float seconds (or None / non-numeric)
            error_msg: str — failure reason (empty on success)
            result_data: dict — pipeline result on success
            structured_log_path: str — agent-local JSONL path
                (N190: written to execution_snapshot.structured_log_path)
            error_code: str — task-level error code from agent (N192 fix)
        """
        update_task_execution_result(
            execution_id=execution_id,
            success=success,
            elapsed_time=elapsed_time,
            error_msg=error_msg,
            result_data=result_data,
            structured_log_path=structured_log_path,
            error_code=error_code,
        )

    @database_sync_to_async
    def _release_resources_for_execution(self, execution_id, payload):
        """Release ConcurrencyController slot + restore Device.status (TD-267 fix).

        Wraps the two helpers in ``tasks.services`` that were previously
        called by the legacy ``agents/consumers.py:AgentConsumer`` but lost
        in spec-29c. Sync ORM work is wrapped for async consumer (mirrors
        ``_db_update_execution_result`` pattern).

        Safe to call when no slot was acquired (release is silent on
        unknown pairs) or when execution has no device (restore no-ops).

        Args:
            execution_id: TaskExecution pk (string or int from agent payload).
            payload: agent message payload dict; passed through to
                ``_restore_device_status_by_msg`` which extracts
                ``execution_id`` itself.
        """
        from tasks.services import (
            _release_concurrency_slot,
            _restore_device_status_by_msg,
        )
        _release_concurrency_slot(self.agent_id, execution_id)
        _restore_device_status_by_msg(payload)

    async def _handle_screenshot_frame(self, frame):
        """Handle screenshot frame from Agent and broadcast to dashboard group.

        Args:
            frame: Validated message frame with device_id, image_base64, width, height, captured_at
        """
        payload = frame.get("payload", {})
        agent_device_id = payload.get("device_id")
        # Map the agent-side device identifier to the backend Device primary key
        # so the frontend can match frames against its numeric device ids.
        db_device_id = await self._map_agent_device_id(
            agent_device_id=agent_device_id,
            device_name=payload.get("device_name", ""),
            device_type=payload.get("device_type", ""),
            window_handle=payload.get("window_handle", ""),
        )
        logger.info(
            "Screenshot frame: agent_id=%s, agent_device_id=%s, db_device_id=%s, trace_id=%s, img_size=%d",
            self.agent_id,
            agent_device_id,
            db_device_id,
            frame.get("trace_id", ""),
            len(str(payload.get("image_base64", ""))),
        )

        try:
            await async_broadcast_to_dashboard(
                FrontendEventType.SCREENSHOT_FRAME,
                {
                    # Prefer the backend Device.id when available; fall back to
                    # the raw agent identifier so the frame is still useful.
                    "device_id": db_device_id if db_device_id is not None else agent_device_id,
                    "agent_device_id": agent_device_id,
                    "image_base64": payload.get("image_base64", ""),
                    "width": payload.get("width", 0),
                    "height": payload.get("height", 0),
                    "captured_at": payload.get("captured_at", ""),
                },
            )
        except Exception as exc:
            logger.exception("group_send screenshot_frame failed: %s", exc)

    async def _map_agent_device_id(self, *, agent_device_id, device_name, device_type, window_handle):
        """Map an agent-side device identifier to the backend Device.id (cached).

        Wraps :meth:`_lookup_agent_device_id_uncached` with a process-local
        in-memory cache (``_AGENT_DEVICE_ID_CACHE``) keyed by the full
        ``(agent_id, agent_device_id, device_name, device_type, window_handle)``
        tuple. The cache is invalidated wholesale on any Device save/delete via
        ``agents.signals._invalidate_agent_device_id_cache``.

        Cache hits return without touching the DB, which is the hot path at
        ~30 FPS screenshot frame rate (TD-259 #22).
        """
        if not self.agent_id:
            return None

        cache_key = (
            self.agent_id,
            agent_device_id,
            device_name,
            device_type,
            window_handle,
        )
        if cache_key in _AGENT_DEVICE_ID_CACHE:
            return _AGENT_DEVICE_ID_CACHE[cache_key]

        result = await self._lookup_agent_device_id_uncached(
            agent_device_id=agent_device_id,
            device_name=device_name,
            device_type=device_type,
            window_handle=window_handle,
        )
        _AGENT_DEVICE_ID_CACHE[cache_key] = result
        return result

    @database_sync_to_async
    def _lookup_agent_device_id_uncached(self, *, agent_device_id, device_name, device_type, window_handle):
        """DB-backed implementation of agent_device_id -> Device.id mapping.

        Delegates to ``protocol.services.lookup_device_id_by_agent``
        (TD-259 #29: cross-app Agent/Device model imports isolated in
        service).

        Performs up to 7 lookup strategies (exact id, window_handle, hwnd
        prefix, device_name, window_title prefix, ADB serial, type-only). See
        :meth:`_map_agent_device_id` for the cached public entry point.

        Agent device ids are opaque strings such as ``windows-0``,
        ``windows-hwnd-0x12345``, ``windows-title-BrownDust II``, or an ADB
        serial like ``127.0.0.1:5555``. The frontend uses the backend's numeric
        Device.id, so we resolve the mapping here before broadcasting the frame.

        Args:
            agent_device_id: The agent's internal device id.
            device_name: Human-readable device name reported by the agent.
            device_type: Agent-reported device type (e.g. ``windows``).
            window_handle: Agent-reported window handle (hex string).

        Returns:
            The backend Device.id (int) or None if no match is found.
        """
        return lookup_device_id_by_agent(
            agent_id=self.agent_id,
            agent_device_id=agent_device_id,
            device_name=device_name,
            device_type=device_type,
            window_handle=window_handle,
        )

    async def _handle_screenshot_control(self, frame):
        """处理 agent 上行的截图流控制消息（罕见 — 主要用于 agent 自检）。

        Agent 通常只发送 ``screenshot.frame``，不会主动发送 control 消息。
        本 handler 仅记录日志便于调试，不实装业务逻辑。

        Args:
            frame: 已校验的消息帧
        """
        payload = frame.get("payload", {})
        logger.info(
            "截图控制上行: trace_id=%s action=%s device_ids=%s",
            frame["trace_id"],
            payload.get("action", ""),
            payload.get("device_ids"),
        )

    async def _handle_device_action(self, frame):
        """Handle device.action frames (protocol reserved, no agent sender yet).

        TD-134 (2026-07-18): The agent (agent/src/) has no send_message call
        for 'device.action' — the protocol reserves this msg_type for future
        device remote-control commands, but no agent-side sender is wired.
        Handler kept to avoid KeyError in handler_map dispatch and to log
        unexpected frames if a future agent version starts sending them.

        Args:
            frame: validated message frame
        """
        logger.info("设备动作 (protocol reserved, no agent sender): trace_id=%s", frame["trace_id"])

    async def _handle_device_sync(self, frame):
        """处理 Agent 上报的本地设备同步消息。

        Agent 在连接建立后通过 ``connection.py:_sync_devices`` 发送
        ``device.sync`` 帧，payload 为 ``{'devices': [...], 'count': N}``，
        其中每个 device 包含 device_id / name / device_type / status /
        adb_serial / emulator。本方法逐个 upsert 到 Device 表并广播到
        前端 Dashboard，使 Agent 自动发现的设备无需手动注册即可在
        设备列表中可见。

        Args:
            frame: 已校验的消息帧，payload 包含 devices 列表
        """
        payload = frame.get("payload", {})
        devices = payload.get("devices", [])
        if not devices:
            logger.debug("device.sync: 无设备需要同步 (agent_id=%s)", self.agent_id)
            return

        synced = 0
        for dev_data in devices[:50]:  # Match agent's 50-device cap
            try:
                result = await self._db_register_device(dev_data)
                if result.get("created") or result.get("updated"):
                    await async_broadcast_to_dashboard(
                        FrontendEventType.DEVICE_STATUS,
                        {
                            "action": "device_updated",
                            "device": {
                                "id": result.get("id"),
                                "name": dev_data.get("name", ""),
                                "device_type": dev_data.get("device_type", ""),
                                "status": dev_data.get("status", "online"),
                                "agent_id": self.agent_id,
                            },
                            "agent_id": self.agent_id,
                            "timestamp": django_timezone.now().isoformat(),
                        },
                    )
                    synced += 1
            except Exception:
                logger.exception(
                    "device.sync: 同步设备失败 device_id=%s, agent_id=%s",
                    dev_data.get("device_id", ""),
                    self.agent_id,
                )

        logger.info(
            "device.sync: 同步完成 agent_id=%s, 共 %d/%d 台设备已 upsert, trace_id=%s",
            self.agent_id,
            synced,
            len(devices),
            frame["trace_id"],
        )

    @staticmethod
    def _recovery_level_for_command(command: str) -> str:
        """Map a device command to its recovery level (P-048).

        'app' level commands: restart_app, relogin, notify_only
        'device' level commands: restart_emulator, reconnect_adb, switch_backup (default)
        """
        app_level_commands = {'restart_app', 'relogin', 'notify_only'}
        return 'app' if command in app_level_commands else 'device'

    async def _handle_device_action_result(self, frame):
        """处理设备动作执行结果消息。

        Agent 通过此消息上报设备发现/截图/输入等操作结果。
        设备发现结果会被写入数据库并广播到前端 Dashboard。
        P-048: 新增 command 分支 — 处理设备命令执行结果, 写入 RecoveryLog。

        Args:
            frame: 已校验的消息帧
        """
        payload = frame.get("payload", {})
        action = payload.get("action", "")
        command = payload.get("command", "")
        logger.info(
            "设备动作结果: agent_id=%s, action=%s, command=%s, trace_id=%s",
            self.agent_id,
            action,
            command,
            frame["trace_id"],
        )

        # P-048: command 分支 — 处理设备命令执行结果
        if command:
            await self._handle_command_result(payload, frame["trace_id"])
            return

        if action == "device_discovered":
            device_data = payload.get("device", {})
            if device_data:
                result = await self._db_register_device(device_data)
                if result.get("created") or result.get("updated"):
                    await async_broadcast_to_dashboard(
                        FrontendEventType.DEVICE_STATUS,
                        {
                            "action": "device_updated",
                            "device": {
                                "id": result.get("id"),
                                "name": device_data.get("name", ""),
                                "device_type": device_data.get("device_type", ""),
                                "status": device_data.get("status", "online"),
                                "agent_id": self.agent_id,
                            },
                            "agent_id": self.agent_id,
                            "timestamp": django_timezone.now().isoformat(),
                        },
                    )
                    logger.info(
                        "设备 %s (created=%s, updated=%s)，已广播到前端",
                        device_data.get("name"),
                        result.get("created"),
                        result.get("updated"),
                    )

    async def _handle_command_result(self, payload: dict, trace_id: str) -> None:
        """Handle device command result: create/update RecoveryLog and broadcast.

        P-048: when payload carries a ``command`` field, the agent is reporting
        the result of a recovery action (e.g. restart_app / restart_emulator).
        We write to RecoveryLog so the recovery engine can track outcomes.

        Args:
            payload: The message payload (contains command, target_id, success,
                output, recovery_log_id, execution_id).
            trace_id: The trace id from the original frame for logging.
        """
        command = payload.get("command", "")
        target_id = payload.get("target_id")
        success = bool(payload.get("success", False))
        output = payload.get("output", {}) or {}
        recovery_log_id = payload.get("recovery_log_id")
        execution_id = payload.get("execution_id", "")
        recovery_level = self._recovery_level_for_command(command)

        logger.info(
            "命令结果处理: agent_id=%s, command=%s, target_id=%s, "
            "success=%s, recovery_log_id=%s, trace_id=%s",
            self.agent_id,
            command,
            target_id,
            success,
            recovery_log_id,
            trace_id,
        )

        await self._db_upsert_recovery_log(
            recovery_log_id=recovery_log_id,
            recovery_level=recovery_level,
            command=command,
            success=success,
            output=output,
            target_id=target_id,
            execution_id=execution_id,
        )

        # Broadcast to dashboard for real-time visibility (N192-B6).
        await async_broadcast_to_dashboard(
            FrontendEventType.EXECUTION_LOG,
            {
                "command": command,
                "target_id": target_id,
                "success": success,
                "recovery_level": recovery_level,
                "output": output,
                "execution_id": execution_id,
                "agent_id": self.agent_id,
                "timestamp": django_timezone.now().isoformat(),
            },
        )

    @database_sync_to_async
    def _db_upsert_recovery_log(self, *, recovery_log_id, recovery_level, command,
                                 success, output, target_id, execution_id):
        """Create or update a RecoveryLog entry for a device command result.

        P-048: if recovery_log_id is provided, update the existing log
        (e.g. the log was created when the command was dispatched). Otherwise
        create a new log entry.
        """
        from scheduler.models import RecoveryLog

        details = {
            "target_id": target_id,
            "command": command,
            "output": output,
        }
        if execution_id:
            details["execution_id"] = execution_id

        if recovery_log_id:
            try:
                log = RecoveryLog.objects.get(id=recovery_log_id)
                log.success = success
                log.action_taken = f"{command} (已确认)"
                log.details = details
                log.save(update_fields=["success", "action_taken", "details", "updated_at"])
                logger.info(
                    "RecoveryLog 已更新: id=%s, command=%s, success=%s",
                    recovery_log_id, command, success,
                )
            except RecoveryLog.DoesNotExist:
                logger.warning(
                    "RecoveryLog 不存在: id=%s, 回退到新建", recovery_log_id,
                )
                RecoveryLog.objects.create(
                    recovery_level=recovery_level,
                    trigger_event=f"device command result: {command}",
                    action_taken=f"{command} (已确认)",
                    success=success,
                    details=details,
                )
        else:
            RecoveryLog.objects.create(
                recovery_level=recovery_level,
                trigger_event=f"device command result: {command}",
                action_taken=f"{command} (已确认)",
                success=success,
                details=details,
            )
            logger.info(
                "RecoveryLog 已创建: command=%s, level=%s, success=%s",
                command, recovery_level, success,
            )

    async def task_assign(self, event):
        """接收 Celery/Channel 分发的任务指派，转发给 Agent WebSocket 客户端"""
        data = event.get("payload", {})
        logger.info(
            "向 Agent 分发任务: agent_id=%s, execution_id=%s, has_device_info=%s",
            self.agent_id,
            data.get("execution_id", ""),
            bool(data.get("device_info")),
        )
        frame = serialize_frame(
            msg_type=MessageType.TASK_DISPATCH,
            payload={
                "execution_id": data.get("execution_id", ""),
                "task_id": data.get("task_id", ""),
                "task_name": data.get("task_name", ""),
                "execution_mode": data.get("execution_mode", "manual"),
                "task_definition": data.get("task_definition", {}),
                "params": data.get("params", {}),
                "timeout": data.get("timeout", 300),
                "retry_policy": data.get("retry_policy", {}),
                "preflight_checks": data.get("preflight_checks", []),
                "recovery_config": data.get("recovery_config", {}),
                # Forward device metadata so the agent can resolve and connect
                # the correct target device before executing the task. Mirrors
                # pipeline_execute behavior (without this the agent falls back
                # to a disconnected discovered device).
                "device_info": data.get("device_info"),
                # N194 fix (2026-07-28): 透传归一化 debug 目录 + 游戏账号 +
                # 资源包 + retry-from-step 参数. 原实现只挑选了部分字段,
                # 导致 agent 收到 debug_dir='' 兜底用 ./debug, structured.jsonl
                # 和 screenshots 写到 agent/debug/ 而非归一化目录; 同时
                # game_account_id / resource_pack 丢失, agent 无法绑定资源.
                "debug_dir": data.get("debug_dir", ""),
                "debug_mode": data.get("debug_mode", False),
                "game_account_id": data.get("game_account_id"),
                "game_account_name": data.get("game_account_name"),
                "resource_pack": data.get("resource_pack"),
                "start_step_index": data.get("start_step_index", 0),
                "previous_results": data.get("previous_results"),
            },
        )
        await self.send(text_data=frame)

    async def task_cancel(self, event):
        """接收 Celery/Channel 分发的任务取消指令，转发给 Agent WebSocket 客户端"""
        data = event.get("payload", {})
        logger.info(
            "向 Agent 发送取消指令: agent_id=%s, execution_id=%s",
            self.agent_id,
            data.get("execution_id", ""),
        )
        frame = serialize_frame(
            msg_type=MessageType.TASK_CANCEL,
            payload={
                "execution_id": data.get("execution_id", ""),
                "reason": data.get("reason", "用户取消"),
            },
        )
        await self.send(text_data=frame)

    async def screenshot_stream_control(self, event):
        """Receive frontend screenshot stream control and forward to the Agent.

        The frontend sends `request_screenshot_stream` / `stop_screenshot_stream`
        messages; FrontendConsumer relays them as group events. This method
        re-serializes them into agent protocol frames so the agent can start or
        stop the periodic screenshot capture thread.

        Per-device control (P-004 R37-P2 + TD-014): ``device_ids`` optional
        field lets the frontend request frames for a subset of devices only.
        The frontend sends DB numeric Device.id values; we translate them to
        agent-side device_id strings here so the agent can match its internal
        device registry. None or empty list = all devices (backward compatible).
        """
        data = event.get("payload", {})
        action = data.get("action", "")
        agent_id = data.get("agent_id", self.agent_id)
        device_ids = data.get("device_ids")  # None or [] = all devices

        # TD-014: translate DB Device.id to agent-side device_id strings.
        # The agent constructs device_ids as:
        #   Windows + window_handle → "windows-hwnd-{hwnd}"
        #   Windows + no handle     → "windows-title-{name}"
        #   Emulator                → str(device.id) or adb_serial
        agent_device_ids = None
        if device_ids:
            agent_device_ids = await self._map_db_device_ids_to_agent(device_ids)

        logger.info(
            "[BACKEND->AGENT] 转发截图流控制: agent_id=%s, action=%s, "
            "db_device_ids=%s, agent_device_ids=%s",
            agent_id,
            action,
            device_ids,
            agent_device_ids,
        )
        payload: dict[str, Any] = {"action": action, "agent_id": agent_id}
        if agent_device_ids is not None:
            payload["device_ids"] = agent_device_ids
        elif device_ids is not None:
            # Fallback: pass original DB ids if mapping returned None
            payload["device_ids"] = list(device_ids)
        frame = serialize_frame(
            msg_type=MessageType.SCREENSHOT_CONTROL,
            payload=payload,
        )
        await self.send(text_data=frame)

    async def _map_db_device_ids_to_agent(
        self, db_device_ids: list
    ) -> list[str] | None:
        """Translate DB Device.id values to agent-side device_id strings.

        Delegates to ``protocol.services.map_db_device_ids_to_agent_strings``
        (TD-259 #29: cross-app Agent/Device model imports isolated in
        service). The original implementation made two separate
        ``database_sync_to_async`` round-trips (Agent lookup, then Device
        filter); the service folds both into a single sync block wrapped
        by one ``database_sync_to_async`` call below.

        Args:
            db_device_ids: List of DB Device.id (int or str) from the frontend.

        Returns:
            List of agent device_id strings, or None if the agent is unknown.
            Unknown DB ids are silently skipped (the agent will simply not
            filter on those devices).
        """
        if not self.agent_id:
            return None
        return await database_sync_to_async(map_db_device_ids_to_agent_strings)(
            self.agent_id, db_device_ids,
        )

    async def pipeline_execute(self, event):
        """接收 PipelineViewSet.execute 下发的 Pipeline 执行指令，转发给 Agent。

        Channels 把 group_send 的 ``{'type': 'pipeline.execute'}`` 路由到本方法
        （点号 → 下划线）。若本方法缺失，消息会被 Channels 静默丢弃，Agent 永远
        收不到 Pipeline 执行指令，TaskExecution 会一直停留在 pending。

        Args:
            event: group_send 事件，payload/data 字段携带 task_data
                （execution_id / task_id / task_name / pipeline_id / graph_data /
                 device_id / device_info）

        Note:
            ``device_info`` MUST be forwarded to the agent. The agent's
            ``handle_pipeline_execute`` uses it to resolve the target device
            (by window_title / name / hwnd for Windows, by adb_serial for
            emulators) and set it active before running the pipeline. Without
            device_info the agent falls back to whatever device happens to be
            active in DeviceManager — which was a disconnected LDPlayer ADB
            device when the user targeted the BrownDust II window. Dropping
            the key here silently defeated the backend's device_info fix.
        """
        data = event.get("payload", {})
        logger.info(
            "向 Agent 分发 Pipeline: agent_id=%s, execution_id=%s, pipeline_id=%s, device_id=%s, has_device_info=%s",
            self.agent_id,
            data.get("execution_id", ""),
            data.get("pipeline_id", ""),
            data.get("device_id"),
            bool(data.get("device_info")),
        )
        frame = serialize_frame(
            msg_type=MessageType.PIPELINE_EXECUTE,
            payload={
                "execution_id": data.get("execution_id", ""),
                "task_id": data.get("task_id", ""),
                "task_name": data.get("task_name", ""),
                "pipeline_id": data.get("pipeline_id", ""),
                "graph_data": data.get("graph_data", {}),
                "device_id": data.get("device_id"),
                "device_info": data.get("device_info"),
                "debug_mode": data.get("debug_mode", False),
                "debug_dir": data.get("debug_dir", ""),
                "wait_when_background": data.get("wait_when_background", {}),
            },
        )
        await self.send(text_data=frame)

    async def device_command(self, event):
        """接收恢复引擎 device.command 下发的命令，转发给 Agent。

        Channels 把 group_send 的 ``{'type': 'device.command'}`` 路由到
        本方法（点号 → 下划线）。若本方法缺失，消息会被 Channels 静默
        丢弃 — 恢复动作（restart_app / relogin / restart_emulator 等）
        报告 success 但 Agent 永远收不到命令（S2 评估发现的死代码路径，
        与 ``pipeline_execute`` 相同的失败模式）。

        Args:
            event: group_send 事件，payload 携带 command / target_id /
                config（由 scheduler/recovery_engine._action_device_command
                构造）。
        """
        payload = event.get("payload", {})
        command = payload.get("command", "")
        logger.info(
            "向 Agent 下发设备恢复命令: agent_id=%s, command=%s, target_id=%s",
            self.agent_id,
            command,
            payload.get("target_id"),
        )
        frame = serialize_frame(
            msg_type=MessageType.DEVICE_COMMAND,
            payload=payload,
        )
        await self.send(text_data=frame)

    async def monitor_rule_update(self, event):
        """Forward monitor rule hot-update to the connected Agent.

        Channels routes ``group_send({'type': 'monitor.rule.update'})`` to
        this method (dot → underscore). If this method is missing the message
        is silently dropped — same failure mode as ``pipeline_execute``
        documented above. The agent's ``handle_monitor_rule_update`` receives
        the frame and calls ``MonitorManager.update_rules(rules)`` to swap
        the active rule set without restarting the agent process.

        Args:
            event: group_send event; ``payload``/``data`` carries ``rules``
                (list of serialized MonitorRule dicts) and optional
                ``agent_id`` for logging.
        """
        data = event.get("payload", {})
        rules = data.get("rules", [])
        logger.info(
            "向 Agent 推送监控规则热更新: agent_id=%s, rules=%d",
            self.agent_id,
            len(rules),
        )
        frame = serialize_frame(
            msg_type=MessageType.MONITOR_RULE_UPDATE,
            payload={"rules": rules},
        )
        await self.send(text_data=frame)

    async def _handle_event_alert(self, frame):
        """Handle event.alert frames (protocol reserved, no agent sender yet).

        TD-134 (2026-07-18): The agent (agent/src/) has no send_message call
        for 'event.alert' — the protocol reserves this msg_type for future
        monitor alerting, but no agent-side sender is wired. Handler kept
        to avoid KeyError in handler_map dispatch and to log unexpected
        frames if a future agent version starts sending them.

        Args:
            frame: validated message frame
        """
        logger.info("事件告警 (protocol reserved, no agent sender): agent_id=%s, trace_id=%s", self.agent_id, frame["trace_id"])

    async def _handle_event_ack(self, frame):
        """Handle event.ack frames from the agent (S1 dispatch acknowledgment).

        S1 (2026-08-16): previously an intentional no-op — the agent never
        sent event.ack upstream. Now the agent acknowledges task.dispatch
        receipt immediately upon handling the assign frame, so the backend
        can distinguish "dispatch frame delivered + accepted" from "frame
        silently dropped" (group_send has no queue/ack, so a healthy agent
        whose dispatch frame was lost would leave the execution RUNNING
        forever).

        Supported ack_types:
        - ``task.dispatch``: agent received the task.assign/task.dispatch
          frame. Persist ``dispatch_ack_at`` into execution_snapshot; the
          ``check_dispatch_acks`` beat task uses it to stop re-dispatching.
        - other ack_types (heartbeat/progress/result acks from legacy
          flows): debug-level logging only, unchanged behavior.

        Args:
            frame: validated message frame; payload carries
                ``{"ack_type": "...", "execution_id": "..."}``
        """
        payload = frame.get("payload", {})
        ack_type = payload.get("ack_type", "")
        if ack_type == "task.dispatch":
            await self._record_dispatch_ack(
                execution_id=payload.get("execution_id", ""),
            )
            return
        logger.debug(
            "事件确认 (legacy ack_type=%s, no-op): trace_id=%s",
            ack_type, frame.get("trace_id", ""),
        )

    @database_sync_to_async
    def _record_dispatch_ack(self, *, execution_id):
        """Persist dispatch_ack_at into TaskExecution.execution_snapshot (S1).

        Called when the agent acknowledges receipt of a task.dispatch frame.
        The ``check_dispatch_acks`` beat task scans RUNNING executions with
        dispatch_sent_at set but dispatch_ack_at missing — once this lands,
        the execution is excluded from re-dispatch / fail sweeps.

        Non-fatal: unknown execution_id / already-terminal states are
        logged and swallowed.
        """
        if not execution_id:
            return
        from tasks.models import TaskExecution

        try:
            execution = TaskExecution.objects.get(pk=execution_id)
        except (TaskExecution.DoesNotExist, ValueError, TypeError):
            logger.warning(
                "event.ack(task.dispatch): execution_id=%s 不存在或无效, 忽略",
                execution_id,
            )
            return
        snap = dict(execution.execution_snapshot or {})
        snap["dispatch_ack_at"] = django_timezone.now().isoformat()
        execution.execution_snapshot = snap
        execution.save(update_fields=["execution_snapshot"])
        logger.info(
            "Dispatch ACK recorded: execution_id=%s, attempts=%s",
            execution_id, snap.get("dispatch_attempts"),
        )

    async def _handle_hello(self, frame):
        """Handle agent Hello frame: negotiate compression + send Hello.ack (spec-42).

        Agent sends this frame right after WS connect to advertise supported
        compression algorithms + threshold. Server picks one (currently only
        "msgpack+zlib" is supported on server side) and responds with Hello.ack.
        If the agent's advertised algorithms don't intersect with server-supported
        ones, server sends enabled=False and the connection falls back to JSON
        text_data end-to-end.

        Per the spec-42 wire contract, Hello/Hello.ack frames themselves are
        always JSON text_data — compression kicks in only for subsequent
        large frames (>= threshold bytes). This keeps the negotiation
        self-describing: an agent that has not yet negotiated can still
        parse the Hello.ack response and decide whether to switch modes.

        Args:
            frame: validated Hello frame; payload carries
                ``{"compression": {"algorithms": [...], "threshold": N}}``
        """
        try:
            algorithms, threshold = parse_hello_capabilities(frame)
        except HelloFrameError as e:
            logger.warning("Hello frame parse failed: %s", e)
            error_frame = build_error_frame(
                f"Hello 帧解析失败: {e}",
                trace_id=str(frame.get("trace_id", "")),
            )
            await self.send(text_data=error_frame)
            return

        # Pick the algorithm. Only "msgpack+zlib" is supported on server side.
        if COMPRESSION_ALGORITHM_MSGPACK_ZLIB in algorithms:
            selected = COMPRESSION_ALGORITHM_MSGPACK_ZLIB
        else:
            # Decline: agent must fall back to JSON text_data for all
            # subsequent frames. We still respond with Hello.ack so the
            # agent knows the server understood the Hello (vs. silently
            # dropping it).
            logger.info(
                "Compression negotiation declined: agent_algos=%s, server_supported=[%s]",
                algorithms,
                COMPRESSION_ALGORITHM_MSGPACK_ZLIB,
            )
            ack_frame = build_hello_ack_frame(
                algorithm=algorithms[0] if algorithms else "",
                threshold=threshold,
                enabled=False,
                trace_id=frame.get("trace_id"),
                seq=frame.get("seq", 1),
            )
            await self.send(text_data=json.dumps(ack_frame))
            return

        # Accept: build Hello.ack and send it BEFORE flipping
        # _compression_negotiated = True. The send() override compresses
        # frames when negotiated + size >= threshold, but Hello.ack must
        # arrive as JSON text_data so the agent can decode it before its
        # own compressor is initialized. Reversing this order (set
        # negotiated → send ack) would compress the ack when threshold is
        # small, breaking negotiation.
        ack_frame = build_hello_ack_frame(
            algorithm=selected,
            threshold=threshold,
            enabled=True,
            trace_id=frame.get("trace_id"),
            seq=frame.get("seq", 1),
        )
        # Hello.ack itself is always JSON text_data (small control frame,
        # and the agent must parse it before switching to compressed mode).
        await self.send(text_data=json.dumps(ack_frame))

        # Now flip negotiation state. From this point on, send() will
        # switch large frames to bytes_data and receive() will accept
        # compressed bytes_data from the agent.
        self._compressor = MessageCompressor(
            compress_threshold=threshold,
            use_msgpack=True,
        )
        self._compression_negotiated = True
        logger.info(
            "Compression negotiated: agent_id=%s, algorithm=%s, threshold=%d",
            self.agent_id,
            selected,
            threshold,
        )

    async def send(self, text_data=None, bytes_data=None):
        """Override send to apply compression when negotiated + frame is large (spec-42).

        Wire contract:
        - Compression NOT negotiated → pass through (JSON text_data, legacy).
        - Compression IS negotiated:
          - Small frames (text_data length < threshold) → still JSON text_data
            (avoid zlib + envelope overhead for control frames like heartbeat).
          - Large frames (text_data length >= threshold) → compressed wire
            bytes_data via MessageCompressor.compress().

        Falls back to text_data on compress failure (logged) so a transient
        compressor error never breaks the WS connection.

        Args:
            text_data: JSON-serialized frame string (from serialize_frame).
            bytes_data: Raw bytes (passed through unchanged; used by tests).
        """
        # spec 2026-08-29-logging-system-consolidation P1-1: 记录 outbound 帧
        if PROTOCOL_FRAME_LOG_ENABLED and text_data is not None:
            try:
                out_frame = json.loads(text_data)
                await self._log_frame(str(out_frame.get("type", "unknown")), "outbound", out_frame)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.debug("outbound 帧无法解析, 跳过记录: %s", exc)

        if (
            text_data is not None
            and self._compression_negotiated
            and self._compressor is not None
            and len(text_data) >= self._compressor.compress_threshold
        ):
            try:
                frame_dict = json.loads(text_data)
                wire_bytes = self._compressor.compress(frame_dict)
                await super().send(bytes_data=wire_bytes)
                return
            except (json.JSONDecodeError, MessageCompressorError) as e:
                logger.warning(
                    "Compressed send failed, falling back to text_data: %s", e,
                )
                # Fall through to default text_data send.
        await super().send(text_data=text_data, bytes_data=bytes_data)

    async def _log_frame(self, message_type: str, direction: str, frame: dict) -> None:
        """写消息帧日志 (best-effort: 失败仅 debug, 不阻塞消息处理).

        spec 2026-08-29-logging-system-consolidation P1-1. 截图/大 payload 帧
        只记元信息; 普通帧 payload 截断到 _FRAME_LOG_MAX_PAYLOAD_CHARS.
        """
        try:
            from protocol.models import MessageFrameLog

            payload = _normalize_frame_payload(message_type, frame)

            trace_id_val = frame.get("trace_id")
            await database_sync_to_async(MessageFrameLog.objects.create)(
                message_type=message_type[:50],
                direction=direction,
                trace_id=trace_id_val or None,
                payload=payload,
                agent_session_id=self._agent_session_id or None,
            )
        except Exception as exc:
            logger.debug("消息帧日志写入失败 (忽略): %s", exc)

    async def _handle_llm_call(self, frame):
        """Handle LLM call from agent via WebSocket RPC (Task 2.1).

        The agent sends ``llm.call`` frames to delegate LLM requests to the
        backend's ``LLMRouter`` (4-level fallback chain). This avoids the
        agent needing its own LLM provider configs and lets it benefit from
        the preferred → backup → local → offline fallback.

        Request payload (from agent):
            ``{"messages": [...], "model": "deepseek-chat",
              "temperature": 0.7, "max_tokens": 4096}``

        Response (``llm.result``, server → agent):
            ``{"status": "success", "content": "...", "model": "...",
              "usage": {"input_tokens": N, "output_tokens": N},
              "route": "preferred"}``

        On error:
            ``{"status": "error", "error": "message"}``

        Args:
            frame: Validated message frame with ``payload`` containing
                ``messages``, optional ``model`` / ``temperature`` /
                ``max_tokens``.
        """
        payload = frame.get("payload", {})
        messages = payload.get("messages", [])
        model = payload.get("model")
        temperature = payload.get("temperature", 0.7)
        max_tokens = payload.get("max_tokens", 4096)
        request_id = frame.get("trace_id", frame.get("seq", ""))

        if not messages:
            error_payload = {
                "status": "error",
                "error": "llm.call: 'messages' is required",
            }
            await self._send_llm_result(request_id, error_payload)
            return

        try:
            # Delegate to the backend's LLM service (call_llm uses LLMRouter
            # with 4-level fallback). Run in thread pool to avoid blocking
            # the async event loop (LLM calls can take 5-30s).
            from gaf_ai.llm_service import call_llm

            def _sync_call():
                return call_llm(
                    messages=messages,
                    model=model or "gpt-4o-mini",
                    temperature=float(temperature),
                    max_tokens=int(max_tokens),
                )

            result = await asyncio.get_event_loop().run_in_executor(None, _sync_call)

            response_payload = {
                "status": "success",
                "content": result.get("content", ""),
                "model": result.get("model", model or "gpt-4o-mini"),
                "usage": {
                    "input_tokens": result.get("input_tokens", 0),
                    "output_tokens": result.get("output_tokens", 0),
                },
                "route": result.get("route", "unknown"),
            }
            await self._send_llm_result(request_id, response_payload)

        except Exception as exc:
            logger.exception(
                "LLM call via WS RPC failed: agent_id=%s, request_id=%s",
                self.agent_id, request_id,
            )
            error_payload = {
                "status": "error",
                "error": f"LLM call failed: {exc}",
            }
            await self._send_llm_result(request_id, error_payload)

    async def _send_llm_result(self, request_id: str, payload: dict) -> None:
        """Send an ``llm.result`` frame back to the agent.

        Args:
            request_id: Trace ID or seq from the original request frame.
            payload: Response payload dict (status, content, etc.).
        """
        frame = serialize_frame(
            msg_type=MessageType.LLM_RESULT,
            payload={
                "request_id": request_id,
                **payload,
            },
        )
        await self.send(text_data=frame)

    async def _handle_unknown(self, frame):
        """处理未知类型的消息帧，返回错误。

        Args:
            frame: 已校验的消息帧
        """
        logger.warning("未知消息类型: type=%s, trace_id=%s", frame["type"], frame["trace_id"])
        error_frame = build_error_frame(
            f"未知消息类型: {frame['type']}",
            trace_id=str(frame.get("trace_id", "")),
        )
        await self.send(text_data=error_frame)

    async def _heartbeat_checker(self):
        """后台心跳超时检测任务：15s 警告 / 30s 标记离线。

        每 HEARTBEAT_CHECK_INTERVAL 秒检查一次，
        若距最后心跳超过阈值则分别记录警告或更新数据库状态。
        """
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL)
                if self.agent_id is None or self._last_heartbeat is None:
                    continue

                # spec P4: 僵尸自愈 — 若 active_channel 已不是自己, 说明已被
                # 新连接接管, 立即取消本任务 (不依赖 disconnect 触发清理).
                still_owner = await self._db_am_i_active_owner()
                if not still_owner:
                    logger.info(
                        "Agent active_channel 已被新连接接管 (曾属 %s), 僵尸 checker 自愈退出",
                        self.agent_id,
                    )
                    return

                elapsed = time.time() - self._last_heartbeat
                if elapsed > HEARTBEAT_OFFLINE_SECONDS:
                    logger.warning(
                        "Agent 心跳超时 %ds，标记为离线: agent_id=%s",
                        int(elapsed),
                        self.agent_id,
                    )
                    await self._db_set_agent_offline(self.agent_id)
                elif elapsed > HEARTBEAT_WARNING_SECONDS:
                    logger.warning(
                        "Agent 心跳超时 %ds，进入警告状态: agent_id=%s",
                        int(elapsed),
                        self.agent_id,
                    )
        except asyncio.CancelledError:
            logger.debug("心跳检测任务已取消: agent_id=%s", self.agent_id)

    @database_sync_to_async
    def _db_create_or_update_agent(self, payload):
        """在数据库中创建或更新 Agent 与 AgentSession 记录，含能力声明与资源配额。

        Delegates to ``protocol.services.update_or_create_agent_with_session``
        (TD-259 #29: cross-app Agent model import isolated in service;
        AgentSession is a local protocol model imported inline inside
        the service for cohesion).

        Args:
            payload: 注册消息负载，包含 agent_id / capabilities / resource_quota 等

        Returns:
            str: AgentSession 的 UUID 字符串
        """
        return update_or_create_agent_with_session(self.agent_id, payload)

    @database_sync_to_async
    def _db_claim_active_channel(self) -> bool:
        """spec P4: 原子接管 agent 所有权 (active_channel = 自身 channel).

        新连接无条件接管 — 它总是比旧连接新. 被覆盖的旧连接其后续心跳/离线
        写入均因 active_channel 不匹配而失效 (见 update_agent_heartbeat /
        set_agent_offline 的 channel 守卫).

        若 Agent 记录尚不存在 (首次连接 / 测试用 MagicMock scope), 返回 True
        放行 — 记录由后续 register/心跳路径创建并接管.
        """
        from agents.models import Agent

        exists = Agent.objects.filter(agent_id=self.agent_id).exists()
        if exists:
            Agent.objects.filter(agent_id=self.agent_id).update(
                active_channel=self.channel_name,
                status=Agent.Status.ONLINE,
                last_heartbeat=django_timezone.now(),
            )
        # 记录不存在 → 只是没得接管, 放行 (测试/首次连接, 后续 register 会 create)
        return True

    @database_sync_to_async
    def _db_am_i_active_owner(self) -> bool:
        """spec P4: 查询 DB 确认自己仍是 agent 的现任 active_channel."""
        from agents.models import Agent

        return (
            Agent.objects.filter(
                agent_id=self.agent_id,
                active_channel=self.channel_name,
            ).exists()
        )

    @database_sync_to_async
    def _db_update_heartbeat(self, agent_id, payload):
        """更新 Agent 心跳时间和资源统计。

        Delegates to ``protocol.services.update_agent_heartbeat``
        (TD-259 #29: cross-app Agent model import isolated in service).
        spec P4: 传入当前 channel, 僵尸连接的心跳 UPDATE 被 active_channel 校验挡住.

        Args:
            agent_id: Agent 唯一标识
            payload: 心跳消息负载，包含 resource_stats / status 等
        """
        update_agent_heartbeat(agent_id, payload, channel=self.channel_name)

    @database_sync_to_async
    def _db_update_agent_session_resource(self, session_id, stats):
        """更新 AgentSession 的资源使用字段（cpu_usage / memory_usage / screenshot_fps）。

        Args:
            session_id: AgentSession 的 UUID 字符串
            stats: 资源统计数据，包含 cpu / memory / fps 键
        """
        cpu = stats.get("cpu")
        memory = stats.get("memory")
        fps = stats.get("fps")

        update_fields = {
            "last_heartbeat": django_timezone.now(),
        }
        if cpu is not None and cpu >= 0:
            update_fields["cpu_usage"] = cpu
        if memory is not None and memory >= 0:
            update_fields["memory_usage"] = memory
        if fps is not None and fps >= 0:
            update_fields["screenshot_fps"] = fps

        try:
            AgentSession.objects.filter(agent_id=session_id).update(**update_fields)
        except Exception as exc:
            logger.warning("更新 AgentSession 资源字段失败: session_id=%s, err=%s", session_id, exc)

    @database_sync_to_async
    def _db_get_agent_session(self, session_id):
        """从数据库获取 AgentSession 实例。

        Args:
            session_id: AgentSession 的 UUID 字符串

        Returns:
            AgentSession 实例，若不存在返回 None
        """
        try:
            return AgentSession.objects.filter(agent_id=session_id).first()
        except Exception as exc:
            logger.warning("获取 AgentSession 失败: session_id=%s, err=%s", session_id, exc)
            return None

    @database_sync_to_async
    def _db_register_device(self, device_data):
        """根据 Agent 上报的设备信息创建或更新 Device 记录。

        Delegates to ``protocol.services.register_agent_device``
        (TD-259 #29: cross-app Agent/Device model imports isolated in
        service; ``agents.game_binding.bind_game_profile_by_title`` also
        moved into the service so the consumer no longer imports it).

        优先级: adb_serial > window_handle > name 前缀匹配。
        避免同一设备被重复创建。

        Args:
            device_data: 设备信息字典，包含 name/device_type/adb_serial/window_handle 等

        Returns:
            dict: {id, created, updated}
        """
        return register_agent_device(self.agent_id, device_data)

    @database_sync_to_async
    def _db_set_agent_offline(self, agent_id):
        """将指定 Agent 标记为离线。

        Delegates to ``protocol.services.set_agent_offline``
        (TD-259 #29: cross-app Agent model import isolated in service).
        spec P4: 仅当前连接 (channel) 是 agent 现任 owner 时才生效 —
        僵尸连接的离线写入被 service 内 active_channel 校验拦截.

        Args:
            agent_id: Agent 唯一标识
        """
        set_agent_offline(agent_id, channel=self.channel_name)


class FrontendConsumer(JWTAuthMixin, AsyncWebsocketConsumer):
    """前端 Dashboard WebSocket 消费者
    浏览器前端连接到 WS，监听 dashboard 组的广播消息（心跳/状态变更/截图帧）
    前端 WS 路径: /ws/

    鉴权 (C6 修复): connect() 中解析 query string 的 ``token`` 参数，
    校验 SimpleJWT Access Token。Token 无效或缺失时关闭连接 (code=4003)。
    """

    async def connect(self):
        # C6+C8 fix: verify JWT access token before accepting.
        user = await self._authenticate()
        if user is None:
            await self.close(code=self.WS_CLOSE_CODE_AUTH_FAILED)
            return

        self.user = user
        # Join the dashboard broadcast group. spec-29a #30: legacy "clients"
        # group membership removed — all backend senders now broadcast to
        # DASHBOARD_GROUP (defined in protocol.constants). The legacy
        # /ws/clients/ route (ClientConsumer in agents/consumers.py) is dead
        # code scheduled for spec-29c removal.
        self.group_name = DASHBOARD_GROUP
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        # C8: echo the requested subprotocol so the browser accepts the handshake.
        subprotocols = self.scope.get("subprotocols", [])
        chosen = subprotocols[0] if subprotocols else None
        await self.accept(subprotocol=chosen)
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.CONNECTED,
                    "trace_id": current_trace_id.get() or "",
                    "payload": {"status": "ok", "group": self.group_name},
                }
            )
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """Handle messages coming from the browser (e.g., screenshot stream control).

        The frontend uses this channel to ask the backend to relay control
        commands to the agent. Keep this lightweight — business logic stays in
        the agent.
        """
        if text_data is None:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            logger.warning("FrontendConsumer 收到无效 JSON")
            return

        msg_type = data.get("type", "")
        payload = data.get("payload", {})
        agent_id = payload.get("agent_id", "")

        # L10: reply to the frontend's application-level ping so its heartbeat
        # sees a live pong. Without this the frontend counts 2 missed pongs
        # (~75s) and force-closes the socket, causing a reconnect loop.
        if msg_type == "ping":
            await self.send(
                text_data=json.dumps(
                    {"type": "pong", "trace_id": current_trace_id.get() or "", "payload": {}}
                )
            )
            return

        if msg_type == "request_screenshot_stream" and agent_id:
            device_ids = payload.get("device_ids")  # None or [] = all devices
            logger.info(
                "[BACKEND] 收到截图流开启请求: agent_id=%s, device_ids=%s, channel=%s",
                agent_id,
                device_ids,
                self.channel_name,
            )
            start_payload: dict[str, Any] = {"action": "start", "agent_id": agent_id}
            if device_ids is not None:
                start_payload["device_ids"] = list(device_ids)
            await self.channel_layer.group_send(
                f"agent_{agent_id}",
                {
                    "type": FrontendEventType.SCREENSHOT_STREAM_CONTROL,
                    "payload": start_payload,
                },
            )
        elif msg_type == "stop_screenshot_stream" and agent_id:
            logger.info(
                "[BACKEND] 收到截图流停止请求: agent_id=%s, channel=%s",
                agent_id,
                self.channel_name,
            )
            await self.channel_layer.group_send(
                f"agent_{agent_id}",
                {
                    "type": FrontendEventType.SCREENSHOT_STREAM_CONTROL,
                    "payload": {"action": "stop", "agent_id": agent_id},
                },
            )

    async def agent_heartbeat(self, event):
        # H25 fix: use canonical `payload` with legacy `data` fallback.
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.AGENT_HEARTBEAT,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )

    async def agent_status(self, event):
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.AGENT_STATUS,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )

    async def device_status(self, event):
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.DEVICE_STATUS,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )

    async def screenshot_frame(self, event):
        """Broadcast screenshot frame to frontend dashboard clients.

        Args:
            event: Contains device_id, image_base64, width, height, captured_at
        """
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.SCREENSHOT_FRAME,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )

    async def execution_step_update(self, event):
        """Forward single-step progress updates to the frontend (P3-2).

        The ExecutionStep post_save signal broadcasts to the "dashboard"
        group so the ExecutionMonitorPanel can upsert step status in real
        time without polling the REST endpoint.
        """
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.EXECUTION_STEP_UPDATE,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )

    async def execution_log(self, event):
        """Forward real-time execution logs to the frontend.

        AgentConsumer converts task.progress / task.result / log_stream
        frames into execution_log group messages; FrontendConsumer echoes
        them to browser clients so the ExecutionMonitorPanel log terminal
        is populated.
        """
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.EXECUTION_LOG,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )

    async def device_updated(self, event):
        """Forward device field updates to the frontend dashboard.

        agents/signals.py broadcasts device.updated to the "clients" group;
        FrontendConsumer joins that group so the browser wsClient receives
        these events and useDeviceStore refetches the device list.
        """
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.DEVICE_UPDATED,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )

    async def device_metrics_updated(self, event):
        """Forward screenshot test metrics updates to the frontend."""
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.DEVICE_METRICS_UPDATED,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )

    async def device_registered(self, event):
        """Forward device registration/update events to the frontend."""
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.DEVICE_REGISTERED,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )

    async def device_capabilities_updated(self, event):
        """Forward available_methods cache refresh events to the frontend."""
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.DEVICE_CAPABILITIES_UPDATED,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )


class LogStreamConsumer(JWTAuthMixin, AsyncWebsocketConsumer):
    """Real-time log stream WebSocket consumer for the LogCenterPage frontend.

    Mounted at ``/ws/logs/``. Browser clients connect with a JWT access token
    (via subprotocol ``access.<jwt>`` or ``?token=`` query string) and
    receive a push for every new ``LogEntry`` record written by
    ``DatabaseLogHandler`` via ``group_send`` to ``LOGS_GROUP``.

    Lifecycle:
      connect → JWT auth → join ``LOGS_GROUP`` → receive ``log.entry`` events
      → echo to browser → disconnect leaves group.

    The consumer is read-only: it does not accept any incoming messages from
    the browser. All log records originate server-side.
    """

    async def connect(self):
        user = await self._authenticate()
        if user is None:
            await self.close(code=self.WS_CLOSE_CODE_AUTH_FAILED)
            return
        self.user = user
        self.group_name = LOGS_GROUP
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        # Echo the requested subprotocol so browser clients complete the
        # handshake (mirrors FrontendConsumer.connect behavior).
        subprotocols = self.scope.get("subprotocols", [])
        chosen = subprotocols[0] if subprotocols else None
        await self.accept(subprotocol=chosen)
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.CONNECTED,
                    "trace_id": current_trace_id.get() or "",
                    "payload": {"status": "ok", "group": self.group_name},
                }
            )
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """No-op: LogStreamConsumer is read-only.

        Browser clients cannot inject log entries via this socket — all
        records must originate from an authenticated Agent connection or
        the server-side ``DatabaseLogHandler``. Silently ignore any inbound
        traffic to keep the connection alive.
        """
        return

    async def log_entry(self, event):
        """Echo a new LogEntry to all connected LogCenterPage clients.

        Channels routes ``group_send({'type': 'log.entry'})`` to this method.
        The payload is the LogEntry dict produced by
        ``AgentConsumer._db_write_log_entry``.
        """
        payload = event.get("payload") or {}
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.LOG_ENTRY,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )
