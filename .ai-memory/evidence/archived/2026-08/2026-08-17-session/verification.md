---
maintainer: manual
source: GAF session 2026-08-17
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: 需要验证 device.command 执行器实现正确
solution: test_s27_recovery_wiring.py 28 passed (TestRestartAppExecutor 6 + TestNotifyOnlyExecutor 3 + 回归); agent 全量 2288 passed / 3 skipped; commit 后 git log 验证
related_files:
  - agent/tests/test_s27_recovery_wiring.py