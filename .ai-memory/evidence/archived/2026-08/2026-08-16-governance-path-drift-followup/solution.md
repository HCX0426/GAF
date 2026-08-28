---
maintainer: manual
source: GAF spec-2026-08-15-governance-redundancy-consolidation followup
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: tech-debt 路径漂移全链路修复
solution: 5 脚本路径迁移 + fixed 计数语义修正 + rules/handbook/hook/测试同步 + N169 退役标注
related_files:
  - scripts/governance/sync_tech_debt_counts.py
  - scripts/governance/governance_dashboard.py
  - scripts/governance/monthly_health_check.py
  - scripts/bootstrap/sync_tech_debt_archive.py
  - scripts/bootstrap/split_active_tech_debts.py
  - .skills/rules/project_rules.md
  - docs/archive/tech-debt-README.md
created_by: AI
last_updated: 2026-08-16
---
## Solution（解决步骤）

1. N169 lesson frontmatter 加 `status: retired` + `superseded_by: N166`, README 同步 (N165 模式, 不合并 N174)
2. scripts/governance/sync_tech_debt_counts.py 路径迁移 docs/archive/ + fixed 计数改索引表行 (FIXED_INDEX_ROW_RE `^\|\s*\[TD-\d+\]`)
3. scripts/governance/governance_dashboard.py + monthly_health_check.py + check_tech_debt_counts.py 同步 archive 路径与索引计数
4. scripts/bootstrap/sync_tech_debt_archive.py + split_active_tech_debts.py 标休眠 + 路径常量更新
5. .skills/rules/project_rules.md (N186 grep 命令) + ai-operating-handbook + thresholds.yaml (d2_bloat 15000) + 测试 fixtures 同步; 跑 sync 归一化 README (243→123)