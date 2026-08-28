---
n_id: N171
date: 2026-07-18
topic: workflow
title: 时间测量纪律 — 脚本 + spec/plan 用时测量 (N171-N173 家族)
priority: high
level: L1-大
cross_refs: [N111, N134, N160, N172, N173]
status: active
symptom:
  - "git commit 耗时 71s (11 个 pre-commit hook × 5-6s venv 激活开销)"
  - "AI 每次 commit 看到 Passed 就认为没问题, 从未测量总耗时"
  - "用户问 '为啥之前没看出这些问题呢' 时才发现"
  - "spec/plan 完成后不算用时, AI 等用户提醒才沉淀 (N173 合并)"
solution: "所有脚本执行必加 Measure-Command; 输出时对照性能基线 (单 hook < 1s / commit < 5s); 异常则分析瓶颈 + 优化; batch 脚本优先 import 而非 subprocess; 每个 spec/plan 完成后必测用时 (start_ts/end_ts) 对照规模基线, 超基线跑根因 6 项检查"
diff_keywords: ["project", "rules", "project_rules", "ai", "operating", "handbook", "ai-operating-handbook", "gaf", "governance", "batch", "gaf_governance_batch", "pre"]
related_files:
  - .trae/rules/project_rules.md
  - .ai-memory/meta/ai-operating-handbook.md
  - scripts/hooks/gaf_governance_batch.py
  - .pre-commit-config.yaml
created_by: AI
---


# N171-N173 — 时间测量纪律家族

> **家族主条目**: 本文件合并 N171 / N173 (同一主题"时间测量纪律", N171 覆盖脚本, N173 覆盖 spec/plan 整体用时)
> **家族**: workflow (与 N172 主动并行+真沉淀 / N134 反思纪律同族)
> **L1 分级**: L1-大 (新 AI 行为规则 + 跨层影响, 5 层全分发)
> **N## 编号**: N171 / N173 各自在 failure-modes.md §Active 索引 + ai-operating-handbook.md Part 2 红线独立生效, 本家族文件是统一 lesson 载体

## 0. 家族时间线

| N## | 触发场景 | 核心约束 | 用户原话 |
|-----|---------|---------|---------|
| N171 | 所有脚本执行时 | 脚本必加 Measure-Command, 对照基线 (单 hook < 1s / commit < 5s); batch 优先 import | "5秒都算很久了吧" / "为啥之前没看出这些问题呢" |
| N173 | 每个 spec/plan 完成后 | 必测用时 (start_ts/end_ts) 对照规模基线; 超基线跑根因 6 项检查; AI 自决沉淀 | "之后我需要你每个计划或者spec算用时, 不是合适的时间就找原因" |

## 症状

- `git commit` 耗时 71s（11 个 pre-commit hook × ~6s venv 激活开销）
- AI 每次 commit 看到一长串 `Passed` 就认为没问题，从未主动测量总耗时
- 用户问 "为啥之前没看出这些问题呢" 时才发现问题存在数月
- 用户标准："5秒都算很久了吧"

## 根因

**AI 反模式**：只验证功能正确性（Passed/Failed），从不验证性能。

深层原因：
1. **pre-commit 框架开销隐性化**：每个 `language: python` hook 都创建独立 managed virtualenv，激活开销 ~5-6s，但 pre-commit 输出只显示 Passed，不显示耗时
2. **AI 倾向于看到 Passed 就过**：没有主动测量耗时的意识
3. **性能问题不阻塞功能**：commit 最终成功，只是慢，不触发任何错误

## 影响

- 每次 commit 浪费 ~65s（71s - 6s 实际工作）
- 假设每天 20 次 commit = 21 分钟/天浪费
- 长期影响 AI 工作效率 + 用户等待体验

## 修复方案

### 短期（已实施）

1. **合并 10 个 governance hook 为 1 个 batch hook**（commit `-`）
   - 新建 `scripts/hooks/gaf_governance_batch.py`：1 个 Python 进程内跑 10 个 sub-check
   - 保留 `gaf-git-status-check` 独立（必须最后跑）
   - commit 耗时：71s → 6.25s（12x speedup）

### 长期（规则沉淀 — N171）

1. **所有脚本执行必加时间测量**
   ```powershell
   $t = Measure-Command { conda run -n gaf python <script> 2>&1 | Out-Null }
   Write-Host ("{0,-40} {1,6:N2}s" -f <name>, $t.TotalSeconds)
   ```

2. **性能基线**（GAF 项目）
   - 单个 hook/check 脚本: < 0.5s (理想) / < 1s (可接受) / > 2s (需优化)
   - `git commit` 总耗时: < 3s (理想) / < 5s (可接受) / > 5s (需优化)
   - pytest 单文件: < 5s / 全套: < 30s
   - sync_ai_memory.py: < 1s / sync_skills.py: < 0.5s

3. **输出时检查耗时**
   - 脚本单次 > 1s → 分析瓶颈
   - commit 流程 > 3s → 评估优化方案
   - 测试套件 > 10s → 评估并行化/拆分

4. **batch 脚本优先用 `import` 而非 `subprocess`**
   - 避免每次 subprocess 启动 Python ~0.3-0.5s
   - 优先 `from <module> import main; main()` 直接调用

5. **框架开销 >> 实际工作 → 必须重构**
   - 如 pre-commit venv 激活 5s 但脚本只跑 0.1s
   - 合并 hooks / 换 `language: system` / 内联 import

## 验证

- ✅ `git commit --allow-empty` 实测：6.25s（3 次稳定）
- ✅ batch 脚本独立测试：10/10 passed in 14.45s → 3.10s（预热后）
- ✅ N171 规则已沉淀到 `project_rules.md §5.6` + `ai-operating-handbook.md`

## 反模式

- ❌ 只看 exit code 不看耗时
- ❌ 看到 Passed 就认为没问题
- ❌ 框架开销 >> 实际工作但不重构
- ❌ batch 脚本用 subprocess 调 N 个子脚本（应 import）
- ❌ 性能问题数月不发现（AI 应主动测量）

## 同根因家族

- N111（命令超时主动中止）— 关注命令卡死，N171 关注命令慢但不卡死
- N134（反思纪律）— N171 是反思纪律的性能维度
- N160（上下文预算管理）— N171 是命令耗时维度
- 同根因：AI 只验证功能正确性，不验证性能/资源消耗

---

# N173 — spec/plan 用时测量 + 慢沉淀根因分析

> **家族**: 并入 N171-N173 时间测量家族 (同一主题 2026-07-18, N173 是 N171 在 spec/plan 层面的扩展)
> **L1 分级**: L1-大 (新 AI 行为规则 + 跨层影响, 5 层全分发)

## 1. 症状 (用户原话)

> "之后我需要你每个计划或者spec算用时，不是合适的时间就找原因"
> "这需要我告诉你要沉淀才会沉淀？还是你自己会判断？"

## 2. 两个反模式

### 反模式 A — spec/plan 完成后不算用时

**场景**: Spec 16-25 完成后, AI 只报告 commit hash + 测试通过数, 不测 spec 整体耗时。Spec 25 用 subagent 并行处理 8 个 TD, 但 AI 没测量"并行比串行快多少", 也无法回答用户"这个沉淀需要花这么长时间, 为啥呢"。

**根因**: N171 只覆盖脚本性能 (Measure-Command), 不覆盖 spec/plan 整体用时。AI 没有"spec 计时"概念。

### 反模式 B — AI 等用户提醒才沉淀

**场景**: 用户问 "真沉淀了？" 后 AI 才开始真沉淀; 用户问 "这个沉淀需要花这么长时间, 为啥呢" 后 AI 才分析慢的根因。

**根因**: AI 没有内化 §3.8 "边执行边沉淀" 硬约束 — 把"沉淀"当作"用户要求才执行的动作", 而不是"AI 自决的常规动作"。

## 3. 修复方案

### 修复 A — spec/plan 用时测量

**硬约束** (每个 spec/plan 完成后必跑):
1. spec 开始时记录 `start_ts` (spec 内第一个工具调用前)
2. spec 完成后记录 `end_ts` (commit 成功后)
3. 计算 `duration = end_ts - start_ts`
4. 对照 spec 规模基线 (见下表)
5. 超基线 → 必找根因 + 沉淀优化 (不等下次)

**spec 规模基线** (GAF 项目):

| spec 规模 | diff 行数 | 工具调用数 | 预期耗时 | 超基线触发根因分析 |
|---|---|---|---|---|
| 小 (typo/1-3 行/配置) | < 10 | < 10 | < 5 min | > 10 min |
| 中 (加 API/组件/修 bug) | 10-500 | 10-50 | < 15 min | > 30 min |
| 大 (跨模块/架构/新功能) | > 500 | 50-200 | < 60 min | > 120 min |
| 沉淀 (L1-大 5 层) | < 100 | < 15 | < 5 min | > 10 min |

**测量方法**:
- 主会话: 在 todo 完成时记录时间戳 (可用 `RunCommand date` 或工具调用间隔估算)
- subagent: subagent 返回结果中必含耗时 (subagent 内部已支持)

**根因分析检查清单** (超基线时跑):
1. 串行调用工具? (应并行未并行 → N172)
2. pre-commit 失败重试? (凭印象写路径/字段 → N172 修复 C)
3. 凭印象写路径导致 Glob/Read 失败? (→ N172 修复 C ②)
4. 串行 Read 找 Edit 位置? (应 1 次 Grep 定位 → N172 修复 C ③)
5. 复杂任务未拆分 spec? (→ §4.10 Spec 分阶段)
6. 上下文压缩导致重复 Read? (→ N160 上下文预算)

### 修复 B — AI 自决沉淀 (强化 §3.8 + N172 修复 B)

**硬约束**:
- ✅ AI 自决沉淀, 不等用户提醒 (§3.8 + N172 修复 B)
- ✅ 判定标准 (问 1 个问题): "用户说的这句话, 下次对话 AI 是否需要遵守?" → 是 → 立即沉淀 / 否 → 不沉淀
- ❌ 禁止等用户说 "这需要沉淀" / "真沉淀了？" 才开始沉淀
- ❌ 禁止把 "应该沉淀" 当结束语修辞 (N172 修复 B)

**用户原话 "这需要我告诉你要沉淀才会沉淀？还是你自己会判断？" 的答案**:
- **AI 自己判断** — 按 §3.8 + N172 修复 B 判定标准
- 用户不需要说 "这个要沉淀" / "沉淀一下"
- AI 听到用户反馈后, 自决判定是否需要沉淀 + 立即调用工具执行

## 4. 与现有规则的关系

| 现有规则 | N173 补充 |
|---|---|
| N171 脚本性能测量 | 补充: N171 覆盖脚本, N173 覆盖 spec/plan 整体用时 |
| N172 修复 B 真沉淀 | 强化: AI 自决沉淀, 不等用户提醒 |
| N172 修复 C 沉淀效率 | 补充: spec 用时测量是"沉淀效率"的延伸 (超基线 → 根因分析 → 优化) |
| §4.9 阶段验收 | 补充: 阶段验收含"用时是否在基线内" |
| §4.10 Spec 分阶段 | 补充: 单 spec 超 1500 行 diff 或超 120 min → 必拆分 |

## 5. Y/N 检查矩阵

> 详见 `.ai-memory/meta/yn-matrices/archived-yn-matrices/_workflow-spec.md` §N173 (L1-大 5 层分发)

**核心 Y/N**:
- [ ] spec/plan 完成后是否记录 start_ts/end_ts + duration?
- [ ] duration 是否对照 spec 规模基线?
- [ ] 超基线是否跑根因分析检查清单 (6 项)?
- [ ] AI 是否自决沉淀 (不等用户提醒)?
- [ ] 沉淀是否在同一回复内调用工具 (N172 修复 B)?
