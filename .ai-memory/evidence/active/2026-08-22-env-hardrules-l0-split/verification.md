---
maintainer: AI
source: GAF/.ai-memory/evidence/active/2026-08-22-env-hardrules-l0-split/verification.md
load_when: [evidence, 3-step-evidence]
priority: high
symptom: [kb:env-hardrules-l0-budget]
solution: 验证 L0 文件降至预算内 + 索引表指向 contextual
related_files:
  - .skills/rules/env-hardrules.md
created_by: AI
last_updated: 2026-08-22
---
## Verification（验证）

$ D:\code\environment\conda\envs\gaf\python.exe -c "import os; p='D:/code/GAF/.skills/rules/env-hardrules.md'; print('env-hardrules.md bytes:', os.path.getsize(p))"
$ git -C D:\code\GAF log --oneline -4

预期输出：env-hardrules.md 约 7.2KB (< 15KB 单文件预算)；最近 4 条 commit 含 env-hardrules L0 拆分 + N191 断链修复 + spec-context 补票。
