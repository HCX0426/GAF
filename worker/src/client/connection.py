"""WebSocket 客户端：管理与 Server 的连接，支持 TLS/wss://"""

import asyncio
import dataclasses
import inspect
import json
import logging
import os
import socket
import ssl
import threading
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

import websockets
from core.config import WorkerConfig
from core.constants import ServerStatus
from core.context_vars import current_user_trace_id
from core.retry import NETWORK_RETRY_EXCEPTIONS, retry_network
from monitor.resources import ResourceMonitor
from utils.message_compressor import (
    COMPRESSION_ALGORITHM_MSGPACK_ZLIB,
    DEFAULT_COMPRESS_THRESHOLD,
    HelloFrameError,
    MessageCompressor,
    MessageCompressorError,
    build_hello_frame,
    parse_hello_ack_capabilities,
)
from websockets.asyncio.client import connect as ws_connect

logger = logging.getLogger(__name__)

# A3 (spec 2026-07-30-debug-directory-restructure): 缓存 handler 方法签名
# 是否接受 trace_id 参数, 避免 _dispatch_to_handler 每次都调 inspect.signature.
_TRACE_ID_SIG_CACHE: dict[int, bool] = {}


def _accepts_trace_id_kwarg(method) -> bool:
    """检测 handler 方法是否接受 ``trace_id`` 关键字参数.

    A3: ``_dispatch_to_handler`` 从 WS 帧顶层提取 trace_id 后, 需判断 handler
    方法签名是否接受 ``trace_id`` 参数. 支持 ``**kwargs`` 的方法也视为接受.
    结果缓存到 ``_TRACE_ID_SIG_CACHE`` 避免重复反射开销.
    """
    method_id = id(method)
    cached = _TRACE_ID_SIG_CACHE.get(method_id)
    if cached is not None:
        return cached
    result = False
    try:
        sig = inspect.signature(method)
    except (ValueError, TypeError):
        result = False
    else:
        for name, param in sig.parameters.items():
            if name == "trace_id":
                result = True
                break
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                result = True
                break
    _TRACE_ID_SIG_CACHE[method_id] = result
    return result


MAX_BACKOFF = 30

# WebSocket ping 间隔，保持连接检测
PING_INTERVAL = 20
PING_TIMEOUT = 10

# spec-42: how long to wait for the server's Hello.ack before giving up
# and falling back to JSON text_data. The server usually responds within
# milliseconds; 2s is a generous upper bound that still keeps connect()
# snappy when the server is a legacy build that doesn't implement the
# negotiation protocol.
HELLO_ACK_TIMEOUT = 2.0

# S1 (2026-08-16): 出站队列上限 — 断线期间积压的上行帧 (task.result /
# task.progress / event.ack 等) 在重连后重放. 上限 50 防内存膨胀;
# 满时丢弃最旧的 (task.progress 可丢, 但 task.result 在任务结束才发,
# 通常位于队列尾部, 不会被挤出).
OUTBOX_MAX_SIZE = 50


def _serialize_for_json(obj: Any) -> Any:
    """Recursively convert non-JSON-native types to plain dicts/lists for JSON.

    Pipeline/task results often contain nested ``AutoResult`` dataclasses in
    ``result.data``. Without this conversion ``json.dumps`` raises
    ``TypeError: Object of type AutoResult is not JSON serializable`` and the
    ``task.result`` frame is silently dropped.

    Also handles numpy ``ndarray`` / scalar types (TD-016 fix): screenshot
    recognition results may embed numpy arrays (e.g. pixel ROI). Without
    explicit handling the ``default=str`` fallback in ``send_message`` would
    stringify the array into a multi-KB ``[[[42 38 38]...]]`` repr that
    bloats the WS frame and corrupts ``result_data`` rendering on the
    frontend. Numpy is imported lazily inside the branch so the module
    loads even when numpy is absent.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        # Use ``dataclasses.fields`` + manual recursion instead of
        # ``dataclasses.asdict`` because ``asdict`` leaves non-dataclass
        # values (e.g. numpy arrays) untouched, bypassing the ndarray
        # branch below and re-introducing the TD-016 ``default=str`` bloat.
        return {f.name: _serialize_for_json(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_for_json(v) for v in obj]
    # Numpy support (TD-016): import lazily so the module loads without numpy.
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is a hard dep for the agent
        np = None
    if np is not None:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
    return obj


def _build_ws_url(base_url: str, token: str) -> str:
    """构建带 Token 查询参数的 WebSocket URL。

    Args:
        base_url: 基础 WebSocket URL
        token: Agent 认证 Token

    Returns:
        str: 拼接 Token 后的完整 WebSocket URL
    """
    if not token:
        return base_url
    parsed = urlparse(base_url)
    query_params = {'token': token}
    new_query = urlencode(query_params)
    return urlunparse(parsed._replace(query=new_query))


class WorkerConnection:
    """管理 Agent 与 Server 之间的 WebSocket 连接，支持自动重连和心跳"""

    def __init__(
        self,
        config: WorkerConfig,
        resource_monitor: ResourceMonitor | None = None,
        outbox_store: Any | None = None,
    ):
        self._config = config
        self._ws = None
        self._connected = False
        self._heartbeat_task = None
        self._heartbeat_thread: threading.Thread | None = None
        self._reconnect_delay = 1.0
        self._resource_monitor = resource_monitor if resource_monitor is not None else ResourceMonitor()
        self._ws_url = _build_ws_url(self._config.server_url, self._config.agent_token)
        self._seq = 0  # 消息序号，单调递增，用于 frame 校验
        # spec-42 compression negotiation state. Stays False for legacy
        # servers that never respond to Hello (or decline with
        # enabled=False) — the agent keeps using JSON text_data end-to-end
        # in that case. Switched to True only after the server confirms
        # with a Hello.ack frame advertising a supported algorithm.
        self._compression_negotiated = False
        self._compressor: MessageCompressor | None = None
        # S1 (2026-08-16): 出站队列 — send_message 在 WS 未连接/未就绪时
        # 把上行帧缓存到队列, 重连成功后按 FIFO 重放. 解决"task.result 在
        # 断线窗口被静默丢弃, backend 执行永久 RUNNING" 缺陷.
        # P3 (2026-08-17): 可选 SQLite 持久化 (outbox_store) — 进程崩溃/重启
        # 后从磁盘恢复积压帧, 断线不丢升级为崩溃也不丢. 未注入 store 时
        # 保持纯内存语义 (行为与 S1 一致).
        self._outbox: deque[tuple[str, dict[str, Any]]] = deque(maxlen=OUTBOX_MAX_SIZE)
        self._outbox_store = outbox_store
        if outbox_store is not None:
            restored = outbox_store.load_all()
            if restored:
                logger.warning(
                    "[AGENT->SERVER][connection] 从持久化 outbox 恢复 %d 帧 (上次进程未完成重放)",
                    len(restored),
                )
                for msg_type, data in restored:
                    self._outbox.append((msg_type, data))

    def _next_seq(self) -> int:
        """原子递增并返回下一个消息序号。"""
        self._seq += 1
        return self._seq

    @property
    def connected(self) -> bool:
        """是否已连接"""
        return self._connected

    def _build_url(self) -> str:
        """构建 WebSocket 连接 URL，附加 Token 参数"""
        url = self._config.server_url
        if self._config.agent_token:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}token={self._config.agent_token}"
        return url

    async def connect(self) -> None:
        """建立 WebSocket 连接并发送注册消息"""
        try:
            self._ws = await ws_connect(
                self._ws_url,
                additional_headers=self._build_headers(),
                ssl=self._build_ssl_context(),
                ping_interval=PING_INTERVAL,
                ping_timeout=PING_TIMEOUT,
            )
            self._connected = True
            self._reconnect_delay = 1.0
            logger.info("已连接到 Server")

            await self._send_register()
            # spec-42: advertise compression capabilities right after
            # register. The server's Hello.ack is handled asynchronously
            # in listen() — until it arrives, send_message() keeps using
            # JSON text_data (the safe fallback for legacy servers).
            await self._send_hello()
        except Exception as exc:
            logger.error("连接 Server 失败: %s", exc)
            await self._try_reconnect()

    async def disconnect(self) -> None:
        """断开 WebSocket 连接"""
        self._connected = False
        # spec-42: reset compression state so a fresh connect() re-negotiates.
        # Without this, a reconnect after disconnect() would skip Hello and
        # the server would never switch to compressed mode for the new WS.
        self._compression_negotiated = False
        self._compressor = None
        # Heartbeat thread is daemon; it exits when _connected becomes False.
        # The previous code referenced self._heartbeat_task which was never
        # assigned (the actual thread is self._heartbeat_thread), making the
        # cancel block dead code.
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("已断开与 Server 的连接")

    @retry_network()
    async def send_message(
        self,
        msg_type: str,
        data: dict[str, Any],
        _enqueue_on_failure: bool = True,
    ) -> None:
        """发送消息到 Server（使用标准 frame 格式: trace_id/type/seq/timestamp/payload）。

        增加了详细的连接状态、消息体大小和发送结果日志，方便排查
        Future 被静默吞掉、backend 没收到 task.result 等问题。

        spec-42 (TD-287): 当压缩协商成功且序列化后字节数 ≥ threshold 时，
        改用 MessageCompressor 走 bytes_data 通道；否则保持 JSON text_data。
        """
        execution_id = data.get("execution_id", "")
        task_id = data.get("task_id", "")
        logger.info(
            "[AGENT->SERVER][connection] 开始发送: msg_type=%s, execution_id=%s, task_id=%s, "
            "ws=%s, connected=%s, thread=%s",
            msg_type, execution_id, task_id,
            self._ws is not None, self._connected,
            threading.current_thread().name,
        )

        if not self._ws:
            logger.error(
                "[AGENT->SERVER][connection] 发送失败: WebSocket 对象为空, msg_type=%s, execution_id=%s",
                msg_type, execution_id,
            )
            if _enqueue_on_failure:
                self._enqueue_outbox(msg_type, data)
            return

        if not self._connected:
            logger.error(
                "[AGENT->SERVER][connection] 发送失败: WebSocket 未连接, msg_type=%s, execution_id=%s",
                msg_type, execution_id,
            )
            if _enqueue_on_failure:
                self._enqueue_outbox(msg_type, data)
            return

        # Convert dataclass results (e.g. nested AutoResult) to plain dicts so
        # ``json.dumps`` does not fail silently and drop task.result frames.
        serializable_payload = _serialize_for_json(data)
        frame_dict = {
            # F19 (spec 2026-07-30-debug-directory-restructure): 优先从
            # ContextVar 取 trace_id (handler 入口 set_current_execution 已设),
            # 为空时降级为新 UUID (agent.heartbeat / agent.register 等无入站帧).
            "trace_id": current_user_trace_id.get() or str(uuid.uuid4()),
            "type": msg_type,
            "seq": self._next_seq(),
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "payload": serializable_payload,
        }
        # 性能计量: 开发模式时附加 sent_at 时间戳, 供 Backend 计算端到端 WebSocket 延迟.
        if os.environ.get("GAF_CELERY_MODE", "eager") != "celery":
            frame_dict["sent_at"] = time.time()
        try:
            message = json.dumps(frame_dict, ensure_ascii=False)
        except TypeError as exc:
            logger.exception(
                "[AGENT->SERVER][connection] JSON 序列化失败: msg_type=%s, execution_id=%s, error=%s. "
                "Falling back to default=str to avoid dropping the frame.",
                msg_type, execution_id, exc,
            )
            try:
                message = json.dumps(frame_dict, ensure_ascii=False, default=str)
            except Exception as fallback_exc:
                logger.exception(
                    "[AGENT->SERVER][connection] JSON 序列化兜底也失败: msg_type=%s, execution_id=%s, error=%s",
                    msg_type, execution_id, fallback_exc,
                )
                return

        message_bytes = message.encode("utf-8")

        # spec-42: pick wire format based on negotiation state + size.
        # When compression is negotiated AND the serialized payload is large
        # enough to benefit from zlib, send through MessageCompressor as
        # binary bytes_data. Otherwise stick with JSON text_data — small
        # control frames (heartbeat, event.ack) avoid zlib overhead, and
        # un-negotiated connections stay on the legacy JSON path.
        use_compression = (
            self._compression_negotiated
            and self._compressor is not None
            and len(message_bytes) >= self._compressor.compress_threshold
        )
        if use_compression:
            try:
                wire_bytes = self._compressor.compress(frame_dict)
            except MessageCompressorError as exc:
                logger.warning(
                    "[AGENT->SERVER][connection] 压缩失败, 回退 JSON: msg_type=%s, error=%s",
                    msg_type, exc,
                )
                wire_bytes = None
        else:
            wire_bytes = None

        wire_kind = "bytes" if wire_bytes is not None else "text"
        wire_size = len(wire_bytes) if wire_bytes is not None else len(message_bytes)
        logger.info(
            "[AGENT->SERVER][connection] 准备调用 ws.send: msg_type=%s, execution_id=%s, "
            "seq=%s, wire=%s, size=%d bytes",
            msg_type, execution_id, self._seq, wire_kind, wire_size,
        )

        try:
            if wire_bytes is not None:
                await self._ws.send(wire_bytes)
            else:
                await self._ws.send(message)
            logger.info(
                "[AGENT->SERVER][connection] 发送成功: msg_type=%s, execution_id=%s, seq=%s, "
                "wire=%s, size=%d bytes",
                msg_type, execution_id, self._seq, wire_kind, wire_size,
            )
        except Exception as exc:
            logger.exception(
                "[AGENT->SERVER][connection] ws.send 异常: msg_type=%s, execution_id=%s, "
                "seq=%s, error=%s, ws_state=%s",
                msg_type, execution_id, self._seq, exc,
                getattr(self._ws, "state", "unknown"),
            )
            # For non-retryable exceptions, mark the connection as
            # disconnected so callers see the state change immediately.
            # For retryable exceptions (ConnectionClosed, etc.), keep
            # _connected=True so @retry_network can re-enter send_message
            # without hitting the "if not self._connected" early-return
            # guard above. After retries are exhausted the exception
            # propagates to the caller, which handles further cleanup.
            if not isinstance(exc, NETWORK_RETRY_EXCEPTIONS):
                self._connected = False
            raise

    def _enqueue_outbox(
        self, msg_type: str, data: dict[str, Any], persist: bool = True
    ) -> None:
        """S1: 缓存一条上行帧到出站队列 (断线期间待重放).

        deque(maxlen=OUTBOX_MAX_SIZE) 满时自动丢弃最旧帧 (通常是
        task.progress, 重放价值低). task.result 在任务结束才发送,
        位于队列尾部, 不会被挤出.

        P3: 注入 outbox_store 时同步落盘; 容量满丢弃最旧帧时同步
        删除持久化最旧行, 保证内存与磁盘队列一致.

        Args:
            msg_type: 消息类型 (task.result / task.progress / event.ack / ...)
            data: 消息 payload dict
            persist: 是否写入持久化 store (flush 中断重新入队时传 False,
                该帧在 store 中已有记录, 避免重复行)
        """
        if len(self._outbox) >= OUTBOX_MAX_SIZE:
            logger.warning(
                "[AGENT->SERVER][connection] 出站队列已满 (%d), 丢弃最旧帧 %s",
                OUTBOX_MAX_SIZE, self._outbox[0][0],
            )
            if self._outbox_store is not None:
                self._outbox_store.delete_first_n(1)
        self._outbox.append((msg_type, data))
        if self._outbox_store is not None and persist:
            self._outbox_store.enqueue(msg_type, data)
        logger.warning(
            "[AGENT->SERVER][connection] 帧 %s 入出站队列 (待重连后重放), 队列长度=%d",
            msg_type, len(self._outbox),
        )

    async def _flush_outbox(self) -> None:
        """S1: 重连成功后按 FIFO 重放出站队列中的帧.

        只重放非心跳帧 (心跳有独立循环, 无需重放). 重放失败时
        记录日志并停止 (等待下一次重连), 不阻塞 listen 主循环.

        P3: 逐条发送成功后累计 sent_count, 结束/中断后按成功帧数
        从持久化 store 删除对应行 (已送达服务端的帧无需保留).
        中断重新入队的帧走内存 append (persist=False, store 行保留),
        下次重连继续重放.
        """
        if not self._outbox:
            return
        if not self._ws or not self._connected:
            logger.warning(
                "[AGENT->SERVER][connection] 重放出站队列失败: 连接未就绪, 保留 %d 帧",
                len(self._outbox),
            )
            return
        pending = list(self._outbox)
        self._outbox.clear()
        logger.info(
            "[AGENT->SERVER][connection] 重连成功, 重放出站队列 %d 帧",
            len(pending),
        )
        sent_count = 0
        for msg_type, data in pending:
            if not self._ws or not self._connected:
                logger.warning(
                    "[AGENT->SERVER][connection] 重放中断: 连接再次断开, 剩余 %d 帧重新入队",
                    len(pending) - sent_count,
                )
                # 剩余帧重新入队, 等待下次重连; 已成功帧从 store 删除
                remaining = pending[sent_count:]
                for m, d in remaining:
                    self._outbox.append((m, d))
                if self._outbox_store is not None and sent_count > 0:
                    self._outbox_store.delete_first_n(sent_count)
                return
            try:
                # _enqueue_on_failure=False: 发送失败时由本函数处理重入队,
                # 避免 send_message 内部重复写 store
                await self.send_message(msg_type, data, _enqueue_on_failure=False)
                sent_count += 1
            except Exception as exc:
                logger.exception(
                    "[AGENT->SERVER][connection] 出站队列重放失败: msg_type=%s, error=%s",
                    msg_type, exc,
                )
        if self._outbox_store is not None and sent_count > 0:
            self._outbox_store.delete_first_n(sent_count)

    async def listen(self, handler) -> None:
        """持续监听 Server 消息并分发给 handler

        Args:
            handler: 消息处理器实例，需实现 handle_task_assign 等方法
        """
        self._loop = asyncio.get_running_loop()
        handler.send_callback = self.send_message
        handler._loop = self._loop
        self.start_heartbeat(interval=self._config.heartbeat_interval)

        while self._connected:
            try:
                if self._ws is None:
                    await self._try_reconnect()
                    if self._ws and self._connected:
                        handler.send_callback = self.send_message
                        self._ensure_heartbeat_running()
                        # S1: 重连成功后重放出站队列 (断线期间积压的
                        # task.result / task.progress / event.ack 帧)
                        await self._flush_outbox()
                    continue

                async for raw_message in self._ws:
                    try:
                        # spec-42: post-negotiation the server may send
                        # compressed bytes_data for large frames. Small
                        # control frames and pre-negotiation traffic stay
                        # as JSON text_data. ``str`` → json.loads; ``bytes``
                        # → MessageCompressor.decompress (only meaningful
                        # when negotiated, but we attempt decompress for
                        # any bytes frame to surface wire-format errors).
                        if isinstance(raw_message, (bytes, bytearray)):
                            if self._compressor is None:
                                logger.warning(
                                    "[SERVER->AGENT][connection] 收到 bytes 帧但协商未完成, 丢弃"
                                )
                                continue
                            try:
                                message = self._compressor.decompress(raw_message)
                            except MessageCompressorError as exc:
                                logger.warning(
                                    "[SERVER->AGENT][connection] 压缩帧解析失败: %s",
                                    exc,
                                )
                                continue
                        else:
                            message = json.loads(raw_message)
                        msg_type = message.get("type", "")
                        trace_id = message.get("trace_id", "")
                        # spec-42: intercept Hello.ack to flip negotiation
                        # state before any other handler runs. This must
                        # happen here (not in _dispatch_to_handler) because
                        # handler_map is for business frames; Hello.ack is
                        # a transport-level control frame.
                        if msg_type == "hello.ack":
                            self._handle_hello_ack(message)
                            continue
                        ack_type = message.get("payload", {}).get("ack_type", "") if isinstance(message.get("payload"), dict) else ""
                        if msg_type == "event.ack":
                            logger.info(
                                "[SERVER->AGENT][connection] 收到 ACK: ack_type=%s, trace_id=%s",
                                ack_type, trace_id,
                            )
                        else:
                            logger.info(
                                "[SERVER->AGENT][connection] 收到消息: type=%s, trace_id=%s",
                                msg_type, trace_id,
                            )
                        self._dispatch_to_handler(message, handler)
                    except json.JSONDecodeError:
                        logger.warning("收到无效 JSON 消息")

            except websockets.ConnectionClosed:
                logger.warning("WebSocket 连接已关闭")
                self._connected = False
                await self._try_reconnect()
                if self._ws and self._connected:
                    handler.send_callback = self.send_message
                    self._ensure_heartbeat_running()
                    # S1: 重连成功后重放出站队列
                    await self._flush_outbox()
            except Exception as exc:
                logger.error("监听消息异常: %s", exc)
                self._connected = False
                await self._try_reconnect()
                if self._ws and self._connected:
                    handler.send_callback = self.send_message
                    self._ensure_heartbeat_running()
                    # S1: 重连成功后重放出站队列
                    await self._flush_outbox()

    def _ensure_heartbeat_running(self) -> None:
        """检查心跳线程状态，已死亡则重新启动"""
        if self._heartbeat_thread is None or not self._heartbeat_thread.is_alive():
            logger.info("心跳线程已退出，重新启动")
            self.start_heartbeat(interval=self._config.heartbeat_interval)

    def start_heartbeat(self, interval: int = 30) -> None:
        """启动心跳线程，每 interval 秒发送携带资源统计数据的心跳消息。

        可重复调用：已有线程运行时忽略（除非线程已退出）。
        重连后通过 _ensure_heartbeat_running 重新启动。

        Args:
            interval: 心跳间隔（秒）
        """
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            logger.debug("心跳线程已在运行中，跳过")
            return

        def _heartbeat_loop():
            while self._connected:
                time.sleep(interval)
                if not self._connected:
                    continue
                try:
                    stats = self._resource_monitor.get_stats()
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self._send_heartbeat(stats),
                            self._loop,
                        )
                except Exception as e:
                    logger.warning("心跳发送失败: %s", e)

        self._heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        logger.info("心跳线程已启动，间隔 %ds", interval)

    async def _send_heartbeat(self, stats) -> None:
        """Send heartbeat without touching _connected (main loop handles reconnection)."""
        if not self._ws or not self._connected:
            return
        message = json.dumps({
            # F34 (spec 2026-07-30-debug-directory-restructure): 从 ContextVar
            # 取 trace_id, 为空时降级为新 UUID. 与 F19 send_message 对称.
            "trace_id": current_user_trace_id.get() or str(uuid.uuid4()),
            "type": "agent.heartbeat",
            "seq": self._next_seq(),
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "payload": {
                "stats": stats,
            },
        }, ensure_ascii=False)
        try:
            await self._ws.send(message)
            logger.debug("已发送心跳: cpu=%.1f%%, mem=%.1f%%, fps=%.1f",
                         stats.get('cpu', -1), stats.get('memory', -1), stats.get('fps', -1))
        except Exception as e:
            logger.debug("heartbeat send failed: %r (main loop handles reconnect)", e)

    def _build_headers(self) -> dict[str, str]:
        """构建 WebSocket 连接请求头，携带 Token 认证信息。

        Returns:
            Dict[str, str]: 包含认证头的字典
        """
        headers = {}
        if self._config.agent_token:
            headers['X-Agent-Token'] = self._config.agent_token
        return headers

    def _build_ssl_context(self) -> ssl.SSLContext | None:
        """根据 WorkerConfig 构建 SSLContext，支持 CA 证书、客户端证书（mTLS）。

        当 server_url 以 wss:// 开头时自动启用 TLS。

        Returns:
            ssl.SSLContext | None: TLS 上下文，未启用 wss 时返回 None
        """
        if not self._config.use_tls:
            return None

        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)

        ca_file = self._config.ssl_ca_file
        if ca_file and Path(ca_file).exists():
            context.load_verify_locations(cafile=ca_file)
            logger.info("已加载 CA 证书: %s", ca_file)

        if not self._config.ssl_verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            logger.warning("TLS 证书验证已禁用（生产环境不推荐）")

        client_cert = self._config.ssl_client_cert_file
        client_key = self._config.ssl_client_key_file
        if client_cert and Path(client_cert).exists():
            logger.info("已加载客户端证书: %s", client_cert)
            context.load_cert_chain(certfile=client_cert, keyfile=client_key)

        return context

    @staticmethod
    def _adb_available() -> bool:
        """Check whether an ADB executable is reachable on this machine.

        Reuses EmulatorDiscovery's path discovery (PATH + common emulator
        install paths). Fast when adb is not on PATH (pure file existence
        check); may spend up to 5s on ``adb version`` when adb is on PATH —
        only happens once at register time.
        """
        try:
            from devices.emulator_discovery import EmulatorDiscovery

            return EmulatorDiscovery._discover_adb_path() is not None
        except Exception:
            return False

    async def _send_register(self) -> None:
        """Send agent registration message to the server with capabilities declared.

        声明能力让 Server 能根据 task_definition 推断的能力匹配合适的 Agent。
        能力集覆盖：screenshot/input/ocr/image_match + windows/adb（按 device_type 开关）。
        """
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            local_ip = "127.0.0.1"

        # 根据 device_type 决定是否声明 adb 能力
        device_type = (self._config.device_type or "").lower()
        is_windows = device_type in ("windows", "window", "win32", "pc")
        is_emulator = device_type in ("emulator", "android", "adb", "emu")

        capabilities = {
            "screenshot": True,
            "input": True,
            "ocr": True,
            "image_match": True,
        }
        if is_windows:
            capabilities["windows"] = True
        if is_emulator:
            capabilities["adb"] = True
        # 2026-09-05: Windows 机器上若检测到 ADB (模拟器), 也声明 adb 能力 —
        # 否则需要 adb 的任务 (模拟器自动化) 永远匹配不到本 agent, 即使机器
        # 上实际有 LDPlayer/雷电等模拟器 (实测: task 22 报"无具备所需能力
        # (adb) 的 Agent", 因 capabilities 仅含 windows).
        if not is_emulator and self._adb_available():
            capabilities["adb"] = True
        # If device_type is unknown, declare both to maximize matching chances
        if not is_windows and not is_emulator:
            capabilities["windows"] = True
            capabilities["adb"] = True

        await self.send_message("agent.register", {
            "device_type": self._config.device_type,
            "version": "0.1.0",
            "hostname": socket.gethostname(),
            "ip_address": local_ip,
            "is_local": True,
            "capabilities": capabilities,
            "resource_quota": {
                "max_concurrent_tasks": 2,
                "max_devices": 4,
            },
        })
        logger.info(
            "已发送注册消息: device_type=%s, ip=%s, capabilities=%s",
            self._config.device_type, local_ip, list(capabilities.keys()),
        )

    async def _sync_devices(self, device_manager) -> None:
        """Sync discovered devices to server after connection established.

        Collects device information from DeviceManager and sends device.sync
        message to server for automatic Device record creation/association.

        Args:
            device_manager: DeviceManager instance containing discovered devices
        """
        if not self._ws or not self._connected:
            logger.warning("无法同步设备：WebSocket 未连接")
            return

        # Collect device info from DeviceManager
        devices_list = []
        if device_manager and hasattr(device_manager, 'list_devices'):
            try:
                all_devs = device_manager.list_devices()
                # No artificial cap on device count — multi-instance scenarios
                # (e.g. 100+ emulator windows) must be fully synced. Previously
                # capped at 50 which silently dropped multi-open windows >50.
                for dev_info in all_devs:
                    dev_id = dev_info.get('device_id', '')
                    if dev_id:
                        dev = device_manager.get_device(dev_id)
                        if dev:
                            # Normalize device_type to values server understands: 'emulator' | 'windows'
                            raw_type = getattr(dev, 'device_type', 'unknown')
                            raw_lower = str(raw_type).lower()
                            # Map agent-side types to server-compatible types
                            if raw_lower in ('windows', 'window', 'win32', 'pc'):
                                normalized_type = 'windows'
                            elif raw_lower in ('emulator', 'android', 'adb', 'emu'):
                                normalized_type = 'emulator'
                            else:
                                # Fallback: detect from class name or device_id
                                dev_class_name = type(dev).__name__.lower()
                                if 'windows' in dev_class_name or 'window' in dev_class_name:
                                    normalized_type = 'windows'
                                elif 'adb' in dev_class_name or 'android' in dev_class_name:
                                    normalized_type = 'emulator'
                                else:
                                    normalized_type = 'emulator'  # Default fallback
                                    logger.debug("未知设备类型 '%s' (device=%s)，默认为 emulator", raw_type, dev_id)

                            # Include window_handle for Windows devices so the
                            # server can de-duplicate by hwnd (authoritative
                            # unique key) instead of falling back to name
                            # prefix matching which mis-merges multi-instance
                            # windows sharing a common title prefix.
                            window_handle = ''
                            # N194 fix: also surface window_title so backend
                            # ``register_agent_device`` can:
                            #   1. Match existing Device by extra_info.window_title
                            #      (priority 2.5, R37-P0) when hwnd is empty
                            #   2. Auto-bind GameProfile via
                            #      ``bind_game_profile_by_title(window_title)``
                            #      so device.game_profile is set without user
                            #      manual configuration
                            #   3. Forward window_title to agent via
                            #      ``_build_device_info_for_execution`` so
                            #      WindowsDevice.connect() can find the window
                            # Without this, Device.extra_info.window_title is
                            # '' and agent falls back to dev.name (e.g.
                            # "BrownDust II") which may not match the actual
                            # OS window title.
                            window_title = ''
                            if normalized_type == 'windows':
                                # WindowsDevice may expose _window_mgr._hwnd
                                # after connect(); device_id encodes hwnd too.
                                hwnd_val = getattr(dev, '_hwnd', None)
                                if hwnd_val is None:
                                    # Try to extract from device_id "windows-hwnd-<int>"
                                    parts = dev_id.split('-')
                                    if len(parts) >= 3 and parts[-2] == 'hwnd':
                                        try:
                                            hwnd_val = int(parts[-1])
                                        except ValueError:
                                            hwnd_val = None
                                if hwnd_val is not None:
                                    window_handle = str(hwnd_val)
                                # _window_title is set by WindowsDevice.connect()
                                # after it locates the OS window. May be None
                                # if device is registered but not yet connected.
                                window_title = getattr(dev, '_window_title', '') or ''

                            # Map agent DeviceStatus to backend-compatible status string
                            dev_status = getattr(dev, 'status', None)
                            if dev_status is not None:
                                status_val = dev_status.value  # DeviceStatus enum → "connected"/"disconnected"/etc.
                                # Backend Device model uses online/offline/busy
                                if status_val in ('connected', 'idle'):
                                    mapped_status = 'online'
                                elif status_val in ('disconnected', 'error'):
                                    mapped_status = 'offline'
                                elif status_val == 'busy':
                                    mapped_status = 'busy'
                                else:
                                    mapped_status = 'online'
                            else:
                                mapped_status = 'online'

                            devices_list.append({
                                'device_id': dev.device_id,
                                'name': getattr(dev, 'name', f'Device-{dev_id}'),
                                'device_type': normalized_type,
                                'status': mapped_status,
                                'adb_serial': getattr(dev, 'serial', '') or '',
                                'emulator': getattr(dev, 'emulator_type', '') or '',
                                'window_handle': window_handle,
                                'window_title': window_title,
                            })
            except Exception as exc:
                logger.warning("收集设备信息失败: %s", exc)

        # Send to server if we have devices
        if devices_list:
            await self.send_message("device.sync", {
                'devices': devices_list,
                'count': len(devices_list),
            })
            logger.info("已同步 %d 个设备到 Server", len(devices_list))
        else:
            logger.info("无本地设备需要同步")

    def _dispatch_to_handler(self, message: dict[str, Any], handler) -> None:
        """将 Server 消息分发到 handler 对应方法.

        A3 (spec 2026-07-30-debug-directory-restructure): 从 WS 帧顶层提取
        ``trace_id``, 根据 handler 方法签名决定是否传递 ``trace_id`` 参数.
        支持 ``trace_id`` 参数的 handler (如 handle_task_assign /
        handle_task_cancel) 会收到帧顶层 trace_id; 不支持的 handler
        按原签名调用, 零影响.
        """
        msg_type = message.get("type", "")
        # Server's serialize_frame() puts the payload under "payload" key.
        # Accept "data" as a fallback for legacy senders that haven't migrated.
        msg_data = message.get("payload", message.get("data", {}))
        # A3: 帧顶层 trace_id (由 backend serialize_frame 从 ContextVar 注入).
        frame_trace_id = message.get("trace_id", "")

        def _noop_ack(_data, trace_id=""):
            # Server acks heartbeat/progress/result with event.ack; nothing to do
            # but log at debug level. Without this entry the agent spammed
            # "未知消息类型: event.ack" every heartbeat interval.
            logger.debug("收到服务端 ack: %s", _data)

        handler_map = {
            "agent.status": handler.handle_status_update,
            # WS 帧名规范（命名归一化 C-5, 2026-08-29 锁定）:
            # 规范帧名 = "task.assign" (canonical); "task.dispatch" 保留为 deprecated
            # alias（历史兼容, 映射同一 handler）. 后端方法名 handle_task_assign 不变.
            "task.assign": handler.handle_task_assign,
            "task.dispatch": handler.handle_task_assign,
            "task.cancel": handler.handle_task_cancel,
            # spec-2026-08-02-backend-execution-unification: pipeline.execute 已删除，
            # 所有执行统一走 task.dispatch/task.assign
            # Server → Agent: MonitorRuleViewSet.push_to_agent triggers
            # MONITOR_RULE_UPDATE frames; handler forwards to
            # MonitorManager.update_rules() for hot-swap without restart.
            "monitor.rule.update": handler.handle_monitor_rule_update,
            "screenshot.control": handler.handle_screenshot_control,
            "event.ack": _noop_ack,
            # Task 2.1: LLM call result from server via WebSocket RPC.
            "llm.result": handler.handle_llm_result,
            # S2-2.7 (2026-08-17): device recovery command dispatched by
            # backend scheduler/recovery_engine._action_device_command.
            # Without this entry the frame was dropped with "未知消息类型"
            # warning and recovery actions never executed on the agent.
            "device.command": handler.handle_device_command,
            # spec-35 Phase 2.2: "error" type removed in spec-29c; backend
            # now sends agent.status with status="error" payload. handler_map
            # entry deleted along with handler.handle_error method.
        }

        handler_method = handler_map.get(msg_type)
        if handler_method:
            # A3: 根据 handler 签名决定是否传 trace_id (避免 TypeError).
            if _accepts_trace_id_kwarg(handler_method):
                handler_method(msg_data, trace_id=frame_trace_id)
            else:
                handler_method(msg_data)
        elif msg_type != ServerStatus.ERROR.value:
            logger.warning("未知消息类型: %s", msg_type)

    async def _try_reconnect(self) -> None:
        """指数退避自动重连，携带 ping_interval/ping_timeout"""
        while not self._connected:
            logger.info("尝试重连，等待 %.1fs...", self._reconnect_delay)
            await asyncio.sleep(self._reconnect_delay)

            try:
                self._ws = await ws_connect(
                    self._ws_url,
                    additional_headers=self._build_headers(),
                    ssl=self._build_ssl_context(),
                    ping_interval=PING_INTERVAL,
                    ping_timeout=PING_TIMEOUT,
                )
                self._connected = True
                self._reconnect_delay = 1.0
                logger.info("重连成功")
                # spec-42: reset compression state on the new WS — the
                # previous negotiation does not carry over to a new
                # connection. Hello will be re-sent by _send_hello below
                # and the server will respond with a fresh Hello.ack.
                self._compression_negotiated = False
                self._compressor = None
                await self._send_register()
                await self._send_hello()
            except Exception as exc:
                logger.error("重连失败: %s", exc)
                self._reconnect_delay = min(self._reconnect_delay * 2, MAX_BACKOFF)

    async def _send_hello(self) -> None:
        """spec-42: Send a Hello frame advertising supported compression algorithms.

        Always sent as JSON text_data (never compressed) so the server can
        decode it without prior negotiation. The server's Hello.ack is
        handled asynchronously by ``listen()`` calling
        ``_handle_hello_ack()``. If the server never responds (legacy
        build) or declines with ``enabled=False``, the agent stays on
        JSON text_data — ``send_message()`` checks
        ``self._compression_negotiated`` before each compress attempt.
        """
        if not self._ws or not self._connected:
            return
        hello_frame = build_hello_frame(
            algorithms=[COMPRESSION_ALGORITHM_MSGPACK_ZLIB],
            threshold=DEFAULT_COMPRESS_THRESHOLD,
            seq=self._next_seq(),
        )
        # Hello is a transport-level control frame; bypass send_message()
        # to avoid the size-based compression gate (Hello must always be
        # JSON text_data so the server can decode it before negotiation).
        message = json.dumps(hello_frame, ensure_ascii=False)
        try:
            await self._ws.send(message)
            logger.info(
                "[AGENT->SERVER][connection] 已发送 Hello: algorithms=%s, threshold=%d",
                [COMPRESSION_ALGORITHM_MSGPACK_ZLIB], DEFAULT_COMPRESS_THRESHOLD,
            )
        except Exception as exc:
            logger.warning("[AGENT->SERVER][connection] Hello 发送失败: %s", exc)

    def _handle_hello_ack(self, frame: dict[str, Any]) -> None:
        """spec-42: Process the server's Hello.ack and flip negotiation state.

        On success: sets ``_compression_negotiated = True`` and initializes
        ``_compressor`` with the negotiated threshold. On decline
        (``enabled=False``) or parse error: leaves negotiation off so
        ``send_message()`` keeps using JSON text_data.
        """
        try:
            algorithm, threshold, enabled = parse_hello_ack_capabilities(frame)
        except HelloFrameError as exc:
            logger.warning(
                "[SERVER->AGENT][connection] Hello.ack 解析失败, 保持 JSON 模式: %s",
                exc,
            )
            return
        if not enabled:
            logger.info(
                "[SERVER->AGENT][connection] 服务端拒绝压缩 (enabled=False), 保持 JSON 模式"
            )
            self._compression_negotiated = False
            self._compressor = None
            return
        if algorithm != COMPRESSION_ALGORITHM_MSGPACK_ZLIB:
            logger.warning(
                "[SERVER->AGENT][connection] 服务端选了未支持的算法 %r, 保持 JSON 模式",
                algorithm,
            )
            self._compression_negotiated = False
            self._compressor = None
            return
        try:
            self._compressor = MessageCompressor(compress_threshold=threshold)
        except ValueError as exc:
            logger.warning(
                "[SERVER->AGENT][connection] compressor 初始化失败 (threshold=%s): %s",
                threshold, exc,
            )
            self._compression_negotiated = False
            self._compressor = None
            return
        self._compression_negotiated = True
        logger.info(
            "[SERVER->AGENT][connection] 压缩协商成功: algorithm=%s, threshold=%d, msgpack=%s",
            algorithm, threshold, self._compressor.uses_msgpack,
        )
