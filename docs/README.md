---
summary: docs/ 双线索导航入口（业务 9 模块 + 架构 5 层）
applies_to: ['docs', 'navigation']
key_decisions:
  - 双线索导航：业务视角（前端侧边栏 9 模块）+ 架构视角（GAF 五层）
  - 文档归属强制二选一，跨业务+架构的文档放 architecture/cross-cutting/
  - spec 目录单一化：docs/specs/{active,archived}/
  - 旧路径零兼容：原 general/ + superpowers/ + governance/ 三目录已删除（P0 重构后）
last_updated: 2026-07-26
---

# GAF docs/ 知识库

> **维护方式**：AI 维护（不是人工维护）。修改文档后必跑 `python scripts/bootstrap/sync_docs_index.py` 更新 `.ai-memory/meta/docs-index.md`。
> **导航原则**：人类按业务或架构找文档，最多 2 次点击定位；AI 通过 `docs-index.md` 的 `module` 字段过滤，0 跳转直达目标。

## ⭐ 项目状态核心入口

所有项目级状态（待办、已完成、技术债务、健康报告）请直接查看：
👉 **[`project-status.md`](project-status.md)**

## 双线索导航

### 线索一：业务视角（9 模块，对应前端侧边栏）

按"我在用哪个功能"找文档 → [`business/`](business/README.md)

| 模块 | 路径 | 说明 |
|------|------|------|
| 工作台 | [`business/workspace/`](business/workspace/) | 工作台（待新文档填入） |
| 游戏档案 | [`business/game-profile/`](business/game-profile/) | 游戏档案（待新文档填入） |
| 任务 | [`business/tasks/`](business/tasks/) | 任务设计（Pipeline / chain / state_machine） |
| 设备 | [`business/devices/`](business/devices/) | 设备相关（DPI / 截图优化） |
| 资源 | [`business/resources/`](business/resources/) | 资源包设计 |
| 账户 | [`business/accounts/`](business/accounts/) | 账户（待新文档填入） |
| 运维 | [`business/ops/`](business/ops/) | 运维监控 + 治理仪表盘 |
| AI | [`business/ai/`](business/ai/) | LLM 集成 + 输入模式 |
| 系统 | [`business/system/`](business/system/) | 系统（待新文档填入） |

### 线索二：架构视角（5 层 + 横切）

按"我在改哪一层"找文档 → [`architecture/`](architecture/README.md)

| 层 | 路径 | 说明 |
|----|------|------|
| 前端层 | [`architecture/frontend/`](architecture/frontend/) | 待新文档填入 |
| 后端层 | [`architecture/backend/`](architecture/backend/) | 待新文档填入 |
| Agent 层 | [`architecture/agent/`](architecture/agent/) | 待新文档填入 |
| Desktop 层 | [`architecture/desktop/`](architecture/desktop/) | Electron 部署设计 |
| 横切关注点 | [`architecture/cross-cutting/`](architecture/cross-cutting/) | 并发 / pre-commit / 数据流 |
| 架构根 | [`architecture/`](architecture/) | 总览 / 最优方案 / 业务×架构映射 |

## 顶层目录

| 目录 | 用途 |
|------|------|
| [`analysis/`](analysis/) | GAF 与外部方案对比分析（Alas / BD2 / MaaFramework / ok-script） |
| [`standards/`](standards/) | 编码规范（API / 后端 / 前端 / 测试） |
| [`specs/`](specs/) | 跨设计文档的 spec 索引 + 已归档 spec |
| [`archive/`](archive/) | 归档文件：技术债详情、已完成功能、健康报告、spec-context 承载体 |
| [`health/`](health/) | 月度健康检查指南 (`procedure.md`) |
| [`reference/`](reference/) | 参考资料：技术栈、数据流、CLI 速查、已知陷阱总结 |

## 顶层文件

- [`project-status.md`](project-status.md) — **【核心】项目状态仪表板** (活跃待办、已完成、技术债务、健康报告)

## 与 .ai-memory 的职责分离

*   **`docs/`** 是**项目的公共知识库**：记录项目的 **What & Why**（是什么、为什么这么设计、项目当前状态）。
*   **`.ai-memory/`** 是 **AI 的内部工作记忆**：记录 AI 的 **How & How-to**（如何工作、有哪些经验教训、工作过程的详细记录）。

两者职责不同，内容互补：
*   `docs/standards/` (项目规范) vs `.ai-memory/lessons/` (AI 从项目中学到的教训)
*   `docs/archive/` (项目历史归档) vs `.ai-memory/evidence/` (AI 解决问题的过程记录)
*   `docs/reference/` (项目技术栈、数据流、CLI 速查) vs `.ai-memory/` (AI 工作记忆：经验教训、失败模式、检查清单)

## 文档 frontmatter 契约

每份 docs/ 文档必含 frontmatter（`sync_docs_index.py` 校验）：

```yaml
---
summary: 一句话说明 (≤ 80 字)
applies_to: [tag1, tag2, ...]
last_updated: YYYY-MM-DD
---
```

以下字段由 `sync_docs_index.py` 自动生成到 `docs-index.md`，**源文档不需要写**：

- `module` — 从目录路径推导（如 `docs/business/tasks/` → `business.tasks`）
- `applies_to_code_paths` — 按内置映射表填充（见 spec §9.1）
- `maintainer` — 固定 `ai`
- `doc_last_updated` — 从 git log 获取文档最近修改日期

## 维护说明

- 修改任何 docs/ 文件 → 更新其 `last_updated` + 重跑 `sync_docs_index.py`
- 新建 docs/ 文件 → 加 frontmatter + 重跑 `sync_docs_index.py`
- pre-commit hook: docs/ 改动 → 强制 `doc_last_updated` 字段同步更新（R8 规则）
- gaf_init.sh L1: 警告过期文档 (> 90 天)
