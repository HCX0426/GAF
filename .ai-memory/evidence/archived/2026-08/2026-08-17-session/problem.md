---
maintainer: manual
source: GAF session 2026-08-17
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: S2-2.7 后剩余 4 类任务待按优先级推进 (device.command 执行器 / 幻觉防线 / 出站队列持久化 / 模板)
solution: 完成 S2-2.7 收尾 commit (- + -) + 实现 device.command 执行器 spec (restart_app + notify_only 真实执行)
related_files:
  - docs/specs/active/2026-08-17-s27-device-command-executors.md
  - agent/src/client/handler.py
  - agent/tests/test_s27_recovery_wiring.py