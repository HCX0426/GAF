---
maintainer: manual
source: 用户反馈 "PowerShell 不支持 heredoc。用临时文件，为啥每次都会犯错" + "governance-batch N105 循环为啥不从根源解决"
load_when: [powershell, heredoc, git-commit, n105, mm-state, governance-batch, performance-baseline, l0-missing, hook-loop]
priority: high
symptom: [kb:powershell-heredoc-repeated-mistake, kb:n105-mm-state-loop, N190, L0-missing, env-hardrules-scope-gap]
solution: "两个根源问题同源: L0 系统级硬约束 (env-hardrules.md) scope 不足。修复: ① N105 hook 加 HOOK_MAINTAINED_PATHS 白名单跳过 governance-batch 写入的 performance-baseline.md; ② env-hardrules.md 扩 scope 加 Shell 命令硬约束段 (禁止 heredoc/&&/||, 多行 commit 用 -F <file>)"
related_files:
  - .trae/rules/env-hardrules.md
  - scripts/hooks/check_git_status_after_hook.py
  - scripts/hooks/gaf_governance_batch.py
  - .pre-commit-config.yaml
  - docs/reference/performance-baseline.md
  - .ai-memory/_archive/lessons-retired/N165-powershell-heredoc-repeated-mistake.md
  - .ai-memory/lessons/N105-commit-bypass-rollback.md
  - .ai-memory/_archive/lessons-retired/N188-conda-env-not-enforced.md
  - .ai-memory/meta/ai-operating-handbook.md
  - .trae/rules/project_rules.md
created_by: AI
topic: governance-hardening
last_updated: 2026-07-26
---

# N190 — N105 governance-batch 循环 + PowerShell heredoc 重复犯错 (L0 scope 不足)

> **级别**: L1 可复用经验 (双根源修复 + L0 scope 扩展)
> **分类**: 治理加固 — hook 循环 + shell 兼容性
> **来源**: 2026-07-26 用户两条反馈
> **状态**: ✅ FIXED (L0 硬约束扩展 + hook 白名单机制)

## 触发原话

> 用户反馈 #1 (PowerShell heredoc): "很多次都这样，为啥不预防？每次都犯？ai没自己捕获这个问题吗，ai思维链没反思这个根源？"
>
> 用户反馈 #2 (N105 循环): "governance-batch 每次跑都追加新行到 performance-baseline.md，导致 N105 循环。所有检查都通过（13/13 + B2 + spec-context），用 --no-verify 跳过这个自身循环。为啥不从根源解决"

## 症状

### 症状 #1: PowerShell heredoc 反复犯错

每次写多行 git commit message 时, AI 用 bash heredoc 语法:

```bash
git commit -m "$(cat <<'EOF'
feat: ...

- bullet 1
- bullet 2
EOF
)"
```

PowerShell 解析阶段就报错:

```
ParserError:
Line |
 15 |  ... ; git commit -m "$(cat <<'EOF'
     |                                                   ~
     | Missing file specification after redirection operator.
```

历史复发记录 (N165 lesson 已记 3 次, N190 又复发 1 次):
- 2026-07-16 Spec B commit (N165 第 1 次)
- 2026-07-16 Spec D commit (N165 第 2 次)
- 2026-07-16 v9.3 commit (N165 第 3 次)
- 2026-07-26 spec §4.4.2 阶段 3.4 commit (N190 第 4 次, 本次)

### 症状 #2: governance-batch 写 performance-baseline.md 触发 N105 循环

每次 pre-commit 跑都会发生:

1. `gaf-governance-batch` hook 跑 13 个 check, 全部 pass
2. 跑完后调 `_append_performance_baseline()` ([gaf_governance_batch.py:287-293](file:///d:/code/GAF/scripts/hooks/gaf_governance_batch.py#L287-L293)) 写入一行到 `docs/reference/performance-baseline.md`
3. 该文件之前已 staged → 进入 MM 状态 (staged 旧版 + work tree 新版)
4. 紧接着跑 `gaf-git-status-check` hook (N105 MM state guard)
5. N105 检测到 MM → 阻断 commit, 提示 3 选 1 (git add / git checkout / --no-verify)
6. AI `git add` 后重试, 又回到步骤 1 (循环)

实际证据: `docs/reference/performance-baseline.md` 18-28 行有 11 行 `FAILED: doc-code sync` 记录, 显示该机制频繁触发。

## 根因分析 (3 维)

### 维度 1: L0 系统级硬约束 scope 不足 (N188 同源问题复发)

`env-hardrules.md` 是 N188 (2026-07-25) 为解决 conda 环境规则散布问题新增的 L0 系统级硬约束文件, `alwaysApply: true` 注入 AI 系统 prompt。但 scope 仅限 Python 环境, **没有涵盖 Shell 命令兼容性**:

- `env-hardrules.md` (L0, alwaysApply): 只含 conda 规则, 无 Shell 段
- `project_rules.md §5.2` (L2): "PowerShell 7 支持 `&&`, 但仍不支持 heredoc `<<'EOF'`" — 仅 1 行, 不够强
- `ai-operating-handbook.md Part 2` (L2): "❌ PowerShell 用 bash heredoc" — 已记但 L2 不总是加载
- `N165 lesson` (L1): 完整记录 3 次复发 + workaround — 但 lesson 是按需加载, 写命令时未必触发

**与 N188 同源**: L0 系统级硬约束缺失, AI 系统 prompt 看不到, 反复违反。

### 维度 2: N105 hook 设计无白名单机制

`check_git_status_after_hook.py` 的 `scan_problems()` 设计是"任何文件被 hook 修改 → 阻断", 没有考虑"hook 主动维护的文件应该被排除":

- `AUTO_MAINTAINED_PATHS` (L79-86) 仅用于 `--auto-only` flag, **缩小**扫描范围, 不是白名单
- 默认 `--all` 模式扫描所有文件
- `GAF_ALLOW_HOOK_WRITES=1` env var 只在 `sync_ai_memory.py` 内生效 (L117-133), N105 hook 不识别
- `check_git_status_after_hook.py` 全文无 `GAF_ALLOW_HOOK_WRITES` 引用, 也无任何文件白名单数组

**根因**: N105 hook 设计时未评估"hook 自身写入文件"场景, 把所有 MM 状态都当 bug。

### 维度 3: spec-2026-07-26-ai-governance-execution-rate-fix Wave 3 未评估 N105 冲突

`_append_performance_baseline()` 是该 spec Wave 3 (L188-232) 新增的自动 append 机制, 但 spec 文件**完全没有评估 N105 hook 冲突**:

- spec 假设 governance-batch 写文件后用户会 `git add` 进 commit
- 实际 N105 hook 在 `git add` 之前就阻断, 形成循环
- spec-context 文件 (`docs/archive/spec-context/` (2026-07-26 治理 spec 的承载体未归档, 仅存 governance-redundancy 版本)) 第 117 行间接提到 "commit 重试", 但未沉淀为 lesson

**根因**: spec 设计阶段未做 hook 依赖图分析, 不知道 governance-batch 写文件会触发 N105。

## 解决方案

### 修复 #1: N105 hook 加 HOOK_MAINTAINED_PATHS 白名单

[scripts/hooks/check_git_status_after_hook.py](file:///d:/code/GAF/scripts/hooks/check_git_status_after_hook.py) 新增 `HOOK_MAINTAINED_PATHS` 集合 (L88-106):

```python
HOOK_MAINTAINED_PATHS = {
    "docs/reference/performance-baseline.md",
}
```

`scan_problems()` 在判定 PROBLEMATIC_COMBOS 后, 先跳过 `HOOK_MAINTAINED_PATHS` 中的路径 (L213-216):

```python
if entry.path in HOOK_MAINTAINED_PATHS:
    continue
```

**效果**: governance-batch 写入 performance-baseline.md 不再触发 N105 MM state guard, 循环消除。白名单是显式声明的, 不会掩盖其他 hook 的真实 bug。

### 修复 #2: env-hardrules.md 扩 scope 加 Shell 段

[.trae/rules/env-hardrules.md](file:///d:/code/GAF/.trae/rules/env-hardrules.md) (L0, alwaysApply) 新增 `## Shell 命令硬约束 (PowerShell) — N190 新增` 段 (L33-44), 包含 4 条规则:

1. 禁止 bash heredoc `<<'EOF'`
2. 禁止 `&&` / `||` 链式
3. git commit message 必须用**单行 `-m`** — 用户在 N190 后续反馈中明确禁用 `-F <file>` 方式, 改为单行 `-m` + 分号串联要点 (`git commit -m "feat(scope): subject — p1; p2; p3"`)
4. `;` 分隔不短路, 失败仍跑下一个

新增 `## Shell 命令校验 (写命令前自检)` 段 (L65-73), 5 项 Y/N 自检清单, 含"遇到重复犯的错先做根源分析"一项。

**演进**: 初版规则用 `-F <file>` 处理多行 commit message, 但用户反馈"commit 不要用 -F, 用 -m"。**反思**: -F 需要写临时文件 + DeleteFile 清理 + .trash 目录约定, 增加了 3 个出错点; 单行 -m 简单可靠, 信息密度用分号/破折号串联即可。这次演进证明: **workaround 越简单越好**, 临时文件方案是过度工程。

**效果**: AI 系统 prompt 每次对话都看到 Shell 硬约束, 与 conda 规则同等约束力。预期复发率从"每次都犯"降到"偶尔违反, 自检清单兜底"。

## 防错机制 (Y/N 检查清单)

AI 写 shell 命令前自检:

```text
□ 是否用了 heredoc `<<'EOF'`? → 改用单行 `-m` (用分号串联要点)
□ 是否用了 `&&` / `||`? → 改用 `;` 分隔, 注意失败不短路
□ 是否引用了 Unix 命令 (head/tail/find/grep/cat/sed/awk)? → 改用 PowerShell 等价或专用工具
□ commit message 想多行? → 禁用 -F/多 -m; 用单行 `-m "subject — p1; p2; p3"`
□ 遇到重复犯的错 (PowerShell heredoc/conda 环境/...)? → 先做根源分析: 能否升级到 L0 硬约束 (env-hardrules.md) 或加 hook 白名单? 不要只解决当前实例
```

## 验证

### 验证 #1: N105 白名单生效

模拟 governance-batch 写入 performance-baseline.md 后跑 N105 hook:

```bash
# 模拟: 先 stage performance-baseline.md, 再修改 work tree 版本 (MM 状态)
git add docs/reference/performance-baseline.md
echo "test row" >> docs/reference/performance-baseline.md
# 跑 N105 hook
python scripts/hooks/check_git_status_after_hook.py
# 预期: ✅ git-status clean (all files) — 白名单跳过 performance-baseline.md
```

### 验证 #2: env-hardrules.md Shell 段加载

新对话开始时, AI 系统 prompt 应包含 Shell 命令硬约束段。AI 写 commit 命令前主动检查 heredoc/&&。

## 与现有 lesson 的关系

- **N165** (PowerShell heredoc 重复犯错): N190 是其根源修复。N165 只记 workaround (临时文件 + `-F`), N190 把规则升到 L0 系统级硬约束。
- **N188** (conda 环境规则): N190 是同源问题的第二个实例。N188 解决 conda 规则散布, N190 解决 Shell 规则散布。两者都通过扩 `env-hardrules.md` scope 修复。
- **N105** (commit bypass rollback): N190 给 N105 家族增加第 6 个变体 (governance-batch 写 performance-baseline.md 触发循环), 并通过白名单机制根治。
- **N150** (3.3 自执行 commit 硬约束): N190 修复后, `--no-verify` 绕过 hook 的需求大幅减少; 同时 N150 第 2 条原是"多行用 `-F <file>`", 但用户在 N190 后续反馈中明确禁用 -F, 改用单行 -m, N150 该条已过时, 待后续清理。

## 反思

### 为啥这次没在 N165 时就根治?

N165 (2026-07-16) 已经识别根因是"L0 系统级硬约束缺失", 但当时只写到 L2 handbook + Y/N 检查清单, **没有升到 L0**。原因是 N165 时 `env-hardrules.md` 还不存在 (N188 是 2026-07-25 才创建), L0 硬约束机制本身还没建立。

N188 建立 L0 机制后, 应该回头把 N165 也升级, 但没有。**这是反思纪律的缺失**: 新机制建立后, 应主动扫描历史 lesson 看哪些可以升级。

### 为啥 spec Wave 3 设计时没评估 N105 冲突?

spec-2026-07-26-ai-governance-execution-rate-fix Wave 3 设计 `_append_performance_baseline()` 时, 只关注"自动沉淀性能数据", 没做 hook 依赖图分析。**这是 spec 设计阶段的盲区**: 新增 hook 写入文件时, 必须检查是否会触发其他 hook。

未来 spec 设计应增加"hook 依赖图"检查项: 新增 hook 写入文件 → 列出所有读该文件的其他 hook → 评估循环风险。

### 为啥 N190 初版选了 -F <file> 而不是单行 -m?

N190 初版规则把"多行 commit message"的方案定为 `-F <file>` (写临时文件 → commit → DeleteFile 清理), 但用户反馈"commit 不要用 -F, 用 -m"。**根因**: AI 默认把"多行"当成硬需求, 没考虑"用分号/破折号压成单行"的更简单方案。这是**过度工程的典型**: 引入 3 个新出错点 (临时文件路径约定 / .trash 目录 / 清理遗漏) 来满足一个本可不存在的需求。

教训: **workaround 越简单越好**。设计规则时, 先问"能不能不做这个 workaround?", 再问"能不能简化?"

### AI 思维链反思纪律

用户原话: "ai思维链没反思这个根源？"

AI 思维链确实有反思环节 (N134 lesson), 但反思深度不够:
- 表层反思: "PowerShell 不支持 heredoc, 改用 -F" — 只解决当前 instance, 还引入了过度工程
- 深层反思: "为啥 L0 系统级硬约束没覆盖 Shell?" — 解决 root cause
- 元反思: "L0 机制建立后, 历史 lesson 哪些应该升级?" — 解决 process gap
- **根源反思 (本次新增)**: "这个 workaround 是不是过度工程? 能不能直接不做?" — 砍需求而非堆方案

本次修复后, 应在 N134 反思纪律中加两条:
1. **新机制建立后, 主动扫描历史 lesson 看哪些可以升级**
2. **设计 workaround 时, 先问"能不能不做这个 workaround?", 再问"能不能简化?"**
