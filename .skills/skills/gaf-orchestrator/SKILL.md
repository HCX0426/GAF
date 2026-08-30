---
name: gaf-orchestrator
description: |
  v9.0 唯一 AI 入口（决策树单一权威源）。所有 AI 任务（fix / add / doc / refactor）必须从这里开始。
  决策树根节点判定 task_type，再加载对应 skill + KB。
  v9.0 强化：L1 启动硬加载 + L2 路由硬加载 + L3 按需加载 + 决策树单一权威源。
  对话起始强制判定（2026-08-27 用户决策）：每次对话先加载本 skill 判定 task_type。
updated: 2026-08-28
---

# gaf-orchestrator — GAF AI 唯一入口

> 变更历史见 `_shared/decision-tree-changelog.md`（v9.0→v9.6 完整记录）。
> **N167**: 七维度评估（代码/规则/skill 文档修改前必跑）— 详见 `gaf-reflect-and-evolve/SKILL.md §7`。
> **AI 入口唯一性**：本 SKILL.md 是 AI 任务**唯一**入口（决策树 + bash wrapper）。
> **强化**：5 skills + 1 rule 强制同步（`sync_skills.py --check`）。

## 对话起始强制判定 (2026-08-27 用户决策强化)

> 用户反馈：AI 在纯检查/问答轮次跳过决策树判定，直接答题。规则原意"任务开始前加载"
> 被解释过窄。用户指令：**每次对话都先加载**。

**协议（任何用户消息到来时）**:
1. 会话第一条用户消息（或新任务开始的任意消息）→ **先**调用 `Skill(name='gaf-orchestrator')`
   判定 task_type（new_feature / bug_fix / documentation / refactor / unknown / meta_audit）
2. 判定后按决策树分支加载对应 skill + KB，再开始响应
3. 纯问答/检查（不写码）也过一遍判定——通常落到 `meta_audit`（默认评估不写码）或 `unknown`（按需 AskUserQuestion 澄清）
4. 例外豁免：用户明确说"只想聊聊/不涉及任务"（闲聊、产品知识）→ 可跳过，但应口头标注跳过理由

## AI 任务开工流程

```bash
# 1. 跑 gaf_init.sh（硬约束入口, 含 L1 加载 + failure-modes 校验; workspace 根执行）
bash scripts/gaf_init.sh
# 1.5 B1 任务恢复: python scripts/step_checkpoint.py list|next <id>|mark <id> <type> <step>
# 2. L2 必加载: Read .ai-memory/meta/ai-operating-handbook.md (见下 L2 hard-load Hooks)
# 3. 读本 SKILL.md 决策树判定 task_type (下面 ## Decision Tree)
```

## §0.5 对话开头 AI patch 流程 (spec-42 — 强制)

> **触发**: 对话开头, 自动修复 doc_health P0/P1 issues. 完整 8 步流程 + 红线见 `ai-operating-handbook.md Part 2` + `scripts/governance/doc_health_patch.py` (PatchPlanner/PatchVerifier). 摘要: 过滤 unconsumed P0/P1 → 按 dimension 批量 patch ≤10 → C1/C2 验证 → mark_consumed; 失败 2 次升级 TD; 连续 ≥3 失败停下报告.

## §4.2 触发点 1 — Evidence 沉淀检查 (spec §4.1)

> **触发**: 会话启动时, 处理历史遗留 `pending_promotion` evidence (同 topic ≥2 提升). 流程: 扫 `evidence/active/` → 同 topic 计数 → 写 lesson + 更新 failure-modes §Active + 移 `archived/YYYY-MM/`; 同会话 ≤5, 完成立即 commit. 与闭环步骤 5 触发点 3 互补.

## Decision Tree

```yaml
root:
  step_1_identify_task_type:
    question: "你的任务属于以下哪一类？"
    options:
      - id: new_feature
        keywords: [add, create, build, implement, 新增, 实现, 添加, 新功能, 开发]
        → load_skills: [gaf-orchestrator, gaf-task-execution, gaf-lesson-router]
        → load_skills_methodology: [test-driven-development]  # 方法论参考
        → load_kb:
            - .ai-memory/meta/auto-kb/api-endpoints.md
            - .ai-memory/meta/auto-kb/pipeline-nodes.md
            - .ai-memory/meta/auto-kb/agent-protocol.md

      - id: bug_fix
        keywords: [fix, debug, error, 修复, 排查, bug, 报错, 不工作, 卡住, 失败]
        → load_skills: [gaf-orchestrator, gaf-reflect-and-evolve, gaf-lesson-router, pipeline-task-diagnosis]
        → load_skills_methodology: [systematic-debugging]  # 方法论参考
        → load_kb:
            - .ai-memory/meta/failure-modes.md
            - .ai-memory/lessons/

      - id: documentation
        keywords: [doc, write, spec, plan, 文档, 写, 改, 重构文档, 整理]
        → load_skills: [gaf-orchestrator, gaf-knowledge-base, gaf-lesson-router]
        → load_skills_methodology: [writing-plans]  # 方法论参考
        → load_kb:
            - docs/
            - .ai-memory/

      - id: refactor
        keywords: [refactor, restructure, architecture, 重构, 改架构, 拆分, 重写]
        → load_skills: [gaf-orchestrator, gaf-task-execution, gaf-reflect-and-evolve, gaf-lesson-router]
        → load_kb:
            - .ai-memory/summaries/architecture-mistakes.md
            - .ai-memory/lessons/

      - id: unknown
        keywords: []
        → load_skills: [gaf-orchestrator]
        → load_kb:
            - .ai-memory/meta/failure-modes.md
        → behavior: "强制人工+AI 协作"
        → hint: "任务类型不明确，用 AskUserQuestion 让用户澄清"

      - id: meta_audit
        keywords: [评估, audit, 复盘, 巡检, 健康度, 梳理, 元评估, meta, 诊断, 改进建议, 自检]
        → load_skills: [gaf-orchestrator, gaf-lesson-router]
        → load_kb:
            - .ai-memory/meta/failure-modes.md
            - .ai-memory/meta/ai-operating-handbook.md
            - .ai-memory/lessons/
        → behavior: "默认仅评估/分析, 不写代码; 发现可立即落地的 [A] 项才落地并报告"
```

### new_feature 分支

```yaml
new_feature:
  step_2_read_context:
    - "读 docs/reference/tech-stack.md（L3 按需: 涉及版本/依赖时）"
    - "L3 按需: 读 docs/reference/version-compat.md（涉及版本/依赖决策时, N137/N144 版本坑）"
  step_3_load_kb:
    - "{task domain: backend} → .ai-memory/meta/auto-kb/api-endpoints.md"
    - "{task domain: frontend} → frontend/src/api/*.ts（直接读源码）"
    - "{task domain: agent} → .ai-memory/meta/auto-kb/agent-protocol.md"
    - "{task domain: pipeline} → .ai-memory/meta/auto-kb/pipeline-nodes.md"
  step_4_check_lessons:
    query: "--query <task domain>:new"
  step_5_implement:
    - "先写后端 API + 测试"
    - "后端按需调用: 调用 Skill(name='test-driven-development') (方法论参考) 写测试 + gaf lessons (架构教训, .ai-memory/lessons/)"
    - "再写前端组件 + e2e"
    - "前端按需调用: 调用 Skill(name='test-driven-development') (方法论参考) 组件测试 + Playwright 库直接用 (规范 E2E/CI, 见 scripts/e2e/)"
    - "最后写 lessons（如有新坑）"
  step_6_verify_before_commit:
    - "调用 Skill(name='verification-before-completion') (方法论参考) 验证完成性"
    - "本地 lint + test + sync 跑通才 commit"
```

### bug_fix 分支

```yaml
bug_fix:
  step_2_read_context:
    - "读 .ai-memory/meta/failure-modes.md（Active N## 失败场景索引, 计数由 sync_ai_memory.py 动态统计, 见 failure-modes.md §状态分档）"
    - "读 .ai-memory/meta/auto-kb/error-codes.md"
  step_3_search_lessons:
    - "提取 symptom 关键词（类别:子类别 格式）"
    - "跑：python GAF/scripts/bootstrap/sync_ai_memory.py --query '<symptom>'"
    - "找到匹配 lesson → 按 solution 步骤执行"
    - "未找到 → 进入 step_4"
  step_4_diagnose:
    - "调用 Skill(name='systematic-debugging') (方法论参考) 获取调试方法论"
    - "{symptom 涉及 pipeline 节点执行/OCR超时/模板匹配失败/坐标偏移} → 调用 Skill(name='pipeline-task-diagnosis') (方法论参考) 获取节点任务诊断方法论"
    - "用 .ai-memory/checklists/data-chain-checklist.md 8 步检查"
    - "用 docs/business/tasks/troubleshooting.md 排查任务执行问题"
    - "用 worker/src/utils/screenshot_diagnostic.py 截图诊断"
  step_5_fix_and_reflect:
    - "调用 Skill(name='test-driven-development') (方法论参考) 先写复现测试"
    - "修复后写 lessons（必填 symptom/solution/related_files）"
    - "写 3 步 evidence（problem/solution/verification）"
    - "{step_4 用了 pipeline-task-diagnosis} → 检查是否发现新诊断模式/新根因，有则更新 ../pipeline-task-diagnosis/SKILL.md（追加到常见错误模式/诊断流程/快速脚本）"
  step_6_verify_before_commit:
    - "调用 Skill(name='verification-before-completion') (方法论参考) 验证完成性"
```

### documentation 分支

```yaml
documentation:
  step_2_read_context:
    - "L2 已加载 ai-operating-handbook.md（含加载策略）"
    - "L3 按需: 读 .ai-memory/meta/docs-index.md（查 docs/ 设计文档时）"
  step_3_route_to_target:
    - "{target: spec} → spec.md（必须修订现有节，不允许新增）"
    - "{target: api} → .ai-memory/meta/auto-kb/api-endpoints.md"
    - "{target: ai-lesson} → .ai-memory/lessons/*.md"
    - "{target: kb} → .ai-memory/**/*.md"
  step_4_write:
    - "调用 Skill(name='writing-plans') (方法论参考) 获取写作方法论"
    - "AI 直接写 + git diff 可查（不阻塞）"
    - "人类 review 时 git diff docs/"
  step_5_sync:
    - "跑 sync_ai_memory.py（auto 文件自动重生成）"
  step_6_verify_before_commit:
    - "调用 Skill(name='verification-before-completion') (方法论参考) 验证完成性"
    - "条件反思 (按规模分级, 与 §4.6 + gaf-reflect-and-evolve §2 对齐):"
    - "  - 小文档改动 (< 50 行 / typo / 段落修订): 跑 ① 4 问 + ④ 状态标记 (轻量反思, 2 项)"
    - "  - 中/大文档变更 (> 50 行 / 跨文档重构 / 新 spec): 调用 Skill(name='gaf-reflect-and-evolve') 跑分级反思 (中=5 项 / 大=24 项+L1 分发)"
```

### refactor 分支

```yaml
refactor:
  step_2_read_context:
    - "读 .ai-memory/summaries/architecture-mistakes.md"
    - "读 .ai-memory/lessons/ 找相关 refactor 教训"
  step_3_assess_impact:
    - "🆕 B2 治本机制: 先跑 python GAF/scripts/check_big_change.py 客观判定是否大修改 (4 维度: diff 行数 / 跨 app 数 / DB 迁移 / API 契约)"
    - "is_big=true → 强制走 N151 5 步流程 (详见 gaf-task-execution §3 step_1 + _ai-autonomy.md §2 ㉕); is_big=false → 正常 refactor"
    - "列出影响范围（哪些模块/接口/数据）"
    - "评估风险：是否需要双写期"
    - "评估收益：行数/复杂度/可测试性"
  step_4_plan:
    - "提交执行计划给用户（NotifyUser）"
    - "🆕 N151+N167 七维度评分自决 (命名归一 = 修改清单): A/B/C 方案产出后, AI 用 §2.0.5 修改清单七维度评分 → 满足自决阈值 → AI 自决执行; 否则 AskUserQuestion 附评分表让用户选 (评分模板见 gaf-reflect-and-evolve/SKILL.md §7, 自决阈值见 §7.3; Y/N 矩阵见 _refactor-dimensions.md)"
    - "用户批准后开始"
  step_5_execute:
    - "按 spec 粒度提交 (§3.4, 默认 1 commit/spec; 复杂任务可分段)"
    - "每个阶段跑测试"
  step_6_verify_before_commit:
    - "调用 Skill(name='verification-before-completion') (方法论参考) 验证完成性"
```

### unknown 兜底

```yaml
unknown:
  step_1b_probe_signals:
    # B4 治本机制: 先跑 probe_unknown_task.py 收集 3 类信号
    # 注意: 编号用 step_1b 避免与 root.step_1_identify_task_type 冲突 (root step_1 已跑过)
    - "跑: python GAF/scripts/probe_unknown_task.py"
    - "按输出 suggested_task_type + roadmap_hints + recent_specs 初判 task_type"
    - "结合对话最近 3 轮用户消息关键词交叉验证"
  step_2_read_context_and_query:
    - "读 .ai-memory/meta/failure-modes.md (L1 已加载, 此处仅按需 grep 主题)"
    - "读 .ai-memory/lessons/README.md 找相似 topic"
    - "L3 必跑: python GAF/scripts/bootstrap/sync_ai_memory.py --query '<symptom keywords>'"
  step_3_clarify_or_route:
    - "若 step_1b + step_2 能判定 task_type → 路由到具体分支 (new_feature/bug_fix/documentation/refactor), 从该分支 step_2 开始"
    - "若仍无法判定 → 用 AskUserQuestion 问用户 (规则未覆盖歧义场景)"
    - "用户回答后 → 路由到具体分支, 从该分支 step_2 开始 (不重启 root.step_1)"
    - "把判定结果加入 lessons/README.md (topic 分类索引)"
  step_4_verify_before_commit:
    - "调用 Skill(name='verification-before-completion') (方法论参考) 验证完成性"
  step_5_reflect_and_sediment:
    - "若发现新反模式 → 写 lesson (按 §6.2 L1 子分级分发)"
    - "若 user 澄清过程反复出现 → 沉淀到 gaf-orchestrator/SKILL.md unknown 分支"
```

### meta_audit 分支

```yaml
meta_audit:
  step_2_read_context:
    - "读 .ai-memory/meta/failure-modes.md (Active 失败场景索引)"
    - "读 .ai-memory/meta/ai-operating-handbook.md (L1/L2/L3 机制 + 行为红线)"
    - "读 .ai-memory/lessons/ (相关教训)"
  step_3_scan:
    - "按任务要求扫描目标维度 (文档/代码/架构/界面/功能/业务/数据/多 app/集成)"
    - "产出 [A] 立即修复 / [B] 登记 TD / [C] wontfix 三类分级"
  step_4_decide:
    - "默认仅评估并报告, 不写代码"
    - "发现可立即落地且无风险的 [A] 项 → 落地并报告 (commit 遵守 N208: commit message 不写规则编号)"
    - "需设计的治理/架构改动 → 登记 TD 到 docs/archive/active-tech-debt.md ([B]), 不擅自大改"
  step_5_verify_before_commit:
    - "调用 Skill(name='verification-before-completion') 验证 (仅当本轮回落了代码)"
```

## End Decision Tree

## §4.10 Spec 分阶段 + 跨会话续接 (TD-137 修复 — 2026-07-18)

> **单一权威源**: `project_rules.md §4.10` — 复杂修复 (>1500 行 diff / 跨模块 / 多缺陷 / 架构修复) 必须拆 multi-phase spec (带阶段状态表); 新对话续接从第一个 ⏳ 阶段开始. 此处仅指针, 规则以 project_rules §4.10 为准.

## L2 hard-load Hooks (决策树 step_1.5 强制段 — v9.5 扩展为 2 文件)

> **位置说明**: 本段在 `## End Decision Tree` 之后, 是决策树 step_1 → step_2 之间的强制加载段。不放决策树块内 (避免污染 `sync_skills.py` 的 Decision Tree hash)。

AI 收到任务后, 在路由到具体 task_type 分支**之前**,
**必须先 Read 以下 2 个 .ai-memory/ 文件**, 不允许跳过。

L0 系统级硬约束 (Trae Layer 1 / opencode instructions 注入, alwaysApply: true, 注入每个对话系统 prompt 顶部, AI 无法跳过):
- ../../rules/env-hardrules.md (conda gaf 环境 L0 单一权威源, N188, 2026-07-25 新增)

L2 必读 (v9.5 扩展, 2026-07-21 spec-65):
- .ai-memory/meta/ai-operating-handbook.md (L1/L2/L3 机制 + AI 行为红线)
- docs/reference/tech-stack.md (4 栈版本 + 开发环境速查: pytest/pre-commit/gaf_init/工作流/关键路径)

> **v9.5 升级理由**: 用户反馈 "ai 每次都要找技术环境" → tech-stack.md 从 L3 按需升级为 L2 硬加载, AI 不用 Glob 探索 pyproject.toml / .pre-commit-config.yaml / package.json

L3 按需 (v9.3 降级, v9.5 tech-stack 移出):
- .ai-memory/meta/docs-index.md (查 docs/ 设计文档时)
- docs/reference/version-compat.md (涉及版本升级/依赖变更/TS 严格选项时)
- docs/reference/cli-cheatsheet.md (CLI 命令速查)
- docs/reference/data-flow.md (跨层数据流问题)

**违反** = 视为未加载 L2, 反思矩阵中 [L2] 必标 N, N96 触发。

L3 按需加载: 任务进入具体分支后, AI 必须按 task_type
跑对应的 `sync_ai_memory.py --query` 强匹配, 找不到再写新 lesson。

**情境硬约束 (env-hardrules-contextual.md) 触发加载**: 当 task_type ∈ {fix, new_feature, refactor, documentation} 或对话出现失败关键词 (失败/超时/报错/卡住/error/timeout) / pipeline 错误码 (NODE_TIMEOUT/TEMPLATE_NOT_FOUND/OCR_LOW_CONFIDENCE) 时, 必须先 `Read .ai-memory/meta/env-hardrules-contextual.md` 对应段 (段名见该文件 `##` 标题 / env-hardrules.md 文末索引表), 跑完其检查清单再 commit。该文件承载已从 L0 迁出的情境硬约束 (N191/N192/N193/N196/N204 活跃 + N194/N197/N198/N199 退役), 不常驻系统提示以守住注入预算。

## §3.2 反思清单

> **单一权威源**: `gaf-reflect-and-evolve/SKILL.md §2` — commit 后按规模分级反思 (小/中/大), 含 ①-⑤ 框架 + ⑥-㉔ Y/N 矩阵. 触发: project_rules §4.6.

---

## task_type → skill 映射

> 权威源为上方 Decision Tree (load_skills/load_kb), 本表仅用于 tools 快速核验, 修改 skill/KB 列表必须改决策树.

| task_type | 必加载 skills |
|-----------|--------------|
| new_feature / bug_fix / documentation / refactor / unknown / meta_audit | 见 Decision Tree 各分支 load_skills (orchestrator + 子 skill + methodology) |

## 闭环步骤（v9.3 简化, v9.6 加文档同步检查）

1. **开工**：跑 bash 流程 (gaf_init + L2 + 决策树判定)
2. **判定**：按决策树根节点判定 task_type
3. **加载**：按 task_type 加载对应 skill + KB
4. **搜索 (L3 硬约束)**：`python scripts/bootstrap/sync_ai_memory.py --query "<symptom>"` — 中大修改必跑; §9.4/§9.5 stale 检查见同步机制 (docs-index 比对 code_last_changed vs doc_last_updated)
5. **执行**：写代码 + 3 步 evidence + lessons（如新坑）; 触发点 3 沉淀 = 写完 evidence 后扫同 topic ≥2 → 主动沉淀
6. **提交**：按 project_rules §3.4 spec 粒度自决 commit; §9.2 文档同步检查 (commit 前扫描 diff 反查 docs-index, 需更新则 AskUserQuestion, 拒绝标记 drift)

> **L3 --query 落地 (2026-07-18)**: step_4 硬约束 (中大修改必跑). **v9.6 (2026-07-26) 文档同步闭环**: §9.2/9.4/9.5 由 check_doc_code_sync.py R8 强制 sync_status.

## 关键依赖

- **session active**：`.trash/.gaf_session_active` 24h TTL（跨平台 binding）
- **v9.0 单一权威源**：决策树只保留在 gaf-orchestrator SKILL.md, 其他子 skill 引用（sync_skills.py --check 验证）
- **失败兜底**：failure-modes.md 索引表 (Active + dormant, 计数由 sync_ai_memory.py 动态统计)
