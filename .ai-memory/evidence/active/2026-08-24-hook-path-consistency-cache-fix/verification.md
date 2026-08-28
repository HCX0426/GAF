---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, verification-step, evidence-verification]
solution: Verification 模板 — 跑过的命令 + 实际输出 + 截图;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/problem.md
  - .ai-memory/evidence/templates/solution.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-08-24
---
## Verification（验证）

$ conda run -n gaf python scripts/hooks/check_path_consistency.py
预期：summary: 0 error(s), 0 warning(s)

$ conda run -n gaf python -m pytest scripts/tests -q -p no:cacheprovider
预期：589 passed, 2 skipped, 31 deselected, 0 failed

$ (Get-Item "scripts/hooks/check_path_consistency.py").LastWriteTime = Get-Date ; conda run -n gaf python scripts/hooks/check_path_consistency.py
预期：输出 "scanning 1583 files" 重扫（非 "cache hit"），证明脚本自身变更触发缓存失效

$ conda run -n gaf python -m pytest scripts/tests/test_path_hooks_cache.py -q -p no:cacheprovider
预期：17 passed
