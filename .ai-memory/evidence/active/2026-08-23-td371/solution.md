# TD-371 solution

- **① gaf_init.sh 计数口径限定 Active 段**（已提交 -, 2026-08-21）：将
  `N_COUNT=$(grep -cE "^\| N[0-9]+" failure-modes.md)` 改为
  `N_COUNT=$(awk '/^## Active/{f=1;next} /^## /&&f{f=0} f' failure-modes.md | grep -cE "^\| N[0-9]+")`，
  只统计 `## Active` 到下一个 `## ` 之间的行。
- **② 执行 N181 退役评估**（2026-08-23 本会话）：`python scripts/governance/n181_retirement_eval.py --check`（CI 只读模式，不修改文件）生成评估报告。
- **③ failure-modes.md 动态计数**（已就位）：line 27 / line 46 已注明 "动态计数 — 不硬编码 N## 数量; 由 sync_ai_memory.py / gaf_init.sh 自动统计"，无需硬编码声称值。
- **范围边界**: 评估报告的 32 个退役候选（条件 A: 最近 3 spec 未提及）需 AI/人工复核条件 B/C 后，按 project_rules §4.12 流程迁移至 §Retired，属独立治理动作，**不在 TD-371 闭环范围内**（TD-371 目标是修正计数口径 + 执行评估，非自动退役规则）。
