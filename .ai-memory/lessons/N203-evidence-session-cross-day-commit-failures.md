---
title: "N203: pre-commit evidence/session 跨天失败三坑"
date: 2026-08-20
topic: commit-hooks
priority: medium
cross_refs: ["N126", "TD-321", "TD-342", "N105"]
symptom: [workflow=hook-failed, evidence-missing, session-expired]
solution: "跨午夜 commit 前先 check_session_active.py --create; evidence 目录按当天命名; verification.md 用 ## Verification 标题 + 行首命令"
diff_keywords: ["failure", "modes", "failure-modes", "ai", "operating", "handbook", "ai-operating-handbook", "workflow", "hook-failed", "evidence-missing", "session-expired"]
related_files:
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/meta/ai-operating-handbook.md
created_by: AI
---


# N203: pre-commit evidence/session 跨天失败三坑

> 来源: s45 commit 连续 3 次 hook 失败（跨午夜场景, 2026-08-19 23:xx → 2026-08-20 00:xx）

## 症状

s45 commit（feat 大修改, B2 触发）pre-commit 连续失败 3 轮：

1. `[governance-batch] FAILED: session active, 3-step evidence` — session 过期
2. `no evidence dir for today (2026-08-20) found` — evidence 目录日期是昨天
3. `verification.md: '## Verification' has no runnable command` — 段标题/格式不符

## 根因

1. **session 24h TTL**: `check_session_active.py` 创建时 `expires_at = now + 24h`，跨午夜长会话过期（s45 开工于 8-19 19:xx，commit 于 8-20 00:xx）
2. **evidence 目录日期前缀 = commit 当天**: `check_3step_evidence.py` 只认 `_today_dirs()`（`<date>-<task>` 且 date == today）。我创建于 8-19（`2026-08-19-s45-...`），commit 时已 8-20 → 不识别。修复：`git mv` 目录为 `2026-08-20-s45-...`
3. **verification.md 格式**: `_is_verification_runnable()` 要求 (a) 存在 `^##\s*Verification` 标题（`## 测试结果` 不认）; (b) 标题到下一个 `##` 之间至少一行以 `$|python|bash|sh|cmd|powershell|ps1|pip|conda|git|npm|pytest|ruff|mypy|pre-commit` 开头（表格内的命令不认，行首才认）

## 修复

1. `python scripts/bootstrap/check_session_active.py --create`（重建 session，24h TTL）
2. evidence 目录用当天日期创建/重命名（跨午夜先查 `Get-Date`）
3. verification.md 固定骨架: `## Verification` 标题 + ```bash 代码块内放行首命令（pytest/ruff/npm test 等）

## 预防（下次 commit 前自检）

```text
□ commit 时是否跨午夜（会话创建于昨天）? → 先跑 check_session_active.py --create
□ evidence 目录日期 == 今天? → 不等，创建时就按当天命名
□ verification.md 是否有 '## Verification' 标题 + 行首命令? → 先跑 check_3step_evidence.py 验证
□ 当天已有 evidence 目录（昨天遗留）? → 新任务另建新目录，不要复用旧目录
```