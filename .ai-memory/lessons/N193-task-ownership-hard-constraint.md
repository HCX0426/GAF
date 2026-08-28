---
maintainer: manual
source: 用户反馈 "为啥遗留优化没加进这个spec的里面，以后在当前任务发现的问题都归属当前任务" (2026-07-28)
load_when: [task-ownership, spec-finalization, leftover-suggestions, scope-creep, 抛锅模式, 遗留建议, N193]
priority: high
symptom: [kb:task-ownership-hard-constraint, N193, L0-missing, spec-completion]
solution: "当前任务中发现的所有问题必须立即纳入当前 spec (新增 task 或扩展现有 task), 不得作为遗留建议抛给用户; spec 全部 ✅ ≠ 任务完成 (任务完成 = spec 全部实现 AND 发现的问题全部处理); 超出范围的优化必须在 spec 已知限制段显式记录"
diff_keywords: [task-ownership, hard-constraint, spec-completion]
related_files:
  - .trae/rules/env-hardrules.md
  - .ai-memory/meta/failure-modes.md
  - docs/specs/archived/2026-07/2026-07-27-dual-debug-perspective-fixes.md
created_by: AI
topic: ai-autonomy
last_updated: 2026-07-28
---

# N193 — 任务归属硬约束 (spec 阶段全部 ✅ ≠ 任务完成)

## Problem（症状 / 触发条件）

2026-07-28 用户反馈: "为啥遗留优化没加进这个spec的里面，以后在当前任务发现的问题都归属当前任务"

### 现象
- AI 在 spec 阶段全部 ✅ 后默认任务完成
- 把实现过程中发现的优化建议/新问题作为"遗留建议"抛给用户决定
- 用户被迫二次确认才能让 AI 做本应在本次任务内完成的事
- 优化建议容易丢失 (下个对话 AI 不知道有这些建议)

### 触发条件

- spec/plan 驱动的任务,有 spec 文档 + 任务清单 + 阶段化实现
- AI 在 spec 完成 + 测试通过后准备宣布任务完成
- 实现过程中发现新问题 / 优化点 / schema 不一致 / 测试缺口 / 文档过时
- 最终总结准备写"遗留建议"/"超出 spec 范围"/"如需实现请告知"

## Root Cause（根因）

AI 对"任务完成"的定义不正确:

- ❌ 错误定义: spec 全部实现 + 测试通过 = 任务完成
- ✅ 正确定义: spec 全部实现 AND 发现的问题全部处理 = 任务完成

这种"抛锅"模式导致:
1. 用户需二次确认才能让 AI 做本应在本次任务内完成的事
2. 优化建议容易丢失 (下个对话 AI 不知道有这些建议)
3. 违反"任务完成"的真实定义

## Solution（修复方案）

### L0 硬约束 (env-hardrules.md)

见 `.ai-memory/meta/env-hardrules-contextual.md` "任务归属硬约束 (N193)" 段。

### 核心约束

1. **当前任务中发现的所有问题归属当前任务**: 实现过程中发现的优化建议、新 bug、schema 不一致、测试缺口、文档过时等, 必须立即纳入当前 spec (新增 task / 扩展现有 task), 不能作为"遗留建议"抛给用户。
2. **spec 阶段全部 ✅ ≠ 任务完成**: 任务完成的真实定义 = spec 全部实现 AND 发现的问题全部处理 (实现或显式降级为 P4+ 并记录到 spec 的"已知限制"段)。
3. **禁止"遗留建议"模式**: 不得在最终总结中使用"遗留优化建议供后续参考"/"超出 spec 范围"/"如需实现请告知"等表述。
4. **优化建议分级**: 发现的优化建议若确实超出当前 spec 范围 (如需引入新依赖/新架构), 必须在 spec 文档的"已知限制"段显式记录, 包含: 描述 + 影响范围 + 建议优先级 + 为何不本次实现。

### 完成前必跑: 任务归属复查清单

```text
□ 1. 实现过程中是否发现新问题 / 优化点? → 有则立即纳入 spec
□ 2. spec 阶段全部 ✅ 后, 是否主动扫描实现过程中的"假设"/"简化"/"临时方案"? → 有则补 task
□ 3. 测试失败修复后, 是否检查根因 (而非只改测试断言)? → 根因是代码问题则补 task 修代码
□ 4. 最终总结是否包含"遗留建议"/"超出 spec 范围"/"如需实现请告知"? → 有则违反本约束
□ 5. spec 文档是否有"已知限制"段? → 超出范围的优化必须记录在此段
□ 6. 自问: "我是否把本应本次做的事抛给了用户?" → 是则违反本约束
```

## Verification（验证）

- spec `2026-07-27-dual-debug-perspective-fixes.md` 归档时, 阶段 12 "预先存在的问题清零" 全部实现 (Task 7.1-7.5 ✅)
- plan `2026-07-28-dual-debug-and-schema-followup.md` 12 项验收全部 ✅
- N194 pytest-django 拖慢问题在发现后立即纳入 spec 阶段 12 并实现, 未作为"遗留建议"抛出

## Reflection（反思 — N193 反思链本身）

这是第 5 次"AI 反复违反 + 用户反馈 + 沉淀到 L0"的循环:
- N188: conda 环境 → L0
- N190: PowerShell heredoc → L0
- N191: schema 归一化 → L0
- N192: 双调试视角 → L0
- N193: 任务归属 → L0

模式: 每次发现 AI 反复违反的问题, 必须升级到 L0 硬约束, 而不是只写 lesson。

## Related Lessons

- N188: conda gaf 环境规则 — 同样是"AI 反复违反 + 升级到 L0"模式
- N192: 双调试视角 — N192 关注「报错可调试」, N193 关注「任务归属」, 二者互补
- N194: pytest-django 拖慢 — N193 任务归属约束的首次应用 (发现测试慢立即纳入 spec 并沉淀)
