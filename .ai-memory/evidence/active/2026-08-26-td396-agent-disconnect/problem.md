---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:td396, agent掉线, backend冻结, GIL, RAG索引]
solution: Problem 记录 TD-396 agent 掉线最终根因（已修复）
related_files:
  - backend/gaf_ai/rag.py
  - backend/gaf_ai/apps.py
  - docs/archive/active-tech-debt.md
created_by: AI
last_updated: 2026-08-26
---
## Problem（症状 / 触发条件）

agent 执行完成后偶发掉线 + backend 假死：agent WebSocket 断开重连超时、HTTP 连接被悬挂，进程存活但 py-spy 全 idle。触发条件：dev eager 模式下 `auto_index_rag` 每 5 分钟在 daphne 进程内全量重索引（245 个 Python 文件）。

最终根因两层：① fastembed ONNX embedding 推理（C 扩展）持 GIL 数十秒冻结 daphne event loop；② `ast.walk` 对同名函数/方法生成重复 doc_id → ChromaDB `get()/upsert()` 抛 DuplicateIDError → diff 降级全量回退，且含重复 id 的批次整批失败 → 每个 tick 都冻结一次。