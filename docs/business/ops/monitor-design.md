---
summary: GAF 监控系统设计
applies_to: ['backend', 'design']
key_decisions:
  - 概述
  - Phase 1 监控启用：MonitorManager.start() + 规则热更新通道 + monitor 节点接入 PopupHandler
last_updated: 2026-07-05
---

# GAF 监控系统设计

> 版本：1.2 | 日期：2026-07-05 | 修订：Phase 1 监控启用后状态矩阵更新

## 0. 现实状态（2026-07-05 审计，Phase 1 监控启用后）

> ✅ **Phase 1 监控启用完成**：`MonitorManager.start()` 已在 agent 生命周期中调用，规则热更新通道已接入，monitor PipelineNode 已接入真实 PopupHandler。本节反映 Phase 1 + Phase 6.3 后状态。

| 项 | 文档声称 | 现实代码 | 状态 |
|----|----------|----------|------|
| MonitorThread 守护线程 | 任务执行时启动 | `MonitorThread` 类实现完整 (`agent/src/monitor/manager.py:40-125`) | ✅ 类已实现 |
| MonitorManager 启动 | Agent 启动时 start | `agent/src/__main__.py:272` 调用 `monitor_manager.start()`（Phase 1 commit `-`）。TD-339 (2026-07-23): `__main__.py` 启动入口已加 `acquire_singleton_lock()` PID 文件锁, 防止重复 agent 进程同时运行 MonitorManager 导致监控事件风暴 | ✅ Phase 1 完成 |
| 规则热更新 | Server → Agent 下发 | `agent/src/client/handler.py:418` `handle_monitor_rule_update()` + `agent/src/client/connection.py:408` `"monitor.rule.update"` 通道（Phase 1.9 commit `-`） | ✅ Phase 1.9 完成 |
| 事件上报 | MonitorEvent 持久化 + WebSocket 广播 | Backend `MonitorEvent` 模型 + Celery 升级任务完整 | ✅ 后端已实现 |
| `monitor` PipelineNode | 任务中可插入监控节点 | `engine/nodes/monitor.py` 接入真实 `PopupHandler.check_and_handle()`；`context.monitor_manager` 缺失或 handler 异常时返回 `fail_result` 暴露问题（不静默 Mock 回退，Phase 1 commit `-` + 后续修复） | ✅ Phase 1 完成 |
| PopupHandler / StorySkipper | 弹窗处理 + 剧情跳过 | 类实现完整 (`agent/src/monitor/handlers.py`)；monitor PipelineNode 在 `context.monitor_manager` 存在时调用 PopupHandler；MonitorThread 守护线程循环中也调用规则 `check_condition` / `handle_action` | ✅ Phase 1 启用 |
| `MonitorManager.force_stop_all` | 强制停止所有监控线程 | `agent/src/monitor/manager.py:215-278`（Phase 6.3）；1 秒 join 超时 + 清空规则 | ✅ Phase 6.3 完成 |

### 0.1 当前可用功能

- ✅ Backend `MonitorRule` 模型 CRUD（`/api/v2/monitors/monitor-rules/`）
- ✅ Backend `MonitorEvent` 模型 + 严重等级 + acknowledge
- ✅ Celery 升级任务 `escalate_unhandled_alerts`（P1 30 分钟未确认 → 升级 P0）
- ✅ 系统状态/告警摘要/诊断 API
- ✅ Agent 端 `MonitorManager.start()` 在 agent 启动时调用（Phase 1）
- ✅ Agent 端规则热更新通道（Phase 1.9）
- ✅ monitor PipelineNode 接入真实 PopupHandler（Phase 1）
- ✅ `MonitorManager.force_stop_all()` 强制停止（Phase 6.3）

### 0.2 启用监控的待办（Phase 1 后）

| # | 待办项 | 状态 | 完成提交 |
|---|--------|------|---------|
| 1 | Agent `__main__.py` 调用 `monitor_manager.start()` | ✅ | `-` |
| 2 | Server 端 `AgentConsumer` 添加 `monitor.rule.update` 消息处理 | ✅ | `-` |
| 3 | Agent `MessageHandler` 添加 monitor 规则接收 + `monitor_manager.update_rules()` | ✅ | `-` |
| 4 | `monitor` PipelineNode 接入 `PopupHandler.check_and_handle` | ✅ | `-` |

---

## 1. 概述

GAF 监控系统负责在任务执行期间持续监控设备界面，自动检测和处理弹窗、剧情对话、异常状态等干扰事件。本设计定义监控规则格式、MonitorThread 守护线程、弹窗检测与处理、剧情跳过、事件上报和规则热更新。

> ✅ **Phase 1 监控启用完成**：本节描述的设计已全部在生产路径启用。现实实现见 §0。

---

## 2. 监控规则定义格式

### 2.1 YAML 格式

```yaml
name: popup_handler                # 规则名称
description: "通用弹窗处理"          # 描述
enabled: true                      # 是否启用
priority: 10                       # 优先级（数值越大越优先）
cooldown: 3.0                      # 冷却时间（秒），避免重复触发
max_triggers: 0                    # 最大触发次数（0=无限）

detect:                            # 检测条件
  method: template                 # 检测方法: template/ocr/color/condition
  template: "common/confirm_button.png"  # 模板图片路径
  threshold: 0.85                  # 匹配阈值
  region: null                     # 检测区域 [x, y, w, h]，null=全屏
  pre_delay: 0.5                   # 检测前延迟

action:                            # 处理动作
  type: click                      # 动作类型: click/swipe/press/wait/chain/ignore
  target: "match"                  # 点击目标: match=匹配位置 / 指定坐标 [x,y]
  offset: [0, 0]                   # 点击偏移 [dx, dy]
  post_delay: 1.0                  # 动作后延迟

fallback:                          # 降级处理
  method: ocr                      # 降级检测方法
  text: "确定"                      # OCR 匹配文本
  action:                          # 降级动作
    type: click
    target: "match"
```

### 2.2 规则类型

| 规则类型 | 说明 | 典型场景 |
|----------|------|---------|
| 弹窗处理 | 检测并关闭弹窗 | 更新提示、公告、广告 |
| 剧情跳过 | 自动跳过剧情对话 | 主线剧情、活动剧情 |
| 异常恢复 | 检测异常状态并恢复 | 断线重连、卡死重启 |
| 资源补充 | 检测资源不足并补充 | 体力不足、道具用完 |
| 状态监控 | 持续监控特定状态 | 网络延迟、帧率下降 |

### 2.3 监控规则 YAML Schema

```yaml
type: object
required: [name, detect, action]
properties:
  name:
    type: string
  description:
    type: string
  enabled:
    type: boolean
    default: true
  priority:
    type: integer
    default: 0
  cooldown:
    type: number
    default: 3.0
  max_triggers:
    type: integer
    default: 0
  detect:
    type: object
    required: [method]
    properties:
      method:
        type: string
        enum: [template, ocr, color, condition]
      template:
        type: string
      threshold:
        type: number
        default: 0.8
      region:
        type: array
        items:
          type: integer
      text:
        type: string
      color:
        type: string
      condition:
        type: string
      pre_delay:
        type: number
        default: 0
  action:
    type: object
    required: [type]
    properties:
      type:
        type: string
        enum: [click, swipe, press, wait, chain, ignore]
      target:
        type: string
      offset:
        type: array
        items:
          type: integer
      post_delay:
        type: number
        default: 1.0
  fallback:
    type: object
```

---

## 3. MonitorThread 守护线程

### 3.1 线程架构

```
┌──────────────────────────────────────────────────────────┐
│  MonitorManager                                          │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ MonitorThread│  │ MonitorThread│  │ MonitorThread│  │
│  │  (Device A)  │  │  (Device B)  │  │  (Device C)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │           │
│         └────────┬────────┘──────────────────┘           │
│                  │                                       │
│         ┌────────▼────────┐                              │
│         │   EventBus      │                              │
│         └─────────────────┘                              │
└──────────────────────────────────────────────────────────┘
```

### 3.2 MonitorThread 实现

```python
import threading
import time
from dataclasses import dataclass

@dataclass
class MonitorRule:
    """监控规则"""
    name: str
    description: str
    enabled: bool
    priority: int
    cooldown: float
    max_triggers: int
    detect: dict
    action: dict
    fallback: dict | None
    trigger_count: int = 0
    last_trigger_time: float = 0.0

@dataclass
class MatchResult:
    """匹配结果"""
    matched: bool
    x: int = 0
    y: int = 0
    confidence: float = 0.0
    data: dict | None = None

class MonitorThread(threading.Thread):
    """监控守护线程"""

    def __init__(
        self,
        device_id: str,
        rules: list[MonitorRule],
        orchestrator: "TaskOrchestrator",
        event_bus: "EventBus",
        check_interval: float = 1.0,
    ):
        super().__init__(daemon=True)
        self._device_id = device_id
        self._rules = rules
        self._orchestrator = orchestrator
        self._event_bus = event_bus
        self._check_interval = check_interval
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._paused = False

    def run(self) -> None:
        """线程主循环"""
        while not self._stop_event.is_set():
            if not self._paused:
                self._check_all_rules()
            self._stop_event.wait(timeout=self._check_interval)

    def stop(self) -> None:
        """停止线程"""
        self._stop_event.set()
        self.join(timeout=5.0)

    def pause(self) -> None:
        """暂停监控"""
        self._paused = True

    def resume(self) -> None:
        """恢复监控"""
        self._paused = False

    def update_rules(self, rules: list[MonitorRule]) -> None:
        """更新监控规则（线程安全）"""
        with self._lock:
            self._rules = rules

    def _check_all_rules(self) -> None:
        """检查所有规则"""
        sorted_rules = sorted(self._rules, key=lambda r: r.priority, reverse=True)
        for rule in sorted_rules:
            if not rule.enabled:
                continue
            if self._is_in_cooldown(rule):
                continue
            if self._is_max_triggers_reached(rule):
                continue

            result = self._detect(rule)
            if result.matched:
                self._handle_match(rule, result)
                rule.trigger_count += 1
                rule.last_trigger_time = time.time()
                break

    def _is_in_cooldown(self, rule: MonitorRule) -> bool:
        """检查是否在冷却期"""
        if rule.last_trigger_time == 0:
            return False
        return (time.time() - rule.last_trigger_time) < rule.cooldown

    def _is_max_triggers_reached(self, rule: MonitorRule) -> bool:
        """检查是否达到最大触发次数"""
        if rule.max_triggers == 0:
            return False
        return rule.trigger_count >= rule.max_triggers

    def _detect(self, rule: MonitorRule) -> MatchResult:
        """执行检测"""
        method = rule.detect.get("method", "template")

        if method == "template":
            return self._detect_template(rule)
        elif method == "ocr":
            return self._detect_ocr(rule)
        elif method == "color":
            return self._detect_color(rule)
        elif method == "condition":
            return self._detect_condition(rule)

        return MatchResult(matched=False)

    def _detect_template(self, rule: MonitorRule) -> MatchResult:
        """模板匹配检测"""
        template = rule.detect.get("template", "")
        threshold = rule.detect.get("threshold", 0.8)
        region = rule.detect.get("region")

        pos = self._orchestrator.image.find_template(
            template, threshold=threshold, region=region
        )
        if pos is not None:
            return MatchResult(matched=True, x=pos[0], y=pos[1])
        return MatchResult(matched=False)

    def _detect_ocr(self, rule: MonitorRule) -> MatchResult:
        """OCR 文字检测"""
        text = rule.detect.get("text", "")
        result = self._orchestrator.ocr.find_text(text)
        if result is not None:
            return MatchResult(matched=True, x=result.x, y=result.y, data={"text": result.text})
        return MatchResult(matched=False)

    def _detect_color(self, rule: MonitorRule) -> MatchResult:
        """颜色检测"""
        return MatchResult(matched=False)

    def _detect_condition(self, rule: MonitorRule) -> MatchResult:
        """条件检测"""
        return MatchResult(matched=False)

    def _handle_match(self, rule: MonitorRule, result: MatchResult) -> None:
        """处理匹配结果"""
        action = rule.action
        action_type = action.get("type", "click")

        if action_type == "click":
            self._action_click(rule, result)
        elif action_type == "swipe":
            self._action_swipe(rule, result)
        elif action_type == "press":
            self._action_press(rule, result)
        elif action_type == "ignore":
            pass

        self._report_event(rule, result)

    def _action_click(self, rule: MonitorRule, result: MatchResult) -> None:
        """执行点击动作"""
        target = rule.action.get("target", "match")
        offset = rule.action.get("offset", [0, 0])

        if target == "match":
            x = result.x + offset[0]
            y = result.y + offset[1]
        else:
            x, y = target

        self._orchestrator.input.click(x, y)

        post_delay = rule.action.get("post_delay", 1.0)
        if post_delay > 0:
            time.sleep(post_delay)

    def _action_swipe(self, rule: MonitorRule, result: MatchResult) -> None:
        """执行滑动动作"""
        direction = rule.action.get("direction", "up")
        distance = rule.action.get("distance", 200)
        duration = rule.action.get("duration", 0.3)

        x, y = result.x, result.y
        if direction == "up":
            self._orchestrator.input.swipe(x, y, x, y - distance, duration)
        elif direction == "down":
            self._orchestrator.input.swipe(x, y, x, y + distance, duration)
        elif direction == "left":
            self._orchestrator.input.swipe(x, y, x - distance, y, duration)
        elif direction == "right":
            self._orchestrator.input.swipe(x, y, x + distance, y, duration)

    def _action_press(self, rule: MonitorRule, result: MatchResult) -> None:
        """执行按键动作"""
        key = rule.action.get("key", "back")
        self._orchestrator.input.key_press(key)

    def _report_event(self, rule: MonitorRule, result: MatchResult) -> None:
        """上报监控事件"""
        self._event_bus.publish(Event(
            type=EventType.MONITOR_EVENT_DETECTED,
            data={
                "device_id": self._device_id,
                "rule_name": rule.name,
                "action_type": rule.action.get("type"),
                "match_position": {"x": result.x, "y": result.y},
                "confidence": result.confidence,
            },
            source=f"MonitorThread:{self._device_id}",
            timestamp=time.time(),
        ))
```

---

## 4. 弹窗检测与处理

### 4.1 弹窗类型

| 弹窗类型 | 检测方式 | 处理动作 |
|----------|---------|---------|
| 更新提示 | 模板匹配"更新"按钮 | 点击"稍后更新"或关闭 |
| 公告弹窗 | 模板匹配关闭按钮 | 点击关闭 |
| 广告弹窗 | 模板匹配关闭/跳过按钮 | 点击关闭 |
| 网络异常 | OCR 检测"网络"文字 | 点击"重试" |
| 权限请求 | 模板匹配"允许"按钮 | 点击"允许" |
| 崩溃报告 | OCR 检测"报告"文字 | 点击"关闭" |

### 4.2 弹窗处理规则示例

```yaml
# monitors/popup_handler.yaml
name: popup_handler
description: "通用弹窗处理"
enabled: true
priority: 20
cooldown: 2.0
max_triggers: 0

detect:
  method: template
  template: "common/close_button.png"
  threshold: 0.85

action:
  type: click
  target: "match"
  post_delay: 0.5

fallback:
  method: ocr
  text: "关闭"
  action:
    type: click
    target: "match"
```

---

## 5. 剧情跳过

### 5.1 剧情跳过规则

```yaml
# monitors/story_skip.yaml
name: story_skip
description: "自动跳过剧情对话"
enabled: true
priority: 15
cooldown: 1.0
max_triggers: 0

detect:
  method: template
  template: "common/skip_button.png"
  threshold: 0.8

action:
  type: click
  target: "match"
  post_delay: 0.3

fallback:
  method: ocr
  text: "跳过"
  action:
    type: click
    target: "match"
    post_delay: 0.3
```

### 5.2 剧情对话连续点击

```yaml
name: story_dialog_click
description: "剧情对话自动点击继续"
enabled: true
priority: 10
cooldown: 0.5

detect:
  method: template
  template: "common/dialog_indicator.png"
  threshold: 0.75

action:
  type: click
  target: "match"
  offset: [0, 100]
  post_delay: 0.8
```

---

## 6. 事件上报机制

### 6.1 上报流程

```
MonitorThread 检测到事件
    │
    ▼
EventBus.publish(MONITOR_EVENT_DETECTED)
    │
    ├──► Agent → WebSocket → Server (实时上报)
    │
    ├──► MonitorEvent 模型 (持久化)
    │
    └──► Client WebSocket (前端展示)
```

### 6.2 事件数据结构

```python
@dataclass
class MonitorEventData:
    """监控事件数据"""
    device_id: str
    rule_name: str
    action_type: str
    match_position: dict
    confidence: float
    screenshot_path: str | None
    timestamp: float
```

### 6.3 Server 端事件处理

```python
class MonitorEventConsumer:
    """Server 端监控事件消费者"""

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._event_bus.subscribe(EventType.MONITOR_EVENT_DETECTED, self._on_event)

    def _on_event(self, event: Event) -> None:
        """处理监控事件"""
        data = event.data

        MonitorEvent.objects.create(
            event_type=data["rule_name"],
            handling_result=data["action_type"],
            screenshot_path=data.get("screenshot_path", ""),
            event_data=data,
            agent_id=data.get("agent_id"),
            resource_pack_id=data.get("resource_pack_id"),
        )

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "monitor_events",
            {
                "type": "monitor_event",
                "data": data,
            },
        )
```

---

## 7. 规则热更新

### 7.1 热更新流程

```
1. 用户在前端修改监控规则
2. 前端发送 PUT /api/v2/monitors/monitor-rules/{id}/
3. Server 更新数据库
4. Server 通过 WebSocket 通知 Agent
5. Agent 收到通知，更新 MonitorThread 的规则列表
6. 无需重启任务
```

### 7.2 热更新实现

```python
class MonitorManager:
    """监控管理器，支持规则热更新"""

    def __init__(self, orchestrator: "TaskOrchestrator", event_bus: "EventBus"):
        self._orchestrator = orchestrator
        self._event_bus = event_bus
        self._threads: dict[str, MonitorThread] = {}
        self._rules_cache: dict[str, list[MonitorRule]] = {}

        self._event_bus.subscribe(EventType.CONFIG_UPDATED, self._on_config_updated)

    def start_monitor(self, device_id: str, rules: list[MonitorRule]) -> None:
        """启动监控"""
        thread = MonitorThread(
            device_id=device_id,
            rules=rules,
            orchestrator=self._orchestrator,
            event_bus=self._event_bus,
        )
        self._threads[device_id] = thread
        self._rules_cache[device_id] = rules
        thread.start()

    def stop_monitor(self, device_id: str) -> None:
        """停止监控"""
        if device_id in self._threads:
            self._threads[device_id].stop()
            del self._threads[device_id]

    def update_rules(self, device_id: str, rules: list[MonitorRule]) -> None:
        """热更新规则"""
        if device_id in self._threads:
            self._threads[device_id].update_rules(rules)
            self._rules_cache[device_id] = rules

    def _on_config_updated(self, event: Event) -> None:
        """配置更新回调"""
        if event.data.get("config_type") == "monitor_rules":
            device_id = event.data.get("device_id")
            rules = self._load_rules_from_server(device_id)
            self.update_rules(device_id, rules)

    def _load_rules_from_server(self, device_id: str) -> list[MonitorRule]:
        """从 Server 加载最新规则"""
        pass
```

### 7.3 规则版本控制

每次规则更新时记录版本号，Agent 确认收到后回复确认消息：

```
Server → Agent: config.update {config_type: "monitor_rules", version: 5, rules: [...]}
Agent → Server: config.ack {config_type: "monitor_rules", version: 5}
```

如果 Agent 未在 10 秒内确认，Server 重发更新消息。
