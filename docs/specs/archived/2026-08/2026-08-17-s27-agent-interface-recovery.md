---
spec_id: spec-2026-08-17-s27-agent-interface-recovery
title: S2-2.7 agent 端界面恢复接线 (yaml 状态机 + device.command handler + backend 解除降级)
status: ✅ 已归档 (docs/specs/archived/2026-08/2026-08-17-s27-agent-interface-recovery.md)
created: 2026-08-17
task_type: refactor
applies_to: [agent, backend, resources, protocol]
---

# S2-2.7 — Agent 端界面恢复接线

> 来源：2026-08-16 AI 大脑 + 工作流全面评估 Phase 1（S2）。用户决策：**S2-2.7 agent 端界面恢复（yaml 状态机）单独排期**，S1/S2/S3 完成后执行。
>
> **缺口盘点（2026-08-17 调研）**：backend 侧已全部接线（S2 P1-P6 + `AgentConsumer.device_command` consumers.py:1187 转发 device.command），但 **agent 端 6 处缺失**，导致恢复动作仍是死路径：
> 1. `engine.load()` 无 `recovery_manager` / `max_recovery_retries` 参数（recovery-design §5.2 Step 4 设计已写但未实现；`set_recovery_manager` pipeline_engine.py:301 已存在未调用）
> 2. `orchestrator._execute_pipeline_inner`（:914-927）未创建/注入 InterfaceRecoveryManager
> 3. `AgentConfig`（config.py）缺 5 字段：interface_states_path / unknown_state_archive_dir / max_recovery_steps / max_recovery_retries / archive_dedupe_window（§5.2 Step 3 未实现）
> 4. `resources/BrownDust II/interface_states.yaml` **不存在**（recovery-design §9.1 声称 [x] 已建，实际缺失 — 文档漂移）
> 5. `handler_map`（connection.py:817-837）无 `device.command` 条目 → 帧到达即 warning 丢弃
> 6. backend recovery_engine.py:942-949 `restart`/`switch_account` 诚实降级（含 "S2-2.7" 字样）

## N151 5 步法评估

1. **架构盘点**: recovery-design.md 已完成设计（interface_recovery.py 713 行 Manager 已实现 + test_interface_recovery.py 已存在 + engine._attempt_recovery pipeline_engine.py:1792 已实现）；缺口全在"接线层"（config 字段 / orchestrator 注入 / handler 注册 / yaml 资源 / backend 降级解除）
2. **识别反模式**: R1 设计文档标 [x] 但 yaml 未建（文档漂移）; R2 set_recovery_manager 存在但无人调用（死代码）; R3 device.command 帧到 agent 被丢弃（同 S2 评估发现的静默丢弃模式）
3. **备选方案**: A) 按 recovery-design 完整接线（config + orchestrator 注入 + yaml + handler + backend 解除降级）B) 只加 handler 处理 device.command（restart_emulator 等用现有 emulator_controller.restart_emulator 直接执行，不接界面恢复 yaml）C) 保持降级不动
4. **拒绝反模式**: 拒绝 C（半途而废，S2-2.7 就是为此排期）; B 为部分接线（界面恢复 yaml 是 2.7 核心诉求，且 Manager 已实现只差接线，不做即浪费）
5. **AI 自决边界**: 界面恢复 yaml 仅建 BD2 初始状态（main_menu + 恢复路径基础态），其他游戏后续扩展；`restart`/`switch_account` backend 降级解除后，backend 仍不等待 agent 执行结果（异步 fire-and-forget，同 device.command 现状），执行结果由 agent 上报状态帧验证

## N167 七维度评分（方案 A）

- **架构长远性**: 按 recovery-design 原设计接线，Manager 复用，后续多游戏只加 yaml — 4
- **全局归一化**: device.command 全链路贯通（backend 派发 → WS 帧 → agent handler → 执行），消除静默丢弃 — 4
- **新旧兼容**: AgentConfig 新字段全可选缺省不启用；engine.load 新参数向后兼容 — 4
- **现有业务完善**: 恢复动作从"诚实降级 error"变为"真正执行"，恢复链路闭环 — 4
- **性能资源优化**: 无热路径影响（恢复仅在失败时触发）— 3
- **安全合规加固**: 无涉 — 2
- **长期维护成本**: 单点维护（yaml + handler 映射表），设计文档与代码对齐消除漂移 — 4
- **总分**: 25（方案 B 总分 20 — 缺界面恢复核心；方案 C 18）→ 领先 ≥ 5 分 → AI 自决执行方案 A

## 阶段状态表

| 阶段 | 内容 | 状态 | 完成时间 | commit hash |
|------|------|------|---------|-------------|
| P1 | AgentConfig 加 5 字段 + config 默认值 | ✅ | 2026-08-17 | - |
| P2 | engine.load 加 recovery_manager/max_recovery_retries 参数 + pipeline_name 设置 | ✅ | 2026-08-17 | - |
| P3 | orchestrator 注入 InterfaceRecoveryManager（§5.2 Step 4 代码落地） | ✅ | 2026-08-17 | - |
| P4 | 创建 resources/BrownDust II/interface_states.yaml 初始版 | ✅ | 2026-08-17 | - |
| P5 | handler 加 handle_device_command + handler_map 注册 device.command | ✅ | 2026-08-17 | - |
| P6 | backend 解除 restart/switch_account 诚实降级 | ✅ | 2026-08-17 | - |
| P7 | 测试 + 文档同步（dispatch-flow.md / recovery-design.md 漂移修复） | ✅ | 2026-08-17 | - |

## 任务清单

### P1: AgentConfig 加 5 字段

- [x] `agent/src/core/config.py` AgentConfig 新增（recovery-design §5.2 Step 3 原文）:
  ```python
  interface_states_path: str | None = None
  unknown_state_archive_dir: str = "debug/unknown_states"
  max_recovery_steps: int = 5
  max_recovery_retries: int = 2
  archive_dedupe_window: int = 10
  ```
- [x] 确认 config 加载路径（env/config.yaml → AgentConfig）透传（from_args **kwargs 自动透传，无需改加载代码）

### P2: engine.load 扩展

- [x] `pipeline_engine.py:431` load() 加 `recovery_manager=None, max_recovery_retries: int = 0` 参数
- [x] load() 内设置 `self._recovery_manager = recovery_manager` + `self._max_recovery_retries = max(1, max_recovery_retries) if recovery_manager else 0`（manager 存在时最少 1 次尝试）
- [x] load() 设置 `self._context.pipeline_name`（从 pipeline_json metadata 提取，context.py:127 字段存在但 load 从未设置 — recovery-design §5.2 注 2）
- [x] `_attempt_recovery` 硬编码 2 次上限改为消费 `self._max_recovery_retries`（:1792 处 LIMIT_REACHED 判断）

### P3: orchestrator 注入

- [x] `orchestrator.py` `_execute_pipeline_inner` engine.load() 调用前（:958 前）:
  - 读 `self._config.interface_states_path`，Path.is_file() 才创建 Manager
  - `_resolved_find_template` 包装 resolve_resource_path（§5.2 Step 4 代码落地）
  - InterfaceRecoveryManager 实例化（screenshot_fn=device.capture_screen / template_match_fn 包装 / action_executor_fn=self._execute_recovery_action / popup_handler=self._monitor_manager.popup_handler）
  - 初始化失败（yaml 校验错等）→ warning + recovery_manager=None 降级，不阻塞执行
- [x] engine.load() 传 recovery_manager + max_recovery_retries（recovery_manager 为 None 时传 0）
- [x] 新增 `_execute_recovery_action` 方法（§5.2 Step 5 代码落地: template_match/key_press/click/swipe/wait 5 种 action + roi 列表→dict 转换 + template 路径解析）

### P4: interface_states.yaml

- [x] 创建 `resources/BrownDust II/interface_states.yaml`（§4.1 格式）: main_menu（安全状态）+ map_view 两状态 + map_view→main_menu ESC 转移（初始最小集，模板路径用现有 templates/public/ 实际文件；Manager 加载验证通过: states=2 transitions=1 safe=['main_menu']）

### P5: device.command handler

- [x] `handler.py` 新增 `handle_device_command(self, data, trace_id="")`:
  - command 分发: restart_emulator → EmulatorController.restart_emulator（已存在）；reconnect_adb → 活跃设备 connect() 重连
  - restart_app / relogin / notify_only / switch_backup / switch_account / restart 无 agent 端执行器 → 显式 not-implemented 结果上报（不假 success）
  - 未知命令 → error 上报
  - 结果帧: `device.action_result`（P-048: backend _handle_command_result 写 RecoveryLog + 广播 dashboard）
- [x] `connection.py` handler_map 加 `"device.command": handler.handle_device_command`（修复帧到达即 warning 丢弃）
- [x] trace_id 透传 + ContextVar 设置（与其他 handler 一致）

### P6: backend 解除降级

- [x] `recovery_engine.py` `_action_semantic` 中 restart/switch_account 改为: 从 target（step 或 execution）反查执行 agent → 找 ONLINE 设备 → 派发 device.command（restart → restart_app 语义，switch_account 原样）→ `_action_device_command(device_command, device.id, config)`
- [x] 解析失败（无 execution / 无 agent / 无 ONLINE 设备）→ 显式 error（不假 success）
- [x] test_recovery_link_wiring.py 降级测试更新为新派发语义（restart→restart_app / switch_account 原样 / 无 agent 无设备 error）

### P7: 测试 + 文档

- [x] agent 测试: 新增 `agent/tests/test_s27_recovery_wiring.py`（21 tests: handler device.command 分发/not-implemented/结果帧 + handler_map 注册 + engine.load pipeline_name/recovery 参数 + orchestrator 注入 3 场景）
- [x] backend: test_recovery_link_wiring.py 新增 5 tests（restart→restart_app 派发 / 无 agent error / 无 ONLINE 设备 error / switch_account 派发 / step 级 target 反查）+ test_scheduler.py test_semantic_action_returns_success 更新（S2-2.7 新语义）
- [x] 全量回归: agent 2281 passed + backend scheduler 47 passed + protocol 268 passed
- [x] 文档: dispatch-flow.md §4.6 restart/switch_account 行更新（降级 → device.command 派发 + agent action_result 上报）；recovery-design.md §9.1 漂移修复（interface_states.yaml + orchestrator 注入 + 测试落地标注）

## 验收标准

1. `device.command` 帧到达 agent 不再静默丢弃（handler_map 注册 + 分发执行）
2. interface_states.yaml 存在且 Manager 能被 orchestrator 注入（存在时）
3. engine.load 设置 pipeline_name（存档目录命名正确）
4. backend restart/switch_account 不再返回 "S2-2.7" 降级 error，改为 device.command 派发
5. 相关 pytest 全绿（agent + backend）

## 已知限制

- 界面恢复 yaml 仅 BD2 最小集（main_menu），恢复动作执行结果 backend 不等待（异步 fire-and-forget，同 device.command 现状）
- handler 部分 command（relogin/switch_account 等）若 agent 端无现成执行器，先显式 not-implemented 结果上报，不假 success
