---
date: 2026-08-28
symptom: [e2e-prereq-missing, skip-instead-of-setup, unattended-not-tested]
solution: E2E 前置配置缺失（缺 GameProfile.routine / 设备绑定 / 默认链）时，应主动构造配置把入口跑通；禁止以"环境前置缺失"标注跳过，除非构造成本超出测试价值并显式告知
related_files:
  - backend/scheduler/unattended_views.py
created_by: AI
priority: medium
n_id: N210
diff_keywords: ["e2e", "前置", "skipped", "跳过", "unattended", "配置"]
---

# E2E 前置缺失 ≠ 跳过：应主动构造配置跑通

## 症状（2026-08-28 用户两次纠正）

- 第一次：无人值守入口无 GameProfile.routine → 我标注"前置缺失未测" → 用户纠正"失败你不会解决？"
- 教训：环境前置（默认例程/设备绑定/账户）是**可构造的测试数据**，不是不可逾越的障碍

## 根因

把"当前 DB 恰好没有配置"误当成"入口不可测"。单机开发环境里，测试前置就是测试夹具的一部分——与单元测试里造 fixture 同理。构造成本通常几十秒（`setup_unattended.py` 三行 ORM 更新）。

## 解决方案

1. 测某入口前先列出其前置条件（读 view 代码即可得：`game_profile__default_routine__isnull=False` 之类过滤）
2. 前置可构造（配置/数据/绑定）→ 构造后真实跑通，禁止"跳过"
3. 仅当前置构造涉及不可逆大改动（如真实游戏账号/外部服务）时才标注不可测，并说明**为什么不可测 + 已覆盖部分**（核心派发若已被其它入口覆盖需指出）
4. 测试配置改动 DB 后，在汇报里明示"已为测试保留/可还原"，避免悄悄改环境