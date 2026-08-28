---
date: 2026-08-22
symptom:
- commit-message
- N## claim without diff evidence
- M2 LOW activation rate
- REVIEW_TRIGGERED blocks commit
- phantom TD-382 misdiagnosis
solution: 'commit message 是改动描述面, 不是规则声称面: 用自然语言描述做了什么, 不写 N## 编号. 规则引用是文档/对话词汇. 仅在 diff 真有证据时才可在 message 写对应编号; 行为/合规类 (N192/N204/N193) 已由 BEHAVIORAL_N 豁免但仍不建议写.'
diff_keywords: ["commit-message", "claimed-rules", "M2", "review-triggered", "N## claim"]
related_files:
- scripts/hooks/check_claimed_rules.py
- .ai-memory/meta/ai-operating-handbook.md
created_by: AI
priority: high
level: L1
n_id: N208
topic: hook-failure
cross_refs: [N201, N192, N204, N193]
status: active
---

# N208: commit message 勿随意声称 N##（防 M2 误判 LOW / REVIEW_TRIGGERED）

## Symptom
AI 在 commit message 写「修复 N191」「遵循 N192/N204」等编号，但本次 diff 并未真正改动对应规则文件或含其 `diff_keywords` 证据。M2 钩子 `check_claimed_rules.py` 从 message 提取声称的 N## 并以 diff 证据核验 → 声称多证据薄 → 激活率拉低 → 反复触发 `REVIEW_TRIGGERED`，经 TD-376 闭环检查阻塞后续 commit。

## Root Cause
M2 的设计意图是「防声称多、证据薄的形式合规」：message 里写 N## 即视为对该规则的「声称」，必须有 diff 证据支撑，与 diff 本身是否含 N## 字样无关。本会话早前误把诊断指向 phantom `TD-382`（仓库从未注册），真实根因是 commit-message 卫生纪律缺失。

## Solution
- **commit message 是改动描述面，不是规则声称面**：用自然语言描述「做了什么」，不写 N## 编号。规则引用是文档/对话词汇，不是 commit 词汇。
- 仅在 commit 真实改动该规则文件且含 evidence 时，才在 message 写对应编号；否则用文字描述（如「修复情境约束链接」）。
- 行为/合规类规则（N192 双调试 / N204 诊断 / N193 任务归属）本就 diff 无代码证据，已在 `check_claimed_rules.py` 加 `BEHAVIORAL_N` 豁免集，视作 N/A 不计入 LOW 分母（可选人体工学改进，非 bug 修复）。
- 主修复 = AI 纪律，非代码。根因是文档全篇用 N## 当默认词汇、AI 把它迁移到 commit message 形成自我强化闭环。

## Related
- `scripts/hooks/check_claimed_rules.py`（`verify_claims` / `BEHAVIORAL_N`）
- `.ai-memory/meta/ai-operating-handbook.md` Part 2 行为红线
