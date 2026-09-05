# GAF Skills 统一索引

> 所有 skills 的统一索引。涵盖 GAF 项目专属 skills (gaf-*) 和通用方法论 skills (superpowers)。
> 边界规则见本文件「边界规则」节；GAF 执行宪法见 `rules/project_rules.md`。

## 接入说明（多 IDE 兼容，v9.4）

`.skills/` 是技能/规则/维护脚本的**唯一权威源**，各 IDE 目录通过 junction 指向这里，物理上只有一份文件：

```
项目根
├── .skills/                  # 唯一权威源（本目录，进 git）
│   ├── skills/               15 个技能（每个技能一个子目录，含 SKILL.md）
│   ├── rules/                规则层（env-hardrules / project_rules）
│   └── README.md             本索引（opencode 始终注入）
├── .trae/                    skills|rules → junction → .skills/（Trae 自动扫描）
├── .opencode/                skills|rules → junction → .skills/（opencode 自动扫描）
└── .workbuddy/               skills → 真实副本（WorkBuddy 自动扫描；junction 受阻，仅 cp -r 同步）
```

| 入口 | 技能发现方式 | 规则加载方式 |
|------|------------|------------|
| `.trae/` | Trae 自动扫描 `.trae/skills/`（junction） | `.trae/rules/` junction，Layer 1 始终加载 |
| `.opencode/` | opencode 自动扫描 `.opencode/skills/`（junction） | `opencode.json` `instructions` 注入 `rules/env-hardrules.md` + `rules/project_rules.md`（始终加载） |
| `.workbuddy/` | WorkBuddy 自动扫描 `.workbuddy/skills/`（真实副本，非 junction） | `.workbuddy/memory/` 派生副本（规则仍以 `.skills/rules/` 为权威源） |

路径铁律：文档内部一律使用相对路径（如 `../../rules/project_rules.md`），禁止带 IDE 目录名（`.trae/`、`.opencode/`）或绝对路径。junction 后三兄弟目录（`skills/` `rules/`）同级，从任一入口进入相对路径都能解析。

新增 IDE 目录：`New-Item -ItemType Junction -Path <IDE目录>\skills -Target .skills\skills`（rules 同理）。

## 统计

| 类别 | 数量 | 说明 |
|------|------|------|
| GAF Core | 5 | GAF 项目专属流程，强制走 gaf-orchestrator 入口 |
| Development Workflow | 2 | 计划编写与并行调度 |
| Testing & Quality | 4 | TDD、调试、验证、节点诊断 |
| Documentation | 2 | 中文文档与审查（显式 /command 触发） |
| Git & CI | 2 | 中文 commit 规范、国内 Git 平台（显式 /command 触发） |
| Review & Audit | 1 | GAF 架构评审 runbook（WorkBuddy 层真实副本，显式触发） |
| External Tools | 1 | 内置全局 playwright-best-practices（Trae 提供） |
| Web & UI | 2 | 内置全局 web-dev / skills-overview（Trae 提供） |
| 合计 | 19 | 15 个位于 `.skills/skills/`，3 个为 Trae 内置全局，1 个为 WorkBuddy 层副本 |

> 2026-08-20 治理评估（TD-375）：11 个 0 引用 skill（brainstorming / executing-plans / finishing-a-development-branch / subagent-driven-development / using-git-worktrees / using-superpowers / requesting-code-review / receiving-code-review / mcp-builder / workflow-runner / writing-skills）移出，git 历史可追溯。原因：边界规则"必须先走 gaf-orchestrator" + 决策树白名单只 load gaf-* + 6 方法论，这些 skill 永远无法被加载，但 description 常驻系统提示浪费 token。
>
> 2026-09-05：新增 `gaf-architecture-review`（架构与代码评审 runbook），落在 `.workbuddy/skills/`（WorkBuddy IDE 层真实副本，非 `.skills/skills/` 权威源）——评审属用户显式触发的元任务，不走 gaf-orchestrator 决策树，故不入权威源白名单。

## GAF Core (5)

GAF 项目专属流程 skills。所有 AI 任务必须先走 `gaf-orchestrator` 决策树，不得直接调用其他 skill。

| Skill | 触发条件 | 路径 |
|-------|---------|------|
| gaf-orchestrator | v9.0 唯一 AI 入口（决策树单一权威源）。所有 AI 任务（fix/add/doc/refactor）必须从这里开始 | `.skills/skills/gaf-orchestrator/SKILL.md` |
| gaf-task-execution | AI 接到 new_feature / refactor 任务时加载 | `.skills/skills/gaf-task-execution/SKILL.md` |
| gaf-reflect-and-evolve | AI 接到 bug_fix / refactor 任务时加载；commit 后必跑反思 | `.skills/skills/gaf-reflect-and-evolve/SKILL.md` |
| gaf-knowledge-base | AI 任务中需要查 KB（.ai-memory/ + docs/）时加载 | `.skills/skills/gaf-knowledge-base/SKILL.md` |
| gaf-lesson-router | gaf-orchestrator 需要教训加载或任务结束反思时调用 | `.skills/skills/gaf-lesson-router/SKILL.md` |

## Development Workflow (2)

| Skill | 触发条件 | 路径 |
|-------|---------|------|
| writing-plans | 有规格说明或需求用于多步骤任务时使用，在动手写代码之前 | `.skills/skills/writing-plans/SKILL.md` |
| dispatching-parallel-agents | 面对 2 个以上可以独立进行、无共享状态或顺序依赖的任务时使用 | `.skills/skills/dispatching-parallel-agents/SKILL.md` |

## Testing & Quality (4)

| Skill | 触发条件 | 路径 |
|-------|---------|------|
| test-driven-development | 在实现任何功能或修复 bug 时使用，在编写实现代码之前 | `.skills/skills/test-driven-development/SKILL.md` |
| systematic-debugging | 遇到任何 bug、测试失败或异常行为时使用，在提出修复方案之前执行 | `.skills/skills/systematic-debugging/SKILL.md` |
| verification-before-completion | 在宣称工作完成、已修复或测试通过之前使用，必须运行验证命令并确认输出 | `.skills/skills/verification-before-completion/SKILL.md` |
| pipeline-task-diagnosis | pipeline 节点执行失败/超时/异常时使用（OCR/超时/坐标/截图问题）；N204 硬约束：任务失败时必调 | `.skills/skills/pipeline-task-diagnosis/SKILL.md` |

## Documentation (2)

| Skill | 触发条件 | 路径 |
|-------|---------|------|
| chinese-documentation | 中文文档排版参考。仅在用户显式 /chinese-documentation 时调用 | `.skills/skills/chinese-documentation/SKILL.md` |
| chinese-code-review | 中文 review 沟通参考。仅在用户显式 /chinese-code-review 时调用 | `.skills/skills/chinese-code-review/SKILL.md` |

## Git & CI (2)

| Skill | 触发条件 | 路径 |
|-------|---------|------|
| chinese-commit-conventions | 中文 commit 与 changelog 配置参考。仅在用户显式 /chinese-commit-conventions 时调用 | `.skills/skills/chinese-commit-conventions/SKILL.md` |
| chinese-git-workflow | 国内 Git 平台配置参考。仅在用户显式 /chinese-git-workflow 时调用 | `.skills/skills/chinese-git-workflow/SKILL.md` |

## Review & Audit (1)

| Skill | 触发条件 | 路径 |
|-------|---------|------|
| gaf-architecture-review | 用户要求对 GAF 做评审/体检/架构梳理/上线前检查，或询问"项目还有什么问题"时使用。含实测验证命令、健康基线（2026-09-05 修复后刷新）与已知误报清单 | `.workbuddy/skills/gaf-architecture-review/SKILL.md`（WorkBuddy 层） |

## External Tools (1)

| Skill | 触发条件 | 路径 |
|-------|---------|------|
| playwright-best-practices | 编写 Playwright 测试、修复 flaky tests、调试失败、POM、CI/CD 配置等场景 | 内置全局（Trae 提供，opencode 无） |

## Web & UI (2)

| Skill | 触发条件 | 路径 |
|-------|---------|------|
| web-dev | 用户显式要求从零构建新网站/网页/Web 应用/Web 游戏时使用 | 内置全局（Trae 提供，opencode 无） |
| skills-overview | 用户需要了解项目中所有技能或寻找特定功能的技能时使用 | 内置全局（Trae 提供，opencode 无） |

## 边界规则

1. **gaf-* 优先**：所有 AI 任务必须先走 `gaf-orchestrator` 决策树，不得直接调用其他 skill
2. **superpowers 作为方法论参考**：在 gaf-orchestrator 决策树中按需引用（白名单: test-driven-development / systematic-debugging / writing-plans / verification-before-completion / pipeline-task-diagnosis / dispatching-parallel-agents），不能作为 AI 任务入口
3. **引用约定**：gaf-* SKILL.md 引用 superpowers 方法论 skill 时统一格式 `调用 Skill(name='<skill-name>') (方法论参考)`，由 gaf-orchestrator 决策树各分支调用（见 `skills/gaf-orchestrator/SKILL.md`）
4. **内置全局 skills**：web-dev / skills-overview / playwright-best-practices 由 Trae IDE 提供，不在项目 `.skills/skills/` 目录中
5. **评审类元任务**：gaf-architecture-review 由用户显式触发（评审/体检），不经 gaf-orchestrator 决策树；评审全程只读，唯一产出为 `docs/analysis/` 报告文件。若未来需要跨 IDE 共享，先迁入 `.skills/skills/` 权威源再向各层派生