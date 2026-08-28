---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-21-diagnosis-trigger-governance/
load_when: [evidence, 3-step-evidence, N204, diagnosis-trigger, superpowers-uninstall, lesson-frontmatter]
priority: high
symptom: [kb:evidence, 3-step-evidence, N204, task-failure-auto-diagnosis, superpowers-zh, lesson-fm-broken]
solution: Solution — N204 L0 硬约束 + 技能联动 + superpowers-zh 卸载 + lesson frontmatter 修复 + TD-378 补漏
related_files:
  - .ai-memory/evidence/templates/solution.md
  - .skills/rules/env-hardrules.md
  - .skills/skills/pipeline-task-diagnosis/SKILL.md
  - .skills/skills/gaf-orchestrator/SKILL.md
  - .skills/README.md
created_by: AI
last_updated: 2026-08-21
---
## Solution（解决方案 / 修复动作）

1. N204: `.skills/rules/env-hardrules.md` 新增「诊断触发硬约束 (N204)」段 — 对话出现失败关键词/日志含错误码 (NODE_TIMEOUT/TEMPLATE_NOT_FOUND/OCR_LOW_CONFIDENCE) 时必须调用 `Skill(name='pipeline-task-diagnosis')`; 跳过须记录理由; failure-modes.md 补 N204 索引 + 新增 `lessons/N204-task-failure-auto-diagnosis.md`
2. 技能联动: `pipeline-task-diagnosis/SKILL.md` 新增 load_when front-matter; `gaf-orchestrator` bug_fix 分支 load_skills 顶层加入该技能; `gaf-reflect-and-evolve` §6.3 明确边界; `gaf-knowledge-base` bug_fix.diagnose 加入引用; `.skills/README.md` 分类统计补条目 (Testing & Quality 3→4)
3. superpowers-zh 卸载: 删除 `.skills/rules/superpowers-zh.md` (僵尸 L0); 边界声明迁移至 `.skills/README.md`; 清理全部活跃引用 (gaf-orchestrator 等 `— 见 superpowers-zh` 后缀)
4. lesson frontmatter 修复: 16 个被格式重排破坏的 lesson 去空行/拆分 `topic: <key>---` (N105/N106/N116/N117/N118/N119/N121/N122/N125/N126/N129/N131/N132/N133/N134/N135/N136/N152); 9 个 archived-early legacy 文件补 diff_keywords (TD-378)
5. 退役迁移: N188/N190/N194 lesson 移至 `.ai-memory/_archive/lessons-retired/` (N181 条件 C, L0 已覆盖); failure-modes.md 同步退役索引
