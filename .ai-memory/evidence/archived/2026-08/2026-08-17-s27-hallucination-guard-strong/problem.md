---
maintainer: manual
source: GAF session 2026-08-17
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: S3 spec 已知限制: 幻觉防线只有弱校验 (evidence 为空 → 附注), 无强校验 (evidence 是否被工具观测支撑)
solution: 实现强校验 — _verify_evidence (text_similarity >= 0.3 比对 evidence vs reasoning_steps observations) + AgentSession.evidence_check JSONField (migration 0010) + 视图透出 + unverified 附注
related_files:
  - backend/gaf_ai/tasks.py
  - backend/gaf_ai/agent/models.py
  - backend/gaf_ai/agent/views.py
  - backend/gaf_ai/migrations/0010_agent_session_evidence_check.py