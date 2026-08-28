---
maintainer: manual
source: GAF session 2026-08-17
load_when: [evidence, 3-step-evidence, 反思]
priority: high
symptom: S1 已知限制: agent 出站队列仅内存 (进程崩溃即丢失), 断线积压的 task.result 随进程消失 → backend 永久 RUNNING
solution: 可选 SQLite 旁路存储 outbox_store.py — 入队 INSERT 落盘, 启动 load_all 恢复 FIFO, flush 成功 delete_first_n; 不注入 store 时行为零变化
related_files:
  - agent/src/client/outbox_store.py
  - agent/src/client/connection.py