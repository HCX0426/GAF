"""check_deps_sync.py - 依赖清单同步检查 (D1, 2026-08-21).

背景: 配置漂移 (TD) — pyproject.toml 与 backend/requirements/*.txt 是
两套独立维护的依赖清单, 曾出现 apscheduler / fastembed 只在一边声明,
导致不同安装路径 (pyproject vs requirements) 缺依赖报错.
本 hook 在 commit 时强制双向一致, 从源头阻断漂移.

检查规则 (双向)
----------------
1. pyproject.toml [project].dependencies  ⟷  backend/requirements/base.txt
2. pyproject.toml [project.optional-dependencies].dev  ⟷  backend/requirements/dev.txt
   (dev.txt 允许额外含 ocr-paddle 组依赖 — paddleocr)
3. pyproject.toml version  ⟷  backend/config/app_info.py APP_VERSION
   (H22 手动同步点, 此处自动校验)
4. env 变量文档化: 代码 os.getenv 读取的变量必须在 .env.example 声明
   (排除系统/内部白名单); deploy/env.prod.example 变量必须在 .env.example 声明
   (N197/TD-334 补充 — 新增 env 变量必须文档化, 否则生产配置无从配置)

Usage
-----
    # 注册在 gaf_governance_batch.py CHECKS 列表 (hooks.check_deps_sync):
    ("hooks.check_deps_sync", "main", [], "deps-sync"),

    # 手动运行:
    python scripts/hooks/check_deps_sync.py
    python scripts/hooks/check_deps_sync.py --no-fail   # warn only
    python scripts/hooks/check_deps_sync.py --root <p>  # different repo

Exit codes
----------
    0 - 无漂移 (或 --no-fail 模式)
    1 - 至少 1 处漂移
    2 - 配置错误 (未找到 pyproject.toml 等)
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

import argparse  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402


def _norm(name: str) -> str:
    """归一化包名: 小写 + 下划线转连字符 (Pillow→pillow, torch_xla→torch-xla)."""
    return name.lower().replace("_", "-")


def parse_pyproject_version(path: Path) -> str:
    """解析 pyproject.toml [project].version."""
    in_project = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s == "[project]":
            in_project = True
            continue
        if in_project and s.startswith("[") and s.endswith("]"):
            break
        if in_project:
            m = re.match(r'^version\s*=\s*[\'"]([^\'"]+)[\'"]', s)
            if m:
                return m.group(1)
    return ""


def parse_app_info_version(path: Path) -> str:
    """解析 backend/config/app_info.py 的 APP_VERSION."""
    if not path.exists():
        return ""
    m = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
                  path.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


# 系统/框架内部变量 — 代码读取但无需在 .env.example 文档化
SYS_ENV_WHITELIST = {
    # 系统环境变量 (OS 提供, 非 GAF 配置)
    "APPDATA", "DISPLAY", "LOCALAPPDATA", "PATH", "PROGRAMFILES", "USER",
    "USERNAME", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE", "PYTHONIOENCODING",
    "PYTHONUTF8",
    # 框架/管理内部变量 (由 manage.py / pytest / pre-commit / hooks 设置)
    "DJANGO_SETTINGS_MODULE", "GAF_SKIP_DOC_SYNC", "GAF_SKIP_AUTO_AGENT",
    "GAF_ALLOW_HOOK_WRITES", "RUN_MAIN", "PRE_COMMIT",
}

_ENV_READ_PAT = re.compile(r'os\.(?:environ\.get|getenv)\(\s*["\']([A-Z][A-Z0-9_]*)["\']')


def parse_env_template(path: Path) -> set[str]:
    """提取 .env 模板声明的变量名 (含注释 `# VAR=` 行, 即可选项声明)."""
    out: set[str] = set()
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^#?\s*([A-Z][A-Z0-9_]+)=", line)
        if m:
            out.add(m.group(1))
    return out


def collect_env_reads(root: Path) -> set[str]:
    """扫描 backend/agent/scripts 的 os.getenv / os.environ.get 变量名."""
    out: set[str] = set()
    for sub in ("backend", "agent", "scripts"):
        for p in (root / sub).rglob("*.py"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in _ENV_READ_PAT.finditer(text):
                out.add(m.group(1))
    return out


def parse_req(path: Path) -> dict[str, str]:
    """解析 requirements.txt 风格: 包名 -> 约束串 (跳过 -r 引用 / 注释 / URL)."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith(("-r ", "-e ", "git+")):
            continue
        m = re.match(r"([A-Za-z0-9_.\-]+)", line)
        if m:
            out[_norm(m.group(1))] = line
    return out


def parse_pyproject_deps(path: Path) -> dict[str, str]:
    """解析 pyproject.toml [project].dependencies: 包名 -> 约束串."""
    out: dict[str, str] = {}
    in_deps = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s == "[project]":
            in_deps = True
            continue
        if s.startswith("[") and s.endswith("]"):
            in_deps = False
            continue
        if in_deps and (s.startswith('"') or s.startswith("'")):
            dep = s.strip('"\'')
            m = re.match(r"([A-Za-z0-9_.\-]+)", dep)
            if m:
                out[_norm(m.group(1))] = dep
    return out


def parse_pyproject_group(path: Path, group: str) -> dict[str, str]:
    """解析 pyproject.toml 指定 optional-dependencies 组 (如 dev / ocr-paddle)."""
    out: dict[str, str] = {}
    in_opt = False
    in_group = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s == "[project.optional-dependencies]":
            in_opt = True
            continue
        if in_opt and s.startswith("[") and s.endswith("]"):
            break  # 进入下一 section
        if not in_opt:
            continue
        if re.match(rf"^{re.escape(group)}\s*=\s*\[", s):
            in_group = True
            # 处理同一行内联: dev = ["a", "b"]
            for d in re.findall(r'"([^"]+)"', s):
                m = re.match(r"([A-Za-z0-9_.\-]+)", d)
                if m:
                    out[_norm(m.group(1))] = d
            continue
        if in_group:
            if s == "]":
                in_group = False
                continue
            if s.startswith('"') or s.startswith("'"):
                dep = s.strip('"\'')
                m = re.match(r"([A-Za-z0-9_.\-]+)", dep)
                if m:
                    out[_norm(m.group(1))] = dep
    return out


def _diff(left_name: str, left: dict[str, str], right_name: str, right: dict[str, str]) -> list[str]:
    """双向缺失对比, 返回人类可读的错误行."""
    issues: list[str] = []
    for n in sorted(set(left) - set(right)):
        issues.append(f"{left_name} 有但 {right_name} 缺: {n} ({left[n]})")
    for n in sorted(set(right) - set(left)):
        issues.append(f"{right_name} 有但 {left_name} 缺: {n} ({right[n]})")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GAF 依赖清单同步检查 (D1)")
    parser.add_argument("--root", default=".", help="repo root (default: cwd)")
    parser.add_argument("--no-fail", action="store_true", help="warn only, always exit 0")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    pyproject = root / "pyproject.toml"
    base_txt = root / "backend" / "requirements" / "base.txt"
    dev_txt = root / "backend" / "requirements" / "dev.txt"

    if not pyproject.is_file():
        print(f"[deps-sync] ERROR: 未找到 pyproject.toml ({root})", file=_sys.stderr)
        return 2

    issues: list[str] = []

    # 1. base.txt ⟷ pyproject [project].dependencies (双向)
    py_deps = parse_pyproject_deps(pyproject)
    base = parse_req(base_txt)
    issues += _diff("pyproject.dependencies", py_deps, "base.txt", base)

    # 2. dev.txt ⟷ pyproject dev 段 (双向; dev.txt 可额外含 ocr-paddle 组)
    py_dev = parse_pyproject_group(pyproject, "dev")
    py_ocr = parse_pyproject_group(pyproject, "ocr-paddle")
    py_dev_all = {**py_dev, **py_ocr}
    dev = parse_req(dev_txt)
    # pyproject dev 段每个包必须在 dev.txt (dev.txt 缺 → 报错)
    for n in sorted(set(py_dev) - set(dev)):
        issues.append(f"pyproject dev 段有但 dev.txt 缺: {n} ({py_dev[n]})")
    # dev.txt 每个包必须在 pyproject dev 或 ocr-paddle 组
    for n in sorted(set(dev) - set(py_dev_all)):
        issues.append(f"dev.txt 有但 pyproject (dev/ocr-paddle) 缺: {n} ({dev[n]})")

    # 3. pyproject version ⟷ app_info.py APP_VERSION (H22 手动同步点)
    app_info = root / "backend" / "config" / "app_info.py"
    py_ver = parse_pyproject_version(pyproject)
    app_ver = parse_app_info_version(app_info)
    if py_ver and app_ver and py_ver != app_ver:
        issues.append(
            f"pyproject version={py_ver} 与 app_info.py APP_VERSION={app_ver} 不一致 "
            "(需同时更新 — H22 single source of truth)"
        )

    # 4. env 变量文档化 (N197/TD-334 补充)
    env_tpl = parse_env_template(root / ".env.example")
    prod_tpl = parse_env_template(root / "deploy" / "env.prod.example")
    env_reads = collect_env_reads(root)
    # 4a. 代码读取但 .env.example 未声明 (排除系统/内部白名单)
    for v in sorted(env_reads - env_tpl - SYS_ENV_WHITELIST):
        issues.append(f"代码读取 env 变量 {v} 但 .env.example 未声明 (新增变量须文档化)")
    # 4b. prod 模板变量但 .env.example 未声明 (排除内部白名单)
    for v in sorted(prod_tpl - env_tpl - SYS_ENV_WHITELIST):
        issues.append(f"deploy/env.prod.example 变量 {v} 但 .env.example 未声明")

    if issues:
        print("[deps-sync] 依赖清单漂移 (TD 配置漂移防护 — 修复: 双向同步 pyproject.toml 与 backend/requirements/*.txt):")
        for it in issues:
            print(f"  ❌ {it}")
        if args.no_fail:
            print("[deps-sync] --no-fail: 仅警告, exit 0")
            return 0
        return 1

    print("[deps-sync] OK: pyproject.toml 与 backend/requirements/*.txt 双向一致")
    return 0


if __name__ == "__main__":
    _sys.exit(main())
