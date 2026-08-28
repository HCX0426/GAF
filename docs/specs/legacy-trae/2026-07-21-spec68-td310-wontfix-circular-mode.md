---
spec_id: spec-68
title: 'TD-310 07-20 单日 24 spec 异常集中 wontfix (评估结论: 真实工作量非过度拆分) + 循环模式规则强化沉淀 (N166 L3-2)'
status: ✅ done
created: 2026-07-21
owner: AI
priority: P2
related_tech_debt: [TD-310]
n167_score: G=30/wontfix=28/A=28/B=25 (最高 G 领先 2 分 < 5, 评估型 TD 直接 wontfix+沉淀)
---

# spec-68: TD-310 wontfix + 循环模式规则强化沉淀

## 背景

TD-310 登记时即为"评估为主, P2"。spec-68 评估结论:
- 07-20 spec-43~spec-57 (15 spec) 是 RBAC + DB 治理 + 路径漂移 3 轮修复的真实工作量
- 24 spec 文件中 spec-43/44/45 各 2 个同名前缀文件 (spec + 补充)
- L3-1 全量扫描 24 spec < 1s (可接受, 非性能瓶颈)
- 加合并阈值会增加 AI 决策负担 (每次拆 spec 判断是否合并)
- 评估结论: wontfix, 沉淀到 lessons/

用户反馈 "循环模式这个连续spec还要问我吗?": 循环模式下 AI 主动接修下一个 TD/spec, 不应问"继续?"。N166 规则强化沉淀。

## Phase 1: 读 TD-310 + 07-20 spec 分布 (✅)

- [x] 1.1 读 active.md TD-310 段落
- [x] 1.2 统计 07-20 spec 分布 (24 文件, spec-43~spec-57 集中)

## Phase 2: N167 七维度评分 (✅)

- [x] 2.1 4 方案评分: A 加合并阈值 28 / B 按日分片 25 / G wontfix+沉淀 30 / wontfix 不沉淀 28
- [x] 2.2 最高 G=30 领先第二名 2 分 < 5 分阈值; TD-310 登记时"评估为主" → 直接 wontfix+沉淀评估结论

## Phase 3: wontfix TD-310 + 沉淀评估到 lessons/ (✅)

- [x] 3.1 active.md TD-310 段落 (🔧 → ❌ wontfix)
- [x] 3.2 fixed.md 追加 TD-310 wontfix 段落
- [x] 3.3 lessons/workflow_spec_concentration_2026-07-20.md 评估结论沉淀

## Phase 4: 循环模式规则强化沉淀 (N166 L3-2) (✅)

- [x] 4.1 lessons/circular_mode_no_continue_prompt.md 沉淀
- [x] 4.2 project_rules.md §3.6 循环模式规则强化 (L1-小分发: rules + handbook)
- [x] 4.3 ai-operating-handbook.md Part 2 自治边界段强化

## Phase 5: active.md 计数 + commit + 反思 (✅)

- [x] 5.1 active.md 顶部计数 6 → 5
- [x] 5.2 git commit
- [x] 5.3 反思段

## 反思 (小修改+评估型+沉淀型 spec, 跑 4 问 + 状态标记)

### ① 4 问反思

1. **改了什么**: TD-310 wontfix (评估结论沉淀 lessons/) + 循环模式规则强化 (project_rules §3.6 + handbook Part 2 + lessons/circular_mode_no_continue_prompt.md, L1-小 3 层分发)
2. **为什么改**: TD-310 评估结论 wontfix (07-20 真实工作量非过度拆分); 用户反馈 "循环模式这个连续spec还要问我吗?" 违反 N166 L3-2 主动接修规则
3. **怎么验证**: 七维度评分 4 方案 (G=30/wontfix=28/A=28/B=25) + lessons 沉淀 + rules/handbook 强化
4. **影响范围**: 文档治理 + 规则强化, 不涉及代码; active.md 6→5 活跃 TD

### ② 状态标记

- ✅ spec-68 done (TD-310 wontfix + 循环模式规则强化)
- ✅ active.md 6 → 5 活跃 TD
- ✅ L1-小 3 层分发完成 (lessons + rules + handbook)
- ✅ 循环模式规则强化: 下次循环模式 AI 不再问"继续?"

### ③ A/B/C 改进

- A: 当前 wontfix + 沉淀评估结论是合理选择 (避免 over-engineering)
- B: 可选 — 加 spec 合并阈值规则 (A 方案 28/35), 但增加 AI 决策负担, 不加
- C: 选 A (当前 wontfix + 沉淀, 留待单日 spec > 30 时重新评估)

### ④ 根因分析 (循环模式问"继续?")

- **直接根因**: spec-65/66/67 末尾 AI 习惯性问"继续?", 未激活 N166 L3-2 主动接修规则
- **深层根因**: project_rules §3.6 已有禁止规则, 但 AI 未在循环模式下主动激活; 需在 lessons + handbook 强化
- **教训**: 用户反馈后立即沉淀 (N172 边执行边沉淀), 不等用户说"这个要沉淀"

### ⑤ 上下文管理

- 本次 spec-68 上下文使用合理: 评估型 spec, 主要工作在文档治理 + lessons 沉淀; 未触发 N160 上下文饱和
