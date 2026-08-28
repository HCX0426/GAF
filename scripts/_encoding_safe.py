"""_encoding_safe.py — v8.4 Windows PowerShell CJK 乱码统一修复。

Background (N92)
----------------
Windows PowerShell 5 默认 console code page 是 GBK (cp936) 或 cp437。
当 Python 脚本往 stdout 打印 UTF-8 中文（`❌`、`✅`、`鉁?`、`含 5 个`）
时，会出现 mojibake：
  - `✅` → `鉁?`
  - `❌` → `鉂?`
  - `ℹ️` → `鈩癸笍`
  - `含 5 个` → `鍚?5 涓?`

**根因**：Python 默认用 `sys.stdout.encoding`（PowerShell 下是 cp936），
UTF-8 字节流无法编码成 cp936。

**修复**（两层防线，对齐 TEST_SFCAPI_LANGUAGE `-X utf8` 方案）：
1. **全局 UTF-8 Mode**（`PYTHONUTF8=1`）：`force_utf8_mode()` 对子进程继承
   生效，等价 `python -X utf8`，一次性覆盖 stdin/stdout/stderr/file IO 五处。
2. **stdout reconfigure 兜底**：`force_utf8_stdout()` 强制当前进程 stdout 为
   UTF-8（幂等）。

**Project convention**：
- 所有 `scripts/check_*.py` / `scripts/sync_*.py` / `scripts/gaf_*.sh`
  都 import 这个模块并调用 `force_utf8_stdout()`。
- `gaf_init.sh` / `gaf_init.ps1` 同时 export `PYTHONIOENCODING=utf-8` +
  `PYTHONUTF8=1`，让子进程继承全局 UTF-8 模式。
"""
from __future__ import annotations

import io
import os
import sys
from typing import TextIO

_DONE = False
_DONE_MODE = False


def force_utf8_mode() -> None:
    """Enable Python UTF-8 Mode for child processes (idempotent).

    Equivalent to `python -X utf8` / `PYTHONUTF8=1`. This module cannot
    switch the *current* process (Python reads the flag at startup), but
    setting the env var makes all subprocesses launched from this process
    inherit the global UTF-8 mode — covering stdin/stdout/stderr and file
    IO default encodings, not just stdout.

    Aligned with TEST_SFCAPI_LANGUAGE's `-X utf8` three-line defense
    (2026-08-15).
    """
    global _DONE_MODE
    if _DONE_MODE:
        return
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    _DONE_MODE = True


def force_utf8_stdout() -> TextIO:
    """Reconfigure stdout to UTF-8 with `errors="replace"` (idempotent).

    Returns the reconfigured stream. Safe to call multiple times;
    only the first call mutates `sys.stdout`.
    """
    global _DONE
    if _DONE:
        return sys.stdout
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        else:  # Python < 3.7 fallback (shouldn't trigger — project requires 3.11+)
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
    except (AttributeError, ValueError, OSError):
        # If reconfigure fails (e.g. detached process), leave stdout alone.
        pass
    _DONE = True
    return sys.stdout


# Eagerly apply on import so callers only need `import _encoding_safe`.
force_utf8_mode()
force_utf8_stdout()
