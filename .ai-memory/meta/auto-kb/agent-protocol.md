---
maintainer: auto
source: backend/protocol/constants.py, backend/protocol/schemas.py, backend/protocol/consumers.py
load_when:
- 任务执行
- Bug修复
priority: high
symptom:
- kb:agent:protocol
- WebSocket-message
- message-frame
- task-state-machine
- agent-to-server
- server-to-agent
solution: 16 种消息类型 + 5 字段帧 + TaskState 6 状态机 + 心跳 30s/15s 阈值
related_files:
- backend/protocol/constants.py
- backend/protocol/schemas.py
- backend/protocol/consumers.py
- backend/protocol/quota.py
- backend/protocol/middleware.py
- backend/protocol/routing.py
- agent/src/client/connection.py
- agent/src/client/handler.py
created_by: AI
generated: 2026-06-16
auto_updated: 2026-07-18
---

        # Auto-generated knowledge entry

        <!-- source: backend/protocol/constants.py, backend/protocol/schemas.py, backend/protocol/consumers.py -->
        <!-- generated: 2026-08-29 -->

        ## Symptom

        kb:agent:protocol, WebSocket-message, message-frame, task-state-machine, agent-to-server, server-to-agent

        ## Solution

        16 种消息类型 + 5 字段帧 + TaskState 6 状态机 + 心跳 30s/15s 阈值

        ## Related files

        - `backend/protocol/constants.py`
- `backend/protocol/schemas.py`
- `backend/protocol/consumers.py`
- `backend/protocol/quota.py`
- `backend/protocol/middleware.py`
- `backend/protocol/routing.py`
- `agent/src/client/connection.py`
- `agent/src/client/handler.py`

        <!-- end of auto-generated section -->
