"""GAF 服务健康探针层 — 应用级健康检查 (spec 2026-08-29-service-orchestration-health-aware P1).

每个服务定义应用级健康检查函数, 统一返回 :class:`Health` (healthy/detail/ts).
被 gaf_daemon 看门狗循环调用, 也支持命令行 ``--check`` 手动探测.

区别于 `verify_service` 的 "进程/端口存活" 快检, 本层验证服务是否真正可用:

- redis:    redis-cli PING → PONG
- backend:  ``/api/v2/accounts/init/health/`` (SystemHealthView, 无认证) → HTTP 200 且 db/redis pass
- agent:    DB 查询 Agent.last_heartbeat 距今 < 30s 且 status ∈ {idle, online}
- frontend: ``http://127.0.0.1:<port>`` HTTP 200 (vite dev server)

用法:
    python scripts/services/health.py --check
    python -m scripts.services.health --check
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

# ---- 路径常量 (与 gaf_daemon.py 保持一致) ------------------------------------
GAF_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = GAF_ROOT / "backend"
AGENT_DIR = GAF_ROOT / "agent"
FRONTEND_DIR = GAF_ROOT / "frontend"
DEBUG_DIR = GAF_ROOT / "debug"
ENV_FILE = GAF_ROOT / ".env"
HEALTH_STATUS_FILE = DEBUG_DIR / "health-status.json"

PYTHON_EXE = Path("D:/code/environment/conda/envs/gaf/python.exe")
REDIS_CLI_EXE = Path("D:/code/environment/redis/redis-cli.exe")

DEFAULT_REDIS_PORT = 6379
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 5173

# Agent 心跳新鲜度阈值 (与 backend agents/agent_runtime _is_agent_connected_via_db 对齐)
AGENT_HEARTBEAT_STALE_SECONDS = 30
AGENT_HEALTHY_STATUSES = {"idle", "online"}


@dataclass
class Health:
    """单项健康检查结果."""

    service: str
    healthy: bool
    detail: str = ""
    ts: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---- env 读取 (与 gaf_daemon.py _read_env 一致) --------------------------------
def _read_env(key: str, default: str = "") -> str:
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            k, v = stripped.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return default


def _load_ports() -> dict:
    redis_url = _read_env("REDIS_URL", f"redis://localhost:{DEFAULT_REDIS_PORT}/0")
    redis_port = DEFAULT_REDIS_PORT
    import re

    m = re.search(r":(\d+)", redis_url)
    if m:
        redis_port = int(m.group(1))
    backend_port = int(_read_env("BACKEND_PORT", str(DEFAULT_BACKEND_PORT)))
    frontend_port = int(_read_env("FRONTEND_PORT", str(DEFAULT_FRONTEND_PORT)))
    return {"redis": redis_port, "backend": backend_port, "frontend": frontend_port}


def _redis_ping(port: int) -> bool:
    try:
        result = subprocess.run(
            [str(REDIS_CLI_EXE), "-p", str(port), "ping"],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
        )
        return result.stdout.strip() == "PONG"
    except (subprocess.TimeoutExpired, OSError):
        return False


def _http_get(url: str, timeout: float = 3.0) -> int | None:
    """发起 HTTP GET, 返回状态码; 失败返回 None (不抛异常)."""
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except Exception:
        return None


# ---- 各服务健康检查 -----------------------------------------------------------

def check_redis(ports: dict) -> Health:
    port = ports["redis"]
    ok = _redis_ping(port)
    return Health(
        service="redis",
        healthy=ok,
        detail=f"redis-cli PING -> {'PONG' if ok else 'fail'} (port {port})",
        ts=time.time(),
    )


def check_backend(ports: dict) -> Health:
    port = ports["backend"]
    url = f"http://127.0.0.1:{port}/api/v2/system/healthz/"
    status = _http_get(url)
    if status is None:
        return Health(service="backend", healthy=False, detail=f"HTTP GET {url} 无响应", ts=time.time())
    if status == 503:
        return Health(service="backend", healthy=False, detail=f"healthz 返回 503 (DB/Redis 不可达)", ts=time.time())
    if status != 200:
        return Health(service="backend", healthy=False, detail=f"HTTP {status} @ {url}", ts=time.time())
    # 200 → 解析 body 确认 checks 全 pass
    try:
        import json as _json
        import urllib.request

        with urllib.request.urlopen(url, timeout=3.0) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
        checks = body.get("checks", {})
        ok = all(v == "pass" for v in checks.values())
        return Health(
            service="backend",
            healthy=ok,
            detail=f"healthz {checks}",
            ts=time.time(),
        )
    except Exception as exc:
        return Health(service="backend", healthy=False, detail=f"healthz 解析失败: {exc}", ts=time.time())


def check_agent(ports: dict) -> Health:
    """DB 查询 Agent.last_heartbeat 新鲜度 + status.

    通过 Django ORM (reuse backend models), 仅查询不写库.
    """
    try:
        import os
        import sys
        import django

        sys.path.insert(0, str(BACKEND_DIR))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()

        from django.utils import timezone
        from agents.models import Agent

        agent = Agent.objects.filter(is_local=True).first() or Agent.objects.first()
        if agent is None:
            return Health(service="agent", healthy=False, detail="DB 无 Agent 记录", ts=time.time())

        fresh = False
        if agent.last_heartbeat is not None:
            age = (timezone.now() - agent.last_heartbeat).total_seconds()
            fresh = age < AGENT_HEARTBEAT_STALE_SECONDS
        healthy = agent.status in AGENT_HEALTHY_STATUSES and fresh
        return Health(
            service="agent",
            healthy=healthy,
            detail=f"status={agent.status} hb_age={(timezone.now() - agent.last_heartbeat).total_seconds() if agent.last_heartbeat else 'N/A'}s",
            ts=time.time(),
        )
    except Exception as exc:
        return Health(service="agent", healthy=False, detail=f"DB 查询失败: {exc}", ts=time.time())


def check_frontend(ports: dict) -> Health:
    port = ports["frontend"]
    url = f"http://127.0.0.1:{port}/"
    status = _http_get(url)
    ok = status is not None and status < 500
    return Health(service="frontend", healthy=ok, detail=f"HTTP {status if status is not None else '无响应'} @ {url}", ts=time.time())


# ---- 编排 ----------------------------------------------------------------------

CHECKERS: dict[str, Callable[[dict], Health]] = {
    "redis": check_redis,
    "backend": check_backend,
    "agent": check_agent,
    "frontend": check_frontend,
}


def check_all(ports: dict | None = None) -> dict[str, Health]:
    """对所有服务跑健康检查, 返回 {service: Health}."""
    ports = ports or _load_ports()
    return {name: fn(ports) for name, fn in CHECKERS.items()}


def write_health_snapshot(snapshot: dict[str, Health]) -> None:
    """健康快照写入 debug/health-status.json (供 monitors/status 读取)."""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "services": {name: h.to_dict() for name, h in snapshot.items()},
    }
    HEALTH_STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GAF 服务健康探针 (spec P1)")
    parser.add_argument("--check", action="store_true", help="对所有服务执行健康检查并输出 JSON")
    parser.add_argument("--write", action="store_true", help="检查后写入 debug/health-status.json")
    args = parser.parse_args(argv)

    if args.check:
        snapshot = check_all()
        for name, h in snapshot.items():
            flag = "OK " if h.healthy else "FAIL"
            print(f"[{flag}] {name}: {h.detail}")
        if args.write:
            write_health_snapshot(snapshot)
            print(f"\n快照写入: {HEALTH_STATUS_FILE}")
        overall = all(h.healthy for h in snapshot.values())
        return 0 if overall else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())