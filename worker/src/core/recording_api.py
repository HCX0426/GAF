"""
录制数据上报到 Server 的 API 模块

N196: base_url 从 server_url 推导（与 llm_client.py 一致），
避免硬编码 localhost:8000。

s45: 增加 agent token 鉴权（Authorization: Token <agent-token>，与 JWT
Bearer 不冲突）+ 截图批量上传（upload_screenshots）。
"""

import logging
import os
from urllib import parse as urllib_parse

import requests

logger = logging.getLogger(__name__)

_TOKEN_PRIORITY = (
    "CLI --agent-token > env GAF_AGENT_TOKEN > TokenStore(server_url)"
)


def _derive_http_base(server_url: str) -> str:
    """从 WebSocket server_url 推导 HTTP base URL。

    Converts ws:// → http:// and wss:// → https://,
    then strips the WebSocket path to keep only scheme://host:port.
    """
    if not server_url:
        return "http://127.0.0.1:8000"
    parsed = urllib_parse.urlparse(server_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    if not parsed.hostname:
        return "http://127.0.0.1:8000"
    if parsed.port:
        return f"{scheme}://{parsed.hostname}:{parsed.port}"
    return f"{scheme}://{parsed.hostname}"


def _resolve_token(server_url: str, explicit_token: str = "") -> str:
    """Token priority: explicit arg > env GAF_AGENT_TOKEN > TokenStore."""
    if explicit_token:
        return explicit_token
    env_token = os.environ.get("GAF_AGENT_TOKEN", "")
    if env_token:
        return env_token
    try:
        from auth.token_store import TokenStore
        stored = TokenStore().load_token(server_url)
        if stored:
            return stored
    except Exception as exc:  # pragma: no cover - token store is best-effort
        logger.debug("TokenStore load failed: %r", exc)
    return ""


class RecordingAPIClient:
    """录制数据上报客户端"""

    def __init__(self, server_url: str = "", token: str = ""):
        """初始化 API 客户端

        Args:
            server_url: Agent 的 WebSocket server_url，
                用于推导 HTTP base URL。为空时使用环境变量 GAF_SERVER_URL
                或默认值。
            token: Agent token（Authorization: Token）。为空时按
                CLI arg > env GAF_AGENT_TOKEN > TokenStore 优先级解析。
        """
        if not server_url:
            ws_path = os.environ.get("GAF_WS_AGENT_PATH", "ws/protocol/agents/")
            server_url = os.environ.get("GAF_SERVER_URL", f"ws://127.0.0.1:8000/{ws_path}")
        self.server_url = server_url
        http_base = _derive_http_base(server_url)
        api_prefix = os.environ.get("GAF_API_PREFIX", "api/v2")
        self.base_url = f"{http_base}/{api_prefix}"
        self.token = _resolve_token(server_url, token)

    def _headers(self) -> dict:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        return headers

    def upload_recording(self, recording_data: dict) -> dict | None:
        """上传录制数据到 Server

        Args:
            recording_data: 录制数据字典（由 RecordingData.to_dict() 生成）

        Returns:
            Server 返回的 JSON 响应，失败返回 None
        """
        try:
            url = f'{self.base_url}/recordings/'
            resp = requests.post(url, json=recording_data, headers=self._headers(), timeout=10)
            if resp.status_code in (200, 201):
                return resp.json()
            logger.warning("上传录制失败: %s %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("上传录制异常: %r", e)
        return None

    def upload_screenshots(self, recording_id: int, events: list) -> dict:
        """上传录制截图到 Server（逐个事件一张，失败不中断）。

        Args:
            recording_id: 后端 Recording id（upload_recording 返回值）。
            events: recording_data['events'] 列表；其中 event_type ==
                'screenshot' 且 screenshot_path 指向存在的本地文件的事件
                会上传。

        Returns:
            {uploaded: int, skipped: int, failed: list[int]} 统计。
        """
        stats = {"uploaded": 0, "skipped": 0, "failed": []}
        for index, event in enumerate(events):
            if event.get("event_type") != "screenshot":
                stats["skipped"] += 1
                continue
            path = event.get("screenshot_path") or ""
            if not path or not os.path.isfile(path):
                stats["skipped"] += 1
                continue
            try:
                url = f'{self.base_url}/recordings/{recording_id}/screenshots/'
                with open(path, "rb") as fh:
                    files = {"file": (os.path.basename(path), fh, "image/png")}
                    data = {"event_index": str(index)}
                    resp = requests.post(url, data=data, files=files,
                                         headers=self._headers(), timeout=30)
                if resp.status_code == 200:
                    stats["uploaded"] += 1
                else:
                    stats["failed"].append(index)
                    logger.warning("截图上传失败 index=%s: %s %s",
                                   index, resp.status_code, resp.text[:200])
            except Exception as e:
                stats["failed"].append(index)
                logger.warning("截图上传异常 index=%s: %r", index, e)
        return stats

    def list_recordings(self) -> list:
        """获取录制列表

        Returns:
            录制列表，失败返回空列表
        """
        try:
            url = f'{self.base_url}/recordings/'
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning("获取录制列表异常: %r", e)
        return []

    def delete_recording(self, recording_id: str) -> bool:
        """删除录制

        Args:
            recording_id: 录制 ID

        Returns:
            是否删除成功
        """
        try:
            url = f'{self.base_url}/recordings/{recording_id}/'
            resp = requests.delete(url, headers=self._headers(), timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning("删除录制异常: %r", e)
        return False
