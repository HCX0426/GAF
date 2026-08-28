---
date: 2026-07-08
symptom: [n150, pre-commit, stale-hook-path, no-verify-overuse, pre-existing-errors, hidden-tech-debt, root-cause, overall-framework, workflow, stash, windows, git-commit, file-loss]
solution: 'pre-commit 治理家族合并 (N150+N153)。(1) pre-commit 失败必须根因修复 (language: system→language: python 避免 Windows Store stub; hook 路径过期→reinstall; 脚本 bug→fix; 数据漂移→makemigrations); --no-verify 仅限 N105 gaf-commit.sh 透传 bug; 预存错误当场修或登记 TD; 从整体框架看同类问题。(2) commit 前 git add 所有变更不留未暂存文件; 有不想 commit 的先 git stash; 跨文件依赖场景用 git add -A 单次 commit 避免 pre-commit stash 丢失。'
diff_keywords: [pre-commit, no-verify, stash, stale-hook, hook-path]
related_files:
  - .git/hooks/pre-commit
  - .pre-commit-config.yaml
  - scripts/hooks/check_spec_consistency.py
  - scripts/hooks/check_lessons_updated.py
  - scripts/hooks/check_3step_evidence.py
  - scripts/hooks/check_git_status_after_hook.py
  - .trae/rules/project_rules.md
  - docs/archive/tech-debt-README.md
created_by: AI
priority: high
l2_candidate: true
merged_n_ids: [N150, N153]
level: L1
n_id: N150
topic: command-errors
---

# N150 + N153 — pre-commit 治理：根因修复 + stash 丢失防护

## 家族合并说明

本文件合并 N150（pre-commit hook 路径过期 + --no-verify 滥用隐藏 10+ 预存错误）和 N153（pre-commit stash 丢失未暂存变更）。两者同属"pre-commit 治理"根因家族：
- **N150** 关注**hook 失败根因修复**：hook 路径过期 / language: system Windows Store stub 拦截 / --no-verify 滥用隐藏预存错误
- **N153** 关注**stash 丢失防护**：commit 前未 git add 所有变更 → pre-commit stash push --keep-index → Windows 文件锁导致 stash pop 失败 → 变更丢失

合并后形成完整的"pre-commit 治理"检查清单：从 hook 失败根因修复到 stash 丢失防护。

---

## N150: pre-commit hook 路径过期 + --no-verify 滥用隐藏 10+ 预存错误

> **登记时间**：2026-07-08
> **发现于**：TD-039 AuditLog 迁移 commit 时 "pre-commit not found"
> **触发原话**：用户 "未找到 pre-commit咋会呢，还有预存错误或者开发中的其他问题，都要记录进去，或者当时就解决，不要留着，修改时要从整体框架看下去，不可只以最小修改来弄"
> **跨引用**：N105 (gaf-commit.sh 透传 bug — --no-verify 的原始适用范围)、N91 (hook 失败映射)、N126 (文档诚实标记)、N128 (3 步验证)

### 1. 症状 (Symptom)

`git commit` 报 "pre-commit not found" / hook 找不到 python。AI 按 N105 教训用 `--no-verify` 绕过继续 commit。

用户质疑 "未找到 pre-commit咋会呢"，要求调查根因。调查发现：

1. **hook 路径过期**：`.git/hooks/pre-commit` 内 `INSTALL_PYTHON='C:\Users\hcx\miniconda3\envs\gaf\python.exe'` — conda env 已迁到 `D:\code\environment\conda\envs\gaf\python.exe`
2. **language: system + Windows Store python stub**：reinstall hooks 后前 4 个 hook 通过，但 hook 5-10 (gaf-spec-consistency 到 gaf-git-status-check) 仍失败，exit code 9009。根因：`language: system` hooks 用 PATH 中的 `python`，而 Windows PATH 中 `C:\Users\hcx\AppData\Local\Microsoft\WindowsApps\python.exe` (Store stub) 拦截了 `python` 命令 — stub 不执行 Python，返回 9009 ("command not found")
3. **--no-verify 滥用**：N105 原本只针对 `gaf-commit.sh` 透传 bug，但被 AI 泛化为"任何 pre-commit 失败都绕过"
4. **10+ hooks 形同虚设**：`gaf-3step-evidence` / `gaf-lessons-updated` / `gaf-spec-consistency` 等 GAF 知识系统 hooks 全部静默跳过
5. **4 类预存错误被隐藏**：
   - TD-063: hook INSTALL_PYTHON 路径过期 + language: system PATH 漂移
   - TD-064: settings/monitors migration drift (help_text/verbose_name 漂移)
   - TD-066: `check_spec_consistency.py` 路径 bug (`root.parent / ".trae"` 应为 `root / ".trae"`)
   - TD-067: 11 个 lesson 文件 front-matter 缺字段 / related_files 路径失效

### 2. 根因 (Root Cause)

#### 直接根因
1. **conda env 迁移后 hook 未重装**：`pre-commit install` 生成的 hook 脚本把 python 路径写死，env 移动后不会自动更新
2. **`language: system` 依赖系统 PATH**：即使 reinstall 修正了 `INSTALL_PYTHON`，`language: system` hooks 的 `entry: python scripts/...` 仍用 PATH 中的 `python`。Windows 的 `WindowsApps\python.exe` Store stub 拦截了 `python` 命令，返回 exit 9009。`INSTALL_PYTHON` 只用于 pre-commit 自身启动，不影响 `language: system` hook 的子进程 python 解析。
3. **N105 教训被过度泛化**：`project_rules.md §3.2` 原文 "AI 可自执行 `git commit --no-verify`（已知 N105 透传 bug,绕开 gaf-commit.sh 兜底用）" 没有限定适用范围，AI 理解为"任何 pre-commit 失败都可绕过"

#### 架构反模式（深层根因）
**「--no-verify 作为通用 escape hatch」**：
- pre-commit hooks 是知识系统的执行层，`--no-verify` 绕过 = 知识系统失效
- N105 的 `--no-verify` 指导本应只针对 `gaf-commit.sh` 的透传 bug（`gaf-commit.sh` 调 `git commit` 时没透传 `--no-verify`），但措辞过于宽泛
- AI 倾向于"最快路径"：遇到 hook 失败 → `--no-verify` 绕过 → 不调查根因 → 预存错误堆积

**「预存错误不登记不修复」**：
- 发现"非本轮范围"的 pre-existing error 时，AI 倾向于"先跳过，下轮再修"
- 但没有登记到 tech-debt/active.md → 遗忘 → 永远不修
- 用户反馈 "都要记录进去，或者当时就解决，不要留着"

**「只改最小范围」**：
- 修复 `check_spec_consistency.py` L52 的 path bug 时，只改了 1 处
- 实际 L229 还有同样的 `root.parent / ".trae"` bug — 修复 1 处后 hook 仍然失败
- 用户反馈 "修改时要从整体框架看下去，不可只以最小修改来弄"

### 3. 修复 (Fix)

#### 3.0 Change `language: system` to `language: python` (N150 真正根因修复)
`.pre-commit-config.yaml` 中 11 个 GAF hooks (10 pre-commit + 1 pre-push) 从 `language: system` 改为 `language: python`。
- `language: python` 让 pre-commit 创建托管 virtualenv，`entry: python scripts/...` 用 venv 的 python，不依赖系统 PATH
- 彻底解决 Windows Store python stub 拦截问题 (exit 9009)
- 脚本只 import stdlib + scripts/ 下本地模块 (`_encoding_safe` / `frontmatter` / `symptom_synonyms`)，无需 `additional_dependencies`
- 4 个 manual-stage lint hooks (eslint/prettier/ruff/mypy) 保持 `language: system` (用 Node/CLI 工具，非 Python 脚本)

#### 3.1 Reinstall pre-commit hooks (TD-063 — INSTALL_PYTHON 路径修正)
```powershell
conda run -n gaf pre-commit install
conda run -n gaf pre-commit install --hook-type pre-push
```
重新生成 `.git/hooks/pre-commit` + `.git/hooks/pre-push`，含正确 `INSTALL_PYTHON='D:\code\environment\conda\envs\gaf\python.exe'`。
注：此步只修正 pre-commit 自身启动路径，不解决 `language: system` hook 子进程的 PATH 问题 (§3.0 才解决)。

#### 3.2 Fix check_spec_consistency.py path bug (TD-066) — 2 处
- `scripts/hooks/check_spec_consistency.py:52` — `REPO_ROOT_DEFAULT.parent / ".trae"` → `REPO_ROOT_DEFAULT / ".trae"`
- `scripts/hooks/check_spec_consistency.py:229` — `root.parent / ".trae"` → `root / ".trae"`

#### 3.3 Fix 11 lesson files (TD-067)
- 6 个文件补齐 front-matter (date/symptom/solution/related_files/created_by)
- 5 个文件修正 related_files 路径 (GAF/ 前缀、已移动文件)
- N110 (merged to N105) → repoint to n105-commit-bypass-rollback.md

#### 3.4 Generate drift migrations (TD-064)
```powershell
conda run -n gaf python backend/manage.py makemigrations settings monitors
conda run -n gaf python backend/manage.py migrate settings monitors
```

#### 3.5 Fill evidence templates (gaf-3step-evidence hook)
用真实 content 替换 `.ai-memory/evidence/active/2026-07-08-pre-commit-stale-path/` 下的模板占位符。

#### 3.6 Update project_rules.md (TD-065)
- §3.2: 收窄 `--no-verify` 到 **仅限** N105 gaf-commit.sh 透传 bug
- §3.2.1: 新增 "pre-commit 失败处理原则" 子节
- §6.4: 添加 N150 索引行
- §6.5: 添加 3 条硬约束 (根因修复 / 预存错误当场处理 / 从整体框架看问题)

### 4. 验证 (Verification)

```powershell
# 1. Lessons validator
conda run -n gaf python -B scripts/hooks/check_lessons_updated.py
# ✅ 40 lessons validated

# 2. Spec consistency
conda run -n gaf python -B scripts/hooks/check_spec_consistency.py
# ✅ spec / tasks / checklist consistent

# 3. 3-step evidence
conda run -n gaf python -B scripts/hooks/check_3step_evidence.py
# ✅ 3-step evidence OK

# 4. Full pre-commit run (ALL 10 hooks) — via conda run
conda run -n gaf pre-commit run --hook-stage pre-commit --all-files
# ALL 10 hooks Passed (exit 0)

# 5. git commit (the REAL test — hooks run via .git/hooks/pre-commit, not conda)
git commit -F .trash/commit_msg_n150.txt
# ALL 10 hooks Passed during actual git commit — no --no-verify needed
# Commit - created, 26 files changed, 734 insertions(+), 36 deletions(-)
```

**关键验证**：步骤 5 是决定性验证。`pre-commit run --all-files` 用 conda env 的 python，但 `git commit` 的 hook 子进程用系统 PATH 的 python。改为 `language: python` 后，两者都通过 — 证明根因已修复。

### 5. Y/N 检查清单 (写入 yn-matrices.md)

#### §3 pre-commit 失败处理 — pre-commit hook 失败时必跑：

| # | 检查项 | Y/N |
|---|--------|-----|
| 1 | **Y**: hook 失败时先调查根因（路径过期？脚本 bug？数据漂移？language 配置？），而非直接 `--no-verify`？ | |
| 2 | **N**: 是否用 `--no-verify` 绕过非 N105 的 pre-commit 失败？（禁止） | |
| 3 | **Y**: 修复后重跑 `pre-commit run --hook-stage pre-commit` 验证全部 Passed？ | |
| 4 | **Y**: 修复后用 `git commit`（非 `pre-commit run`）验证 hook 在实际 commit 时也通过？ | |
| 5 | **Y**: 发现"非本轮范围"的 pre-existing error，当场修复或登记 tech-debt/active.md？ | |
| 6 | **Y**: 修复一个 bug 后检查同类问题是否存在于其他文件（整体框架视角）？ | |
| 7 | **N**: 是否只改最小范围而忽略同根因问题？（禁止 — §2.0 三原则） | |
| 8 | **Y**: Python-based GAF hooks 使用 `language: python`（非 `language: system`）避免 Windows PATH 漂移？ | |

#### §3 预存错误处理 — 发现 pre-existing error 时必跑：

| # | 检查项 | Y/N |
|---|--------|-----|
| 1 | **Y**: pre-existing error 当场修复（如果是 quick fix）？ | |
| 2 | **Y**: 无法当场修复的，登记 tech-debt/active.md（含症状/根因/影响/修复方案/验证标准/何时修）？ | |
| 3 | **N**: 是否"先跳过，下轮再修"但不登记？（禁止 — 会遗忘） | |
| 4 | **Y**: 修复后更新 TD 状态为 ✅ FIXED 并附 commit hash？ | |

### 6. 反模式家族

- **N105**: gaf-commit.sh `--no-verify` 透传 bug — `--no-verify` 的**原始**适用范围
- **N150**: `--no-verify` 被过度泛化为"任何 pre-commit 失败的通用绕过" — 本教训
- **N126**: 文档诚实标记 — 预存错误不登记 = 不诚实
- **N128**: 3 步验证 — 修复后必须验证（Glob + Grep + 命令）
- **§2.0 三原则**: 改动范围由正确性决定，不由"改动最小"决定

### 7. 关联

- **触发**: TD-039 AuditLog 迁移 commit 时 "pre-commit not found"
- **修复**: TD-063 (hook reinstall) + TD-064 (migration drift) + TD-065 (--no-verify 收窄) + TD-066 (spec consistency path) + TD-067 (lessons front-matter)
- **相关 lesson**: N105 (gaf-commit.sh 透传 bug — --no-verify 原始范围)、N91 (hook 失败映射)、N126 (诚实标记)、N128 (3 步验证)
- **相关文件**: `.git/hooks/pre-commit`、`.pre-commit-config.yaml`、`scripts/hooks/check_spec_consistency.py`、`scripts/hooks/check_lessons_updated.py`、`scripts/hooks/check_3step_evidence.py`、`.trae/rules/project_rules.md`、`docs/archive/active-tech-debt.md`

### 8. Distribution (L1 — 4 层)

- ① **lessons/**: 本文件 (完整教训历史)
- ② **arch-mistakes**: "hook 失败绕过 ≠ 根因修复" 架构反模式摘要
- ④ **yn-matrices**: §3 pre-commit 失败处理 + §3 预存错误处理 Y/N 矩阵
- ⑤ **project_rules §6.4**: N150 索引行 + §3.2.1 pre-commit 原则 + §6.5 硬约束

---

## N153: pre-commit stash 丢失未暂存变更 (Windows 文件锁)

> **Date**: 2026-07-11
> **Severity**: L1 (可复用 Y/N 检查清单)
> **Status**: ✅ Fixed (规则约束 + 流程更新)
> **Trigger**: 用户反馈 "为什么测试中会出现前端变更在 pre-commit hook stash 过程中丢失了这种问题"

### Symptom

执行 `git commit` 时，pre-commit 检测到未暂存文件（.gitignore 被修改但未 `git add`），
自动执行 `git stash push --keep-index` 保存未暂存部分。hooks 运行后恢复时，
`git checkout .` 失败：`error: unable to unlink old '.gitignore': Invalid argument`。
stash 未被 pop，前端文件变更（api-paths.test.ts 等 6 个文件）全部丢失。

### Root Cause

1. **操作问题**：commit 时有未暂存变更（.gitignore 修改未 `git add`）
2. **Windows 文件锁**：pre-commit 的 `git checkout .` 恢复 stash 时，
   .gitignore 被 Trae IDE 或 git 进程锁定，`unlink` 失败
3. **pre-commit stash 机制**：stash 失败后 pre-commit 不报错只 warning，
   stash 被丢弃，变更静默丢失

### Fix

#### 规则层 (project_rules.md §3.4)
- 分段提交流程增加步骤 5：`git status 确认无未暂存变更残留`
- N153 硬约束：commit 前必须确保所有变更都已 `git add` 暂存

#### 操作层
- commit 前跑 `git status`，确认没有 `Changes not staged for commit` 行
- 如果有不想 commit 的变更，先 `git stash` 手动保存
- commit 后 `git stash pop` 恢复

#### 跨文件依赖场景 (2026-07-12 补充)
当变更涉及跨文件依赖时（如 scripts/ 重组 + .pre-commit-config.yaml + lesson
related_files 路径 + 测试文件），分段提交不可行 —— pre-commit hooks 检查跨
文件一致性，部分文件被 stash 后 hooks 看到不一致状态会失败。
**正确策略**：`git add -A` 暂存全部 → 单次 commit（无未暂存文件，pre-commit
不会 stash，N153 不触发）。

### Recovery (2026-07-12 补充)

如果 N153 已发生（stash pop 失败，文件丢失）：

1. **定位 patch 文件**：pre-commit 将 stash 内容保存为 patch 文件，位于
   `C:\Users\<user>\.cache\pre-commit\patch<timestamp>-<pid>`
2. **恢复工作树**：`git restore .`（从 index 恢复被删除的文件到 HEAD 状态）
3. **应用 patch**：`git apply --3way <patch-file>`（重新应用未暂存修改）
4. **验证**：`git status --short` 确认所有变更恢复

关键点：
- `git stash list` 为空不代表数据丢失 —— stash 被 pop 但 apply 失败时，
  stash 条目被消耗但 patch 文件仍在磁盘上
- `git apply --3way` 比 `git apply` 更容错，能处理部分 3-way merge
- patch 文件列出所有 `diff --git` 条目，可用于确认恢复范围

### Y/N Checklist

- [ ] commit 前是否跑了 `git status` 确认无未暂存变更？
- [ ] 所有修改的文件是否都已 `git add`？
- [ ] 如果有不想 commit 的变更，是否先 `git stash` 了？
- [ ] 跨文件依赖场景是否考虑了单次 commit 策略？
- [ ] 如果 N153 已发生，是否检查了 pre-commit patch 文件恢复？

### Related

- N105: hook-induced rollback guard (check_git_status_after_hook.py)
- N150: pre-commit 失败根因修复
- project_rules.md §3.4 分段提交流程
