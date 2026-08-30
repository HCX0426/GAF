---
maintainer: derived-manual
source: backend/protocol/routing.py, worker/src/client/connection.py, backend/tasks/webhook.py
load_when:
- 新功能 (前后端数据流)
- Bug修复 (WebSocket 断连/REST 404)
- AI 任务开工
priority: high
symptom:
- kb:data:chain
- rest-ws-sync
- data-flow
- 数据链路
- WebSocket
solution: 3 链路 (REST CRUD / WS 实时 / Webhook 回调) + 4 转换节点 + 5 AI 易错点
related_files:
- backend/protocol/routing.py
- backend/protocol/consumers.py
- worker/src/client/connection.py
- worker/src/client/handler.py
- .ai-memory/meta/auto-kb/agent-protocol.md
- .ai-memory/meta/auto-kb/api-endpoints.md
created_by: AI
generated: 2026-06-16
auto_updated: 2026-06-16
last_manual_edit: 2026-07-20
---
# Data Chain (数据链路) - AI 速查

> **适用场景**: AI 调试前后端数据不一致 / WebSocket 断连 / 状态不同步
> **核心架构**: REST CRUD (持久化) + WebSocket (实时) + Webhook (回调) 三链路

## 1. 三链路架构

```
┌─────────┐                    ┌─────────┐
│Frontend │                    │ Backend │
│ (React) │                    │ (Django)│
└────┬────┘                    └────┬────┘
     │                              │
     │ ① REST CRUD                  │ ③ Webhook
     │ (持久化操作)                  │ (任务完成回调)
     │                              │
     ├─────── HTTP ────────────────►│
     │◄────── 200/201 ─────────────┤
     │                              │
     │ ② WebSocket (实时)            │
     │                              │
     ├─────── WS ──────────────────►│
     │◄────── events ──────────────┤
     │                              │
     ▼                              ▼
┌─────────┐                    ┌─────────┐
│  WS     │                    │  Agent  │
│ Client  │                    │ (Python)│
└─────────┘                    └─────────┘
```

### 1.1 链路 ①: REST CRUD (持久化)

**用途**: 任务创建/更新/删除, 设备配置, 用户管理
**客户端**: `frontend API client files` (axios 封装)
**后端**: `backend/<app>/views.py` (DRF ViewSet)
**协议**: HTTP + JSON, 状态码 (200/201/400/404/500)
**特点**:
- ✅ 持久化, 有 history
- ❌ 客户端必须主动拉取 (轮询)
- 适用: 不需要实时的操作 (CRUD)

**例子**:
```typescript
// frontend/src/api/tasks.ts
const createTask = (data: TaskCreate) =>
  api.post<{ id: number }>('/api/tasks/tasks/', data)
```

### 1.2 链路 ②: WebSocket (实时)

**用途**: 设备状态推送, 任务进度更新, 日志流
**客户端**: `frontend/src/hooks/useWebSocket.ts`
**后端**: `backend/protocol/consumers.py` (Channels)
**协议**: WS + JSON frame
**特点**:
- ✅ 实时推送, 客户端无需轮询
- ❌ 无持久化, 重连后丢失中间事件
- 适用: 状态变化, 实时日志

**消息帧格式**:
```json
{
  "type": "device.status_changed",
  "device_id": "device-001",
  "status": "running",
  "timestamp": 1718438400,
  "data": { "task_id": 42 }
}
```

**易错点**: 见 `agent-protocol.md` 的 5 维约束

### 1.3 链路 ③: Webhook (回调)

**用途**: 任务完成通知外部系统, AI 异步结果回调
**客户端**: 外部系统 (用户配置 URL)
**后端**: `tasks webhook (未实现)`
**协议**: HTTP POST + HMAC 签名
**特点**:
- ✅ 异步, 不阻塞任务
- ❌ 需要重试机制 (网络失败)
- 适用: 任务完成异步通知

**签名验证**:
```python
# tasks webhook (未实现)
def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
```

## 2. 4 个转换节点

### 2.1 REST → WS 转换 (后端内部)

**触发**: REST API 修改 DB → 触发 WS 推送
**实现**: Django signal → consumer group_send
**位置**: `backend/<app>/signals.py` + `consumers.py`

```python
# backend/tasks/signals.py
@receiver(post_save, sender=Task)
def task_saved(sender, instance, created, **kwargs):
    channel_layer.group_send(
        'tasks',
        {
            'type': 'task.update',
            'task_id': instance.id,
            'status': instance.status,
        }
    )
```

### 2.2 WS → Agent 推送

**触发**: 后端 → Agent 发送指令 (启动任务/暂停/取消)
**实现**: `worker/src/client/handler.py` 接收 WS 消息
**协议**: `agent-protocol.md` 定义的 frame

### 2.3 Agent → 后端 报告

**触发**: Agent 完成任务/失败/进度更新
**实现**: `worker/src/client/connection.py` 发送消息
**协议**: 同上, 反向

### 2.4 后端 → Webhook 回调

**触发**: 任务终态 (SUCCESS/FAILED/TIMEOUT)
**实现**: Celery task `webhook.send_callback.delay(...)`

## 3. 5 个 AI 易错点 (历史教训)

### 3.1 ❌ REST 修改后忘了触发 WS (N40)

**错误**: ViewSet 里 `task.save()`, 但没发 WS 推送
**后果**: 前端看不到状态变化, 需手动刷新
**正确**: 用 Django signal 自动触发, 或在 `services.py` 显式 `channel_layer.group_send()`

### 3.2 ❌ WS 断连不重试 (N41)

**错误**: 客户端 `ws.onclose = () => {}` 不重连
**后果**: 网络抖动后永远断连, 用户必须刷新
**正确**: 指数退避重连 (`useWebSocket.ts` 已实现)

### 3.3 ❌ Webhook 失败不重试 (N42)

**错误**: `requests.post(webhook_url, json=data)` 失败就丢
**后果**: 任务完成通知丢失, 外部系统状态不一致
**正确**: Celery task + retry policy (`max_retries=3, retry_backoff=True`)

### 3.4 ❌ 状态不同步 (REST 已改, WS 还在推旧值) (N43)

**错误**: 两个地方改 `task.status`, 顺序不一致
**后果**: 前端看到状态回滚
**正确**: 单一 source of truth (DB), 改完 DB 再发 WS, 客户端以最新 WS 为准

### 3.5 ❌ REST 404 但 WS 还在 (N44)

**错误**: 任务被删, 但 WS 还推 `task.update` 事件
**后果**: 前端收到幽灵任务
**正确**: 删除任务时显式发 `task.deleted` 事件, 前端订阅并清空

## 4. 速查表 (Cheatsheet)

| 场景 | 用 REST | 用 WS | 用 Webhook |
|------|:-------:|:----:|:----------:|
| 创建设备 | ✅ | ❌ | ❌ |
| 设备状态变化 | ❌ | ✅ | ❌ |
| 任务进度 50% | ❌ | ✅ | ❌ |
| 任务完成 100% | ⚠️ 标终态 | ⚠️ 推事件 | ✅ 外部通知 |
| 用户登录 | ✅ | ❌ | ❌ |
| 实时日志流 | ❌ | ✅ | ❌ |
| AI 异常发现 | ⚠️ 存 DB | ✅ 弹窗 | ❌ |

## 5. 反思 (Reflection)

- **三链路各有分工**: REST 持久化, WS 实时, Webhook 异步回调
- **数据一致性**: 改 DB 后必须推 WS, 否则前端看不到
- **失败兜底**: WS 断连重试, Webhook 失败重试, REST 5xx 重试
- **相关**: agent-protocol.md (WS 协议细节) / api-endpoints.md (REST 路由表)
