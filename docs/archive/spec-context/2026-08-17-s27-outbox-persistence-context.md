# spec-context: 2026-08-17-s27-outbox-persistence

> 承载体: spec-2026-08-17-s27-outbox-persistence
> 关联: docs/specs/archived/2026-08/2026-08-17-s27-outbox-persistence.md

## 1. 用户决策原文

- 用户 2026-08-17: "你按优先级来吧" (自决排序授权, §3.6) — P3 = 出站队列跨进程持久化
- S1 spec 已知限制: "出站队列仅内存（进程崩溃即丢失），跨进程持久化后续排期"

## 2. N151 5 步法评估过程

1. **架构盘点**: `AgentConnection._outbox` (agent/src/client/connection.py:176) 内存 deque(maxlen=50);
   `_enqueue_outbox` (:367) 断线入队; `_flush_outbox` (:389) 重连后 FIFO 重放;
   backend `update_task_execution_result` 终态守卫 (S1 P2) → 重复发送安全;
   agent 已有文件存储先例 (token_store.py / offline_cache.py)
2. **识别反模式**: R1 自造文件格式 (JSONL 无事务/半行风险); R2 引入外部依赖 (Redis);
   R3 改动现有 deque 语义 (应保持内存结构 + 持久化旁路)
3. **A/B/C 备选**: A) SQLite (新组件 outbox_store.py: 事务安全/WAL 崩溃恢复/内置 sqlite3 零依赖);
   B) JSONL append; C) Redis 队列
4. **拒绝反模式**: 拒绝 B (无事务)、C (外部依赖); 选 A
5. **AI 自决边界**: 默认无 store 行为零变化; store 路径由调用方传入 (测试用 tmp_path);
   flush 中 send 失败 → 帧回内存不再重复写 DB (send_message 加 `_enqueue_on_failure` 内部参数);
   delete_first_n 按成功帧数删

## 3. N167 七维度评分细节

| 维度 | 评分 | 说明 |
|------|------|------|
| 1 架构长远性 | 4 | SQLite 标准嵌入式存储, 后续可扩展 |
| 2 全局归一化 | 4 | 复用 stdlib sqlite3, 与 token_store 同模式 |
| 3 新旧兼容 | 4 | 无 store (默认) 行为完全不变 |
| 4 现有业务完善 | 4 | 补 S1 已知限制, 崩溃后 task.result 不丢失 |
| 5 性能资源优化 | 3 | 入队低频 (仅断线), 1 INSERT/帧可接受 |
| 6 安全合规加固 | 3 | payload 无凭据/敏感数据 |
| 7 长期维护成本 | 4 | 单组件 + 单测试文件 |
| **总分** | **26** | B: 21, C: 18 → 领先 ≥ 5 → AI 自决方案 A |

## 4. 关键实施决策

- `OutboxStore._connect` 失败 (磁盘满/权限/损坏) → 捕获降级内存模式, 不阻塞主链路
- 启动恢复: `load_all()` 按 id ASC 灌入 deque (FIFO)
- `_enqueue_outbox` 容量满丢弃最旧帧时同步 `delete_first_n(1)` 保证内存与磁盘一致
- `_flush_outbox` 逐条 send 成功后累计 sent_count, 结束/中断后 delete_first_n(sent_count);
  中断重新入队仅内存 (persist=False, store 行保留)
- 损坏帧 (json.loads 失败) → 跳过并 log, 不崩
- 现有测试 `_fake_send(msg_type, data)` 需加 `_enqueue_on_failure=True` 参数兼容新签名

## N173 用时字段

- `start_ts`: 2026-08-17T20:05:00+08:00
- `end_ts`: 2026-08-17T20:40:00+08:00
- `duration_min`: 35
- `within_baseline`: true
- `root_cause_if_over`: 大修改基线 < 60min 内; 含 agent 全量回归 2305 tests 3min