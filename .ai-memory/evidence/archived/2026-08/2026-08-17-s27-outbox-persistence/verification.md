---
maintainer: manual
source: GAF session 2026-08-17
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: 需要验证持久化正确
solution: agent/tests/test_outbox_store.py 12 tests (FIFO/delete/crash recovery/corrupted db/json integrity) + test_outbox_and_dispatch_ack.py 5 integration tests (enqueue persist/init restore/flush clears/interrupt keeps/no-store unchanged); agent 全量 2305 passed / 3 skipped
related_files:
  - agent/tests/test_outbox_store.py
  - agent/tests/test_outbox_and_dispatch_ack.py