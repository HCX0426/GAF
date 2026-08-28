"""敏感文件扫描 — 检查 .env、密钥、凭据是否被 git 追踪。

用法:
    python scripts/security/check_sensitive_files.py             # 扫描默认路径
    python scripts/security/check_sensitive_files.py --check-git # 检查 git 追踪状态
    python scripts/security/check_sensitive_files.py --verbose    # 详细输出

设计目标 (N192 用户调试视角 B):
    - 开发/部署前一键验证是否有敏感文件泄露风险
    - 输出人类可读的分级报告 (OK/WARN/CRIT)
    - 可在 gaf_init 或 CI 中集成
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# === 敏感文件模式 ===
# 只匹配真正含敏感数据的文件名; 忽略 migration/test/常规源码
_SENSITIVE_NAME_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\.env(\.local|\.[^.]+)?$", re.IGNORECASE),
    re.compile(r"\.(pem|key|crt|p12|pfx)$", re.IGNORECASE),
    re.compile(r"(id_rsa|id_dsa|id_ecdsa|id_ed25519)$", re.IGNORECASE),
    re.compile(r"(?i)credential[s]?\b"),
    re.compile(r"(?i)(secret[s]?|credentials?)\.(json|yaml|yml|env|txt)$"),
    re.compile(r"(?i)\.pgpass$"),
    re.compile(r"(?i)\.netrc$"),
]

# 目录级排除 (匹配则认为是安全的项目结构)
_SAFE_PATH_PATTERNS: list[re.Pattern] = [
    re.compile(r"migrations[\\/]"),
    re.compile(r"[\\/]tests?[\\/]"),
    re.compile(r"[\\/]test_.*\.py$"),
    re.compile(r"[\\/]__pycache__[\\/]"),
    re.compile(r"[\\/]node_modules[\\/]"),
    re.compile(r"[\\/]\.venv[\\/]"),
    re.compile(r"tsconfig\.json$"),
    re.compile(r"pyrightconfig\.json$"),
    re.compile(r"skill-config\.json$"),
    re.compile(r"api\.generated\.ts$"),
]

# 内容级敏感模式 (仅应用于小型配置文件)
_CONTENT_SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?i)(secret|api[_-]?key|password|passwd|token)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]"),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key
    re.compile(r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED) PRIVATE KEY-----"),
    re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),  # Slack token
]

# 扫描中跳过的目录
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".mypy_cache",
    ".cache",
    "venv",
    "dist",
    "build",
    "coverage",
    ".trash",
}


def _is_sensitive_file(path: Path, root: Path) -> str | None:
    """返回敏感原因; 不敏感返回 None。"""
    rel = str(path.relative_to(root))

    # 1) 路径级安全判定 (白名单, 避免误报)
    for safe_pat in _SAFE_PATH_PATTERNS:
        if safe_pat.search(rel):
            return None

    name = path.name
    for pat in _SENSITIVE_NAME_PATTERNS:
        if pat.search(name):
            return f"文件名匹配 {pat.pattern}"

    # 2) 内容级检测 (仅对小型/配置类文件)
    if path.suffix.lower() in {".env", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".txt"}:
        try:
            if path.stat().st_size > 1024 * 1024:  # >1MB 跳过
                return None
            text = path.read_text(encoding="utf-8", errors="ignore")
            for cp in _CONTENT_SECRET_PATTERNS:
                if cp.search(text):
                    return f"内容匹配 {cp.pattern[:50]}"
        except (OSError, UnicodeDecodeError):
            return None
    return None


@dataclass
class Finding:
    path: str
    reason: str
    severity: str = "WARN"  # OK / WARN / CRIT
    tracked_in_git: bool = False
    snippet: str = ""


@dataclass
class ScanReport:
    root: Path
    findings: list[Finding] = field(default_factory=list)

    def summary(self) -> str:
        counts: dict[str, int] = {"CRIT": 0, "WARN": 0, "OK": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return (
            f"扫描根: {self.root}\n"
            f"  严重(CRIT): {counts['CRIT']}\n"
            f"  警告(WARN): {counts['WARN']}\n"
            f"  通过(OK):   {counts['OK']}"
        )


def _is_sensitive_file(path: Path, root: Path) -> str | None:
    """返回敏感原因; 不敏感返回 None。"""
    rel = str(path.relative_to(root))
    name = path.name

    # .env.example / .env.template 是模板, 不是敏感文件
    if name.endswith(".example") or name.endswith(".template"):
        return None

    for pat in _SENSITIVE_NAME_PATTERNS:
        if pat.search(name):
            return f"文件名匹配 {pat.pattern}"
    if path.suffix.lower() in {".env", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"(?i)(secret|api[_-]?key|password|passwd|token)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]", text):
                return "疑似硬编码密钥/密码"
            if re.search(r"AKIA[0-9A-Z]{16}", text):  # AWS Access Key
                return "疑似 AWS Access Key"
        except (OSError, UnicodeDecodeError):
            return None
    return None


def _iter_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            yield Path(dirpath) / fname


def _git_is_tracked(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(rel)],
            cwd=root, capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (OSError, ValueError):
        return False


def scan(root: Path, check_git: bool = True, verbose: bool = False) -> ScanReport:
    report = ScanReport(root=root)
    for p in _iter_files(root):
        reason = _is_sensitive_file(p, root)
        if reason is None:
            continue
        tracked = _git_is_tracked(p, root) if check_git else False
        severity = "CRIT" if tracked else "WARN"
        finding = Finding(
            path=str(p.relative_to(root)),
            reason=reason,
            severity=severity,
            tracked_in_git=tracked,
        )
        report.findings.append(finding)
        if verbose:
            marker = "🔴" if severity == "CRIT" else "🟡"
            tracked_tag = " [GIT 追踪中!]" if tracked else ""
            print(f"{marker} {finding.path} [{severity}]{tracked_tag} — {reason}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="敏感文件扫描工具")
    parser.add_argument("--root", default=".", help="扫描根目录")
    parser.add_argument("--check-git", action="store_true", default=True, help="检查 git 追踪状态")
    parser.add_argument("--no-git", action="store_false", dest="check_git")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--fail-on-crit", action="store_true", help="存在 CRIT 时 exit 1")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"❌ 目录不存在: {root}", file=sys.stderr)
        return 2

    report = scan(root, check_git=args.check_git, verbose=args.verbose)
    print(report.summary())

    if not report.findings:
        print("✅ 未发现敏感文件")
        return 0

    crit = [f for f in report.findings if f.severity == "CRIT"]
    if crit:
        print("\n⚠️  以下敏感文件被 git 追踪 (严重!):")
        for f in crit:
            print(f"  - {f.path}: {f.reason}")
        print("\n修复建议:")
        print("  1. 立即从 git 移除: git rm --cached <file>")
        print("  2. 加入 .gitignore")
        print("  3. 轮换密钥 (如已泄露)")
        if args.fail_on_crit:
            return 1

    warn = [f for f in report.findings if f.severity == "WARN"]
    if warn and args.verbose:
        print("\n🟡 警告 (未被 git 追踪, 但建议检查):")
        for f in warn:
            print(f"  - {f.path}: {f.reason}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
