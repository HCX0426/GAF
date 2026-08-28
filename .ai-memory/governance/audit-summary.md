# GAF Governance Audit Summary

_Generated: 2026-08-06 22:53_
_Mode: DRY-RUN (no changes)_

## Audit Overview

- **cleanup_cheatsheet** [dry-run]: ✅ PASS
- **retire_rules** [dry-run]: ✅ PASS
- **execution_rate**: ✅ PASS
- **lifecycle_report**: ✅ PASS

## Cleanup Cheatsheet

  [OK] cheatsheet: 46 lines, 6 sections, 29 entries
  
  === Dormant Cheatsheet Entries (unused > 30 days) ===
  No dormant entries found.
  
  Summary: 0 dormant / 29 total entries

## Retire Rules

  === N## Rule Retirement Evaluation ===
  Active:   45 entries
  Dormant:  20 entries
  Retired:  7 entries
  
  No N## eligible for retirement.
  
  Not eligible: 45 N## (N91, N95, N106, N109, N111, N112, N116, N117, N118, N121...)
  
  Summary: 0 eligible / 45 total active

## Execution Rate

  === GAF 治理规则执行率报告 ===
  Period: last 30 days
  Total tasks: 0
  
  (无 N## 规则执行数据 — session-traces 目录为空或无近 30 天记录)
  
  报告已写入: D:\code\GAF\.ai-memory\governance\execution-rate-report.md

## Lifecycle Report

  Analyzing governance entities...
    Cheatsheet: 29 entries (29 active, 0 dormant)
    N## Rules: 45 active, 24 dormant, 8 retired
    Lessons: 10 active, 69 archived
    Session Traces: 0 files (healthy)
    Scan Patterns: 6 patterns (6 active, 0 dormant)
  
  Health Score: A (100.0%)
  
  Report written to: D:\code\GAF\.ai-memory\governance\lifecycle-report.md
  
  ============================================================
  # GAF Governance Lifecycle Report
  
  _Generated: 2026-08-06 22:53_
  
  ## Health Score: **A** (100.0%)
  
  | Entity | Active | Dormant | Other | Total | Active Rate |
  |--------|--------|---------|-------|-------|-------------|
  | Cheatsheet entries | 29 | 0 | - | 29 | 100% |
  | N## rules | 45 | 24 | 8 (retired) | 77 | 58% |
  | Lessons | 10 | 69 (archived) | - | 79 | 13% |
  | Scan patterns | 6 | 0 | - | 6 | 100% |
  | Session traces | 0 (retained) | 0 (compressed) | 0 (deleted) | 0 | healthy |
  
  ## Cheatsheet Details
  
  | Entry | Age (days) | Status |
  |-------|-----------|--------|
  ... (40 more lines)

## Next Steps

- Run `python scripts/governance/cleanup_cheatsheet.py --execute` to mark dormant entries in cheatsheet
- Run `python scripts/governance/retire_rules.py --execute` to move eligible N## rules to Dormant section
