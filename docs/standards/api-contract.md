---
summary: 前后端接口契约 — URL 约定/请求/响应/错误码/分页/类型共享/版本控制，约束 AI 写出一致的 API
applies_to: [frontend, backend, api-contract, rest]
last_updated: 2026-07-27
key_decisions:
  - URL 用复数名词 + kebab-case：/api/v2/devices/, /api/v2/agent-instances/
  - 路径以 / 结尾（DRF 默认行为）
  - 当前响应格式：DRF 默认分页 { count, next, previous, results }（统一 { code, message, data } 已实现，通过 GAF_UNIFIED_RESPONSE_ENABLED 开启，默认 False 兼容旧客户端）
  - 错误码 4 位：1xxx 通用 / 2xxx 认证 / 3xxx 业务 / 4xxx 限流（已实现 gaf_core/error_codes.py，统一异常处理器接管 DRF 异常）
  - TypeScript 类型优先使用 OpenAPI 自动生成（frontend/src/types/api.generated.ts），通过 npm run generate:api-types 同步；手写类型在 types/models/ 仅作遗留兼容
  - 列表分页用 page+page_size（不用 offset/limit），默认 page_size=20
  - 时间戳统一 ISO 8601 UTC（"2026-06-15T08:30:00Z"），前端转本地时区
  - WebSocket /ws/<channel>/ 路径，消息用 JSON 帧 { type, data }（接收兼容 payload）
  - API 版本在 URL：当前 /api/v2/...（v2 在 path prefix）
  - 写操作幂等：POST 创建返回 201，PUT 替换 200/204，PATCH 部分更新 200
  - 鉴权：Bearer JWT (前端 REST) / Agent Token (WebSocket, ?token= 或 Sec-WebSocket-Protocol 子协议)，refresh token 走 /api/v2/accounts/auth/refresh/
---

# GAF API Contract

> **强制**：AI 写接口（前后端）前必读。所有 REST/WS API 必须遵循本文契约。
> 配套：`docs/standards/frontend-conventions.md` + `docs/standards/backend-conventions.md`

## 1. URL 命名

```
✅ 正确
GET    /api/v2/devices/              # 列表
POST   /api/v2/devices/              # 创建
GET    /api/v2/devices/{id}/         # 详情
PUT    /api/v2/devices/{id}/         # 替换
PATCH  /api/v2/devices/{id}/         # 部分更新
DELETE /api/v2/devices/{id}/         # 删除
POST   /api/v2/devices/{id}/reboot/  # 自定义动作

❌ 错误
GET  /api/v2/device               # 单数
GET  /api/v2/agents/getDevice    # 动词
GET  /api/v2/agents/device_list   # snake_case
```

**规则**：
- 资源名用**复数**（devices/tasks/agents/...）
- 命名风格：`kebab-case`（multi-word：`agent-instances`）
- 路径以 `/` 结尾（DRF 默认）
- 自定义动作用动词：`/reboot/`, `/cancel/`, `/pause/`
- 嵌套资源：`/api/v2/devices/{id}/screenshots/`（不超 2 层嵌套）

## 2. HTTP 方法语义

| 方法 | 用途 | 成功状态码 | 幂等 |
|------|------|----------|------|
| GET | 读取（list/detail） | 200 | ✅ |
| POST | 创建 / 自定义动作 | 201 (创建) / 200 (动作) | ❌ |
| PUT | 完整替换 | 200 / 204 | ✅ |
| PATCH | 部分更新 | 200 | ❌ |
| DELETE | 删除 | 204 | ✅ |

**规则**：
- 创建成功返回 201 + 资源 URL（`Location` header）
- 自定义动作（reboot/cancel）返回 200 + 结果
- DELETE 不返回 body（204）
- GET 请求绝不修改状态

## 3. 响应格式

> **现状**：默认仍使用 DRF 默认分页格式 `{ count, next, previous, results }`。统一响应格式已实现并通过 `GAF_UNIFIED_RESPONSE_ENABLED` 开关控制（默认 `False` 以保持旧客户端兼容）。开启后所有 JSON 响应包装为 `{ code, message, data }`。

### 3.1 当前成功响应（DRF 默认，未开启统一格式时）

```json
{
  "count": 156,
  "next": "http://localhost:8000/api/v2/devices/?page=2",
  "previous": null,
  "results": [
    { "id": 1, "name": "..." }
  ]
}
```

### 3.2 统一成功响应（开启 `GAF_UNIFIED_RESPONSE_ENABLED=True`）

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "count": 156,
    "next": "http://localhost:8000/api/v2/devices/?page=2",
    "previous": null,
    "results": [
      { "id": 1, "name": "..." }
    ]
  }
}
```

### 3.3 错误响应

未开启统一格式时返回 DRF 默认错误格式 + HTTP 状态码。开启后统一为 4 位错误码：

| 范围 | 含义 | 示例 |
|------|------|------|
| 0 | 成功 | 0 |
| 1xxx | 通用错误 | 1000 服务器内部错误 / 1001 参数无效 / 1002 资源不存在 / 1003 权限不足 |
| 2xxx | 认证/授权 | 2001 未登录 / 2002 token 过期 / 2003 token 无效 / 2010 无 API Key |
| 3xxx | 业务错误 | 3001 设备离线 / 3002 任务冲突 / 3010 资源包未启用 / 3050 用量超限 |
| 4xxx | 限流/熔断 | 4001 请求过快 / 4002 配额耗尽 |
| 5xxx | 第三方错误 | 5001 LLM 服务不可用 / 5010 ADB 执行失败 |

**分页规则**（已实现）：
- 用 `?page=N&page_size=M` 不用 `offset/limit`
- 默认 `page=1`, `page_size=20`
- 最大 `page_size=100`（超出返回 400）

## 4. 请求 / 响应头

### 4.1 通用请求头

```http
Authorization: Bearer <jwt_token>          # 用户认证（前端 REST）
Content-Type: application/json
Accept-Language: zh-CN                      # 国际化
X-Request-ID: <uuid>                       # 链路追踪
```

### 4.2 通用响应头

```http
Content-Type: application/json; charset=utf-8
X-Request-ID: <uuid>                       # 与请求对应
X-RateLimit-Limit: 100                     # 限流信息
X-RateLimit-Remaining: 95
```

## 5. 鉴权

### 5.1 前端用户：JWT

```http
# 登录
POST /api/v2/accounts/auth/login/
{ "username": "admin", "password": "..." }
→ 200 { "access": "...", "refresh": "..." }

# 访问受保护资源
GET /api/v2/devices/
Authorization: Bearer <access_token>

# 刷新 token
POST /api/v2/accounts/auth/refresh/
{ "refresh": "..." }
→ 200 { "access": "..." }

# 登出
POST /api/v2/accounts/auth/logout/
{ "refresh": "..." }
→ 204
```

**规则**：
- `access` token 寿命：15 分钟
- `refresh` token 寿命：7 天
- `access` 过期返 401，前端自动 refresh
- 401 仍不成功（refresh 也过期）→ 跳登录

### 5.2 Agent：Agent Token（WebSocket）

```http
# Agent 通过 WebSocket 连接后端控制信令通道
ws://127.0.0.1:8000/ws/protocol/agents/?token=<agent_token>

# 或通过 Sec-WebSocket-Protocol 子协议传递 token
Sec-WebSocket-Protocol: bearer.<agent_token>
```

**规则**：
- Agent 默认连接 `ws://127.0.0.1:8000/ws/protocol/agents/`（见 `agent/src/__main__.py`）
- 鉴权走 `TokenAuthMiddleware`（见 `backend/protocol/middleware.py`）：从 `?token=` query string 或 `Sec-WebSocket-Protocol` 子协议提取 Agent Token
- Token 经 `hash_token` 后与 `Agent.token_hash` 比对校验
- 校验失败关闭连接（WebSocket close code 4003）
- 本地 Agent（`is_local=True` + 来源 127.0.0.1）可经 `GAF_ALLOW_LOCALHOST_BYPASS=1` 免 Token 连接（默认关闭）

## 6. 时间与时区

**后端存储**：UTC + `DateTimeField`（带时区）

**API 传输**：ISO 8601 UTC 字符串
```json
{
  "created_at": "2026-06-15T08:30:00Z",
  "scheduled_at": "2026-06-15T12:00:00+08:00"
}
```

**前端展示**：用 `dayjs` / `date-fns` 转本地时区
```typescript
import dayjs from 'dayjs';
dayjs(device.created_at).format('YYYY-MM-DD HH:mm');  // 用户本地时间
```

**规则**：
- 后端永远存 UTC
- API 传输 ISO 8601 字符串（必带时区后缀 `Z` 或 `+08:00`）
- 前端不存时间，只展示

## 7. 文件上传 / 下载

### 7.1 资源包扫描 / 新建

```http
# 扫描 resources/ 目录下的子文件夹，将未导入的资源包注册到数据库
POST /api/v2/resources/resource-packs/scan/
Content-Type: application/json

# 新建资源包（自动生成目录结构和 manifest.json）
POST /api/v2/resources/resource-packs/create/
Content-Type: application/json

{
  "name": "pack-001",
  "version": "1.0",
  "target_app": "game-x",
  "description": "资源包描述"
}
```

**规则**：
- 资源包扫描走 `/api/v2/resources/resource-packs/scan/`（`scan_packs` action）
- 资源包新建走 `/api/v2/resources/resource-packs/create/`（`create_pack` action，返回 201）
- 图片/截图走 `/api/uploads/` 统一入口

### 7.2 下载

```http
GET /api/v2/resources/resource-packs/<pk>/export/
  200 application/zip
Content-Disposition: attachment; filename="pack-v1.0.gafpack"
```

### 7.3 模板匹配预览（R37-P2, 2026-08-28）

```http
POST /api/v2/resources/template-match-preview/
Content-Type: application/json
Authorization: Bearer <access-token>

{
  "image_base64": "<裸 base64 或 data URL>",      # 设备实时截图帧
  "template_base64": "<裸 base64 或 data URL>",   # 标注裁剪/资源包模板
  "threshold": 0.8                                 # 可选，置信度阈值
}
```

- 返回 `{"matches": [{"x","y","w","h","confidence"}...]}`（图片像素坐标系，最多 5 个，NMS 去重叠）
- 后端 `cv2.matchTemplate (TM_CCOEFF_NORMED)`；模板大于截图 / 解码失败返回 400
- 前端标注页"匹配预览"调用；后端不可用时前端回退原 mock 并提示

## 8. 批量操作

```http
POST /api/v2/devices/batch_update/
{
  "ids": [1, 2, 3],
  "action": "reboot"
}
→ 200 {
  "succeeded": [1, 2],
  "failed": [{"id": 3, "message": "设备离线"}]
}
```

**规则**：
- 批量上限 100 个 / 请求
- 响应含 `succeeded` + `failed`（不全成功不报错）

## 9. WebSocket

> **v9.4 (2026-07-19, spec-39 Phase 3)** — 同步 C-048 (legacy /ws/agents/ 删除) + C-063 (ExecutionConsumer + ScreenshotStreamConsumer 删除); 5 active WS routes (与 backend/config/asgi.py 1:1 对齐)

### 9.1 端点 (5 active, 见 `backend/config/asgi.py` + 各 app `routing.py`)

```
/ws/protocol/agents/                          # AgentConsumer (protocol/routing.py) — Agent ↔ 后端控制信令 (C-048 后唯一 agent 信令通道)
/ws/dashboard/                                # FrontendConsumer (protocol/routing.py) — 后端推送任务/截图/执行步骤事件给前端 (C-063 后接管 screenshot_frame + execution_step_update)
/ws/logs/                                     # LogStreamConsumer (protocol/routing.py) — 全局日志流 (LogEntry 实时推送, 配合 gaf_core/handlers.DatabaseLogHandler)
/ws/notifications/                            # NotificationConsumer (notifications/routing.py) — 全局通知 (TD-200 2026-07-18 从 executions/routing.py 迁入)
/ws/devices/{device_id}/adb-logs/             # AdbLogStreamConsumer (agents/routing.py) — ADB logcat 实时流
```

**已删除端点** (代码已清, docs 同步):
- ~~`/ws/agents/`~~ — legacy (2026-07-19 spec-29c C-048 删除, 改走 `/ws/protocol/agents/`)
- ~~`/ws/clients/`~~ — 历史规划, 未实现
- ~~`/ws/devices/{device_id}/screenshot-stream/`~~ — ScreenshotStreamConsumer (2026-07-19 spec-35 Phase 4.2 C-063 删除, 前端通过 `/ws/dashboard/` 收 screenshot_frame)
- ~~`/ws/executions/{execution_id}/`~~ — ExecutionConsumer (2026-07-19 spec-35 Phase 4.1 C-063 删除, executions/routing.py + executions/consumers.py 已删; executions app 现 REST only)

### 9.2 消息格式

```json
// 服务端 → 客户端
{
  "type": "screenshot.frame",
  "data": {
    "device_id": "device-001",
    "image": "base64...",
    "ts": "2026-06-15T08:30:00Z"
  }
}

// 客户端 → 服务端（订阅）
{
  "action": "subscribe",
  "channel": "screenshot",
  "params": { "device_id": "device-001" }
}

// 客户端 → 服务端（业务消息，兼容旧格式）
{
  "type": "ping",
  "data": {},
  "timestamp": "2026-06-15T08:30:00Z"
}
```

**规则**：
- 路径前缀 `/ws/`
- 服务端 → 客户端消息必须含 `type` 字段，业务数据放在 `data` 字段
  - `data` 是规范字段（A008-A010 修订：原规范写 `payload`，但代码库主体使用 `data`，此处更新为承认 `data` 为合法字段）
  - 后端反序列化时同时接受 `data` 和 `payload`（向后兼容，见 `protocol/serializers.py` + `agents/consumers.py` 各 `data.get('data') or data.get('payload', {})` 模式）
  - 新代码发送用 `data`，接收兼容 `payload`
- 客户端发送订阅消息用 `{ action: "subscribe"/"unsubscribe", channel, params }` 格式
- 客户端发送业务消息用 `{ type, data, timestamp }` 格式（`timestamp` 可选）
- 鉴权：通过 `Sec-WebSocket-Protocol` 子协议 `access.<jwt>` 传递（C8 修复，避免 token 泄漏到 URL 日志/历史/Referrer）；旧客户端可降级到 URL query `?token=<jwt>`

## 10. 限流

> **现状**：已配置基础限流（`backend/config/settings/base.py:166-174`）：
> - `AnonRateThrottle`: anon = `60/min`
> - `UserRateThrottle`: user = `300/min`
> - `login` scope = `5/min`（登录端点防爆破）
>
> 以下为未来调整目标（🔧 规划中），当前未启用。

```http
# 触发限流（已实现 anon/user/login, 规划中扩展到 IP/Agent 维度）
HTTP/1.1 429 Too Many Requests
{
  "detail": "请求过快",
  "retry_after": 60
}
```

**未来调整目标**：
- 用户级：1000 请求/小时（当前 300/min 已够用，可视情况上调）
- IP 级：100 请求/秒（防扫描，当前未启用）
- Agent：500 请求/分钟（当前走 user scope 300/min，未来按 agent 维度单独限流）

## 11. 版本控制

**当前策略**：URL 前缀

```
/api/v2/devices/      # 当前 v2
/api/v3/devices/      # 未来 v3（重大变更时开启）
```

**规则**：
- 当前生产版本为 v2（`API_PREFIX = 'api/v2'`）
- v2 在生产期间**只加不减**
- 重大变更（如响应格式）→ 开 v3
- 废弃 API 在响应头加 `Deprecation: true` + `Sunset: <date>`

## 12. 前后端类型共享

> **现状**：OpenAPI 自动生成类型已落地。前端优先使用 `frontend/src/types/api.generated.ts`，通过 `npm run generate:api-types` 从 DRF Spectacular schema 生成。
> 手写类型保留在 `frontend/src/types/models/` 仅作遗留兼容，新代码应避免新增手写 model 类型。

**类型生成命令**：
```bash
# 一键生成（脚本会自动先跑 Django spectacular 输出 JSON schema，再调 openapi-typescript）
cd frontend
npm run generate:api-types
```

生成产物：
- `frontend/src/types/api.generated.ts`：原始生成文件，**禁止手动修改**。
- `frontend/src/types/api.ts`：稳定命名空间导出（`export type * as API from './api.generated'`），业务代码从这里导入。

**使用示例**：
```typescript
import type { API } from '@/types/api';

type User = API.components['schemas']['User'];
type TaskListResponse = API.paths['/api/v2/tasks/']['get']['responses']['200']['content']['application/json'];
```

**规则**：
- ✅ 后端改 serializer/model 后，重新运行 `npm run generate:api-types` 同步前端类型
- ✅ 新组件/Hook 优先使用 `API.components['schemas']['Xxx']`
- ❌ 不再新增手写 `interface Device` 等 model 类型
- ❌ 禁止直接编辑 `api.generated.ts`
- ⚠️ **注意**：`API` 是 `export type * as API` 创建的 namespace binding，**不能**用 `API['components']` (indexed access) — TypeScript 6.0+ 报 `TS2709: Cannot use namespace 'API' as a type`。必须用 `API.components` (dotted member access) 取出 interface，再对 interface 用 indexed access `['schemas']['X']`。

## 13. OpenAPI 文档

```python
# 后端用 drf-spectacular 自动生成（已实现）
# config/urls.py
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path(f"{API_PREFIX}/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(f"{API_PREFIX}/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
]
```

**规则**：
- 访问 `/api/v2/docs/` 看 Swagger UI
- 所有 ViewSet / APIView 加 `@extend_schema` 注解
- 自动生成的 schema 必含：tags / summary / parameters / responses
- schema 变更后同步运行 `npm run generate:api-types`，保持前端类型最新

## 14. 禁止清单

- ❌ URL 用动词（`/getDevice`, `/createTask`）
- ❌ URL 用单数（`/device` 改 `/devices`）
- ❌ 时间戳用 Unix epoch 数字（用 ISO 8601 字符串）
- ❌ WebSocket 心跳用 ping/pong 帧（用业务消息 `{ type: "ping" }`）
- ❌ 手写 `interface` 跟后端 model 漂移（优先用 `npm run generate:api-types` 生成类型）
- ❌ 直接编辑 `frontend/src/types/api.generated.ts`

## 15. 资源字段取值约定 (Spec A-E)

### 15.1 Device.screenshot_method 合法取值

| 取值 | 平台 | 状态 | 备注 |
|------|------|------|------|
| `auto` | Windows + ADB | ✅ | handler 自动选最佳 |
| `printwindow` / `PrintWindow` | Windows | ✅ safe | hwnd-isolated |
| `bitblt` / `BitBlt` | Windows | ✅ safe | hwnd-isolated |
| `gdi` / `GDI` | Windows | ✅ safe | delegate 到 BitBlt |
| `dxgi` / `DXGI` | Windows | ✅ blocked in multi | 支持 hwnd crop (Spec E TD-124); 但仍依赖全桌面 AcquireNextFrame, 保守 blocked |
| `wgc` / `WGC` | Windows | ⚠️ delegate | backend WGC mock 已删除 (Spec E TD-125), `_capture_wgc` delegate 到 PrintWindow; agent 端 WGC 仍真实可用 |
| `screencap` / `screencap_png` | ADB | ✅ safe | serial-isolated |
| `nemuipe` / `bluestacks` / `droidcast` / `ld_opengl` | ADB | ✅ safe | serial-isolated |

### 15.2 Device.input_method 合法取值

| 取值 | 平台 | 状态 | 备注 |
|------|------|------|------|
| `auto` | Windows + ADB | ✅ | handler 自动选最佳 |
| `postmessage` / `PostMessage` | Windows | ✅ safe | hwnd-isolated, client 坐标 (Spec B TD-122) |
| `sendmessage` / `SendMessage` | Windows | ✅ safe | hwnd-isolated, client 坐标 (Spec B TD-122) |
| `sendinput` / `SendInput` | Windows | ⚠️ blocked in multi | 实例级 RLock 串行化 (Spec C TD-121); 依赖全局前台/光标, multi 模式 downgrade |
| `pseudobackground` / `PseudoBackground` | Windows | ⚠️ blocked in multi | RLock 串行化 (Spec C TD-121); 临时前台化, multi 模式 downgrade |
| `adb` / `adb_input` | ADB | ✅ safe | serial-scoped subprocess |
| `sendevent` | ADB | ✅ safe | serial-scoped |
| `minitouch` | ADB | ⚠️ blocked in multi | 动态端口分配 (Spec D TD-123); 保守 blocked, multi 模式 downgrade 到 PostMessage |
| `maatouch` | ADB | ⚠️ blocked in multi | 动态端口分配 (Spec D TD-123); 保守 blocked, multi 模式 downgrade |

### 15.3 Device.control_mode 合法取值

| 取值 | 说明 |
|------|------|
| `auto` | 继承 GameProfile |
| `foreground` | 前台 (SendInput) |
| `background` | 后台 (PostMessage) |
| `pseudo_background` | 伪后台 (PrintWindow + SendInput 临时前台化) |

### 15.4 FeatureFlag `unattended_multi_game_mode` (Spec A)

- **name**: `unattended_multi_game_mode`
- **enabled**: `true` (multi 模式) / `false` (single 模式, 默认 fail-closed)
- **行为**: `enabled=true` 时, `resolve_device_methods` 把 `MULTI_GAME_BLOCKED_*` 方法降级到 safe 默认 (PrintWindow / PostMessage), 保留 `original_*` 字段诊断; `unattended_start_view` 400 拒绝不安全 device

### 15.5 DeviceSerializer 多游戏模式扩展字段 (Spec A)

multi 模式下 DeviceSerializer 额外返回:

| 字段 | 类型 | 说明 |
|------|------|------|
| `multi_game_restricted` | bool | 当前 device 是否被 multi 模式降级 |
| `allowed_screenshot_methods` | list[str] | 当前模式允许的截图方法 |
| `allowed_input_methods` | list[str] | 当前模式允许的输入方法 |
| `original_screenshot_method` | str | 用户配置的原方法 (诊断用) |
| `original_input_method` | str | 用户配置的原方法 (诊断用) |

## 16. 审计日志 (Audit Log) — spec34 (C-045, 114 接入点, 19 个 ViewSet 已接入)

### 16.1 数据模型

`accounts.AuditLog` 记录所有敏感操作的不可变审计追踪。

| 字段 | 类型 | 说明 |
|------|------|------|
| `user` | FK(User, null) | 操作者 (system 操作时为 null) |
| `action` | TextChoices | `LOGIN` / `LOGOUT` / `CREATE` / `UPDATE` / `DELETE` / `ENABLE` / `DISABLE` / `EXECUTE` / `IMPORT` / `EXPORT` |
| `resource_type` | str(64) | 资源类型 (见 §16.2 取值表) |
| `resource_id` | str(128) | 资源 ID (通常 pk; bulk 操作为空字符串) |
| `details` | JSONField | 操作详情 (敏感字段自动 redact, 见 §16.3) |
| `ip_address` | str(39) null | 客户端 IP (X-Forwarded-For 第一 IP → REMOTE_ADDR) |
| `created_at` | datetime | 操作时间 |

### 16.2 `resource_type` 合法取值 (与前端 i18n 一一对应)

合法取值单一权威源: `backend/gaf_core/audit_constants.py::AuditResourceType`。
新增取值必须同步:
1. `AuditResourceType` 类新增常量
2. `frontend/src/i18n/locales/auditLog.ts` 4 locale (zh-CN/en-US/ja-JP/ko-KR) 各加 `auditLog.resource_<value>` 键
3. `frontend/src/pages/System/AuditLogPage.tsx::RESOURCE_TYPE_LABEL_KEYS` 新增映射

由 `backend/gaf_core/tests/test_audit_i18n_meta.py` 强制校验 (5 个测试)。

当前 38 个合法取值 (8 前端已有 + 30 spec34 新增):

| 取值 | i18n key (zh-CN) | 来源 |
|------|-----------------|------|
| `user` | `auditLog.resource_user` | 前端已有 |
| `task` | `auditLog.resource_task` | 前端已有 |
| `device` | `auditLog.resource_device` | 前端已有 |
| `resource_pack` | `auditLog.resource_resource_pack` | 前端已有 |
| `api_key` | `auditLog.resource_api_key` | 前端已有 |
| `feature_flag` | `auditLog.resource_feature_flag` | 前端已有 |
| `game_account` | `auditLog.resource_game_account` | 前端已有 |
| `game_profile` | `auditLog.resource_game_profile` | 前端已有 |
| `agent` / `agent_token` / `pipeline` / `scheduled_task` / `task_chain` / `task_folder` / `custom_task` / `recording` / `template_version` / `template_annotation` / `tag` / `plugin` / `time_window` / `notification` / `webhook_config` / `alert_rule` / `monitor_rule` / `agent_session` / `qa_session` / `qa_message` / `crash_report` / `debug_log_archive` / `game_state_rule` / `task_execution` / `user_session` / `game_account_group` / `rotation_rule` / `llm_config` / `app_settings` / `unattended_strategy` / `device_group` / `marketplace` | `auditLog.resource_<value>` | spec34 Phase 4 |

### 16.3 `details` 字段敏感字段保护

`details` JSONField 自动 redact 敏感字段 (deny-list 模式):

- **内置 deny-list** (`SENSITIVE_FIELD_NAMES`): `password` / `password1` / `password2` / `password_hash` / `old_password` / `new_password` / `secret` / `client_secret` / `api_key` / `apikey` / `token` / `access_token` / `refresh_token` / `totp_secret` / `totp_code` / `private_key` / `credential` / `credentials` / `authorization` / `cookie` / `session_key`
- **匹配规则**: 字段名小写比较 (case-insensitive), 命中 deny-list 则值替换为 `"<redacted>"` (保留键存在性)
- **调用方扩展**: `filter_sensitive_fields(data, extra_sensitive={"url", "code"})` 临时扩展 deny-list (per-resource)
- **ViewSet 实践**: `_build_audit_details` 实现只挑 safe fields (username/email/role/status 等), 不依赖 deny-list 兜底

### 16.4 接入模式 (3 种)

ViewSet/View 接入审计日志有 3 种模式 (优先级 A > B > C):

**A. AuditMixin 继承** (ModelViewSet/GenericViewSet 子类, 有 `perform_*` hook):
```python
from gaf_core.mixins import AuditAction, AuditMixin, AuditResourceType

class TaskViewSet(AuditMixin, viewsets.ModelViewSet):
    audit_resource_type = AuditResourceType.TASK

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        if action == AuditAction.UPDATE and old_instance:
            return build_diff_details(
                before={"name": old_instance.name, "status": old_instance.status},
                after={"name": instance.name, "status": instance.status},
            )
        return super()._build_audit_details(action, instance, old_instance=old_instance)
```

**B. 显式 `log_audit` 调用** (APIView/generics.*View/function-based view, 无 `perform_*` hook):
```python
from accounts.audit import log_audit  # lazy import in function body
from gaf_core.audit_constants import AuditAction, AuditResourceType, get_client_ip, filter_sensitive_fields

def execution_intervene_view(request, pk):
    # ... business logic ...
    from accounts.audit import log_audit
    log_audit(
        user=request.user,
        action=AuditAction.EXECUTE,
        resource_type=AuditResourceType.TASK_EXECUTION,
        resource_id=str(pk),
        details={"action": "pause", "execution_id": str(pk)},
        ip_address=get_client_ip(request),
    )
```

**C. `@audit_action` 装饰器** (`@action` 自定义端点, 装饰器就近原则):
```python
from gaf_core.mixins import AuditAction, AuditResourceType, audit_action

class TaskViewSet(AuditMixin, viewsets.ModelViewSet):
    audit_resource_type = AuditResourceType.TASK

    @action(detail=True, methods=["post"])
    @audit_action(action=AuditAction.EXECUTE, resource_type=AuditResourceType.TASK, resource_id_kw="pk")
    def execute(self, request, pk=None):
        # business logic — exception re-raises, no audit written on failure
        ...
```

### 16.5 接入统计 (spec34 全量)

| App | AuditMixin | 显式 log_audit | @audit_action | 跳过 (只读) |
|-----|-----------|---------------|--------------|-------------|
| accounts | 7 | 13 | 6 | 16 |
| settings | 3 | 3 | 0 | 6 |
| tasks | 6 | 6 | 3 | 6 |
| agents | 3 | 4 | 3 | 12 |
| pipeline | 3 | 1 | 6 | 4 |
| resources | 4 | 2 | 6 | 多个 GET |
| plugins | 0 | 6 | 0 | 1 |
| scheduler | 1 | 0 | 0 | 多个 |
| notifications | 3 | 0 | 3 | 0 |
| monitors | 1 | 0 | 1 | 1 |
| protocol | 1 | 0 | 2 | 1 |
| qa | 2 | 1 | 1 | 1 |
| debug | 2 | 0 | 1 | 1 |
| gamestate | 2 | 0 | 8 | 1 |
| executions | 0 | 1 | 0 | 9 |
| **总计** | **37** | **37** | **40** | **~65** |

合计 **114 个接入点** (37 AuditMixin + 37 显式 log_audit + 40 @audit_action)。

### 16.6 验证机制

- **单元测试**: `backend/gaf_core/tests/test_audit_mixin.py` (31 tests) 覆盖 AuditMixin / @audit_action / build_diff_details / get_client_ip / filter_sensitive_fields / AuditResourceType
- **i18n meta-test**: `backend/gaf_core/tests/test_audit_i18n_meta.py` (5 tests) 强制 AuditResourceType ↔ auditLog.ts 4 locale 一一对应
- **全量回归**: 1149 backend tests pass (含 31 + 5 audit tests + 各 app 现有测试)

---

## 17. 前端崩溃上报端点 (Spec P0-10, 2026-07-27 新增)

### 17.1 端点

```
POST /api/v2/logs/frontend-errors/    # 接收浏览器端崩溃报告 (匿名, 不带用户身份)
```

### 17.2 请求体

```json
{
  "event": "unhandledrejection" | "error" | "componentdidcatch",
  "message": "TypeError: ...",
  "stack": "...",
  "location": { "url": "...", "pathname": "...", "hash": "..." },
  "user_agent": "...",
  "session_id": "<uuid>",
  "occurred_at": "2026-07-27T10:30:00Z"
}
```

### 17.3 响应

成功响应返回 `200` + `{ "received": true }`，崩溃报告异步写入 `gaf_core.frontend_error` 表供 AI 调试使用。该端点匿名（不强制鉴权），仅接收结构化字段，不接收任意 JSON。

---

**维护者**：AI（不人工维护）
**变更触发**：修改任何 API → 检查本规范 + 后端 model + 前端类型同步 → 同步 `last_updated`
**验证**：
- 后端：`pytest` + `python manage.py spectacular --validate`
- 前端：`npm run lint` + `npx tsc --noEmit` + `npm test`
