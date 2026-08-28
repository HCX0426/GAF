---
spec_id: spec-42
title: 自我进化飞轮 — consumed 标记 + AI patch + 自动 commit + lesson 沉淀
created: 2026-07-19
status: design
applies_to: [scripts, .ai-memory, .trae]
related_skills: [gaf-orchestrator, gaf-reflect-and-evolve, gaf-lesson-router]
related_lessons: [N166, N172, N173, N176]
parent_spec: spec-41 (doc health checker static layer)
child_specs: [spec-43 (遗忘机制), spec-44 (月度检查瘦身)]
---

# Spec-42: 自我进化飞轮

> **范围声明**: 本 spec 实现"完全自动化的自我进化飞轮"闭环 — consumed 标记 + AI patch 流程 + 自动 commit + lesson 沉淀 + recurrence 监控。
> 遗忘机制 (重要性 × 触发频率 × 时间) 在 spec-43。月度检查瘦身 12→5 类在 spec-44。

## 阶段状态表 (TD-137 / §4.10)

| Phase | 标题 | 状态 | 完成时间 | commit hash | 验收 evidence |
|:-----:|------|:----:|:---------:|:-----------:|---------------|
| Phase 1 | 基础设施: consumed 标记存储 | ✅ | 2026-07-19 | - | 15 tests PASS, 性能 13.79ms (< 100ms budget) |
| Phase 2 | AI patch 流程 (核心) | ✅ | 2026-07-19 | - | 20 tests PASS, sync_skills.py --check 通过 |
| Phase 3 | 闭环验证 + lesson 沉淀 + recurrence 监控 | ✅ | 2026-07-19 | - | 22 tests PASS, D2/D3/F2 触发与 spec §3.3 一致 |

> 全量回归: 104 tests PASS (47 spec-41 + 15 Phase 1 + 20 Phase 2 + 22 Phase 3) in 7.24s
> 性能: doc_health_check.py 0.846s (内部, < 2s budget)
> 审查: 3 Phase 两阶段审查全 ✅ PASS

> 状态: ⏳ pending / 🔄 in-progress / ✅ done (N126 诚实标记)

## 1. 背景与动机

### 1.1 用户原话

> "我希望有个完全自动化的自我进化飞轮: 检查器跑 → 发现问题 → AI 分析根因 → AI patch 规则文档 → AI commit → 下次不再犯"
> "人工不要干预这个流程"
> "零对话开销: 静态层在 gaf_init.sh 跑完才进对话"

### 1.2 现状痛点 (spec-41 后状态)

- ✅ spec-41 已交付静态层 7 维度扫描 + `report.json` + `gaf_init.sh` 接入 (commit `-`)
- ✅ 47 tests PASS, 1.0s 性能达标
- ❌ **缺环节**: AI 读 report 但无"已处理"标记 → 同一 issue 下次对话又出现 → AI 重复分析 → 浪费上下文
- ❌ **缺环节**: AI patch 后无验证流程 → 不知道 patch 是否真的解决了 issue → recurrence 无监控
- ❌ **缺环节**: 同 dimension 反复出现 issue (≥ 3 次) → 未触发 lesson 沉淀 → 反模式未固化为硬约束
- ❌ **缺环节**: AI patch 失败 → 无升级 TD 路径 → issue 永远在 report 里悬空

### 1.3 设计目标

1. **完全自动化**: 检查器跑 → AI 读 report → AI patch → AI commit → 下次不再犯
2. **零对话开销**: 用户不参与, AI 在对话开头自动跑 patch 流程
3. **可追溯**: 每个 consumed issue 记录 `action_taken` + `commit_hash` + `consumed_at`
4. **可监控**: `recurrence_count` 跟踪同 dimension issue 反复出现次数, ≥ 2 升级 TD
5. **闭环验证**: patch 后重跑 `doc_health_check` + 相关 pytest, 确认 issue 消失
6. **沉淀纪律**: 同 dimension ≥ 3 次强制写 lesson (§3.8 + N166)

### 1.4 非目标 (Out of Scope)

- ❌ 遗忘机制 (按重要性 × 触发频率 × 时间淘汰老 issue) → spec-43
- ❌ 月度检查瘦身 (12 类→5 类) → spec-44
- ❌ 语义层规则冲突检测 (需 LLM 推理) → L3-1 扫描时跑
- ❌ AI patch 失败时人工介入 → 直接升级 TD, 不打扰用户

## 2. 架构设计

### 2.1 系统拓扑 (飞轮闭环)

```
[对话开头]
    ↓
gaf_init.sh 跑 doc_health_check.py (spec-41 静态层)
    ↓
输出 .cache/doc_health_report.json (issues list)
    ↓
AI 读 report.json + .cache/doc_health_consumed.json (spec-42 NEW)
    ↓
过滤: issues - consumed_issues = 待 patch issues
    ↓
按 severity 排序: P0 > P1 (P2 不自动 patch, 进 L3 循环)
    ↓
按 dimension 分组, 同 dimension 批量 patch
    ↓
[AI patch 执行] (主会话直接处理, 上限 10 issues/对话)
    ├─ C1: 重跑 doc_health_check 全 7 维度, 确认 patched issues 不再出现
    └─ C2: 跑相关 pytest, 确认未引入 regression
    ↓
[更新 consumed 标记] .cache/doc_health_consumed.json
    ├─ issue.id → consumed_at + commit_hash + action_taken
    ├─ recurrence_count (patch 失败 +1)
    └─ patch_failed (true → 升级 TD, 不再自动 patch)
    ↓
[AI commit] (git add + commit, message: "fix(doc-health): patch <dim> issues <id1>,<id2> (auto, spec-42)")
    ↓
[D2 lesson 沉淀] 同 dimension recurrence_count ≥ 3 → 写 lesson (按 §6.2 L1-中分发)
    ↓
[D3 规则文档强制] patch 涉及 rules/handbook/failure-modes → 同步沉淀到对应文件
    ↓
飞轮闭环: 下次对话 gaf_init.sh 跑 → consumed 已标记 → 跳过已 patch 的 issues
```

### 2.2 文件布局

```
scripts/governance/
├── doc_health_check.py                    # spec-41 (existing)
├── doc_health_consumed.py                 # NEW (spec-42 Phase 1): consumed 标记读写
├── doc_health_patch.py                    # NEW (spec-42 Phase 2): AI patch 辅助工具 (生成 patch 计划)
├── report_schema.py                       # spec-41 (existing, 加 consumed_count 字段)
└── check_dimensions/                      # spec-41 (existing)

.cache/                                    # gitignored
├── doc_health_report.json                 # spec-41 (existing)
└── doc_health_consumed.json               # NEW (spec-42 Phase 1): consumed 标记存储

scripts/tests/
└── test_doc_health_consumed.py            # NEW (spec-42 Phase 1): 单元测试
└── test_doc_health_patch.py               # NEW (spec-42 Phase 2): 单元测试

.ai-memory/
├── meta/ai-operating-handbook.md          # NEW 段 (spec-42 Phase 2): "AI patch 红线" 段
└── lessons/workflow_2026-07-19-n177-...md # NEW (spec-42 Phase 3): 飞轮反模式 lesson (如有)

.trae/skills/gaf-orchestrator/SKILL.md     # NEW 段 (spec-42 Phase 2): "对话开头 AI patch 流程" 段
```

### 2.3 与现有系统的关系

| 系统 | 关系 |
|------|------|
| spec-41 `doc_health_check.py` | 上游: 产出 report.json, spec-42 读取消费 |
| `gaf_init.sh` | spec-41 已接入, spec-42 不改 gaf_init.sh (AI 在对话开头跑 patch 流程) |
| `gaf-orchestrator/SKILL.md` | 新增"对话开头 AI patch 流程"段, 在 step_1 之前 |
| `ai-operating-handbook.md` | 新增"AI patch 红线"段 (上限 10 issues / 失败 2 次升级 TD / 涉及规则文档同步沉淀) |
| `gaf-reflect-and-evolve/SKILL.md` | 不改 (反思流程不变, spec-42 patch 完成后跑标准反思) |
| L3 循环 (§3.7) | spec-42 是"快速通道" (P0/P1 自动 patch), L3 处理 P2 + 9 维度其他问题 |
| TD 登记 (§4.8) | patch 失败 2 次 + recurrence_count ≥ 2 → 自动登记 TD |
| `completed-features.md` | spec-42 完成后追加 C-069 |

### 2.4 与 L3 循环的边界

```
spec-42 快速通道 (P0/P1 自动 patch)
    ├─ 触发: 对话开头自动 (读 report.json + consumed.json)
    ├─ 范围: P0 + P1 issues
    ├─ 上限: 10 issues/对话
    ├─ 频率: 每次对话开头
    └─ 失败处理: 升级 TD, 不阻塞对话

L3 循环 (§3.7, 被动触发)
    ├─ 触发: 用户说"循环执行" / "扫一下" / "评估一下"
    ├─ 范围: P2 issues + 9 维度其他问题 (代码层/架构层/界面层等)
    ├─ 上限: 无硬上限 (按 spec 拆分)
    ├─ 频率: 用户触发
    └─ 失败处理: 登记 TD, 等 L3 Round N+1 处理
```

## 3. 详细设计

### 3.1 Phase 1: consumed 标记存储

#### 3.1.1 JSON Schema

`.cache/doc_health_consumed.json`:

```json
{
  "schema_version": 1,
  "last_updated": "2026-07-19T10:30:00+08:00",
  "consumed_issues": {
    "<issue_id_12char>": {
      "dimension": "d4_path_drift",
      "severity": "P0",
      "file": ".ai-memory/lessons/x.md",
      "line": 8,
      "consumed_at": "2026-07-19T10:30:00+08:00",
      "commit_hash": "abc1234",
      "action_taken": "updated related_files path",
      "lesson_id": "N177",
      "recurrence_count": 0,
      "patch_failed": false,
      "failure_reason": null
    }
  }
}
```

#### 3.1.2 `doc_health_consumed.py` API

```python
class ConsumedTracker:
    """Read/write consumed issues state. Single source of truth."""

    def __init__(self, consumed_file: Path):
        self.consumed_file = consumed_file  # .cache/doc_health_consumed.json

    def load(self) -> dict[str, dict]:
        """Load consumed issues. Return empty dict if file missing."""

    def save(self, consumed: dict[str, dict]) -> None:
        """Persist consumed issues. Atomic write (tmp + rename)."""

    def is_consumed(self, issue_id: str) -> bool:
        """Check if issue_id is already consumed."""

    def mark_consumed(self, issue_id: str, *, dimension: str, severity: str,
                      file: str | None, line: int | None, commit_hash: str,
                      action_taken: str, lesson_id: str | None = None) -> None:
        """Mark issue as consumed. Overwrites if exists (updates consumed_at + commit_hash)."""

    def mark_failed(self, issue_id: str, *, dimension: str, severity: str,
                    file: str | None, line: int | None, failure_reason: str) -> None:
        """Mark issue as patch_failed=true, recurrence_count += 1. If recurrence_count >= 2 → return signal for TD escalation."""

    def filter_unconsumed(self, issues: list[Issue]) -> list[Issue]:
        """Filter out consumed issues (patch_failed=false)."""

    def get_recurrence_count(self, dimension: str) -> int:
        """Count distinct issue_ids in dimension with recurrence_count >= 1 (for D2 lesson trigger)."""
```

#### 3.1.3 `report_schema.py` 改动

`ReportSummary` 加 `consumed_count` 字段:

```python
@dataclass
class ReportSummary:
    total: int
    by_severity: dict[str, int]
    by_dimension: dict[str, int]
    consumed_count: int = 0  # NEW: issues already consumed (patched in prior sessions)
```

`doc_health_check.py` 主入口加载 consumed.json, 标记 `Issue.consumed = True`:

```python
# In main(), after run_all_dimensions:
tracker = ConsumedTracker(REPO_ROOT / ".cache" / "doc_health_consumed.json")
consumed = tracker.load()
for issue in issues:
    if issue.id in consumed and not consumed[issue.id].get("patch_failed", False):
        issue.consumed = True
report = DocHealthReport(
    ...,
    summary=ReportSummary.from_issues(issues),  # auto-computes consumed_count
    issues=issues,
)
```

#### 3.1.4 单元测试 (`test_doc_health_consumed.py`)

- `test_load_missing_file_returns_empty` — 文件不存在返回 `{}`
- `test_save_then_load_roundtrip` — save + load 数据一致
- `test_is_consumed_true_after_mark` — mark 后 `is_consumed` 返回 True
- `test_mark_consumed_overwrites_existing` — 重复 mark 更新 consumed_at + commit_hash
- `test_mark_failed_increments_recurrence` — patch_failed=true 时 recurrence_count += 1
- `test_filter_unconsumed_excludes_consumed` — 已 consumed 且 patch_failed=false 的被过滤
- `test_filter_unconsumed_includes_failed` — patch_failed=true 的不过滤 (需重新 patch)
- `test_get_recurrence_count_by_dimension` — 同 dimension 多个 issue 累加
- `test_atomic_write_no_corruption` — 并发写不损坏 JSON (tmp + rename)
- `test_schema_version_migration` — schema_version != 1 时优雅降级

### 3.2 Phase 2: AI patch 流程 (核心)

#### 3.2.1 `gaf-orchestrator/SKILL.md` 新增段 (在 step_1 之前)

新增段 "## §0.5 对话开头 AI patch 流程 (spec-42)":

```markdown
## §0.5 对话开头 AI patch 流程 (spec-42 — 强制)

> **触发**: 对话开头 (在 step_1_identify_task_type 之前)
> **目标**: 自动修复 doc_health_check 发现的 P0/P1 issues, 零对话开销

**流程** (8 步):
1. Read `.cache/doc_health_report.json` — 若文件不存在或 < 1h 内已跑过, 跳过
2. Read `.cache/doc_health_consumed.json` — 加载已 consumed issues
3. 过滤: `unconsumed_issues = issues - consumed_issues (patch_failed=false)`
4. 过滤: `patchable_issues = [i for i in unconsumed_issues if i.severity in ("P0", "P1")]`
5. 若 `len(patchable_issues) == 0` → 跳过 (进入 step_1)
6. 按 dimension 分组, 每组取前 N 使总数 ≤ 10
7. 对每组:
   a. 分析 root_cause (读 issue.evidence + issue.root_cause_hint + 对应文件)
   b. 用 Edit/Write 工具 patch (按 issue.suggested_fix)
   c. C1 验证: 重跑 `python scripts/governance/doc_health_check.py --no-fail`, 确认 patched issue.id 不再出现
   d. C2 验证: 跑相关 pytest (如 patch 涉及 scripts/governance/ → `pytest scripts/tests/test_doc_health_*.py`)
   e. 若 C1 + C2 通过 → mark_consumed(issue.id, commit_hash=..., action_taken=...)
   f. 若 patch 失败 (C1/C2 失败 2 次) → mark_failed + 升级 TD
8. commit: `git add -A && git commit -m "fix(doc-health): patch <dim> issues <id1>,<id2> (auto, spec-42)"`

**红线** (在 ai-operating-handbook.md Part 2 同步沉淀):
- ✅ 上限 10 issues/对话 (防上下文爆炸)
- ✅ 同 dimension 批量 patch (一次 Edit/Write 多个 issue)
- ✅ patch 完成立即 commit (不积攒)
- ✅ patch 失败 2 次 → mark_failed + 登记 TD (不打扰用户)
- ✅ 涉及 rules/handbook/failure-modes → D3 强制同步沉淀 (§3.8)
- ❌ 禁止 patch P2 issues (留给 L3 循环)
- ❌ 禁止跨 dimension 批量 (不同 dimension 逻辑独立, 分别 patch)
- ❌ 禁止跳过 C1/C2 验证 (假 patch = 假实现, N126)
- ❌ 禁止 patch_failed=true 的 issue 重复 patch (升级 TD 后人工处理)
```

#### 3.2.2 `ai-operating-handbook.md` Part 2 新增段 "AI patch 红线"

```markdown
### AI patch 红线 (spec-42)

**触发**: 对话开头自动 (gaf-orchestrator §0.5)

**上限**:
- 10 issues/对话 (P0+P1)
- 单 dimension 批量 (不限数量, 但同 dimension)
- 单次对话 1 commit (合并所有 dimension 的 patch)

**验证 (C1 + C2)**:
- C1: 重跑 `python scripts/governance/doc_health_check.py --no-fail`, patched issue.id 不再出现
- C2: 跑相关 pytest (scripts/tests/test_doc_health_*.py)

**失败处理**:
- patch 失败 1 次: 重试 (换 patch 策略, 如 Edit → Write)
- patch 失败 2 次: mark_failed + 登记 TD (TD-NNN: doc_health <dimension> issue <id> 自动 patch 失败)
- recurrence_count >= 2: 升级 TD (同 dimension 反复出现 = 根因未解决)

**commit message 格式**:
- `fix(doc-health): patch <dim> issues <id1>,<id2> (auto, spec-42)`
- 例: `fix(doc-health): patch d4_path_drift issues a1b2c3d4e5f6,7890abcdef12 (auto, spec-42)`

**D2 lesson 沉淀触发**:
- 同 dimension recurrence_count >= 3 → 写 lesson (按 §6.2 L1-中分发: lesson + project_rules + ai-operating-handbook 3 层)

**D3 规则文档强制沉淀**:
- patch 涉及 rules/handbook/failure-modes/yn-matrices → 同步沉淀到对应文件 (§3.8 边执行边沉淀)
- 例: patch d7_index_consistency 涉及 failure-modes.md 索引 → 同步在 failure-modes.md 追加 N## 索引行 (如有新反模式)

**白名单 (允许 patch 的目标文件)**:
- ✅ `.ai-memory/lessons/*.md`
- ✅ `.ai-memory/summaries/*.md`
- ✅ `.ai-memory/meta/*.md` (failure-modes / ai-operating-handbook / yn-matrices)
- ✅ `.trae/rules/project_rules.md`
- ✅ `.trae/skills/gaf-*/SKILL.md`
- ✅ `docs/general/**/*.md` (design/analysis/standards/tech-debt)
- ❌ 禁止 patch 代码文件 (backend/agent/frontend) — 代码 bug 走 bug_fix 分支
- ❌ 禁止 patch spec/plan 文件 (.trae/specs/, .trae/plans/) — 历史记录不修改
```

#### 3.2.3 `doc_health_patch.py` 辅助工具

提供 patch 计划生成 + 验证辅助:

```python
class PatchPlanner:
    """Generate patch plan from unconsumed P0/P1 issues."""

    def __init__(self, report_file: Path, consumed_file: Path):
        self.report_file = report_file
        self.consumed_file = consumed_file

    def get_patchable_issues(self, max_issues: int = 10) -> list[dict]:
        """Return list of patchable issues (P0/P1, unconsumed), grouped by dimension."""

    def group_by_dimension(self, issues: list[Issue]) -> dict[str, list[Issue]]:
        """Group issues by dimension for batch patching."""

class PatchVerifier:
    """Verify patch success by re-running checks."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def rerun_check(self, dimension: str | None = None) -> list[Issue]:
        """Re-run doc_health_check (optionally single dimension). Return new issues."""

    def verify_patched(self, patched_issue_ids: list[str]) -> dict[str, bool]:
        """Return {issue_id: True if no longer in report, False if still present}."""

    def run_relevant_pytest(self, dimension: str) -> tuple[int, int]:
        """Run pytest for dimension-specific tests. Return (passed, failed)."""
```

#### 3.2.4 单元测试 (`test_doc_health_patch.py`)

- `test_get_patchable_issues_filters_consumed` — 已 consumed 的不在列表
- `test_get_patchable_issues_filters_p2` — P2 不在列表
- `test_get_patchable_issues_respects_max` — 上限 10
- `test_group_by_dimension_batches_correctly` — 同 dimension 归一组
- `test_rerun_check_returns_current_issues` — 重跑返回当前 issues
- `test_verify_patched_detects_success` — patched issue 不在 → True
- `test_verify_patched_detects_failure` — patched issue 仍在 → False
- `test_run_relevant_pytest_passes` — pytest 通过
- `test_run_relevant_pytest_fails` — pytest 失败时返回 (passed, failed)

### 3.3 Phase 3: 闭环验证 + lesson 沉淀 + recurrence 监控

#### 3.3.1 C1 + C2 闭环验证 (集成测试)

`scripts/tests/test_doc_health_flywheel.py`:

- `test_full_flywheel_e2e` — 完整飞轮: 创建 issue → AI patch → consumed → 重跑 → issue 消失
- `test_patch_failed_escalates_td_pattern` — patch 失败 2 次 → mark_failed → recurrence_count = 2
- `test_recurrence_3_triggers_lesson_pattern` — 同 dimension 3 个不同 issue 失败 → D2 触发 (返回 lesson 提示)
- `test_consumed_persists_across_sessions` — consumed.json 跨会话持久化
- `test_patch_involves_rules_triggers_d3` — patch rules/handbook 文件 → D3 触发 (返回规则文档同步提示)

#### 3.3.2 D2 lesson 沉淀触发

`doc_health_consumed.py` 加方法:

```python
def check_d2_lesson_trigger(self, dimension: str) -> dict | None:
    """If dimension has >= 3 distinct issue_ids with recurrence_count >= 1, return lesson trigger dict.

    Returns:
        dict with keys: dimension, recurrence_issue_ids, suggested_lesson_topic
        None if trigger condition not met.
    """
    recurrences = [
        iid for iid, data in self.load().items()
        if data.get("dimension") == dimension
        and data.get("recurrence_count", 0) >= 1
    ]
    if len(recurrences) >= 3:
        return {
            "dimension": dimension,
            "recurrence_issue_ids": recurrences,
            "suggested_lesson_topic": f"doc_health_{dimension}_recurrence",
        }
    return None
```

#### 3.3.3 D3 规则文档强制沉淀

`doc_health_patch.py` 加方法:

```python
RULES_FILES = {
    ".trae/rules/project_rules.md",
    ".ai-memory/meta/ai-operating-handbook.md",
    ".ai-memory/meta/failure-modes.md",
}

def check_d3_sediment_trigger(self, patched_files: list[str]) -> list[str]:
    """Return list of rules files that were patched (need D3 sedimentation).

    D3 trigger: any patched file in RULES_FILES → must sync sedimentation
    per §3.8 边执行边沉淀.
    """
    return [f for f in patched_files if f in RULES_FILES]
```

#### 3.3.4 F2 recurrence 监控

`doc_health_consumed.py` 加方法:

```python
def check_td_escalation(self, dimension: str) -> dict | None:
    """If dimension has any issue with recurrence_count >= 2, return TD escalation dict.

    Returns:
        dict with keys: dimension, issue_id, recurrence_count, suggested_td_title
        None if no escalation needed.
    """
    for iid, data in self.load().items():
        if (data.get("dimension") == dimension
                and data.get("recurrence_count", 0) >= 2):
            return {
                "dimension": dimension,
                "issue_id": iid,
                "recurrence_count": data["recurrence_count"],
                "suggested_td_title": f"doc_health {dimension} issue {iid} auto-patch failed {data['recurrence_count']}x",
            }
    return None
```

#### 3.3.5 单元测试 (`test_doc_health_flywheel.py` 补充)

- `test_check_d2_lesson_trigger_below_threshold` — 2 个 recurrence → None
- `test_check_d2_lesson_trigger_at_threshold` — 3 个 recurrence → 返回 trigger dict
- `test_check_d3_sediment_trigger_with_rules` — patch project_rules.md → 返回 ["project_rules.md"]
- `test_check_d3_sediment_trigger_without_rules` — patch lessons/x.md → 返回 []
- `test_check_td_escalation_below_threshold` — recurrence_count=1 → None
- `test_check_td_escalation_at_threshold` — recurrence_count=2 → 返回 dict
- `test_f1_flywheel_next_session_skips_consumed` — 下次对话同 issue_id 被跳过

## 4. 风险与缓解

### 4.1 风险 1: AI patch 误改规则文档

**风险**: AI 自动 patch rules/handbook 可能引入错误, 破坏现有约束

**缓解**:
- D3 强制同步沉淀 (§3.8 边执行边沉淀)
- C1 + C2 验证 (patch 后重跑检查 + pytest)
- 限制白名单 (禁止 patch 代码 / spec / plan)
- 失败 2 次升级 TD (人工兜底)

### 4.2 风险 2: consumed.json 损坏

**风险**: JSON 文件损坏导致全飞轮失效

**缓解**:
- 原子写 (tmp + rename)
- `load()` 优雅降级 (损坏返回 `{}`)
- 单元测试覆盖损坏场景

### 4.3 风险 3: 同 dimension 反复出现 issue

**风险**: 根因未解决, AI 反复 patch 同 dimension 不同 issue

**缓解**:
- D2 lesson 沉淀 (≥ 3 次强制写 lesson)
- F2 TD 升级 (≥ 2 次升级 TD)
- recurrence_count 监控 (consumed.json 跟踪)

### 4.4 风险 4: 上下文爆炸

**风险**: 单次对话 patch 太多 issues, 上下文耗尽

**缓解**:
- 上限 10 issues/对话
- 同 dimension 批量 patch (一次 Edit 多个)
- 单次对话 1 commit (不分散)

### 4.5 风险 5: patch 后引入 regression

**风险**: patch 规则文档影响其他维度检查

**缓解**:
- C1 重跑全 7 维度 (不仅 patched dimension)
- C2 跑相关 pytest
- 失败回滚 (mark_failed, 不 commit)

## 5. 验收标准

### 5.1 Phase 1 验收

- [ ] `.cache/doc_health_consumed.json` schema 实现 + 单元测试 10+ PASS
- [ ] `report_schema.py` 加 `consumed_count` 字段 + `Issue.consumed` 标记
- [ ] `doc_health_check.py` 主入口加载 consumed.json 标记 issues
- [ ] 性能: consumed.json load + filter < 0.1s

### 5.2 Phase 2 验收

- [ ] `gaf-orchestrator/SKILL.md` §0.5 段添加
- [ ] `ai-operating-handbook.md` Part 2 "AI patch 红线" 段添加
- [ ] `doc_health_patch.py` (PatchPlanner + PatchVerifier) + 单元测试 9+ PASS
- [ ] 端到端: 构造 1 个 P0 issue → 跑 patch 流程 → consumed + commit + 验证 PASS

### 5.3 Phase 3 验收

- [ ] C1 + C2 闭环验证集成测试 5+ PASS
- [ ] D2 lesson 沉淀触发 + 单元测试 3+ PASS
- [ ] D3 规则文档强制沉淀 + 单元测试 2+ PASS
- [ ] F2 recurrence 监控 + TD 升级 + 单元测试 3+ PASS
- [ ] 端到端飞轮测试: issue → patch → consumed → recurrence → D2 → TD 升级 全链路 PASS

### 5.4 全量回归

- [ ] 47 (spec-41) + 10 (Phase 1) + 9 (Phase 2) + 13 (Phase 3) = 79+ tests PASS
- [ ] `doc_health_check.py` 性能 < 2s 不退化
- [ ] `gaf_init.sh` 流程不破坏 (spec-41 接入保留)

## 6. spec 完成后落地清单

- [ ] commit message: `feat(spec-42): self-evolution flywheel (consumed + AI patch + lesson sediment + recurrence monitor)`
- [ ] `completed-features.md` 追加 C-069
- [ ] `pending-roadmap.md` 更新 spec-42 ✅ + spec-43/44 状态
- [ ] failure-modes.md 如有新反模式 (N177) → 追加 N## 索引行
- [ ] 反思 (§4.6 中修改以上): 跑 gaf-reflect-and-evolve 5 项 Y/N 矩阵

## 7. 与 spec-41 一致性

| 项 | spec-41 | spec-42 |
|----|---------|---------|
| 范围 | 静态层 7 维度扫描 + report.json | 飞轮闭环 (consumed + AI patch + 沉淀) |
| 触发 | gaf_init.sh | 对话开头 (AI 自动) |
| 修改文件 | scripts/governance/ + .cache/ | scripts/governance/ + .cache/ + .trae/skills/ + .ai-memory/meta/ |
| 测试 | 47 tests | +32 tests (Phase 1-3) |
| 性能 | < 2s | < 0.1s (consumed load) + patch 主会话开销 |
| commit | `-` + `-` + `-` | 待 commit (N176 单对话单 commit) |

## 8. Open Questions

无 — 用户已通过 AskUserQuestion 确认:
- 范围: 完整飞轮
- 触发时机: 对话开头自动
- commit 策略: AI 自决 commit
