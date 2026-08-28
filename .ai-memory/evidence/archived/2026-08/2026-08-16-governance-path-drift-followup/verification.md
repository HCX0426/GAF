---
maintainer: manual
source: GAF spec-2026-08-15-governance-redundancy-consolidation followup
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: tech-debt 路径漂移修复验证
solution: 测试 + 脚本 --check + doc-path-drift 全链验证
related_files:
  - scripts/tests/test_sync_tech_debt_counts.py
  - scripts/tests/test_governance_dashboard.py
  - scripts/tests/test_monthly_health_check.py
  - scripts/governance/sync_tech_debt_counts.py
  - scripts/hooks/check_doc_path_drift.py
created_by: AI
last_updated: 2026-08-16
---
## Verification（验证）

$ D:\code\environment\conda\envs\gaf\python.exe -m pytest scripts/tests/test_sync_tech_debt_counts.py scripts/tests/test_governance_dashboard.py scripts/tests/test_monthly_health_check.py scripts/tests/test_sync_tech_debt_archive.py scripts/tests/test_doc_health_check.py -p no:django -o addopts="" --tb=short -q
预期: 107 passed, 1 skipped (实际输出一致)

$ D:\code\environment\conda\envs\gaf\python.exe scripts/governance/sync_tech_debt_counts.py --check
预期: "✅ tech-debt counts consistent: active=0 fixed=123 wontfix=32 total=155" (实际输出一致)

$ D:\code\environment\conda\envs\gaf\python.exe scripts/hooks/check_doc_path_drift.py
预期: "[doc-path-drift] 0 violation(s), 373 file(s) skipped (whitelist)" (实际输出一致)