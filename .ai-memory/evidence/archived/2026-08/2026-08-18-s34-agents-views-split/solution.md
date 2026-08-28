---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-18-s34-agents-views-split/
load_when: [evidence, 3-step-evidence, s34, views-split]
priority: high
symptom: [拆分方案落地, view_sets 包, re-export 兼容层]
solution: AST 精确边界拆分 + re-export + __all__ + 预存错误修复
related_files:
  - .trash/s34_split_views.py
  - backend/agents/views.py
  - backend/agents/view_sets/
created_by: AI
last_updated: 2026-08-18
---
## Solution（解决步骤）

1. 用 AST (git show HEAD 版本) 提取 20 个顶层定义的精确行边界 (end = 下一顶层节点 lineno - 1), 按 8 功能域分组生成 `backend/agents/view_sets/` 包 8 模块 (crud/scan_register/capture/lock_stats/capability/input/recognition/app_info)。
2. `backend/agents/views.py` 重写为 re-export 兼容层 (42 行, 19+1 符号 + `__all__`), 引用方零改动 (agents/urls.py, monitors/views.py:780, agent_runtime.py:436 均验证)。
3. 修复拆分脚本 3 个 bug: header pop(0)→pop() (尾部空行误删头部), docstring 完整剥离, services import 块上移到 import 区 (E402)。
4. 包名用 view_sets/ 而非 views/ (同名模块冲突 ImportError)。
5. 4 处预存空 except (防御性解析容错) 补 logger.debug 日志 (gaf-code-rules R001 修复)。