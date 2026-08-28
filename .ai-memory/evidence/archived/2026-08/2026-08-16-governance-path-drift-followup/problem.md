---
maintainer: manual
source: GAF spec-2026-08-15-governance-redundancy-consolidation followup
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: tech-debt 路径漂移 — docs/tech-debt/ 已迁移 docs/archive/ 但全链路残留旧路径引用
solution: 主治理 spec commit - 后, 2026-08-09 的 docs/tech-debt/ → docs/archive/ 迁移未全链路清理
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
## Problem（症状 / 触发条件）

1. 现象: 5 个 tech-debt 治理脚本 + project_rules/handbook + 3 个测试 fixture 仍引用 `docs/tech-debt/` 旧路径; README 计数 243 是旧 fixed.md 快照 (实际 fixed-tech-debt.md 索引表 123 行); d2_bloat 阈值指向不存在的 `docs/tech-debt/fixed.md`。
2. 触发条件: 2026-08-09 归档迁移 `docs/tech-debt/` → `docs/archive/` (active-tech-debt.md / fixed-tech-debt.md / fixed-tech-debt-details.md / wontfix-tech-debt.md / tech-debt-README.md) 后, 未做全链路引用清理。
3. 影响范围: tech-debt 治理工具失效 (sync 指向不存在路径) + README 计数漂移 (drift guard 误报/漏报) + N186 登记验证命令指向旧路径。