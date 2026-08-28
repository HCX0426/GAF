---
date: 2026-06-14
symptom: [pipeline:stuck:running, 卡住, 永远运行, stuck, timeout-fail]
solution: 加超时 + 心跳检测
related_files:
  - backend/pipeline/views.py
  - agent/src/engine/pipeline_engine.py
created_by: AI
priority: high
diff_keywords: ["pipeline", "stuck", "running", "timeout", "heartbeat"]
---

# Pipeline 节点永远停留在 running 状态

## 症状

Pipeline 跑 30+ 分钟后，节点状态仍为 `running`，UI 显示"执行中"。

## 触发条件

- 节点执行时间超过预期（如 OCR 大图）
- 节点抛异常但未更新状态
- Agent 进程崩溃但 Backend 未感知

## 根因

- 节点无超时机制
- 状态更新与执行分离（异常时未回滚）
- 无心跳检测

## 解决步骤

1. 节点 `engine.py` 加 `@timeout(300)` 装饰器
2. 状态机 `state_machine.py` 加 `try/except` 必更新 `state=failed`
3. Backend 加心跳：30s 未收到 Agent 心跳 → 标记 `aborted`

## 验证

- 故意构造 OCR 超时节点：300s 后状态自动变 `failed`
- kill -9 Agent：30s 后 Backend 标记 `aborted`

## 预防

- 所有节点必加超时
- 状态机更新和异常处理 must coexist
