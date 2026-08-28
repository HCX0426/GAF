---
maintainer: manual
source: 用户反馈 "conda gaf 环境没用, 这个问题好多次了"
load_when: [conda-env, python-env, env-not-activated, base-env, system-python, StrEnum, Python-3.11]
priority: high
symptom: [kb:conda-env-not-enforced, N188, L0-missing, env-hardrules]
solution: "L0 硬约束放 .trae/rules/env-hardrules.md (alwaysApply: true); 所有 Python 命令必用 conda run -n gaf"
related_files:
  - .trae/rules/env-hardrules.md
  - .trae/rules/project_rules.md
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/meta/ai-operating-handbook.md
  - docs/reference/cli-cheatsheet.md
  - docs/reference/tech-stack.md
  - .trae/skills/gaf-orchestrator/SKILL.md
  - scripts/gaf_init.sh
created_by: AI
topic: platform-env
last_updated: 2026-07-25
---

# N188 — conda gaf 环境规则多次未生效

## Problem（症状 / 触发条件）

2026-07-25 用户反馈: "为啥 conda 的 gaf 环境没用, 这个问题好多次了, 规则文档没说明还是什么地方没加载?"

这不是第一次出现, 历史上多次发生 AI 直接用 `python` / `python -m pytest` / `python manage.py runserver` 跑代码, 导致:
1. 系统 Python 3.10.11 被使用, 缺 StrEnum (Python 3.11+) 等 3.11+ 特性 → ImportError
2. base 环境被使用, 缺 rapidocr-onnxruntime / opencv 等依赖 → ModuleNotFoundError
3. TRAE 内置 Python 被使用, 路径与依赖都不对

触发条件: AI 在任何任务中执行 Python 命令时, 没有显式用 `conda run -n gaf` 前缀.

根因链 (本次排查发现):
1. **conda 规则散布在 8+ 文件** (project_rules.md §1 / cli-cheatsheet.md §0 / tech-stack.md §7 / ai-operating-handbook.md Part 2 / failure-modes.md / .skills/skills/gaf-orchestrator/SKILL.md / gaf_init.sh / session-context.md), 无单一权威源, 违反 GAF 自己的"单一权威源"原则
2. **规则放置层级错误**: conda 规则只在 L2/L3 层, 缺 L0 系统级硬约束
3. **project_rules.md 无 frontmatter** (没有 `alwaysApply: true`), 所以不作为系统级硬约束加载, 只作为普通项目规则文件被 AI 按需读取
4. **superpowers-zh.md 是唯一有 `alwaysApply: true` 的规则文件, 但完全不提 conda**
5. **failure-modes.md 40+ 条 N## 索引中, 没有任何一条针对"未激活 conda gaf 环境"的失败模式**
6. **.skills/skills/gaf-orchestrator/SKILL.md 把 conda 校验完全委托给 gaf_init.sh, 但 AI 可以跳过脚本直接开始任务** (特别是小修改豁免 gaf_init.sh)
7. **lessons/ 目录没有任何针对"AI 没用 conda gaf 环境"的失败模式记录**, 导致每次违规后没有教训沉淀到 L1, 下次对话 AI 系统 prompt 看不到这条硬约束, **同一错误反复出现**

Trae IDE 规则加载层级 (强制力从高到低):
| 层级 | 机制 | 强制力 |
|---|---|---|
| L0 系统级 | `.trae/rules/*.md` 中标记 `alwaysApply: true` 的文件, 注入每个对话的系统 prompt 顶部 | AI 无法跳过 |
| L1 启动硬加载 | `gaf_init.sh` exit 1 + `failure-modes.md` N## 索引 grep | 脚本拦截 + 索引兜底 |
| L2 任务路由加载 | `gaf-orchestrator` SKILL.md 强制 Read `ai-operating-handbook.md` + `tech-stack.md` | AI 应该读, 但内容是软指导 |
| L3 按需加载 | `sync_ai_memory.py --query` + `cli-cheatsheet.md` | AI 主动查询才加载, 触发不可靠 |

conda 规则原本只在 L2/L3 层, 所以 AI 系统 prompt 看不到, 反复违反.

## Solution（解决步骤）

1. **新建 `.trae/rules/env-hardrules.md`** (40 行, `alwaysApply: true`), 作为 conda gaf 环境规则的 L0 系统级单一权威源
   - 包含: Python 环境硬约束 + 失败模式 + 双环境隔离 + 校验命令
   - 不重复其他文件已有的细节, 只放硬约束语句

2. **在 `.ai-memory/meta/failure-modes.md` Active N## 索引表新增 N188 行** (L1 硬加载兜底)
   - 索引行: `| N188 | conda gaf 环境规则多次未生效 | 所有 Python 命令必用 conda run -n gaf python ...; L0 硬约束在 .trae/rules/env-hardrules.md (alwaysApply: true, 单一权威源); 任务开工必跑 gaf_init.sh; 详见 lesson N188 | lessons/platform-env_2026-07-25-n188-conda-env-not-enforced.md |`

3. **在 `ai-operating-handbook.md` Part 2 "命令使用"段加 conda 环境硬约束红线语句** (L2 加固)
   - 红线: `❌ 用 base 环境 / 系统 Python / TRAE Python 跑 backend/agent 代码 → ✅ 必用 conda run -n gaf 或 conda activate gaf`

4. **在 `project_rules.md §1` 顶部加 L0 硬约束指针** (单一权威源指引)
   - `> **L0 硬约束**: conda gaf 环境规则在 .trae/rules/env-hardrules.md (alwaysApply: true, 单一权威源)`

5. **在 `.skills/skills/gaf-orchestrator/SKILL.md` L2 hard-load hooks 段加 L0 硬约束引用**
   - `L0 硬约束: 所有 Python 命令必须用 conda run -n gaf (详见 .trae/rules/env-hardrules.md, alwaysApply: true)`

**关键设计原则**:
- **不直接给 project_rules.md 加 `alwaysApply: true`**, 因为它 700+ 行会触发系统 prompt 中的 `[always applied workspace rules omitted due to size limit]` 截断, 反而更糟
- **新规则文件必须简短** (< 50 行), 避免 size limit 截断
- **单一权威源**: env-hardrules.md 是 conda 环境规则的唯一硬约束源, 其他文件只引用不重复

## Verification（验证）

```bash
# 1. 验证 env-hardrules.md frontmatter 正确
head -3 d:/code/GAF/.trae/rules/env-hardrules.md
# 预期:
# ---
# alwaysApply: true
# ---

# 2. 验证 N188 索引已加入 failure-modes.md Active 段
grep "^| N188" d:/code/GAF/.ai-memory/meta/failure-modes.md
# 预期: | N188 | conda gaf 环境规则多次未生效 ... | lessons/platform-env_2026-07-25-n188-conda-env-not-enforced.md |

# 3. 验证 L0 硬约束已生效 (在 AI 对话中, 系统 prompt 应显示 env-hardrules.md 内容)
# 这一步通过 AI 在后续对话中"自觉用 conda run -n gaf"来验证

# 4. 验证 L1 硬加载 (gaf_init.sh grep Active 段 N## 数量应增加 1)
bash scripts/gaf_init.sh 2>&1 | grep -i "failure-modes\|N##"
# 预期: N## 数量从原值 +1 (N188 新增)
```

预期: env-hardrules.md frontmatter 正确, N188 索引在 Active 段, AI 后续对话自觉用 conda run -n gaf.

## 反思

**为何"问题好多次了"才沉淀**: 用户多次反馈 conda 环境未生效, 但每次违规后没有 N## 教训沉淀到 L1, 下次对话 AI 系统 prompt 看不到这条硬约束, L2/L3 又是软指导, 自然反复出现. 这暴露了 GAF 教训沉淀机制的盲区: **不是所有"AI 反复违反的规则"都自动有 N## 索引**, 需要主动识别"反复违反"模式并登记 N##.

**根因不是"规则没说明"而是"规则放错了层级"**: 用户原话"规则文档没说明还是什么地方没加载?" — 排查发现规则文档有说明 (8+ 文件都提了), 但都放在 L2/L3 软约束层, 缺 L0 系统级硬约束. 这是规则架构层面的缺陷, 不是规则内容缺失.

**Trae IDE 的 always_applied_workspace_rules 机制**: 通过 `.trae/rules/*.md` + frontmatter `alwaysApply: true` 实现, 注入每个对话的系统 prompt 顶部. 但有 size limit 截断风险, 所以规则文件必须简短 (< 50 行). 这与 GAF 的 L1/L2/L3 加载机制互补:
- L0 (Trae 原生): alwaysApply 注入系统 prompt, AI 无法跳过
- L1 (GAF 自建): gaf_init.sh + failure-modes.md, 启动时硬校验
- L2 (GAF 自建): orchestrator SKILL.md 强制 Read, 任务路由时加载
- L3 (GAF 自建): sync_ai_memory.py --query, 按需加载

**与 N187 的关系**: N187 是 venv gaf-agent 与 conda gaf env 双环境依赖同步问题 (部署层), N188 是 conda gaf 环境激活规则未生效问题 (规则层). 两者都涉及 conda gaf 环境, 但 N187 是依赖清单同步, N188 是规则加载机制. N188 的 L0 硬约束文件 (env-hardrules.md) 顺便引用了 N187 的双环境隔离原则, 形成 conda 环境规则的完整闭环.

**关联反模式**:
- N164 (L1/L2 不加载教训内容 → AI 重复犯错): N188 是 N164 的具体实例, L1/L2 没 conda 失败模式 N##, 导致 AI 重复犯错
- N172 (AI 思维链不主动用 subagent + 假沉淀): 本次排查主动用了 2 个 search subagent 并行验证"新框架扩展性"和"conda 规则加载根因", 避免 N172 反模式
