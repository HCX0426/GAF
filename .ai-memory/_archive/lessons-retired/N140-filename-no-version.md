---
date: 2026-07-03
symptom: [filename, version-number, naming-convention, workflow]
solution: 文件名禁止带版本号后缀 (v1/v2/v3); 版本由 git 追踪, 文件名是稳定标识符
related_files:
  - .trae/rules/project_rules.md
  - .ai-memory/lessons/README.md
  - .ai-memory/meta/yn-matrices.md
created_by: AI
priority: medium
l2_candidate: true
level: L1
n_id: N140
topic: workflow
---

# N140: 文件命名禁止版本号

## 触发原话

> 文件命名不要带版本号，这个要记录到skill或者规则中，带版本的不符合规范吧

## 根因

在 `.trash/` 临时文件和部分文档中，文件名包含版本号后缀（`v1`/`v2`/`v3`），例如：
- `fix_m10_v2.py`, `fix_m10_v3.py`, `fix_m10_v4.py`, `fix_m10_v5.py` — 同一脚本的 4 个版本
- `diag_release_v2.py` ~ `diag_release_v6.py` — 同一诊断脚本的 5 个版本
- `gaf-v2-enhanced-feature-spec.md` (文档名含 v2)

**问题**：
1. 版本号在文件名中是冗余的 — git 已经追踪文件的完整变更历史
2. 当文件需要迭代时，开发者倾向于创建新版本（`_v2`, `_v3`）而非覆盖原文件，导致：
   - 仓库膨胀（同一逻辑的多个副本）
   - 不清楚哪个版本是"最新"的
   - 引用时需要指定版本号，引用过时后忘记更新
3. 文件名应是**稳定标识符**，不应随版本变化

## 修复方案

**规则**：文件名不得包含 `v1`/`v2`/`v3` 等版本后缀。

**正确做法**：
- 需要迭代时，**覆盖同一文件**（git 追踪历史变更）
- 如果需要保留不同变体（如不同算法实现），用**描述性后缀**：
  - ✅ `fix_m10_retry.py`（重试版本）
  - ✅ `fix_m10_parallel.py`（并行版本）
  - ❌ `fix_m10_v2.py`（版本号无语义）

**例外**：
- 第三方库文件（如 `version-compat.md` 描述版本兼容性，文件名中的 "version" 是主题不是版本号）
- `__version__.py` 等约定俗成的版本声明文件

## 验证

- `project_rules.md` §2 已添加 N140 硬约束
- `project_rules.md` §6.4 N## 索引表已添加 N140 条目
- `project_rules.md` §6.5 通用硬约束已添加 N140 汇总
- `.trash/` 中已有的版本号文件不追溯清理（临时文件，任务中不删除 N125）

## 5 层分发检查

| 层级 | 路径 | 状态 |
|:---:|------|:---:|
| ① | `.ai-memory/lessons/N140-filename-no-version.md` | ✅ 本文件 |
| ② | `.ai-memory/summaries/architecture-mistakes.md` | ✅ (命名规范, 非架构错误, 仅 rules 层) |
| ③ | spec/plan 文档 | ✅ (N140 已编入 §2, 无独立 spec 条款) |
| ④ | `.ai-memory/meta/yn-matrices.md` §1 workflow | ✅ 待添加 |
| ⑤ | `.trae/rules/project_rules.md` §2 + §6.4 + §6.5 | ✅ 已添加 |
