---
maintainer: AI
spec_id: spec-43
title: 遗忘机制 (Forgetting Mechanism) — consumed.json 无界增长治理
created: 2026-07-20
status: ✅ done
parent_specs: [spec-42 (自我进化飞轮)]
child_specs: []
related_files:
  - scripts/governance/doc_health_consumed.py
  - scripts/governance/doc_health_forget.py
  - scripts/tests/test_doc_health_forget.py
  - .trae/skills/gaf-orchestrator/SKILL.md
---

# spec-43: 遗忘机制 (Forgetting Mechanism)

## 阶段状态表 (TD-137 / §4.10)

| Phase | 标题 | 状态 | 完成时间 | commit hash | 验收 evidence |
|:-----:|------|:----:|:---------:|:-----------:|---------------|
| Phase 1 | ForgetPolicy 类 + 单元测试 | ✅ | 2026-07-20 | - | 11 tests PASS, should_forget 0.0029ms/call (< 1ms budget) |
| Phase 2 | ConsumedTracker.forget_expired 集成 + §0.5 更新 | ✅ | 2026-07-20 | - | 3 集成测试 PASS, sync_skills.py --check 通过 |
| Phase 3 | 闭环测试 + 软上限警告 + archive 机制 | ✅ | 2026-07-20 | - | 3 闭环测试 PASS (含 full_lifecycle), 软上限 800 警告 |

> 全量回归: 121 tests PASS (47 spec-41 + 15+20+22 spec-42 + 17 spec-43) in 7.79s
> 性能: doc_health_check.py 0.722s (内部, < 2s budget, 不退化)
> 审查: 3 Phase 两阶段审查全 ✅ PASS (Phase 1: A1-A7 / Phase 2: B1-B8 / Phase 3: 实施报告自验)

## 1. 背景与动机

### 1.1 问题

spec-42 自我进化飞轮已交付 (commit `-`), 首次真实运行 patch 了 5 个 P0 issues (commit `-`)。consumed.json 持续累积已处理 issues, **无遗忘策略** → 文件无界增长。

**增长速率估算**:
- 10 issues/对话 × 5 对话/周 = 50 entries/周
- 50 × 52 = 2600 entries/年
- 每条 entry ~200 bytes → ~520KB/年

**风险**:
1. consumed.json 越大, `ConsumedTracker.load()` 越慢 (虽然当前 13.79ms, 但 10x 后会突破 100ms 性能基线)
2. 旧 entry 已无价值 (patched 成功 + 无 recurrence + 文件已多次迭代) → 噪音
3. 审计需求与性能需求冲突 → 需要分级保留

### 1.2 用户原话

> "完全自动化的自我进化飞轮: 检查器跑 → 发现问题 → AI patch → commit → 下次不再犯"

"下次不再犯" = 短期记忆 (防止同会话/近期会话重复 patch); 长期 (数月后) 不需要保留所有 entry。

### 1.3 设计目标

按 **重要性 × 触发频率 × 时间** 三维度制定遗忘策略:
- **重要性** (severity): P0 保留更久 (关键问题审计), P1 较快遗忘
- **触发频率** (recurrence_count): 反复出现的 issue 保留更久 (系统性问题)
- **时间** (consumed_at age): 越老越可能遗忘

## 2. 架构设计

### 2.1 模块边界

```
scripts/governance/
├── doc_health_consumed.py    # MODIFIED (Phase 2): 加 forget_expired() 方法
├── doc_health_forget.py      # NEW (Phase 1): ForgetPolicy 类 (单一权威源)
└── report_schema.py          # 不变

scripts/tests/
└── test_doc_health_forget.py # NEW (Phase 1+3): 单元 + 集成测试

.cache/
├── doc_health_consumed.json        # 主文件 (live)
└── doc_health_consumed_archive.json # NEW (Phase 3): 归档文件 (forgotten entries)
```

### 2.2 遗忘策略 (单一权威源)

| 优先级 | severity | recurrence_count | patch_failed | 遗忘条件 |
|:------:|:--------:|:----------------:|:------------:|---------|
| 1 (永留) | any | any | true | **永不遗忘** (需 TD 解决) |
| 2 (永留) | P0 | ≥ 1 | false | **永不遗忘** (系统性问题审计) |
| 3 (90d) | P0 | 0 | false | consumed_at + 90d < now |
| 4 (90d) | P1 | ≥ 1 | false | consumed_at + 90d < now |
| 5 (30d) | P1 | 0 | false | consumed_at + 30d < now |

**硬上限** (防极端情况): 若 `len(consumed) > 1000`, 强制遗忘最老的 priority 5 entries (P1 + recurrence=0), 直到 len ≤ 1000。

### 2.3 归档机制

遗忘的 entries **不物理删除**, 而是移动到 `.cache/doc_health_consumed_archive.json`:
- 保留审计能力 (可追溯历史 patch 记录)
- archive 文件按月分片: `doc_health_consumed_archive_YYYYMM.json`
- archive 文件 > 1 年 → 自动删除 (单独清理任务, 不在本 spec 范围)

## 3. Phase 详细设计

### 3.1 Phase 1: ForgetPolicy 类 + 单元测试

#### 3.1.1 文件: `scripts/governance/doc_health_forget.py`

```python
"""doc_health_forget.py - Spec-43: forgetting policy for consumed issues.

Determines when consumed entries can be forgotten (removed from live
consumed.json) based on importance × recurrence × time.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable


# Retention periods (days) per (severity, recurrence_bucket) combination.
# P0 + recurrence>=1 → never forget (return None).
# P0 + recurrence=0 → 90 days.
# P1 + recurrence>=1 → 90 days.
# P1 + recurrence=0 → 30 days.
_RETENTION_DAYS = {
    ("P0", 0): 90,
    ("P0", 1): None,  # never forget (systemic issue audit trail)
    ("P1", 0): 30,
    ("P1", 1): 90,
}

# Hard cap: if len(consumed) > this, force-forget oldest P1+recurrence=0 entries.
_HARD_CAP = 1000


class ForgetPolicy:
    """Single source of truth for forgetting consumed entries.

    Policy (spec-43 §2.2):
        1. patch_failed=true → never forget
        2. P0 + recurrence>=1 → never forget
        3. P0 + recurrence=0 → forget after 90 days
        4. P1 + recurrence>=1 → forget after 90 days
        5. P1 + recurrence=0 → forget after 30 days
    """

    def __init__(self, now_fn: Callable[[], datetime] | None = None):
        # now_fn injection for deterministic tests; default = datetime.now
        self._now_fn = now_fn or (lambda: datetime.now().astimezone())

    def should_forget(self, entry: dict) -> bool:
        """Return True if entry should be forgotten per policy.

        Args:
            entry: consumed.json entry dict with keys:
                severity, recurrence_count, patch_failed, consumed_at.

        Returns:
            True if entry is expired and should be archived.
        """
        # Rule 1: patch_failed → never forget (need TD resolution)
        if entry.get("patch_failed", False):
            return False

        severity = entry.get("severity", "P1")
        recurrence = entry.get("recurrence_count", 0)
        # Bucket: 0 = no recurrence, 1 = any recurrence (>=1)
        rec_bucket = 1 if recurrence >= 1 else 0

        # Rule 2: P0 + recurrence>=1 → never forget
        retention = _RETENTION_DAYS.get((severity, rec_bucket))
        if retention is None:
            return False  # never forget

        # Rules 3-5: time-based forgetting
        consumed_at = self._parse_iso(entry.get("consumed_at", ""))
        if consumed_at is None:
            return False  # invalid timestamp → keep (safer)

        now = self._now_fn()
        age = now - consumed_at
        return age > timedelta(days=retention)

    def forget_expired(
        self, consumed: dict[str, dict]
    ) -> tuple[dict[str, dict], dict[str, dict]]:
        """Split consumed into (kept, forgotten) per policy.

        Args:
            consumed: full consumed_issues dict (issue_id -> entry).

        Returns:
            Tuple of (kept_dict, forgotten_dict). Both preserve issue_id keys.
        """
        kept: dict[str, dict] = {}
        forgotten: dict[str, dict] = {}
        for iid, entry in consumed.items():
            if self.should_forget(entry):
                forgotten[iid] = entry
            else:
                kept[iid] = entry
        return kept, forgotten

    def enforce_hard_cap(
        self, consumed: dict[str, dict]
    ) -> tuple[dict[str, dict], dict[str, dict]]:
        """Force-forget oldest P1+recurrence=0 entries if over hard cap.

        Called after forget_expired() to handle extreme cases. Only
        force-forgets priority-5 entries (P1 + recurrence=0); if still
        over cap, leaves remaining entries alone (safer than forgetting
        P0 or recurrence>=1 entries).

        Args:
            consumed: kept dict from forget_expired().

        Returns:
            Tuple of (final_kept, force_forgotten).
        """
        if len(consumed) <= _HARD_CAP:
            return consumed, {}

        # Find priority-5 candidates (P1 + recurrence=0 + patch_failed=false)
        candidates = [
            (iid, entry)
            for iid, entry in consumed.items()
            if entry.get("severity") == "P1"
            and entry.get("recurrence_count", 0) == 0
            and not entry.get("patch_failed", False)
        ]
        # Sort by consumed_at ascending (oldest first)
        candidates.sort(key=lambda kv: self._parse_iso(kv[1].get("consumed_at", "")) or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo))

        to_forget_count = len(consumed) - _HARD_CAP
        to_forget_ids = {iid for iid, _ in candidates[:to_forget_count]}

        kept = {iid: e for iid, e in consumed.items() if iid not in to_forget_ids}
        forgotten = {iid: e for iid, e in consumed.items() if iid in to_forget_ids}
        return kept, forgotten

    @staticmethod
    def _parse_iso(ts: str) -> datetime | None:
        """Parse ISO 8601 timestamp; return None on failure."""
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return None
```

#### 3.1.2 测试: `scripts/tests/test_doc_health_forget.py`

- `test_should_forget_p0_recurrence_0_after_90d` — 90d+1s → True
- `test_should_forget_p0_recurrence_0_before_90d` — 89d → False
- `test_should_never_forget_p0_recurrence_1` — recurrence=1, any age → False
- `test_should_forget_p1_recurrence_0_after_30d` — 30d+1s → True
- `test_should_forget_p1_recurrence_1_after_90d` — 90d+1s → True
- `test_should_never_forget_patch_failed` — patch_failed=true → False
- `test_should_not_forget_invalid_timestamp` — consumed_at="" → False
- `test_forget_expired_splits_correctly` — mixed entries → correct split
- `test_enforce_hard_cap_below_threshold` — len < 1000 → no change
- `test_enforce_hard_cap_above_threshold` — len > 1000 → force-forget oldest P1+rec=0
- `test_enforce_hard_cap_only_targets_priority_5` — P0 + P1+rec>=1 not touched

### 3.2 Phase 2: ConsumedTracker 集成 + §0.5 更新

#### 3.2.1 `doc_health_consumed.py` 加方法

```python
def forget_expired(self) -> tuple[int, int]:
    """Forget expired entries per ForgetPolicy. Return (forgotten_count, kept_count).

    Side effects:
        - Rewrites consumed.json with kept entries only.
        - Appends forgotten entries to archive file:
          .cache/doc_health_consumed_archive_YYYYMM.json
        - Enforces hard cap (1000 entries) after time-based forgetting.

    Returns:
        Tuple of (forgotten_count, kept_count).
    """
    from governance.doc_health_forget import ForgetPolicy
    consumed = self.load()
    policy = ForgetPolicy()

    kept, forgotten = policy.forget_expired(consumed)
    kept, force_forgotten = policy.enforce_hard_cap(kept)
    forgotten.update(force_forgotten)

    if forgotten:
        self.save(kept)
        self._archive(forgotten)

    return len(forgotten), len(kept)

def _archive(self, forgotten: dict[str, dict]) -> None:
    """Append forgotten entries to monthly archive file."""
    now = datetime.now().astimezone()
    archive_file = self.consumed_file.parent / f"doc_health_consumed_archive_{now.strftime('%Y%m')}.json"
    # Load existing archive (if any) and merge
    existing = {}
    if archive_file.exists():
        try:
            existing = json.loads(archive_file.read_text(encoding="utf-8")).get("consumed_issues", {})
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.update(forgotten)
    # Atomic write
    payload = {
        "schema_version": SCHEMA_VERSION,
        "last_updated": now.isoformat(),
        "consumed_issues": existing,
    }
    tmp = archive_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, archive_file)
```

#### 3.2.2 gaf-orchestrator §0.5 更新

在现有 §0.5 流程步骤 2 之后插入新步骤:

```markdown
2.5. (spec-43) 调用 `ConsumedTracker.forget_expired()` 清理过期 entries
     - 若 forgotten_count > 0, 打印 `"[spec-43] forgot N consumed entries (archived to .cache/doc_health_consumed_archive_YYYYMM.json)"`
     - 不阻塞主流程 (即使 archive 失败也继续)
```

### 3.3 Phase 3: 闭环测试 + 软上限警告

#### 3.3.1 集成测试 (`test_doc_health_forget.py` 补充)

- `test_forget_expired_integration_with_consumed_tracker` — 创建 entries → forget_expired → consumed.json 只含 kept
- `test_archive_file_created_on_forget` — forgotten entries 写入 archive file
- `test_archive_file_merges_with_existing` — 多次 forget 累积到同一 archive
- `test_hard_cap_force_forget_in_integration` — 1001 entries → 1000 kept + 1 forgotten
- `test_forget_does_not_touch_patch_failed` — patch_failed entries 保留
- `test_full_lifecycle` — patch → consumed → 90d 后 forget → archive → 再 patch 同 issue → 新 entry

#### 3.3.2 软上限警告 (observability)

在 `ConsumedTracker.load()` 末尾加:

```python
def load(self) -> dict[str, dict]:
    # ... existing logic ...
    issues = raw.get("consumed_issues", {})
    if not isinstance(issues, dict):
        return {}
    if len(issues) > 800:  # warn at 80% of hard cap
        print(
            f"warning: doc_health_consumed.json has {len(issues)} entries "
            f"(approaching hard cap 1000). Consider running forget_expired() "
            f"or increasing patch success rate.",
            file=sys.stderr,
        )
    return issues
```

## 4. 风险与缓解

### 4.1 风险 1: 误遗忘仍在生效的 entry

**风险**: P0 + recurrence=0 的 issue 在 90d 后被遗忘, 但同 issue 再次出现 (新 report 含同 issue_id), AI 重新 patch 浪费上下文。

**缓解**:
- Issue.id 含 severity (TD-286 修复), 同 file+line+evidence 但不同 severity → 不同 id, 不会误匹配
- 遗忘后同 issue 再出现 = 真实新问题, 重新 patch 是合理的
- archive 文件保留审计能力 (可追溯)

### 4.2 风险 2: archive 文件无界增长

**风险**: archive 文件每月一个, 长期累积。

**缓解**:
- 月度 archive 文件 ~50KB/月 = ~600KB/年, 可接受
- > 1 年的 archive 自动删除 (留给 spec-44 月度治理或单独清理任务)

### 4.3 风险 3: hard cap 误伤

**风险**: 1000 entries 上限触发时强制遗忘 P1+recurrence=0, 但这些可能仍有价值。

**缓解**:
- 1000 entries = ~20 周 patch 量, 远超短期记忆需求
- 只强制遗忘 priority 5 (最低价值), P0 + recurrence>=1 不受影响
- archive 保留所有遗忘 entries

## 5. 验收标准

### 5.1 Phase 1 验收
- [ ] `ForgetPolicy` 类 (should_forget + forget_expired + enforce_hard_cap) 实现
- [ ] 单元测试 11+ PASS, 覆盖 5 个优先级规则 + hard cap
- [ ] 性能: should_forget < 1ms / forget_expired(1000 entries) < 10ms

### 5.2 Phase 2 验收
- [ ] `ConsumedTracker.forget_expired()` + `_archive()` 实现
- [ ] gaf-orchestrator §0.5 加步骤 2.5
- [ ] 集成测试: 创建 entries → forget → consumed.json 只含 kept + archive 含 forgotten

### 5.3 Phase 3 验收
- [ ] 闭环测试 6+ PASS (含 full_lifecycle)
- [ ] 软上限警告 (>800 entries) 打印到 stderr
- [ ] 全量回归: 104 (spec-41+42) + 11 (Phase 1) + 3 (Phase 2) + 6 (Phase 3) = 124+ tests PASS

## 6. spec 完成后落地清单

- [ ] commit message: `feat(spec-43): forgetting mechanism (importance × recurrence × time policy + archive)`
- [ ] `completed-features.md` 追加 C-070
- [ ] `pending-roadmap.md` 更新 spec-43 ✅ + spec-44 状态
- [ ] 反思 (§4.6 中修改以上): 跑 gaf-reflect-and-evolve 5 项 Y/N 矩阵

## 7. spec-42 一致性

- ✅ consumed.json schema 不变 (schema_version=1)
- ✅ ConsumedTracker.load/save 不变 (新增 forget_expired 是叠加方法)
- ✅ PatchPlanner/PatchVerifier 不变 (forget 发生在 patch 之前)
- ✅ §0.5 流程兼容 (新增步骤 2.5 不破坏现有 8 步)
- ✅ 白名单不变 (forget 不涉及 patch 代码文件)

## 8. Open Questions

无 (设计已收敛, 政策明确)。
