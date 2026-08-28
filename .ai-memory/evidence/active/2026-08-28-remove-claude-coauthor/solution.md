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
## Solution（解决步骤）

1. `git rev-list HEAD > .trash/hashes_before.txt`（记录改写前 2112 条 hash）
2. `git filter-branch -f --msg-filter "sed '/Claude Code/d'" -- -^..HEAD`（删除 Claude Code trailer 行, 803 秒完成）
3. `git rev-list HEAD > .trash/hashes_after.txt`（记录改写后 hash）, PowerShell 循环逐条对比确认 changed=1799
4. 运行 `.trash/update_hash_refs.py`（建立 old→new 前缀映射, 扫描 `docs/` 下 125 个 .md, 替换 1124 处短 hash 引用）
5. 运行 `.trash/verify_hash_refs.py`（全量扫描 1203 处 hash token, 校验仅 79 处占位符/日期假阳性残留）