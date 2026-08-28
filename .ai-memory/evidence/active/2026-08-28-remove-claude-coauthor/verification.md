---
maintainer: manual
source: GAF
load_when: [evidence]
priority: high
symptom: [hash-rewrite, filter-branch, co-author, claude, doc-hash-sync]
solution: 去除 commit message 中的 Claude co-author trailer 并同步更新文档中的 commit hash 引用
created_by: AI
last_updated: 2026-08-28
---
## Verification（验证）

$ git log main --format='%an <%ae>' | Group-Object

预期输出：Count=2112, Name=`HCX0426 <chongxuan-huang@outlook.com>`（作者全部归一为 HCX0426）

$ git log main --format='%(trailers:key=Co-authored-by,valueonly)' | Where-Object { $_ } | Sort-Object -Unique

预期输出：`HCX0426 <chongxuan-huang@outlook.com>`（无 Claude）

$ git log main --format='%h %s' --grep='Claude' | Measure-Object -Line

预期输出：0（main 无任何 Claude 相关 commit）

$ D:\code\environment\conda\envs\gaf\python.exe .trash/verify_hash_refs.py

预期：stale/unresolved references = 79（均为 `a1b2c3d4`/`12345678`/日期等占位符假阳性，无真实失效 hash）