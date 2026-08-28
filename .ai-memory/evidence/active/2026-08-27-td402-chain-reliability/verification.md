---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-27-td402-chain-reliability/
load_when: [evidence, td402, dispatch-ack]
priority: high
symptom: [TD-402, verification]
solution: 跑过的验证命令与结果
related_files:
  - backend/pipeline/tasks.py
  - backend/tasks/heartbeat.py
created_by: AI
last_updated: 2026-08-27
---
## Verification（验证）

$ conda run -n gaf python -m pytest backend/pipeline/tests/test_chain_dispatch_ack.py backend/pipeline/tests/test_chain_executor.py backend/pipeline/tests/test_chain_node_pipeline.py backend/tasks/tests/test_dispatch_ack.py -q --tb=short
预期：49 passed（含 2 个新 dispatch_sent_at 断言）

$ conda run -n gaf python -m pytest backend/scheduler backend/tasks -q --tb=short
预期：268 passed（1 个预存失败 test_analytics_views.py::test_weekly_report_includes_recovery_metrics，与本次改动无关，独立复现于 - 之前的 analytics 改动）

$ conda run -n gaf ruff check backend/pipeline/tasks.py backend/tasks/heartbeat.py backend/scheduler/unattended_views.py backend/scheduler/tasks.py
预期：All checks passed!

$ conda run -n gaf python -m pytest backend/pipeline/tests/test_chain_dispatch_ack.py backend/scheduler/tests/test_start_registers_session.py backend/scheduler/tests/test_loop_rotation.py -q
预期：9 passed（A1 闭环 + loop rotation + 新 ack 断言回归）