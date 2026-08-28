---
date: 2026-07-06
symptom: [websocket, control-message, routing, agent_id, channels-group, pk-vs-business-id, silent-drop]
solution: Include agent_id in all control message payloads (start AND stop); use Agent.agent_id string (not DB pk) for Channels group routing.
diff_keywords: ["consumers", "usescreenshotstream", "executionmonitorpanel", "websocket", "control-message", "routing", "agent_id", "channels-group", "pk-vs-business-id", "silent-drop"]
related_files:
  - backend/protocol/consumers.py
  - frontend/src/hooks/useScreenshotStream.ts
  - frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx
created_by: AI
level: L1
n_id: N148
topic: agent-protocol
---


# N148 — 双向控制消息缺路由标识被静默丢弃 + Channels group 路由混淆

> **登记时间**：2026-07-06
> **发现于**：R37-P3 设备公共方法 + BD2 端到端验证
> **跨引用**：N139 (Vite proxy localhost)、N145 (consumer 上行消息处理)

## Symptom（症状）

R37-P3 浏览器测试中暴露两个相关 bug，根因同属"控制消息路由标识缺失"：

### Bug 1: 停止截图按钮无反应
- **现象**：用户点击"停止截图"按钮，UI 上 `isStreaming` 状态切回 false，但 agent 持续推 screenshot.frame 帧，截图画面继续刷新
- **诊断**：[backend/protocol/consumers.py:1417](file:///D:/code/AUTO_PROJECTS/GAF/backend/protocol/consumers.py#L1417) FrontendConsumer 的 stop_screenshot_stream 处理用 `elif msg_type == "stop_screenshot_stream" and agent_id:` 守卫，agent_id 为空时**静默丢弃**（无日志、无 error frame）
- **根因**：[useScreenshotStream.ts:88](file:///D:/code/AUTO_PROJECTS/GAF/frontend/src/hooks/useScreenshotStream.ts#L88) `stopStream` 发的 payload 是 `{}`，**没把 `agent_id` 字段放进去**。`startStream` 接受 `agentId` 参数并放进 payload 所以能成功；`stopStream` 没参数所以漏了

### Bug 2: ExecutionMonitorPanel 截图流卡在"等待截图数据"
- **现象**：BD2 execution 跑起来后，日志终端正常显示 task.progress/task.result，但截图区一直显示"等待截图数据"
- **诊断**：agent 日志显示截图持续推送（screenshot.frame seq=N, 532KB, 发送成功），但前端没收到
- **根因**：[index.tsx:252](file:///D:/code/AUTO_PROJECTS/GAF/frontend/src/pages/Executions/index.tsx#L252) `setMonitoringAgentId(record.agent ? String(record.agent) : undefined)` 把**DB 主键**（int 4）当成了 agent_id string。但 Channels group name 是 `agent_{Agent.agent_id}`（string `td010-repro-agent`），见 [consumers.py:208](file:///D:/code/AUTO_PROJECTS/GAF/backend/protocol/consumers.py#L208)。前端用 `"4"` 订阅，backend 路由到 group `agent_4` —— 没有任何 agent 加入过这个 group，消息全部丢失

## Root Cause（深度根因）

### 直接根因
1. **Bug 1**: `stopStream` 的 payload 构造遗漏了 `agent_id` 字段
2. **Bug 2**: TaskExecutionSerializer 只暴露 `agent`（DB pk int），没暴露 `agent_identifier`（Agent.agent_id string），前端被迫用 DB pk 做路由

### 架构反模式（深层根因）
**「双向控制消息」缺少显式的路由契约**：
- 上行（前端→backend→agent）：`request_screenshot_stream` / `stop_screenshot_stream` 都需要 `agent_id` 才能路由到 `agent_{agent_id}` group
- 但 hook API 设计成 `startStream(agentId)` / `stopStream()` —— `stopStream` 无参数，让开发者很容易忘记保留 agent_id
- 后端守卫用 `and agent_id` 静默丢弃，没有 error frame 也没 warning log，让 bug 不可观测

**「DB 主键 vs 业务标识符」混淆**：
- Agent 表有 DB 自动主键 `id` (int) 和业务字段 `agent_id` (string)
- Channels group name 用业务字段 `agent_td010-repro-agent`
- 但 TaskExecution.agent 是 FK 到 Agent.id（DB pk）
- 序列化层没显式暴露 `agent_identifier` 字段，前端只能拿到 DB pk，被迫猜测哪个是路由标识

## Fix（修复）

### Bug 1: stop_screenshot_stream 补 agent_id
[useScreenshotStream.ts](file:///D:/code/AUTO_PROJECTS/GAF/frontend/src/hooks/useScreenshotStream.ts)：用 `useRef<string | null>` 在 `startStream` 时记录 agent_id，`stopStream` 时取出放进 payload

```typescript
const activeAgentIdRef = useRef<string | null>(null);

const startStream = useCallback((agentId: string, deviceIds?: string[]) => {
  activeAgentIdRef.current = agentId;
  // ... existing send logic
}, []);

const stopStream = useCallback(() => {
  const agentId = activeAgentIdRef.current;
  if (agentId) {
    wsClient.send('stop_screenshot_stream', { agent_id: agentId });
  } else {
    wsClient.send('stop_screenshot_stream', {});
  }
  activeAgentIdRef.current = null;
  setIsStreaming(false);
}, []);
```

### Bug 2: 后端暴露 agent_identifier，前端用它做路由
- backend `TaskExecutionSerializer` 加 `agent_identifier = SerializerMethodField(read_only=True)`，返回 `obj.agent.agent_id` string
- frontend `TaskExecution` type 加 `agent_identifier: string | null`
- `handleStartMonitoring` 改用 `record.agent_identifier ?? undefined`

## Prevention（预防 — Y/N 检查清单）

### Y/N 矩阵（写入 yn-matrices.md）

**§3 双向控制消息路由** — 写任何 frontend→backend→agent 的双向控制消息时必跑：
- [ ] **Y**: 上行消息（start/request/subscribe）和下行消息（stop/unsubscribe/cancel）**都**包含 `agent_id` 路由字段？
- [ ] **Y**: hook 的 stop/unsubscribe API 即使无参数，也通过 ref/state 保留路由标识？
- [ ] **N**: 后端守卫是否用 `and agent_id` 静默丢弃空值？（应改为：log warning + 返回 error frame）

**§3 ORM 主键 vs 业务标识符** — 涉及 Channels group / 任何字符串路由标识时必跑：
- [ ] **Y**: serializer 显式暴露业务标识符字段（如 `agent_identifier`）给前端？
- [ ] **N**: 前端用 `record.agent`（DB pk）做路由？（必须用业务标识符）
- [ ] **Y**: 注释明确区分 FK 字段（DB pk）和路由字段（业务 string）？

### 防御性编程模式

```typescript
// ❌ 反模式：stopStream 无参数，依赖后端"知道"当前 active 的 agent
const stopStream = useCallback(() => {
  wsClient.send('stop_screenshot_stream', {});  // agent_id 丢失
  setIsStreaming(false);
}, []);

// ✅ 正确：ref 保留状态，stop 时主动传递
const stopStream = useCallback(() => {
  const agentId = activeAgentIdRef.current;  // 从 ref 取
  wsClient.send('stop_screenshot_stream', { agent_id: agentId });  // 显式路由
  activeAgentIdRef.current = null;
  setIsStreaming(false);
}, []);
```

## Related Files（相关文件）

- frontend: [useScreenshotStream.ts](file:///D:/code/AUTO_PROJECTS/GAF/frontend/src/hooks/useScreenshotStream.ts), [Executions/index.tsx](file:///D:/code/AUTO_PROJECTS/GAF/frontend/src/pages/Executions/index.tsx), [types/models.ts](file:///D:/code/AUTO_PROJECTS/GAF/frontend/src/types/models.ts)
- backend: [protocol/consumers.py](file:///D:/code/AUTO_PROJECTS/GAF/backend/protocol/consumers.py) (FrontendConsumer.receive), [tasks/serializers.py](file:///D:/code/AUTO_PROJECTS/GAF/backend/tasks/serializers.py) (TaskExecutionSerializer.get_agent_identifier), [agents/models.py](file:///D:/code/AUTO_PROJECTS/GAF/backend/agents/models.py) (Agent.agent_id string field)
- evidence: [test_device_ops_playwright.py](file:///D:/code/AUTO_PROJECTS/GAF/.trash/test_device_ops_playwright.py), [verify_execution_monitor_fixed.py](file:///D:/code/AUTO_PROJECTS/GAF/.trash/verify_execution_monitor_fixed.py)

## Verification（3 步 evidence）

### Problem
- Execution 60/61: 截图区"等待截图数据"，agent 持续推帧但前端收不到
- 停止截图按钮点击后无反应，agent 继续推帧

### Solution
- commit `-`: stopStream 补 agent_id + DeviceOperationPanel 改用 App.useApp()
- commit `-`: TaskExecutionSerializer 暴露 agent_identifier，前端用它做路由

### Verification
- Execution 63 status=success
- 截图流 "screenshot stream is showing content"（不再"等待截图数据"）
- 停止截图按钮点击后切换为"开始截图"按钮（状态正确）
- 无 console error，无 antd warning
