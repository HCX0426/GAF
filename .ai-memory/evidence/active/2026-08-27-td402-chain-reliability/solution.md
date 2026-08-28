---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-27-td402-chain-reliability/
load_when: [evidence, td402, dispatch-ack]
priority: high
symptom: [TD-402, S1-ack, heartbeat-advance, start-atomic, row-lock]
solution: 5 项修复明细（见下方步骤）
related_files:
  - backend/pipeline/tasks.py
  - backend/tasks/heartbeat.py
  - backend/scheduler/unattended_views.py
  - backend/scheduler/tasks.py
created_by: AI
last_updated: 2026-08-27
---
## Solution（解决步骤）

1. `backend/pipeline/tasks.py` `_dispatch_task_node`：execution 置 RUNNING 时写 `execution_snapshot = {"dispatch_sent_at": now, "dispatch_attempts": 1}`（S1 ack 契约）
2. `backend/pipeline/tasks.py` `_dispatch_pipeline_node`：`TaskExecution.objects.create(..., execution_snapshot={...})` 同契约
3. `backend/pipeline/tasks.py` `advance_chain_execution`：整体纳入 `transaction.atomic()` + `TaskChainExecution.objects.select_for_update()`（并发 advance 串行，防双派下一节点）
4. `backend/tasks/heartbeat.py` `check_agent_heartbeats`：置链节点 FAILED 后 `if exec_.chain_execution_id: advance_chain_execution.delay(exec_.chain_execution_id)`（心跳失败也推进/终止链）
5. `backend/scheduler/unattended_views.py` `unattended_start_view`：409 检查移入 `GameProfile.objects.select_for_update()` 行锁；session 创建前置；派发循环加 tick 式 `TaskChainExecution` has_active 防护（skipped reason=device_busy）
6. `backend/scheduler/tasks.py` `_process_chain_completion`：整体纳入 `transaction.atomic()` + `UnattendedSession.objects.select_for_update()`（并发 completion 不丢归还/计数）
7. 测试：`backend/pipeline/tests/test_chain_dispatch_ack.py` 新增（TASK/PIPELINE 两路径写 dispatch_sent_at 断言）