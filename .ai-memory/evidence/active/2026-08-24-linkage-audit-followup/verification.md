# Verification

## Verification

- Read `.ai-memory/lessons/README.md`: frontmatter `active_n_count=36 / retired_n_count=22 / next_n_id=209`，正文"口径说明"与数学关系(76)自洽。
- Grep `failure-modes.md` N192: Lesson 链接指向 `.ai-memory/meta/env-hardrules-contextual.md §双调试视角硬约束 (N192)`，不再引用 `docs/plans/`。
- Grep `active-tech-debt.md`: 含 TD-392/TD-393 条目 + 状态摘要 "🔧 2 项活跃"。
- 规则联动校验（确保 A3 改指目标存在、未引入断链）：
  - `conda run -n gaf python scripts/bootstrap/sync_skills.py --check`
  - `conda run -n gaf python scripts/hooks/check_yn_matrices_index.py`
  - `conda run -n gaf python scripts/hooks/check_path_consistency.py`

## Verification (第二轮正确性回归 — 2026-08-24)

- failure-modes.md §Active 新增 N208 行，Active 计数 36→37；README frontmatter/正文/数学关系同步为 37/77。
- lessons/README.md line33 陈旧声明 "sync_ai_memory 自动校准 active_n_count" 已改为明确 "仅校准 lessons_count, active/retired/next 手动维护(TD-392)"。
- archived-lessons.md N119 引用由失效的 `testing_2026-06-17-n119-m2b-command-hang.md` 改为实际存在的 `N119-m2b-command-hang.md`。
- 回归: `check_path_consistency.py` → 0 error; N208(lessons/N208-commit-message-no-claim.md) + N119(lessons/N119-m2b-command-hang.md) 目标文件均存在。

## Verification (反向孤儿审计 — 2026-08-24)

- 反向孤儿扫描(lessons 文件 n_id vs failure-modes ∪ archived-lessons): 15 个历史低活跃 lesson(N95/N111/N116/N117/N118/N122/N124/N131/N132/N133/N135/N136/N137/N141/N145) 有文件但未入分级索引，仅靠 lessons README Topic 表软检索；属归档不完整整理项，非 N208 型功能断链(该型已清零)。
- 已登记 TD-394 统一归档整理(P3)。