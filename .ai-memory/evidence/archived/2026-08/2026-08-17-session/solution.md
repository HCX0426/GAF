---
maintainer: manual
source: GAF session 2026-08-17
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: 恢复链路 device.command 6 命令无 agent 端执行器, restart_app/notify_only 假死
solution: handler.py 新增 _exec_restart_app (复用 app_control._run_adb, ADB force-stop+monkey / Windows taskkill+Popen) + _exec_notify_only (logger 按 level); not-implemented 收敛为 relogin/switch_backup/switch_account/restart; 测试 +9, 文档同步 dispatch-flow.md + scheduler.md
related_files:
  - agent/src/client/handler.py
  - agent/tests/test_s27_recovery_wiring.py
  - docs/architecture/cross-cutting/dispatch-flow.md
  - docs/business/ops/scheduler.md