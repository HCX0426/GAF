---
spec_id: spec-2026-08-17-s27-outbox-persistence
title: P3 — 出站队列跨进程持久化 (outbox SQLite)
status: ✅ 已归档 (commit -, 2026-08-17)
created: 2026-08-17
task_type: refactor
applies_to: [agent]
---

# P3 — 出站队列跨进程持久化 (outbox SQLite)

> 来源: S1 spec (-) 已知限制 "出站队列仅内存（进程崩溃即丢失），跨进程持久化后续排期"。用户授权"按优先级来"（2026-08-17），P3 = 持久化。
>
> **范围**: agent `AgentConnection._outbox` 目前是内存 `deque(maxlen=50)`，进程崩溃/重启即丢失，断线期间积压的 task.result 随进程一起消失。本 spec 引入 SQLite 持久化存储，启动时恢复、入队即落盘、flush 成功后删除 — 把"断线不丢"升级为"崩溃也不丢"。

## N151 5 步法评估

1. **架构盘点**: `AgentConnection._outbox` (agent/src/client/connection.py:176) 内存 deque; `_enqueue_outbox` (:367) 断线入队; `_flush_outbox` (:389) 重连后 FIFO 重放; backend 侧 `update_task_execution_result` 已有终态守卫 (S1 P2, SUCCESS/FAILED 拒绝覆盖) → 重复发送安全; agent 已有文件存储先例 (auth/token_store.py Fernet 加密, core/offline_cache.py)
2. **识别反模式**: R1 自造文件格式 (JSONL 无事务、断电半行风险、需自实现恢复); R2 引入外部依赖 (Redis 队列 — agent 无 Redis 依赖, 复杂度 + 部署成本); R3 改动现有 deque 语义 (保持内存结构, 加持久化旁路)
3. **备选方案**: A) SQLite 持久化 (新组件 `outbox_store.py`: 单文件、事务安全、WAL 崩溃恢复、Python 内置 sqlite3 零新依赖; 入队 INSERT, flush 成功后批量 DELETE); B) JSONL append 文件 (简单但无事务, 断电半行风险, 需自实现恢复逻辑); C) Redis 队列 (引入外部服务依赖, agent 已不依赖 Redis)
4. **拒绝反模式**: 拒绝 B (无事务/半行风险)、C (外部依赖); 选 A SQLite。flush 中 send 失败时帧回内存不再重复写 DB (send_message 加 `_enqueue_on_failure` 内部参数, flush 传 False)
5. **AI 自决边界**: 默认无 store 时行为不变 (兼容现有 8 个 outbox 测试); store 路径由调用方传入 (测试用 tmp_path); DB 行含 id, flush 成功后按成功帧数 `delete_first_n`; 重复发送安全 (backend 终态守卫 + task.progress 无害)

## N167 七维度评分（方案 A）

- **架构长远性**: SQLite 标准嵌入式存储, 后续可扩展其他持久化 (event 队列等) — 4
- **全局归一化**: 复用 stdlib sqlite3, 无新依赖; 与 token_store 同属 agent 本地文件存储模式 — 4
- **新旧兼容**: 无 store (默认) 时行为完全不变; 有 store 时仅增加持久化, deque 语义不变 — 4
- **现有业务完善**: 直接补 S1 已知限制, 崩溃后 task.result 不再丢失 — 4
- **性能资源优化**: 入队低频 (仅断线期间), 每次 1 INSERT 可接受; flush 成功后批量 DELETE — 3
- **安全合规加固**: 本地文件, payload 无凭据/敏感数据 (task.result/progress 执行数据) — 3
- **长期维护成本**: 单组件 + 单测试文件, 逻辑正交于 connection 主链路 — 4
- **总分**: 26 (B: JSONL 半行风险 21; C: Redis 依赖 18) → 领先 ≥ 5 → AI 自决方案 A

## 阶段状态表

| 阶段 | 内容 | 状态 | 完成时间 | commit hash |
|------|------|------|---------|-------------|
| P1 | `outbox_store.py` OutboxStore 组件 (CREATE/INSERT/SELECT/delete_first_n) | ✅ | 2026-08-17 | - |
| P2 | `AgentConnection` 集成 (启动恢复 + 入队落盘 + flush 删除 + `_enqueue_on_failure`) | ✅ | 2026-08-17 | - |
| P3 | 测试 (持久化单元 + 集成 + 崩溃恢复) + 文档同步 | ✅ | 2026-08-17 | - |

## 任务清单

### P1: OutboxStore 组件

- [x] `agent/src/client/outbox_store.py` 新建 `OutboxStore`:
  - `__init__(db_path: str | Path)` — `sqlite3.connect` + `CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, msg_type TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL)`
  - `enqueue(msg_type, data)` — INSERT (data = json.dumps(ensure_ascii=False))
  - `load_all() -> list[tuple[str, dict]]` — SELECT ORDER BY id ASC (FIFO)
  - `delete_first_n(n: int)` — DELETE WHERE id IN (SELECT id ... LIMIT n) (flush 成功后按成功帧数删)
  - `count() -> int` / `__len__`
  - 连接异常 (磁盘满/权限) → 捕获并 logger 降级 (不阻塞主链路)

### P2: AgentConnection 集成

- [x] `connection.py`:
  - `__init__(..., outbox_store: OutboxStore | None = None)`; 有 store 时启动 `load_all()` 灌入 `self._outbox` (倒序 append 保 FIFO)
  - `_enqueue_outbox(msg_type, data, persist=True)` — 有 store 且 persist 时同时 `store.enqueue`; 容量满丢弃最旧帧时同步 `delete_first_n(1)` (最旧)
  - `send_message(msg_type, data, _enqueue_on_failure: bool = True)` — 内部参数, flush 传 False
  - `_flush_outbox` — 逐条 send 成功后累计 `sent_count`; 全部结束 (或中断) 后 `store.delete_first_n(sent_count)`; 中断重入队仅内存 (DB 行保留)
  - 现有无 store 行为零变化

### P3: 测试 + 文档

- [x] `agent/tests/test_outbox_store.py` 新建:
  - enqueue → load_all FIFO / 顺序一致
  - delete_first_n 部分删除 / 全部删除 / 超量安全
  - 崩溃恢复: 新 OutboxStore 打开同一 db → load_all 返回旧帧
  - 损坏文件 (写入垃圾字节) → 打开不崩 (捕获 sqlite3.DatabaseError)
- [x] `agent/tests/test_outbox_and_dispatch_ack.py` 集成:
  - store 注入: enqueue 落盘 + load 恢复
  - flush 成功 → store.count() == 0
  - flush 中断 → store.count() 保留剩余帧 (不重复写)
  - 无 store 时原有 8 测试全部通过
- [x] 文档: `docs/architecture/cross-cutting/dispatch-flow.md` §1.8 补持久化语义

## 验收标准

1. 无 store 注入: 现有 outbox 测试全部通过 (行为零变化)
2. 有 store: enqueue 落盘, 新连接 (模拟崩溃) 打开同 db 恢复 FIFO
3. flush 成功后 store 清空; 中断时剩余帧保留在 store
4. `agent/tests/test_outbox_store.py` + `test_outbox_and_dispatch_ack.py` 全绿
archived_to: docs/specs/archived/2026-08/2026-08-17-s27-outbox-persistence.md
