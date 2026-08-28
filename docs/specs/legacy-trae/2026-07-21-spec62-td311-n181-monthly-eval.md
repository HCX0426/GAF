---
spec_id: spec-62
title: TD-311 N181 规则退役机制强化 (季度→月度 + Active N## > 70 硬阈值紧急评估)
status: ✅ done
created: 2026-07-21
owner: AI
task_type: documentation
td_refs: [TD-311]
---

# spec-62: TD-311 N181 规则退役机制强化

## 背景

2026-07-21 元评估发现 Active N## 60 条 (v9.1 归一化时 51 条 → 当前 60 条, 增长 9 条对应 N164-N181 新增)。
N181 季度评估频率可能不够, 季度间可能新增 10+ N## (如 2026-07 单月新增 N176-N181 6 条)。

## 修复方案 (A+B 组合)

### Phase 1: N181 频率调整

- [x] 1.1 §4.12 N181 段: "每季度 (3 个月) 评估" → "每月评估"
- [x] 1.2 加硬阈值: "Active N## > 70 触发紧急评估" (类似 failure-modes.md P5 硬阈值机制)
- [x] 1.3 调整退役条件 A 阈值: "连续 5 spec 未触发" → "连续 3 spec 未触发" (月度评估下更敏感)
- [x] 1.4 同步更新 failure-modes.md N181 索引描述

### Phase 2: 验证

- [x] 2.1 grep "季度评估" project_rules.md → 1 处 (修订说明 "原'季度评估'频率不足", 历史描述保留) ✅
- [x] 2.2 grep "Active N## > 70" project_rules.md → 1 处 ✅
- [x] 2.3 grep "连续 3 spec" project_rules.md → 1 处 (N181 段) ✅
- [x] 2.4 failure-modes.md body 163 ≤ 170 (margin -7) ✅

## 反思 (小修改 < 20 行, 跑 ① 4 问 + ④ 状态标记)

① 4 问:
1. 改动量是否最小? 是 (§4.12 段 3 处修订 + failure-modes.md N181 索引 1 处同步, 约 8 行实质改动)
2. 是否引入新依赖? 否
3. 是否破坏现有功能? 否 (N181 退役机制强化, 不影响已退役的 N165/N170)
4. 是否需要沉淀? 是 (已同步 failure-modes.md N181 索引 + spec-62 spec 文件)

④ 状态标记:
- spec-62: ✅ done
- TD-311: ✅ FIXED (待迁 fixed.md)
