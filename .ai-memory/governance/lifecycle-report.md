# GAF Governance Lifecycle Report

_Generated: 2026-08-08 13:27_

## Health Score: **A** (96.6%)

| Entity | Active | Dormant | Other | Total | Active Rate |
|--------|--------|---------|-------|-------|-------------|
| Cheatsheet entries | 29 | 0 | - | 29 | 100% |
| N## rules | 73 | 11 | 8 (retired) | 92 | 79% |
| Lessons | 73 | 69 (archived) | - | 142 | 51% |
| Scan patterns | 6 | 0 | - | 6 | 100% |
| Session traces | 0 (retained) | 0 (compressed) | 0 (deleted) | 0 | healthy |

## Cheatsheet Details

| Entry | Age (days) | Status |
|-------|-----------|--------|
| conda gaf env: `D:\code\environment\conda\envs\gaf\python.ex | 2 | active |
| Start all services: `scripts/gaf_services.ps1 start` (Redis  | 2 | active |
| Agent tests: `...\python.exe -m pytest agent/tests/ -p no:dj | 2 | active |
| Backend tests: `...\python.exe -m pytest backend/` (needs Dj | 2 | active |
| Use direct python.exe path (not `conda run`) to avoid PowerS | 2 | active |
| ... (24 more) | | |

## N## Rules Details

| N## | Topic | Status |
|-----|-------|--------|
| N91 | pre-commit hook 失败 | active |
| N95 | 分级分发缺位 | active |
| N105 | commit --no-verify 透传 bug | active |
| N106 | SYNC_STATE 路径常量 | active |
| N109 | 计划内任务仍问用户 | active |
| ... (68 more active) | | |

## Session Traces

- Total trace files: 0
- Retained (newest 20): 0
- Compressed (20-100): 0
- Deleted (>100): 0
- Retention status: healthy

## Scan Patterns

| Pattern | N## | Description | Hit Count | Status |
|---------|-----|-------------|-----------|--------|
| `/api/v2` | N197 | URL 归一化 | 1 | active |
| `action_type|next_step|retry_in` | N191 | Schema 统一 | 1 | active |
| `conda run -n gaf|python manage` | N188 | Conda 环境 | 1 | active |
| `<<EOF|<<'EOF'|\|\||&&` | N190 | PowerShell shell | 1 | active |
| `time\.sleep\(|sleep\(\d+\)` | N196 | 测试数据 | 1 | active |
| `grep|head\s|tail\s|sed\s|awk\s` | N190 | Windows 上的 Unix 命令 | 1 | active |

## Recommendations

- **N## Rules**: 2 active N## have trigger_count=0 or last_triggered>90d. Run `python scripts/governance/retire_rules.py --execute` to evaluate retirement.
