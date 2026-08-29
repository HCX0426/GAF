# scripts/ — GAF Automation Scripts Index

This directory hosts all automation scripts for the GAF knowledge system:
pre-commit hooks, knowledge-base synchronizers, lesson management, e2e
scenario runners, and shell entry points. All Python scripts target the
`gaf` conda environment and force UTF-8 stdout via `_encoding_safe.py`
(N92 Windows CJK mojibake fix).

## Directory Structure

```
scripts/
├── gaf_init.sh            # Entry point (bash) �?L1 hard-load + session
├── gaf-commit.sh          # git commit wrapper (bash) �?session/bypass/audit
├── gaf_capture.ps1        # PS5 UTF-8 command-capture helper
├── conftest.py            # pytest config �?adds subdirs to sys.path
├── _encoding_safe.py      # Library: UTF-8 stdout fix (imported by all CLI scripts)
├── frontmatter.py         # Library: YAML-less frontmatter parser
├── source_parser.py       # Library: cross-language source parser
├── symptom_synonyms.py    # Library: symptom taxonomy + synonym dict
├── sync_lock.py           # Library: cross-platform file-lock context manager
├── scan_empty.py          # Utility: empty dir/file scanner
├── layer_benchmark.py     # Utility: sync_ai_memory latency benchmark
├── step_checkpoint.py     # B1: per-step checkpoint (interrupted task resume)
├── check_big_change.py    # B2: N151 4-dim big-change check
├── probe_unknown_task.py  # B4: unknown task_type signal collector
├── select_reflection_checks.py  # P4: auto-select Y/N reflection items by diff
├── bootstrap/             # KB sync + session + env check + evidence lifecycle (11 scripts)
├── hooks/                 # Pre-commit / audit hooks (10 scripts)
├── lessons/               # Lesson management (6 scripts)
├── refactor/              # Large-file split template (TD-365)
├── e2e/                   # E2E test runner + scenarios
└── tests/                 # Unit tests (collected by pytest)
```

## Conventions

- Run Python scripts from the repo root: `python scripts/<subdir>/<name>.py`
  (the `gaf` conda env must be active; `gaf_init.sh` activates it).
- Library modules (`_encoding_safe`, `frontmatter`, `source_parser`,
  `symptom_synonyms`, `sync_lock`) live at the top level and are imported
  by scripts in subdirs via a sys.path bootstrap block at the top of each
  moved script.
- Pre-commit hooks are wired in `.pre-commit-config.yaml`; the `entry:`
  line uses `python scripts/<subdir>/<name>.py` so pre-commit's managed
  venv resolves the local modules.
- Tests live under `scripts/tests/` and are collected by pytest via
  `scripts/conftest.py` (adds the repo root + all subdirs to `sys.path`).

## Top-Level Scripts

| Script | Purpose | Invocation | Trigger |
|---|---|---|---|
| `gaf_init.sh` | v9.0 hard-constraint entry point: L1 hard-load + session active (fast), or pre-commit install + sync + L2 existence check (full). | `bash scripts/gaf_init.sh` (or `--fast` / `--full`) | AI task start (mandatory, see `project_rules.md` §6.1) |
| `gaf-commit.sh` | `git commit` wrapper: verifies session active (24h TTL), requires `GAF_BYPASS_REASON` for `--no-verify`, appends audit + hook logs. | `bash scripts/gaf-commit.sh -m "type(scope): subject"` | Manual commit (replaces raw `git commit`) |
| `gaf_capture.ps1` | PowerShell 5 UTF-8 command-capture helper: redirects a child command to a temp file and reads it back as UTF-8, bypassing PS5 cp936 stdout decoding. | `powershell -File scripts/gaf_capture.ps1 -Command "python scripts/bootstrap/sync_ai_memory.py"` | Manual (Windows PS5 only, when CJK output garbles) |
| `gaf_services.ps1` | **N194 unified service manager** (2026-07-28): start/stop/restart/status for Redis + Backend + Agent + Frontend. Ensures unique instance by killing stale processes before start. Replaces deleted root-level `start.bat` / `start.ps1` / `stop.bat` / `stop.sh`. | `powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 start` / `stop` / `restart` / `status` | Manual (replaces all root-level start/stop scripts) |
| `setup-dev-env.ps1` | **N194 relocated** (2026-07-28): one-shot Windows dev env deployer (Git/Redis/Miniconda/Node.js + conda gaf). Moved from repo root to `scripts/`. | `powershell -ExecutionPolicy Bypass -File scripts\setup-dev-env.ps1` | Manual (first-time env setup only) |
| `start_gaf_unix.sh` | **N194 relocated** (2026-07-28): Linux/macOS one-shot service launcher (Redis + Django + Agent + Frontend). Moved from repo root `start.sh`. Does NOT ensure unique instance — prefer Docker Compose for production Linux deploys. | `bash scripts/start_gaf_unix.sh` | Manual (Linux/macOS only) |
| `start_gaf.sh` | Bash entry point that runs `manage.py run_startup_checks` (spec §5) before `runserver`. Distinct from `start_gaf_unix.sh` (which starts all 4 services). | `bash scripts/start_gaf.sh` / `--dry-run` / `--skip-checks` | Manual (backend-only startup with cleanup) |

## bootstrap/ — KB Sync & Session

| Script | Purpose | Invocation | Trigger |
|---|---|---|---|
| `sync_ai_memory.py` | Core `.ai-memory/` KB synchronizer. Resolves `auto`/`derived-manual`/`manual` maintainer modes, rewrites derived files, queries lessons. | `python scripts/bootstrap/sync_ai_memory.py` / `--query <kw>` / `--dry-run` / `--index` / `--stats` | pre-commit hook + L3 on-demand query (`gaf-orchestrator` step_3) |
| `sync_skills.py` | v9.0 skill+rule 4+1 synchronizer (renamed from `sync_decision_tree`). Distributes `gaf-orchestrator` decision tree + `project_rules.md` to 4 SKILL.md copies. | `python scripts/bootstrap/sync_skills.py` / `--check` / `--changelog` | pre-commit hook (`--check`) + refactor branch |
| `sync_docs_index.py` | Generates `.ai-memory/meta/docs-index.md` from `docs/` markdown frontmatter (L2 hard-load bridge). | `python scripts/bootstrap/sync_docs_index.py` / `--check` / `--check --strict` | pre-commit hook (`--check`) + documentation branch |
| `sync_session_context.py` | Generates `.ai-memory/ref/session-context.md` snapshot (env, backend apps, recent commits, active tech debt / roadmap) for L2 hard-load. | `python scripts/bootstrap/sync_session_context.py` | `gaf_init.sh --full` + manual |
| `check_session_active.py` | Cross-platform 24h-TTL session guard (N58): binds to inode (Linux/macOS) or size+mtime fingerprint (Windows). | `python scripts/bootstrap/check_session_active.py --check` / `--create` | pre-commit hook (`--check`) + `gaf_init.sh` (`--create`) |
| `check_env.py` | Environment verifier: checks Python / Node.js / npm / Redis / Git / Docker dependencies are ready. | `python scripts/bootstrap/check_env.py` | Manual (env setup) + `gaf_init.sh --full` |
| `archive_evidence.py` | Evidence lifecycle management (TD-252): `status` reports active/archived/candidates; `archive --apply` moves dirs ≥30 days to `archived/<YYYY-MM>/`; `prune --apply` deletes archived dirs ≥90 days. | `python scripts/bootstrap/archive_evidence.py status` / `archive --dry-run` / `archive --apply` / `prune --dry-run` / `prune --apply` | Manual (monthly L3-1 health-check) |
| `audit_scripts.py` | Quarterly scripts/ audit: detects stale scripts (90 days untouched + no README reference) + missing frontmatter. | `python scripts/bootstrap/audit_scripts.py` / `--stale-days 180` / `--check` | Quarterly health-check (category N) + pre-commit hook (`--check`) |
| `build_memory_index.py` | C1 治本机制: builds ChromaDB collection from `.ai-memory/` 4 dirs for semantic search fallback when fuzzy keyword matching returns 0 results. Reuses `FastembedMultilingualEF` from `backend/gaf_ai/rag.py` (no new deps). | `python scripts/bootstrap/build_memory_index.py` / `--rebuild` / `--stats` | Manual (after major .ai-memory updates) |
| `split_active_tech_debts.py` | Tech-debt file slim down utility: migrates `## TD-NNN:` sections from `active.md` based on title state marker (`✅ FIXED` → `fixed.md`, `❌` → `wontfix.md`, others kept). Inserts slim-down date marker + rebuilds priority list table. | `python scripts/bootstrap/split_active_tech_debts.py` | Manual (periodic active.md cleanup when closed TDs accumulate) |
| `scan_scripts_vs_readme.py` | CI scanner enforcing §5.5 (every new script must be in README.md). Walks `scripts/` recursively for `.py` files (excludes `__init__.py`), checks each basename as a whole word in README.md, reports drift. Lightweight companion to `audit_scripts.py` (which also checks mtime/frontmatter quarterly). | `python scripts/bootstrap/scan_scripts_vs_readme.py` / `--check` (quiet for pre-commit) / `--root <repo>` | pre-commit hook (CI drift guard) + manual (post new-script add) |
| `archive_low_trigger_lessons.py` | Archives lessons with low trigger counts to `lessons/archived-low-trigger/` (TD-380). | `python scripts/bootstrap/archive_low_trigger_lessons.py` / `--dry-run` | Manual (periodic lesson hygiene) |
| `auto_archive_specs.py` | Auto-archives completed specs from `docs/specs/active/` to `archived/<YYYY-MM>/` (1-day cooldown on `archived: true` / `status: FIXED/COMPLETED`). | `python scripts/bootstrap/auto_archive_specs.py` | pre-commit: folded into `gaf-governance-batch` (TD-377, 2026-08-23) |
| `jsonl_query.py` | Query tool for structured JSONL logs (`.cache/`/debug), filters by field/keyword. | `python scripts/bootstrap/jsonl_query.py` / `--file <f>` / `--key <k>` | Manual (debug) |
| `sync_error_codes_i18n.py` | Syncs backend error codes into frontend i18n messages (backend ↔ frontend contract). | `python scripts/bootstrap/sync_error_codes_i18n.py` / `--check` | Manual + pre-commit (i18n drift guard) |
| `sync_tech_debt_archive.py` | Syncs active-tech-debt archive state (fixed/wontfix sections) across tech-debt files. | `python scripts/bootstrap/sync_tech_debt_archive.py` | Manual (after tech-debt changes) |
| `track_n_trigger.py` | Tracks N## trigger counts in failure-modes.md (trigger_count + last_triggered columns). | `python scripts/bootstrap/track_n_trigger.py` | Manual (N-tracking updates) |

## hooks/ — Pre-commit / Audit Hooks

| Script | Purpose | Invocation | Trigger |
|---|---|---|---|
| `check_3step_evidence.py` | v8.3.1 3-step evidence validator: enforces today's evidence dir + problem/solution/verification files + runnable verification command. | `python scripts/hooks/check_3step_evidence.py` | pre-commit hook |
| `check_lessons_updated.py` | Lesson front-matter validator: enforces required fields (date, symptom, solution, related_files, created_by) per lesson contract. | `python scripts/hooks/check_lessons_updated.py` | pre-commit hook |
| `check_spec_consistency.py` | v8.3.1 spec/tasks/checklist cross-validator: ensures `spec.md`, `tasks.md`, `checklist.md` stay in sync. | `python scripts/hooks/check_spec_consistency.py` | pre-commit hook |
| `check_path_consistency.py` | N106/N107 path-consistency checker: flags inline path construction that should use module-level `SYNC_STATE` constants. | `python scripts/hooks/check_path_consistency.py` / `--root <repo>` / `--no-fail` / `--fix` | pre-commit hook |
| `check_git_status_after_hook.py` | N105 MM-state detector: detects files left in `MM` state after pre-commit hooks re-stage, preventing silent rollback. | `python scripts/hooks/check_git_status_after_hook.py` | pre-commit hook (post-hook) |
| `check_skip_rate.py` | v8.3 bypass-rate monitor: rolling 30-commit window, blocks push when bypass rate >= 30% (min 10 samples). | `python scripts/hooks/check_skip_rate.py` | pre-push hook |
| `post_commit_reflection_check.py` | N134 post-commit reflection guard: for 50+ line diffs, warns if reflection evidence (A/B/C classification) is missing. Exits 0 always. | `python scripts/hooks/post_commit_reflection_check.py` | post-commit hook |
| `check_yn_matrices_index.py` | R10 governance audit fix: validates `.ai-memory/meta/yn-matrices.md` (slice index) vs actual `### N###` / `### §X.Y` headings inside each `yn-matrices/` sub-file. Blocks drift at commit time. | `python scripts/hooks/check_yn_matrices_index.py` | pre-commit hook (via `gaf_governance_batch`) |
| `gaf_governance_batch.py` | N171 batch runner: collapses 10 read-only governance checks (session/sync/3step/lessons/spec/skills/promote/docs/path/yn-matrices) into a single pre-commit hook invocation, reducing commit time from ~71s to ~5s (12x+ speedup). v2 import-based. | (invoked by pre-commit framework) | pre-commit hook (single venv batch) |
| `check_deps_sync.py` | D1 (2026-08-21) deps-drift guard: enforces bidirectional sync between `pyproject.toml` (`[project].dependencies` + `dev`/`ocr-paddle` groups) and `backend/requirements/{base,dev}.txt`; + pyproject version ⟷ `app_info.py` APP_VERSION (H22); + env 变量文档化 (代码 os.getenv 读取的变量必须在 `.env.example` 声明; `deploy/env.prod.example` ⊂ `.env.example`, N197). | `python scripts/hooks/check_deps_sync.py` / `--no-fail` / `--root <p>` | pre-commit hook (via `gaf_governance_batch` CHECKS) + manual |
| `gaf_post_commit_batch.py` | N171 batch runner: collapses 2 post-commit checks (`post_commit_reflection_check` + `select_reflection_checks`) into a single hook invocation. Non-blocking (post-commit cannot fail), only prints WARNINGS. | (invoked by post-commit framework) | post-commit hook (single venv batch) |
| `check_tier_alignment.py` | v9.2 Spec C-3 tier feedback (warn-only): classifies staged diff by actual added+deleted lines (<50 small / 50-500 medium / >500 big) and prints the mandatory checklist for that tier; reminds when a medium change touches no test files. Never blocks — enforcement stays with the B2 evidence hook. | `python scripts/hooks/check_tier_alignment.py` | pre-commit hook |

## lessons/ — Lesson & Knowledge Management

| Script | Purpose | Invocation | Trigger |
|---|---|---|---|
| `extract_lessons.py` | v8.3.1 auto lessons extractor (M0.D/M2.A): parses 4 data sources (code-rules, library-conflicts, bug-tracker, git log) into draft lessons with frontmatter. | `python scripts/lessons/extract_lessons.py` | Manual (lesson backfill) |
| `promote_lessons.py` | M0.M promotion loop: scans `.ai-memory/lessons/` and suggests promotions to 4 target files by `priority` + cross-ref count. v9.2 Spec A adds Active-cap enforcement: `--enforce-cap` mechanically clears stale entries (last_triggered >60d && trigger_count ≤3 && not rules-referenced) down to `ACTIVE_N_CAP=35`; `--check-cap` is the ratchet commit-time guard (blocks only when clearable candidates remain). | `python scripts/lessons/promote_lessons.py --dry-run` / `--apply` / `--stats` / `--enforce-cap --apply` / `--check-cap` | pre-commit hook (`--dry-run`, `--check-cap`) + lesson collect (`gaf-lesson-router`) |
| `append_lesson_block.py` | Idempotent markdown block appender: appends a block to a target `.md` only when a marker is absent. Consolidates one-off `_append_n*.py` helpers. | `python scripts/lessons/append_lesson_block.py --target <f> --marker "### N##:" --block <block.md>` / `--dry-run` | Manual (lesson N## registration) |
| `weekly_summary.py` | M2.E weekly summary: scans `.trash/.e2e-failures.log` + `meta/why-skipped.md`, aggregates high-frequency failures, proposes lessons/failure-modes. | `python scripts/lessons/weekly_summary.py` / `--days 7` / `--apply` | Weekly (manual or scheduled) |
| `bypass_weekly_review.py` | Weekly review of `--no-verify` bypass reasons mined from `.gaf_audit.log`; appends to `.ai-memory/ops/bypass-patterns.md`. | `python scripts/lessons/bypass_weekly_review.py` / `--audit-log <f>` / `--output <f>` | Weekly (manual; paired with `gaf-commit.sh` audit log) |
| `generate_architecture_mistakes_summary.py` | Reads `.ai-memory/summaries/architecture-mistakes.md` and writes a curated summary table to `docs/architecture/architecture-mistakes-summary.md`. | `python scripts/lessons/generate_architecture_mistakes_summary.py` | Manual (after arch-mistakes updates) |
| `match_lessons_by_diff.py` | M3 diff→lesson trigger: matches the just-committed diff (paths + added lines) against lesson front-matter `diff_keywords`, lists related lessons (advisory, exit 0). | `python scripts/lessons/match_lessons_by_diff.py --base HEAD~1 --head HEAD` | post-commit hook (`gaf-lesson-diff-trigger`) |

## E2E Test Runner

| Script | Purpose | Invocation | Trigger |
|---|---|---|---|
| `e2e/run_all.py` | M2.B end-to-end runner for the 7 canonical AI scenarios (cold_start, new_feature, bug_fix, documentation, refactor, cross_repo, + browser_login). Writes per-scenario verdict + `.trash/.e2e-failures.log`. | `python scripts/e2e/run_all.py` / `python scripts/e2e/run_all.py cold_start` / `--strict` | Manual + `[manual]` pre-commit stage + CI |
| `e2e/conftest.py` | Shared fixtures + path setup for e2e pytest; exports `SCENARIO_NAMES` (mirrors `spec/tasks.md` §3.2.2). | (imported by pytest) | pytest collection of `scripts/e2e/tests/` |
| `e2e/scenarios/browser_login.py` | Playwright browser login scenario: headless Chromium, logs in as admin, asserts redirect to `/dashboard`, records console/page errors. | (called by `e2e/run_all.py`; standalone via `playwright install chromium` first) | `python scripts/e2e/run_all.py browser_login` |
| `e2e/scenarios/ai_qa_chat.py` | Playwright AI QA chat scenario: login → /ai/qa → send message → verify LLM reply rendered. Regression for commit 6a32763 (model_name NameError + QAPanel wrong endpoint). | (called by `e2e/run_all.py`; requires dev servers + LLMConfig configured) | `python scripts/e2e/run_all.py ai_qa_chat` |
| `e2e/scenarios/console_monitor.py` | **AI 默认监控入口**（project_rules §1.1.2）：headed Chrome + 自动登录 + 全量 console/pageerror/requestfailed/click 监听 → `.trash/console_monitor.log`。用户关闭浏览器停止。打开 GAF 界面时必启动此脚本，AI 定时读取日志，发现问题立即登记。 | `conda run -n gaf python scripts/e2e/scenarios/console_monitor.py` | **打开 GAF 界面时必启动**（long_running_process）+ AI 每 2-5 分钟读日志 + 用户关闭后读最终日志 |
| `e2e/scenarios/console_verify.py` | Headless regression check: visits a list of routes, fails if any `[ERROR]`/`[WARNING]` matching `EXPECTED_ISSUES_FIXED` patterns remain. Extends `PAGES_TO_VERIFY` + `EXPECTED_ISSUES_FIXED` when new categories are introduced. | `conda run -n gaf python scripts/e2e/scenarios/console_verify.py` | Manual (post-fix regression check) + after antd upgrades |
| `e2e/scenarios/devices_control_mode.py` | Playwright E2E: device center control mode toggle (autonomous/manual). Regression for control-mode state machine + WS message routing. | (called by `e2e/run_all.py`; requires dev servers) | `python scripts/e2e/run_all.py devices_control_mode` |
| `e2e/scenarios/verify_task_result_e2e.py` | Playwright E2E verification for I1 task.result WS protocol fix: login → WS connect → device center page render → 0 JS errors. Verifies `backend/agents/consumers.py` task.result handler registration + WS channel connectivity. | `conda run -n gaf python scripts/e2e/scenarios/verify_task_result_e2e.py` | Manual (post-fix verification for task.result handler) + requires dev servers running |
| `e2e/scenarios/execute_path_smoke.py` | Browser-first real execution-path smoke (testing-conventions §1.1): login → click task execute → observe executions page until terminal status. Proves dispatch→WS→agent-ack→result→persist chain end-to-end. | `conda run -n gaf python scripts/e2e/scenarios/execute_path_smoke.py --task <关键词>` | Manual (after dispatch-chain/UI changes) + requires dev servers + online Agent + Playwright |
| `e2e/scenarios/__init__.py` | Scenarios package init; re-exports `run_browser_login`, `run_devices_control_mode`, `run_ai_qa_chat`. | (imported) | package import |
| `e2e/fixtures/mock_agent.py` | Mock agent stub: returns a deterministic response for e2e tests without spinning up the real backend. | (imported by `e2e/run_all.py` + e2e pytest) | e2e test runs |

## refactor/ — Large-File Split Template (TD-365)

| Script | Purpose | Invocation | Trigger |
|--------|---------|-----------|---------|
| `refactor/split_large_python_file.py` | Template for splitting a large Python module into mixin modules (AST-precise method boundaries incl. decorator lines; header reuse; re-export `__all__`; forwarding indirection for test patch points). Proven on s34 views.py (view_sets package) + s35 pipeline_engine.py (7 modules). Edit CONFIG section (SRC/GROUPS/EXTRA_IMPORTS/EXTRA_CODE) per target, then run. | `python scripts/refactor/split_large_python_file.py` (adapt config first) | TD-365 large-file governance; run 8-item checklist in `lessons/N202-large-file-split-patch-point-contract.md` before use |

## governance/ — Doc Health Checkers (spec-41)

| Script | Purpose | Invocation | Trigger |
|--------|---------|-----------|---------|
| `governance/doc_health_check.py` | Static-layer 7-dimension doc health scan, produces `.cache/doc_health_report.json` for AI consumption at session start. Read-only. | `python scripts/governance/doc_health_check.py [--output PATH] [--no-fail]` | `gaf_init.sh --full` (every session start) |
| `governance/thresholds.yaml` | Centralized thresholds for all 7 dimensions (d1_overlap / d2_bloat / d3_count_drift / d4_path_drift / d5_frontmatter / d6_staleness / d7_index_consistency). | (read by `doc_health_check.py`) | — |
| `governance/report_schema.py` | JSON schema dataclasses (`Issue` / `ReportSummary` / `DocHealthReport`) for the report; handles stable `Issue.id` hashing. | (imported by `doc_health_check.py` + dimension modules) | — |
| `governance/check_dimensions/d1_overlap.py` | d1: Jaccard similarity on `summary` keywords across `docs/` + `.ai-memory/`. P2 ≥ 0.6 / P1 ≥ 0.8. | (imported by `doc_health_check.py`) | — |
| `governance/check_dimensions/d2_bloat.py` | d2: per-file line-count thresholds (default 1000; severity multipliers 1.5x→P2 / 2.0x→P1 / 3.0x→P0). | (imported by `doc_health_check.py`) | — |
| `governance/check_dimensions/d3_count_drift.py` | d3: hardcoded N##/doc counts vs actual (via `d3_counters.py` helpers). P1 on drift / P2 when source missing. | (imported by `doc_health_check.py`) | — |
| `governance/check_dimensions/d4_path_drift.py` | d4: frontmatter `related_files` + body paths (`file:///`, backtick paths) existence check. P0 on missing. | (imported by `doc_health_check.py`) | — |
| `governance/check_dimensions/d5_frontmatter.py` | d5: 3-mode frontmatter compliance (auto / derived-manual / manual) — required-fields check. P1 on missing. | (imported by `doc_health_check.py`) | — |
| `governance/check_dimensions/d6_staleness.py` | d6: `last_updated` age (60/90/180 days → P2/P1/P0) refined by `git log` commit count on `applies_to` modules. | (imported by `doc_health_check.py`) | — |
| `hooks/check_section_numbers.py` | 规范文档章节序号一致性检查 (2026-08-29): 扫描 api-contract / backend-conventions / frontend-conventions 的 `## N.` 顶层章节, 重复序号 → 阻断, 跳号 → 警告. 防"新增章节时重号" (本次 TD-420/421 §19 冲突重演防护). | `python scripts/hooks/check_section_numbers.py [--no-fail]` | `gaf_governance_batch` (commit 热路径) |
| `governance/check_dimensions/d7_index_consistency.py` | d7: 3-way N## diff (failure-modes.md vs lessons/README.md vs yn-matrices/_*.md). A-B→P1 / B-A→P2 / A-C→P2. | (imported by `doc_health_check.py`) | — |
| `governance/audit_governance.py` | Governance system audit: runs all governance checks + dashboard, aggregates findings. | `python scripts/governance/audit_governance.py` / `--no-fail` | Manual (governance health review) |
| `governance/bump_cheatsheet_usage.py` | Bumps cheatsheet usage counters in cli-cheatsheet.md (derived-manual maintenance). | `python scripts/governance/bump_cheatsheet_usage.py` | Manual (cheatsheet maintenance) |
| `governance/check_change_scope.py` | Checks whether a change exceeds governance scope thresholds (diff size / cross-app count). | `python scripts/governance/check_change_scope.py` | Manual (big-change triage) |
| `governance/check_lesson_level.py` | Validates lesson priority/level classification (L0-L3) consistency. | `python scripts/governance/check_lesson_level.py` | Manual (lesson hygiene) |
| `governance/cleanup_cheatsheet.py` | Cleans stale/duplicate entries in cli-cheatsheet.md. | `python scripts/governance/cleanup_cheatsheet.py` | Manual (cheatsheet cleanup) |
| `governance/gen_reflection_checks.py` | Generates Y/N reflection checklists from failure-modes (N167 reflection automation). | `python scripts/governance/gen_reflection_checks.py` | Manual (reflection setup) |
| `governance/governance_dashboard.py` | Prints a governance dashboard (checks pass/fail + drift summary). | `python scripts/governance/governance_dashboard.py` | Manual (governance overview) |
| `governance/lifecycle_report.py` | Lesson/document lifecycle report (created/updated/retired counts). | `python scripts/governance/lifecycle_report.py` | Manual (lifecycle review) |
| `governance/monthly_health_check.py` | Monthly 7-dimension health check aggregator (runs doc_health + governance). | `python scripts/governance/monthly_health_check.py` / `--no-fail` | Manual (monthly) |
| `governance/n181_retirement_eval.py` | Evaluates rule retirement candidates (N181 condition evaluation). | `python scripts/governance/n181_retirement_eval.py` | Manual (rule retirement) |
| `governance/retire_lessons.py` | Retires lessons to `_archive/` based on staleness/priority criteria. | `python scripts/governance/retire_lessons.py` / `--dry-run` | Manual (lesson retirement) |
| `governance/retire_rules.py` | Retires obsolete rules from rules docs (N## → archived). | `python scripts/governance/retire_rules.py` / `--dry-run` | Manual (rule retirement) |
| `governance/scan_hardcoded_patterns.py` | Scans for hardcoded patterns (paths/URLs/versions) violating normalization rules. | `python scripts/governance/scan_hardcoded_patterns.py` / `--check` | Manual + pre-commit (drift guard) |
| `governance/spec_dependency_graph.py` | Builds spec dependency graph (specs → related specs/docs). | `python scripts/governance/spec_dependency_graph.py` / `--json` | Manual (spec planning) |
| `governance/sync_spec_index.py` | Syncs `docs/specs/` index file with actual spec files (drift guard). | `python scripts/governance/sync_spec_index.py` / `--check` | pre-commit hook (spec index drift) + manual |
| `governance/sync_tech_debt_counts.py` | Syncs tech-debt counts across active/archive tables. | `python scripts/governance/sync_tech_debt_counts.py` | Manual (after TD changes) |

## Library Modules (top-level, imported by subdir scripts)

| Module | Purpose | Import Pattern |
|---|---|---|
| `_encoding_safe.py` | N92 Windows CJK mojibake fix: reconfigures stdout to UTF-8. Imported as the first statement in every CLI script. | `import _encoding_safe  # noqa: F401` |
| `frontmatter.py` | Tiny YAML-less frontmatter parser shared by `sync_docs_index.py`, `check_lessons_updated.py`, `promote_lessons.py`. | `from frontmatter import parse` |
| `source_parser.py` | M1.B cross-language source parser: extracts classes/functions/constants/headings from 5 languages + fallback for `.ai-memory/` `auto` files. | `from source_parser import parse_source` |
| `symptom_synonyms.py` | Symptom taxonomy + synonym dictionary (N89): single source of truth for `sync_ai_memory.py --query` synonym expansion. | `from symptom_synonyms import SYNONYMS` |
| `sync_lock.py` | M1.G cross-platform file-lock context manager (fcntl on Linux/macOS, msvcrt on Windows) used by `sync_ai_memory.py` to prevent concurrent-run races. | `with FileLock(path):` / `python scripts/sync_lock.py` (self-test) |

## Utilities (top-level)

| Script | Purpose | Invocation | Trigger |
|---|---|---|---|
| `scan_empty.py` | Empty directory/file scanner: scans project for empty dirs (excluding .git/node_modules/etc) and empty files (excluding __init__.py/.gitkeep/etc). | `python scripts/scan_empty.py [root_dir]` | Monthly health check (category N) |
| `layer_benchmark.py` | M1.G performance-tier benchmark: measures `sync_ai_memory` latency against L1 (<1s) / L2 (<5s) / L3 tiers. | `python scripts/layer_benchmark.py` / `--stress 1000` / `--json report.json` | Manual (performance regression checks) |
| `step_checkpoint.py` | B1 治本机制: per-step checkpoint files for interrupted task resume. Writes `.ai-memory/session/<task_id>.json` so tasks resume at exact step (not spec phase level). | `python scripts/step_checkpoint.py mark <task_id> <task_type> <step>` / `next <task_id>` / `list` / `done <task_id>` | `gaf-orchestrator` step transitions (B1) |
| `check_big_change.py` | B2 治本机制: N151 4-dimension objective check for "big change" (diff > 500 / cross-app ≥ 2 / new migration / API contract files). Triggers N151 5-step flow. | `python scripts/check_big_change.py` / `--base HEAD~2 --head HEAD` / `--json` | Manual + orchestrator big-change detection (B2) |
| `probe_unknown_task.py` | B4 治本机制: collects 3 signal types (active roadmap / recent specs / conversation keywords) to help AI determine task_type when unknown. | `python scripts/probe_unknown_task.py` / `--json` | `gaf-orchestrator` step_1 unknown branch (B4) |
| `select_reflection_checks.py` | P4 治本机制: auto-selects 3-6 Y/N reflection items by git diff keywords (models.py → N112/N128; sync_*.py → N116/N117; etc.). Replaces 24-item manual selection. | `python scripts/select_reflection_checks.py --diff HEAD~1` | post-commit hook (via `gaf_post_commit_batch`) |
| `gaf_daemon.py` | TD-352 service daemon: process manager + watchdog auto-restart (start/stop/restart/status/monitor), replaces gaf_services.ps1 orchestration. PID: `debug/gaf_daemon.pid`. Since spec 2026-08-29-services-management-monitor: captures each service stdout/stderr to `debug/system/services/<name>.log` (5MB rotate, was DEVNULL). | `python scripts/gaf_daemon.py start` / `status` / `stop` | Manual + `gaf_services.ps1` integration |
| `services/health.py` | spec 2026-08-29 service health probes: 4 app-level checks (redis PING / backend /api/v2/system/healthz/ / agent DB heartbeat / frontend HTTP), writes `debug/health-status.json` (+ process/error scan `scan_log_errors`, 近 1h 时间窗口过滤历史报错); consumed by gaf_daemon watchdog + monitors/status + monitors/services. | `python scripts/services/health.py --check --write` | import by `gaf_daemon.py` (`_run_health_checks`) |
| `inspect_ocr_debug.py` | OCR debug PNG inspector: verifies ROI (blue) vs text (red) box positions via HSV masking. | `python scripts/inspect_ocr_debug.py <path-to-ocr-debug.png>` | Manual (OCR debug) |
| `scan_hardcoded_chinese.py` | Scans source for hardcoded Chinese strings (i18n leak detection). | `python scripts/scan_hardcoded_chinese.py` | Manual (i18n audit) |
| `sync_brown_dust_pipelines_to_db.py` | Syncs `resources/<game>/tasks/*.json` pipeline definitions into DB tasks (`task_definition` + `execution_mode='pipeline'`). tasks/ is the single source (pipelines/ retired, N191). | `python scripts/sync_brown_dust_pipelines_to_db.py` / `--game <g>` / `--dry-run` | Manual (after tasks/ JSON edits) |
| `test_get_email_real.py` | Real-device smoke test: runs BrownDust-II get_email pipeline against the live game window; verifies auto-discover + end-to-end execution + structured JSONL. | `conda run -n gaf python scripts/test_get_email_real.py` | Manual (real-device verification, N196 workflow) |
| `security/check_sensitive_files.py` | Security audit: detects sensitive files (.env, credentials) staged/tracked in git. | `python scripts/security/check_sensitive_files.py` | pre-commit + manual (security audit) |

## Unit Tests (`scripts/tests/`)

Collected by pytest via `scripts/conftest.py` (repo root + all subdirs on `sys.path`).
Run with: `conda run -n gaf python -m pytest scripts/tests/`.

| Test | Validates |
|---|---|
| `tests/test_bootstrap_gaf.py` | `gaf_init.sh` bootstrap behavior |
| `tests/test_gaf_commit_wrapper.py` | `gaf-commit.sh` session/bypass/audit logic |
| `tests/test_gaf_init_shell.py` | `gaf_init.sh` fast/full mode split |
| `tests/test_session_active.py` | `check_session_active.py` 24h TTL binding |
| `tests/test_check_3step_evidence.py` | 3-step evidence validator rules |
| `tests/test_check_git_status_after_hook.py` | N105 MM-state detector |
| `tests/test_check_skip_rate.py` | bypass-rate window/threshold logic |
| `tests/test_evidence_content.py` | evidence file content contract |
| `tests/test_extract_lessons.py` | lesson extractor frontmatter generation |
| `tests/test_cross_language_parser.py` | `source_parser.py` multi-language parsing |
| `tests/test_decision_tree_sync.py` | `sync_skills.py` decision-tree hash sync |
| `tests/test_sync_ai_memory.py` | KB synchronizer modes + query |
| `tests/test_sync_changelog.py` | `sync_skills.py --changelog` tracking |
| `tests/test_sync_conflict.py` | `sync_lock.py` concurrent-run safety |
| `tests/test_sync_lock.py` | file-lock backend selection |
| `tests/test_layer_benchmark.py` | benchmark tier measurement |
| `tests/test_e2e_run_all.py` | e2e runner scenario dispatch |
| `tests/e2e_smoke_test.py` | e2e smoke harness |
| `tests/test_archive_evidence.py` | `archive_evidence.py` lifecycle (status/archive/prune + dry-run/apply, 13 tests) |
| `tests/test_bypass_weekly_review.py` | `bypass_weekly_review.py` audit-log mining + pattern aggregation |
| `tests/test_select_reflection_checks.py` | `select_reflection_checks.py` P4 keyword → Y/N auto-selection |

## Quick Reference

- AI task start: `bash scripts/gaf_init.sh`
- Commit: `bash scripts/gaf-commit.sh -m "type(scope): subject"`
- Lesson query (L3): `python scripts/bootstrap/sync_ai_memory.py --query <keyword>`
- Full sync: `python scripts/bootstrap/sync_ai_memory.py` (+ `sync_skills.py` + `sync_docs_index.py`)
- Lesson promotion: `python scripts/lessons/promote_lessons.py --dry-run`
- E2E run: `python scripts/e2e/run_all.py`
- Benchmarks: `python scripts/layer_benchmark.py`
- Unit tests: `conda run -n gaf python -m pytest scripts/tests/`
