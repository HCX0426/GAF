---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-20-governance-evaluation/
load_when: [evidence, 3-step-evidence, governance, TD-369, TD-370, TD-374, TD-375, TD-379]
priority: high
symptom: [kb:evidence, 3-step-evidence, governance-evaluation, injection-bloat, dead-skill]
solution: Solution — Phase 1 修复 5 项 P1 TD: TD-375 11 skill 移出 / TD-374 10 lesson + 84 evidence 归档 / TD-370 gaf_init 修复 / TD-379 R9R10 归档 / TD-369 注入瘦身 47% + 预算约束
related_files:
  - .ai-memory/evidence/templates/solution.md
  - docs/specs/archived/2026-08/2026-08-20-governance-evaluation-fixes.md
  - docs/archive/fixed-tech-debt.md
  - .skills/rules/project_rules.md
  - .skills/rules/env-hardrules.md
created_by: AI
last_updated: 2026-08-20
---
## Solution（解决方案 / 修复动作）

1. TD-375: 11 个 0 引用 skill Move-Item 到 `.skills/_archive/skills/`; `.skills/README.md` (17 合计) + `superpowers-zh.md` (15 skills) 重写; junction 生效 available_skills 剩 15
   - 2026-08-21 追加：`.skills/_archive/skills/` 整个目录删除（git 可追溯）；systematic-debugging 的 CREATION-LOG.md + test-academic/test-pressure-1/2/3.md 历史验证记录删除；README.md 移除 `_archive` 结构与归档恢复规则
2. TD-374: 10 个 Retired lesson → `.ai-memory/_archive/lessons-retired/`; 29 个 session 目录 84 文件 → `evidence/archived/2026-08/`; failure-modes.md 6 链接改指 `../_archive/lessons-retired/` (archived, TD-374); N202 related_files 同步
3. TD-370: `scripts/gaf_init.sh` line200 根因修复 (awk `exit NR` 退出码=NR 触发 `|| echo 0` 追加第二行 → `exit` 无参); 支持 `--check-env` (conda+UTF-8 校验 exit 0); session active 文档统一 `.trash/.gaf_session_active`
4. TD-379: check_thinking_trace/check_reflection_evidence 实测从未接入 commit 链 → 归档 `scripts/_archive/hooks/`; session-traces/README.md 加退役声明
5. TD-369: opencode.json instructions 移除 README.md; project_rules 71.4KB→27.8KB/211 行 (节号全保留); env-hardrules 根因段压缩 34.7→32.2KB; 合计 114.6→60.5KB (-47%); 注入预算 ≤62KB 硬约束入 env-hardrules
6. 配套: check_doc_code_sync R4 归档白名单补 `.ai-memory/_archive/` / `.skills/_archive/` / `scripts/_archive/`; E2E cross_repo 措辞同步 (不可逆数据删除); evidence/active 空壳目录清理