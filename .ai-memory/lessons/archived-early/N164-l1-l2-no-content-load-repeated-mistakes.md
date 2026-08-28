---
date: 2026-07-14
symptom: [l1-no-content-load, l2-missing-redlines, repeated-mistakes, failure-modes-stale, triple-index-maintenance]
solution: L1/L2 只加载索引不加载教训内容是 AI 重复犯错的根因。修复：L2 hard-load 增加 ai-operating-handbook.md Part 2（高频错误模式精简段；v9.3 合并自 ai-behavior-redlines.md）；failure-modes.md 索引必须同步 N## 新增；rules §6.4 与 failure-modes.md 不得双重维护。
related_files:
  - .ai-memory/meta/ai-operating-handbook.md
  - .ai-memory/meta/failure-modes.md
  - .trae/skills/gaf-orchestrator/SKILL.md
  - .trae/rules/project_rules.md
created_by: AI
priority: high
n_id: N164
topic: workflow
level: L1
cross_refs: [N126, N128, N134, N160, N161, N162, N163]
diff_keywords: ["l1-l2", "content-load", "repeated-mistakes", "failure-modes"]
---

# N164 — L1/L2 不加载教训内容 → AI 重复犯错

> **级别**: L1 可复用经验（Y/N 检查清单 + 影响 AI 全局行为）
> **分类**: AI 元认知系统 — 记忆加载机制缺陷
> **来源**: 2026-07-14 用户反馈"有些错误能不能在一开始就加载一个详情让 AI 知道。会犯的错误。不然现在有时候犯了你又要反思一下。然后才会发现问题。或者有时候根本就不反思，就发现不了"
> **状态**: ✅ FIXED（P0 修复完成，P1/P2 制定 spec）

## 触发原话

> "有些错误。能不能在一开始就加载一个详情让 AI 知道。会犯的错误。不然现在有时候犯了你又要反思一下。然后才会发现问题。或者有时候根本就不反思，就发现不了"

## 症状

AI 重复犯同类错误：
- N162 写 related_files 猜路径 → N163 又犯（日期错）
- N161 说不推卸决策 → N163 又犯（问用户优先级）
- 这些都是 L1 应该覆盖的，但 L1 只 grep `### N##:` entries，不加载内容

根因审计发现：
1. **L1 机制缺陷**：`gaf_init.sh` 只 grep failure-modes.md 的 N## 计数（≥5），不加载内容。AI 启动时上下文完全没有教训内容。
2. **L2 机制缺陷**：SKILL.md L2 hard-load 4 个文件（loading-strategy + tech-stack + version-compat + docs-index），全是索引/参考文件，不含教训内容。
3. **failure-modes.md 过期**：L1 校验的索引落后 6 条教训（N158-N163 零匹配），但 project_rules.md §6.4 已收录 N160-N163。
4. **三重索引维护**：project_rules.md §6.4 + failure-modes.md + archived-lessons.md 三处维护同一 N## 索引，导致同步漂移。

## 根因分析

AI 记忆系统设计假设：L1 验证索引存在 → L2 加载参考文件 → L3 按需加载教训。

但实际执行中：
- L1 只验证条目数，AI 看不到任何教训内容
- L2 加载的 4 个文件不含教训内容
- L3 按需加载依赖 AI 主动 grep，但 AI 不知道该 grep 什么

结果：AI 启动时处于"零教训"状态，只靠对话中遇到问题时才可能 grep lessons — 如果不反思就发现不了。

## 修复方案

### P0 修复（本轮完成）

1. **创建 ai-behavior-redlines.md**（< 60 行；v9.3 合并入 ai-operating-handbook.md Part 2）
   - 从 N126-N163 提取高频错误模式
   - 每条 Y/N 可判，格式：`❌ 错误模式 → ✅ 正确做法`
   - 6 大类：自治边界 / 诚实标记 / 命令使用 / 反思纪律 / 上下文管理 / 文件命名

2. **L2 hard-load 增加第 5 个文件**（v9.3 瘦身：合并后 L2 从 4 文件减到 1 文件 ai-operating-handbook.md）
   - SKILL.md L2 段从 4 文件改为 5 文件（v9.0）；v9.3 合并为 1 文件
   - 新增 `.ai-memory/meta/ai-operating-handbook.md`（含 Part 2 行为红线）
   - AI 启动时强制 Read，看到具体错误模式

3. **更新 failure-modes.md**
   - 补 N160-N164（5 条缺失）
   - 修过期索引

### P1/P2 待执行（spec 制定）

- **P1**: rules.md 瘦身至 ≤ 400 行（外迁 §6 N## 治理段 + §1.0/1.2 细节 + §4.6-4.10 详细矩阵）
- **P1**: lessons 文件名加 topic 前缀（`testing_2026-07-11-n156-*.md`），AI 不再需要先 Read README 再映射路径
- **P2**: 合并同主题 lessons（N154+N155 / N160+N162 / N161+N163 / N156+N147 / N150+N153）
- **P2**: 拆分 _ai-autonomy-workflow.md 987 行巨型文件

## Y/N 检查清单

- [ ] L2 hard-load 是否包含 ai-operating-handbook.md（Part 2 行为红线）？
- [ ] failure-modes.md 是否同步最新 N##？（新增 lesson 后必同步）
- [ ] rules §6.4 与 failure-modes.md 是否双重维护？（应归一化到 failure-modes.md）
- [ ] 新 lesson 沉淀时是否更新 ai-operating-handbook.md Part 2？（如属高频错误模式）

## 验证

- ai-operating-handbook.md 已创建（v9.3 合并，Part 2 含 6 类 30+ 条红线）
- SKILL.md L2 hard-load v9.3 瘦身为 1 文件
- failure-modes.md 已补 N160-N164
- N164 lesson 文件已创建（本文件）

## 关联

- **N126** (诚实标记) — 红线文件"诚实标记"类来源
- **N128** (3 步验证) — 红线文件"诚实标记"类来源
- **N134** (反思优先) — 红线文件"反思纪律"类来源
- **N160** (上下文预算) — 红线文件"上下文管理"类来源
- **N161/N163** (自决边界) — 红线文件"自治边界"类来源
- **N162** (命令防错) — 红线文件"命令使用"类来源
