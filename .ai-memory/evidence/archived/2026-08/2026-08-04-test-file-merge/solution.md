---
maintainer: AI
source: GAF/test-merge-2026-08-04
load_when: [test-merge, refactor]
priority: medium
symptom: [kb:test-merge, fragment-test, test-maintainability]
solution: 按主题合并 — accounts(game_account + game_account_crypto), gaf_ai(rag + rag_auto_index; views_anomaly/pipeline/skill → views), protocol(compression e2e/negotiation/compressor; concurrency_wiring/device_status_lifecycle → consumer_lifecycle; step_failure_e2e/step_progress_persistence → step_execution), scheduler(recovery_engine/recovery_log_api/p048_recovery_wiring → recovery; scheduler_engine/plan/timewindow → scheduler; unattended_session/tick → unattended)
related_files:
  - backend/accounts/tests/test_game_account.py
  - backend/gaf_ai/tests/test_rag.py
  - backend/gaf_ai/tests/test_views.py
  - backend/protocol/tests/test_compression.py
  - backend/protocol/tests/test_consumer_lifecycle.py
  - backend/protocol/tests/test_step_execution.py
  - backend/scheduler/tests/test_recovery.py
  - backend/scheduler/tests/test_scheduler.py
  - backend/scheduler/tests/test_unattended.py
created_by: AI
last_updated: 2026-08-04
---
## Solution（解决步骤）

1. 合并 accounts: `git mv backend/accounts/tests/test_game_account_crypto.py backend/accounts/tests/test_game_account.py` + 编辑 import/类命名空间
2. 合并 gaf_ai: 5 个文件 → 3 个文件 (`test_rag.py` / `test_views.py` / 原 `test_feature_flags.py` / `test_model_evaluation.py` 保持独立)
3. 合并 protocol: 8 个文件 → 3 个文件 (`test_compression.py` / `test_consumer_lifecycle.py` / `test_step_execution.py`)
4. 合并 scheduler: 7 个文件 → 3 个文件 (`test_recovery.py` / `test_scheduler.py` / `test_unattended.py`)
5. 修复 N152 lesson `related_files` 引用 (`test_recovery_log_api.py` → `test_recovery.py`)
6. 跑 `D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/protocol/tests/ backend/scheduler/tests/ backend/accounts/tests/ backend/gaf_ai/tests/ -p no:django -o addopts=""` 验证
