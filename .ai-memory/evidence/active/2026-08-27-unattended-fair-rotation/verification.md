---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-27-unattended-fair-rotation/
load_when: [evidence, unattended, rotation]
priority: high
symptom: [verification]
solution: 测试命令与真实 E2E 结果
related_files:
  - backend/scheduler/tests/test_loop_rotation.py
created_by: AI
last_updated: 2026-08-27
---
## Verification

单元回归：
- `pytest backend/scheduler -q` → 55 passed（含新公平轮换测试）
- `ruff check` 改动文件 → All checks passed
- `frontend npx tsc -b --noEmit` → 0 错误

真实 E2E（daemon 服务 + Chrome 设备 + 自建数据）：
- 自建链路数据：profile BrowserCycle-E2E + chain cycle-baidu-chain（克隆已验证的百度循环任务 cycle-baidu-loop，非存量资源包）+ 2 账户 + 轮换规则 sequential + Chrome-Browser 绑定
- `POST unattended/start {game_profile_id:2, rotation_rule_id:1, loop_rotation:true}` → session 6
- 80s 内 CE 序列：`(21,acc2),(22,acc1),(23,acc2),(24,acc1),(25,acc2)` —— **严格交替，5 轮全 success**
- session6: status=running, cursor=3, completed=3, failed=0 —— 归还 + 循环成立
- preflight（带 game_profile_id）：`设备在线 通过（全部 1 个设备在线）`（此前跨档案 LDPlayer 离线阻塞已修复）
- i18n：无人值守页显示「选择轮换规则（未选择=不轮换）」「循环轮换」中文文案（此前显示 key 原文）