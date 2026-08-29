---
date: 2026-08-29
symptom: [windows-detached-subprocess-console-popup, tasklist-redis-cli-ping-flash-window, subprocess-utf8-decode-crash-gbk]
solution: detached 后台进程 (DETACHED_PROCESS 无控制台) spawn 任何控制台子进程必须加 creationflags=CREATE_NO_WINDOW, 否则每次调用弹空白终端一闪而过; 控制台程序输出按系统 locale 编码 (GBK), 勿用 text+utf-8, 用 bytes 比较
related_files:
  - scripts/gaf_daemon.py
  - scripts/services/health.py
created_by: AI
priority: low
n_id: null
diff_keywords: ["CREATE_NO_WINDOW", "DETACHED_PROCESS", "subprocess.run", "tasklist", "redis-cli", "gaf_daemon", "health.py"]
---

# Windows detached 后台进程 spawn 控制台子进程: 弹窗 + locale 编码双坑

## 症状（2026-08-29 服务管理功能实测）

gaf_daemon 以 `DETACHED_PROCESS` 启动（无控制台），其看门狗每 15s 跑健康探针 `redis-cli ping`、进程存活 `tasklist`、停止时 `taskkill`——**每次调用都弹出空白终端窗口一闪而过**（用户反馈"终端时不时跳出来又自己关了"）。此外 `subprocess.run(..., text=True, encoding="utf-8")` 读 `tasklist` 输出时因系统为中文 locale（GBK 字节 0xcf）抛 `UnicodeDecodeError` → `proc.stdout=None` → `TypeError`（daemon restart 直接崩溃）。

## 根因

1. **弹窗**: Windows 上 `CreateProcess` 创建控制台程序时，若父进程无控制台且子进程未指定 `CREATE_NO_WINDOW`/`DETACHED_PROCESS`/`CREATE_NEW_CONSOLE`，系统为新进程分配一个**可见**控制台。`capture_output=True` 只重定向句柄，不阻止分配。
2. **编码崩溃**: 控制台程序（tasklist/taskkill/redis-cli 的中文输出）按系统 OEM 代码页（中文系统=GBK/cp936）输出，硬用 `encoding="utf-8"` 解码即崩；`text=True` 的无编码默认同样有风险。

## 解法

```python
def _no_console_flags() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0

# 1) 弹窗: 所有 daemon 循环内 spawn 加 creationflags=_no_console_flags()
# 2) 编码: 不用 text/encoding, 直接 bytes 比较
proc = subprocess.run(cmd, capture_output=True, creationflags=_no_console_flags())
out = proc.stdout or b""
is_alive = str(pid).encode("ascii") in out          # tasklist
is_pong  = out.strip() == b"PONG"                    # redis-cli
killed   = b"SUCCESS" in out or "成功".encode("utf-8") in out or "成功".encode("gbk") in out  # taskkill
```

## 适用范围

- 任何以 `DETACHED_PROCESS` / `CREATE_NO_WINDOW` 运行的后台守卫进程（gaf_daemon、hook、CI agent），spawn 控制台工具（adb/tasklist/redis-cli/git 等）必须显式 `CREATE_NO_WINDOW`。
- 跨 locale 判定控制台输出用 bytes（含 GBK/UTF-8 双编码按需匹配），不要假设 UTF-8。