---
date: 2026-08-28
symptom: [stale-service, backend-not-restarted, fake-green, e2e-false-pass, stale-code]
solution: 改动 backend/agent 代码后，跑 E2E 前必须先确认对应服务已加载新代码（重启 Daphne/Celery/agent）；"部分入口成功"可能是旧代码恰兼容，不是新代码验证通过
related_files:
  - backend/tasks/tasks.py
  - worker/src/client/handler.py
created_by: AI
priority: high
n_id: N209
diff_keywords: ["restart", "stale", "fake-green", "旧代码", "重启"]
---

# 改码后服务未重启 → E2E 部分入口"假绿"

## 症状（2026-08-28 实测暴露）

执行路径清理 B1 收尾时给 `dispatch_task` 新增 `force_agent_id` 参数。运行中的 backend（Daphne）仍是旧代码：

- **Task / Pipeline 执行 → 显示 SUCCESS**（旧签名用位置参数调用，恰兼容）
- **TaskChain 执行 → 500：`dispatch_task() got an unexpected keyword argument 'force_agent_id'`**

如果不重启 backend，只跑 Task/Pipeline 入口会得出"全部通过"的错误结论——**这是新代码路径根本没被加载的假绿**。

## 根因

服务进程（daphne/worker/agent）在改动之前启动，持有旧字节码；单元测试跑的是新代码，E2E 跑的是旧代码，二者结论都正确但都只覆盖一半。没有"改码 → 重启 → 再验"的显式步骤，AI 默认以为测试观察到的就是新代码行为。

## 解决方案

1. **改 backend/agent 代码后，E2E 前先确认服务进程是新的**：`Get-CimInstance Win32_Process | where CommandLine -match 'daphne|python -m src'` 看启动时间，或 `git log -1 --format=%ci <code>` 对比；不确定就重启（daphne 由 gaf_daemon 看门狗自动拉起，kill 即可）
2. **新入口路径必须有独立 E2E 用例**：单元测试 + 至少一个真实链路入口（如 TaskChain）显式覆盖新参数/新分支，防止"旧签名恰兼容"掩盖
3. 与 N99（Vite 缓存旧代码）同族：一切"改了却不见效果/不全通过"先查**服务是否加载新代码**

## 反查

- architecture-mistakes §8（stale agent process）互补：那是进程残留，这里是**进程未重启**，两者都造成"以为在用新代码"