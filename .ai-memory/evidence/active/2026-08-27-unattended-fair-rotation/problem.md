---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-27-unattended-fair-rotation/
load_when: [evidence, unattended, rotation, loop]
priority: high
symptom: [公平轮换, sequential 单设备总选队首, preflight 跨档案设备阻塞]
solution: rotation_index 游标 + start 统一 cursor + preflight profile 过滤 + i18n zh/en
related_files:
  - backend/scheduler/models.py
  - backend/scheduler/tasks.py
  - backend/scheduler/unattended_views.py
  - frontend/src/pages/Ops/UnattendedControlBar.tsx
created_by: AI
last_updated: 2026-08-27
---
## Problem

E2E 实测（Chrome 百度循环任务 + 2 账户 + sequential 轮换 + loop_rotation）发现 3 类问题：
1. 公平轮换缺失：loop_rotation 归还池后 tick 永远选 ordered_accounts[0]，单设备下同一账户反复执行，另一账户轮不到（实测 session2/4 连续多轮 acc 相同）
2. 预检误判：`unattended_preflight_view` 的 device_online 检测 `Device.objects.all()`——另一档案的离线模拟器（LDPlayer）阻塞本档案（Chrome 在线）启动
3. 前端 i18n 缺中文/英文文案：`dashboard.rotation_rule_placeholder` / `dashboard.loop_rotation` / hint 键在 zh/en locale 缺失，UI 显示 key 原文