---
date: 2026-07-21
topic: workflow/circular-mode-no-continue-prompt
priority: high
cross_refs: [N166, project_rules §3.6, ai-operating-handbook Part 2 自治边界]
status: active
created_by: AI
symptom: 循环模式下每个 spec 完成后 AI 问"继续?" — 违反 N166 循环模式规则
solution: 循环模式下 AI 主动接修下一个 TD/spec 直到用户叫停或 L3-4 终止条件, 不应问"继续?"; spec 全部 ✅ 后默认停下报告 + 等用户指令 (非循环模式)
related_files:
- .ai-memory/meta/ai-operating-handbook.md
- .trae/rules/project_rules.md
diff_keywords: ["circular-mode", "no-continue", "loop-mode", "n166"]
---

# Lesson: 循环模式不应问"继续?" (N166 L3-2 规则强化)

## 反模式 (用户反馈)

循环模式下每个 spec ✅ 后, AI 回复末尾问"继续?" / "是否继续?" / "下一步?" — 违反 N166 循环模式规则。

用户原话: **"循环模式这个连续spec还要问我吗?"**

## 正确行为

### 循环模式 (用户触发词进入, 见 project_rules.md §3.6)

- ✅ spec ✅ 后 AI 主动接修下一个 TD/spec (N166 L3-1 扫描 + L3-2 接修)
- ✅ 直到 L3-4 终止条件触发 (用户叫停 / 无活跃 TD / 上下文饱和 / 优先级耗尽)
- ❌ 禁止问 "继续?" / "是否继续?" / "下一步?" (违反 N166 L3-2 主动接修)
- ❌ 禁止 spec 全部 ✅ 后停下等用户 (循环模式默认不停)

### 非循环模式 (默认)

- ✅ spec 全部 ✅ 后停下报告 commit hash + 验证 evidence + 下一个候选 TD/spec
- ✅ 等用户明确指令 (进入循环模式 / 接修特定 TD / 停止)

### 判定规则

- 用户说"继续" / "循环模式" / "自动接修" → 进入循环模式, 后续 spec ✅ 不问"继续?"
- 用户说"停下" / "结束循环" / "停" → 退出循环模式, 回到非循环模式
- spec 全部 ✅ 后 AI 报告 + 下一个候选, 等用户指令 (非循环模式)

## 沉淀位置 (L1-小分发)

- ✅ lessons/circular_mode_no_continue_prompt.md (本文件)
- ✅ project_rules.md §3.6 循环模式段强化 (禁止问"继续?")
- ✅ ai-operating-handbook.md Part 2 自治边界段强化 (循环模式不问"继续?")

## 触发条件 (何时复查本教训)

- AI 在循环模式下问"继续?" → 立即重读本教训 + project_rules §3.6
- 用户再次反馈 "还要问我?" → 升级为 L1-中分发 (加 failure-modes 索引)

## 关联

- N166 循环模式 5 步 (L3-1 扫描 → L3-2 接修 → L3-3 实施 → L3-4 终止 → L3-5 实测验证)
- N109 spec 内自决 (spec ⏳/🔄 任务完成后不停下, 立即推进下一阶段)
- §3.6 循环模式触发词列表
