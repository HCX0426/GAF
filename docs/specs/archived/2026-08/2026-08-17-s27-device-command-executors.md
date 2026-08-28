---
spec_id: spec-2026-08-17-s27-device-command-executors
title: S2-2.7 后续 — device.command 执行器实现 (restart_app + notify_only 真实执行)
status: ✅ 已归档 (commit -, 2026-08-17)
archived_to: docs/specs/archived/2026-08/2026-08-17-s27-device-command-executors.md
created: 2026-08-17
task_type: new_feature
applies_to: [agent, resources, protocol]
---

# S2-2.7 后续 — device.command 执行器实现

> 来源：S2-2.7 spec（-）已知限制段登记的 6 个无执行器命令。用户授权"按优先级来"（2026-08-17），P1 = 执行器实现。
>
> **范围决策（N151 盘点）**：
> - **restart_app**：agent 已有 `start_app`/`stop_app` 节点（app_control.py，ADB am force-stop/am start + Windows taskkill/Popen）→ 复用执行能力，handler 直接接线真实执行
> - **notify_only**：agent 已有 `notify` 节点（log + 可选 webhook）→ 复用，handler 接线
> - **relogin / switch_account**：需 GameAccount 凭据从 backend 下发到 agent（decrypt_password 在 backend，加密存储），涉及安全边界设计（凭据传递契约），不在本 spec
> - **switch_backup**：语义不明（模拟器备份？账号备份？），保持 not-implemented
> - **restart**：backend 已映射为 restart_app，agent 不直接收 restart（保持 not-implemented 兜底）

## N151 5 步法评估

1. **架构盘点**: handler.py `handle_device_command`（-）已接线 restart_emulator/reconnect_adb 真实执行 + 6 命令 not-implemented 显式上报；agent 引擎已有 start_app/stop_app/notify 节点（app_control.py 344 行 + notify.py，均带 fail diagnostics + coord_system）；`_run_adb` 是模块级函数可复用；notify 节点支持 log/webhook/level/variables
2. **识别反模式**: R1 重复实现风险 — handler 若重写 ADB 启动逻辑则与 start_app 节点双套；R2 凭据下发设计缺失 — relogin/switch_account 硬做会把 GameAccount 明文密码引入 WS 帧（安全边界未定义）
3. **备选方案**: A) 复用节点能力实现 restart_app + notify_only，relogin/switch_account/switch_backup 保持 not-implemented（凭据设计另排） B) 6 命令全做（引入凭据下发安全设计，范围膨胀） C) 不动（保持全 not-implemented）
4. **拒绝反模式**: 拒绝 B（安全边界未设计就传凭据 = 破坏加密存储体系；范围超本 spec 阈值）、C（恢复链路核心命令 restart_app 假死）；选 A
5. **AI 自决边界**: config 契约与 start_app/stop_app 节点一致（package/process/command/timeout）；restart_app 等待参数 wait_seconds 默认 10s；notify_only 仅 log + action_result 上报（webhook 复用 notify 节点能力，handler 内不重实现 HTTP 客户端）

## N167 七维度评分（方案 A）

- **架构长远性**: 复用现有节点能力，无新架构；后续 relogin 凭据设计可独立演进 — 4
- **全局归一化**: restart_app 执行逻辑与 start_app/stop_app 节点同源（同 _run_adb），无双套实现 — 4
- **新旧兼容**: config 契约与 start_app 节点参数一致（package/command/timeout）；not-implemented 行为不变（剩余命令）— 4
- **现有业务完善**: restart_app（最常见恢复动作）从"显式失败"变"真实执行"，恢复链路闭环 — 4
- **性能资源优化**: 无热路径影响（仅恢复触发时执行）；ADB 命令 10s 超时 — 3
- **安全合规加固**: 不引入凭据下发（relogin/switch_account 登记限制），加密存储体系不变 — 4
- **长期维护成本**: 复用节点能力无新维护面；命令→执行器映射集中 handler 一处 — 4
- **总分**: 27（方案 B 因安全边界未定义否决 22；方案 C 18）→ 领先 ≥ 5 分 → AI 自决执行方案 A

## 阶段状态表

| 阶段 | 内容 | 状态 | 完成时间 | commit hash |
|------|------|------|---------|-------------|
| P1 | handler 实现 restart_app（ADB + Windows 双平台，复用 app_control） | ✅ | 2026-08-17 | - |
| P2 | handler 实现 notify_only（log + action_result 上报） | ✅ | 2026-08-17 | - |
| P3 | 测试：restart_app 双平台 + notify_only + not-implemented 列表更新 | ✅ | 2026-08-17 | - |
| P4 | 文档同步：dispatch-flow.md §4.6 + scheduler.md §9.2 | ✅ | 2026-08-17 | - |

## 任务清单

### P1: restart_app 真实执行

- [x] `agent/src/client/handler.py` `handle_device_command` 的 restart_app 分支:
  - 设备类型 emulator/android → `_run_adb(device, ["shell", "am", "force-stop", package])` + `["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"]`（同 app_control.start_app 语义）
  - 设备类型 windows → `taskkill /IM <process> /F` + `Popen(command)`（同 app_control.stop_app/start_app 语义）
  - config 参数: `package`（android）/ `process` 或 `command`（windows）/ `timeout`（默认 10）/ `wait_seconds`（默认 10，重启后等待）
  - 参数缺失 → 显式 error（同 restart_emulator missing type 模式）
  - 复用 `from engine.nodes.app_control import _run_adb`（不重写 ADB 调用）

### P2: notify_only 真实执行

- [x] `handle_device_command` 的 notify_only 分支:
  - config 参数: `message`（必填）/ `level`（默认 info）
  - logger 输出（info/warning/error 按 level）+ 通过 `_send_to_server("device.action_result", ...)` 上报 success=True + output 含 message
  - 参数缺失 → 显式 error

### P3: 测试

- [x] `agent/tests/test_s27_recovery_wiring.py`:
  - 更新 `test_not_implemented_commands_report_explicitly` 参数列表: 移除 restart_app/notify_only，保留 relogin/switch_backup/switch_account/restart
  - 新增 restart_app Android 路径测试（mock `engine.nodes.app_control._run_adb`）
  - 新增 restart_app Windows 路径测试（mock subprocess.Popen + taskkill）
  - 新增 restart_app 参数缺失测试（无 package/无 process/无 command → error）
  - 新增 notify_only 测试（success 上报 + message 透传 + 缺 message error）
  - `test_reports_device_action_result_frame_type` 改用 restart_app 带 config 或保留（restart_app 现在真实执行，需带 package mock）

### P4: 文档同步

- [x] `docs/architecture/cross-cutting/dispatch-flow.md` §4.6 表: restart_app/notify_only 行标注"agent 真实执行（S2-2.7 后续）"
- [x] `docs/business/ops/scheduler.md` §9.2: device.command 命令契约表补 restart_app/notify_only config 参数说明（recovery-design.md 为界面恢复文档，不含 device.command 契约表，契约表实际在 scheduler.md）
- [x] 本 spec 已知限制段更新（relogin/switch_account 凭据下发设计 + switch_backup 语义确认）

## 已知限制

- relogin / switch_account: 需 GameAccount 凭据从 backend 下发到 agent 的安全设计（明文密码不落 WS 帧、解密时机、TTL），另排 spec
- switch_backup: 语义未确认（模拟器多开备份 vs 账号备份），待产品定义
- restart: backend 映射 restart_app 后 agent 不直接收该命令，not-implemented 兜底保留
