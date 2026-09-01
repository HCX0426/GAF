---
summary: architecture/ 架构视角索引（5 层 + 横切）
applies_to: ['architecture', 'navigation']
key_decisions:
  - 五层架构：frontend / backend / worker / desktop / cross-cutting
  - 架构根放总览类文档（overview / optimal-solution / features-overview）
  - 跨层文档放 cross-cutting/
last_updated: 2026-09-01
---

# architecture/ 架构视角索引

按"我在改哪一层"找文档。GAF 五层架构 + 横切关注点。

## 架构根（总览类）

| 文档 | 说明 |
|------|------|
| [`overview.md`](overview.md) | 架构总览 |
| [`optimal-solution.md`](optimal-solution.md) | GAF 最优方案 |
| [`features-overview.md`](features-overview.md) | 业务×架构映射（功能总览） |
| [`system-overview.svg`](system-overview.svg) | 全栈架构一图总览（前端 → 后端 → Agent → 设备 + AI 治理层） |

## 五层架构

| 层 | 路径 | 文档数 | 说明 |
|----|------|--------|------|
| 前端层 | [`frontend/`](frontend/) | 0 | 待新文档填入 |
| 后端层 | [`backend/`](backend/) | 0 | 待新文档填入 |
| Worker 层 | [`worker/`](worker/) | 0 | 待新文档填入 |
| Desktop 层 | [`desktop/`](desktop/) | 1 | 部署设计（Electron） |
| 横切关注点 | [`cross-cutting/`](cross-cutting/) | 2 | 并发设计 / pre-commit 阶段 |

## 文档归属规则

- 文档主要描述**架构实现**（代码怎么组织、跨多业务） → 放 `architecture/<layer>/`
- 文档主要描述**业务功能** → 放 `business/<module>/`
- 跨业务+架构的文档 → 放 `architecture/cross-cutting/`
- 业务×架构映射表 → 放架构根（如 `features-overview.md`）

## 维护说明

- 新建架构文档 → 加 frontmatter + 重跑 `sync_docs_index.py`
- `module` 字段由 `sync_docs_index.py` 自动从目录路径推导（如 `architecture.desktop` / `architecture.cross-cutting` / 架构根文档为 `architecture`）
