---
spec: 2026-08-08-architechure-debt-refactor
title: GAF 核心架构技术债务重构 Spec
status: active
created: 2026-08-08
estimated_effort: 3-5 days
risk: high
---

# GAF 核心架构技术债务重构 Spec (增强版)

## 1. 背景与动机 (Background & Motivation)

经过对 GAF 项目 8 大架构层面的深度分析，识别出多项严重的技术债务（Technical Debt）。这些问题导致：
- **维护困难**：核心业务逻辑（如任务执行、设备控制）高度耦合在 `views.py` 和 `__main__.py` 中，难以单独测试和复用。
- **一致性缺失**：LLM 客户端、WebSocket 协议等基础组件在前后端存在重复实现或版本不一致。
- **扩展性差**：新增设备类型、AI 能力或监控指标需要修改多处硬编码的条件分支。
- **稳定性风险**：进程管理依赖脆弱的 PowerShell 脚本，监控体系分散导致故障排查困难。

本次重构旨在从根本上解决架构臃肿问题，建立清晰、健壮、可扩展的系统骨架。

## 2. 核心问题定义 (Problem Statement)

| 层级 | 问题描述 | 严重程度 |
| :--- | :--- | :--- |
| **3. 业务服务层** | **View 层过重**：业务逻辑散落在 `views.py`，缺乏 Service 层，导致测试困难、逻辑无法复用。 | 高 |
| **5. Agent 引擎层** | **三段引擎边界模糊**：`StateMachine`, `ChainManager`, `Pipeline Engine` 职责重叠，缺乏统一的执行入口。 | 高 |
| **7. AI 辅助层** | **LLM 客户端重复**：`agent` 与 `backend` 分别维护 LLM 调用逻辑，难以统一管理和测试。 | 高 |
| **8. 基础设施层** | **监控体系分散**：前端、Agent、Backend 各自监控，缺乏统一的事件协议和数据管道。 | 中 |
| **5. Agent 引擎层** | **节点类型膨胀**：35+ 种节点类型硬编码，缺乏元数据注册机制，扩展困难。 | 中 |
| **6. 设备交互层** | **设备发现分散**：ADB/Windows 窗口/LDPlayer 扫描逻辑分散在多个模块。 | 中 |
| **4. 数据持久层** | **数据库无归档**：`TaskExecution` 大表数据无定期归档策略，长期运行会导致性能下降。 | 中 |
| **8. 基础设施层** | **进程管理脆弱**：依赖 PowerShell 脚本，缺乏真正的守护进程和看门狗机制。 | 低 |

## 3. 重构目标 (Goals)

1.  **分层解耦**：引入 Service 层，明确 UI (View)、业务逻辑 (Service)、数据访问 (Repository) 的边界。
2.  **统一入口**：建立 Agent 执行引擎的统一调度层和 LLM 能力的统一路由层。
3.  **注册驱动**：将硬编码的节点类型和设备发现机制改造为注册表驱动（Registry-Driven），提升扩展性。
4.  **健壮运维**：构建跨进程的监控事件总线，升级进程管理器为守护进程模式。

## 4. 详细实施计划 (Implementation Plan - Actionable)

### Phase 1: 核心业务分层解耦 (Service Layer & Clear Boundaries)
> 目标：解决最严重的代码耦合问题，为后续重构奠定基础。

#### Task 1.1: 引入 Service 层模式

**详细代码映射分析**：

| 源文件 (`views.py`) | 目标文件 (`services/`) | 涉及逻辑 | 函数签名建议 |
| :--- | :--- | :--- | :--- |
| `tasks/views.py::dispatch_task` | `tasks/services/task_service.py::TaskService` | 派发任务逻辑（校验、创建执行、分配设备） | `def dispatch_task(self, task_id: int, user_id: int) -> TaskExecution` |
| `scheduler/views.py::execute_scheduled_task` | `scheduler/services/scheduler_service.py::SchedulerService` | 定时任务执行逻辑 | `def execute_scheduled_task(self, schedule_id: int) -> ScheduledExecution` |
| `agents/views.py::update_device_status` | `agents/services/device_service.py::DeviceService` | 设备状态更新逻辑 | `def update_device_status(self, device_id: int, status: str) -> Device` |

**实施步骤**：
1.  **创建服务目录与基类**：
    ```python
    # backend/tasks/services/__init__.py
    from .task_service import TaskService
    from .execution_service import ExecutionService
    ```
2.  **实现 `TaskService`**：
    ```python
    # backend/tasks/services/task_service.py
    class TaskService:
        def __init__(self):
            # 依赖注入 Repositories 或直接使用 ORM
            pass

        def dispatch_task(self, task_id: int, user_id: int) -> TaskExecution:
            task = Task.objects.get(id=task_id)
            # ... 原本在 views 中的复杂逻辑
            execution = TaskExecution.objects.create(...)
            return execution
    ```
3.  **重构视图层 (`views.py`)**：
    ```python
    # backend/tasks/views.py
    @api_view(['POST'])
    def dispatch_task_view(request, pk):
        task_service = TaskService()  # 实例化 (或通过依赖注入)
        try:
            execution = task_service.dispatch_task(task_id=pk, user_id=request.user.id)
            return Response(data=ExecutionSerializer(execution).data, status=status.HTTP_201_CREATED)
        except Task.DoesNotExist:
            return Response({"error": "Task not found"}, status=status.HTTP_404_NOT_FOUND)
    ```

---

#### Task 1.2: 梳理 Agent 三段引擎边界

**接口契约与代码结构**：

```python
# agent/src/engine/executor.py

from abc import ABC, abstractmethod

class BaseEngine(ABC):
    """所有执行引擎的基类"""
    @abstractmethod
    def run(self, *args, **kwargs) -> ExecutionResult:
        pass

class PipelineEngine(BaseEngine):
    """负责单一流程的步骤执行 (Click -> Input -> Screenshot)"""
    def run(self, pipeline_data: dict) -> ExecutionResult:
        print("Running Pipeline Engine...")
        # ... 现有 pipeline 逻辑

class ChainManager(BaseEngine):
    """负责复杂业务编排 (如：先启动 A，再启动 B)"""
    def run(self, chain_data: dict) -> ExecutionResult:
        print("Running Chain Manager...")
        # ... 现有 chain 逻辑

class TaskExecutor:
    """Agent 统一任务执行入口"""
    def __init__(self):
        self.engines: dict[str, BaseEngine] = {
            "pipeline": PipelineEngine(),
            "chain": ChainManager(),
        }

    def execute(self, task_type: str, task_data: dict) -> ExecutionResult:
        if task_type not in self.engines:
            raise ValueError(f"Unknown task type: {task_type}")
        print(f"Executing {task_type} task...")
        return self.engines[task_type].run(task_data)

```

**重构后 `agent/src/` 目录结构**：
```
agent/src/
├── engine/
│   ├── executor.py      # [新增] TaskExecutor 统一入口
│   ├── pipeline_engine.py # [重命名] 原 engine.py
│   ├── chain_manager.py   # [重命名] 原 chain.py
│   └── state_machine.py   # 保持不变
├── devices/
...
```

---

### Phase 2: AI 与设备层标准化 (AI & Device Standardization)

#### Task 2.1: 统一 LLM 客户端与能力路由

**Agent ↔ Backend WebSocket RPC 契约**：
*   **操作**：`llm.call`
*   **请求 Payload**:
    ```json
    {
      "action": "llm.call",
      "request_id": "uuid-string",
      "payload": {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 100
      }
    }
    ```
*   **响应 Payload** (通过 WebSocket `llm.result` 返回):
    ```json
    {
      "action": "llm.result",
      "request_id": "uuid-string",
      "status": "success",
      "payload": {
        "content": "Hi there!",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
      }
    }
    ```

#### Task 2.2: 构建设备发现注册表

**抽象基类 `BaseDiscovery` 接口**：
```python
# agent/src/devices/discovery/base.py

from abc import ABC, abstractmethod
from typing import List
from .models import DeviceInfo

class BaseDiscovery(ABC):
    """设备发现器抽象基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """发现器名称 (e.g., "ADB Emulator")"""
        pass

    @abstractmethod
    def discover(self) -> List[DeviceInfo]:
        """
        执行设备扫描。
        Returns:
            List[DeviceInfo]: 发现的设备列表
        """
        pass
    
    def is_available(self) -> bool:
        """检查该发现器所需的依赖/环境是否就绪"""
        return True

# agent/src/devices/discovery/registry.py

class DeviceDiscoveryRegistry:
    def __init__(self):
        self._discoveries: List[BaseDiscovery] = []

    def register(self, discovery: BaseDiscovery):
        self._discoveries.append(discovery)

    def discover_all(self) -> List[DeviceInfo]:
        all_devices = []
        for discovery in self._discoveries:
            if discovery.is_available():
                print(f"Discovering via {discovery.name}...")
                try:
                    devices = discovery.discover()
                    all_devices.extend(devices)
                except Exception as e:
                    print(f"Discovery failed for {discovery.name}: {e}")
        return all_devices

# 示例注册
# registry.register(EmulatorDiscovery())
# registry.register(WindowDiscovery())
```

---

### Phase 3: 运维与数据治理 (Ops & Data Governance)

#### Task 3.1: 构建跨进程监控事件总线

**`MonitoringEvent` 数据结构**：
```python
# backend/monitors/events.py
from pydantic import BaseModel
from datetime import datetime
from typing import Literal, Any

class MonitoringEvent(BaseModel):
    event_id: str
    timestamp: datetime = datetime.utcnow
    source: Literal["agent", "backend", "frontend"]
    level: Literal["INFO", "WARNING", "ERROR", "CRITICAL"]
    category: str # e.g., "resource", "task_execution", "llm"
    payload: dict[str, Any]
    
# 示例
event = MonitoringEvent(
    event_id="evt-123",
    source="agent",
    level="ERROR",
    category="resource",
    payload={"device_id": 5, "cpu_usage": 95, "message": "CPU overload"}
)
```

#### Task 3.2: 实施数据库归档与进程守护

**Python 守护进程 `gaf_daemon.py` 伪代码**：
```python
# scripts/gaf_daemon.py
import subprocess
import time
import signal

SERVICES = {
    "backend": "python manage.py runserver",
    "celery_worker": "celery -A config worker",
    # ...
}

def start_service(name, cmd):
    return subprocess.Popen(cmd.split())

def stop_service(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

def main():
    running_procs = {}
    
    # 1. 启动所有服务
    for name, cmd in SERVICES.items():
        print(f"Starting {name}...")
        running_procs[name] = start_service(name, cmd)
        
    # 2. 看门狗循环
    try:
        while True:
            for name, proc in running_procs.items():
                if proc.poll() is not None: # 进程已退出
                    print(f"Service {name} died. Restarting...")
                    # 3. 自动重启
                    running_procs[name] = start_service(name, SERVICES[name])
            time.sleep(5)
    except KeyboardInterrupt:
        # 4. 优雅退出
        print("Shutting down all services...")
        for proc in running_procs.values():
            stop_service(proc)

if __name__ == "__main__":
    main()
```

## 5. 测试与验收方案 (Testing & Acceptance)

### 单元测试场景
- **Service 层测试** (`backend/tasks/tests/test_service.py`):
  - **测试点**: 模拟 `TaskService.dispatch_task`。
  - **Mock**: 用 `unittest.mock.patch` 模拟 `Task.objects.get` 和 `TaskExecution.objects.create`。
  - **断言**: 验证当任务存在时，方法返回正确的 `TaskExecution` 对象；当任务不存在时，抛出 `Task.DoesNotExist`。
- **设备发现注册表测试** (`agent/src/devices/discovery/test_registry.py`):
  - **测试点**: 测试 `DeviceDiscoveryRegistry.discover_all`。
  - **Mock**: 创建假的 `MockDiscovery` 类（继承 `BaseDiscovery`），返回预设的设备列表。
  - **断言**: 验证 `discover_all` 返回的设备列表包含所有注册的发现器返回的设备。

### 集成测试场景
- **Agent ↔ Backend LLM RPC 测试** (`backend/gaf_ai/tests/test_ws_rpc.py`):
  - **步骤**:
    1. 启动测试版的 Backend WebSocket 服务器。
    2. 模拟 Agent 连接并发送 `llm.call` 消息。
    3. Backend 接收消息，调用真实的 LLM 服务（或 Mock LLM）。
  - **断言**: 验证 Agent 收到格式正确的 `llm.result` 消息，且 `request_id` 匹配。
- **进程守护测试**:
  - **步骤**:
    1. 启动 `gaf_daemon.py`，它会启动 Backend 进程。
    2. 使用 `psutil` 或 `os.kill` 强制杀死 Backend 进程。
    3. 等待 5 秒。
  - **断言**: Backend 进程应被自动重启，且在任务管理器中可见。
