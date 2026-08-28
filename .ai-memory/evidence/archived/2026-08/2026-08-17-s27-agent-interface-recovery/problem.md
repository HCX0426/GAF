---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, problem-step, evidence-problem]
solution: Problem 模板 — 描述症状/触发条件/影响范围;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/solution.md
  - .ai-memory/evidence/templates/verification.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-06-16
---
## Problem（症状 / 触发条件）

S2 恢复链接线已接 backend 侧，但 agent 端界面恢复（yaml 状态机）未接线：
1. 现象：config.py 无 interface_states 相关 5 字段，engine.load 无 recovery_manager 注入，orchestrator 未创建 InterfaceRecoveryManager，handler_map 无 device.command 处理，backend _action_semantic 的 restart/switch_account 诚实降级不派发
2. 触发条件：执行恢复流程时 agent 无法加载 interface_states.yaml / 无法执行恢复动作 / backend 派发 device 命令无 agent 执行者
3. 影响范围：agent/src/core/ + agent/src/engine/ + agent/src/client/ + backend/scheduler/recovery_engine.py 全链路恢复能力缺失
