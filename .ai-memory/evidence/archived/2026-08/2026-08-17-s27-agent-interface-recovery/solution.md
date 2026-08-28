---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, solution-step, evidence-solution]
solution: Solution 模板 — 列步骤 + 涉及文件 + 命令;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/problem.md
  - .ai-memory/evidence/templates/verification.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-06-16
---
## Solution（解决步骤）

1. agent/src/core/config.py: AgentConfig 加 interface_states_path / unknown_state_archive_dir / max_recovery_steps / max_recovery_retries / archive_dedupe_window 5 字段（from_args **kwargs 透传）
2. agent/src/engine/pipeline_engine.py: load() 加 recovery_manager/max_recovery_retries 参数，_attempt_recovery 消费 self._max_recovery_retries，_context.pipeline_name 从 metadata 设置
3. agent/src/core/orchestrator.py: _execute_pipeline_inner 在 engine.load 前按 Path(interface_states_path).is_file() 创建 InterfaceRecoveryManager（_resolved_find_template + popup_handler），失败 warning 降级 None；新增 _execute_recovery_action
4. resources/BrownDust II/interface_states.yaml: main_menu + map_view + ESC 转移（2 状态 1 转移）
5. agent/src/client/handler.py + connection.py: handle_device_command（restart_emulator/reconnect_adb 真实执行，其余显式 not-implemented）+ handler_map 注册 device.command
6. backend/scheduler/recovery_engine.py: _action_semantic restart/switch_account 解析 execution→agent→device 后 _action_device_command 派发 device.command（restart→restart_app）
