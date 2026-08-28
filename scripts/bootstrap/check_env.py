"""
GAF 环境验证脚本
检查所有依赖是否就绪：Python / Node.js / npm / Redis / Git / Docker
"""
# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import io
import shutil
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PASS = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"


def check_command(name: str, cmd: str, min_version: str = None, version_flag: str = "--version") -> dict:
    """检查命令是否可用及版本是否符合要求"""
    result = {"name": name, "available": False, "version": None, "status": f"{FAIL} 未找到 {cmd}"}
    exe = shutil.which(cmd)
    if not exe:
        result["status"] = f"{FAIL} 未找到 {cmd}, 请安装后重试"
        return result
    result["available"] = True
    try:
        output = subprocess.run(
            [cmd, version_flag], capture_output=True, text=True, encoding="utf-8", timeout=10
        )
        version_str = (output.stdout or output.stderr).strip()
        result["version"] = version_str.split("\n")[0]
        result["status"] = f"{PASS} {result['version']}"
    except Exception as e:
        result["status"] = f"{WARN} 已安装但无法获取版本: {e}"
    return result


def check_conda_env(env_name: str) -> dict:
    """检查 conda 环境是否存在"""
    result = {"name": f"conda env '{env_name}'", "available": False, "status": f"{FAIL} 未创建"}
    try:
        output = subprocess.run(
            ["conda", "env", "list"], capture_output=True, text=True, encoding="utf-8", timeout=30
        )
        if env_name in output.stdout:
            result["available"] = True
            result["status"] = f"{PASS} env '{env_name}' exists"
        else:
            result["status"] = f"{FAIL} env '{env_name}' not found, run: conda create -n {env_name} python=3.12.4"
    except Exception as e:
        result["status"] = f"{WARN} cannot check: {e}"
    return result


def check_redis_connection(url: str = "localhost", port: int = 6379) -> dict:
    """检查 Redis 是否可连接"""
    result = {"name": "Redis", "available": False, "status": f"{FAIL} not connected"}
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((url, port))
        sock.close()
        result["available"] = True
        result["status"] = f"{PASS} Redis connected ({url}:{port})"
    except Exception:
        result["status"] = f"{FAIL} Redis not reachable ({url}:{port}), run: docker compose up -d redis"
    return result


def main():
    """运行所有环境检查"""
    print("=" * 50)
    print("  GAF Environment Check")
    print("=" * 50)
    print()

    checks = [
        check_conda_env("gaf"),
        check_command("Python", sys.executable, version_flag="--version"),
        check_command("Node.js", "node"),
        check_command("npm", "npm"),
        check_command("Git", "git"),
        check_command("Docker", "docker"),
        check_redis_connection(),
    ]

    print(f"{'Check':<25} {'Status'}")
    print("-" * 60)
    for check in checks:
        print(f"{check['name']:<25} {check['status']}")

    print()
    failed = [c for c in checks if not c["available"]]
    if failed:
        print(f"{WARN} {len(failed)} check(s) failed, please install missing dependencies")
        return 1
    else:
        print(f"{PASS} All environment checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
