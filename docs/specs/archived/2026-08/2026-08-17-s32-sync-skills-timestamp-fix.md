# s32 — sync_skills timestamp 自引用缺陷修复 (updated 永滞后循环)

> **类型**: fix (脚本缺陷) | **日期**: 2026-08-17 | **来源**: 用户第五次"继续" → 轻量 L3-1 扫描发现 sync_skills --check 报 5 个 SKILL.md updated 滞后 (s31 同步后仍报)
> **状态**: ✅ 已归档 (2026-08-17, commit -) | **归档位置**: `docs/specs/archived/2026-08/2026-08-17-s32-sync-skills-timestamp-fix.md`
> **关联**: sync_skills.py TD-323/spec-85 (timestamp 机制) / test_sync_skills_timestamps.py

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit hash | 验收 evidence |
|------|------|---------|------------|--------------|
| Phase 1 修复 cmd_update_timestamps 写 today | ✅ | 2026-08-17 | - | --update-timestamps 改写 today; 同步 commit 后 check 不再报 stale (收敛验证通过) |
| Phase 2 测试更新 + 回归 | ✅ | 2026-08-17 | - | test_sync_skills_timestamps.py +2 (写 today / 幂等); 10 passed |
| Phase 3 实际同步 + commit + 归档 | ✅ | 2026-08-17 | - | 5 个 SKILL.md updated=2026-08-17; 9 文件 131+/20-; pre-commit 全过 |

## 背景与根因

**现象**: 每次 `sync_skills.py --update-timestamps` 同步后, 提交 commit, 下次 `--check` 仍报 5 个 SKILL.md `updated` 滞后。永不收敛。

**根因 (self-referential timestamp loop)**:

```
check:      updated != git log 日期 → 报 stale
sync:       updated ← git log 日期 (同步前)
用户 commit: git log 日期变为今天, updated 还是同步前的旧日期
下次 check: updated (旧) != git log (今天) → 又报 stale → 死循环
```

例: SKILL.md 上次 commit 08-15 → sync 写 updated=08-15 → commit (08-17) → git log=08-17 vs updated=08-15 → stale。

**正确语义**: `updated` = **同步动作执行日** (今天)。因为同步 commit 后 git log 日期就是今天, check 比对才收敛。之后内容实质变更 commit (未来某日) → git log=未来日期 vs updated=今天 → stale ✓ 正确提示需再同步。

## Phase 1 详细任务

修改 `scripts/bootstrap/sync_skills.py` `cmd_update_timestamps()`:
- `last_commit` 值 → 改为 `datetime.date.today().isoformat()`
- 保留 `get_skill_last_commit_date` 用于 `--check` 比对 (不变)
- 输出文案: "updated 08-15 → 2026-08-17 (today)" 语义清晰

## 验收标准

1. 修改后: `--update-timestamps` 写 today; `--check` 立即收敛 (updated=today=git log today)
2. `test_sync_skills_timestamps.py` 更新: 新增/修改测试覆盖"同步写 today"语义
3. 实际执行: 5 个 SKILL.md updated=2026-08-17; commit 后 `--check` 全绿
4. 提交前 `git status` 无未暂存残留

## 已知限制

- 方案假设同步后立即 commit (用户手动 commit) — 若同步后不 commit, check 报 stale 是正确行为 (有未提交修改)
- git log 日期按 commit 日 (非 author 日), 与 sync_skills 现有 `%cs` 一致
- 不修改 `--check` 的比对逻辑 (updated != git log 语义正确)
