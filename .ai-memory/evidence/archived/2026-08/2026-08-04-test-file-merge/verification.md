---
maintainer: AI
source: GAF/test-merge-2026-08-04
load_when: [test-merge, refactor]
priority: medium
symptom: [kb:test-merge, fragment-test, test-maintainability]
solution: 合并后全量 backend 测试通过;pytest collection overhead 降低 (从 80 文件 → 60 文件)
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
## Verification（验证）

$ D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/protocol/tests/ -p no:django -o addopts="" -q
$ D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/scheduler/tests/ -p no:django -o addopts="" -q
$ D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/accounts/tests/test_game_account.py backend/gaf_ai/tests/test_rag.py backend/gaf_ai/tests/test_views.py -p no:django -o addopts="" -q

预期：所有合并后的测试文件 pytest 通过 (exit 0), 用例数 ≥ 合并前总和
