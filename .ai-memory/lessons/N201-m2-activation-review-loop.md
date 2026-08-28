---
maintainer: manual
source: 对比 TEST_SFCAPI_LANGUAGE AI 大脑 (2026-08-16) — M2 激活率 6 条全 LOW 却无复盘闭环
load_when: [m2, claimed-rules, claimed-activation, activation-rate, review-loop, 复盘触发, 用户质疑]
priority: high
symptom: "M2 激活率'只测不治' — claimed-activation.md 已 6 条记录全 LOW 却无复盘闭环; rate 分母含 unknowable (声称无 lesson 的 N## 误判 LOW); 用户质疑无标准化响应协议"
solution: "复盘触发闭环: effective_rate 排除 unknowable (分母 0 → N/A 不参与判定); 累计有效记录 ≥ 3 且最近 3 条中 ≥ 2 条 < 50% → 🔴 警告 + REVIEW_TRIGGERED 标记 (幂等); AI 看到标记必按复盘模板 Q1-Q4 执行; 用户质疑四步响应 (确认→根因→修复→判沉淀)"
related_files:
  - scripts/hooks/check_claimed_rules.py
  - scripts/tests/test_check_claimed_rules.py
  - .ai-memory/ops/claimed-activation.md
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/meta/ai-operating-handbook.md
created_by: AI
topic: workflow
last_updated: 2026-08-16
n_id: N201
trigger_count: 1
last_triggered: 2026-08-16
diff_keywords:
  - check_claimed_rules
  - claimed-activation
  - review_trigger
  - REVIEW_TRIGGERED
  - 复盘触发
---

# N201 — M2 激活率"只测不治" + 用户质疑四步响应 (2026-08-16)

## 问题背景

对比 TEST_SFCAPI_LANGUAGE AI 大脑时发现: GAF 的 M2 声称-激活率回执
(`scripts/hooks/check_claimed_rules.py`) 已运行 1 天, `.ai-memory/ops/claimed-activation.md`
积累 6 条记录**全部 LOW** (0% / 0% / 25% / 0% / 40% / 0%), 但机制只打印 warn,
**从不触发复盘** — 数据在报警, 没有闭环处理 ("只测不治")。

TEST 侧对应机制: `workflow_rules.md §3 连续低激活率复盘规则` —
数据驱动强制复盘: 累计 ≥ 3 条记录 且 最近 3 条中 ≥ 2 条正向率 < 50%
→ 🔴 规则系统复盘警告 → ⏸️ 强制暂停询问用户 → 用户确认后执行复盘模板 (Q1-Q4),
用户拒绝则记录备注不阻塞主流程。N/A 记录 (改动极小无案例命中) 不参与判定。

## 根因分析 (三维)

- **代码层**: M2 的 `rate = positive / claimed_total` 把 unknowable (无 lesson /
  无 diff_keywords 回填) 算进分母 — `-` 声称 N200 但 N200 无 lesson,
  被标 0% LOW, 实为"不可判定"误判。且 main() 只写记录, 无读回+判定逻辑。
- **工作流层**: post-commit hook 是自动异步的, 无法像 TEST 工作流内那样
  "⏸️ 强制暂停问用户"; 需要把"触发 → 标记 → AI 下次任务开工时复盘"串起来。
- **规则层**: GAF 无"连续低激活率 → 复盘"规则; 用户质疑时也无标准化响应协议
  (TEST 有 §11 四步响应: 确认→根因→修复→判沉淀)。

## 修复方案 (本次实现)

### 1. check_claimed_rules.py — 复盘触发闭环

- **有效激活率**: `effective_rate = positive / (claimed - unknowable)`,
  分母为 0 → 记录为 `N/A` (不参与复盘判定, 对齐 TEST §3 N/A 跳过语义)
- **记录格式**: 表头加 `no-evidence` 列 (7 列), 兼容解析旧 6 列记录
- **复盘触发判定** `check_review_trigger`: 累计有效记录 ≥ 3 且最近 3 条有效中
  ≥ 2 条 < 50% → 触发
- **触发动作**: 打印 🔴 复盘触发警告 (含最近 3 条 commit+rate) +
  追加 `> 🔴 REVIEW_TRIGGERED (snapshot ..., trigger ...)` 标记行 (幂等)
- 退出码恒 0, post-commit 只提示不阻断

### 2. AI 行为规则沉淀

- **复盘警告处理**: AI 在任务开工/commit 反思时看到 REVIEW_TRIGGERED 标记
  → 按复盘模板执行 (Q1 根因 / Q2 规则调整 / Q3 声称清单更新 / Q4 规则文件更新)
  → 复盘结果写回 claimed-activation.md 备注或新段, 标记已处理
- **用户质疑四步响应** (TEST §11 借鉴): ① 确认事实 (Read/Grep 查证)
  → ② 追根因 (规范缺失? 没加载? 执行偏差?) → ③ 修问题 → ④ 判沉淀 (问用户)

## 反模式 (禁止)

- ❌ M2 只写记录不读回判定 (数据报警无闭环)
- ❌ rate 分母含 unknowable (声称无 lesson 的 N## 被误判 LOW)
- ❌ 复盘触发后 AI 自行跳过 (必须按模板执行 + 记录)
- ❌ 用户质疑时辩解/跳过查证 (必须先确认事实再解释再修)

## 已验证

- `pytest scripts/tests/test_check_claimed_rules.py` — 17 passed
  (新增: N/A 语义 / 复盘触发判定 / 幂等标记 / 6/7 列兼容解析)
- 手动跑 `check_claimed_rules.py --no-record` — 输出复盘触发警告
  (- 0% / - 40% / - 0%)

## 相关

- TEST 参照: `workflow_rules.md §3` (复盘触发) + `§11` (四步响应)
- 家族: N179 (反思形式化) — 本 N201 是 N179 的数据驱动解法 (低激活率数据
  自动触发复盘, 防"无 A 类就过")