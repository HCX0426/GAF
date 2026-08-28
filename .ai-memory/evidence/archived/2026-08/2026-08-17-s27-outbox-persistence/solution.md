---
maintainer: manual
source: GAF session 2026-08-17
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: 崩溃后帧丢失
solution: OutboxStore (sqlite3 单表 id/msg_type/data/created_at); send_message 加 _enqueue_on_failure 内部参数 (flush 传 False 防重复行); flush 成功帧累计 sent_count 后 delete_first_n; store 打开失败降级内存模式
related_files:
  - agent/src/client/outbox_store.py
  - agent/src/client/connection.py