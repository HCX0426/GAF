---
topic: linkage-audit-followup
created_at: 2026-08-24
---

# Problem

GAF 规则文档体系联动性审计（2026-08-24, meta_audit，4 并行 agent 硬核验证）发现联动断链：
1. **计数严重漂移**: lessons/README.md frontmatter `active_n_count=69` 但 failure-modes §Active 表实际 36 条；`next_n_id=202` 但已分配至 N208（AI 按 202 写新 lesson 必撞号）；retired 16 vs 实际 22。
2. **L0 硬约束断链**: failure-modes.md N192 的 Lesson 链接指向 `docs/plans/2026-07-27-dual-debug-perspective-fixes.md`，但 `docs/plans/` 目录已不存在（真实文件在 `docs/specs/archived/2026-07/`）→ 404。
3. **文档滞后**: tech-stack §9.4 声称 pre-commit "10 checks"，实测 17（TD-377 折叠后）。

根因：`sync_ai_memory.py` 仅自动维护 `lessons_count`，不维护 `active_n_count`/`next_n_id`；计数由分散脚本/手动维护，随 Active 段增删不刷新。