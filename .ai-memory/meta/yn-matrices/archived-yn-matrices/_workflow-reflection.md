---
maintainer: derived-manual
source: Split from yn-matrices/_workflow.md (Phase 4 拆分优化 2026-07-26)
generated: 2026-07-26
auto_updated: 2026-07-26
last_manual_edit: 2026-07-26
load_when: [反思, 沉淀, 教训, 工具纪律, bug排查, 上下文预算]
priority: medium
symptom: [workflow-reflection, reflection-trigger, lesson-collect]
solution: 反思分级触发 + 沉淀纪律 + L1/L2 教训加载 + 工具使用纪律 + bug 排查三维根因 Y/N 矩阵; 详见各家族段
related_files:
  - .skills/skills/gaf-reflect-and-evolve/SKILL.md
  - .ai-memory/meta/ai-operating-handbook.md
---

# _workflow-reflection.md — 反思/工具纪律/bug 排查 Y/N 矩阵

> 原 `_workflow.md` (697 行) 按 N## 家族拆分为 3 sub-file。本文件主题: 反思分级触发 + 沉淀纪律 + L1/L2 教训加载 + 工具使用纪律 (上下文预算/命令防错) + bug 排查链路归一化/三维根因/节点观测性/测试盲区。姊妹文件: [_workflow-commit.md](_workflow-commit.md) (commit/hook/skill 治理) | [_workflow-spec.md](_workflow-spec.md) (spec/plan/阶段/前端/技术债)

### ㉘ 循环迭代反思分级触发 Y/N 矩阵 (§4.6)

> **单一权威源**: `gaf-reflect-and-evolve/SKILL.md §2` (分级触发标准 + ①-㉔ 反思清单)
> 本节仅保留 Y/N 检查项

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 修改规模已判定（小/中/大） | | 自检 diff 行数 |
| 2 | 按规模跑了对应必跑项（小=2项/中=5项/大=24项, 见 gaf-reflect-and-evolve §2） | | 自检 |
| 3 | 中/大修改 commit 后跑了反思（N134） | | 自检 |
| 4 | 问题分类落地（A/B/C） | | 自检 |
| 5 | 小修改未走全套反思 | | 自检 |

### ㉞ N166 沉淀纪律 Y/N 矩阵 (§3.8)

> **来源**: 用户反馈 "上面所有对话的，我的要求咋都没主动沉淀到文档里？"

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | 用户对话中的工作模式要求已沉淀到 project_rules.md | | `git diff .trae/rules/project_rules.md` |
| 2 | 用户对话中的反模式已沉淀到 failure-modes.md N## + lessons/ | | `git log --oneline .ai-memory/lessons/` |
| 3 | L1 教训按 §6.2 子分级分发 (L1-小→2层/L1-中→3层/L1-大→5层含新 N##), 未过度分发 | | 自检 |
| 4 | 沉淀后跑 sync_ai_memory.py 验证索引一致 | | `python scripts/bootstrap/sync_ai_memory.py --check` |
| 5 | 沉淀后跑 sync_skills.py --check 验证 5 skills+1 rule 同步 | | `python scripts/bootstrap/sync_skills.py --check` |

**AI 必做**:
- ✅ **判定标准** (只问 1 个问题): "用户说的这句话, 下次对话 AI 是否需要遵守?" → 是 → 必须沉淀 / 否 → 不沉淀
- ✅ **当轮任务结束前完成沉淀**: 不等用户提醒, 不留到下次对话
- ❌ **禁止** 用户要求只在当前对话生效
- ❌ **禁止** 沉淀时只写 lessons 不更新 rules (L1 教训必须按 §6.2 子分级分发, L1-小不创建 lesson/N##/Y/N 矩阵)

> **交叉引用**: N173 spec/plan 用时测量 + AI 自决沉淀 (L1-大 5 层分发) 详见 [_workflow-spec.md](_workflow-spec.md) §㉙

### ㉟ N164 L1/L2 不加载教训内容 Y/N 矩阵 (AI 元认知系统)

> **来源**: 用户反馈 — "有些错误能不能在一开始就加载一个详情让 AI 知道。会犯的错误。不然现在有时候犯了你又要反思一下。然后才会发现问题。或者有时候根本就不反思，就发现不了"
> **触发条件**: AI 重复犯同类错误（如 N162→N163 路径猜测/日期错）且 L1/L2 加载机制不包含教训内容
> **Lesson**: `lessons/N164-l1-l2-no-content-load-repeated-mistakes.md`

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | L2 hard-load 包含 `ai-operating-handbook.md`（Part 2 行为红线 + L1/L2/L3 加载策略） | | `grep "ai-operating-handbook" .trae/skills/gaf-orchestrator/SKILL.md` |
| 2 | failure-modes.md 索引同步最新 N##（新增 lesson 后必同步，无落后条目） | | `grep -c "^\| N[0-9]" .ai-memory/meta/failure-modes.md` 与 lessons/ 文件数比对 |
| 3 | rules §6.4 与 failure-modes.md 不双重维护 N## 索引（v9.1 归一化到 failure-modes.md） | | `grep "N[0-9]\{3\}" .trae/rules/project_rules.md` 应无 N## 索引表 |
| 4 | 新 lesson 沉淀时同步更新 ai-operating-handbook.md Part 2（如属高频错误模式） | | 自检：新 N## 是否触发 Part 2 红线追加 |
| 5 | L3 按需加载通过 `sync_ai_memory.py --query <keyword>` 跑通（非靠 AI 凭印象 grep） | | `python scripts/bootstrap/sync_ai_memory.py --query <kw>` |

**AI 必做**:
- ✅ 启动时 L2 hard-load ai-operating-handbook.md（看到具体红线，非仅索引）
- ✅ 新增 L1 lesson 后立即同步 failure-modes.md 索引 + Part 2 红线（如适用）
- ✅ N## 索引只在 failure-modes.md 维护（rules §6.4 只引用，不重复）
- ❌ NEVER L2 只加载索引/参考文件（tech-stack/docs-index/version-compat），无教训内容
- ❌ NEVER 新增 lesson 后忘记同步 failure-modes.md（导致索引落后）
- ❌ NEVER project_rules.md 与 failure-modes.md 双重维护 N## 索引

**同根因家族**: N126 (诚实标记) + N128 (3 步验证) + N134 (反思优先) + N160 (上下文预算) + N161/N163 (自决边界) + N162 (命令防错) — 同根因（L1/L2 不加载内容 → AI 重复犯错）

## §7 工具使用纪律 (上下文预算管理 + 命令防错反思)

### ㊲ N160/N162 工具使用纪律 Y/N 矩阵 (上下文预算管理 + 命令防错反思)

> **来源**: 用户反馈 2026-07-14 — "对话咋莫名其妙断了，又要新开" + "为什么不多分配子agent呢" + "AI 用错命令要反思根因, 是否有更好替代, 下次怎么防错" + "spec 范围外的架构问题, 在 spec 中也要关注"
> **TD-316 修复 (2026-07-21)**: failure-modes.md §Dormant L148 原引用 `_command-errors.md N160 段` 是断链 (_command-errors.md 不存在); 现统一沉淀到本段 (workflow topic, 因 N160/N162 工具使用纪律属工作流约束); failure-modes.md L148 引用已改为本段
> **触发条件** (任意一条即触发):
> - AI 跑 pytest/长输出命令未加 `-q`/`--oneline`/`head_limit`
> - E2E 调试逐次试错 (改 1 selector 重跑 1 次, 而非诊断脚本一次性 dump)
> - 大文件 (>100 行) 整文件 Read 未用 `offset`+`limit`
> - AI 用错命令但只当场改对, 未反思根因/替代/防错
> - 标 spec/阶段 ✅ 但未跑全量回归或 E2E 验证
> - spec 执行中发现范围外问题但未登记到"范围外关注"段
> - 对话轮次 ≥ 15 但未提示新开对话或未用 N159 子 agent 分发
> **Lesson**: `lessons/N160-n162-context-budget-command-reflection.md`

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | pytest 命令用 `-q --tb=short` 非 `-v` (避免全量测试名+PASSED 进上下文) | | 自检最近 pytest 命令 |
| 2 | git log 用 `--oneline -N` (N ≤ 10); Grep 用 `head_limit`; 长输出用 `Select-Object -First N` | | 自检最近 git/grep 命令 |
| 3 | E2E 调试 ≤ 2 轮 (首次失败写诊断脚本一次性 dump DOM+bbox+元素计数, 非逐次试错) | | 自检最近 Playwright 调试轮数 |
| 4 | 大文件 (>100 行) Read 用 `offset`+`limit` 参数, 禁止整文件 Read | | 自检最近 Read 调用 |
| 5 | 对话轮次 ≥ 15 → 主动提示新开对话 OR 用 N159 子 agent 分发独立子任务 | | 自检当前对话轮次 |
| 6 | 独立子任务分发子 agent (N159), 主 agent 只做协调+commit+验证 | | 自检是否有可并行任务未分发 |
| 7 | 用错命令后必反思 4 项: 根因/替代方案/防错机制/同类扫描 | | 自检最近命令错误是否已反思沉淀 |
| 8 | spec 执行中发现范围外问题 → 立即追加到"范围外关注"段 + 登记 TD | | `grep "范围外关注" docs/specs/legacy-trae/<spec>.md` |
| 9 | 标阶段 ✅ 前跑 3 项验证: 单元测试 + 全量回归 + E2E (有前端改动) | | 自检最近阶段 ✅ 前验证 |
| 10 | 标"全部完成"时同时报告范围外问题 + 未完成验证 (N126 诚实标记) | | 自检最近 spec 完成报告 |

**AI 必做 (N160/N162 闭环)**:
- ✅ pytest `-q --tb=short`; git log `--oneline -N`; Grep `head_limit`; 长 PowerShell 输出 `Select-Object -First N`
- ✅ E2E 失败首次写诊断脚本一次性 dump DOM + bbox + 元素计数
- ✅ 大文件用 offset+limit (除非 < 100 行)
- ✅ 长任务 (≥ 15 轮 / 跨模块) 主动用 N159 子 agent 分发
- ✅ 命令用错 → 反思 4 项 → 沉淀到 lesson 或 rules
- ✅ spec 含"范围外关注"段, 标 ✅ 前同时报告范围外问题
- ❌ 禁止 pytest -v (全量测试名 + PASSED 进上下文, ~2000 token 浪费)
- ❌ 禁止 E2E 逐次试错 (改 1 selector 重跑 1 次, 每轮 5000+ token)
- ❌ 禁止整文件 Read > 100 行 (用 offset+limit 精确读取)
- ❌ 禁止标 ✅ 但未跑全量回归或 E2E
- ❌ 禁止只修 spec 清单就标"全部完成"不提范围外发现

**同根因家族**: N134 (反思优先) + N126 (诚实标记) + N128 (3 步验证) + N151 (大修改架构视角) + N156 (E2E 先测试后理解) + N159 (长任务分子 agent) + **N160/N162 (本条 工具使用纪律)** — 同根因 (工具使用纪律缺位 + 上下文预算管理缺位)

## §8 bug 排查与根因评估

### N91 Hook ID 失败映射表（来源: gaf-reflect-and-evolve/SKILL.md §4）

> **触发**：pre-commit hook 跑失败，输出含 `[FAIL]` 行。
> **2026-07-18 优化 (N171)**: 10 个 governance hook → 1 个 `gaf-governance-batch` (subprocess→import, 71s→4s, 18x speedup); 2 个 post-commit hook → 1 个 `gaf-post-commit-batch` (2.37s→0.3s, 87% reduction); batch 脚本内部用 importlib 直接调 main(), 失败时 print `[FAIL] <sub-check-name>` + 上下文
> **跨引用**: N150 (pre-commit 失败根因修复) 详见 [_workflow-commit.md](_workflow-commit.md) §7 hook-failure

**排查流程**: 看 pre-commit 输出找 `[FAIL]` 行 → 查下表 → 跑修复命令 → 重试 → 仍失败升级 N## → 分发 (N95)

**Hook ID 映射表 (5 hook, batch 内含 12 sub-check)**:

| Hook ID / Sub-check | 失败原因 | 修复命令 | 验证 |
|---------|----------|----------|------|
| `gaf-governance-batch` (pre-commit 主 hook) | 10 个 sub-check 之一失败 | 看输出 `[FAIL] <sub-check>` 行定位 | batch 重跑 exit 0 |
| ↳ sub: `session active` | session 缺失 / 过期 / binding 不匹配 | `python scripts/bootstrap/check_session_active.py --create` | exit 0 + binding_hash 输出 |
| ↳ sub: `sync_ai_memory` | `.ai-memory/auto` 文件未重生成 | `python scripts/bootstrap/sync_ai_memory.py` | exit 0 + index 条数 |
| ↳ sub: `3-step evidence` | evidence 缺 heading 或字符 | 按 `## 症状/触发/步骤/原因/方法/标准` 6 模板补 | `check_3step_evidence` exit 0 |
| ↳ sub: `lessons front-matter` | lesson 缺 front matter 字段 | 补 `id / symptom / solution / related_files / created_by` | `check_lessons_updated` exit 0 |
| ↳ sub: `spec/tasks/checklist` | spec ↔ tasks ↔ checklist 编号漂移 | 同步 spec/tasks.md + pending-roadmap.md 状态 | `check_spec_consistency` exit 0 |
| ↳ sub: `5 skills + 1 rule` | 4 份 SKILL.md 决策树副本 hash 不一致 | `python scripts/bootstrap/sync_skills.py` | `sync_skills --check` exit 0 |
| ↳ sub: `promote lessons` | 提议提升 lessons 到 4 目标 (rules/SKILL/arch/failure-modes) | `python scripts/lessons/promote_lessons.py --apply` | exit 0 |
| ↳ sub: `docs/ index` | docs-index.md 过期 / 缺 frontmatter | `python scripts/bootstrap/sync_docs_index.py` | `sync_docs_index --check` exit 0 |
| ↳ sub: `path consistency` | inline 拼路径违反 N106 | 改用模块级常量 (e.g. `SYNC_STATE`) | `check_path_consistency` exit 0 |
| ↳ sub: `Y/N matrices index` | yn-matrices.md 索引与 sub-file drift | 同步索引表 "包含 N##" 列与 sub-file ### heading | `check_yn_matrices_index` exit 0 |
| `gaf-git-status-check` (pre-commit) | hook 改动文件未 staged (MM/MD/AM/AD 状态) | 手动 add + commit hook 改动的文件 | exit 0 |
| `gaf-post-commit-batch` (post-commit 主 hook) | 2 个 sub-check 之一有 warning (不阻塞) | 看输出 `[WARN] <sub-check>` 行定位 | always exit 0 (advisory) |
| ↳ sub: `N134 reflection` | post-commit, N134 evidence 缺失 (不阻塞) | 写 3-step evidence + A/B/C 分类 | 下次 commit 看 warning 消失 |
| ↳ sub: `P4 checklist` | post-commit, P4 反思清单 (不阻塞) | 按提示 Read 对应 yn-matrices sub-file | 下次 commit 看 warning 消失 |
| `gaf-skip-rate` (pre-push) | 滚动 30 commit bypass 率 > 30% | 减少 `--no-verify` 使用 | bypass 率 < 30% |
| `gaf-audit-scripts` (manual) | 90 天未修改 + 无 README 引用的脚本 | 季度审计手动触发, informational only | exit 0 (不阻塞) |
| `eslint` (manual) | 前端代码 lint 错 | `npx eslint --fix` 或改代码 | exit 0 |
| `prettier` (manual) | 前端代码格式错 | `npx prettier --write` | exit 0 |
| `ruff` (manual) | 后端 Python lint 错 | `ruff check --fix` 或改代码 | exit 0 |
| `mypy` (manual) | 后端类型错 | 改类型注解或 `# type: ignore` | exit 0 |

**4 lint hook 已改 manual stage**: eslint/prettier/ruff/mypy 标 `stages: [manual]`, 本地 `git commit` 不跑; 手动跑 `pre-commit run --hook-stage manual`; 详细 `docs/architecture/cross-cutting/pre-commit-stages.md`

**Batch hook 调试**:
- `python scripts/hooks/gaf_governance_batch.py` — 10 sub-check PASS/FAIL + 耗时
- `python scripts/hooks/gaf_post_commit_batch.py` — 2 sub-check OK/WARN + 耗时

### N182 — bug 排查链路归一化评估

| # | 检查项 | Y/N |
|:-:|--------|:---:|
| 1 | bug 排查动手前是否评估 fail 节点上下游归一化? | ☐ |
| 2 | fail 节点是否是同根因家族的唯一例外? | ☐ |
| 3 | 链路归一化评估是否在写测试前? | ☐ |
| 4 | 上下游节点契约是否文档化? | ☐ |
| 5 | 同链路其他节点是否同步检查? | ☐ |

### N183 — bug 修复三维根因评估

| # | 检查项 | Y/N |
|:-:|--------|:---:|
| 1 | TD 条目三维根因字段是否填全 (代码层+工作流层+规则层)? | ☐ |
| 2 | 代码层根因是否覆盖同根因家族? | ☐ |
| 3 | 工作流层根因是否归因到测试覆盖/e2e 时机/隐式契约? | ☐ |
| 4 | 规则层根因是否归因到规则盲区? | ☐ |
| 5 | 三维根因是否在 commit 前评估而非事后补? | ☐ |

### N184 — 节点观测性硬约束

| # | 检查项 | Y/N |
|:-:|--------|:---:|
| 1 | fail_result 是否带 logger.warning + exc_info? | ☐ |
| 2 | 错误消息是否包含上下游上下文 (输入参数+上游状态+失败原因)? | ☐ |
| 3 | except Exception 是否都有 logger.warning (禁止 pass)? | ☐ |
| 4 | fail 路径是否禁止 return None 不抛错? | ☐ |
| 5 | 节点观测性是否在 code review 检查清单? | ☐ |

### N185 — 测试覆盖盲区 = AI 思维链缺陷

| # | 检查项 | Y/N |
|:-:|--------|:---:|
| 1 | 测试覆盖盲区是否归因到 AI 思维链层? | ☐ |
| 2 | 同类关键方法是否同步补单测? | ☐ |
| 3 | testing-conventions 是否覆盖 agent 节点层? | ☐ |
| 4 | 节点关键方法是否有非 happy path 单测? | ☐ |
| 5 | 测试覆盖盲区反思是否在写测试前而非后? | ☐ |
