---
date: 2026-06-10
symptom: [popup:agent:duplicate, 弹窗, 多开, 重复启动, agent-popup]
solution: 文件锁 + SW_HIDE
related_files:
  - worker/src/client/connection.py
created_by: AI
priority: high
diff_keywords: ["agent", "popup", "duplicate", "singleton", "runserver-autoreload"]
---

# Agent 启动后弹窗重复

## 症状

Django runserver 启动后，Agent 进程出现 2 个窗口（父子进程都创建 Agent 实例）。

## 触发条件

- `python manage.py runserver` 启动（autoreload 机制）
- 或用 `gunicorn --reload` 启动
- Windows 平台

## 根因

Django runserver 的 autoreload 用 `spawn` 创建子进程，父子进程都执行 `Agent.__init__()`，均创建 GUI 窗口。

## 解决步骤

1. 在 `worker/src/client/connection.py` 启动前加 `fcntl.flock`（Linux）/ `msvcrt.locking`（Windows）
2. Agent 启动时检查 `ShellExecuteW(..., nShowCmd=SW_HIDE=0)` 改为 `SW_SHOWMINIMIZED`
3. 加 `if __name__ == "__main__"` 双重保护

## 验证

- 跑 `python manage.py runserver`，任务管理器只看到 1 个 Agent 进程
- 日志中"Agent started" 仅出现 1 次

## 预防

- Agent 启动前必跑文件锁检查
- runserver 启动时设 `DJANGO_AUTORELOAD_ENV=check` 环境变量触发自检
