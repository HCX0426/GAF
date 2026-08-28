---
spec_id: spec-54
title: TD-281 migration to fixed.md + plan-44 status sync + B-9~B-14 new TD registration
status: ✅ done
created: 2026-07-20
last_updated: 2026-07-20
related: spec-39 (TD-281 fix), spec-44 (plan-44 status), spec-53 (L3-1 scan that found these)
n167_score: 15/15 (3 dimensions, medium modification)
commit: -
---

# Spec-54: TD-281 状态迁移 + plan-44 状态同步 + B-9~B-14 新 TD 登记

> **来源**: spec-53 commit (`-`) 后 L3-1 轻量扫描发现 3 个 [A] 类 + 6 个新 [B] 类
> **目标**: (1) A-1 TD-281 已修复验证 + 迁移到 fixed.md; (2) A-2 plan-44 status 同步; (3) B-9~B-14 新 [B] 类登记到 active.md (TD-283~288)

## 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | N167 3 维度评分 (中修改) | ✅ | 2026-07-20 | - | 15/15 自决 |
| Phase 2 | A-1 TD-281 验证 + 迁移到 fixed.md | ✅ | 2026-07-20 | - | TD-281 剪切到 fixed.md, spec-39 commit - |
| Phase 3 | A-2 plan-44 status 同步 (⏳ → ✅) | ✅ | 2026-07-20 | - | plan-44 status ✅ done, commit - |
| Phase 4 | B-9~B-14 新 [B] 类登记到 active.md (TD-287~292) + TD-292 顺便闭环 | ✅ | 2026-07-20 | - | 5 新 TD 登记 + TD-292 修复后迁 fixed.md |
| Phase 5 | 验证 + commit + hash 回填 | ✅ | 2026-07-20 | - | doc_health P2=0 保持; commit - |

## §1 Background

### 1.1 来源

- spec-53 commit (`-`) 后 L3-1 轻量扫描 (①+② 维度)
- 发现 3 个 [A] 类:
  - A-1: TD-281 状态漂移 (active.md 中 TD-281 应迁移到 fixed.md, spec-39 Phase 4 + Phase 8 已修复)
  - A-2: plan-44 status 不同步 (⏳ pending 但 spec-44 已 ✅ done)
  - A-3: backend/tasks/resource_lock.py 未接入 dispatch_task (推迟到 [B] 类, 单 worker 不触发)
- 发现 6 个新 [B] 类 (B-9~B-14) 未登记到 active.md

### 1.2 现状

- TD-281 在 active.md 中标 🔧 待修, 但 spec-39 Phase 4 + Phase 8 已修复 3 个修复方案:
  - tech-stack.md §4 L177-179: v9.4 (spec-39 Phase 8) 已更新路径
  - GAF-optimal-solution.md L105-106: 已补全 backend 路径
  - architecture-overview.md §9.5: v3.2 (spec-39 Phase 2) 已标注 device_bridge 非 Django app
- plan-44 frontmatter status: ⏳ pending, 但 spec-44 已 ✅ done (commit -, C-071)
- 6 个新 [B] 类未登记 (B-9~B-14): message_compressor 未接入 / agent_selector 未接入 / except Exception 滥用 / coord_transformer TODO / api.generated.ts placeholder / active.md 顶部触发段过期

### 1.3 根因

1. **TD-281 状态漂移**: spec-39 Phase 4 + Phase 8 修复了 TD-281, 但 commit 时未按 §4.5 TD 状态迁移硬约束把 TD-281 段落剪切到 fixed.md
2. **plan-44 status 不同步**: spec-44 完成时只更新了 spec 文件 status, 未同步 plan 文件
3. **6 个新 [B] 类未登记**: L3-1 扫描新发现的问题, 之前未跑过这个维度的扫描

## §2 N167 3 维度评分 (中修改)

### 2.1 方案 A (TD-281 迁移 + plan-44 同步 + 6 新 TD 登记) ✅

| 维度 | 分数 | 理由 |
|------|------|------|
| 1. 架构长远性 | 5/5 | TD 状态迁移是 §4.5 硬约束 (✅ FIXED 必须迁出 active.md); plan status 同步是 §4.5 立即同步类; 新 [B] 类登记是 §4.8 硬约束 |
| 2. 全局归一化 | 5/5 | active.md 只留活跃 TD (归一); plan status 与 spec status 一致 (归一); 新 TD 按统一格式登记 |
| 7. 长期维护成本 | 5/5 | 一次性文档同步, 配套验证; TD-281 迁移后 active.md 减 1 条; 6 新 TD 登记"何时修"明确触发点 |
| **总分** | **15/15** | ≥ 9/12 阈值, AI 自决 |

### 2.2 反向论证 (为何不选 B/C)

- **方案 B (只做 A-1+A-2, 不登记新 TD)**: 10/15
  - 维度 1: 3/5 — 不补齐 §4.8 硬约束 (新 [B] 类必须登记)
  - 维度 7: 3/5 — 新 TD 不登记会丢失, 后续无法追踪
  - 不选理由: 违反 §4.8 "范围外技术债务必须登记" 硬约束

- **方案 C (A-3 ResourceLock 接入也合并到 spec-54)**: 8/15
  - 维度 1: 2/5 — A-3 涉及 dispatch_task 业务逻辑修改, 风险高, 应独立 spec
  - 维度 7: 2/5 — 合并增加 spec 复杂度, 测试范围扩大
  - 不选理由: A-3 单 worker 不触发, 应归 [B] 类, 不混入本 spec

### 2.3 硬场景 ③ 业务语义判定

- 问: 这个决策影响数据保留/业务流程吗?
- 答: N (文档状态同步 + 新 TD 登记, 不动业务代码)
- 结论: 可自决

## §3 实施计划

### 3.1 Phase 2: A-1 TD-281 验证 + 迁移

**验证** (已完成):
- ✅ `backend/device_bridge/platforms/macos/screenshot.py` 存在
- ✅ `backend/device_bridge/platforms/linux/screenshot.py` 存在
- ✅ `backend/device_bridge/apps.py` 不存在 (非 Django app)
- ✅ tech-stack.md §4 L177-179 已更新 (v9.4 spec-39 Phase 8)
- ✅ GAF-optimal-solution.md L105-106 已补全 backend 路径
- ✅ architecture-overview.md §9.5 device_bridge 已标注非 Django app (v3.2 spec-39 Phase 2)

**迁移**: 把 TD-281 段落从 active.md 剪切到 fixed.md, 标 ✅ FIXED, 附 spec-39 commit hash (- 是 spec-53, spec-39 commit 需查 git log)

### 3.2 Phase 3: A-2 plan-44 status 同步

- `.trae/plans/2026-07-20-spec44-monthly-check-slimming.md` frontmatter:
  - `status: ⏳ pending` → `status: ✅ done`
  - 加 `commit: -` (spec-44 commit hash)
  - 加 `completed: 2026-07-20`

### 3.3 Phase 4: B-9~B-14 新 TD 登记

按 active.md 现有格式登记 6 个新 TD (TD-283~286 已被 fixed.md 使用, 从 TD-287 开始):

| 新 TD ID | 来源 | 标题 | 优先级 | 何时修 |
|---------|------|------|:----:|-------|
| TD-287 | B-9 | message_compressor.py 未接入 AgentConsumer | P3 | spec-37 后端性能治理 spec |
| TD-288 | B-10 | agent_selector.py 未接入 dispatch_task | P3 | spec-37 agent 重构 spec |
| TD-289 | B-11 | backend/ 20+ 处 except Exception 防御性捕获 | P3 | spec-37 后端代码质量治理 spec |
| TD-290 | B-12 | coord_transformer.py:114 per-monitor detection TODO | P3 | spec-37 agent 重构 spec |
| TD-291 | B-13 | api.generated.ts:5987 screenshot_retention_gb placeholder | P3 | spec-37 前后端 schema 治理 spec |
| TD-292 | B-14 | active.md 顶部"下一 spec 触发"段过期 | P3 | 下次 spec 完成时一并同步 |

### 3.4 Phase 5: 验证 + commit + hash 回填

- 跑 doc_health_check 验证 (P0=0, P1=0, P2=0 保持)
- 跑 4 sync 工具
- commit spec-54 (含 spec-53 follow-up hash 回填)
- 回填 spec-54 hash (N176 follow-up, 不 commit)

## §4 风险

- **低**: 纯文档同步, 不动业务代码
- **TD-281 迁移**: 验证已 100% 确认 spec-39 修复 3 个方案, 迁移安全
- **新 TD 登记**: 每个新 TD 必填"修复方案验证"字段 (N174), grep 验证修复方向

## §5 飞轮效果

- active.md 瘦身: 9 → 14 个 TD (减 TD-281, 加 TD-287~292)
- 状态诚实: TD-281 不再"已修未迁"; plan-44 不再"⏳ 已完"
- L3-4 [B] 类评估闭环: 6 个新 [B] 类有明确触发点, 不再悬空
