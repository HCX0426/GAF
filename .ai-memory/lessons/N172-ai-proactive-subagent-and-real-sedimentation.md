---
date: 2026-07-18
topic: [workflow, ai-autonomy]
priority: high
cross_refs: [N109, N166, N171, N173, N175, §3.6, §3.8, dispatching-parallel-agents]
status: active
created_by: AI
trigger: 用户批评 "ai思维链没子agent吗？真沉淀了？"
symptom: [serial-processing-independent-tds, fake-sedimentation, user-fatigue-from-continue-prompts]
solution: 剩余 ≥2 独立 TD 主动用 Task 工具并行 subagent (search 评估/general_purpose_task 修复); "应该沉淀" = 立即调用工具写文档非口头修辞; 沉淀完成必列文件路径 evidence
diff_keywords: ["project", "rules", "project_rules", "ai", "operating", "handbook", "ai-operating-handbook", "failure", "modes", "failure-modes", "autonomy", "_ai-autonomy"]
related_files:
  - .trae/rules/project_rules.md
  - .ai-memory/meta/ai-operating-handbook.md
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/meta/yn-matrices/archived-yn-matrices/_ai-autonomy.md
  - .trae/skills/dispatching-parallel-agents/SKILL.md
---


# N172-N175 — subagent 并行 + 结果落地家族

> **家族主条目**: 本文件合并 N172 / N175 (同一事件 2026-07-18 subagent 并行, N175 是 N172 修复 A 的下游补充)
> **家族**: workflow + ai-autonomy (与 N109 AI 自决 / N166 持续评估循环 / N171 脚本性能同族)
> **L1 分级**: L1-大 (新 AI 行为反模式 + 跨层影响, 5 层全分发)
> **N## 编号**: N172 / N175 各自在 failure-modes.md §Active 索引 + ai-operating-handbook.md Part 2 红线独立生效, 本家族文件是统一 lesson 载体

## 0. 家族时间线

| N## | 触发场景 | 核心约束 | 用户原话 |
|-----|---------|---------|---------|
| N172 | 选下一个 TD 前 (AI 思维链检查点) | 主动识别并行场景, 用 subagent 并行; 真沉淀 (立即调用工具) | "为什么不用子agent了？这么多小任务，每次都要我继续，很麻烦的" |
| N175 | subagent 并行结果整合时 (主会话 commit 前) | 落地检查清单 — subagent 数 vs active.md 更新数一致, 缺一即结果丢失 | "8 TD 并行" 但 evidence 只见 3 TD |

## 1. 症状 (用户原话)

> "为什么不用子agent了？这么多小任务，每次都要我继续，很麻烦的"
> "ai思维链没子agent吗？真沉淀了？"

## 2. 两个反模式

### 反模式 A — AI 思维链不主动识别"并行任务"场景

**场景**: Spec 16-24 串行处理 9 个 TD (TD-208/225/200/219/141/142/222/143-146/133-135), 每个 TD 都需要用户说"继续"才推进下一个。

**根因**: AI 在思维链中识别到"还有 N 个独立 TD 待处理"时, 没有触发 `dispatching-parallel-agents` skill — 该 skill 触发条件明确写着 "当面对 2 个以上可以独立进行、无共享状态或顺序依赖的任务时使用"。

**思维链缺陷**:
- AI 看到"剩余 33 个 TD"时, 思考的是"选下一个 TD 处理" (串行思维)
- 而不是"哪些 TD 可以并行评估/修复" (并行思维)
- 即使每个 TD 独立 (无共享状态), AI 仍默认串行调用工具

**触发条件 (AI 应识别但未识别)**:
- ✅ 剩余 ≥ 2 个独立 TD (无文件冲突 + 无顺序依赖)
- ✅ TD 评估类任务 (wontfix 判定 / 描述核查) 天然适合并行研究
- ✅ TD 修复类任务如无共享文件 (如 TD-206 改 tracing/tests/ + TD-133 改 api.generated.ts) 可并行

### 反模式 B — 假沉淀 (口头说沉淀, 实际没做)

**场景**: Spec 25 完成后, AI 回复 "这次 subagent 并行处理暴露两个反模式, 应该沉淀到 lessons" — 但实际没有调用任何工具写 lessons/failure-modes.md。

**根因**: AI 在回复末尾把"沉淀"当作"结束语修辞", 而不是"立即执行的动作"。

**违反硬约束**:
- §3.8 "边执行边沉淀" 模式: AI 听到用户反馈后, **执行任务 + 同步沉淀到文档**, 不分先后
- §3.8 ❌ 禁止 "先执行再沉淀" 模式 (任务结束后统一沉淀) — 有遗忘风险
- §3.8 ❌ 禁止用户要求只在当前对话生效

## 3. 修复方案 (本 lesson 即修复)

### 修复 A — 主动用 subagent

**AI 思维链检查点** (每次选下一个 TD 前):
1. 剩余 TD 有 ≥ 2 个独立任务吗? (无文件冲突 + 无顺序依赖)
2. 是 → 用 `Task` 工具并行启动 subagent (search 子类型做评估, general_purpose_task 做修复)
3. 否 → 串行处理

**subagent 分工原则**:
- **评估类 TD** (wontfix 判定 / 描述核查) → `subagent_type: search`, 只研究不改文件
- **修复类 TD** (无共享文件) → `subagent_type: general_purpose_task`, 改文件 + 跑测试
- **主会话职责**: 统一更新 active.md + commit (避免 subagent 并行 commit 冲突)

### 修复 B — 真沉淀

**沉淀动作检查清单** (AI 说"应该沉淀"时立即执行):
1. 调用 `Skill(gaf-lesson-router)` 或直接判定 L1 分级
2. 创建 lesson 文件 (`lessons/<topic>_<date>-<nNNN>-<slug>.md`)
3. 更新 `failure-modes.md` §Active 追加 N## 索引行 (L1-大)
4. 更新 `ai-operating-handbook.md` Part 2 追加行为红线 (L1-大/中)
5. 更新 `project_rules.md` 对应章节 (L1-大/中/小)
6. L1-大 额外: 更新 `yn-matrices/_<topic>.md` + `.ai-memory/summaries/architecture-mistakes.md`

**判定标准** (§3.8): "用户说的这句话, 下次对话 AI 是否需要遵守?" → 是 → 必须沉淀 / 否 → 不沉淀

### 修复 C — 沉淀效率 (避免慢沉淀, 用户反馈 "这个沉淀需要花这么长时间，为啥呢")

**慢沉淀 3 根因 + 优化**:

| 根因 | 反模式 | 优化 |
|------|--------|------|
| ① lesson frontmatter 缺必填字段 | 凭印象写, pre-commit hook `check_lessons_updated` 报错重试 | **frontmatter 模板必填**: date/topic/priority/cross_refs/status/created_by + **symptom/solution/related_files** (后 3 个是 hook 强制校验) |
| ② related_files 路径不存在 | `.trae/skills/superpowers/X` 凭印象写, 实际 `.trae/skills/X` | **路径必 Glob 验证**: 涉及 `.trae/skills/` / `docs/` 子路径时, 先 Glob 确认再写入 related_files |
| ③ 5 层分发多次 Read 找位置 | 4 次 Read 串行找 failure-modes/handbook/yn-matrices/rules 位置 | **沉淀前 1 次 Grep 定位所有目标**: `Grep "^## Retired\|^### ㉙\|^### 沉淀纪律"` 一次性返回所有 Edit 位置, 然后 5 个 Edit 并行 |

**优化后预期**: 5 层分发从 ~20 工具调用 → ~8 工具调用 (Grep 1 + Write lesson 1 + Edit 5 并行 + commit 1), 耗时减半。

## 4. 与现有规则的关系

| 现有规则 | N172 补充 |
|---------|----------|
| §3.6 AI 自决范围 | 补充: AI 自决包括"主动选择执行方式 (串行 vs 并行 subagent)" |
| §3.8 沉淀纪律 | 强化: "边执行边沉淀" = 立即调用工具写文档, 不是口头说 |
| N109 AI 自决 | 补充: 自决能力包括识别并行场景 |
| N166 持续评估循环 | 补充: L3 循环中遇到独立 TD 优先并行 |
| `dispatching-parallel-agents` skill | 强化触发: 不等用户提醒, AI 思维链主动识别 |

## 5. Y/N 检查矩阵

> 详见 `.ai-memory/meta/yn-matrices/archived-yn-matrices/_ai-autonomy.md` §N172 (L1-大 5 层分发)

**核心 Y/N**:
- [ ] 剩余 ≥ 2 个独立 TD 时, AI 是否主动用 subagent 并行处理?
- [ ] AI 说"应该沉淀"时, 是否在同一条回复内调用工具写文档?
- [ ] AI 思维链中是否有"并行识别"检查点 (选下一个 TD 前先评估并行可能性)?

## 6. 验证 evidence (本 lesson 创建过程)

- 本 lesson 文件创建: `workflow_2026-07-18-n172-ai-proactive-subagent-and-real-sedimentation.md`
- failure-modes.md §Active 追加 N172 索引行
- ai-operating-handbook.md Part 2 追加 N172 行为红线
- project_rules.md §3.6/§3.8 追加 N172 强化约束
- yn-matrices/archived-yn-matrices/_ai-autonomy.md §N172 追加 Y/N 矩阵
- **N172 修复 C ② 自检 (2026-07-18 三维评估后补)**: `related_files` 路径已修正 (删除错误的 `superpowers/` 子目录, 实际路径 `.trae/skills/dispatching-parallel-agents/SKILL.md`)
- **N173 用时自检**: N172 首次沉淀 ~20 工具调用 (超基线), 修复 C 后 N173 ~15 调用 (仍超基线), 三维评估后批量修复 P0 ~10 调用 (在基线内)

## 7. 相关文件路径

- `d:\code\GAF\.trae\rules\project_rules.md` §3.6 (AI 自决范围) + §3.8 (沉淀纪律)
- `d:\code\GAF\.ai-memory\meta\ai-operating-handbook.md` Part 2 (AI 行为红线)
- `d:\code\GAF\.ai-memory\meta\failure-modes.md` §Active (N## 索引)
- `d:\code\GAF\.ai-memory\meta\yn-matrices\archived-yn-matrices\_ai-autonomy.md` (Y/N 矩阵)
- `d:\code\GAF\.trae\skills\dispatching-parallel-agents\SKILL.md` (触发条件)

---

# N175 — subagent 并行结果落地检查清单

> **家族**: 并入 N172-N175 subagent 家族 (同一事件 2026-07-18, N175 是 N172 修复 A 的下游补充)
> **L1 分级**: L1-中 (新 AI 行为反模式 + 流程环节, 3 层分发: lesson + rules + handbook)

## 1. 症状 (三维评估发现)

Spec 25 用户称 "3 个 subagent 并行处理 8 个 TD", 但 active.md evidence 只见 3 个 TD 更新 (TD-128/129/130)。其余 5 个 TD 去向不明 — 可能是:
- subagent 返回结果未整合到 active.md
- subagent 实际只处理了 3 个 TD (用户描述与实际不符)
- subagent 返回结果被主会话遗漏

## 2. 根因

N172 修复 A (主动用 subagent) 缺下游检查:
- N172 只规定"主会话统一更新 active.md + commit", 未规定"如何核查 subagent 返回结果是否全部落地"
- 主会话在整合 subagent 结果时, 没有"每个 subagent 必对应 N 个 TD 更新"的检查清单
- subagent 返回结果过长时, 主会话可能漏读部分 TD

## 3. 修复方案

### subagent 并行结果落地检查清单 (主会话 commit 前必跑)

1. **subagent 数 vs TD 数对照**: 记录每个 subagent 处理的 TD 列表, commit 前核查总数
2. **active.md 更新核查**: 每个 subagent 处理的 TD 必须在 active.md 有对应条目更新 (状态变更 + evidence)
3. **结果丢失处理**: 如果 subagent 数 vs active.md 更新数不一致, 必须重新读取 subagent 返回结果 + 补更新
4. **evidence 必含 subagent ID**: active.md 条目 evidence 标注 "via subagent #N"

### 主会话职责强化 (N172 修复 A 补充)

```
主会话 commit 前检查:
  for each subagent in subagents:
    for each td in subagent.td_list:
      assert td in active_md.updates  # 每个 TD 必须有对应更新
      assert td.evidence contains "via subagent #N"
  assert len(active_md.updates) == sum(len(s.td_list) for s in subagents)
```

## 4. Y/N 检查矩阵

| # | 检查项 | Y/N |
|:-:|--------|:---:|
| 1 | 主会话是否记录每个 subagent 处理的 TD 列表? | ☐ |
| 2 | commit 前是否核查 subagent 数 vs active.md 更新数一致? | ☐ |
| 3 | 结果丢失时是否重新读取 subagent 返回结果补更新? | ☐ |
| 4 | active.md evidence 是否标注 "via subagent #N"? | ☐ |
| 5 | subagent 失败时是否回退串行 (重试 1 次 / 串行接管 / 登记 TD)? | ☐ |

## 5. 与现有规则的关系

- N172 修复 A (主动用 subagent): N175 补充下游检查
- N173 spec/plan 用时测量: subagent 并行用时也需测量 + 对照基线
- §3.6 AI 自决范围: subagent 失败回退策略 (未覆盖场景, N175 补充)
