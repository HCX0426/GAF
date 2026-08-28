# TD-376 problem

- **症状**: M2 claimed-activation 记录 2026-08-18 后 3 次 REVIEW_TRIGGERED 触发 (-/N202, -/N192, -/N203) 均无复盘写回, 标记持续存在, 每 commit 被阻塞, 被迫形式化补复盘。
- **根因**: 原 `check_unclosed_review` 只判"标记后有无 📋 复盘", 不区分触发条件当前是否仍成立 (陈旧标记无法自然闭环)。
- **影响**: 治理形式化风险 (N189); M2 数据报警但无真实闭环。
