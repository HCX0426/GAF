---
spec: 2026-08-29-naming-c-default-routine
title: 命名归一化 C-2：GameProfile.default_routine → default_task_chain（含端点）
status: done
created: 2026-08-29
estimated_effort: 0.5 day
risk: high
depends_on: []
source: docs/analysis/concept-naming-normalization.md §1/§5(4)/§7
---

# 命名归一化 C-2：default_routine → default_task_chain

## 1. 背景与动机 (Background)

`backend/gamestate/models.py:53` 的 `GameProfile.default_routine` 是 `TaskChain` 的 FK（"Routine"=默认 TaskChain，评估稿 §2.1/§3）。"Routine" 命名掩盖了它本质是一条任务链；同时暴露端点 `default-routine`（21 命中）命名不一致。全仓 `default_routine` 183 命中（含 API/迁移/前端类型），属高危。

## 2. 核心问题 (Problem)

| 项 | 现状 | 目标 |
|----|------|------|
| `GameProfile.default_routine` (FK→TaskChain) | 字段名 Routine | `default_task_chain` |
| 端点 `default-routine` | URL 名 | `default-task-chain` |
| 文档 "Routine"/`routine.json` | 别名 | 改指"默认任务链" |

## 3. 目标 (Goals)

1. 字段重命名 `default_routine`→`default_task_chain`，端点 `default-routine`→`default-task-chain`。
2. 前端类型重生成 + 引用替换。
3. 全仓 183 命中逐项改写，区分字段 vs URL。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 后端模型 + 迁移 + serializers/views/urls | ✅ |
| P2 | 前端类型重生成 + 引用替换 | ✅ |
| P3 | 文档同步 + 测试 | ✅ |

#### Task P1.1: 后端

- `backend/gamestate/models.py:53`：`default_routine`→`default_task_chain`（FK 名同步）。
- 迁移 `RenameField` model `GameProfile`。
- `gamestate/serializers.py`、`views.py`：字段 + `default-routine` URL（`urls.py` path/name）→`default-task-chain`。
- grep 全仓 `default_routine`（183）与 `default-routine`（21），区分模型字段 / URL name / 前端调用，逐项替换。

#### Task P1.2: 前端

- 重生成 `api.generated.ts` / `models/game_profile.ts`；组件引用 `default_routine`→`default_task_chain`，端点 `default-routine`→`default-task-chain`。

#### Task P1.3: 文档

- overview/features 中 "Routine"/`routine.json` 改指"默认任务链（default_task_chain）"；评估稿标记 C-2 完成。

## 5. 测试与验收

- `makemigrations --check` 无 diff；`pytest backend/gamestate` 通过。
- 前端 `tsc --noEmit` 无 `default_routine` 残留。
- 手动：GameProfile 配置默认任务链 UI 正常读写。

## 6. 回滚

- 迁移反向 + 代码 revert。
