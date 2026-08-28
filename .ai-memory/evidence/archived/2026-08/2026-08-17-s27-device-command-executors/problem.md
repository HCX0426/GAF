# Evidence: 2026-08-17-s27-device-command-executors

## problem

S2-2.7 (-) 已知限制: 6 个 device.command 命令无 agent 端执行器,
backend recovery_engine 派发的 device.command 帧只能收到 not-implemented 结果,
restart_app / notify_only 两个常用恢复动作假死。

## solution

- handler.py 新增 _exec_restart_app (ADB force-stop+monkey / Windows taskkill+Popen,
  复用 engine.nodes.app_control._run_adb) + _exec_notify_only (logger 按 level 输出)
- not-implemented 列表收敛为 relogin / switch_backup / switch_account / restart
  (凭据下发安全设计与语义确认待定, 显式上报不假 success)

## verification

- test_s27_recovery_wiring.py 28 passed (新增 TestRestartAppExecutor 6 + TestNotifyOnlyExecutor 3)
- agent 全量回归: 2288 passed, 3 skipped
- 文档: dispatch-flow.md §4.6 / scheduler.md §9.2 同步