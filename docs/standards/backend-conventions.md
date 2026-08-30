---
summary: 后端通用规范 — Django/DRF 命名/序列化/权限/响应/测试，约束 AI 写出格式一致的 Python 代码
applies_to: [backend, python, django, drf, celery]
key_decisions:
  - Django app 一个目录一个业务域（accounts/tasks/agents/...），禁止单文件 app
  - 模型字段加 help_text + verbose_name，便于 admin 和 OpenAPI
  - ViewSet 优先用于 CRUD；@api_view 仅用于非 CRUD 业务逻辑（须加 @extend_schema + 注释，见 §4.1）
  - 序列化器用 ModelSerializer（不用 Serializer），嵌套只读字段显式声明
  - 权限类拆细（IsOwner/IsAdmin/HasAPIKey），不用 superuser 单一判断
  - 统一响应格式 { code, message, data }（已实现，通过 GAF_UNIFIED_RESPONSE_ENABLED 开启，默认 False 兼容旧客户端）
  - 错误码统一 4 位（1xxx 通用 / 2xxx 认证 / 3xxx 业务 / 4xxx 限流 / 5xxx 第三方），错误消息走 i18n
  - 异步任务用 Celery + redis broker，长任务必须 ack_late
  - 测试用 pytest-django + factory_boy（factories 位于各 app 的 `factories.py`）
last_updated: 2026-07-22
---

# GAF Backend Conventions

> **强制**：AI 写后端代码前必读。所有 Python/Django/DRF 代码必须遵循本文规范。
>
> **与 .ai-memory/summaries/code-rules.md 边界**:
> - **本文件** = 代码规范 (写什么代码) — Django/DRF 命名/序列化/权限/响应/测试
> - **code-rules.md** = AI 工具规则 (怎么用工具) — SearchReplace/PowerShell/监控控制台/PS7 vs 5.1
> - 两者互补不重叠; 改代码规范查本文件, 改工具使用查 code-rules.md

## 1. 项目结构

```
GAF/                          # 项目根（backend/ agent/ frontend/ 平级）
├── backend/                  # Django project
│   ├── config/               # Django project config
│   │   ├── settings/{base,dev,prod}.py
│   │   ├── urls.py           # 根路由
│   │   ├── celery.py         # Celery 入口
│   │   └── asgi.py / wsgi.py
│   ├── [app_name]/           # 一个业务域一个 app
│   │   ├── migrations/       # Django migrations
│   │   ├── tests/            # pytest 测试
│   │   ├── models.py         # 数据模型
│   │   ├── serializers.py    # DRF 序列化器
│   │   ├── views.py          # ViewSet / APIView
│   │   ├── urls.py           # app 路由
│   │   ├── services.py       # 业务逻辑（可选）
│   │   ├── permissions.py    # 权限类（可选）
│   │   ├── tasks.py          # Celery 任务（可选）
│   │   └── admin.py          # Django admin
│   ├── requirements/{base,dev,prod}.txt
│   ├── manage.py
│   └── pytest.ini
├── agent/                    # 跨平台抽象（与 backend/ 平级，非子目录）
│   └── platforms/{windows,linux,macos}/
└── frontend/                 # React 前端
```

**App 划分规则**：
- ✅ 一业务域一 app（accounts/agents/tasks/monitors/...）
- ✅ 每个 app 至少含 `models.py` `serializers.py` `views.py` `urls.py` `tests/`
- ❌ 不建"工具"app（功能放进对应业务 app 或 `agent/`）

## 2. 模型定义

```python
# ✅ 模型字段必须加 help_text + verbose_name
from django.db import models

class Device(models.Model):
    serial = models.CharField(
        max_length=128,
        unique=True,
        verbose_name="设备序列号",
        help_text="ADB serial 或模拟器端口",
    )
    name = models.CharField(
        max_length=128,
        verbose_name="设备名",
        help_text="用户自定义显示名",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="是否启用",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "设备"
        verbose_name_plural = "设备"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["serial"])]

    def __str__(self):
        return f"{self.name}({self.serial})"

# ❌ 字段无 help_text
class Device(models.Model):
    serial = models.CharField(max_length=128)
```

**规则**：
- 所有字段加 `verbose_name`（admin 显示）+ `help_text`（API 文档）
- 时间字段：`created_at`（auto_now_add）+ `updated_at`（auto_now）
- 字符串字段加 `max_length`
- 必填字段不写 `null=True, blank=True`
- 必加 `class Meta` 含 `verbose_name` + `ordering`
- 高频查询字段加 `indexes` 或 `db_index=True`
- 游标/状态字段示例（2026-08-27 E2E 落地）：`UnattendedSession.rotation_index`（`IntegerField(default=0)` + `verbose_name` + `help_text`），用于 loop_rotation 公平轮换——session 级推进、派发后自增，保证多账户轮流而非总选队首
- 连接/会话指纹字段示例（2026-08-29 服务编排落地）：`Agent.active_channel`（`CharField(max_length=255, null=True, blank=True)` + `verbose_name` + `help_text`），存 Channels `channel_name` 作连接所有权仲裁——heartbeat/offline 写入带 `active_channel` 守卫，僵尸连接 UPDATE 0 行不污染状态；新增连接级状态字段时沿用"连接指纹 + 写入仲裁"模式

## 3. 序列化器

```python
# ✅ ModelSerializer + 显式字段控制
from rest_framework import serializers
from .models import Device

class DeviceSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Device
        fields = ["id", "serial", "name", "owner_name", "status_display",
                  "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_serial(self, value):
        if Device.objects.filter(serial=value).exists():
            raise serializers.ValidationError("serial 已存在")
        return value

# ❌ 继承 Serializer 手撸字段
class DeviceSerializer(serializers.Serializer):
    serial = serializers.CharField()
    # 重复定义 model 字段，易遗漏
```

**规则**：
- 优先 `ModelSerializer`（不用 `Serializer`）
- 嵌套只读字段显式声明 + `source=`（如 `owner_name`）
- 验证方法命名：`validate_<field>` / `validate` (跨字段)
- 不在序列化器里写业务逻辑（业务逻辑放 services.py）
- 写操作（create/update）只暴露必要字段

## 4. 视图（ViewSet）

```python
# ✅ ModelViewSet + 权限类 + 过滤
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Device
from .serializers import DeviceSerializer
from .permissions import IsOwnerOrAdmin

class DeviceViewSet(viewsets.ModelViewSet):
    queryset = Device.objects.select_related("owner").all()
    serializer_class = DeviceSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    filterset_fields = ["is_active", "owner"]
    search_fields = ["name", "serial"]
    ordering_fields = ["created_at", "updated_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_superuser:
            qs = qs.filter(owner=self.request.user)
        return qs

    @action(detail=True, methods=["post"])
    def reboot(self, request, pk=None):
        device = self.get_object()
        device.reboot()
        return Response({"detail": "重启指令已发送"})

# ❌ CRUD-as-function-view（重复样板代码，应使用 ViewSet）
@api_view(["GET", "POST"])
def device_list(request):
    if request.method == "GET":
        ...
    elif request.method == "POST":
        ...

# ✅ Non-CRUD business logic as @api_view (allowed per §4.1)
from drf_spectacular.utils import extend_schema

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@extend_schema(tags=["ai"], summary="Generate pipeline from natural language")
def generate_pipeline(request):
    # @api_view allowed: external LLM service wrapper, not a model CRUD
    ...
```

**规则**：
- 优先 `ModelViewSet`（CRUD 自动生成）
- 自定义动作用 `@action(detail=True/False, methods=[...])`
- `get_queryset()` 做权限过滤
- 用 `filterset_fields` / `search_fields` / `ordering_fields` 暴露给前端
- `select_related` / `prefetch_related` 避免 N+1
- 对单模型的 list/retrieve/create/update/delete 五大操作，**禁止**用 `@api_view` 手写（必须用 ViewSet）

### 4.1 When `@api_view` is allowed

`@api_view` 函数视图**仅**用于以下非 CRUD 场景，且必须同时满足两个硬约束：
(1) 加 `@extend_schema(tags=[...], summary="...")` 装饰器（OpenAPI 文档）；
(2) 在函数体上方加注释 `# @api_view allowed: <reason>` 说明允许理由。

**允许的使用场景**：

| 场景 | 说明 | 典型示例 |
|------|------|---------|
| 非 CRUD 业务逻辑 | 聚合、统计、报表、分析（无对应资源的标准五操作） | `daily_report_view`、`task_stats`、`trend`、`weekly_report` |
| 跨模型操作 | 一个端点涉及多个模型读写，不归属单一资源 | `create_backup`、`restore_backup`、`global_search_view` |
| 外部服务封装 | 调用 LLM / ADB / 子进程等外部服务 | `generate_pipeline`、`ai_chat_view`、`diagnose_view`、`auto_fix_view` |
| 一次性动作端点 | 启停/暂停/恢复/干预等状态机动作，不属于资源 CRUD | `unattended_start_view`、`execution_intervene_view` |
| 自定义响应结构 | 响应非模型序列化器结构（分组、矩阵、Span 树等） | `unattended_status_view`、`list_traces`、`alert_history_view` |
| Singleton Upsert | 单例配置的 get/upsert，非标准集合操作 | `unattended_strategy_view`、`warmup_config_view` |

**禁止的使用场景**：

- ❌ 单模型的 `GET list` + `POST create` + `GET retrieve` + `PUT update` + `DELETE destroy` 用 `@api_view` 手写 → 必须用 `ModelViewSet`
- ❌ 用 `@api_view` 仅仅因为“懒得写 ViewSet” → 必须重构为 ViewSet
- ❌ `@api_view` 函数不加 `@extend_schema` → OpenAPI 文档会缺失该端点

**判断流程**（写视图前必走）：

1. 端点是否操作单一模型的五操作之一？→ 是 → 用 `ModelViewSet`
2. 端点是否是资源上的自定义动作（如 `reboot`）？→ 是 → 用 `ViewSet + @action`
3. 端点是否归以上 6 个允许场景之一？→ 是 → 用 `@api_view` + `@extend_schema` + 注释
4. 都不是 → 重审设计，很可能应该用 ViewSet

**迁移策略**（针对历史 FBV）：
- 纯 CRUD 的 FBV → 逐步重构为 ViewSet（URL 路径保持不变，用 `router.register` 匹配原路径）
- 复杂业务逻辑 FBV → 保留 `@api_view`，补 `@extend_schema` + 允许理由注释
- 模糊的 FBV（如 singleton upsert）→ 保留 `@api_view`，按 §4.1 注明允许理由

### 4.2 When `APIView` is allowed

> **现状**：项目中大量使用 `APIView` 子类（如 `agents/views.py` 有 16 个 `class XxxView(APIView)`）。这些视图用于资源上的非 CRUD 动作端点，是 `@action` 和 `@api_view` 之间的中间层选择。

`APIView` 类视图**仅**用于以下场景，且必须满足硬约束：
(1) 加 `@extend_schema(tags=[...], summary="...")` 装饰器（OpenAPI 文档）；
(2) 类 docstring 说明端点用途和允许理由。

**允许的使用场景**：

| 场景 | 说明 | 典型示例 |
|------|------|---------|
| 资源上的复杂动作端点 | 对单一资源执行非 CRUD 操作，逻辑较复杂需要独立类组织（多 HTTP 方法 / 辅助方法 / 状态管理） | `DeviceScanView`、`DeviceRegisterView`、`DeviceScreenshotView`、`DeviceLockView`、`DeviceUnlockView` |
| 需要请求/响应拦截的端点 | 需要重写 `initial()` / `finalize_response()` / `handle_exception()` 等生命周期方法 | 自定义认证流程、流式响应 |
| 多 HTTP 方法的非 CRUD 端点 | 同一端点需要处理 GET + POST 且语义非标准 CRUD（如 scan 的 GET 触发扫描 + POST 注册） | `DeviceScanView`（GET 扫描 / POST 注册） |

**`APIView` vs `@action` vs `@api_view` 选择流程**：

1. 端点是否操作单一模型的五操作之一？→ 是 → 用 `ModelViewSet`
2. 端点是否是资源上的简单自定义动作（1-2 个方法，逻辑简短）？→ 是 → 用 `ViewSet + @action`
3. 端点是否是资源上的复杂动作（多方法 / 多辅助方法 / 需要生命周期重写）？→ 是 → 用 `APIView` 子类
4. 端点是否归 §4.1 的 6 个非资源场景？→ 是 → 用 `@api_view` + `@extend_schema` + 注释
5. 都不是 → 重审设计，很可能应该用 ViewSet

**禁止的使用场景**：

- ❌ 用 `APIView` 手写单模型的 list/retrieve/create/update/delete → 必须用 `ModelViewSet`
- ❌ `APIView` 子类不加 `@extend_schema` → OpenAPI 文档会缺失该端点
- ❌ 能用 `@action` 一行解决的简单动作拆成独立 `APIView` 类 → 增加无谓的样板代码

## 5. 路由

### 5.1 基本模式

```python
# ✅ app/urls.py — DRF router 自动注册资源路由
from rest_framework.routers import DefaultRouter
from .views import AgentViewSet, DeviceViewSet, DeviceGroupViewSet

router = DefaultRouter()
router.register(r"agents", AgentViewSet, basename="agent")
router.register(r"devices", DeviceViewSet, basename="device")

urlpatterns = [
    path("device-groups/", DeviceGroupViewSet.as_view({...}), name="devicegroup-list"),
    path("", include(router.urls)),
]
```

### 5.2 挂载约定（关键）

**核心原则**：`config/urls.py` 挂载前缀 + `app/urls.py` 资源路径 = 最终 URL，**不允许重复**。

```python
# ✅ 正确：app 定义多个资源 → 挂载在 API 根前缀
# agents app 定义了 /agents/, /devices/, /device-groups/ 三个资源
path(f"{API_PREFIX}/", include("agents.urls")),
# 最终 URL: /api/v2/agents/, /api/v2/devices/, /api/v2/device-groups/

# ✅ 正确：app 定义单资源且 app 名 = 资源名 → 挂载在 app 名前缀
# tasks app 只定义 /tasks/ 资源
path(f"{API_PREFIX}/tasks/", include("tasks.urls")),
# 最终 URL: /api/v2/tasks/

# ❌ 错误：挂载前缀与 app 内资源路径重复 → 产生双重前缀
path(f"{API_PREFIX}/agents/", include("agents.urls")),
# 产生: /api/v2/agents/agents/, /api/v2/agents/devices/ ← 双重前缀！
```

**规则**：
- 每个 app 一个 `urls.py`，用 `DefaultRouter` 注册 ViewSet
- **app 定义多个资源** → 挂载在 `f"{API_PREFIX}/"`（API 根前缀）
- **app 定义单资源且 app 名 = 资源名** → 挂载在 `f"{API_PREFIX}/<app>/"`
- **app 名 ≠ 资源名** → 挂载在 `f"{API_PREFIX}/"`，不要用 app 名做前缀
- 根 `config/urls.py` 包含各 app urls
- URL 前缀：`/api/v2/` 复数（`API_PREFIX = 'api/v2'`）
- **禁止**：挂载前缀与 app 内资源路径重复（产生双重前缀）

## 6. 权限

```python
# ✅ 拆细权限类，按业务组合
from rest_framework import permissions

class IsOwnerOrAdmin(permissions.BasePermission):
    """资源所有者或超管可访问"""
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        return obj.owner == request.user

class HasAPIKey(permissions.BasePermission):
    """Agent 通过 API Key 访问"""
    def has_permission(self, request, view):
        return "X-API-Key" in request.headers

# ViewSet 中组合
permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
```

**规则**：
- 权限类按业务拆细（`IsOwner`/`IsAdmin`/`HasAPIKey`/`ReadOnly`/...）
- 不用单一 `IsAdminUser`，按需组合
- `has_object_permission` 做实例级检查（GET/PUT/DELETE）
- `has_permission` 做视图级检查（list/create）

## 7. 响应格式

> **现状**：默认仍使用 DRF 默认响应格式（`{ count, next, previous, results }` 分页 / 裸对象详情）。
> 统一响应格式已实现并通过 `GAF_UNIFIED_RESPONSE_ENABLED` 开关控制（默认 `False` 以保持旧客户端兼容）。开启后所有 JSON 响应包装为 `{ code, message, data }`。

**DRF 默认响应**（未开启统一格式时）：
```json
{
  "count": 156,
  "next": "...",
  "previous": null,
  "results": [...]
}
```

**统一成功响应**（开启 `GAF_UNIFIED_RESPONSE_ENABLED=True`）：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "count": 156,
    "next": "...",
    "previous": null,
    "results": [...]
  }
}
```

**实现位置**：
- 辅助函数：`gaf_core/responses.py` — `unified_response(...)`
- 中间件：`gaf_core/middleware.py` — `UnifiedResponseMiddleware`
- 开关：`config/settings/base.py` — `GAF_UNIFIED_RESPONSE_ENABLED`

**规则**：
- 列表响应：`{ count, next, previous, results }`（DRF PageNumberPagination，未开启统一格式时）
- 详情响应：裸对象 `{ id, name, ... }`（未开启统一格式时）
- 开启统一格式后：成功 `{ code: 0, message: "ok", data: <payload> }`，失败 `{ code: 4xxx, message, data: null }`
- 中间件跳过已携带 `{ code, message, data }` 的响应，避免重复包装

## 8. 错误处理

> **现状**：默认仍使用 DRF 默认异常处理（`{ detail: "..." }` + HTTP 状态码）。
> 自定义业务异常 + 4 位错误码已实现，同样通过 `GAF_UNIFIED_RESPONSE_ENABLED` 控制是否接管错误响应。

**自定义业务异常**（`gaf_core/exceptions.py`）：
```python
from gaf_core.exceptions import BusinessException
from gaf_core.error_codes import ErrorCode

if not device.is_online():
    raise BusinessException(
        detail="device is offline",
        code=ErrorCode.DEVICE_OFFLINE,
        status_code=400,
    )
```

**统一异常处理器**（`gaf_core/exceptions.py`）：
- 安装位置：`REST_FRAMEWORK["EXCEPTION_HANDLER"] = "gaf_core.exceptions.unified_exception_handler"`
- 仅在 `GAF_UNIFIED_RESPONSE_ENABLED=True` 时包装错误；默认保持 DRF 原生格式
- 标准 DRF 异常映射到 4 位错误码（见 `gaf_core/error_codes.py`）

**规则**：
- 用 DRF 内置异常处理常规校验/权限/404
- 业务语义错误用 `BusinessException` + `ErrorCode`
- 错误消息优先走 i18n（后端使用 Django 翻译框架）

## 9. 异步任务（Celery）

```python
# ✅ tasks/app_name/tasks.py
from celery import shared_task

@shared_task(bind=True, max_retries=3, acks_late=True)
def reboot_device(self, device_id: int):
    try:
        device = Device.objects.get(id=device_id)
        device.reboot()
    except Device.DoesNotExist:
        # 不重试业务异常
        logger.error(f"Device {device_id} not found")
        return
    except Exception as exc:
        # 网络/IO 异常重试
        raise self.retry(exc=exc, countdown=10)

# 调用
reboot_device.delay(device.id)
```

**规则**：
- 异步任务放 `app/tasks.py`
- 必须 `acks_late=True`（防 worker 崩溃丢任务）
- `max_retries=3` + `countdown=10` 退避
- 业务异常（数据不存在）不重试，IO 异常重试
- 任务必须有 logger

## 10. 测试

> **现状**：当前用 pytest + pytest-django + factory_boy，测试数据优先用 factory_boy factories，遗留 pytest fixtures 逐步迁移。

```
backend/
├── [app_name]/
│   ├── factories.py       # factory_boy factories（按 app 拆分）
│   └── tests/
│       ├── __init__.py
│       ├── test_models.py
│       ├── test_api.py
│       └── test_services.py
└── tests/
    ├── conftest.py         # 全局 fixture + factory fixtures
    └── test_integration.py
```

**factory 写法**：
```python
import factory
from accounts.models import User

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    role = User.Role.VIEWER
    password = factory.PostGenerationMethodCall("set_password", "testpass123")


class AdminUserFactory(UserFactory):
    role = User.Role.ADMIN
```

**测试中使用 factory**：
```python
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory, OperatorUserFactory
from agents.factories import AgentFactory, DeviceFactory

class TestDeviceApi(TestCase):
    def setUp(self):
        self.operator = OperatorUserFactory()
        self.device = DeviceFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)
```

**全局 pytest fixtures**（`backend/conftest.py`）：
```python
import pytest
from accounts.factories import AdminUserFactory, OperatorUserFactory, UserFactory
from agents.factories import AgentFactory, DeviceFactory
from tasks.factories import TaskFactory, TaskExecutionFactory

@pytest.fixture
def admin(db):
    return AdminUserFactory()

@pytest.fixture
def operator(db):
    return OperatorUserFactory()

@pytest.fixture
def device(db):
    return DeviceFactory()

@pytest.fixture
def task_execution(db):
    return TaskExecutionFactory()
```

**规则**：
- 框架：pytest + pytest-django + factory_boy
- factory 文件：`app/factories.py`，按模型拆分
- 测试文件：`app/tests/test_<module>.py`
- 全局 fixture 在 `tests/conftest.py`（优先复用 factory）
- DB fixture 默认 `scope="function"`（测试隔离）
- API 测试用 `APIClient` + `force_authenticate`
- 覆盖率：核心业务 ≥ 80%
- 新增测试优先用 factory，不再新增 `User.objects.create_user` 的重复样板

## 11. 跨平台抽象（agent/）

```python
# ✅ device_bridge/platforms/base.py — 三个独立 ABC（截图 / 输入 / 设备发现）
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class ScreenshotResult:
    """截图操作结果"""
    image_bytes: bytes = b''
    latency_ms: float = 0.0
    fps: float = 0.0
    resolution: dict = field(default_factory=lambda: {'width': 0, 'height': 0})
    method: str = ''
    success: bool = False
    error: str | None = None

@dataclass
class InputResult:
    """输入操作结果"""
    success: bool = False
    latency_ms: float = 0.0
    method: str = ''
    error: str | None = None

@dataclass
class DeviceInfo:
    """发现的设备信息（统一格式，跨平台通用）"""
    name: str
    device_type: str  # 'window' | 'emulator' | 'adb'
    identifier: str   # hwnd / adb_serial / window_id
    resolution: dict = field(default_factory=lambda: {'width': 0, 'height': 0})
    platform: str = ''  # 'windows' | 'macos' | 'linux'
    extra: dict = field(default_factory=dict)

class PlatformScreenshotHandler(ABC):
    """截图处理器抽象基类"""
    @abstractmethod
    def available_methods(self) -> list[str]: ...
    @abstractmethod
    def capture(self, target: str, method: str = '') -> ScreenshotResult: ...
    @abstractmethod
    def benchmark(self, target: str, method: str, rounds: int = 10) -> dict: ...

class PlatformInputHandler(ABC):
    """输入处理器抽象基类"""
    @abstractmethod
    def available_methods(self) -> list[str]: ...
    @abstractmethod
    def click(self, target: str, x: int, y: int, method: str = '') -> InputResult: ...
    @abstractmethod
    def swipe(self, target: str, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int = 300, method: str = '') -> InputResult: ...
    @abstractmethod
    def key_press(self, target: str, key: str, method: str = '') -> InputResult: ...
    @abstractmethod
    def scroll(self, target: str, x: int, y: int, delta: int,
               method: str = '') -> InputResult: ...

class PlatformDeviceDiscoverer(ABC):
    """设备发现器抽象基类（位于 device_bridge/discovery/ 模块）"""
    @abstractmethod
    def discover_windows(self) -> list[DeviceInfo]: ...
    @abstractmethod
    def discover_emulators(self) -> list[DeviceInfo]: ...
    @abstractmethod
    def discover_adb_devices(self) -> list[DeviceInfo]: ...

# device_bridge/platforms/windows/screenshot.py — Windows 截图实现
class WindowsScreenshotHandler(PlatformScreenshotHandler):
    def capture(self, target: str, method: str = '') -> ScreenshotResult:
        # BitBlt / PrintWindow / DXGI (支持 hwnd crop, TD-124)
        # backend WGC mock 已删除 (TD-125), _capture_wgc delegate 到 PrintWindow
        # agent 端 worker/src/platforms/windows/wgc.py 保留真实 WGC 实现
        ...

# device_bridge/discovery/windows.py — Windows 设备发现实现
class WindowsDeviceDiscoverer(PlatformDeviceDiscoverer):
    def discover_windows(self) -> list[DeviceInfo]:
        ...

# 业务代码通过 registry 选平台
from device_bridge.platforms.registry import get_screenshot_handler, get_input_handler
screenshot = get_screenshot_handler()  # 自动检测当前 OS
screenshot.capture(hwnd, method='printwindow')
```

**规则**：
- 平台无关代码只调 `device_bridge.platforms.base` 定义的接口
- 截图、输入、设备发现是**三个独立的 ABC**，不要合并为单一 `PlatformBase`
  - `PlatformScreenshotHandler`：`available_methods()` / `capture()` / `benchmark()`
  - `PlatformInputHandler`：`available_methods()` / `click()` / `swipe()` / `key_press()` / `scroll()`
  - `PlatformDeviceDiscoverer`：`discover_windows()` / `discover_emulators()` / `discover_adb_devices()`（实现在 `device_bridge/discovery/` 模块）
- 平台实现：`device_bridge/platforms/{windows,linux,macos}/`
- 业务代码不直接 `import` Win32 API / X11 / Cocoa
- 新增平台必须先实现对应 ABC 的所有抽象方法

### 11.1 Multi-game 模式安全白名单约束 (Spec A)

**背景**: Spec A 引入 `FeatureFlag.unattended_multi_game_mode` + `resolve_device_methods` 白名单降级, 多游戏并行时禁用非 hwnd-isolated 方法防止串台。

**硬约束**:
- ✅ 所有 device method 选择逻辑必须走 `resolve_device_methods()`, 不允许在 views / serializers / consumers 中另写方法判断
- ✅ 修改 `MULTI_GAME_SAFE_SCREENSHOT_METHODS` / `MULTI_GAME_SAFE_INPUT_METHODS` / `MULTI_GAME_BLOCKED_SCREENSHOT_METHODS` / `MULTI_GAME_BLOCKED_INPUT_METHODS` 常量时, 必须同步更新 `DeviceSerializer.allowed_screenshot_methods` / `allowed_input_methods` 字段
- ✅ `unattended_start_view` 必须检查 `is_multi_game_mode_enabled()` + `original_input_method` 强制 operator 显式 rebind (Spec A safety gate 400)
- ✅ 白名单方法标识符使用小写 (Spec A Phase 2 fix): `'printwindow'` / `'bitblt'` / `'gdi'` / `'postmessage'` / `'sendmessage'` / `'adb'` / `'adb_input'` / `'sendevent'` / `'screencap'` / `'screencap_png'` / `'nemuipe'` / `'bluestacks'` / `'droidcast'` / `'ld_opengl'`
- ❌ 禁止绕过 `is_multi_game_mode_enabled()` 检查直接调用 device method
- ❌ 禁止在 `WINDOWS_METHODS` 中重新加入 'WGC' (TD-125, backend WGC 是 mock)
- ❌ 禁止在 `MULTI_GAME_SAFE_SCREENSHOT_METHODS` 中加入 'wgc' / 'dxgi' / 'sendinput' / 'pseudobackground' / 'minitouch' / 'maatouch' (这些方法依赖全局状态或截全桌面, 多游戏并行会串台)

参考: `backend/agents/models.py` 常量定义 + `backend/agents/services.py` `resolve_device_methods()` 实现

### 11.2 Win32 消息坐标约定 (Spec B / TD-122)

**背景**: Win32 不同消息的 lParam 坐标空间不同, Spec B 修复了 backend PostMessage 4 个非 scroll 方法误调 `_client_to_screen` 的 bug。

**坐标空间规则**:

| 消息 | lParam 坐标空间 | 是否调 `_client_to_screen` |
|------|----------------|--------------------------|
| `WM_LBUTTONDOWN` / `WM_LBUTTONUP` | client | ❌ 不调 |
| `WM_RBUTTONDOWN` / `WM_RBUTTONUP` | client | ❌ 不调 |
| `WM_MBUTTONDOWN` / `WM_MBUTTONUP` | client | ❌ 不调 |
| `WM_MOUSEMOVE` | client | ❌ 不调 |
| `WM_MOUSEWHEEL` | screen | ✅ 调 `_client_to_screen` |
| SendInput (`mouse_event` / `SetCursorPos`) | screen 绝对坐标 | ✅ 调 `_client_to_screen` |

**硬约束**:
- ✅ 新增 PostMessage / SendMessage 路径前, 必须先查 Win32 文档确认消息的 lParam 坐标空间
- ✅ 4 个非 scroll 方法 (`_postmessage_click` / `_sendmessage_click` / `_postmessage_swipe` / `_sendmessage_swipe`) 直接 pack client 坐标, 不调 `_client_to_screen`
- ✅ 2 个 scroll 方法 (`_postmessage_scroll` / `_sendmessage_scroll`) 保留 `_client_to_screen` (WM_MOUSEWHEEL 例外)
- ❌ 禁止在非 scroll 路径加 `_client_to_screen` (会引入 TD-122 同类 bug)
- ❌ 禁止用 `_make_lparam(screen_x, screen_y)` 命名误导 (应直接 `_make_lparam(x, y)` + docstring 注明坐标空间)

参考: `backend/device_bridge/platforms/windows/input.py` 实现

## 12. 数据库迁移

```python
# ✅ 写 migration 时加 RunPython 兼容旧数据
from django.db import migrations, models

def set_default_status(apps, schema_editor):
    Device = apps.get_model("agents", "Device")
    for device in Device.objects.filter(status__isnull=True):
        device.status = "unknown"
        device.save()

class Migration(migrations.Migration):
    dependencies = [("agents", "0005_add_status")]
    operations = [
        migrations.AddField(
            model_name="device",
            name="status",
            field=models.CharField(default="unknown", max_length=32),
        ),
        migrations.RunPython(set_default_status, migrations.RunPython.noop),
    ]
```

**规则**：
- 必填字段加 `default` 或 `null=True`
- 旧数据迁移用 `RunPython` 显式处理
- 不删除已合并的 migration 文件
- 大表 ALTER 拆 batch（避免长时间锁表）

## 13. 日志与配置

```python
# ✅ 每个模块独立 logger
import logging
logger = logging.getLogger(__name__)

# ✅ 配置走环境变量 + django-environ
# config/settings/base.py
import environ
env = environ.Env()
DEBUG = env.bool("DEBUG", default=False)
DATABASE_URL = env("DATABASE_URL")

# ❌ 硬编码配置
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",  # 2026-08-03 已移除 PG, dev/prod 统一 SQLite+WAL
        "NAME": "gaf_prod",  # 写死
    }
}
```

**规则**：
- 每个 .py 文件：`logger = logging.getLogger(__name__)`
- 关键路径（创建/删除/支付/权限）必加 INFO/WARN 日志
- 配置 12-factor：环境变量 + `django-environ`
- ❌ 禁止硬编码密钥/URL/端口

## 14. 禁止清单

- ❌ `print()` 调试（用 logger）
- ❌ `try: ... except: pass` 静默吞错
- ❌ 业务代码里 `import` 平台特定库（用 device_bridge.platforms 抽象）
- ❌ Migration 里改数据不加 default（必填字段会卡住）
- ❌ 用 `datetime.now()`（用 `django.utils.timezone.now()` 带时区）
- ❌ 序列化器里写业务逻辑（放 services.py）

---

**维护者**：AI（不人工维护）
**变更触发**：修改任何后端代码 → 检查本规范是否需要更新 → 同步 `last_updated`
**验证**：`ruff check` + `mypy` + `pytest`
