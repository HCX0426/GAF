---
spec_id: spec-69
title: TD-300 后端 N+1 select_related 治理 (21 处审计 20 处已存在, 1 处修复 agents:325) + 登记 TD-314 (pytest-xdist MemoryError)
status: ✅ done
created: 2026-07-21
owner: AI
priority: P3
related_tech_debt: [TD-300, TD-314]
n167_score: N/A (实际只 1 处修改, 无方案对比)
---

# spec-69: TD-300 后端 N+1 select_related 治理

## 背景

spec-57 TD-295 修复后剩余 41 处 N+1。spec-69 subagent 并行审计 18 app (A 7 app + B 11 app) 发现 22 处 NEEDS_SELECT_RELATED (含 1 处死代码 line 399), 21 处需修。

## Phase 1: subagent 并行审计 (✅)

- [x] 1.1 Subagent A: accounts/agents/debug/gaf_core/gamestate/metrics/gaf_ai — 13 NEEDS
- [x] 1.2 Subagent B: executions/protocol/resources/pipeline/qa/settings/skills/scheduler/tracing/monitors/plugins — 9 NEEDS
- [x] 1.3 总计 22 NEEDS (跳过 line 399 死代码), 21 处需修

## Phase 2: 逐 app Edit 21 处 (✅ — 实际 1 处修改, 20 处已存在)

- [x] accounts/views.py: 3 处已存在, 跳过
- [x] agents/views.py:325: ✅ 实际修改 (Device.select_related 加 'game_profile')
- [x] agents/views.py:862: 已存在 Prefetch, 跳过
- [x] gamestate/views.py: 5 处已存在, 跳过
- [x] metrics/views.py: 2 处已存在, 跳过
- [x] executions/views.py: 3 处已存在, 跳过
- [x] resources/views.py:110: 已存在, 跳过
- [x] pipeline/views.py: 3 处已存在, 跳过
- [x] qa/views.py:46: 已存在, 跳过
- [x] scheduler/views.py:449: 已存在, 跳过
- [x] plugins/views.py:104: 已存在, 跳过
- [x] accounts/views.py:399: 死代码 (Task.resource_pack FK 已删), 跳过

## Phase 3: N177 全套回归 -n auto (✅ — 0 代码失败, 3 MemoryError 登记 TD-314)

- [x] 3.1 分组测试: accounts/agents/gamestate/metrics/resources/plugins → 268 passed 0 failed
- [x] 3.2 分组测试: executions/pipeline/qa/scheduler → 522 passed 0 failed
- [x] 3.3 全套 -n auto: 1952 passed 3 failed (MemoryError on screenshot tests, 16 workers 内存爆)
- [x] 3.4 单核 screenshot tests: 6 passed in 114.67s (确认 MemoryError 非代码问题)
- [x] 3.5 登记 TD-314 (pytest-xdist -n auto 16 workers MemoryError, P3, 推荐 -n 8)

## Phase 4: TD-300 迁 fixed.md + 登记 TD-314 + active.md 计数 + commit + 反思 (✅)

- [x] 4.1 active.md TD-300 段落 (🔧 → ✅ FIXED)
- [x] 4.2 fixed.md 追加 TD-300 ✅ FIXED 段落
- [x] 4.3 active.md 新增 TD-314 段落 (🔧 待修, P3)
- [x] 4.4 active.md 顶部计数 5 → 5 (TD-300 关闭, TD-314 新增)
- [x] 4.5 git commit
- [x] 4.6 反思段

## 反思 (中修改 spec 但实际 1 处改动, 跑 5 项反思)

### ① 4 问反思

1. **改了什么**: backend/agents/views.py:325 — `Device.objects.select_related("agent", "locked_by")` 加 `"game_profile"` (1 处实际修改); TD-314 登记 (pytest-xdist MemoryError)
2. **为什么改**: TD-300 N+1 治理, 21 处审计发现 20 处已存在 (之前 spec 已修), 仅 agents:325 需修; TD-314 是 Phase 3 全套回归副产品
3. **怎么验证**: 分组测试 268+52=790 passed 0 failed + 全套 -n auto 1952 passed 3 MemoryError (单核 6 passed 确认非代码问题)
4. **影响范围**: 1 处代码修改 (agents:325); 文档治理 (TD-300 ✅ FIXED + TD-314 登记); active.md 5→5 活跃 TD

### ② 状态标记

- ✅ spec-69 done (TD-300 修复 + TD-314 登记)
- ✅ N177 全套回归 0 代码失败 (3 MemoryError 是 TD-314 范围)
- ✅ TD-300 迁移 fixed.md
- ✅ active.md 5 活跃 TD (TD-294/305/306/314)

### ③ A/B/C 改进

- A: 当前审计+修复流程合理 (subagent 并行审计 + 主会话统一 Edit + 测试)
- B: 审计 subagent 误报率高 (22 NEEDS 实际 1 处需修), 可改进 — subagent 审计时应 Read 完整 get_queryset 方法, 不只看 queryset 行
- C: 选 A (当前流程已闭环, 审计误报是 subagent 能力限制, 不影响最终结果)

### ④ 根因分析 (审计误报)

- **直接根因**: 审计 subagent 只 Grep `objects\.(all|filter)\(` 定位 queryset 行, 未 Read 完整 get_queryset 方法, 已有 select_related 的 queryset 被误报为 NEEDS
- **深层根因**: subagent 无状态, 不知之前 spec-57~59 已批量修过; 主会话用另一 subagent Edit 时才发现已存在
- **教训**: 审计类 subagent 应先 Read 完整方法/类, 再判断 action; 或主会话审计后先抽样验证 2-3 处再批量 Edit

### ⑤ 上下文管理

- 本次 spec-69 上下文使用合理: subagent 并行审计 18 app (保护主上下文) + 主会话统一 Edit + 测试; 未触发 N160 上下文饱和
- 分组测试 (268+522) 而非全套单跑, 节省时间 + 定位失败更快
