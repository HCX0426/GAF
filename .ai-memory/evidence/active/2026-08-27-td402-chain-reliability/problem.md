---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-27-td402-chain-reliability/
load_when: [evidence, td402, dispatch-ack, unattended]
priority: high
symptom: [TD-402, 链执行器可靠性, dispatch_sent_at, 帧丢卡死, unattended]
solution: 5 项可靠性修复 — S1 ack 覆盖链路径 / 心跳推进链 / start 原子 / completion+advance 行锁
related_files:
  - backend/pipeline/tasks.py
  - backend/tasks/heartbeat.py
  - backend/scheduler/unattended_views.py
  - backend/scheduler/tasks.py
created_by: AI
last_updated: 2026-08-27
---
## Problem（症状 / 触发条件）

无人值守循环挂机链路存在 5 项可靠性缺口（TD-402，2026-08-27 端到端审查发现）：
1. 链节点派发（`backend/pipeline/tasks.py` `_dispatch_task_node` / `_dispatch_pipeline_node`）不写 `execution_snapshot.dispatch_sent_at`，而 `tasks/heartbeat.py` 的 `check_dispatch_acks`（S1，10s beat）只扫描带该字段的执行 → WS 帧丢失（agent 重连窗口/组名不匹配）时 TaskExecution + TaskChainExecution 永久 RUNNING 卡死，无任何兜底。
2. 心跳超时把链节点 execution 置 FAILED 后不调用 `advance_chain_execution`（唯一调度点只在 result 回执路径）→ 链不推进不 fail。
3. `unattended_start_view` 409 检查非原子且无 tick 式 has_active 就地防护 → 并发 start / 设备已有手动链时双派。
4. `_process_chain_completion` 归还与计数、`advance_chain_execution` 无行锁 → 并发 completion/advance 丢失归还或双派下一节点。

影响范围：无人值守轮换挂机（多号活动脚本）在帧丢/并发窗口下卡死、双跑、轮换池失真；`backend/` 的 scheduler / pipeline / tasks 模块。