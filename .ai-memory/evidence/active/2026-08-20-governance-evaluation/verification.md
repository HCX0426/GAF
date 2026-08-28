---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-20-governance-evaluation/
load_when: [evidence, 3-step-evidence, governance, TD-369, TD-370, TD-374, TD-375, TD-379]
priority: high
symptom: [kb:evidence, 3-step-evidence, governance-evaluation, injection-bloat, dead-skill]
solution: Verification — 命令/文件路径/API 端点验证
related_files:
  - .ai-memory/evidence/templates/verification.md
  - docs/specs/archived/2026-08/2026-08-20-governance-evaluation-fixes.md
created_by: AI
last_updated: 2026-08-20
---
## Verification（验证结果）

1. `bash scripts/gaf_init.sh --check-env` → exit 0, 输出 "conda gaf env OK (python 3.11.15)" + "utf8_mode=1 stdout=utf-8", 无 arithmetic error
2. `bash scripts/gaf_init.sh --fast` → L1 hard-load OK (97 entries), 无 line 200 报错
3. `python scripts/hooks/check_lessons_updated.py` → 无 FAIL (5 处 lesson 链接改指归档路径后)
4. `python scripts/hooks/check_doc_code_sync.py` → 0 hard fail (R4 归档白名单补充后)
5. `python scripts/hooks/check_yn_matrices_index.py` → OK; `check_path_consistency.py` → 0 error
6. `python -m pytest scripts/tests/ -p no:django -o addopts=""` → 610 passed / 3 failed (2 为 cross_repo 已修复, 1 为 browser_login 环境依赖 pre-existing: 需前端 dev server 5173)
7. project_rules.md 27.8KB / env-hardrules 32.2KB → 合计 60.5KB ≤ 62KB 预算; 节号 §0-§6.5 全保留, 关键硬约束 §3.4/§4.6/§4.8/§6.2 grep 无遗漏