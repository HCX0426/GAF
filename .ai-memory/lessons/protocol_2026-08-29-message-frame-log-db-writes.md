---
date: 2026-08-29
symptom: [message-frame-log-empty, synchronousonlyoperation, transactionmanagementerror-async-db, test-logs-pollute-service-errors]
solution: async consumer DB 写入用 sync_to_async(thread_sensitive=False) 独立连接; payload 过 JSON round-trip; FK 用 PK; 测试 settings 用 NullHandler 禁写生产 debug 目录
related_files:
  - backend/protocol/consumers.py
  - backend/config/settings/test.py
  - scripts/services/health.py
created_by: AI
priority: high
n_id: null
diff_keywords: ["database_sync_to_async", "thread_sensitive", "MessageFrameLog", "SynchronousOnlyOperation", "NullHandler", "LOGGING", "消息帧日志"]
---

# 消息帧日志 DB 写入三坑 + 测试日志污染服务报错 (2026-08-29)

## 症状

日志中心"消息帧日志"tab 恒空 + 服务管理大量报错。排查链(M3 diff 触发):
1. 帧日志 inbound 0 条, 看到 `消息处理器异常: type=agent.heartbeat`
2. 服务管理 backend 34 条报错 (TMError + `OSError: disk full`)

## 根因

**坑 A — async consumer 裸同步 ORM**: 在 `AgentConsumer.receive/send` (async 上下文)
直接 `MessageFrameLog.objects.create()` → `SynchronousOnlyOperation: You cannot call
this from an async context`。

**坑 B — database_sync_to_async 同线程冲突**: `database_sync_to_async` (thread_sensitive=True)
把 DB 写到主线程, 与 heartbeat 等处理器**主线程同步 DB 访问**
(update_agent_heartbeat) 在 SQLite + async 下并发 → `TransactionManagementError`,
连锁把 heartbeat handler 打崩 (真正的"消息处理器异常"来源)。

**坑 C — FK 误传 UUID**: `_agent_session_id` 是 AgentSession.agent_id (UUID),
直接当 `agent_session_id` (PK int) 传 → `Field 'id' expected a number`。

**坑 D — 测试日志污染**: pytest 用 dev 继承的 LOGGING (`database`=FileLogHandler)
把 mock 异常/测试期错误写进生产 `debug/YYYYMMDD/backend/system/`,
daemon 报错扫描当成"服务报错" → 服务管理页计数被测试污染
(实测: `OSError: disk full`(mock) / heartbeat TMError 均来自测试运行)。

## 解法

```python
# 坑 A/B: async consumer DB 写 → sync_to_async(thread_sensitive=False)
# 独立线程 + 独立连接, 既过 async 安全检查, 又不碰主线程事务
await sync_to_async(_create_frame_log, thread_sensitive=False)(...)

# 坑 C: FK 传解析后的 PK 实例, 不是 UUID
session = AgentSession.objects.filter(agent_id=agent_id).first()
MessageFrameLog.objects.create(..., agent_session=session)

# 坑 D: test.py 禁用文件日志
LOGGING["handlers"]["database"] = {"class": "logging.NullHandler"}

# 附: payload 含 UUID/datetime 无法入 JSONField → json.dumps(default=str) round-trip
```

## 适用范围

- 任何 Channels async consumer 里的 DB 写入: 必须 `sync_to_async`/`database_sync_to_async`,
  优先 `thread_sensitive=False` 隔离连接
- JSONField 存自带对象时先 JSON round-trip
- pytest 环境必须隔离日志输出 (测试 settings 覆盖 LOGGING), 否则污染生产 debug 目录
  与服务健康监控 (daemon scan_log_errors / /logs/files/)