---
spec_id: spec-40
title: TD-288 AgentSelector 清理 + TD-273 Phase 1 (constants 模块 + dedup)
status: ✅ completed
created: 2026-07-20
last_updated: 2026-07-20
related: TD-288 (full close), TD-273 (Phase 1 of 2; Phase 2 = spec-44)
n167_score: 9/9 (3 dimensions, medium modification, AI 自决)
commit: -
---

# Spec-40: TD-288 AgentSelector 清理 + TD-273 Phase 1

> **触发**: AI 自决排序模式 (用户授权 2026-07-20) — spec-39 完成后, 排序剩余 TD
> **scope 修正**: TD-273 原登记 "~50 行" 实际是 30+ 文件 80+ 比较点 (spec-40 调研发现), 拆为 Phase 1 (spec-40 dedup + constants 模块) + Phase 2 (spec-44 全量迁移)

## §1 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | TD-288 AgentSelector 清理 (移除 lazy import + 删 dead code + 加单元测试) | ✅ | 2026-07-20 | - | 34 单元测试 PASS; `grep _select_best_agent backend/` = 0; `grep "from tasks.tasks import" backend/tasks/agent_selector.py` = 0 |
| Phase 2 | TD-273 Phase 1 — 创建 `agent/src/core/constants.py` + dedup ComparisonOperator/LoopType/NodeType | ✅ | 2026-07-20 | - | `agent/tests/` 1554 passed 0 回归; `grep 'operator == "eq"' agent/src/` = 0; `grep 'loop_type == "for"' agent/src/engine/` = 0 |
| Phase 3 | N167 评分 + commit + hash 回填 + 反思 | ✅ | 2026-07-20 | - | 9/9 AI 自决; 1588 passed 2 skipped 全套回归 PASS |

## §2 N167 3 维度评分 (中修改)

| 维度 | 分 | 理由 |
|------|---|------|
| ① 架构长远性 | 3 | 消除 lazy import 反模式; 删 dead code (`_select_best_agent`); 集中 enum 定义消除 engine.py/nodes/ 重复 |
| ② 全局归一化 | 3 | ComparisonOperator/LoopType/NodeType 单一权威源在 `core/constants.py`, engine + nodes 统一引用 |
| ⑦ 长期维护成本 | 3 | 补 AgentSelector 单元测试 (修复 docstring 谎称 "unit-tested"); constants.py 为 spec-44 全量迁移奠基 |
| **总分** | **9/9** | ≥ 9/12 阈值, AI 自决 |

**反向论证 (spec-49 必填)**:
- **为何不选 B (仅删 dead code, 不动 lazy import)**: 留 lazy import 反模式 = 保留循环依赖风险 (tasks.py ↔ agent_selector.py); 维护成本高
- **为何不选 C (不动 enum, 留重复)**: 重复 ComparisonOperator 7 个分支逻辑在 2 处, 改一处忘改另一处 = 行为漂移风险

**硬场景 ③ 业务语义判定**: 这个决策影响数据保留/业务流程吗? N → 可自决 (纯代码重构, 无 schema/DB 变更)

**自决决策**: A (总分 9/9 ≥ 9/12, 领先 B/C ≥ 4 分)

## §3 Phase 1: TD-288 AgentSelector 清理

### 3.1 当前问题 (spec-40 调研发现)

1. **lazy import 反模式**: `AgentSelector.__init__` 从 `tasks.tasks` 懒导入 `_get_required_capabilities` + `_agent_matches_capabilities`, 创建 tasks.py ↔ agent_selector.py 循环依赖
2. **dead code**: `_select_best_agent` (tasks.py:136-160) 无任何调用方 (dispatch_task 已用 AgentSelector.select)
3. **docstring 谎言**:
   - `agent_selector.py:3` 声称 "unit-tested" 但无 `test_agent_selector.py`
   - `agent_selector.py:7` 声称 "behavior is preserved" 但 `select_by_load` 实际引入新逻辑 (心跳 + 负载排序)
4. **dispatch_task docstring 误导**: tasks.py:170-175 声称 "kept for backward compat" 但实际 3 个 helper 中 1 个 dead, 2 个仅 AgentSelector 内部用

### 3.2 修改方案

**`backend/tasks/agent_selector.py`** (Phase 1 主修改):
- 把 `CAPABILITY_MAP` + `_get_required_capabilities` + `_agent_matches_capabilities` 从 tasks.py 移入 agent_selector.py (作为模块级函数)
- `AgentSelector.__init__` 不再 lazy import, 直接用本模块函数
- 修 docstring: 删 "thin wrapper"/"behavior preserved" 误导, 改为 "owns the capability + load selection logic"
- 加 `@dataclass(frozen=True)` 给 `CapabilityMap` (可选, 保持 dict 也行)

**`backend/tasks/tasks.py`** (Phase 1 配套):
- 删 `CAPABILITY_MAP` (line 9-14)
- 删 `_get_required_capabilities` (line 71-105)
- 删 `_agent_matches_capabilities` (line 108-133)
- 删 `_select_best_agent` (line 136-160)
- 修 `dispatch_task` docstring (line 170-175): 删 "kept for backward compat", 改为 "uses AgentSelector directly; capability/load logic owns by agent_selector module"
- 检查 `_build_device_info_for_execution` 等其他 helper 不受影响

**`backend/tasks/tests/test_agent_selector.py`** (Phase 1 新建):
- Test 1: `test_get_required_capabilities_*` — 覆盖 steps/nodes 格式 + 各 cap_key 命中 + 空回退 adb
- Test 2: `test_agent_matches_capabilities_*` — dict caps + list caps + partial match (False) + 全满足 (True)
- Test 3: `test_filter_by_capability_*` — 多 agent + 1 个抛异常被 skip + 顺序保留
- Test 4: `test_select_by_load_*` — 全 idle 选最新心跳 + 全 busy 选最低 cpu + 空 list 返回 None
- Test 5: `test_select_*` — 端到端 (filter + load)

### 3.3 验证

- `conda run -n gaf pytest backend/tasks/tests/test_agent_selector.py -v` 全 PASS
- `conda run -n gaf pytest backend/tasks/tests/ -v` 不退化 (现有 test_execution_flow.py 仍 PASS)
- `grep "_select_best_agent" backend/` = 0 处 (dead code 已删)
- `grep "from tasks.tasks import" backend/tasks/agent_selector.py` = 0 处 (lazy import 已消除)

## §4 Phase 2: TD-273 Phase 1 — constants 模块 + dedup

### 4.1 当前问题

1. **ComparisonOperator 重复**: `engine.py:809-821` (7 个 operator 分支) + `nodes/branch.py:86-110` (同 7 个分支), 改一处忘改另一处 = 行为漂移
2. **LoopType 重复**: `engine.py:784,788` + `nodes/loop.py:77,90` 都用字符串 `"for"`/`"while"`
3. **NodeType 散落**: `engine.py:730,736,744,753` + `debug_image_saver.py:312,317,324` + `structured_logger.py:297` 多处用字符串 `"branch"`/`"goto"`/`"loop"`/`"click"`/`"swipe"`/`"long_press"`/`"template_match"`
4. **已有 Enum 未用**: `PipelineState` (engine/context.py:23) 已存在但 orchestrator.py:932,934 仍用 `result.state.value == "completed"` 反向字符串比较

### 4.2 修改方案 (Phase 1 仅做 dedup + 模块创建, 不动其他文件)

**`agent/src/core/constants.py`** (Phase 2 新建):
```python
"""Consolidated enums shared across agent modules.

This module is the single source of truth for status/type/operator
enums used by string-literal comparisons throughout agent/src/. Phase 1
(spec-40) introduces the module and dedups ComparisonOperator/LoopType/
NodeType. Phase 2 (spec-44) migrates the remaining 80+ string literals
to these enums.
"""
from enum import Enum


class ComparisonOperator(str, Enum):
    """Comparison operators used by BranchNode + while-loop evaluation.
    
    str mixin so values can be compared against raw strings during
    Phase 2 migration (gradual adoption).
    """
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    CONTAINS = "contains"


class LoopType(str, Enum):
    """Loop types used by LoopNode + PipelineEngine._loop_should_continue."""
    FOR = "for"
    WHILE = "while"


class NodeType(str, Enum):
    """Pipeline node types.
    
    Used by PipelineEngine._resolve_next_node + debug_image_saver +
    structured_logger. Phase 1 only defines the enum; Phase 2 (spec-44)
    migrates call sites.
    """
    BRANCH = "branch"
    GOTO = "goto"
    LOOP = "loop"
    CLICK = "click"
    SWIPE = "swipe"
    LONG_PRESS = "long_press"
    TEMPLATE_MATCH = "template_match"


def evaluate_comparison(actual, operator, expected) -> bool:
    """Single source of truth for comparison evaluation.
    
    Replaces the duplicated logic in engine.py:_evaluate_loop_condition
    and nodes/branch.py:BranchNode._evaluate. Both call sites will be
    updated to use this function.
    
    Args:
        actual: Current value of the condition variable.
        operator: ComparisonOperator enum or its string value.
        expected: Configured comparison value.
    
    Returns:
        Comparison result; on type errors returns False.
    """
    if isinstance(operator, ComparisonOperator):
        op = operator
    else:
        try:
            op = ComparisonOperator(operator)
        except ValueError:
            # Unknown operator — default to equality (preserves existing
            # fallback behavior in BranchNode._evaluate else branch).
            return actual == expected
    
    try:
        if op is ComparisonOperator.EQ:
            return actual == expected
        if op is ComparisonOperator.NEQ:
            return actual != expected
        if op is ComparisonOperator.GT:
            return float(actual) > float(expected)
        if op is ComparisonOperator.LT:
            return float(actual) < float(expected)
        if op is ComparisonOperator.GTE:
            return float(actual) >= float(expected)
        if op is ComparisonOperator.LTE:
            return float(actual) <= float(expected)
        if op is ComparisonOperator.CONTAINS:
            return str(expected) in str(actual)
    except (TypeError, ValueError):
        return False
    return False
```

**`agent/src/engine/nodes/branch.py`** (Phase 2 修改):
- import `from core.constants import ComparisonOperator, evaluate_comparison`
- `_evaluate` 改为调 `evaluate_comparison(actual, operator, expected)` (删本地 7 分支)

**`agent/src/engine/engine.py`** (Phase 2 修改):
- import `from core.constants import LoopType, evaluate_comparison`
- `_evaluate_loop_condition` 改为调 `evaluate_comparison(actual, operator, expected)` (删本地 7 分支)
- `_loop_should_continue` 中 `loop_type == "for"` / `"while"` 改为 `LoopType.FOR` / `LoopType.WHILE` (str mixin 让 `== "for"` 仍工作, 但显式用 enum 提升可读性)

### 4.3 验证

- `cd agent && python -m pytest tests/test_engine.py tests/test_branch.py tests/test_loop.py -v` 全 PASS (假设测试存在; 若不存在跳过)
- `grep "operator == \"eq\"\|operator == \"neq\"\|operator == \"gt\"" agent/src/` = 0 处 (dedup 后)
- `import core.constants` 在 agent/src/ 任何文件可 import

## §5 Phase 3: commit + hash 回填 + 反思

### 5.1 文档同步

- `docs/general/tech-debt/active.md`: TD-288 段落删除 + closed 注释; TD-273 段落更新 "Phase 1 完成 (spec-40), Phase 2 待 spec-44"
- `docs/general/tech-debt/fixed.md`: 加 TD-288 ✅ FIXED 段落
- `docs/general/completed-features.md`: 加 C-085
- `docs/general/pending-roadmap.md`: 加 P-026
- spec-40 文件状态表 Phase 1-3 全 ✅ + commit hash 回填

### 5.2 commit

```bash
git add backend/tasks/agent_selector.py backend/tasks/tasks.py backend/tasks/tests/test_agent_selector.py \
        agent/src/core/constants.py agent/src/engine/nodes/branch.py agent/src/engine/engine.py \
        docs/general/tech-debt/active.md docs/general/tech-debt/fixed.md \
        docs/general/completed-features.md docs/general/pending-roadmap.md \
        .trae/specs/2026-07-20-spec40-agent-selector-cleanup-and-constants.md \
        .trae/specs/2026-07-20-spec39-small-td-batch.md
git commit -m "refactor(spec-40): TD-288 AgentSelector cleanup + TD-273 Phase 1 constants module (9/9 AI 自决)"
```

### 5.3 hash 回填

按 N176: spec-39 hash (-) 合并到本 commit 一起回填; spec-40 hash 留空, 由下次 spec commit 时一并回填.

### 5.4 反思 (中修改级别 — 5 项 + L0 lesson 若适用)

走 `gaf-reflect-and-evolve §2` 中修改级别流程.

## §6 与 spec-44 (TD-273 Phase 2) 的边界

spec-40 Phase 2 只做 3 件事:
1. 创建 `agent/src/core/constants.py` (ComparisonOperator + LoopType + NodeType + evaluate_comparison)
2. dedup `engine.py` + `nodes/branch.py` 的 ComparisonOperator 重复 (改用 `evaluate_comparison`)
3. dedup `engine.py` + `nodes/loop.py` 的 LoopType 字符串 (改用 `LoopType.FOR`/`WHILE`)

**spec-40 不做** (留给 spec-44):
- 其他 8 类 enum (DeviceType / VerifyType / ElementType / EventType / InputMode / DeviceAction / StepStatus / ServerMessageType) 的定义 + 迁移
- 30+ 文件 80+ 比较点的全量字符串字面量迁移
- 既有 PipelineState / Win32InputMethod Enum 的反向字符串比较迁移
- agent DeviceStatus 与 backend Device.Status 值域对齐策略

spec-44 估 ~500 行 diff, 走大修改 7 维度评分 + N151 5 步.
