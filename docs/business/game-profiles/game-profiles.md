---
summary: 游戏档案管理（GameProfile）— 多游戏模式 / 默认 routine / 子资源绑定
applies_to: ['backend', 'frontend', 'business']
key_decisions:
  - GameProfile 是 Window-centric 架构的顶层组织单元，下绑 Device/Account/Task/TaskChain
  - default_routine FK → TaskChain，一键派发到所有在线设备
  - routine_path 支持 TD-113 多 GameProfile 指向不同 routine.json
  - ResourcePack 不直接绑 GameProfile，而是绑 GameAccount（跨服务器账户用不同资源包）
  - device_type_hint (windows/emulator) 避免设备绑定误选
last_updated: 2026-08-01
---

# 游戏档案管理（GameProfile）

> 模块路径：`backend/gamestate/` · 前端路由：`/game-profiles` · API 前缀：`/api/v2/gamestate/`

## 1. 概述

**GameProfile**（游戏适配档案）是 GAF Window-centric 架构的顶层组织单元。每个 GameProfile 描述"一款游戏在 GAF 中如何运行"的全局配置：截图/输入方式、OCR 语言、参考分辨率、控制模式、默认任务链、已知弹窗等。其下挂载 5 类子资源（Device / GameAccount / Task / TaskChain / ResourcePack），构成一棵"游戏 → 窗口/账户 → 任务"的资源树。

**核心定位**（来自模型 docstring）：

> Belongs in gamestate because it is game-wide configuration (screenshot methods, OCR language, popup templates, resolution strategy) consumed by the game-state tracking layer, device auto-binding, and resource-pack association.

**位置历史**：R37-P3 Stage 7 (TD-039) 从 `tasks` app 迁入 `gamestate`，`db_table` 保持 `game_profile` 零数据迁移。Spec v3 §2.5.1 将前端从 `/system/game-profiles` 提升为顶层菜单 `/game-profiles`。

## 2. 数据模型

### 2.1 GameProfile 主模型

定义位置：[backend/gamestate/models.py](file:///d:/code/GAF/backend/gamestate/models.py)

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `game_name` | CharField(255) unique | — | 游戏唯一名称（如 `BrownDust-II`） |
| `screenshot_methods` | JSONField(list) | `[]` | 按优先级排序的截图方式列表 |
| `ocr_language` | CharField(50) | `ch` | OCR 语言代码（`ch`/`en`/`ja`/`ko`） |
| `ui_reference_resolution` | JSONField({w,h}) | `{}` | UI 设计参考分辨率，如 `{w:1920, h:1080}` |
| `known_popups` | JSONField(list) | `[]` | 已知弹窗模板列表 |
| `resolution_strategy` | CharField(50) | `scale` | 分辨率适配策略（`scale`/`crop`/`letterbox`/`stretch`） |
| `default_routine` | FK → `pipeline.TaskChain` | NULL | **默认任务链**（spec v3 §2.7.2），`on_delete=SET_NULL` |
| `routine_path` | CharField(500) | `''` | TD-113：该档案对应的 `routine.json` 路径，支持多 GameProfile 指向不同 routine |
| `default_screenshot_method` | CharField(50) | `''` | 推荐默认截图方式（Device 字段为空时继承） |
| `default_input_method` | CharField(50) | `''` | 推荐默认输入方式（Device 字段为空时继承） |
| `default_control_mode` | CharField(30) | `''` | 推荐默认控制模式（Device 字段为空时继承） |
| `device_type_hint` | CharField(20) | `''` | 设备类型提示：`windows` / `emulator` / 空 |
| `allowed_device_types` | JSONField(list) | `[]` | N197: 可操作的窗口类型列表，如 `["windows", "emulator"]`。空列表=不限制 |
| `created_at` / `updated_at` | DateTimeField | auto | 时间戳 |

**ControlMode 枚举**（嵌套在 GameProfile 内）：

| 值 | 显示名 | 说明 |
|----|--------|------|
| `foreground` | 前台模式 | 窗口须前置，使用 SendInput |
| `background` | 后台模式 | 窗口可后台，使用 PostMessage |
| `pseudo_background` | 伪后台模式 | 部分操作后台，部分前台 |

**device_type_hint 与 allowed_device_types 的配合**：

- `device_type_hint`（单值提示）— 告知管理员"这款游戏建议跑在什么类型的窗口上"，用于设备绑定时的默认推荐
- `allowed_device_types`（多选限制）— 限制该游戏档案允许操作的窗口类型，设备绑定和任务分发时据此校验
- 示例：`device_type_hint=emulator` + `allowed_device_types=["emulator"]` 表示该游戏仅支持模拟器，禁止绑定 Windows 窗口

### 2.2 辅助模型

#### GameStateRule — 游戏状态规则

定义"用于检测游戏状态的识别规则和触发动作"，与 GameProfile 通过 `game_name` 字符串关联（非 FK）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | CharField(255) | 规则名称 |
| `game_name` | CharField(255) | 游戏名称（与 GameProfile.game_name 字符串匹配） |
| `tracker_type` | CharField(50) | 跟踪器类型 |
| `ocr_region` | JSONField | OCR 检测区域 |
| `ocr_regex` | CharField(500) | OCR 正则 |
| `threshold` / `threshold_direction` | Float / Char | 阈值与方向 |
| `trigger_action` | JSONField | 触发动作 |
| `is_active` | Boolean | 是否启用 |

#### GameStateSnapshot — 游戏状态快照

规则触发时的状态快照，FK → `GameStateRule`（`on_delete=CASCADE`）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `rule` | FK → GameStateRule | 关联规则 |
| `value` | Float | 检测值 |
| `raw_text` | TextField | 原始文本 |
| `triggered` | Boolean | 是否触发 |
| `created_at` | DateTime | 创建时间 |

#### GameVersionCheck — 游戏版本更新检测

检测游戏客户端更新（EXE/资源文件变化），自动标记受影响模板为"待验证"，用于无人值守场景：游戏更新后自动暂停相关任务，避免使用过期模板。

| 字段 | 类型 | 说明 |
|------|------|------|
| `game_name` | CharField(100) | 游戏名称 |
| `resource_pack` | FK → ResourcePack | 关联资源包 |
| `previous_version_hash` / `current_version_hash` | CharField(64) | 更新前后版本 hash |
| `files_changed` | JSONField(list) | 变更文件列表 |
| `affected_templates` | M2M → Template | 受影响模板 |
| `detected_at` | DateTime | 检测时间 |

## 3. API 端点

挂载位置：`config/urls.py` 将 `gamestate/` app 挂载到 `/api/v2/gamestate/`（注意：`gamestate/urls.py` 不再加重复前缀，TD-100 修复）。

### 3.1 标准 CRUD

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/v2/gamestate/game-profiles/` | view | 列表（支持 `search=game_name`、`filterset=game_name/ocr_language/resolution_strategy`） |
| POST | `/api/v2/gamestate/game-profiles/` | manage | 创建 |
| GET | `/api/v2/gamestate/game-profiles/{id}/` | view | 详情 |
| PUT/PATCH | `/api/v2/gamestate/game-profiles/{id}/` | manage | 更新 |
| DELETE | `/api/v2/gamestate/game-profiles/{id}/` | manage | 删除 |

**序列化字段**（[GameProfileSerializer](file:///d:/code/GAF/backend/gamestate/serializers.py)）：

```
id, game_name, screenshot_methods, ocr_language,
ui_reference_resolution, known_popups, resolution_strategy,
default_routine, routine_path, default_screenshot_method,
default_input_method, default_control_mode,
device_type_hint, allowed_device_types, created_at, updated_at
```

> spec-29f (TD-266 Phase 3b)：`screenshot_methods` / `ui_reference_resolution` / `known_popups` 显式声明 `ListField` / `DictField`，让 DRF Spectacular 生成精确的 OpenAPI 类型（`string[]` / `{[key:string]: number}`）。

### 3.2 子资源查询 API（spec v3 §2.5.2）

5 个 `@action(detail=True)` 端点返回某个 GameProfile 下挂载的子资源列表，全部需要 `view` 权限：

| 方法 | 路径 | 返回 | 数据来源 |
|------|------|------|---------|
| GET | `/game-profiles/{id}/tasks/` | Task 列表 | `Task.objects.filter(game_profile=profile)` |
| GET | `/game-profiles/{id}/task_chains/` | TaskChain 列表 | `TaskChain.objects.filter(game_profile=profile)` |
| GET | `/game-profiles/{id}/devices/` | Device 列表 | `Device.objects.filter(game_profile=profile)` |
| GET | `/game-profiles/{id}/accounts/` | GameAccount 列表 | `GameAccount.objects.filter(game_profile=profile)` |
| GET | `/game-profiles/{id}/resource_packs/` | ResourcePack 列表（去重） | `ResourcePack.objects.filter(id__in=profile.game_accounts.values_list('resource_pack_id'))` |

> **ResourcePack 关系**：ResourcePack 不直接绑 GameProfile，而是绑 GameAccount（架构 §3.2），所以 `/resource_packs/` 端点通过 accounts 间接聚合，distinct 去重。前端 `ResourcePacksTab` 是只读的，绑定/解绑在 `AccountsTab` 完成。

### 3.3 子资源绑定 API（spec v3 §2.5.2）

允许在 GameProfile 详情页直接 attach/detach 已存在的子资源，无需跳转到子资源自己的页面。所有端点需要 `manage` 权限，会写审计日志（`AuditResourceType.GAME_PROFILE` + `AuditAction.UPDATE`）。

| 方法 | 路径 | Body | 说明 |
|------|------|------|------|
| POST | `/game-profiles/{id}/bind-task/` | `{task_id}` | 把 Task 绑到此 profile |
| POST | `/game-profiles/{id}/unbind-task/` | `{task_id}` | 解绑 Task |
| POST | `/game-profiles/{id}/bind-task-chain/` | `{task_chain_id}` | 把 TaskChain 绑到此 profile |
| POST | `/game-profiles/{id}/unbind-task-chain/` | `{task_chain_id}` | 解绑 TaskChain |
| POST | `/game-profiles/{id}/bind-account/` | `{account_id}` | 把 GameAccount 绑到此 profile |
| POST | `/game-profiles/{id}/unbind-account/` | `{account_id}` | 解绑 GameAccount |

**绑定校验**（`_bind_child` 共享逻辑）：

1. 目标资源必须存在
2. 目标资源不能已绑到另一个 GameProfile（返回 400：`is already bound to another GameProfile (id=X)`）
3. 成功后设置 `game_profile` FK 并 `save(update_fields=['game_profile'])`

**解绑校验**（`_unbind_child`）：目标资源的 `game_profile_id` 必须等于当前 profile，否则返回 400。

### 3.4 默认 routine 管理 API（spec v3 §2.7.2）

#### PATCH `/game-profiles/{id}/default-routine/` — 设置默认任务链

**权限**：`manage` · **审计**：`AuditAction.UPDATE`

**Body**：`{"task_chain_id": 123}`

**原子操作**（`transaction.atomic`）：

1. 校验目标 TaskChain 属于此 GameProfile（`chain.game_profile_id == profile.pk`，否则 400）
2. 清空同 profile 下其他 `is_default=True` 的 chain（`update(is_default=False)`）
3. 设置目标 chain `is_default=True`
4. 同步 `profile.default_routine = chain` 并保存

**响应**：

```json
{
  "status": "ok",
  "game_profile_id": 1,
  "game_name": "BrownDust-II",
  "default_routine_id": 123,
  "default_routine_name": "BD2 日常",
  "is_default": true,
  "message": "TaskChain [BD2 日常] set as default routine for GameProfile [BrownDust-II]"
}
```

> **镜像端点**：`POST /api/v2/pipeline/task-chains/{id}/set-default/` 是 pipeline 侧的同一操作，二者保持 `GameProfile.default_routine` 与 `TaskChain.is_default` 一致。前端 `TaskChainsTab` 用本端点。

### 3.5 默认 routine 派发 API（spec v3 §2.7.2 + §2.4.1）

#### POST `/game-profiles/{id}/dispatch-routine/` — 派发到所有在线设备

**权限**：`execute` · **审计**：`AuditAction.EXECUTE`

**Body**（可选）：`{"agent_id": "agent-xxx"}` — 强制所有派发通过指定 Agent；省略时每个 Device 用自己的 `device.agent`。

**流程**：

1. 取 `profile.default_routine`，为空返回 400（"call PATCH default-routine first"）
2. 校验 chain `is_enabled=True`，否则 400
3. 遍历 `profile.devices.select_related('agent', 'game_account')`：
   - 解析 agent：强制 agent_id 或 device.agent；agent 为空 → skip；agent 状态非 ONLINE/IDLE → skip
   - 调用 `create_chain_execution_and_dispatch(chain_id, agent_id, device_id, game_account_id, triggered_by=user)`
   - 失败（`ChainDispatchError`）→ 加入 `failed` 列表，继续下一个

**响应**：

```json
{
  "status": "dispatched",
  "dispatched_count": 2,
  "skipped_count": 1,
  "failed_count": 0,
  "dispatched": [
    {"chain_execution_id": 101, "device_id": 5, "device_name": "BD2-窗口1",
     "agent_id": "agent-xxx", "game_account_id": 8, "status": "running"}
  ],
  "skipped": [
    {"device_id": 6, "device_name": "BD2-窗口2", "reason": "agent_offline (status=offline)"}
  ],
  "failed": [],
  "game_profile_id": 1,
  "default_routine_id": 123,
  "default_routine_name": "BD2 日常"
}
```

## 4. 前端结构

### 4.1 路由

| 路由 | 组件 | 说明 |
|------|------|------|
| `/game-profiles` | `GameProfilesPage` | 列表页（Spec v3 §2.5.1） |
| `/game-profiles/:id` | `GameProfileDetailPage` | 详情页，5 Tab（Spec v3 §2.5.2） |

> 列表页通过 `lazy(() => import('@/pages/GameProfiles'))` 懒加载（[App.tsx#L77-L81](file:///d:/code/GAF/frontend/src/App.tsx)）。

### 4.2 列表页 [index.tsx](file:///d:/code/GAF/frontend/src/pages/GameProfiles/index.tsx)

| 功能 | 实现 |
|------|------|
| 列表展示 | Antd Table，列：游戏名 / 默认 routine / 默认截图方式 / 默认输入方式 / 默认控制模式 / OCR 语言 / 参考分辨率 / 分辨率策略 / 已知弹窗 / 创建时间 |
| 搜索 | `Input.Search`，按 `game_name` 模糊搜索 |
| 创建 | `+` 按钮 → `GameProfileEditorModal`（create 模式） |
| 编辑 | 行内 `Edit` 按钮 → `GameProfileEditorModal`（edit 模式） |
| 删除 | 行内 `Delete` 按钮 + `Popconfirm` |
| 详情 | 点击游戏名 / `View Detail` 按钮 → `navigate(/game-profiles/:id)` |

### 4.3 详情页 [DetailPage.tsx](file:///d:/code/GAF/frontend/src/pages/GameProfiles/DetailPage.tsx)

**布局**：

```
┌────────────────────────────────────────────────────────────┐
│  ← GameProfile: <name>                                      │
│  [Refresh] [Dispatch Routine] [Edit] [Delete]               │
│  Default Screenshot: wgc | Default Input: postmessage | ...  │
├────────────────────────────────────────────────────────────┤
│  Tabs: [Tasks] [Task Chains] [Devices] [Accounts]           │
│        [Resource Packs]                                     │
└────────────────────────────────────────────────────────────┘
```

**顶部 Descriptions 卡片**：展示 9 个字段（默认 routine / 截图方式 / 输入方式 / 控制模式 / OCR 语言 / 参考分辨率 / 分辨率策略 / 已知弹窗 / 创建时间）。

**Dispatch Routine 按钮**：`disabled={!profile.default_routine}`，调用 `dispatchRoutine(profile.id)`，根据 `dispatched_count` 显示成功 / 警告（空派发）。

**内联编辑**：`Edit` 按钮打开 `GameProfileEditorModal`，保存后 `loadProfile()` 就地刷新（不跳回列表页）。

### 4.4 5 个 Tab 组件

| Tab | 组件 | 功能 | 操作 |
|-----|------|------|------|
| Tasks | [TasksTab.tsx](file:///d:/code/GAF/frontend/src/pages/GameProfiles/components/TasksTab.tsx) | 列出绑定的 Task | + Add (bind) / Edit (跳 `/tasks/:id/edit`) / Unbind |
| Task Chains | [TaskChainsTab.tsx](file:///d:/code/GAF/frontend/src/pages/GameProfiles/components/TaskChainsTab.tsx) | 列出绑定的 TaskChain | + Add / Set Default / Edit (跳 `/ops/scheduler/dag/:id`) / Unbind |
| Devices | [DevicesTab.tsx](file:///d:/code/GAF/frontend/src/pages/GameProfiles/components/DevicesTab.tsx) | 列出绑定的 Device | 排任务（DispatchRoutineModal，单设备派发） |
| Accounts | [AccountsTab.tsx](file:///d:/code/GAF/frontend/src/pages/GameProfiles/components/AccountsTab.tsx) | 列出绑定的 GameAccount | + Add / Unbind |
| Resource Packs | [ResourcePacksTab.tsx](file:///d:/code/GAF/frontend/src/pages/GameProfiles/components/ResourcePacksTab.tsx) | 列出（只读）绑定的 ResourcePack | 仅 Refresh，绑定/解绑在 Accounts Tab |

**共享子组件**：

- [BindResourceModal.tsx](file:///d:/code/GAF/frontend/src/pages/GameProfiles/components/BindResourceModal.tsx)：通用绑定弹窗，3 种 `resourceType`（`task` / `task_chain` / `account`）。打开时加载未绑定资源列表，过滤掉 `excludeIds`（已绑定的）。
- [GameProfileEditorModal.tsx](file:///d:/code/GAF/frontend/src/pages/GameProfiles/components/GameProfileEditorModal.tsx)：create/edit 模态框，含 9 个字段表单（game_name / 3 个默认方式 / OCR 语言 / 参考分辨率 / 分辨率策略 / known_popups / routine_path）。

### 4.5 选项常量 [options.ts](file:///d:/code/GAF/frontend/src/pages/GameProfiles/options.ts)

提取共享的 Select 选项，避免列表页和编辑模态框重复定义：

| 常量 | 取值 |
|------|------|
| `SCREENSHOT_METHOD_OPTIONS` | bitblt / dxgi_dupl / wgc / gdi / adb |
| `INPUT_METHOD_OPTIONS` | sendinput / postmessage / adb |
| `CONTROL_MODE_OPTIONS` | foreground / background / pseudo_background |
| `OCR_LANG_OPTIONS` | ch / en / ja / ko |
| `RESOLUTION_STRATEGY_OPTIONS` | scale / crop / letterbox / stretch |

Hook `useGameProfileOptions()` 返回带本地化 label 的选项数组。

## 5. 与其他模块的关系

### 5.1 资源树（Window-centric 架构）

```
GameProfile (1)
  ├── Device (N)              ← device.game_profile FK
  │     └── Agent             ← device.agent FK
  ├── GameAccount (N)         ← account.game_profile FK
  │     └── ResourcePack      ← account.resource_pack FK (跨服务器账户用不同资源包)
  ├── Task (N)                ← task.game_profile FK
  ├── TaskChain (N)           ← chain.game_profile FK
  │     └── is_default=True   ← 同一 profile 下最多一条
  └── UnattendedSession (N)   ← session.game_profile FK (scheduler)
        ↑ P-011: 同一 profile 下最多一个 RUNNING/PAUSED session (409 强制)

default_routine ──FK──→ TaskChain (spec v3 §2.7.2 镜像字段)
routine_path ──string──→ resources/<game>/routine.json (TD-113)
```

**关键设计**：

- **ResourcePack 不绑 GameProfile**：架构 §3.2 决定 ResourcePack 绑 GameAccount，因为"跨服务器账户可能用不同资源包"（如国服/台服账户配不同模板）。`/resource_packs/` API 通过 accounts 间接聚合 + distinct。
- **GameProfile.default_routine ↔ TaskChain.is_default**：一对镜像字段，必须保持一致。`PATCH /default-routine/` 和 `POST /task-chains/{id}/set-default/` 任一端点都同步两者。
- **UnattendedSession 唯一性约束**：P-011 多会话支持后，同一 GameProfile 下最多一个 RUNNING/PAUSED session（在 `unattended_start_view` 用 409 强制，非 DB unique_together，因为 status 字段非唯一）。
- **allowed_device_types 校验**：设备绑定和任务分发时，如果该 GameProfile 配置了 `allowed_device_types`，会根据 `Device.device_type` 校验窗口类型是否匹配。不匹配的窗口无法绑定到该游戏档案。
- **控制模式与窗口类型的关联**：`device_type=emulator` 的窗口（模拟器）始终通过 ADB 控制，可最小化运行；`device_type=windows` 的窗口（非模拟器）受 `control_mode` 限制，分为 foreground（必须前台）/ background（可后台）/ pseudo_background（折中）。详见架构文档 §4.3。

### 5.2 default_routine 完整调用链

```
用户在 TaskChainsTab 点击 "Set Default"
  ↓
setDefaultRoutine(profileId, chainId)  →  PATCH /game-profiles/{id}/default-routine/
  ↓
GameProfileViewSet.default_routine (transaction.atomic):
  1. 校验 chain.game_profile_id == profile.pk
  2. TaskChain.objects.filter(game_profile=profile, is_default=True).exclude(pk=chain.pk).update(is_default=False)
  3. chain.is_default = True; chain.save()
  4. profile.default_routine = chain; profile.save()
  ↓
用户在 DetailPage 顶部点击 "Dispatch Routine"
  ↓
dispatchRoutine(profileId)  →  POST /game-profiles/{id}/dispatch-routine/
  ↓
GameProfileViewSet.dispatch_routine:
  1. chain = profile.default_routine (为空 → 400)
  2. 校验 chain.is_enabled
  3. 遍历 profile.devices (select_related agent + game_account)
  4. 对每个在线 device: create_chain_execution_and_dispatch(chain_id, agent_id, device_id, game_account_id, user)
  5. 收集 dispatched / skipped / failed → 返回汇总
```

### 5.3 routine_path 与 convert_routine_to_chain（TD-113）

**问题背景**：原本 `convert_routine_to_chain` 接收一个硬编码的 routine.json 路径参数，无法支持多 GameProfile 各自指向不同 routine。

**TD-113 修复**：把路径存到 `GameProfile.routine_path`，`convert_routine_to_chain(game_profile, user=None)` 从 `game_profile.routine_path` 读取，每个 GameProfile 可指向不同的 `routine.json`（如不同账号策略）。

**关键逻辑**（[backend/pipeline/services.py:138](file:///d:/code/GAF/backend/pipeline/services.py)）：

- 读 `game_profile.routine_path`，为空 → `RoutineImportError`
- 解析 routine.json，按 pipeline name 解析为 Pipeline 对象
- **幂等**：同名 + 同 game_profile 的 TaskChain 已存在则复用（替换 nodes），否则新建
- 新建/更新后强制 `chain.is_default = True`，绑定 `game_profile = game_profile`

### 5.4 多游戏模式（Multi-Game）

GAF 通过 GameProfile 支持同时管理多款游戏：

| 维度 | 多游戏实现 |
|------|-----------|
| **数据隔离** | 每个 GameProfile 独立的 `routine_path` / `screenshot_methods` / `known_popups` / `ui_reference_resolution` |
| **资源隔离** | `resources/<game>/` 目录按游戏分子目录（如 `resources/BrownDust-II/`、`resources/OtherGame/`），通过 `game_profile.routine_path` 指向各自的 routine.json |
| **任务隔离** | Task / TaskChain 通过 `game_profile` FK 隔离 |
| **设备隔离** | Device 通过 `game_profile` FK 隔离；`device_type_hint` 区分 windows/emulator 避免误绑 |
| **会话隔离** | UnattendedSession 通过 `game_profile` FK 隔离，P-011 后支持多 session 并行（每 profile 一个 RUNNING/PAUSED） |
| **派发隔离** | `dispatch-routine` 只派发 `profile.devices` 下的设备，不会跨游戏派发 |

### 5.5 默认方式继承（Device 字段为空时）

Device 模型的 `screenshot_method` / `input_method` / `control_mode` 字段为空时，从其 `game_profile` 继承：

| Device 字段 | 继承自 GameProfile 字段 |
|-------------|------------------------|
| `screenshot_method` 为空 | `default_screenshot_method` |
| `input_method` 为空 | `default_input_method` |
| `control_mode` 为空 | `default_control_mode` |

> 这是 Window-centric Stage 2 引入的设计：GameProfile 描述"该游戏的推荐方式"，Device 可显式覆盖或留空继承。

## 6. 审计与权限

### 6.1 权限矩阵

| Action | required_permission |
|--------|---------------------|
| list / retrieve / 5 个子资源 GET | `view` |
| create / update / partial_update / destroy | `manage` |
| bind-* / unbind-* / default-routine | `manage` |
| dispatch-routine | `execute` |

权限通过 `RoleBasedPermission` + `required_permission` 类属性实现（[views.py:43-56](file:///d:/code/GAF/backend/gamestate/views.py)）。

### 6.2 审计

GameProfileViewSet 和 GameStateRuleViewSet 都继承 `AuditMixin`，通过 `@audit_action` 装饰器记录审计日志。

**审计资源类型**：

- `AuditResourceType.GAME_PROFILE` — GameProfile CRUD + bind/unbind + default-routine
- `AuditResourceType.GAME_STATE_RULE` — GameStateRule CRUD
- dispatch-routine 记为 `AuditAction.EXECUTE`（不是 UPDATE），因为触发实际任务执行

**敏感字段脱敏**（`_build_audit_details`）：

- `known_popups` / `screenshot_methods` / `routine_path` 标为 sensitive，避免审计日志泄露内部模板名/文件系统路径
- `default_routine_id` 单独记录，让审计者能看到默认 routine 何时变更

## 7. 管理后台

[backend/gamestate/admin.py](file:///d:/code/GAF/backend/gamestate/admin.py) 注册了 4 个 ModelAdmin：

- `GameProfileAdmin` — GameProfile
- `GameStateRuleAdmin` — GameStateRule
- `GameStateSnapshot` — 已自定义 `GameStateSnapshotAdmin`（只读字段配置）
- `GameVersionCheckAdmin` — GameVersionCheck

## 8. 已知限制

| # | 限制 | 影响 | 建议 |
|---|------|------|------|
| 1 | GameStateRule 通过 `game_name` 字符串关联 GameProfile，非 FK | 删除 GameProfile 不会级联删除规则；改名需手动同步 | 长期可加 migration 改为 FK，但需数据迁移 |
| 2 | GameVersionCheck 通过 `resource_pack` FK 间接关联 GameProfile | 无法直接从 GameProfile 查询版本检测历史 | 通过 `resource_pack.game_profile` 二跳查询 |
| 3 | `default_routine` 为 FK + `TaskChain.is_default` 布尔，存在双写一致性问题 | 两个镜像端点必须同步，依赖 `transaction.atomic` 保证 | 已有 clean() 校验"一个 profile 下最多一个 is_default=True"，运行时一致性靠 `default-routine` API 保证 |
| 4 | dispatch-routine 是同步遍历设备 | 设备多时阻塞请求 | 大规模部署可改为 Celery 异步，当前规模够用 |
