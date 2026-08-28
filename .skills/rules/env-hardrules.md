---
alwaysApply: true
---

# GAF 环境硬约束（L0 系统级 — AI 必须每次对话遵守）

> **单一权威源**：仅承载每次对话任何操作都适用的真全局约束（N188/N190/N207/N208 + N192/N204 常驻提醒）。
> **注入预算 (TD-369/v9.2)**：本文件 ≤ 4KB + project_rules.md ≤ 14KB，超限由 governance hook 阻塞。
> **情境硬约束**（N191/N193/N196 等）正文在 `.ai-memory/meta/env-hardrules-contextual.md`，命中触发条件时按需 Read（见文末索引），不常驻 L0。

## Python 环境 (N188)

1. 所有 Python 命令必须 `conda run -n gaf python ...`（或先 `conda activate gaf`）
2. 环境名固定 `gaf`；Python 必须 3.11.15（系统 3.10 不可用）
3. 大/中修改开工前跑 `bash scripts/gaf_init.sh`
4. 多行 `python -c` 禁止 → 写临时 .py 再执行

## Shell 命令 (PowerShell) (N190)

1. 禁止 bash heredoc `<<'EOF'`；禁止 `&&` / `||` 链式 → 用 `;` 分隔（不短路，链前先 `git status --short` 验证）
2. commit message 只用 `-m`（多行 = 多个 `-m` flag）；禁止 `-F <file>`
3. 禁止 Unix 命令 head/tail/find/grep/cat/sed/awk → 用 PowerShell 等价或 Grep/Glob 工具
4. `gaf_init.ps1` 必须用 `pwsh`（PowerShell 7+）调用；`powershell` 5.1 因文件头 `#requires -Version 7.0` 失败，改用 `pwsh -NoProfile -File scripts/gaf_init.ps1`

## Git 回退前检查 (N207)

任何 stash/reset/checkout ./restore ./clean -f/branch -D/pull --rebase 前：
1. 必跑 `git status` + `git diff --stat` 评估修改价值
2. 有价值修改先 `git stash push -m "WIP: <描述>"` 或 commit
3. pre-commit 失败先看原因修复重试，不盲目 stash；代码丢失必跑 `git reflog`

## Commit message 纪律 (N208)

1. 用自然语言描述改动；仅在 diff 真有证据时才可写 N##（该 commit 确实改了对应规则文件且含 diff_keywords）
2. 行为/合规类已由 BEHAVIORAL_N 豁免，但纪律上仍避免写编号

## L0 常驻提醒

- **N192 双调试视角**：fix/add/refactor 完成前必跑双 7 项复查，跳过须记录理由。清单见 contextual §N192。
- **N204 诊断触发**：出现失败关键词（失败/超时/报错/卡住/error/timeout）或 pipeline 错误码（NODE_TIMEOUT/TEMPLATE_NOT_FOUND/OCR_LOW_CONFIDENCE）时，必须 `Skill(name='pipeline-task-diagnosis')`，跳过须记录理由。

## 情境硬约束索引（按需 Read contextual）

| N## | 触发条件 |
|-----|---------|
| N191 | schema 重构 / 字段重命名 / 数据契约跨端修改 |
| N192 (常驻) | fix/add/refactor 完成前 |
| N193 | spec 驱动任务 / 发现新问题 / 测试修复后 |
| N196 | 写测试 / 大文件大数据量 / 真实网络请求 |
| N204 (常驻) | 失败关键词 / pipeline 错误码 |

> 加载纪律：AI 进入 fix/new_feature/refactor/documentation 任务或命中上表触发条件时，必须先 `Read .ai-memory/meta/env-hardrules-contextual.md` 对应段，跑完检查清单再 commit。
