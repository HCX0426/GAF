# spec-context: 2026-08-17-s27-device-command-executors

> 承载体: spec-2026-08-17-s27-device-command-executors
> 关联: docs/specs/archived/2026-08/2026-08-17-s27-device-command-executors.md

## 1. 用户决策原文

- 用户 2026-08-17: "还有任务吗" → AI 报告任务池 → 用户: "你按优先级来吧"
  (自决排序授权, §3.6)
- 用户此前 (S2-2.7 阶段): "为啥遗留优化没加进这个spec的里面，以后在当前任务发现的问题都归属当前任务"
  (N193 任务归属 — 6 个 device.command 无执行器是 S2-2.7 已知限制, 本次任务归属闭环)

## 2. N151 5 步法评估过程

1. **架构盘点**: handler.py `handle_device_command` (-) 已接线 restart_emulator/
   reconnect_adb 真实执行 + 6 命令 not-implemented; agent 引擎已有 start_app/stop_app
   节点 (app_control.py, ADB am force-stop/am start + Windows taskkill/Popen) 与 notify
   节点 (log + webhook), 均带 fail diagnostics + coord_system; `_run_adb` 是模块级函数
2. **识别反模式**: R1 重复实现 — handler 若重写 ADB 启动逻辑则与 start_app 节点双套;
   R2 凭据下发设计缺失 — relogin/switch_account 硬做会把 GameAccount 明文密码引入
   WS 帧 (backend accounts/crypto.py decrypt_password 在 backend 侧, 加密存储)
3. **A/B/C 备选**:
   - A) 复用节点能力实现 restart_app + notify_only, relogin/switch_account/switch_backup
     保持 not-implemented (凭据设计另排)
   - B) 6 命令全做 (引入凭据下发安全设计, 范围膨胀)
   - C) 不动 (保持全 not-implemented)
4. **拒绝反模式**: 拒绝 B (安全边界未设计就传凭据 = 破坏加密存储体系; 范围超阈值)、
   C (恢复链路核心命令 restart_app 假死); 选 A
5. **AI 自决边界**: config 契约与 start_app/stop_app 节点一致; wait_seconds 默认 10s;
   notify_only 仅 log + action_result 上报 (webhook 复用 notify 节点能力, handler 内
   不重实现 HTTP 客户端)

## 3. N167 七维度评分细节

| 维度 | 评分 | 说明 |
|------|------|------|
| 1 架构长远性 | 4 | 复用现有节点能力无新架构, relogin 凭据设计可独立演进 |
| 2 全局归一化 | 4 | restart_app 执行逻辑与 start_app/stop_app 节点同源 (同 _run_adb) |
| 3 新旧兼容 | 4 | config 契约与 start_app 节点参数一致, not-implemented 行为不变 |
| 4 现有业务完善 | 4 | restart_app (最常见恢复动作) 从显式失败变真实执行, 恢复链路闭环 |
| 5 性能资源优化 | 3 | 无热路径影响 (仅恢复触发时执行), ADB 命令 10s 超时 |
| 6 安全合规加固 | 4 | 不引入凭据下发, 加密存储体系不变 |
| 7 长期维护成本 | 4 | 命令→执行器映射集中 handler 一处, 无新维护面 |
| **总分** | **27** | 方案 B 因安全边界未定义否决 (22), C (18); 领先 ≥ 5 → AI 自决 |

## 4. 关键实施决策

- restart_app Windows 分支: `command` 必填 (启动命令), `process` 可选 (杀进程目标,
  默认取 command[0]) — 只有 process 无 command 时无法重启, 报显式 error (测试驱动)
- restart_app 复用 `from engine.nodes.app_control import _run_adb` 而非重写 ADB 调用
  (避免双套实现, N151 step_4)
- not-implemented 列表收敛为 relogin / switch_backup / switch_account / restart
  (restart 由 backend 映射为 restart_app, agent 兜底保留)
- 测试: mock `engine.nodes.app_control._run_adb` (patch 点取模块路径而非 import 路径,
  避免 handler 内 import 时机问题 — 实际在函数内 import, patch 模块属性有效)
- 文档: recovery-design.md 是界面恢复文档不含 device.command 契约表,
  契约表实际在 docs/business/ops/scheduler.md §9.2 → 同步该处 (N193 任务归属)

## N173 用时字段

- `start_ts`: 2026-08-17T18:42:00+08:00
- `end_ts`: 2026-08-17T19:15:00+08:00
- `duration_min`: 33
- `within_baseline`: true
- `root_cause_if_over`: 含全量 agent 回归 173s + pre-commit 3 轮 (B2 acknowledge 重跑 /
  session evidence 补齐 / spec-context N173 字段) ; 大修改基线 < 60min 内