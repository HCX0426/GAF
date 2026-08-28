# Evidence: 2026-08-17-s27-device-command-executors

## problem

S2-2.7 spec (-) 已知限制段登记 6 个 device.command 命令无 agent 端执行器
(restart_app / relogin / notify_only / switch_backup / switch_account / restart)。
backend recovery_engine 已派发 device.command 帧并等待真实 action_result,
agent 端对 6 命令全部返回 "not implemented" — 恢复链路中最常用的两个恢复动作
(restart_app 应用重启 / notify_only 告警通知) 处于假死状态。

## solution

实现 agent 端真实执行器 (spec 2026-08-17-s27-device-command-executors):

- restart_app: 复用 engine.nodes.app_control._run_adb 能力 —
  - Android/emulator: `am force-stop <package>` + `monkey -p <package>` 重启
  - Windows: `taskkill /IM <process> /F` + `subprocess.Popen(command)` 重启
  - config: package (android) / command (+可选 process) (windows) / timeout / wait_seconds
- notify_only: logger 按 level (info/warning/error) 输出 message, action_result 上报
  - config: message (必填) / level (默认 info)
- relogin / switch_account / switch_backup / restart 保持显式 not-implemented
  (relogin/switch_account 需 GameAccount 凭据下发安全设计, switch_backup 语义待定,
  restart 由 backend 映射为 restart_app)

测试: test_s27_recovery_wiring.py 新增 TestRestartAppExecutor (6 测试) +
TestNotifyOnlyExecutor (3 测试), not-implemented 参数列表更新为 4 命令。
全量 agent 回归 2288 passed / 3 skipped (原 2281 + 7 新测试)。

## verification

- agent/tests/test_s27_recovery_wiring.py: 28 passed
- agent 全量回归: 2288 passed, 3 skipped
- 文档同步: dispatch-flow.md §4.6 表 + scheduler.md §9.2 命令契约表