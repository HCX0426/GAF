# TD-343 + TD-346: 低触发 lesson 归档 + governance_dashboard 计数漂移修复

> **关联 TD**: TD-343 (低触发 lesson 归档) + TD-346 (governance_dashboard 计数漂移)
> **来源**: `docs/tech-debt/active.md` TD-343 + TD-346
> **状态**: 🔧 待修 → 🚧 进行中 → ✅ 完成
> **优先级**: P3 (合并)
> **登记时间**: 2026-08-08
> **完成时间**: 2026-08-08

---

## 1. 问题描述

### 1.1 TD-343: 低触发 lesson 归档

`track_n_trigger.py` 统计显示 73 个 Active N## 中 **15 个 trigger_count = 1**（占比 20.5%），超过 N189 校准后的目标 < 10%。这些低触发 N## 仍占 failure-modes.md §Active 索引空间，增加 AI L1 加载负担。

`archive_low_trigger_lessons.py` 脚本已存在但 `is_recent_entry()` 函数有 bug：
- 只检查 `last_triggered == "-"`（从未触发），未实现真正的日期比较
- 应检查是否在最近 14 天内创建，而不是仅检查 "-"

### 1.2 TD-346: governance_dashboard 计数漂移

`governance_dashboard.py` 的 §3 `collect_lessons_counts()` 从 `lessons/README.md` frontmatter 读取 `active_n_count`（手工维护，可能滞后），而 §4 `collect_failure_modes_counts()` 从 `failure-modes.md` 实时 grep（实时准确）。两个数据源口径不同导致漂移。

---

## 2. 修复方案

### 2.1 TD-343: 修复 archive_low_trigger_lessons.py

**`is_recent_entry()` 修复**:
- 当前实现只检查 `last_triggered == "-"`，返回 True（跳过归档）
- 改为：解析 `last_triggered` 日期，如果距离今天 ≤ 14 天则跳过
- 如果 `last_triggered == "-"`（从未触发），允许归档

**执行归档**:
```bash
# 1. 先 dry-run 确认
D:\code\environment\conda\envs\gaf\python.exe scripts/bootstrap/archive_low_trigger_lessons.py --dry-run --threshold 1

# 2. 执行归档
D:\code\environment\conda\envs\gaf\python.exe scripts/bootstrap/archive_low_trigger_lessons.py --execute --threshold 1
```

### 2.2 TD-346: 修复 governance_dashboard.py 计数漂移

修改 `collect_lessons_counts()`，接受 `failure_modes_path` 参数，用 `collect_failure_modes_counts()` 的结果覆盖 `active_n_count`、`retired_n_count`、`dormant_n_count` 字段：

```python
def collect_lessons_counts(
    lessons_readme: Path,
    failure_modes_path: Optional[Path] = None,
) -> Dict[str, int]:
    """..."""
    result = {f: 0 for f in LESSONS_FIELDS}
    # ... 从 README.md 读取 lessons_count, archived_n_count ...
    
    # 如果提供了 failure_modes_path，覆盖 active/retired/dormant 计数
    if failure_modes_path:
        fm_counts = collect_failure_modes_counts(failure_modes_path)
        result["active_n_count"] = fm_counts["active"]
        result["retired_n_count"] = fm_counts["retired"]
        result["dormant_n_count"] = fm_counts["dormant"]
    
    return result
```

---

## 3. 任务清单

### Task 1: 修复 archive_low_trigger_lessons.py

- [x] 1.1 修复 `is_recent_entry()` 函数：实现真正的日期比较（14 天内跳过）
- [x] 1.2 修复逻辑：`last_triggered == "-"` 不再跳过（从未触发的也归档）
- [x] 1.3 `--dry-run` 验证归档候选列表
- [x] 1.4 `--execute` 执行归档
- [x] 1.5 验证 failure-modes.md 更新正确
- [x] 1.6 验证 lessons/README.md 计数更新正确

### Task 2: 修复 governance_dashboard.py (TD-346)

- [x] 2.1 修改 `collect_lessons_counts()` 接受 `failure_modes_path` 参数
- [x] 2.2 修改 `main()` 传递 `failure_modes_path`
- [x] 2.3 验证：§3 active_n_count == §4 Active count

### Task 3: 测试验证

- [x] 3.1 运行 `test_governance_dashboard.py` 确认通过（20 passed, 2 skipped）
- [x] 3.2 运行 `governance_dashboard.py --dry-run` 确认 §3 == §4

---

## 4. 验证标准

| # | 验证项 | 期望 | 验证方式 |
|---|--------|------|----------|
| 1 | 低触发 N## 占比 < 10% | 归档后 §Active 中 trigger_count ≤ 1 的占比 < 10% | `archive_low_trigger_lessons.py --dry-run` |
| 2 | failure-modes.md 有 Archived-Early 段 | 含 `### Archived-Early N## 索引` | 文件检查 |
| 3 | governance_dashboard §3 == §4 | §3 active_n_count == §4 Active count | 运行 dashboard |
| 4 | 原测试通过 | `test_governance_dashboard.py` 全通过 | pytest |

---

## 5. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/bootstrap/archive_low_trigger_lessons.py` | 修改 | 修复 `is_recent_entry()` 日期比较 |
| `scripts/governance/governance_dashboard.py` | 修改 | `collect_lessons_counts()` 接受 failure_modes_path |
| `.ai-memory/meta/failure-modes.md` | 修改 | 自动更新（归档脚本执行） |
| `.ai-memory/lessons/README.md` | 修改 | 自动更新（归档脚本执行） |
| `.ai-memory/meta/archived-lessons.md` | 修改 | 自动更新（归档脚本执行） |
| `docs/business/ops/governance-dashboard.md` | 修改 | 自动更新（dashboard 脚本执行） |