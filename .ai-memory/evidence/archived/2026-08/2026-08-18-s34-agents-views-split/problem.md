---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-18-s34-agents-views-split/
load_when: [evidence, 3-step-evidence, s34, views-split, 大文件拆分]
priority: high
symptom: [monthly_health_check i1_large_files 报 backend/agents/views.py 3983 行超 2000 阈值, 全仓最大单文件, 无拆分治理]
related_files:
  - docs/specs/active/2026-08-17-s34-agents-views-split.md
  - backend/agents/views.py
  - backend/agents/view_sets/
created_by: AI
last_updated: 2026-08-18
---
## Problem（症状 / 触发条件）

1. 现象：`backend/agents/views.py` 3983 行 (全仓最大文件), monthly_health_check i1_large_files 维度持续报警；20 个顶层定义 (19 视图类 + 1 函数) 单文件堆积, 定位/审查成本高。
2. 触发条件：monthly_health_check 扫描 (TD-365 登记, 2026-08-17)；功能迭代持续向同一文件追加视图。
3. 影响范围：backend agents app 全部视图 API；引用方 3 处 (agents/urls.py 19 符号 + monitors/views.py:780 懒加载 + agent_runtime.py:436 懒加载)。