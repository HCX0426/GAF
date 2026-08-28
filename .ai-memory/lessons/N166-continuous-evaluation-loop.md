---
n_id: N166
topic: workflow
title: 持续评估+循环修复模式（任务间空闲主动寻缺）
date: 2026-07-16
priority: high
category: workflow
severity: P0
symptom: spec 全部完成后 AI 停下等用户；用户对话中的工作模式要求未沉淀到文档
solution: 新增 L3 持续评估循环（spec ✅ 后扫描 6 评估源→[A/B/C] 分级→[A] 开 spec→循环到终止条件）+ 沉淀纪律（用户要求当轮沉淀到 rules/handbook/lessons/yn-matrices）
diff_keywords: [evaluation-loop, loop-review, idle]
related_files:
  - .trae/rules/project_rules.md
  - .ai-memory/meta/ai-operating-handbook.md
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/meta/yn-matrices/archived-yn-matrices/_workflow-spec.md
created_by: AI
cross_refs:
  - N161
  - N109
  - N127
  - N113
  - N134
related_rules:
  - project_rules.md §3.6 AI 自决范围
  - project_rules.md §4.6 循环迭代反思
  - ai-operating-handbook.md Part 2 自治边界
status: active
level: L1
---

# N166 — 持续评估+循环修复模式（任务间空闲主动寻缺）

## 触发原话（用户反馈）

> "现在ai做任务是按照什么流程来的，没有循环执行评估，或者接着任务的了吗，没任务就接着评估这个项目能评估的地方啊，评估完然后有问题就开始修复，上面所有对话的，我的要求咋都没主动沉淀到文档里？"

结合上一轮指令：
> "所有要修的弄个spec再开始，而且你都发现问题了，就不要停下来问我了，直接开做，做完评估，循环到没问题，以后都这样"

## 根因

现有 AI 工作模式只有两层循环，缺第三层：

| 层级 | 现状 | 是否存在 |
|:----:|------|:------:|
| L1 任务内步骤推进 | N109/N127 计划内任务自决推进下一段 | ✅ |
| L2 任务内反思循环 | §4.6 Round 1→N 直到无新 A 类问题 | ✅ |
| **L3 任务间持续评估循环** | 任务完成后主动找下一个可改进点 → 开新 spec → 修复 → 再评估 | ❌ **缺失** |

L3 缺失导致：
- spec 全部 ✅ 后 AI 直接停下等用户
- 用户明明说"做完评估循环到没问题"但 AI 只跑了 1 轮就停
- 项目有大量可评估的地方（tech-debt/active.md 12 项 / pending-roadmap.md Review Checklist / 月度健康检查 84 项 / 架构评估文档），但 AI 不会主动触发
- 用户对话中的要求没沉淀成规则，下次对话 AI 又会犯同样错误

## 解决方案（三层循环模式）

### L3 持续评估循环流程

```
任务完成（spec 全部 ✅）
  ↓
L3-1 扫描可评估清单（多维度 — 用户反馈 2026-07-16 扩充）:
     ① 文档层: tech-debt/active.md 🔧/🚧 + pending-roadmap.md Review Checklist + monthly-health-check.md 上次报告 ❌/⚠️ + architecture/*-evaluation.md "待优化" + specs/ 中 ⏳/🔄
     ② 代码层: ruff/mypy/tsc 预存错误、测试覆盖率、死代码、重复实现
     ③ 架构层: 跨平台抽象是否到位、模块边界、FK 合理性、双套并存反模式
     ④ 界面层: 前端页面功能是否完整实现、交互元素是否全部可点击、响应式布局、无障碍属性
     ⑤ 功能层: spec 中设计的功能是否全部落地、是否有"🔧代码存在"标记未升 ✅
     ⑥ 业务逻辑层: 状态机流转、边界条件、错误处理、并发安全
     ⑦ 数据层: 变量/属性命名是否准确、字段是否被使用、DB schema 是否合理、migration 是否一致
     ⑧ 多 app 层: 各 Django app 功能是否独立完整、app 间依赖是否合理、是否有死 app
     ⑨ 集成层: 前后端 API 契约一致性、WS 实际连通、Agent ↔ Backend 协议一致性
  ↓
L3-2 评估发现 → 分级:
     [A] 立即开 spec 修复（P0/P1 + 改动量 < 500 行）
     [B] 登记到 tech-debt/active.md（P2/P3 或 > 500 行需拆分）
     [C] 无法解决（登记 wontfix.md）
  ↓
L3-3 [A] 类 → 开新 spec → 修复 → 回到 L3-1 继续扫描
L3-3 [B]/[C] 类 → 登记后继续扫描下一个评估点
  ↓
L3-4 终止条件（满足任一）:
     ① 连续扫描 2 轮无新增 [A] 类
     ② 所有 [A] 类已修复且 [B] 类已登记
     ③ 上下文预算告警（N160: ≥ 15 轮提示新开对话）
     ④ 用户显式叫停
```

### L3-5 实测验证（用户反馈 2026-07-16 强制）

**单元测试不够，必须打开 GAF 实际点击测试**：

- ✅ 前后端单元测试只覆盖"代码逻辑正确"，不覆盖"实际运行时交互"
- ✅ 必须启动 backend + frontend + agent，打开浏览器实际点击页面交互元素
- ✅ 验证：WS 实际连通、UI 交互元素全部可点击、前后端数据流端到端、Agent 实际响应
- ✅ 使用 Playwright E2E (主推) + browser-use (快速验证) — 见 `docs/standards/testing-conventions.md` §4.4
- ✅ 测试结果用表格记录：每项 ✅/❌，JS 错误数 — 见 project_rules.md §4.3
- ❌ 禁止只跑 pytest 就标 ✅（前后端测不到的：UI 渲染、WS handshake、实际设备响应等）

### 沉淀纪律（用户要求落地）

用户在对话中提出的要求，AI 必须**主动**沉淀到对应文档，不等用户提醒：

| 要求类型 | 沉淀位置 | 触发时机 |
|---------|---------|---------|
| 工作模式/流程要求 | `project_rules.md` 对应章节 + `ai-operating-handbook.md` Part 2 | 立即（当轮任务结束前） |
| 新反模式/坑 | `failure-modes.md` N## 索引 + `lessons/<topic>_<date>-<n##>.md` + 对应 yn-matrices sub-file | 立即（commit 前） |
| 架构原则 | `project_rules.md` §2.0.x + `.ai-memory/summaries/architecture-mistakes.md` | 立即 |
| 命令/工具用法 | `ai-operating-handbook.md` Part 2 对应红线段 | 立即 |

**判定标准**（只问 1 个问题）：用户说的这句话，下次对话 AI 是否需要遵守？
- 是 → 必须沉淀（L1 教训走 4 层：lessons + arch-mistakes + yn-matrices + failure-modes 索引行 + rules 硬约束）
- 否 → 不沉淀（L0 历史记录只写 lessons/）

## 防错机制

- ❌ spec 全部 ✅ 后停下等用户 → ✅ 立即进入 L3-1 扫描可评估清单
- ❌ 评估发现 [A] 类但不开 spec 直接修 → ✅ 必须开 spec（用户要求"所有要修的弄个 spec 再开始"）
- ❌ 用户要求只在当前对话生效 → ✅ 立即沉淀到对应文档（rules/handbook/lessons）
- ❌ 评估一轮就停 → ✅ 循环到 L3-4 终止条件满足
- ❌ 沉淀时只写 lessons 不更新 rules → ✅ L1 教训走 4 层分发（§6.2 真二分制）

## 验证

- [x] 本 lesson 已创建
- [x] failure-modes.md N166 索引行已追加
- [x] project_rules.md §3.6 已追加 L3 持续评估循环硬约束
- [x] ai-operating-handbook.md Part 2 已追加沉淀纪律红线
- [x] yn-matrices/_workflow-spec.md 已追加 L3 循环 Y/N 矩阵

## 关联

- 上一轮指令："所有要修的弄个spec再开始，做完评估循环到没问题，不要停下来问"（已沉淀到 N161）
- 本轮指令："没任务就接着评估，评估完有问题就开始修复"（沉淀到 N166）
- 本轮指令："要求咋都没主动沉淀到文档里"（沉淀到 N166 沉淀纪律段）

## 修订记录 (2026-08-21): 沉淀触发审慎化

- 用户反馈: "用户对话要求必须主动沉淀，这不好，每次我反问，或者追问时，你要主动思考这个该不该沉淀"
- 根因: 旧表述"必须主动沉淀，不等提醒"把"用户说话"当无条件触发 → AI 因用户每次反问/认可就沉淀, 导致过度沉淀 (本次对话用户仅"认可"即沉淀 N206)
- 修订: §3.8 第 1 条改为 "用户反问/追问时, 主动思考该不该沉淀" (1 问判定标准审慎判断, 非必要不沉淀); handbook 沉淀纪律段新增 "反问/追问 = 评估时机, 非必然沉淀"
- 判定: 反问/追问 → 主动评估 (非必然沉淀); 用户明确要求沉淀 → 必须沉淀 (N166 原意保留); 1 问判定标准不变
