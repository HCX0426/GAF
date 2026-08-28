---
maintainer: AI
source: GAF/test-merge-2026-08-04
load_when: [test-merge, refactor]
priority: medium
symptom: [kb:test-merge, fragment-test, test-maintainability]
solution: 合并碎片化测试文件 — accounts/gaf_ai/protocol/scheduler 4 个目录共合并 18 个文件 → 6 个大文件
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
## Problem（症状 / 触发条件）

backend/accounts/gaf_ai/protocol/scheduler 4 个测试目录存在 18 个 < 200 行的碎片化测试文件（如 `test_recovery_engine.py` / `test_recovery_log_api.py` / `test_p048_recovery_wiring.py` 共 3 个文件测同 1 个模块）。触发条件：跑测试时文件切换频繁，单文件修复需在 3 个文件间跳转；测试维护成本高，新人 onboarding 难。影响范围：仅 dev 测试体验，CI 测试仍能跑通但慢（pytest collection overhead 大）。
