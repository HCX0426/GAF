---
date: 2026-06-17
symptom:
- pre-commit
- hook-failed
- ai-behavior-undefined
- retry-loop
solution: '14 hook ID → 修复命令映射表 + 6 步排查流程 + 重试 ≤ 2 次; M3.B: B2 大修改 3 门槛预处置 (evidence + spec-context + B2 --acknowledge) + GAF_SKIP_DOC_SYNC=1 env var'
diff_keywords: ["skill", "pre-commit"]
related_files:
- .trae/skills/gaf-reflect-and-evolve/SKILL.md
- .ai-memory/meta/failure-modes.md
- scripts/e2e/run_all.py
- scripts/hooks/check_doc_code_sync.py
- scripts/check_big_change.py
- docs/archive/spec-context/
created_by: AI
priority: high
level: L1
n_id: N91
topic: hook-failure
---


# N91: pre-commit hook 失败（AI 行为未定义）

## Symptom

pre-commit, hook-failed, ai-behavior-undefined, retry-loop

## Solution

**触发条件**
- AI 提交代码 → pre-commit hook 拒绝 commit
- AI 不确定下一步该做什么

**检测**
- pre-commit 退出码非 0
- hook 输出含 `❌` 但无明确"下一步"

**兜底（3 步内）**
1. **看 hook 输出找 `❌` 行**（pre-commit 输出按 hook ID 分段）
2. **根据 hook ID 跑对应修复命令**（见下方映射表）
3. **重新跑 `git gaf-commit`**

**Hook ID → 修复命令映射**

| Hook ID | 失败时跑什么 |
|---------|--------------|
| gaf-session-check | `bash GAF/scripts/gaf_init.sh` |
| gaf-sync | 跑通即可（无需操作） |
| gaf-3step-evidence | 补 evidence 文件 3 步模板 |
| gaf-lessons-updated | 补 front matter 必填字段 |
| gaf-spec-consistency | 跑 `python check_spec_consistency.py --fix` |
| gaf-decision-tree-sync | 跑 `python sync_decision_tree.py` |

**M2.B 闭环补充 (N91, 2026-06-17)**
- 上方"修复命令映射表"仅覆盖 7 hook, M2.B 扩到 14 hook (新增 eslint / prettier / ruff / mypy / gaf-docs-index / gaf-path-consistency-check / gaf-git-status-check)
- 14 hook → 修复命令 + 验证命令映射见 `.trae/skills/gaf-reflect-and-evolve/SKILL.md §1 触发场景` + `scripts/e2e/run_all.py` 的 n91 验证场景
- 测试: `scripts/tests/test_e2e_run_all.py` 故意构造 hook 失败 → 跑对应修复命令 → 验证成功 (10 用例)
- 配套脚本: `一次性脚本 (已删除)` (binary-safe append)
- 反模式家族: N82 + N100 + N101 + N105 + N106 + N110 + N114 + N116 + N117 + N118 + **N91 (本条 Hook 失败 AI 行为未定义)**

## M3.B 补充 (2026-08-16, spec-2026-08-15-governance-redundancy-consolidation)

**教训 1: B2 大修改 3 门槛预处置 (evidence 三件套 + spec-context + B2 --acknowledge) 需在 commit 前统一准备, 而非 hook 报错后逐个救火**

- 症状: B2 大修改 commit 时连续踩 3 个 hook (gaf-b2-evidence TTL 过期 → gaf-evidence-completeness 缺三件套 → gaf-spec-context 缺承载体), 每个 hook 失败后补一个文件再重跑
- 根因: B2 evidence TTL 仅 30 min, 工作会话中途生成会过期; evidence 三件套 + spec-context 承载体是 B2 大修改的 3 个前置门槛, 分散在 3 个 hook 中
- 修复: B2 大修改 commit 前统一准备 3 项 → ① `python scripts/check_big_change.py --staged --acknowledge` (TTL 30 min, 紧邻 commit 跑) ② evidence 三件套 (problem/solution/verification) ③ `docs/archive/spec-context/<spec>-context.md` (用户决策原文 + N151 + N167 + 实施决策 + N173 字段)
- 关联: project_rules §6.5 (spec-context 硬约束) / §2.0.4 (N151) / §2.0.5 (N167)

**教训 2: `GAF_SKIP_DOC_SYNC=1` env var 是 doc-code-sync R4 skip 的唯一可靠途径 (commit message `[skip-doc-sync]` token 对 `-m` 无效)**

- 症状: commit message 含 `[skip-doc-sync]` 但 hook 仍失败
- 根因: `check_doc_code_sync.py` 读 `.git/COMMIT_EDITMSG` 检测 token, 但 `git commit -m` 不填充 COMMIT_EDITMSG (hook 运行时为空)
- 修复: `$env:GAF_SKIP_DOC_SYNC="1"; git commit -m "..."` (env var 方案在脚本 L196-204 文档化, 是 `-m` 场景的推荐替代)
- 纪律: skip 前必须 grep 验证 deleted/modified 文件无 live 引用残留 (evidence/archived/specs 为历史记录不改); skip 会记录到 `.cache/doc_sync_skips.json`, N167 反思阶段强制确认

## Related files

- `.trae/skills/gaf-reflect-and-evolve/SKILL.md`
- `.ai-memory/meta/failure-modes.md`
- `scripts/e2e/run_all.py`
