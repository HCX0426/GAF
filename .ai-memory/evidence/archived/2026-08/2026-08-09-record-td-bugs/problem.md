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
last_updated: 2026-08-09
---
## Problem（症状 / 触发条件）

1. 现象: 任务执行链路审查发现 8 项问题，包括 Pipeline 路由 405、截图流延迟 2-3 秒、线程泄漏、FramePool 无校验、ADB 坐标不支持旋转、全屏检测不准、chain 兼容分支未清理
2. 触发条件: 2026-08-08 任务执行数据流审查（数据流通/图片流通/实时性）
3. 影响范围: backend/pipeline/urls.py、agent/src/client/handler.py、agent/src/platforms/windows/window_monitor.py、agent/src/platforms/windows/frame_pool.py、agent/src/utils/adb_coord_transformer.py、agent/src/utils/coord_transformer.py