---
date: 2026-07-06
symptom: [task-dispatch, device-info, skill-sync, direction, r37-p3]
solution: Forward device_info in task.dispatch messages; edit skill files in GAF repo (not workspace root) to avoid sync_skills.py overwrite.
related_files:
  - backend/tasks/tasks.py
  - .trae/skills/gaf-lesson-router/SKILL.md
created_by: AI
n_id: N149
topic: workflow
title: R37-P3 wrapup — task.assign device_info gap + skill sync direction
category: workflow
priority: low
load_when: [editing-skill-files, adding-dispatch-types]
level: L0
---

# N149 — R37-P3 收尾：task.assign device_info gap + skill 编辑方向

## Symptom

R37-P3 测试期间发现两个独立问题：

1. **task.assign device_info gap**: BD2 端到端执行时，agent 收到 task.dispatch 消息但
   无法解析目标设备，discovered Windows devices 保持 DISCONNECTED，任务立即失败。
   `pipeline.execute` 正常工作（会转发 device_info），但 `task.dispatch` 不会。

2. **skill 编辑方向错误**: 编辑 `.trae/skills/gaf-lesson-router/SKILL.md` 添加 N148 条目时，
   误编辑了 workspace 根副本 `D:\code\AUTO_PROJECTS\.trae\skills\...`，而
   `sync_skills.py` 的 source-of-truth 是 GAF repo 内副本
   `D:\code\AUTO_PROJECTS\GAF\.trae\skills\...`。若跑 `sync_skills.py`（不带 --check）
   会用 repo 内副本覆盖 workspace 根副本，丢失 N148 改动。

## Root Cause

1. **device_info gap**: `backend/tasks/tasks.py:dispatch_task` 没有像
   `PipelineViewSet.execute` 那样调用 `_build_device_info_for_task()` 构建
   device metadata，导致 `task.assign` 消息缺 `device_info` 字段。

2. **skill 编辑方向**: 没有先读 `sync_skills.py` 理解 source-of-truth 方向就编辑文件。
   `sync_skills.py:473` 注释明确 "Source-of-truth paths" 指向 repo 内副本，同步方向是
   repo → workspace 根。

## Fix

1. **device_info gap** (commit `-`):
   - `backend/tasks/tasks.py`: 新增 `_build_device_info_for_task()` 函数
   - `backend/protocol/consumers.py`: task.assign 消息转发 `device_info` 字段
   - `agent/src/client/handler.py`: 解析 `device_info` 并 resolve target device

2. **skill 编辑方向** (commit `-`): 手动 Copy-Item 把 workspace 根副本
   反向同步到 repo 内副本（歪打正着，因为 workspace 根副本有更新内容）。
   正确流程应是：编辑 repo 内副本 → 跑 `sync_skills.py` 同步到 workspace 根。

## Prevention

- **编辑 skill 文件前**: 确认路径是 `.trae/skills/...`（repo 内，source of truth），
  不是 `D:\code\AUTO_PROJECTS\.trae\skills/...`（workspace 根，target）
- **添加新 dispatch 类型时**: 检查是否包含 `device_info` 字段，参考
  `PipelineViewSet.execute` 和 `dispatch_task` 的一致性
- **编辑 skill 后**: 跑 `python GAF/scripts/bootstrap/sync_skills.py --check` 验证一致性

## Related Files

- `backend/tasks/tasks.py` — `_build_device_info_for_task()` + `dispatch_task`
- `backend/protocol/consumers.py` — `task.assign` 消息转发
- `agent/src/client/handler.py` — `_resolve_target_device()`
- `scripts/bootstrap/sync_skills.py:473-510` — source-of-truth + 同步方向

## Verification

- BD2 execution 63 status=success（device_info 透传验证通过）
- `sync_skills.py --check` 报告 "4 skills + 1 rule 副本一致"
- commit `-` (device_info) + `-` (skill sync)

## Distribution

L0 (一次性历史记录) — 只写 lessons 层，不进 arch-mistakes/yn-matrices/SKILL.md taxonomy。
未来如果"编辑错 skill 副本"重复出现，提升为 L1 加 Y/N 矩阵。
