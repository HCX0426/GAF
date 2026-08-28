---
date: 2026-07-16
symptom: [powershell-heredoc-failure, commit-message-syntax-error, repeated-mistake, no-anti-recurrence-mechanism]
solution: "N190 已取代本文件的修复建议 (2026-07-26): ① 禁用 bash heredoc `<<'EOF'` (保持不变) ② 禁用 `&&`/`||` 链式 (保持不变) ③ commit message 用单行 `-m` 或多个 `-m` flag 串联, **禁用 `-F <file>`** (N190 明确禁用 -F, 引入临时文件 + .trash + 清理遗漏 3 个出错点); ④ `-F` 从建议变为禁用 — 本文件 P0 修复段历史建议已失效; L0 硬约束在 env-hardrules.md Shell 段"
related_files:
  - .ai-memory/meta/ai-operating-handbook.md
  - .trae/rules/project_rules.md
  - scripts/gaf_init.sh
created_by: AI
priority: high
n_id: N165
topic: command-errors
level: L1
cross_refs: [N134, N162, N150, N100, N190]
l2_candidate: true
superseded_by: N190
status: superseded
---

# N165 — PowerShell heredoc 重复犯错（无防错机制）

> **状态**: ⚠️ **superseded_by N190** (2026-07-26) — 本 lesson 的修复建议 (临时文件 + `git commit -F`) 已被 N190 反转: N190 明确**禁用 `-F`**, 改用单行 `-m` 或多个 `-m` flag 串联。本文件仅作历史教训保留, 当前规则以 `env-hardrules.md §Shell` (N190) 为准。

> **级别**: L1 可复用经验（Y/N 检查清单 + 影响 AI 全局行为）
> **分类**: 命令使用 — PowerShell 环境兼容性
> **来源**: 2026-07-16 用户反馈"我见了很多次 PowerShell 不支持 heredoc。用临时文件，为啥每次都会犯错，ai 没有反思链了吗"
> **历史状态**: ✅ FIXED（防错机制已写入 L2 硬加载文件）→ 后被 N190 取代

## 触发原话

> "我见了很多次PowerShell 不支持 heredoc。用临时文件，为啥每次都会犯错，ai没有反思链了吗，我之前说过的啊，继续吧"

## 症状

AI 在 PowerShell 环境下多次使用 bash heredoc 语法 `git commit -m "$(cat <<'EOF' ... EOF)"`，导致：
1. PowerShell 解析失败
2. 需要重写为临时文件 + `git commit -F`
3. 浪费对话轮次 + 打断任务流

历史发生次数（不完全统计）：
- Spec B commit（2026-07-16）
- Spec D commit（2026-07-16）
- v9.3 瘦身 commit（2026-07-16）

## 根因分析

1. **肌肉记忆**：bash 环境下 heredoc 是多行 commit 的标准做法，AI 记忆中"多行 commit = heredoc"
2. **环境检测缺失**：AI 没有在 commit 前主动检测当前 shell 环境
3. **防错机制未沉淀到 L2**：虽然每次事后都改用临时文件，但没有写入 L2 硬加载文件，导致下次对话又忘了
4. **N134 反思纪律未执行**：每次犯错只当场改，没有反思根因 + 写防错机制

## 修复方案

### P0 修复（本轮完成，后被 N190 取代）

1. **写入 ai-operating-handbook.md Part 2 命令使用段**（L2 硬加载）
   - 新增红线：`❌ PowerShell 用 bash heredoc → ✅ 写临时 .txt 文件 + git commit -F` **（N190 修订：`-F` 已禁用，改为多个 `-m` flag 串联）**
   - 新增红线：`❌ PowerShell 用 && 链式执行 → ✅ 用 ; 分隔`
   - AI 启动时强制 Read，看到具体防错规则

2. **N165 lesson 文件创建**（本文件）
   - 记录触发原话 + 根因 + 修复 + 防错机制
   - 沉淀到 failure-modes.md 索引

### 防错机制

- ✅ 多行 commit message 一律用 `git commit -F <file>`，禁止用 `-m` 传递多行 **（N190 修订：禁用 `-F`，改用单行 `-m` 或多个 `-m` flag 串联）**
- ✅ 临时文件放 `.trash/` 目录，commit 后删除 **（N190 修订：无需临时文件，`-F` 已禁用）**
- ✅ commit 前检测环境：如果是 PowerShell（默认终端），不用 heredoc

## Y/N 检查清单

- [ ] 多行 commit message 是否用 `git commit -F <file>`？**（N190 修订：禁用 `-F`，用多个 `-m` flag 串联）**
- [ ] PowerShell 环境下是否避免 heredoc `<<'EOF'`？
- [ ] PowerShell 环境下是否避免 `&&` 链式执行？（用 `;` 分隔）
- [ ] 临时 commit message 文件是否放 `.trash/` 并 commit 后删除？**（N190 修订：无临时文件，`-F` 已禁用）**

## 验证

- ai-operating-handbook.md Part 2 命令使用段已新增 2 条红线
- N165 lesson 文件已创建（本文件）
- failure-modes.md Active 索引已追加 N165

## 关联

- **N134** (反思纪律) — 本教训就是 N134 触发：命令用错只当场改不够，必须反思根因 + 防错机制
- **N162** (命令防错) — 同类家族，命令使用层面的防错
- **N150** (pre-commit 失败根因修复) — heredoc 失败虽不是 pre-commit 失败，但同属命令使用错误
- **N100** (Set-Content 损坏 f-string) — 同类家族，PowerShell 环境兼容性问题
