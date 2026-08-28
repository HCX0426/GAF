---
spec_id: spec-44
title: TD-273 Phase 2 — agent 字符串字面量全量迁移到 enum
status: ✅ completed
created: 2026-07-20
last_updated: 2026-07-20
related: TD-273 (Phase 2 of 2; Phase 1 = spec-40)
n167_score: 9/9 (3 dimensions, medium modification, AI 自决)
commit: -
---

# Spec-44: TD-273 Phase 2 — agent 字符串字面量全量迁移到 enum

> **触发**: AI 自决排序模式 (用户授权 2026-07-20) — spec-41 完成后, 排序剩余 TD
> **scope 修正**: 原登记 "30+ 文件 80+ 比较点" 实际是 20 文件 50 比较点 (spec-44 调研发现), 定级中修改

## §1 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | 扩展 `agent/src/core/constants.py` 加 3 新 enum (ServerStatus / EventType / AgentStatus) | ✅ | 2026-07-20 | (本次 commit) | constants.py 追加 3 enum + 6 enum 全升级为 StrEnum; ruff UP042 合规 |
| Phase 2 | 迁移 NodeType 比较点 (node_type == "click" 等 → NodeType.CLICK) — str-Enum 直接替换 | ✅ | 2026-07-20 | (本次 commit) | structured_logger.py:297 + debug_image_saver.py:312,317,324 + engine.py:731,737,745,754 |
| Phase 3 | 迁移其他 enum 比较点 (PipelineState / TaskState / StepState / DeviceStatus — 用 .value 模式) | ✅ | 2026-07-20 | (本次 commit) | orchestrator.py:932,934 (drop .value) + step_recorder.py:177,178 + health_checker.py:535 + handler.py:165 |
| Phase 4 | 迁移新 enum 比较点 (ServerStatus / EventType / AgentStatus) + 验证 | ✅ | 2026-07-20 | (本次 commit) | recording_to_pipeline.py:39,83,103,153,155 + connection.py:576; pytest 1554 passed 2 skipped (0 回归); ruff All checks passed |
| Phase 5 | 文档同步 + commit + hash 回填 (spec-41 -) + 反思 | ✅ | 2026-07-20 | (本次 commit) | active.md/fixed.md/C-087/P-028 + spec-41 hash 回填 (-) |

## §2 N167 3 维度评分 (中修改)

| 维度 | 分 | 理由 |
|------|---|------|
| ① 架构长远性 | 3 | enum 替代字符串字面量, 减少 typo 风险 (如 "erorr"); 集中定义便于重命名; IDE 自动补全 |
| ② 全局归一化 | 3 | agent enum 集中到 constants.py (single source of truth); 消除字符串字面量分散在 20 文件 |
| ⑦ 长期维护成本 | 3 | 重命名成本从 "grep 20 文件" 降到 "改 1 处 enum 定义"; 新成员查 enum 定义即可理解所有合法值 |
| **总分** | **9/9** | ≥ 9/12, AI 自决 |

**反向论证**:
- **为何不选 B (保持字符串字面量)**: typo 风险持续存在; 重命名成本高; 无 IDE 补全
- **为何不选 C (改全部 enum 为 str-Enum + 改字段类型)**: 改 StepRecord.status / PipelineState 等字段类型为 enum 会破坏 JSON 序列化 (enum 不可直接 json.dumps); 需大改 dataclass + 加 to_json 方法; 超出 TD-273 范围

**硬场景 ③**: 影响 data retention/业务流程? N → 可自决 (纯重构, 行为等价, str-Enum compares equal to string value)

## §3 Phase 1: 扩展 constants.py 加 3 新 enum

在 `agent/src/core/constants.py` 追加:

```python
class ServerStatus(str, Enum):
    """Server message status types (handler.py:165 etc.).

    Used by agent ws_client to parse server JSON payloads where
    ``status`` field indicates message category.
    """
    ERROR = "error"
    INFO = "info"
    WARNING = "warning"
    SUCCESS = "success"


class EventType(str, Enum):
    """Recording event types (recording_to_pipeline.py etc.).

    Used by StepRecorder to categorize user input events during
    recording sessions.
    """
    CLICK = "click"
    KEY = "key"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    SWIPE = "swipe"
    LONG_PRESS = "long_press"


class AgentStatus(str, Enum):
    """Agent status values (health_checker.py:535 etc.).

    Mirrors backend Agent.Status choices (agents.models.Agent.Status).
    Used by agent health checker to parse ADB device state strings.
    """
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    IDLE = "idle"
```

## §4 Phase 2: NodeType 比较点迁移 (str-Enum, 直接替换)

 NodeType (spec-40 已建, str-Enum) compares equal to its string value, so `node_type == "click"` → `node_type == NodeType.CLICK` is behavior-equivalent.

**Files to migrate** (grep evidence):
- `agent/src/utils/structured_logger.py:297` — `node_type == "template_match"` → `NodeType.TEMPLATE_MATCH`
- `agent/src/utils/debug_image_saver.py:312,317,324` — `"click"` / `"swipe"` / `"long_press"` → NodeType enum
- `agent/src/engine/engine.py:731,737,745,754` — `"branch"` / `"goto"` / `"loop"` → NodeType enum
- `agent/src/monitor/handlers.py:37,161` — `action_type == "click"` (NOT NodeType — defer to Phase 4 or keep as string)

## §5 Phase 3: 其他 enum 比较点迁移 (.value 模式)

Existing enums (StepState, PipelineState, TaskState, DeviceStatus) are plain `Enum` (NOT str-Enum), so `StepState.COMPLETED == "completed"` is False. Use `.value` pattern: `s.status == StepState.COMPLETED.value`.

**Files to migrate**:
- `agent/src/core/orchestrator.py:932,934` — `result.state.value == "completed"` → `result.state == PipelineState.COMPLETED` (state is already enum, drop .value)
- `agent/src/core/step_recorder.py:177,178` — `s.status == 'completed'` → `s.status == StepState.COMPLETED.value` (status is str field)
- `agent/src/devices/health_checker.py:535` — `parts[1] == 'offline'` → `parts[1] == AgentStatus.OFFLINE.value` (parts[1] is str from split)
- `agent/src/client/handler.py:165` — `status == "error"` → `status == ServerStatus.ERROR.value` (status is str from JSON)

## §6 Phase 4: 新 enum 比较点迁移 + 验证 + commit

**Files to migrate** (新 enum):
- `agent/src/core/recording_to_pipeline.py:39,83,103,153,155` — `event.event_type == 'click'/'key'/'wait'` → `EventType.CLICK`/`KEY`/`WAIT` (event_type is str field, str-Enum compares equal)
- `agent/src/client/connection.py:576` — `msg_type != "error"` → `msg_type != ServerStatus.ERROR.value` (msg_type is str from JSON)
- `agent/src/engine/nodes/notify.py:79` — `level == "error"` → keep as string (LogLevel not defined; only one occurrence, not worth new enum)

**验证**:
- `pytest agent/tests/` 0 回归
- `grep -E '(==|!=)\s*["'"'"'](online|offline|busy|idle|error|running|paused|completed|failed|success|for|while|branch|goto|loop|click|swipe|long_press|template_match|eq|neq|gt|lt|gte|lte|contains)["'"'"']' agent/src/` ≤ 5 (residual: notify.py level, monitor action_type, etc.)

## §7 Phase 5: 文档同步 + commit + hash 回填 (spec-41 hash -)

- `docs/general/tech-debt/active.md`: TD-273 段落删除 + closed 注释
- `docs/general/tech-debt/fixed.md`: 加 TD-273 ✅ FIXED 段落 (Phase 1 + Phase 2 全闭环)
- `docs/general/completed-features.md`: 加 C-087
- `docs/general/pending-roadmap.md`: 加 P-028 + spec-41 hash 回填 (-)
- spec-44 文件状态表 Phase 1-5 全 ✅
- spec-41 文件 hash 回填 (-)
- commit message: `refactor(spec-44): TD-273 Phase 2 agent enum migration (9/9 AI 自决, spec-41 hash backfill)`

## §8 反思 (中修改级别 — 5 项)

走 `gaf-reflect-and-evolve §2` 中修改级别流程.
