"""Worker 配置定义

N196+: 统一配置归一化 — Worker 从根目录 .env 文件读取配置。
使用 python-dotenv 加载 .env（repo 根目录），使 WorkerConfig 默认值
可被 .env 中的环境变量覆盖，无需修改代码。

Env var 读取优先级：CLI 参数 > 环境变量 > 代码默认值
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# 加载根目录 .env 文件（repo 根目录，agent/ 的父目录）
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)


def _get_config_dir() -> Path:
    """获取 Worker 配置文件目录，优先使用 APPDATA 下的 gaf 目录。

    Returns:
        Path: 配置目录路径
    """
    appdata = os.environ.get('APPDATA', '')
    config_dir = Path(appdata) / 'gaf' if appdata else Path.home() / '.gaf'
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def load_token_from_file(server_url: str) -> str | None:
    """从本地加密存储文件中加载指定 Server 的 Agent Token。

    Args:
        server_url: Server WebSocket 地址

    Returns:
        str | None: Token 字符串，未找到则返回 None
    """
    try:
        from auth.token_store import TokenStore
        store = TokenStore()
        return store.load_token(server_url)
    except (ImportError, Exception):
        return None


def load_token_from_env() -> str:
    """从环境变量 GAF_AGENT_TOKEN 读取 Agent Token。

    Returns:
        str: Token 字符串，未设置则返回空字符串
    """
    return os.environ.get('GAF_AGENT_TOKEN', '')


# WebSocket 默认路径 — 从 GAF_WS_AGENT_PATH 环境变量读取，与 backend/app_info.py 同步
_DEFAULT_WS_AGENT_PATH = os.environ.get("GAF_WS_AGENT_PATH", "ws/protocol/agents/")
_DEFAULT_SERVER_URL = f"ws://127.0.0.1:8000/{_DEFAULT_WS_AGENT_PATH}"


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0


@dataclass
class WorkerConfig:
    """Worker 客户端配置"""
    server_url: str = os.environ.get("GAF_SERVER_URL", _DEFAULT_SERVER_URL)
    agent_token: str = ""
    is_local: bool = False
    screenshot_method: str = "auto"
    input_method: str = ""
    control_mode: str = "pseudo_background"
    # Phase 3.1: SSIM dedup thresholds. Consumed by SSIMChecker when wired
    # into ScreenshotManager.capture() (screenshot-optimization.md §3.2).
    ssim_threshold: float = 0.95
    ssim_downsample: int = 4
    screenshot_interval: float = 0.5
    # TD-340 (2026-07-23): Was 30s, critical vs backend's
    # HEARTBEAT_OFFLINE_SECONDS=30. Reduced to 10s to provide 3x safety
    # margin (backend marks agent offline at 30s no-heartbeat; agent sends
    # every 10s). Prevents status flicker between ONLINE/OFFLINE that broke
    # pipeline execute ("没有在线 Agent" intermittently).
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    device_type: str = "windows"
    extra: dict[str, Any] = field(default_factory=dict)
    ssl_verify: bool = True
    ssl_ca_file: str | None = None
    ssl_client_cert_file: str | None = None
    ssl_client_key_file: str | None = None
    # Debug visualization (template_match etc.): when True, annotated debug
    # PNGs are written to debug_dir/template_match/ on every match attempt.
    # Disabled by default to avoid runtime overhead and disk usage.
    # N196: 默认值由 .env 的 GAF_DEBUG 控制（__main__.py build_config 读取）
    debug_mode: bool = True
    # N196: 调试目录根路径，可通过 .env 的 GAF_DEBUG_DIR 覆盖
    debug_dir: str = os.environ.get("GAF_DEBUG_DIR", "./debug")
    # N196: JPEG 质量，从 .env 的 SCREENSHOT_JPEG_QUALITY 读取（与 backend 共享）
    jpeg_quality: int = int(os.environ.get("SCREENSHOT_JPEG_QUALITY", "80"))
    # N196: 截图缓存 TTL（秒），从 .env 的 GAF_AGENT_CACHE_TTL 读取
    # 注意：与后端 SCREENSHOT_CACHE_TTL（毫秒）完全独立，互不干扰
    cache_ttl: int = int(os.environ.get("GAF_AGENT_CACHE_TTL", "300"))
    # N196: 心跳间隔（秒），从 .env 的 GAF_HEARTBEAT_INTERVAL 读取
    # 后端 HEARTBEAT_OFFLINE_SECONDS 应 >= 3x 此值
    heartbeat_interval: int = int(os.environ.get("GAF_HEARTBEAT_INTERVAL", "10"))
    # S2-2.7 (2026-08-17): 界面恢复配置 (recovery-design.md §5.2 Step 3).
    # 全部可选, 缺省不启用恢复. interface_states_path 指向 yaml 状态图;
    # orchestrator 在 Path.is_file() 为真时才注入 InterfaceRecoveryManager.
    interface_states_path: str | None = None
    unknown_state_archive_dir: str = "debug/unknown_states"
    max_recovery_steps: int = 5
    max_recovery_retries: int = 2
    archive_dedupe_window: int = 10

    @property
    def use_tls(self) -> bool:
        """根据 server_url 协议判断是否启用 TLS"""
        return self.server_url.startswith("wss://")

    @classmethod
    def from_args(cls, server_url: str = "",
                  agent_token: str = "", is_local: bool = False, **kwargs) -> 'WorkerConfig':
        """从命令行参数构建 WorkerConfig，自动从多来源加载 Token。

        Token 加载优先级：命令行参数 > 环境变量 > 本地加密文件

        Args:
            server_url: Server WebSocket 地址
            agent_token: 命令行传入的 Token（可为空）
            is_local: 是否本地模式
            **kwargs: 其他配置参数

        Returns:
            WorkerConfig: 构建好的配置实例
        """
        token = agent_token
        if not token:
            token = load_token_from_env()
        if not token:
            token = load_token_from_file(server_url) or ''
        return cls(
            server_url=server_url,
            agent_token=token,
            is_local=is_local,
            **kwargs,
        )
