---
date: 2026-06-14
symptom: [agent:message:frame, 消息, 格式, frame-error, ws-protocol]
solution: 统一 4 字节长度前缀 + JSON body
related_files:
  - backend/protocol/constants.py
  - backend/protocol/consumers.py
  - worker/src/client/handler.py
created_by: AI
priority: high
diff_keywords: ["websocket", "frame", "message", "ws-protocol"]
---

# WebSocket 消息帧解析失败

## 症状

Agent 与 Backend 通信时，WebSocket 偶发"消息帧格式错误"日志，连接断开重连。

## 触发条件

- 消息体包含 UTF-8 多字节字符
- 大消息（> 4KB）
- 高频消息（> 100 msg/s）

## 根因

前后端消息帧格式不一致：后端用 4 字节长度前缀 + JSON，Agent 端用换行符分隔 JSON。

## 解决步骤

1. 后端：`backend/protocol/constants.py` 定义 `MSG_HEADER_SIZE = 4`
2. Agent：`worker/src/client/handler.py` 改为 `struct.unpack('>I', header)[0]` 解析
3. 加 `protocol_version` 字段，握手时校验

## 验证

- 发送 1000 条含中文的消息，0 错误
- Wireshark 抓包：每条消息都是 4 字节长度 + UTF-8 JSON

## 预防

- 协议版本不匹配 → 立即断开
- 任何协议变更必须同步更新 `constants.py` + `handler.py` + 测试
