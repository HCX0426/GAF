# GAF AI Cheat Sheet

<!-- meta: {version: "1.0", created: "2026-08-06", max_lines: 150} -->

## 环境与命令
- conda gaf env: `D:\code\environment\conda\envs\gaf\python.exe` (Python 3.11.15, 3.11+ required for StrEnum etc) <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- Start all services: `scripts/gaf_services.ps1 start` (Redis → Backend → Worker → Beat → Agent → Frontend) <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- Agent tests: `...\python.exe -m pytest agent/tests/ -p no:django -o addopts=""` (2.5min vs 2h, disables pytest-django) <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- Backend tests: `...\python.exe -m pytest backend/` (needs Django, no -p no:django needed) <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- Use direct python.exe path (not `conda run`) to avoid PowerShell CLIXML serialization <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->

## Shell (PowerShell)
- No bash heredoc `<<'EOF'` / `&&` / `||` — PowerShell rejects these at parse time <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- git commit with multi `-m` flags: `git commit -m "subject" -m "body paragraph"` (no `-F <file>`) <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- No `&&` chaining — use `;` (note: failure doesn't short-circuit) <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- No Unix commands (head/tail/grep/sed/awk) — use PowerShell equivalents or Trae tools <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- `conda run -n gaf` doesn't support multi-line `-c` — write temp .py file <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->

## 跨层约束
- API version from `GAF_API_PREFIX` env var, never hardcode `/api/v2` <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- URL route paths from `APP_ROUTES` mapping, never hardcode in `config/urls.py` <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- Schema changes MUST run data-flow full-chain scan (7-item checklist) — see N191 <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- ROI sub-image coords MUST add back ROI origin offset (common bug) <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- Task findings belong to current task — never throw to user as "suggestion" <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->

## 常见坑
- pytest-django forces `django.setup()`: disable with `-p no:django` for agent/scripts tests <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- pre-commit hook failure: don't blindly stash, check the failure reason first <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- `git stash`/`checkout .` MUST run `git status` first — can lose uncommitted work <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- No real `time.sleep` in tests — mock `time.time` or use `freezegun` <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- No real large files in tests (>10MB) — write 1-byte placeholder + mock `Path.stat` <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- No real network requests in tests — use `responses` / `httpx_mock` <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->

## 提交规范
- spec-68: no "continue?" prompts — AI proceeds to next TD/spec in circular mode <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- AskUserQuestion only for: rule-uncovered ambiguity / irreversible auth / scoring-fail / 4 hard scenarios <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- Commit size: 1 commit per spec (default); complex tasks can split <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- Always `git status` after `git add` before commit — verify staging state <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->

## 诊断脚本
- Hardcoded pattern scan: `python scripts/governance/scan_hardcoded_patterns.py --diff-only` <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- Change scope check: `python scripts/governance/check_change_scope.py` <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->
- Reflection evidence gen: `python scripts/governance/gen_reflection_checks.py --task-type <type> --diff-lines <N>` <!-- meta: {last_used: "2026-08-06", trigger_count: 0, expire_days: 90} -->

<!-- Usage: L2 hard-loaded via ai-operating-handbook.md. Updated as needed when new patterns are discovered. -->