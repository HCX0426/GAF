# Solution

落地 [A] 无风险文档修正 + 登记 [B] TD（meta_audit 默认仅评估，用户确认"落地 [A] + 登记 [B]"）：
- **[A1]** lessons/README.md `next_n_id` 202→209（防撞号）。
- **[A2]** `active_n_count` 69→36、`retired_n_count` 16→22；正文"口径说明"段同步（lessons_count 60 / active 36 / archived 3 / retired 22）+ 数学关系更新为 36+22+3+15=76。
- **[A3]** failure-modes.md N192 链接从失效的 `docs/plans/...` 改指权威源 `.ai-memory/meta/env-hardrules-contextual.md §双调试视角硬约束 (N192)`。
- **[B]** 登记 TD-392（`sync_ai_memory` 自动维护 active/next，P1）、TD-393（tech-stack §9.4 hook 清单同步，P3）到 active-tech-debt.md，状态摘要更新为"🔧 2 项活跃"。