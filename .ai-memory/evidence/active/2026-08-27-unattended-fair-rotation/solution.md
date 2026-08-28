---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-27-unattended-fair-rotation/
load_when: [evidence, unattended, rotation]
priority: high
symptom: [rotation_index, cursor]
solution: 见下方步骤
related_files:
  - backend/scheduler/models.py
  - backend/scheduler/tasks.py
  - backend/scheduler/unattended_views.py
  - frontend/src/api/misc.ts
created_by: AI
last_updated: 2026-08-27
---
## Solution

1. `scheduler/models.py`：`UnattendedSession.rotation_index = IntegerField(default=0)`（migration 0013）
2. `scheduler/tasks.py` tick：rotation 分支在 loop_rotation 且账户>1 时，用 `ordered[(session.rotation_index + i) % n]` 从游标位置起找未派发账户（跳过活动集）；每次成功派发后 `rotation_index += 1`（锁内 save）
3. `scheduler/unattended_views.py` start：rotation 模式**始终从 ordered[cursor] 取账户**（不再使用陈旧 device.game_account），派发后 cursor+1 → 保证新会话从 ordered[0] 起、tick 严格交替（session6 实测 2→1→2→1→2）
4. `scheduler/unattended_views.py` preflight：`game_profile_id` query → device_online 只检测该档案设备（未传则全量，向后兼容）
5. 前端：`api/misc.ts fetchUnattendedPreflight(gameProfileId?)` → `stores/useUnattendedStore.fetchPreflight(gameProfileId?)` → `UnattendedControlBar.handleStart` 传 `selectedProfileId`
6. i18n：`dashboard.ts` zh-CN/en 补 rotation_rule_placeholder / loop_rotation / loop_rotation_hint（ja 已有）
7. 测试：`test_loop_rotation.py::test_loop_rotation_alternates_accounts_via_cursor`（tick 两轮选不同账户 + 游标递增；链需节点、session 需 game_profile、completion 前需置 SUCCESS 模拟回执）