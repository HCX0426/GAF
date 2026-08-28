import asyncio
import contextlib
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


# spec-35 Phase 4.2 (2026-07-19): ScreenshotStreamConsumer +
# _normalize_event helper removed — the frontend receives screenshot
# frames via /ws/dashboard (FrontendConsumer.screenshot_frame), so the
# /ws/devices/{id}/screenshot-stream/ endpoint was dead code.


class AdbLogStreamConsumer(AsyncWebsocketConsumer):
    """ADB logcat 实时日志流 WebSocket 消费者 (P-021 H7).

    连接 /ws/devices/{device_id}/adb-logs/ 获取实时 ADB logcat 输出。

    Query string 参数 (可选):
      - tag=<tag>      过滤日志 tag (如 'ActivityManager')
      - level=<level>  过滤日志级别 (V/D/I/W/E/F)
      - pid=<pid>      过滤进程 PID

    客户端控制消息:
      - {'type': 'pause'}    暂停日志推送
      - {'type': 'resume'}   恢复日志推送
      - {'type': 'clear'}    清空服务端缓冲 (重启 logcat)
      - {'type': 'filter', 'tag': ..., 'level': ..., 'pid': ...}  动态调整过滤

    服务端推送消息:
      - {'type': 'adb_log.connected', 'device_id': ...}
      - {'type': 'adb_log.line', 'line': ..., 'seq': ...}
      - {'type': 'adb_log.error', 'message': ...}
      - {'type': 'adb_log.paused'} / {'type': 'adb_log.resumed'}
    """

    MAX_BUFFER_LINES = 5000  # 防止前端积压过多日志

    async def connect(self):
        """验证 JWT + 设备存在 + 设备有 ADB serial 后接受连接。"""
        # Parse query string for filters (tag/level/pid); JWT comes via subprotocol (C8 fix)
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        query_params = {}
        for pair in query_string.split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                query_params[key] = value

        # C8 fix: prefer Sec-WebSocket-Protocol subprotocol `access.<jwt>` over URL query string
        # (token in URL leaks via browser history / access logs / referrer).
        token = ''
        for proto in self.scope.get('subprotocols', []):
            if proto.startswith('access.'):
                token = proto[len('access.'):]
                break
        if not token:
            token = query_params.get('token', '')

        user = await self._authenticate_jwt(token)
        if user is None or not user.is_authenticated:
            await self.close()
            return

        self.device_id = self.scope['url_route']['kwargs'].get('device_id')
        self.stream_group_name = f'adb_logs_{self.device_id}'
        self._process = None
        self._reader_task = None
        self._paused = False
        self._seq = 0
        self._filter_tag = query_params.get('tag', '')
        self._filter_level = query_params.get('level', '').upper()
        self._filter_pid = query_params.get('pid', '')

        # C8: echo the chosen subprotocol on every accept path so the browser
        # completes the handshake (Sec-WebSocket-Protocol must be echoed,
        # otherwise Chromium reports "Sent non-empty header but responded
        # with an empty one" as a console error).
        subprotocols = self.scope.get('subprotocols', [])
        chosen = subprotocols[0] if subprotocols else None

        try:
            from agents.models import Device
            device = await database_sync_to_async(Device.objects.get)(pk=self.device_id)
            if not device.adb_serial:
                await self.accept(subprotocol=chosen)
                await self.send_json({'type': 'adb_log.error', 'message': '设备没有 ADB serial，无法查看 logcat'})
                await self.close()
                return
            self._adb_serial = device.adb_serial
        except Exception:
            logger.warning("AdbLogStream: connect failed to load device (device_id=%s)", self.device_id, exc_info=True)
            await self.accept(subprotocol=chosen)
            await self.send_json({'type': 'adb_log.error', 'message': '设备不存在或不可用'})
            await self.close()
            return

        await self.accept(subprotocol=chosen)
        await self.send_json({
            'type': 'adb_log.connected',
            'device_id': self.device_id,
            'adb_serial': self._adb_serial,
            'filters': {
                'tag': self._filter_tag,
                'level': self._filter_level,
                'pid': self._filter_pid,
            },
        })

        # Start logcat subprocess
        await self._start_logcat()

    @staticmethod
    async def _authenticate_jwt(token):
        """Verify JWT token and return user. Returns None if invalid."""
        if not token:
            return None
        try:
            from django.contrib.auth import get_user_model
            from rest_framework_simplejwt.tokens import AccessToken

            user_model = get_user_model()
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            user = await database_sync_to_async(user_model.objects.get)(pk=user_id)
            return user
        except Exception:
            logger.warning("AdbLogStream: JWT auth failed", exc_info=True)
            return None

    async def disconnect(self, close_code):
        """断开连接时终止 logcat 子进程。"""
        await self._stop_logcat()

    async def receive(self, text_data=None, bytes_data=None):
        """处理客户端控制消息。"""
        if text_data is None:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type', '')
        if msg_type == 'pause':
            self._paused = True
            await self.send_json({'type': 'adb_log.paused'})
        elif msg_type == 'resume':
            self._paused = False
            await self.send_json({'type': 'adb_log.resumed'})
        elif msg_type == 'clear':
            # Restart logcat with -c to clear buffer
            await self._stop_logcat()
            await self._start_logcat(clear_buffer=True)
            await self.send_json({'type': 'adb_log.cleared'})
        elif msg_type == 'filter':
            self._filter_tag = data.get('tag', '')
            self._filter_level = str(data.get('level', '')).upper()
            self._filter_pid = str(data.get('pid', ''))
            # Restart logcat with new filters
            await self._stop_logcat()
            await self._start_logcat()
            await self.send_json({
                'type': 'adb_log.filter_updated',
                'filters': {
                    'tag': self._filter_tag,
                    'level': self._filter_level,
                    'pid': self._filter_pid,
                },
            })

    async def _start_logcat(self, clear_buffer=False):
        """启动 adb logcat 子进程。"""
        # Build adb command
        cmd = ['adb', '-s', self._adb_serial]
        if clear_buffer:
            cmd.extend(['logcat', '-c'])
            # Clear is a one-shot command, then start streaming
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
            except Exception as e:
                await self.send_json({'type': 'adb_log.error', 'message': f'清空 logcat 失败: {e}'})

        # Build logcat filter argument: tag:level *:S
        cmd = ['adb', '-s', self._adb_serial, 'logcat', '-v', 'time']
        if self._filter_tag and self._filter_level:
            cmd.append(f'{self._filter_tag}:{self._filter_level}')
            cmd.append('*:S')
        elif self._filter_level:
            cmd.append(f'*:{self._filter_level}')
        if self._filter_pid:
            cmd.append(f'--pid={self._filter_pid}')

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._reader_task = asyncio.create_task(self._read_logcat_output())
        except Exception as e:
            await self.send_json({'type': 'adb_log.error', 'message': f'启动 logcat 失败: {e}'})

    async def _stop_logcat(self):
        """终止 logcat 子进程。"""
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except Exception:
                with contextlib.suppress(Exception):
                    self._process.kill()
            self._process = None

    async def _read_logcat_output(self):
        """异步读取 logcat stdout 并转发给前端。"""
        if self._process is None or self._process.stdout is None:
            return

        try:
            while True:
                line_bytes = await self._process.stdout.readline()
                if not line_bytes:
                    # EOF — process exited
                    await self.send_json({'type': 'adb_log.error', 'message': 'logcat 进程已退出'})
                    break

                if self._paused:
                    continue

                try:
                    line = line_bytes.decode('utf-8', errors='replace').rstrip('\r\n')
                except Exception:
                    line = str(line_bytes)

                self._seq += 1
                await self.send_json({
                    'type': 'adb_log.line',
                    'line': line,
                    'seq': self._seq,
                })
        except asyncio.CancelledError:
            pass
        except Exception as e:
            with contextlib.suppress(Exception):
                await self.send_json({'type': 'adb_log.error', 'message': f'读取 logcat 输出失败: {e}'})

    async def send_json(self, data):
        """发送 JSON 消息给前端。"""
        await self.send(text_data=json.dumps(data, ensure_ascii=False))
