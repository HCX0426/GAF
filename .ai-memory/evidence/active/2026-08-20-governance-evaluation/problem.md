---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-20-governance-evaluation/
load_when: [evidence, 3-step-evidence, governance, TD-369, TD-370, TD-374, TD-375, TD-379]
priority: high
symptom: [kb:evidence, 3-step-evidence, governance-evaluation, injection-bloat, dead-skill]
solution: Problem — 治理体系评估发现 12 项 TD: 注入层 114.6KB/对话 (README 重复注入), gaf_init 算术 bug + --check-env 缺失, 11 个死 skill 常驻, 10 个 Retired lesson + 84 evidence 未归档, R9/R10 思维链 hook 摆设
related_files:
  - .ai-memory/evidence/templates/problem.md
  - docs/specs/archived/2026-08/2026-08-20-governance-evaluation-fixes.md
  - docs/archive/active-tech-debt.md
  - scripts/gaf_init.sh
created_by: AI
last_updated: 2026-08-20
---
## Problem（症状 / 触发条件）

1. 现象: 每对话固定注入 114.6KB 规则 (README 8.5 + env-hardrules 34.7 + project_rules 71.4KB), 60-80K tokens; gaf_init --check-env 报 Unknown arg, line 200 算术语法错误; 26 个 skill 中 11 个 0 引用常驻 available_skills
2. 触发条件: 任何新对话打开 (注入固定开销); 运行 `bash scripts/gaf_init.sh --check-env` (文档写了参数但脚本不支持)
3. 影响范围: 全 AI 任务 (注入信噪比); .ai-memory 膨胀 558KB; commit 链 15s; gaf-init L1 硬加载每轮报错