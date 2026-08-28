# Evidence: 2026-08-17-s27-device-command-executors

## problem

S2-2.7 (-) 已知限制: 6 个 device.command (restart_app / relogin / notify_only /
switch_backup / switch_account / restart) 在 agent 端全部显式 not-implemented,
backend 已派发 device.command 帧等真实 action_result, 最常用的恢复动作假死。

## solution

- restart_app: 复用 engine.nodes.app_control._run_adb (ADB force-stop+monkey /
  Windows taskkill+Popen), config 参数 package/command/process/timeout/wait_seconds
- notify_only: logger 按 level 输出 message, action_result 上报
- relogin/switch_account: 需 GameAccount 凭据下发安全设计 (backend decrypt_password,
  明文密码不落 WS 帧), 另排 spec
- switch_backup: 语义未确认 (模拟器多开备份 vs 账号备份), 待产品定义
- restart: backend 已映射 restart_app, not-implemented 兜底保留

## verification

- agent 全量回归 2288 passed / 3 skipped (+7 新测试)
- test_s27_recovery_wiring.py 28 passed
- dispatch-flow.md §4.6 + scheduler.md §9.2 文档同步
- commit: <PENDING>