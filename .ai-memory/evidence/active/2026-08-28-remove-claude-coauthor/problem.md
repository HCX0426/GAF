---
maintainer: manual
source: GAF
load_when: [evidence]
priority: high
symptom: [hash-rewrite, filter-branch, co-author, claude, doc-hash-sync]
solution: 去除 commit message 中的 Claude co-author trailer,导致 1799 条 commit hash 变化,文档引用需同步替换
created_by: AI
last_updated: 2026-08-28
---
## Problem（症状 / 触发条件）

GitHub 贡献者列表中出现 Claude（来自 commit - 的 `Co-Authored-By: Claude <noreply@anthropic.com>` trailer）。
用户要求去除 Claude 署名、全部改为 HCX0426，因此必须改写历史。
改写 `-` 的 commit message 会导致该 commit 及之后 1799 条 commit hash 全部变化，
而 docs/ 下有 1203 处短 hash 引用（如 `-`）会失效。

## Solution（解决步骤）

1. `git rev-list HEAD > .trash/hashes_before.txt`（改写前基线 2112 条）
2. `git filter-branch -f --msg-filter "sed '/Claude Code/d'" -- -^..HEAD`（sed 删除 Claude Code trailer 行, 803s）
3. `git rev-list HEAD > .trash/hashes_after.txt`（改写后基线）, 对比确认 changed=1799
4. `.trash/update_hash_refs.py`（按 old→new 前缀映射, 扫描 docs/*.md 替换 1124 处短 hash）
5. `.trash/verify_hash_refs.py`（校验残留 79 处均为占位符/日期假阳性, 无真实失效引用）

## Verification（验证）

$ git log main --format='%an <%ae>' | Group-Object
$ git log main --format='%(trailers:key=Co-authored-by,valueonly)' | Sort-Object -Unique
$ git log main --grep='Claude'

预期：作者全部为 HCX0426；co-author 仅 HCX0426；main 无 Claude 字样。