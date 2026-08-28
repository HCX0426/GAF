---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:td396, agent掉线, backend冻结, GIL, RAG索引]
solution: Solution 记录 TD-396 修复步骤
related_files:
  - backend/gaf_ai/rag.py
  - backend/gaf_ai/apps.py
  - backend/gaf_ai/tasks_rag.py
  - backend/gaf_ai/tests/test_llm.py
created_by: AI
last_updated: 2026-08-26
---
## Solution（解决步骤）

1. `backend/gaf_ai/apps.py`：AppConfig.ready() 启动 daemon 线程 `warmup_rag_retriever()` 预热 ONNX 模型，把首次数十秒 GIL 加载挪出请求/Beat 线程
2. `backend/gaf_ai/rag.py`：`get_rag_retriever` 双检锁线程安全单例；`_flush_batch` 增量 diff（metadata 存 content_hash）+ 64 条/批批量 upsert（一次 batched ONNX 推理）
3. `backend/gaf_ai/rag.py`：symbol doc_id 加行号 `{name}:{lineno}` + `_flush_batch` 前置去重（last-wins），杜绝 DuplicateIDError 触发全量回退
4. `backend/gaf_ai/tests/test_llm.py`：FakeChromaCollection 补 get/upsert；新增 `test_reindex_same_content_is_no_op` / `test_reindex_only_changed_files`
5. 运行验证：重启服务后 HTTP 持续观测，第二 tick 起稳态 6ms 基线