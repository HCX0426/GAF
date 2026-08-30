---
summary: GAF 并发与性能设计
applies_to: ['backend', 'design']
key_decisions:
  - 截图缓存策略
  - 设计稿部分类已实现为 helper，部分尚未接入生产路径
last_updated: 2026-08-02
---

# GAF 并发与性能设计

> 版本：1.5 | 日期：2026-08-08 | 修订：更新文件路径 (engine.py → pipeline_engine.py, tasks/services.py → tasks/services/monitor_service.py)

## 0. 现实状态（2026-07-22 审计）

> ⚠️ **重要**：本文档为设计稿。Phase 5.1-5.4 + Phase 3.3 已将文档中的类实现为独立 helper（🔧 状态），但部分 helper 尚未接入生产热路径。`WorkerSelector` 和 `ConcurrencyController` 是例外 — 均已接入 `dispatch_task`。

| 项 | 文档声称 | 现实代码 | 状态 |
|----|----------|----------|------|
| `WorkerSelector` 类 | 任务分配时按能力+负载选 Agent | `backend/tasks/worker_selector.py` — 类已实现并接入 `dispatch_task`（Phase 5.2，commit `-`） | ✅ 已实现并接入 |
| `ConcurrencyController` 类 | 控制每 Agent 最大任务数 | `backend/tasks/concurrency_controller.py` — 类已实现（Phase 5.3，commit `-`），**已接入 `dispatch_task`**（`tasks.py:109-110` 调用 `can_assign` 过滤，`tasks.py:156` 调用 `assign`）+ `AgentConsumer`（task.completed/task.failed 时 release）+ force-terminate 路径（`services/monitor_service.py` cancel/execution/heartbeat timeouts） | ✅ 已实现并接入 |
| `ResourceLock` 类 | 设备资源锁 | `backend/tasks/resource_lock.py` — 类已实现（Phase 5.4，commit `-`），**未接入 dispatch 路径** | 🔧 helper 就绪，集成待办 |
| `ScreenshotCache` / `RedisScreenshotCache` | 截图缓存 | `worker/src/devices/screenshot_cache.py` — 类已实现（Phase 3.3，commit `-`），**未接入 `ScreenshotManager.capture()` 热路径** | 🔧 helper 就绪，集成待办 |
| `MessageCompressor` | WebSocket 消息压缩 | `backend/protocol/message_compressor.py` + `worker/src/utils/message_compressor.py` — 双端镜像已实现并接入 `AgentConsumer.send()` + `AgentConnection.send_message()` (spec-42, 2026-07-20, Hello/Hello.ack 协商 + msgpack+zlib 压缩 + 端到端测试 12/12 passed) | ✅ 已实现并接入 (spec-42) |
| 数据库索引 | TaskExecution/TaskStep/MonitorEvent 索引 | 索引在 migration 中定义，与文档基本一致 | ✅ 一致 |
| 查询优化 | select_related/prefetch_related | `TaskExecutionViewSet.get_queryset` 实现了优化 | ✅ 一致 |

### 0.1 实际并发控制

`backend/tasks/tasks.py:dispatch_task` 实现了（Phase 5.2 起通过 `WorkerSelector` 封装，Phase 5.3 起叠加 `ConcurrencyController` 并发限制）：
1. 按任务 required_capabilities 过滤 Agent（`WorkerSelector.filter_by_capability`）
2. 通过 `ConcurrencyController.can_assign(agent_id)` 过滤掉已达并发上限的 Agent（`tasks.py:109-110`）— 全部 Agent 都满载时将 execution 置为 PENDING 并调度重试（`tasks.py:111-122`）
3. 优先选空闲 Agent，空闲中选心跳最新鲜的；非空闲选 cpu 最低的（`WorkerSelector.select_by_load`）
4. 通过 `task.assign` WebSocket 消息下发

> **WS 帧名规范（命名归一化 C-5, 2026-08-29 锁定）**: 规范帧名 = `task.assign`（canonical）；`task.dispatch` 保留为 **deprecated alias**（历史兼容，映射同一 handler `handle_task_assign`）。后端方法名 `handle_task_assign`（下划线）保持不变——帧名与内部方法名不强求一致，wire-contract 级对齐通过本文档保证。alias 计划在未来大版本移除。
5. Agent 标记 BUSY 后调用 `ConcurrencyController.assign(agent_id, execution_id)` 占用并发槽位（`tasks.py:156`）

> **心跳协议安全余量** (TD-340, 2026-07-23): agent 端 `heartbeat_interval=10s` (原 30s), backend `HEARTBEAT_OFFLINE_SECONDS=30s`. WorkerSelector 依赖 `last_heartbeat` 判断 agent 健康, 30s/30s 临界会导致 status 在 ONLINE/OFFLINE 间抖动, 进而让 `select_by_load` 选到刚被标 offline 的 agent. 10s 间隔提供 3x 安全余量, 消除抖动.

设备锁通过 `TaskExecution` 状态机隐式实现：running 状态的 execution 持有设备，新任务无法分配到同一设备。`ResourceLock` 类已实现但尚未接入，未来可作为强锁替换隐式状态机依赖。

### 0.2 集成路线图（Phase 5.5 标注）

| Helper | 接入点 | 集成复杂度 | 优先级 |
|--------|--------|-----------|--------|
| `WorkerSelector` | `dispatch_task` | ✅ 已接入 | — |
| `ConcurrencyController` | `dispatch_task` (can_assign + assign) + `AgentConsumer` (release on task.completed/task.failed) + `services/monitor_service.py` (release on force-terminate) | ✅ 已接入 | — |
| `ResourceLock` | `dispatch_task` + device 操作前 | 高（需确定 device_id 来源 + 跨 agent 协调） | P3 |
| `ScreenshotCache` | `ScreenshotManager.capture()` | 中（需 frame hash + 缓存查询） | P3 |
| `MessageCompressor` | `AgentConsumer.send()` + Agent 端解码 | ✅ 已接入 (spec-42, Hello/Hello.ack 协商 + msgpack+zlib 压缩) | — |

---

## 1. 概述

GAF 需要支持多 Agent 并发执行任务、高效截图传输、实时状态同步等场景。本设计定义多 Agent 并发控制、截图缓存策略、WebSocket 消息压缩、数据库查询优化和前端渲染优化方案。

> ⚠️ **现实提示**：Phase 5.1-5.4 + Phase 3.3 已将并发控制相关类实现为独立 helper，但除 `WorkerSelector` 和 `ConcurrencyController` 外均未接入生产热路径。集成路线图见 §0.2。

---

## 2. 多 Agent 并发控制

### 2.1 并发架构

```
┌──────────────────────────────────────────────────────────┐
│  Server (Django)                                         │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  dispatch_task (WorkerSelector 选 Worker)          │   │
│  │  - 任务分配                                       │   │
│  │  - Agent 选择                                     │   │
│  │  - 负载均衡                                       │   │
│  └──────────────────┬───────────────────────────────┘   │
│                     │                                    │
│    ┌────────────────┼────────────────┐                  │
│    │                │                │                  │
│  ┌─▼──────┐  ┌─────▼──────┐  ┌─────▼──────┐          │
│  │ Agent A │  │  Agent B   │  │  Agent C   │          │
│  │ (WS连接)│  │  (WS连接)  │  │  (WS连接)  │          │
│  └────────┘  └────────────┘  └────────────┘          │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Agent 选择策略

```python
class WorkerSelector:
    """Agent 选择器，负责任务分配"""

    def select_agent(self, task: Task, agents: list[Agent]) -> Agent | None:
        """选择最合适的 Agent 执行任务"""
        available = [a for a in agents if a.status in ("online", "idle")]
        if not available:
            return None

        candidates = self._filter_by_capability(available, task)
        if not candidates:
            return None

        return self._select_by_load(candidates)

    def _filter_by_capability(self, agents: list[Agent], task: Task) -> list[Agent]:
        """按能力过滤 Agent"""
        required_caps = task.task_definition.get("required_capabilities", [])
        result = []
        for agent in agents:
            agent_caps = agent.capabilities or {}
            if all(agent_caps.get(cap) for cap in required_caps):
                result.append(agent)
        return result

    def _select_by_load(self, agents: list[Agent]) -> Agent:
        """按负载选择最空闲的 Agent"""
        return min(agents, key=lambda a: a.active_tasks_count)
```

### 2.3 并发控制

```python
class ConcurrencyController:
    """并发控制器"""

    def __init__(self, max_tasks_per_agent: int = 3, max_total_tasks: int = 20):
        self._max_per_agent = max_tasks_per_agent
        self._max_total = max_total_tasks
        self._agent_tasks: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def can_assign(self, agent_id: str) -> bool:
        """检查是否可以给 Agent 分配任务"""
        with self._lock:
            total = sum(len(tasks) for tasks in self._agent_tasks.values())
            if total >= self._max_total:
                return False
            agent_count = len(self._agent_tasks.get(agent_id, set()))
            if agent_count >= self._max_per_agent:
                return False
            return True

    def assign(self, agent_id: str, task_id: str) -> None:
        """分配任务"""
        with self._lock:
            if agent_id not in self._agent_tasks:
                self._agent_tasks[agent_id] = set()
            self._agent_tasks[agent_id].add(task_id)

    def release(self, agent_id: str, task_id: str) -> None:
        """释放任务"""
        with self._lock:
            if agent_id in self._agent_tasks:
                self._agent_tasks[agent_id].discard(task_id)

    def get_agent_load(self, agent_id: str) -> int:
        """获取 Agent 当前任务数"""
        with self._lock:
            return len(self._agent_tasks.get(agent_id, set()))
```

### 2.4 资源锁

```python
class ResourceLock:
    """设备资源锁，防止同一设备被多个任务同时操作"""

    def __init__(self):
        self._locks: dict[str, threading.Lock] = {}
        self._holders: dict[str, str] = {}

    def acquire(self, device_id: str, task_id: str, timeout: float = 30.0) -> bool:
        """获取设备锁"""
        if device_id not in self._locks:
            self._locks[device_id] = threading.Lock()
        lock = self._locks[device_id]
        acquired = lock.acquire(timeout=timeout)
        if acquired:
            self._holders[device_id] = task_id
        return acquired

    def release(self, device_id: str, task_id: str) -> None:
        """释放设备锁"""
        if device_id in self._holders and self._holders[device_id] == task_id:
            del self._holders[device_id]
            self._locks[device_id].release()
```

---

## 3. 截图缓存策略

### 3.1 缓存架构

> **TTL 口径 (D21 归一)**: 两层缓存 TTL 独立——Worker 本地 `ScreenshotCache` 用**秒**（`config.cache_ttl`，N196 默认 300s，env `GAF_AGENT_CACHE_TTL`）；后端 Redis 端缓存用**毫秒**（`SCREENSHOT_CACHE_TTL`）。下文 50ms 为早期示意值，非实现常量。

```
Agent 截图 → 本地 ScreenshotCache (秒级, config.cache_ttl=300) → Server → Redis Cache (毫秒级) → WebSocket → Client
```

### 3.2 缓存实现

```python
import time
import threading

class ScreenshotCache:
    """截图缓存，TTL 由 config.cache_ttl 驱动（默认 300s），避免重复截图"""

    def __init__(self, ttl: float = 300.0, max_size: int = 10):
        self._ttl = ttl
        self._max_size = max_size
        self._cache: dict[str, tuple[bytes, float]] = {}
        self._lock = threading.Lock()

    def get(self, device_id: str) -> bytes | None:
        """获取缓存的截图"""
        with self._lock:
            if device_id in self._cache:
                data, timestamp = self._cache[device_id]
                if time.time() - timestamp < self._ttl:
                    return data
                del self._cache[device_id]
        return None

    def set(self, device_id: str, data: bytes) -> None:
        """缓存截图"""
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest = min(self._cache.items(), key=lambda x: x[1][1])
                del self._cache[oldest[0]]
            self._cache[device_id] = (data, time.time())

    def invalidate(self, device_id: str) -> None:
        """使缓存失效"""
        with self._lock:
            self._cache.pop(device_id, None)
```

### 3.3 Redis 端缓存

```python
class RedisScreenshotCache:
    """Redis 截图缓存（毫秒级，与 Worker 本地 ScreenshotCache 秒级 TTL 独立）"""

    SCREENSHOT_PREFIX = "screenshot:"
    TTL = 0.1  # 100ms

    def __init__(self, redis_client):
        self._redis = redis_client

    def get(self, device_id: str) -> bytes | None:
        """从 Redis 获取截图"""
        key = f"{self.SCREENSHOT_PREFIX}{device_id}"
        return self._redis.get(key)

    def set(self, device_id: str, data: bytes) -> None:
        """存入 Redis"""
        key = f"{self.SCREENSHOT_PREFIX}{device_id}"
        self._redis.setex(key, int(self.TTL * 1000), data)
```

---

## 4. WebSocket 消息压缩

> ✅ **spec-42 已实施 (2026-07-20)**: MessageCompressor 已接入 `AgentConsumer.send()` + `AgentConnection.send_message()` 双端热路径。Hello/Hello.ack 协商帧 (JSON text) → 协商成功后大帧 (size ≥ threshold) 走 msgpack+zlib 压缩 bytes_data, 小帧保持 JSON text; legacy agent 不发 Hello 则端到端 JSON text。端到端测试 12/12 passed (backend 6 + agent 6), 压缩率 ~10KB payload ≤ 50%。详见 `backend/protocol/message_compressor.py` + `worker/src/utils/message_compressor.py` (双端镜像, drift mitigation docstring 标注)。

### 4.1 压缩策略

| 消息类型 | 压缩方式 | 说明 |
|----------|---------|------|
| 截图数据 | JPEG 压缩 + base64 | 质量 80，约 30KB/帧 |
| 进度更新 | JSON 精简 | 仅发送变更字段 |
| 日志流 | 差量传输 | 仅发送新增日志行 |
| 状态同步 | 二进制编码 | MessagePack 替代 JSON |

### 4.2 消息格式优化

```python
class MessageCompressor:
    """消息压缩器"""

    def compress_screenshot(self, image: bytes, quality: int = 80) -> str:
        """压缩截图为 JPEG + base64"""
        import cv2
        import base64
        import numpy as np

        nparr = np.frombuffer(image, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
        _, compressed = cv2.imencode(".jpg", img, encode_param)

        return base64.b64encode(compressed.tobytes()).decode()

    def compress_progress(self, full_data: dict, last_data: dict) -> dict:
        """差量压缩进度数据"""
        delta = {}
        for key, value in full_data.items():
            if key not in last_data or last_data[key] != value:
                delta[key] = value
        return delta

    def compress_log(self, full_log: str, last_position: int) -> dict:
        """差量传输日志"""
        new_content = full_log[last_position:]
        return {
            "position": len(full_log),
            "content": new_content,
        }
```

### 4.3 WebSocket 帧大小控制

| 消息类型 | 最大帧大小 | 超出处理 |
|----------|-----------|---------|
| 截图 | 100 KB | 降低 JPEG 质量 |
| 进度 | 10 KB | 仅发送变更 |
| 日志 | 50 KB | 分批发送 |
| 状态 | 5 KB | 精简字段 |

---

## 5. 数据库查询优化

### 5.1 索引优化

```python
# 关键索引
DATABASE_INDEXES = {
    "TaskExecution": [
        ("task_id", "status"),           # 按任务查执行状态
        ("agent_id", "status"),          # 按 Agent 查执行
        ("created_at",),                  # 按时间排序
        ("status", "created_at"),         # 按状态+时间
    ],
    "TaskStep": [
        ("execution_id", "step_index"),   # 步骤序号唯一
    ],
    "MonitorEvent": [
        ("agent_id", "created_at"),       # 按 Agent 查事件
        ("event_type", "created_at"),     # 按类型查事件
    ],
    "LLMUsageLog": [
        ("user_id", "created_at"),        # 按用户查用量
    ],
}
```

### 5.2 查询优化策略

| 策略 | 说明 | 适用场景 |
|------|------|---------|
| select_related | 预加载外键关联 | TaskExecution → Task, Agent |
| prefetch_related | 预加载多对多 | Task → TaskSteps |
| only/defer | 延迟加载大字段 | 列表页不加载 log 字段 |
| 分页查询 | 统一分页 | 所有列表 API |
| 缓存 | Redis 缓存热点数据 | Agent 状态、配置 |

### 5.3 查询优化示例

```python
class TaskExecutionViewSet(viewsets.ModelViewSet):
    """任务执行 API（优化查询）"""

    def get_queryset(self):
        return (
            TaskExecution.objects
            .select_related("task", "agent", "triggered_by")
            .prefetch_related("steps")
            .only(
                "id", "task__name", "agent__hostname",
                "status", "started_at", "completed_at",
                "duration", "error_message",
            )
        )

    def list(self, request):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = TaskExecutionListSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)
```

### 5.4 数据库连接池

> 2026-08-03 spec: dev/prod 统一 SQLite + WAL，单机部署 < 100 并发。
> SQLite WAL 模式读写并发不阻塞，写性能 ~1000 TPS，读性能 ~10万 QPS。

```python
# config/settings/base.py (SQLite + WAL 配置)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;",
            "transaction_mode": "IMMEDIATE",
        },
    }
}
```

---

## 6. 前端渲染优化

### 6.1 优化策略

| 策略 | 说明 | 预期效果 |
|------|------|---------|
| 虚拟列表 | 大数据列表仅渲染可见项 | 10x 渲染性能提升 |
| 懒加载 | 页面组件按需加载 | 首屏加载时间减半 |
| 截图流节流 | 截图更新频率限制 | CPU 使用率降低 50% |
| 状态分片 | Zustand store 按功能拆分 | 减少不必要的重渲染 |
| Memo | 组件级缓存 | 避免重复渲染 |
| Web Worker | 图像处理移到 Worker 线程 | 主线程不阻塞 |

### 6.2 截图流优化

```typescript
class ScreenshotStream {
  private lastRenderTime: number = 0;
  private readonly minInterval: number = 100; // 最小渲染间隔 100ms
  private pendingFrame: string | null = null;
  private rafId: number | null = null;

  constructor(private canvas: HTMLCanvasElement) {}

  onFrame(base64Data: string): void {
    this.pendingFrame = base64Data;
    const now = Date.now();
    if (now - this.lastRenderTime >= this.minInterval) {
      this.renderFrame();
    } else if (!this.rafId) {
      this.rafId = requestAnimationFrame(() => {
        this.renderFrame();
        this.rafId = null;
      });
    }
  }

  private renderFrame(): void {
    if (!this.pendingFrame) return;
    const img = new Image();
    img.onload = () => {
      const ctx = this.canvas.getContext("2d");
      if (ctx) {
        ctx.drawImage(img, 0, 0);
      }
      this.lastRenderTime = Date.now();
      this.pendingFrame = null;
    };
    img.src = `data:image/jpeg;base64,${this.pendingFrame}`;
  }
}
```

### 6.3 虚拟列表

```typescript
import { FixedSizeList as List } from "react-window";

interface TaskListProps {
  tasks: Task[];
  height: number;
}

function TaskList({ tasks, height }: TaskListProps) {
  const Row = ({ index, style }: { index: number; style: React.CSSProperties }) => (
    <div style={style}>
      <TaskCard task={tasks[index]} />
    </div>
  );

  return (
    <List height={height} itemCount={tasks.length} itemSize={80} width="100%">
      {Row}
    </List>
  );
}
```

### 6.4 性能监控

```typescript
class PerformanceMonitor {
  private metrics: Map<string, number[]> = new Map();

  measure(name: string, fn: () => void): void {
    const start = performance.now();
    fn();
    const duration = performance.now() - start;
    if (!this.metrics.has(name)) {
      this.metrics.set(name, []);
    }
    this.metrics.get(name)!.push(duration);
  }

  getReport(): Record<string, { avg: number; max: number; count: number }> {
    const report: Record<string, { avg: number; max: number; count: number }> = {};
    for (const [name, durations] of this.metrics) {
      report[name] = {
        avg: durations.reduce((a, b) => a + b, 0) / durations.length,
        max: Math.max(...durations),
        count: durations.length,
      };
    }
    return report;
  }
}
```

---

## 7. 性能基准

### 7.1 目标指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 截图延迟 | < 50ms | 从截图到 Agent 可用 |
| 截图传输 | < 200ms | 从 Agent 到 Client 展示 |
| API 响应 | < 100ms | 95% 请求 |
| WebSocket 延迟 | < 50ms | 消息端到端 |
| 任务分配 | < 500ms | 从创建到 Agent 开始执行 |
| 前端首屏 | < 2s | 首次加载 |
| 前端交互 | < 100ms | 页面切换 |
| 数据库查询 | < 50ms | 95% 查询 |

### 7.2 压力测试场景

| 场景 | Agent 数 | 并发任务 | 截图频率 | 预期 |
|------|---------|---------|---------|------|
| 单 Agent | 1 | 1 | 1fps | 全部达标 |
| 多 Agent | 5 | 10 | 5fps | 全部达标 |
| 高负载 | 10 | 20 | 10fps | API < 200ms |
| 极限 | 20 | 50 | 20fps | 系统不崩溃 |
