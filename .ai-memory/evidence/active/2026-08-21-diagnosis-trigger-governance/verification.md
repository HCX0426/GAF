---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-21-diagnosis-trigger-governance/
load_when: [evidence, 3-step-evidence, N204, diagnosis-trigger, superpowers-uninstall, lesson-frontmatter]
priority: high
symptom: [kb:evidence, 3-step-evidence, N204, task-failure-auto-diagnosis, superpowers-zh, lesson-fm-broken]
solution: Verification — 命令/文件路径验证
related_files:
  - .ai-memory/evidence/templates/verification.md
  - .ai-memory/lessons/N204-task-failure-auto-diagnosis.md
  - scripts/hooks/check_lessons_updated.py
  - scripts/bootstrap/sync_skills.py
created_by: AI
last_updated: 2026-08-21
---
## Verification（验证结果）

$ python scripts/hooks/check_lessons_updated.py
$ python scripts/bootstrap/sync_skills.py --check
$ git grep superpowers-zh
$ git status --short
$ python scripts/hooks/check_evidence_completeness.py

预期/实际:

1. `check_lessons_updated.py` → ✅ 68 lessons validated (修复前 12 文件 frontmatter 破坏 + 9 文件缺 diff_keywords, 全部修复)
2. `sync_skills.py --check` → ✅ 4 skills + 1 rule 副本一致 (仅 2 个非阻塞 updated 时间戳警告)
3. `git grep superpowers-zh` → 残留引用均在 archive/历史文档 (docs/archive, _archive/, evidence history), 活跃文件 0 引用
4. `git status --short` → N188/N190/N194 显示 `R ... -> .ai-memory/_archive/lessons-retired/` (rename 正确)
5. `check_evidence_completeness.py` → active/ 扫描全 OK (清理空壳 2026-08-20-session 后)
