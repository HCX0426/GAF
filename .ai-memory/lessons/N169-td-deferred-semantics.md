---
date: 2026-07-18
symptom: [tech-debt, deferred, wait-for-user, semantics]
solution: TD "延后" 语义 = 做完上一个 spec/类别后立即接着做, 不是等用户指令; AI 主动按优先级接修
diff_keywords: [tech-debt, deferred, wait-for-user]
related_files:
  - .trae/rules/project_rules.md
  - docs/project-status.md
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/meta/yn-matrices/_workflow-commit.md
created_by: AI
priority: high
n_id: N169
topic: workflow
status: retired
superseded_by: N166
level: L1
---

# N169: TD "延后" 语义错位 — 等用户指令 vs 接着做

> **⚠️ 已退役 (spec-33 Phase 4 合并)**: 本 N## 已并入 N166 (L3 循环被动触发家族), failure-modes §Retired 标注。核心约束 (TD "延后" 语义 + TD 处理顺序) 已并入 `project_rules.md §4.8` 硬约束, Y/N 矩阵在 `.ai-memory/meta/yn-matrices/_workflow-commit.md` ㊱ 段。本文件仅作历史事件记录保留。

## 触发原话

> "要是有技术债务，为啥会延后，延后也是指在做完上一个类别接着做，而不是等我的指令"

## 症状

`docs/archive/active-tech-debt.md` 中 98 个 TD 的 "何时修" 字段大量使用模糊延后写法:
- "后续 Phase (P3, 不阻塞功能)"
- "下次 TaskExecution 模型重构"
- "下次 yn-matrices 维护"
- "下次文档治理 spec"

用户反馈: 这种写法让 AI 误以为"延后 = 等用户指令修", 实际上"延后"应该是"做完上一个 spec/类别后立即接着做"。

## 根因

1. **语义错位**: "何时修" 字段的"延后"被 AI 理解为"等用户主动指令修", 但用户意图是"做完上一个类别后接着做"
2. **缺乏明确触发点**: "下次 XXX 重构" / "后续 Phase" 没有明确的 spec 编号或触发条件, 等于无触发点
3. **缺乏主动接修机制**: rules §4.8 只说"必跑 Review Checklist 挑 1-2 个推进", 没有明确"AI 主动按优先级接修, 不等用户指令"
4. **优先级清单缺失**: active.md 没有顶部优先级清单, AI 无法快速判断下一个该修哪个

## 影响

- TD 堆积: 98 个 TD 中大部分处于 🔧 状态, 实际未推进
- AI 行为被动: spec 完成后等用户指令, 不主动接修
- 用户需手动驱动: 每次都要用户说"现在修 TD-XXX", 违背 "GAF 是 AI 主导" 定位

## 修复

### 1. project_rules.md §4.8 强化 (已完成)

新增硬约束:
- ✅ **"延后" 语义**: "何时修" 字段禁止写"等用户指令"类被动语义; "延后" = 做完上一个 spec/类别后立即接着做
- ✅ 合法写法: "spec-XX 完成后立即接修" / "下一 spec" / "L3 Round N 后接修" (明确触发点)
- ❌ 禁止写法: "后续 Phase" / "下次重构" / "待定" / "看情况" (模糊延后 = 等用户指令)
- ✅ **TD 处理顺序**: 当前 spec 全部 ✅ 后, AI 主动按优先级 (P1 > P2 > P3) + 登记时间接修下一个 TD, 不等用户指令

### 2. active.md 顶部加优先级清单 (已完成)

新增 "TD 处理顺序" 段:
- AI 自动接修规则 (4 条)
- "何时修" 字段语义 (合法/禁止写法)
- 当前待修 TD 优先级清单表 (16 个主要 TD, 按优先级 + 登记时间排序)
- 下一 spec 触发点明确

### 3. 过渡说明 (已完成)

active.md 加过渡说明: 以下各 TD 的 "何时修" 字段为历史写法, 实际处理以顶部清单为准, 各 TD 字段留待 spec-32 文档治理 spec 统一改。

## 验证

- ✅ project_rules.md §4.8 含 "延后" 语义硬约束 + 合法/禁止写法
- ✅ active.md 顶部含 "TD 处理顺序" 段 + 优先级清单表
- ✅ active.md 顶部含过渡说明
- ⏳ 待验证: spec-27 完成后, AI 是否主动接修 spec-28 (TD-132 e2e 验证, P2 优先)

## Y/N 检查矩阵

详见 `.ai-memory/meta/yn-matrices/_workflow-commit.md` §㊱ N169。

## 与相关 N## 的关系

- **N166 (L3 循环)**: N166 定义"spec ✅ 后进入 L3-1 扫描", N169 进一步明确"扫描发现 [A] 类后立即接修, 不等用户指令"
- **N161 (自决不推卸)**: N161 是"架构决策不推卸给用户", N169 是"TD 处理不推卸给用户", 同根因家族
- **N164 (L1/L2 不加载教训)**: N169 是 L1 教训, 必须走 4 层分发, 避免 N164 重复犯错
