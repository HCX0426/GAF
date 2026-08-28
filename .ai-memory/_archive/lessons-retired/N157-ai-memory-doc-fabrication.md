---
date: 2026-07-11
priority: high
symptom: [ai-memory-fabrication, doc-code-mismatch, fictional-implementation, path-error, node-type-error, maturity-false-marking]
solution: AI memory documents must be verified against actual code/resources before writing. Never describe "planned" implementation as "actual" implementation. When reading AI memory docs, verify paths/files exist before trusting them.
diff_keywords: [fabrication, doc-code-mismatch, fictional-implementation, manifest]
related_files:
  - .ai-memory/games/browndust-ii/common-tasks.md
  - .ai-memory/games/browndust-ii/assets.md
  - .ai-memory/games/browndust-ii/coordinate-system.md
  - .ai-memory/games/browndust-ii/overview.md
  - resources/BrownDust II/manifest.json
  - resources/BrownDust II/tasks/login.json
  - agent/src/engine/resource_resolver.py
created_by: AI
level: L1
n_id: N157
topic: honest-status
---

# N157 — AI memory documents fabricated implementation: paths, node types, maturity all fictional

> **级别**: L1 可复用经验（Y/N 检查清单价值 + 影响 AI 全局行为 + 架构反模式）
> **分类**: 文档诚实标记 — AI memory 文档虚构实现
> **来源**: 2026-07-11 BD2 任务测试 — 用户指出 `resources/BrownDust-II/` 存在但 AI 搜了 `assets/templates/browndust-ii/`
> **登记**: 2026-07-11
> **状态**: ✅ FIXED (4 份文档重写 + N157 教训分发)

## 触发原话

"D:\code\GAF\resources\BrownDust-II\templates这里的不是任务吗？？D:\code\GAF\resources\BrownDust-II资源不是在这里吗"

"之前搜 assets/templates/browndust-ii/，为啥会搜这个，什么文档或代码错了？"

## 事件概述

用户要求测试 BD2 任务。AI 审计资源时 `Glob("assets/templates/browndust-ii/**")` 返回空，于是报告"模板图片不存在，无法测试"。用户指出实际资源在 `resources/BrownDust-II/`。

**根因调查**发现 `.ai-memory/games/browndust-ii/` 下 4 份文档（2026-06-16 生成）全面失真：

| # | 错误类型 | 文档写的 | 实际情况 |
|:-:|---------|---------|---------|
| 1 | 模板路径错误 | `assets/templates/browndust-ii/` | `resources/BrownDust-II/templates/` |
| 2 | 模板命名虚构 | `btn_battle.png`/`btn_confirm.png` 等英文命名 | `主界面.png`/`开始游戏.png` 等中文命名 |
| 3 | 节点类型虚构 | `click_template`/`ocr_region`/`wait_for_template`/`conditional` | `template_match`/`ocr`/`wait`/`branch` |
| 4 | 不存在的文件 | `Bd2ImportPanel (已删除)` | `frontend/src/pages/Setup/StepRecommendedTemplates.tsx` |
| 5 | 成熟度虚标 | "✅ 成熟, 准确率 98%" | 无任何验证证据，刚从 BD2-AUTO 移植 |
| 6 | 格式虚构 | YAML `steps:` + `type: click_template` | JSON `nodes:` + `type: template_match` |
| 7 | 坐标基准错误 | 1280x720 | 实际 ROI 基准 1920x1080 (`original_base_res`) |
| 8 | 虚构代码文件 | `agent/src/core/pipeline_nodes.py` | 实际 `agent/src/engine/nodes/template_match.py` |

## 根因分析

### 时间线

| 时间 | 事件 | 问题 |
|------|------|------|
| 2026-06-14 (`-`) | BD2 资源包迁移到 `resources/BrownDust-II/`（中文模板名 + JSON pipeline） | — |
| 2026-06-16 (`-`) | AI memory 4 份文档生成 | **没有对照实际资源**，写了一个虚构的实现 |
| 2026-07-05 (`-`) | R37-P2 迁移到 Pipeline JSON | AI memory 文档仍未更新 |
| 2026-07-11 | 用户发现 AI 搜错路径 | 4 份文档全面失真暴露 |

### 为什么会虚构？

AI memory 文档生成时（2026-06-16），资源包已存在 2 天（2026-06-14），但 AI **没有 Read/Glob 实际资源目录**，而是凭空写了一个"看起来合理"的实现：
- 路径用 `assets/templates/browndust-ii/`（常见的前端资源路径约定）
- 模板名用 `btn_battle.png`（常见的英文命名约定）
- 节点类型用 `click_template`（直觉性的命名）
- 成熟度标 `✅ 98%`（没有验证就标了）

这是 **"先文档后实现"反模式** + **N126 文档诚实标记违规**的极端案例：不只是标记错误，而是整个文档描述了虚构的实现。

### 为什么 AI 会被误导？

后续 AI session 读取这些文档时，**信任了文档内容没有验证**：
- `Glob("assets/templates/browndust-ii/**")` → 空 → 报告"资源不存在"
- 没有反过来检查"文档说的路径是否真的存在"

## 修复

### 4 份文档重写

| 文档 | 修正内容 |
|------|---------|
| `common-tasks.md` | 12 个实际 pipeline JSON + 真实节点类型 + 🔧 待验证成熟度 |
| `assets.md` | 实际 `resources/BrownDust-II/` 结构 + 67 个中文模板名 + resource_resolver.py |
| `coordinate-system.md` | 1920x1080 ROI 基准 + 实际 rois.json 值 + resource_resolver.py |
| `overview.md` | StepRecommendedTemplates.tsx + 12 pipeline 移植状态 + 🔧 待验证 |

### N157 教训分发 (L1, 4 层)

| 层 | 文件 | 内容 |
|---|------|------|
| ① lessons | 本文件 | 完整教训 |
| ② arch-mistakes | `_audit-verification-honesty.md` | #58 架构反模式 |
| ④ yn-matrices | `_honest-status.md` | Y/N 检查矩阵 |
| ⑤ project_rules | §6.4 N157 索引行 | 硬约束 |

## Y/N 检查清单

| # | 检查项 | Y/N | 说明 |
|:-:|--------|:---:|------|
| 1 | 写 AI memory 文档前，是否 Glob/Read 了实际代码/资源目录？ | | Y=基于实际写 / N=先验证再写 |
| 2 | 文档中写的路径，是否验证过存在？ | | `Glob("<path>")` 非空 |
| 3 | 文档中写的文件名，是否验证过存在？ | | `Glob("**/<filename>")` 非空 |
| 4 | 文档中写的 API/节点类型，是否 Grep 过实际代码？ | | `Grep("<type>" agent/src/)` 非空 |
| 5 | 标 ✅ 前，是否有验证证据（测试通过/浏览器截图/pytest 输出）？ | | N128 3 步验证 |
| 6 | 读 AI memory 文档后，是否验证了关键路径/文件存在？ | | 不盲目信任 |
| 7 | 文档生成后，实际代码变更时是否同步更新文档？ | | 代码改了文档也要改 |

## 适用范围

- **触发条件**：任何写/读 AI memory 文档的场景
- **特别适用**：游戏档案、架构文档、API 文档、资源路径文档
- **核心原则**：AI memory 文档描述"实际怎么做"，不描述"打算怎么做"

## 关联

- **N126**: 文档诚实标记 — 本教训是 N126 的极端案例（整个文档虚构，不只是标记错误）
- **N128**: 文档状态 3 步验证 — 本教训补充：读文档时也要验证，不只写文档时
- **N129**: 审计 3 棵代码树 — 本教训是"审计资源目录"的补充
- **N156**: 先读代码再测试 — 本教训是"先验证文档再信任"的变体

## 复发记录

- 2026-07-11: 首次登记（4 份 AI memory 文档全面失真，导致 AI 搜错路径）
