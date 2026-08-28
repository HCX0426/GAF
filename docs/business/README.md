---
summary: business/ 业务视角索引（9 模块，对应前端侧边栏）
applies_to: ['business', 'navigation']
key_decisions:
  - 9 模块对应前端侧边栏：workspace / game-profile / tasks / devices / resources / accounts / ops / ai / system
  - 文档归属强制二选一，跨业务+架构的文档放 architecture/cross-cutting/
last_updated: 2026-07-26
---

# business/ 业务视角索引

按"我在用哪个功能"找文档。9 模块对应前端侧边栏。

## 9 模块清单

> **路径对照**：表格"前端路由"列对应 `frontend/src/App.tsx` 的实际路由；"docs 目录"列对应本目录下的子目录（`-` 表示尚未创建，待新文档填入时再建）。

| 模块 | 前端路由 | docs 目录 | 文档数 | 说明 |
|------|---------|-----------|--------|------|
| 工作台 | `/dashboard` | - | 0 | 待新文档填入 |
| 游戏档案 | `/game-profiles` | - | 0 | 待新文档填入 |
| 任务 | `/tasks` | [`tasks/`](tasks/) | 8 | Pipeline 设计 / 时间线 / 调试模式 / 恢复 / 取消 / 执行现实 / 故障排查 / Pipeline 作者指南 |
| 设备 | `/devices` | [`devices/`](devices/) | 2 | DPI 坐标系 / 截图优化 |
| 资源 | `/resources` | [`resources/`](resources/) | 1 | 资源包设计 |
| 账户 | `/accounts` | - | 0 | 待新文档填入 |
| 运维 | `/ops` | [`ops/`](ops/) | 2 | 监控设计 / 治理仪表盘 |
| AI | `/ai` | [`ai/`](ai/) | 2 | LLM 集成 / 输入模式与窗口等待 |
| 系统 | `/system` | - | 0 | 待新文档填入 |

## 文档归属规则

- 文档主要描述**业务功能**（用户能用它做什么）→ 放 `business/<module>/`
- 文档主要描述**架构实现**（代码怎么组织）→ 放 `architecture/<layer>/`
- 跨业务+架构的文档 → 放 `architecture/cross-cutting/`
- 外部对比分析 → 放顶层 `analysis/`

## 维护说明

- 新建业务文档 → 加 frontmatter + 重跑 `sync_docs_index.py`
- `module` 字段由 `sync_docs_index.py` 自动从目录路径推导（如 `business.tasks`）
