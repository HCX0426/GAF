---
maintainer: manual
source: GAF session 2026-08-17
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: evidence 无观测支撑时诊断结论可能幻觉
solution: _verify_evidence 比对 evidence ↔ reasoning_steps observations (difflib text_similarity, 阈值 0.3, evidence 为转述故低于检索 0.5); unverified 附注前 2 条; 弱校验注记保留 (evidence 为空时)
related_files:
  - backend/gaf_ai/tasks.py
  - backend/gaf_ai/tests/test_agent.py