---
summary: GAF 架构设计文档
applies_to: ['architecture', 'design']
applies_to_code_paths:
  - backend/
  - agent/
  - frontend/
  - desktop/
key_decisions:
  - 六、轮换策略
  - 九、关键设计决策记录
last_updated: 2026-08-26
---

# GAF 架构设计文档

> **版本**: 3.7 | **创建日期**: 2026-05-31 | **最后更新**: 2026-08-08 (Phase 1-3 架构重构: 服务层/统一 LLM 客户端/设备发现注册表/EventBus/ArchiveService/GafDaemon)
> **用途**: 记录 GAF 核心架构、数据模型关系、执行流程，供开发和 AI 理解系统全貌
> **架构图**: [system-overview.svg](./system-overview.svg) — 全栈架构一图总览（前端 → 后端 → Worker → 设备 + AI 治理层）
> **状态**: 核心架构重构已完成 (Phase 1-3 [OK]) + 设备自动关联已实施 (Phase R16 [OK] + Phase R18 [OK]) + 跨平台层落地 (P-028 [OK]) + AI Agent 集成 (LangGraph [OK]) + Django App 合并优化 [OK] + 前端 API 文件合并 [OK] + 服务层/注册表/EventBus/守护进程 [OK]
> **本文档状态**: 截至 2026-08-08 同步有效 (Phase 1-3: TaskExecutor/DeviceDiscoveryRegistry/EventBus/ArchiveService/GafDaemon)

---

## 一、系统概览

GAF (Game Automation Framework) 是一个游戏自动化框架，支持多游戏、多账户、多设备并发执行。定位为 **PC 窗口（Windows/macOS/Linux）+ 模拟器（ADB）** 控制框架，不需要手机端。

### 技术栈

| 层 | 技术栈 | 关键版本 |
|------|--------|---------|
| **前端** | React + TypeScript + Vite + Ant Design + Zustand + React Flow + WebSocket | React 19.2 / TS 6.0 / Vite 8.0 / Antd 6.4 |
| **后端** | Django + DRF + Celery + Redis + SQLite + WAL + Channels (Daphne) + drf-spectacular | Django 5.2 / DRF 3.15 / Channels 4.1 / Python 3.11 |
| **Agent** | Python 独立进程，WebSocket 连接后端，平台抽象层 + Pipeline Engine | Python 3.11 自研 |
| **Desktop** | Electron 桌面应用（封装前端 + 后端 + Agent 一体化分发） | 见 `desktop/` |
| **认证** | SimpleJWT + pyotp (TOTP 2FA) + OAuth2 (GitHub/Google) + AES-256-GCM | — |
| **AI** | OpenAI 兼容 LLM (OpenAI/DeepSeek/Ollama/Custom) + ChromaDB RAG + LangGraph Agent | — |
| **API** | 统一前缀 `/api/v2/`，OpenAPI 文档 `/api/v2/docs/` | — |

### 核心设计原则

1. **资源包绑定在任务上** — 任务直接关联资源包（`Task.resource_pack` FK），运行时通过此资源包加载服务器对应模板；换服务器只需改任务绑定的资源包，同一任务可被多个服务器共用，仅加载的识别模板不同
2. **账户资源包做回退** — 游戏账户的 `resource_pack` 作为账户级别默认资源包，仅当 `Task.resource_pack` 未设置时回退使用；`ResourcePack.get_templates_for_server(server_region)` 按服务器分区选择模板
3. **设备不绑资源包** — 设备只负责执行方式，与游戏无关
4. **轮换按账户维度** — 一个账户所有任务完成后再换下一个
5. **设备并行执行** — 多开模拟器可同时跑不同账户
6. **跨平台抽象** — Windows/macOS/Linux 通过 `device_bridge/platforms/` 统一接口，业务代码不直接调平台 API
7. **Agent 自治** — Agent 端独立进程，WebSocket 心跳上报，断线重连，本地状态机驱动

### 项目目录结构

```
GAF/
├── backend/                    # Django 后端 (17 个自研 App + 1 个纯 Python 包)
│   ├── config/                 # Django project 配置 (settings/urls/celery/asgi)
│   ├── accounts/               # 认证 + 用户 + 游戏账户 + API Key + OAuth
│   ├── agents/                 # Agent/Device/DeviceGroup + WebSocket 同步
│   ├── tasks/                  # Task/TaskExecution/ScheduledTask + 执行记录视图 + services/ 服务层子包
│   │   └── services/           # 服务层: task_service.py, execution_service.py (Phase 1)
│   ├── pipeline/               # Pipeline JSON + 18+ 节点 + 校验器 + 估算器
│   ├── resources/              # 资源包/模板/版本/标注
│   ├── scheduler/              # 无人值守 + 5 层恢复 + ActionChain
│   ├── monitors/               # 监控规则/事件/告警升级 + SLA 指标 + EventBus + ArchiveService
│   ├── gaf_ai                  # LLM Router + RAG + LangGraph Agent + 智能问答 + 成本控制 (含 base_client.py 统一客户端)
│   │   ├── agent/              # LangGraph AI Agent (graph/tools/models)
│   │   └── base_client.py      # 统一 LLM 客户端基类 (Phase 2)
│   ├── skills/                 # Skill YAML 引擎 + 市场
│   ├── debug/                  # 崩溃报告 + 日志归档 + LLM 分析
│   ├── protocol/               # 消息帧协议 + 心跳 + 配额
│   ├── device_bridge/          # 跨平台设备桥接 (platforms/{windows,macos,linux}) 纯 Python 包 (非 Django app)
│   ├── gaf_core                # 全局 mixin/exception/error_code + tracing + i18n + search (合并)
│   ├── gamestate/              # OCR 区域识别 + 阈值触发
│   ├── settings/               # LLMConfig + FeatureFlag + AppSettings
│   ├── notifications/          # 7 渠道通知 (邮件/Webhook/钉钉/飞书/企微/Telegram/自定义)
│   └── plugins/                # 插件系统 + 沙箱执行
├── agent/                      # Agent 独立进程 (Python 3.11 自研)
│   └── src/
│       ├── engine/             # TaskExecutor + PipelineEngine + StateMachineEngine + StateMachine (Phase 1 统一入口)
│       ├── devices/            # 设备抽象 + 发现注册表 (discovery/ 子包: DeviceDiscoveryRegistry Phase 2)
│       ├── platforms/windows/  # Win32 截图(6种) + 输入(3方法: SendInput/PostMessage/PseudoBackground) + LDPlayer/MuMu 专用
│       ├── recognition/        # OCR 4 引擎 + OpenCC + 缓存
│       ├── core/               # retry/timeout/worker_pool/script_dsl/state_machine 等
│       ├── client/             # WebSocket 连接 + 设备同步
│   ├── ai/                 # Worker 端 LLM 客户端 (Phase 2: 统一客户端)
│       └── monitor/            # CPU/内存/截图资源监控
├── frontend/                   # React 前端 (31+ 页面, 9 大模块)
│   └── src/
│       ├── pages/              # 页面级组件 (Dashboard/Tasks/Devices/Resources/Accounts/Ops/AI/System)
│       ├── components/         # 业务组件 (按功能子目录)
│       ├── stores/             # Zustand 状态 (8 个 store)
│   ├── api/                # 后端接口封装 (每资源一个 .ts; alertRules→monitors, scheduledTasks→scheduler, marketplace→skills, qa→ai 已合并)
│       ├── hooks/              # 自定义 React hooks
│       ├── i18n/               # 4 语言 locales
│       ├── websocket/          # WebSocket 客户端
│       └── types/              # TypeScript 类型 (OpenAPI 自动生成)
├── desktop/                    # 🆕 Electron 桌面应用 (封装前端 + 后端 + Agent)
│   └── src/main/               # 主进程 (autostart/tray/updater/window/ipc)
├── docs/                       # 项目级文档 (架构/规范/分析/设计)
├── scripts/                    # 工具脚本 (gaf_init.sh/sync_ai_memory.py/e2e 等)
├── resources/                  # 默认资源包 (BrownDust-II/default)
├── deploy/                     # 部署配置 (nginx/systemd)
├── .ai-memory/                 # AI 记忆库 (lessons/summaries/meta/knowledge)
├── .skills/                    # AI 技能+规则唯一权威源 (skills/ + rules/, 多 IDE junction)
├── .trae/                      # Trae 入口 (skills/rules junction → .skills/)
├── .opencode/                  # opencode 入口 (skills/rules junction → .skills/)
```

---

## 二、核心概念

| 概念 | 说明 | 示例 |
|------|------|------|
| **游戏 (GameProfile)** | 游戏产品定义 | 明日方舟、原神、崩坏：星穹铁道 |
| **游戏账户 (GameAccount)** | 具体账号（带服务器信息） | 明日方舟-官服-账号A |
| **资源包 (ResourcePack)** | 视觉资源集合（模板图片+坐标+配置） | 明日方舟-官服-v1.0 |
| **任务 (Task)** | 流程逻辑（Pipeline 步骤定义） | 每日签到、清体力、抽卡 |
| **Worker (Worker)** | 自动化执行节点/进程，每台机器一个 Worker 进程 | 本机 Worker、远程 Worker-1 |
| **窗口 (Device 模型)** | 被控制的游戏窗口，分模拟器窗口和非模拟器窗口两类 | BD2 窗口、雷电模拟器 1 |
| **轮换规则 (GameAccountRotation)** | 账户轮换策略 (4 选：sequential/random/by_stamina/by_last_executed) | 按时间/任务完成/体力/上次执行时间切换 |

> **命名说明**：代码中 `Device` 模型实际代表的是"窗口"（Window 或 模拟器实例），而非"运行 GAF 的机器"。运行 GAF 的执行节点/进程是 `Worker` 的概念（历史遗留 `Agent` 称呼已在 2026-08-29 归一化为 `Worker`，保留 `Agent` 给未来 AI 智能体）。每台机器运行一个 Worker 进程，Worker 自动发现本机所有窗口（Windows 窗口 + 模拟器实例）并注册为 Device 记录。

---

## 三、数据模型关系

### 3.1 ERD 实体关系图

```
User (用户)
  └── owns → GameAccount (游戏账户)

GameProfile (游戏档案)
  └── defines → GameAccount (游戏账户)

GameAccount (游戏账户)
  ├── FK → ResourcePack (资源包) ← 回退：账户级别默认资源包，供未绑定资源包的任务使用
  └── M2M ↔ Task (任务) ← 通过 TaskGameAccount 中间表 [OK] 前后端完整

Task (任务)
  ├── FK → ResourcePack (资源包) ← N197-8: 任务直接关联资源包，运行时通过此资源包加载服务器对应模板
  ├── M2M ↔ GameAccount (游戏账户) ← 任务可绑定多个账户 [OK]
  ├── FK → GameProfile (游戏档案, 归属过滤) [OK] 阶段 1
  └── FK → GameAccountRotation (轮换规则，可选) [OK]

GameProfile (游戏档案) — 中心枢纽 [OK] 阶段 1 v3
  ├── FK → TaskChain (default_task_chain, 默认任务链) [OK] 阶段 1
  ├── default_screenshot_method (默认截图方式, 'auto' 继承) [OK] 阶段 1
  ├── default_input_method (默认输入方式, 'auto' 继承) [OK] 阶段 1
  └── default_control_mode (默认控制模式, 'auto' 继承) [OK] 阶段 1

TaskChain (任务链) [OK] 阶段 1 v3
  ├── FK → GameProfile (game_profile, 归属游戏档案) [OK]
  ├── is_default (BooleanField, 标记为该 GameProfile 的默认链) [OK]
  └── TaskChainNode (有序任务节点) [OK]
      ├── node_type ('task' | 'pipeline') [OK] TD-110 Phase 1
      ├── FK → Task (task, nullable) [OK]
      ├── FK → TaskChainNode (parent, nullable) [OK]
      └── FK → Pipeline (pipeline, nullable) [OK] TD-110 Phase 1 — Pipeline 一等公民
          (node_type='pipeline' 时引用 Pipeline; node_type='task' 时引用 Task)

TaskChainExecution (任务链执行记录) [OK] 阶段 2 v3 新增
  ├── FK → TaskChain (任务链)
  ├── FK → Device (执行设备, 运行时绑定)
  ├── FK → GameAccount (运行时游戏账户, nullable)
  ├── FK → User (triggered_by, 触发者)
  └── status (pending/running/completed/failed/cancelled)

Device (设备)
  ├── FK → Agent (Agent) ← [OK] Phase R18: 自动关联
  ├── FK → GameProfile (game_profile, 绑定游戏档案) [OK] 阶段 1
  ├── FK → GameAccount (game_account, 运行时绑定当前账户) [OK] 阶段 1
  └── screenshot_method/input_method/control_mode ('auto' 时继承 GameProfile) [OK] 阶段 5

GameAccount (游戏账户)
  ├── FK → GameProfile (game_profile, 明确归属) [OK] 阶段 1
  └── FK → ResourcePack (resource_pack, 运行时资源包) [OK] Phase R16

TaskDevice (任务设备映射) ← 中间表
  └── M2M ↔ Task ↔ Device ← 任务可指定在多个设备上执行 [OK]
  (注: is_default 字段已在阶段 1 删除 — 死字段, 执行链路不读取)

TaskExecution (执行记录)
  ├── FK → Task (任务)
  ├── FK → GameAccount (账户, 运行时绑定) [OK] 阶段 1
  ├── FK → Device (设备, 运行时绑定) [OK] 阶段 1
  └── FK → TaskChainExecution (任务链执行, nullable) [OK] 阶段 2 v3
```

### 3.2 核心关系说明

| 关系 | 类型 | 状态 | 说明 |
|------|------|------|------|
| GameProfile → TaskChain | FK (default_task_chain) | [OK] 阶段 1 v3 | 游戏档案的默认任务链, 新窗口绑 GameProfile 自动继承 |
| TaskChain → GameProfile | FK (game_profile) | [OK] 阶段 1 v3 | 任务链归属游戏档案 |
| TaskChain.is_default | BooleanField | [OK] 阶段 1 v3 | 每 GameProfile 下最多一个 is_default=True (clean() 校验) |
| Task → ResourcePack | FK (多对一) | [OK] N197-8 | 任务直接关联资源包，运行时通过此资源包加载服务器对应模板；`ResourcePack.get_templates_for_server(server_region)` 按服务器分区选择模板 |
| GameAccount → ResourcePack | FK (多对一) | [OK] 已实施 | 账户级别默认资源包，供 Task.resource_pack 未设置时回退使用 |
| GameAccount → GameProfile | FK (game_profile) | [OK] 阶段 1 v3 | 明确归属, 替代 game_name 字符串弱关联 |
| Task ↔ GameAccount | M2M (多对多) | [OK] 已完成 | 前后端完整：任务可绑定多个账户 |
| Task ↔ Device | M2M (多对多) | [OK] 已完成 | TaskDevice 中间表（is_default 已删除 — 死字段） |
| Device → Agent | FK (多对一) | [OK] Phase R18 | Agent 启动后自动发现并关联设备 |
| Device → GameProfile | FK (game_profile) | [OK] 阶段 1 | 设备绑定游戏档案 |
| Device → GameAccount | FK (game_account) | [OK] 阶段 1 | 运行时绑定当前执行的账户 |
| Task → GameAccountRotation | FK (多对一) | [OK] 已有 | 任务可选轮换规则 (4 选: sequential/random/by_stamina/by_last_executed) |
| TaskExecution → Task/Account/Device | FK (多对一) | [OK] 已有 | 记录每次执行的完整上下文 |
| TaskExecution → TaskChainExecution | FK (nullable) | [OK] 阶段 2 v3 | 追踪 TaskChain 派发, nullable 兼容单 Task 执行 |
| TaskChainExecution → TaskChain/Device/GameAccount | FK | [OK] 阶段 2 v3 | TaskChain 派发追踪 (1:N → TaskExecution) |
| DeviceResourceMapping | 中间表 | [OK] 已删除 | Phase R16 中已移除 |

### 3.3 当前后端模型

```python
# [OK] Task 模型 (阶段 1 v3 后 + N197-8)
class Task:
    resource_pack = models.ForeignKey(ResourcePack, ...)    # [OK] N197-8: 任务直接关联资源包，运行时加载对应服务器模板
    game_accounts = models.ManyToManyField(GameAccount, ...)  # [OK] 保留 (可选账户白名单)
    game_profile = models.ForeignKey(GameProfile, ...)        # [OK] 保留 (归属过滤；2026-07-14 起 GameProfile 详情页支持 bind/unbind)
    rotation_rule = models.ForeignKey(GameAccountRotation, ...)      # [OK] 保留 (执行链路在用，4 选: sequential/random/by_stamina/by_last_executed)
    # game_account (单 FK) 已移除 → M2M game_accounts 已替代

# [OK] GameProfile 模型 (阶段 1 v3 后) — 中心枢纽
class GameProfile:
    default_task_chain = models.ForeignKey('TaskChain', ...)     # [OK] v3 新增: 默认任务链
    default_screenshot_method = models.CharField(...)         # [OK] v3 新增: 'auto' 继承
    default_input_method = models.CharField(...)              # [OK] v3 新增: 'auto' 继承
    default_control_mode = models.CharField(...)              # [OK] v3 新增: 'auto' 继承
    # screenshot_methods (JSONField 数组) 已废弃 → default_screenshot_method (单数) 替代
    # 2026-07-14: GameProfileViewSet 新增 6 个 @action POST 端点
    #   bind-task / unbind-task / bind-task-chain / unbind-task-chain /
    #   bind-account / unbind-account
    #   详情页 4 个 Tab 可绑定/解绑子资源（资源包 Tab 只读，绑 Account）

# [OK] TaskChain 模型 (阶段 1 v3 后)
class TaskChain:
    game_profile = models.ForeignKey(GameProfile, ...)        # [OK] v3 新增: 归属游戏档案
    is_default = models.BooleanField(default=False)           # [OK] v3 新增: 标记默认链
    def clean(self): ...                                      # [OK] v3 新增: 校验每 GameProfile 最多一个 is_default

# [OK] TaskChainExecution 模型 (阶段 2 v3 新增) — TaskChain 派发追踪
class TaskChainExecution:
    chain = models.ForeignKey(TaskChain, ...)                 # 关联的任务链
    device = models.ForeignKey(Device, ...)                   # 运行时设备绑定
    game_account = models.ForeignKey(GameAccount, ...)        # 运行时账户绑定 (nullable)
    triggered_by = models.ForeignKey(User, ...)               # 触发者
    status = models.CharField(choices=PENDING/RUNNING/SUCCESS/FAILED/CANCELLED)
    # 1:N → TaskExecution (通过 task_chain_execution FK)

# [OK] GameAccount 模型 (阶段 1 v3 后)
class GameAccount:
    resource_pack = models.ForeignKey(ResourcePack, ...)      # [OK] 回退: 账户级别默认资源包, Task.resource_pack 未设置时使用
    game_profile = models.ForeignKey(GameProfile, ...)        # [OK] v3 新增: 明确归属
    # allowed_resource_packs (M2M) 已移除 → 死字段, 执行不校验

# [OK] TaskDevice 中间表 (阶段 1 后)
class TaskDevice:
    task = models.ForeignKey(Task, ...)
    device = models.ForeignKey(Device, ...)
    # is_default 已移除 → 死字段, 执行链路不读取

# [OK] Device 模型 (阶段 1 v3 后)
class Device:
    agent = models.ForeignKey(Agent, null=True, blank=True)   # Phase R18: 自动关联
    game_profile = models.ForeignKey(GameProfile, ...)        # [OK] v3: 绑定游戏档案
    game_account = models.ForeignKey(GameAccount, ...)        # [OK] v3: 运行时绑定当前账户
    # screenshot_method/input_method/control_mode: 'auto' 时继承 GameProfile (阶段 5)

# [OK] TaskExecution 模型 (阶段 2 v3 后)
class TaskExecution:
    task = models.ForeignKey(Task, ...)
    game_account = models.ForeignKey(GameAccount, ...)        # [OK] 阶段 1: 运行时账户绑定
    device = models.ForeignKey(Device, ...)                   # [OK] 阶段 1: 运行时设备绑定
    task_chain_execution = models.ForeignKey(TaskChainExecution, null=True, ...)  # [OK] 阶段 2 v3
```

---

## 四、设备自动关联流程（Phase R18 新增）

### 4.0 Agent 启动后的设备同步机制

```
Agent 启动
    ↓
1. 本地自动发现 (DeviceCenter.auto_discover)
   ├─ 扫描 ADB 模拟器 (EmulatorDiscovery)
   └─ 扫描 Windows 窗口 (WindowDiscovery)
    ↓
2. 注册到本地 DeviceManager
    ↓
3. WebSocket 连接 Server 成功
    ↓
4. 发送 device.sync 消息 (ConnectionManager._sync_devices)
   ├─ devices: [{device_id, name, device_type, adb_serial, ...}]
   └─ count: N
    ↓
5. Server 接收并处理 (AgentConsumer._handle_device_sync)
   ├─ 遍历设备列表
   │   ├─ 存在？→ 更新状态为 online + 关联当前 Agent
   │   └─ 不存在？→ 创建新 Device 记录 + 关联当前 Agent
   └─ 返回 device.sync_ack 确认
        ├─ created: X (新建数量)
        ├─ updated: Y (更新数量)
        └─ errors: Z (失败数量)
    ↓
6. 完成：所有设备已关联到该 Agent [OK]
```

### 4.1 核心设计原则

| 原则 | 说明 |
|------|------|
| **一台机器一个 Agent** | 单机模式下只运行一个本地 Agent |
| **自动发现** | Agent 启动时自动扫描本机所有可用设备 |
| **主动上报** | 连接成功后立即同步设备列表到 Server |
| **幂等操作** | 重复同步不会创建重复记录 |
| **事务保证** | 使用数据库事务确保原子性 |

### 4.2 技术实现

| 层级 | 文件 | 方法/函数 | 功能 |
|------|------|----------|------|
| **Agent 端** | `worker/src/client/connection.py` | `_sync_devices()` | 收集设备信息并发送 device.sync |
| **Agent 端** | `worker/src/__main__.py` | `run_agent()` Step 6 | 连接成功后调用 _sync_devices() |
| **Server 端** | `backend/agents/consumers.py` | `_handle_device_sync()` | 处理设备同步消息，创建/更新 Device 记录 |
| **数据层** | `backend/agents/models.py` | `Device.agent` FK | 设备与 Agent 的外键关联 |

### 4.3 窗口类型与行为

> 注：`Device` 模型的 `device_type` 字段仅包含 `WINDOWS` 和 `EMULATOR` 两种（见 `backend/agents/models.py`）。下表为概念分类 + 行为差异。

**窗口分类**：GAF 控制两类窗口，行为差异取决于控制方式和窗口类型。

| 类型 | 发现方式 | ADB 序列号示例 | 能否最小化 | 控制方式 | 说明 |
|:---:|:---:|:---|:---:|:---|:---|
| **emulator** | EmulatorDiscovery | `127.0.0.1:5555` | [OK] 可最小化 | ADB（截图/输入不依赖窗口前台） | 雷电/MuMu/夜神等模拟器 (DeviceType.EMULATOR)。最小化后仍可通过 ADB 控制 |
| **windows** | WindowDiscovery | - | [FAIL] 视控制模式而定 | Win32 API | Windows 游戏窗口 (DeviceType.WINDOWS)。控制模式决定前台依赖程度 |
| **android** | ADB devices | `emulator-5554` | N/A | ADB | 真机通过 ADB 访问，归入 EMULATOR 类型，无独立枚举 |
| **ios** | 未来扩展 | - | N/A | [FAIL] 待实现 | iOS 设备 (待实现) |

**非模拟器窗口的控制模式**（`Device.control_mode`，继承自 `GameProfile.default_control_mode`）：

| 控制模式 | 窗口要求 | 输入方式 | 截图方式 | 适用场景 |
|---------|---------|---------|---------|---------|
| **foreground（前台模式）** | 窗口必须在前台可见 | SendInput（模拟真实输入） | 全部方式 | 需要真实输入的游戏，抗检测强 |
| **background（后台模式）** | 窗口可被遮挡/最小化 | PostMessage（发消息到窗口） | 后台截图（PrintWindow/BitBlt） | 窗口可后台操作的游戏，效率高 |
| **pseudo_background（伪后台）** | 窗口临时切换到前台操作 | 混合：后台操作 + 必要时前台 | 混合 | 部分操作必须前台的游戏 |

**模拟器窗口始终可通过 ADB 控制**：无论窗口是否最小化、是否在前台，ADB 截图 (`screencap`/`scrcpy`) 和 ADB 输入 (`adb input`/`minitouch`/`MaaTouch`) 都不依赖窗口状态。这是模拟器和非模拟器窗口的核心行为差异。

---

## 五、执行流程

### 5.1 执行触发

```
触发方式：
  ├─ 手动执行（用户点击）
  ├─ 定时触发（Cron 表达式）
  └─ API 调用
```

### 5.2 执行调度

```
1. 获取待执行账户列表
2. 获取空闲设备列表（已关联 Agent 的在线设备）
3. 并行调度：
   设备 A 空闲 → 分配账户 A（用账户A的资源包）
   设备 B 空闲 → 分配账户 B（用账户B的资源包）
   设备 C 空闲 → 分配账户 C（用账户C的资源包）

   设备 A 完成 → 分配账户 D
   设备 B 完成 → 分配账户 E
```

> **调度链路详见**: [dispatch-flow.md](../architecture/cross-cutting/dispatch-flow.md) — 从执行创建到 Agent 执行的完整链路, 含 Celery 调度、服务协调、异常恢复机制。

### 5.3 执行组合公式

```
每次执行 = 任务 (流程) + 资源包 (任务关联, 视觉) + 账户服务器 (模板选择) + 可用设备 (执行)
```

**资源包解析优先级**（N197-8）:
1. **Task.resource_pack**（主）— 任务直接关联的资源包，运行时加载该资源包下的模板
2. **GameAccount.resource_pack**（回退）— 账户级别默认资源包，供未绑定资源包的任务使用
3. **服务器模板分区** — 通过 `ResourcePack.get_templates_for_server(server_region)` 根据账户的 `server_region` 字段加载对应服务器的模板子目录；默认国服（`cn`）

---

## 六、轮换策略

### 6.1 轮换维度

| 维度 | 说明 |
|------|------|
| **账户维度** | 账户 A 的所有任务 → 账户 B 的所有任务 |
| **设备维度** | 哪个设备空闲就分配下一个账户 |
| **资源包归属** | 资源包绑在任务上（主）+ 回退到账户（辅）；`ResourcePack.get_templates_for_server(server_region)` 按服务器分区加载模板 |

### 5.2 轮换规则类型

| 策略 | 说明 |
|------|------|
| 按时间切换 | 每隔 N 分钟切换账户 |
| 按任务完成切换 | 当前账户所有任务完成后切换 |
| 按失败次数切换 | 连续失败 N 次后切换 |

---

## 七、前端路由结构

> **2026-07-13 (C-026)**: UI 归一化 — 34 个 `<Navigate>` 兼容重定向 → 2 个；ops 组 9→7 项（log-analysis+crash-reports 合并到 `/ops/logs`）；system 组 8→7 项（unattended-strategy 合并到 `/ops/unattended`）；`/resources/templates` → `/resources/template-effectiveness`。

```
📊 工作台     /dashboard
📋 任务       /tasks, /tasks/pipeline, /tasks/recordings, /tasks/marketplace
🖥 设备       /devices, /devices/emulators, /devices/windows
📦 资源       /resources, /resources/template-effectiveness, /resources/annotation
👤 账户       /accounts/users, /accounts/game-accounts
📡 运维       /ops/unattended, /ops/executions, /ops/scheduler, /ops/monitors,
              /ops/analytics, /ops/logs, /ops/sla
🤖 AI         /ai/assistant, /ai/qa, /ai/anomaly, /ai/skill-demo,
              /ai/skill-editor, /ai/log-analysis
⚙ 系统       /system/settings, /system/config, /system/api-keys,
              /system/game-profiles, /system/feature-flags, /system/audit-log,
              /system/notifications, /system/plugins, /system/ai-config, /system/ai-usage
```

---

## 八、API 端点规范

| 模块 | URL 前缀 | 说明 |
|------|---------|------|
| 认证 | `/api/v2/accounts/` | 登录/注册/2FA/OAuth |
| 设备 | `/api/v2/agents/` | 设备 CRUD/扫描/健康检查 |
| 任务 | `/api/v2/tasks/` | 任务 CRUD/执行/绑定 |
| 资源 | `/api/v2/resources/` | 资源包/模板/版本 |
| 调度 | `/api/v2/scheduler/` | 定时任务/时间窗口 |
| 监控 | `/api/v2/monitors/` | 规则/事件/诊断 |
| AI | `/api/v2/ai/` | 对话/异常检测 |
| 游戏状态 | `/api/v2/gamestate/` | GameProfile CRUD + 6 个 bind/unbind @action 端点 (2026-07-14 新增) + 5 个子资源列表 (tasks/task_chains/devices/accounts/resource_packs) + default-routine/dispatch-routine |
| 设置 | `/api/v2/settings/` | 系统配置 |

---

## 九、Backend App 架构（17 个 Django App + 1 个纯 Python 包）

> **v3.6 (2026-08-04)** — 计数校正: 17 个 Django app (在 `INSTALLED_APPS`) + `device_bridge` 纯 Python 包 (跨平台抽象层, 不在 INSTALLED_APPS, 无 apps.py/models.py)
> 本次合并: tracing/i18n/search → gaf_core; metrics → monitors; qa → gaf_ai; TaskExecution CRUD 视图 → tasks (executions app 保留执行管理视图层, 见 9.2 注)
> 按职责分组，每个 app 一个业务域：

### 9.1 业务核心 (5 个)

| App | 职责 | 关键模型 |
|-----|------|---------|
| [accounts](file:///d:/code/GAF/backend/accounts) | 用户/游戏账户/2FA/OAuth/API Key | User, GameAccount, APIKey, LoginHistory, UserSession |
| [tasks](file:///d:/code/GAF/backend/tasks) | 任务/执行/调度/标签/文件夹 | Task, TaskExecution, ScheduledTask, TaskVersion, TaskFolder |
| [pipeline](file:///d:/code/GAF/backend/pipeline) | Pipeline JSON + 录制 + TaskChain 编排 + routine.json 转换 | Pipeline, PipelineSnapshot, TaskChain, TaskChainNode, TaskChainExecution, Recording |
| [resources](file:///d:/code/GAF/backend/resources) | 资源包/模板/标注 (含唯一 Tag 模型) | ResourcePack, Template, TemplateVersion, TemplateAnnotation, Tag |
| [workers](file:///d:/code/GAF/backend/workers) | Worker/Device/DeviceGroup (原 agents) | Worker, Device, DeviceGroup |

### 9.2 调度执行 (3 个)

| App | 职责 | 关键模型 |
|-----|------|---------|
| [scheduler](file:///d:/code/GAF/backend/scheduler) | 无人值守/恢复引擎/时间窗口/轮换/AutoStop | UnattendedSession, GameAccountRotation, TimeWindow, WarmupConfig, AutoStopCondition, RecoveryLog, PreflightCheck |
| [monitors](file:///d:/code/GAF/backend/monitors) | 监控规则/事件/告警升级 + SLA 指标 (metrics 合并) | MonitorRule, MonitorEvent, SLAMetric |
| [executions](file:///d:/code/GAF/backend/executions) | 执行管理视图层 (无自有模型，视图读取 TaskExecution/ExecutionStep) + 分析报表端点 (`/executions/*` + `/analytics/*`) | (无 Model) |

> 注: TaskExecution CRUD 视图集 (task-executions) 已于 2026-08-04 迁入 `tasks` app (`tasks/execution_views.py`)；`executions` app 仍保留执行管理视图层 (steps/intervene/analysis/daily-report/unattended-logs/trend + analytics 5 端点)，无自有模型。ExecutionStep 为运行期步骤权威模型 (TaskStep 已于 2026-08-30 合并入 ExecutionStep)。

### 9.3 AI 模块 (2 个)

> **概念边界（2026-08-29 锁定）**：本节的 "Agent" = **AI 智能体**（`backend/gaf_ai` LangGraph agent，会话模型 `AgentSession`），与 §十 的 **Worker（自动化执行节点/进程，原 "Agent"）** 是不同概念。未来 AI 相关开发统一归入本模块（`gaf_ai` + `skills`）。LLM 日志分析能力（`LLMAnalysisResult`，前端 `/ai/log-analysis`）后端模型历史原因落在 `debug` app（见 §9.4），概念上归属本 AI 模块。

| App | 职责 | 关键模型 |
|-----|------|---------|
| [gaf_ai](file:///d:/code/GAF/backend/gaf_ai) | LLM Router + RAG + Agent + 异常检测 + 智能问答 + 成本控制 (qa 合并) | LLMConfig, ModelEvaluation, CustomSkill, AgentSession, QASession, QAMessage, LLMUsageLog |
| [skills](file:///d:/code/GAF/backend/skills) | Skill YAML 引擎 + 市场 | SkillDefinition, SkillMarketItem |

**AI Agent (LangGraph)** — `backend/gaf_ai/agent/`:
- `graph.py` — LangGraph 状态图定义
- `tools.py` — Agent 工具集 (设备控制/任务查询/Pipeline 生成)
- `llm_adapter.py` — LLM 适配器 (OpenAI/DeepSeek/Ollama)
- `models.py` — Agent 会话/消息模型（`AgentSession` 为 AI 智能体会话，**非**执行节点 WS 会话）
- `views.py` — Agent API 端点

### 9.4 运维监控 (1 个)

| App | 职责 | 关键模型 |
|-----|------|---------|
| [debug](file:///d:/code/GAF/backend/debug) | 崩溃报告/日志归档/LLM 分析 | CrashReport, DebugLogArchive, LLMAnalysisResult (备份为 ZIP 快照 API `/tasks/backup/`，无 ORM 模型 BackupRecord/BackupJob) |

### 9.5 基础设施 (3 个 Django app + 1 个纯 Python 包)

| App | 职责 | 关键模型 |
|-----|------|---------|
| [protocol](file:///d:/code/GAF/backend/protocol) | WebSocket 消息帧协议/心跳/配额 (5 active WS routes, 见 data-flow.md §0) | WorkerSession (执行节点 WS 会话；AI 智能体会话 `AgentSession` 见 §9.3 `gaf_ai`) |
| [device_bridge](file:///d:/code/GAF/backend/device_bridge) | 🔧 纯 Python 包 (非 Django app, 不在 INSTALLED_APPS, 无 apps.py/models.py); 跨平台设备桥接 (Win/macOS/Linux 抽象层, P-028 [OK]); 平台代码在 `backend/device_bridge/platforms/{windows,macos,linux}/` | (无 Model, 纯接口层) |
| [gaf_core](file:///d:/code/GAF/backend/gaf_core) | 全局 mixin/exception/error_code/middleware + 链路追踪 (tracing) + 国际化 (i18n) + 聚合搜索 (search); **AuditMixin (C-045, 114 接入点, 19 个 ViewSet 已接入)**; LogEntry 统一日志中心 | LogEntry |
| [gamestate](file:///d:/code/GAF/backend/gamestate) | OCR 区域识别/阈值触发/GameProfile + bind/unbind 端点 | GameState, GameVersionCheck, GameProfile (ScreenState/ScreenStateTransition 已于 2026-07-13 移除) |

### 9.6 系统设置 (3 个)

| App | 职责 | 关键模型 |
|-----|------|---------|
| [settings](file:///d:/code/GAF/backend/settings) | LLMConfig/FeatureFlag/AppSettings | LLMConfig, FeatureFlag, AppSettings |
| [notifications](file:///d:/code/GAF/backend/notifications) | 7 渠道通知 | Notification, AlertRule, WebhookConfig |
| [plugins](file:///d:/code/GAF/backend/plugins) | 插件系统/沙箱 | PluginPackage, PluginSandbox |

---

## 十、Worker 架构（自动化执行节点）

> **概念边界**：本节 "Worker" = 自动化执行节点/进程（原称 "Agent"），负责连接后端、持有令牌、在 Device 上执行 Pipeline。**与 §9.3 的 Agent（LangGraph AI 智能体）是不同概念**——Agent 指 AI 推理实体，Worker 指执行节点。术语拆分详见 `docs/analysis/concept-naming-normalization.md` OQ-10。

Worker 是独立 Python 进程，通过 WebSocket 连接后端，提供跨平台设备控制能力。

### 10.1 模块结构

```
worker/src/
├── engine/                # Pipeline 执行引擎
│   ├── nodes/             # 35+ 节点类型 (click/swipe/ocr/template_match/loop/branch/...)
│   ├── pipeline_engine.py # 主执行器 (PipelineEngine)
│   ├── executor.py        # TaskExecutor 统一执行入口
│   ├── parser.py          # Pipeline JSON 解析 + PipelineGraph (DAG 结构/拓扑校验)
│   ├── validator.py       # 循环检测/死节点/类型校验
│   └── context.py         # 执行上下文
├── devices/               # 设备抽象层
│   ├── adb/               # ADB 设备 + 连接池
│   ├── base.py            # 抽象基类
│   ├── center.py          # DeviceCenter (自动发现)
│   ├── emulator_controller.py  # 模拟器生命周期
│   ├── emulator_discovery.py   # 5 途径扫描
│   └── health_checker.py  # 设备健康检查
├── platforms/windows/     # Windows 平台实现 (完整)
│   ├── screenshot.py      # 6 种截图方式 (WGC/DXGI/BitBlt/PrintWindow/GDI/LDOpenGL)
│   ├── input.py           # 输入 (SendInput/PostMessage/Legacy)
│   ├── input_variants.py  # 9 输入变体
│   ├── background_key_input.py  # 后台按键守护 (RegisterHotKey+WM_HOTKEY)
│   ├── wgc.py             # Windows Graphics Capture
│   ├── dxgi_capture.py    # DXGI Desktop Duplication
│   ├── ldopengl.py        # LDPlayer OpenGL 截图
│   ├── nemu_ipc.py        # MuMu NemuIpc 输入
│   ├── subwindow.py       # 子窗口合成
│   ├── dccache.py         # DC/Bitmap 缓存
│   └── pseudo_minimizer.py  # 伪最小化
├── recognition/           # 识别引擎
│   ├── ocr/               # OCR 4 引擎 (PaddleOCR/RapidOCR/ONNXPaddleOCR/DGOCR)
│   │   ├── registry.py    # 引擎注册表 + 竞速选择
│   │   ├── opencc_converter.py  # 繁简转换
│   │   └── post_processor.py  # 后处理 + gettext 翻译
│   └── cache.py           # pHash 缓存 (避免重复识别)
├── core/                  # 核心工具
│   ├── state_machine_engine.py   # StateMachineEngine 状态机执行
│   ├── state_machine.py   # 状态机引擎
│   ├── script_dsl.py      # Script DSL 编译器 (625 行)
│   ├── worker_pool.py     # Alas 风格 8 线程池
│   ├── retry.py / timeout.py / delay.py  # 重试/超时/延迟
│   ├── recovery.py        # 5 层异常恢复
│   ├── safe_point.py      # 安全点检查
│   ├── cleanup.py         # 清理管理器
│   ├── recording.py       # 录制系统
│   ├── recording_to_pipeline.py  # 录制转 Pipeline
│   ├── batch_ocr.py       # 批量 OCR
│   ├── onnx_engine.py     # ONNX 神经网络推理
│   ├── segmentation.py    # AI 分割 (SAM/U²-Net)
│   ├── emulator_sync.py   # 模拟器同步
│   └── task_queue.py      # 任务队列
├── client/                # WebSocket 客户端
│   ├── connection.py      # 连接管理 + 设备同步
│   └── handler.py         # 消息处理
├── ai/                    # Worker 端 LLM 客户端
│   └── llm_client.py
├── auth/                  # Agent 端认证
│   └── token_store.py
├── monitor/               # 资源监控
│   ├── manager.py
│   ├── handlers.py
│   └── resources.py
└── utils/                 # 工具
    ├── coord_transformer.py  # Windows 5 层坐标变换 (BASE→LOGICAL→PHYSICAL→SCREEN + SUB_IMAGE)
    ├── adb_coord_transformer.py  # ADB 路径坐标变换 (N191 §10.7 P0-2, base→physical 直接缩放)
    ├── display_context.py  # RuntimeDisplayContext 数据类
    ├── screenshot_diagnostic.py  # 截图诊断
    └── debug_image_saver.py
```

### 10.2 Worker 与 Backend 通信协议

```
Worker 启动
  ├─ 1. 本地自动发现设备 (DeviceCenter.auto_discover)
  │      ├─ ADB 模拟器 (EmulatorDiscovery)
  │      └─ Windows 窗口 (WindowDiscovery)
  ├─ 2. WebSocket 连接 Backend (ws://backend:8000/ws/protocol/agents/)
  ├─ 3. 发送 device.sync 消息上报设备列表
  ├─ 4. Backend 创建/更新 Device 记录 + 关联 Worker
  ├─ 5. Backend 下发任务 (Pipeline JSON)
  ├─ 6. Worker 执行 + 实时上报进度 (WebSocket)
  └─ 7. 执行完成/失败 → Backend 记录 TaskExecution
```

**消息帧协议** (`backend/protocol/constants.py`):
- `MESSAGE_FRAME_SCHEMA` — 消息帧 schema
- 心跳: agent 端 `heartbeat_interval=10s` (TD-340, 原 30s 临界 backend `HEARTBEAT_OFFLINE_SECONDS=30s` 导致 status 抖动), 3x 安全余量
- 配额: `protocol/quota.py` 限流

### 10.3 Worker 进程管理 (TD-339, 2026-07-23)

Worker 进程管理分两层独立机制, 不要混淆:

| 层 | 代码位置 | 保护范围 | 机制 |
|----|---------|---------|------|
| **backend 端自启 worker** | `backend/workers/worker_runtime.py` (TD-217 闭环, 原 `backend/agents/agent_runtime.py`) | backend 拉起 worker 子进程时 | `manager.lock` + `worker.pid` + `_kill_stale_worker_processes()` + DB 心跳双检测 + 指数退避重启 |
| **worker 自身独立进程** | `worker/src/__main__.py` `acquire_singleton_lock()` (TD-339, 原 `worker/src/__main__.py`) | 手动 `python -m src` 或外部脚本调用时 | `%TEMP%\gaf_worker_lock\standalone.pid` PID 文件锁, 检测到存活 PID 则 exit(1), `--skip-singleton-check` 可绕过 (仅限调试) |

**关键边界**: backend 端 `worker_runtime.py` 的 `_kill_stale_worker_processes()` 只在 backend 自启 worker 时生效; 用户手动 `python -m src` 启动完全绕过 backend 管理, 由 worker 自身的 `acquire_singleton_lock()` 兜底.

---

## 十一、跨平台抽象层

参考 MaaFramework 跨平台设计，GAF 采用平台抽象层 + 设备插件系统：

```
┌──────────────────────────────────────────────┐
│              GAF 统一设备接口                   │
│  screenshot() / click() / swipe() / key_press() │
└──────────────────┬───────────────────────────┘
                   │ device_bridge/platforms/base.py
┌──────────────────┼───────────────────────────┐
│  Windows 插件    │  macOS 插件    │  Linux 插件  │
│  WGC/BitBlt/     │  CGWindowList  │  XGetImage/ │
│  PrintWindow/    │  screencapture │  XShm/      │
│  DXGI/GDI/       │  CGEventPost/  │  xdg-portal │
│  LDOpenGL        │  CGEventMouse/ │  XTest/     │
│  SendInput/      │  AppleScript/  │  XSendEvent/│
│  PostMessage/    │  cliclick      │  uinput/    │
│  SendMessage     │                │  evdev      │
└──────────────────┴───────────────┴────────────┘
                   │
┌──────────────────┴───────────────────────────┐
│         模拟器 ADB 插件（跨平台通用）            │
│  scrcpy / DroidCast / NemuIpc / ADB screencap  │
│  MaaTouch / minitouch / ADB input              │
└──────────────────────────────────────────────┘
```

### 11.1 后端跨平台桥接 (device_bridge)

**位置**: `backend/device_bridge/platforms/`

| 平台 | 路径 | 实现 |
|------|------|------|
| Windows | [platforms/windows/](file:///d:/code/GAF/backend/device_bridge/platforms/windows) | `_dxgi.py` `_bitblt.py` `_printwindow.py` `_adb_*.py` `input.py` `ld_opengl.py` `discovery.py` (backend WGC mock 已删除 TD-125, `_capture_wgc` delegate 到 PrintWindow; agent 端 `worker/src/platforms/windows/wgc.py` 保留真实 WGC 实现) |
| macOS | [platforms/macos/](file:///d:/code/GAF/backend/device_bridge/platforms/macos) | `screenshot.py` `input.py` `discovery.py` |
| Linux | [platforms/linux/](file:///d:/code/GAF/backend/device_bridge/platforms/linux) | `screenshot.py` `input.py` `discovery.py` |

**抽象接口** (`device_bridge/platforms/base.py`):
```python
class PlatformBase(ABC):
    @abstractmethod
    def take_screenshot(self) -> bytes: ...
    @abstractmethod
    def click(self, x: int, y: int) -> bool: ...
    @abstractmethod
    def discover_devices(self) -> list[DeviceInfo]: ...
```

**业务代码通过 registry 选平台**:
```python
from device_bridge.platforms.registry import get_platform
platform = get_platform()  # 自动检测当前 OS
platform.click(100, 200)
```

### 11.2 Agent 端平台实现

**位置**: `worker/src/platforms/windows/` (目前仅 Windows 完整实现, macOS/Linux 在 device_bridge)

### 11.3 跨平台能力矩阵

| 能力 | Windows | macOS | Linux | 模拟器(ADB) |
|------|:---:|:---:|:---:|:---:|
| 截图方式数 | 6 | 2 | 3 | 10 |
| 输入方式数 | 3 (TD-090 删除 9 变体) | 3 | 3 | 6 |
| 后台截图 | [OK] agent WGC/PrintWindow (backend WGC mock 删除 TD-125, DXGI 支持 hwnd crop TD-124) | ⚠️ CGWindow 有限 | ⚠️ XShm 有限 | [OK] scrcpy/NemuIpc |
| 后台输入 | [OK] PostMessage (client 坐标, Spec B TD-122); SendInput/PseudoBackground 串行化 (Spec C TD-121) | [FAIL] 需辅助功能权限 | ⚠️ XSendEvent | [OK] minitouch/MaaTouch (动态端口分配, Spec D TD-123) |
| 伪最小化 | [OK] | [FAIL] 不需要 | [FAIL] 不需要 | [FAIL] 不需要 |
| 模拟器发现 | [OK] 注册表+进程 | ⚠️ 进程+ADB | ⚠️ 进程+ADB | [OK] ADB devices |
| Multi-game 模式约束 | [OK] FeatureFlag `unattended_multi_game_mode` + 白名单降级 (Spec A) | [FAIL] 不适用 | [FAIL] 不适用 | [OK] 同 Windows 白名单 |
| OCR | [OK] 全引擎 | [OK] PaddleOCR/RapidOCR | [OK] PaddleOCR/RapidOCR | — |
| ONNX 推理 | [OK] DirectML/CUDA | [OK] CoreML/CPU | [OK] CUDA/CPU | — |

---

## 十二、Desktop 桌面应用（Electron）

**位置**: `desktop/`

Electron 封装 GAF 前端 + 后端 + Agent 为一体化桌面应用，便于分发。

```
desktop/
├── src/
│   ├── main/               # 主进程
│   │   ├── index.ts        # 入口
│   │   ├── window.ts       # 窗口管理
│   │   ├── tray.ts         # 系统托盘
│   │   ├── ipc.ts          # IPC 通信
│   │   ├── autostart.ts    # 开机自启
│   │   ├── updater.ts      # 自动更新
│   │   └── config.ts       # 配置
│   └── preload/            # 预加载脚本
├── resources/              # 图标 (icon.ico/icon.png/tray-icon.png)
├── electron-builder.yml    # 打包配置
└── vite.config.ts          # Vite 集成
```

---

## 十三、当前状态

### 13.1 已完成模块

| 模块 | 状态 | 说明 |
|------|------|------|
| 认证系统 | [OK] | JWT + 2FA + OAuth + API Key |
| 设备管理 | [OK] | Windows + Android + 模拟器 + 自动关联 |
| 任务管理 | [OK] | CRUD + Pipeline 编辑 + 录制 + 市场 |
| 资源包管理 | [OK] | 导入/导出 + 模板库 + 标注 |
| 游戏账户 | [OK] | CRUD + 分组 + 轮换 + AES 加密 |
| 调度中心 | [OK] | 定时任务 + 时间窗口 + 无人值守 + 5 层恢复 (task 级 + step 级信号接入 P-010) |
| TaskChain 编排 | [OK] | DAG editor + Pipeline 一等公民节点 (TD-110) + routine.json → TaskChain 自动转换 |
| 监控告警 | [OK] | 规则 + 事件 + 诊断 + 告警升级 (P1→P0) |
| AI 模块 | [OK] | 助手 + QA + Skill + LangGraph Agent + RAG |
| 跨平台层 | [OK] | Windows 完整 (agent 侧 `worker/src/platforms/windows/`) + macOS/Linux 已落地 (backend 侧 `backend/device_bridge/platforms/{macos,linux}/`, P-028); 注: agent 侧仅 Windows, macOS/Linux 在 backend 侧 |
| 运维监控 | [OK] | 链路追踪 + SLA 指标 + 崩溃报告 + 日志归档 |
| **审计日志 (C-045)** | [OK] | AuditMixin (gaf_core/mixins/audit.py) — 114 接入点, 19 个 ViewSet 自动写 AuditLog (accounts/tasks/agents/pipeline/resources/qa/notifications/scheduler/settings/gamestate/debug/protocol/monitors/plugins); AuditLog 模型在 `accounts/models.py:454` |
| 通知系统 | [OK] | 7 渠道 (邮件/Webhook/钉钉/飞书/企微/Telegram/自定义) |
| 插件系统 | [OK] | 上传/安装/启停/沙箱 |
| 国际化 | [OK] | 4 语言 (en/zh_Hans/ja/ko) |
| **服务层 (Phase 1)** | [OK] | TaskExecutor 统一执行入口 + TaskService/ExecutionService 服务层子包 |
| **设备发现注册表 (Phase 2)** | [OK] | DeviceDiscoveryRegistry 注册表驱动发现，统一 ADB/Windows/模拟器发现 |
| **统一 LLM 客户端 (Phase 2)** | [OK] | BaseLLMClient ABC + WebSocket RPC，agent 和 backend 统一客户端 |
| **EventBus (Phase 3)** | [OK] | monitors/bus.py 跨进程事件总线，事件发布/订阅/路由 |
| **ArchiveService (Phase 3)** | [OK] | 数据库归档服务，自动清理历史记录 |
| **GafDaemon (Phase 3)** | [OK] | `scripts/gaf_daemon.py` Python 守护进程实现；`gaf_services.ps1` Windows 启停兼容层；统一称 **GafDaemon** 为权威名 |
| **服务编排健康感知 (2026-08-29)** | [OK] | app 级健康探针 + 看门狗健康循环 + 状态灯服务矩阵；服务终端输出捕获 `debug/system/services/*.log` + ERROR 扫描 → 服务管理页 `/system/services`（系统页签） |
| Desktop | 🔧 | Electron 框架已搭建 (待 M2 完整集成) |

### 13.2 架构问题（已修复）

| 问题 | 当前实现 | 正确实现 | 优先级 |
|------|---------|---------|--------|
| ~~资源包绑定位置~~ | ~~Task.resource_pack (FK)~~ | ~~GameAccount.resource_pack (FK)~~ | ⚠️ N197-8 重新引入: Task.resource_pack 作为「任务直接关联资源包」的独立 FK，与 GameAccount.resource_pack 并存。区别：Task.resource_pack 是任务运行时加载模板的依据，GameAccount.resource_pack 是账户级别默认资源包。 |
| 设备资源映射表 | ~~DeviceResourceMapping 存在~~ | 已删除 | [OK] 已修复 (R16) |
| 前端绑定 UI | 只有资源包绑定 | 账户/设备绑定 | [OK] 已修复 (R16) |
| 任务-账户绑定 | 后端有 M2M，前端无 UI | 补全绑定 UI | [OK] 已修复 (R16) |

### 13.3 缺失的前端 UI（已补全）

| 功能 | 后端 | 前端 | 说明 |
|------|------|------|------|
| 任务绑定资源包 | [OK] FK | [OK] 已完成 | TaskFormModal 支持 resource_pack 选择；任务列表显示资源包列 + 下拉筛选 |
| 任务绑定账户 | [OK] M2M | [OK] 已完成 | TaskFormModal 支持 game_accounts 多选 |
| 任务分配设备 | [OK] TaskDevice | [OK] 已完成 | TaskFormModal 支持 devices 多选 |
| 账户绑定资源包 | [OK] FK | [OK] 已完成 | GameAccountEditor 支持 resource_pack 选择 |

---

## 十四、关键设计决策记录

| 决策 | 内容 | 原因 |
|------|------|------|
| 轮换双入口 + 循环轮换 (TD-400) | [OK] 2026-08-26 已实施 | 任务级轮换（每次执行按 `rotation_rule` 全账户矩阵选取）适合"定时跑一遍"；无人值守级轮换（`session.rotation_rule` + `loop_rotation`）适合"持续循环挂机"——链完成后账户归还池子继续派发，循环模式不触发 `all_completed` 自动停止 |
| 资源包绑在任务上（主）+ 回退到账户（辅） | [OK] N197-8: Task.resource_pack 直接关联；`get_templates_for_server(server_region)` 按服务器分区加载 | 任务运行时加载模板的依据；换服务器只需改任务绑定的资源包，同一任务可被多个服务器共用 |
| 设备不绑资源包 | [OK] 已实施 | 设备只负责执行方式，与游戏无关 |
| 轮换按账户维度 | [OK] | 一个账户所有任务完成后再换下一个 |
| 设备并行执行 | [OK] | 多开模拟器可同时跑不同账户 |
| TaskDevice 中间表 | [OK] 新增 | 任务指定执行设备，替代原 DeviceResourceMapping |
| Agent 自动关联 | [OK] Phase R18 | Agent 启动上报 → Server 创建/更新 Device |
| 跨平台抽象层 | [OK] P-028 | Windows/macOS/Linux 统一接口，业务代码不直接调平台 API |
| LangGraph AI Agent | [OK] 已实施 | 状态图 + 工具集 + LLM 适配器 |
| Pipeline JSON + StateMachineEngine 并存 | [OK] 已实施 | Pipeline 声明式上层 + StateMachineEngine 编程式底层 + StateMachine 状态驱动（task_type `chain` 为 `state_machine` 的废弃别名） |
| 5 层截图降级 | [OK] 已实施 | scrcpy→droidcast→nemuipe→ld_opengl→screencap |
| 3 方法输入 (TD-090) | [OK] 已实施 | SendInput/PostMessage/PseudoBackground (TD-090 删除 1320 行 9 变体死代码) |
| Multi-game 模式开关 (Spec A) | [OK] 2026-07-16 | FeatureFlag `unattended_multi_game_mode` + `resolve_device_methods` 白名单降级 + 前端模式选择器 disabled 约束 |
| PostMessage client 坐标 (Spec B / TD-122) | [OK] 2026-07-16 | 4 个非 scroll PostMessage 方法移除 `_client_to_screen`, 直接 pack client 坐标 (WM_LBUTTONDOWN/UP/MOUSEMOVE lParam 期望 client) |
| SendInput/PseudoBackground 串行化 (Spec C / TD-121) | [OK] 2026-07-16 | `WindowsInputHandler` 实例级 `threading.RLock` 串行化 6 个方法 (RLock 因 PseudoBackground 内部调 `_sendinput` 需重入) |
| minitouch/MaaTouch 动态端口 (Spec D / TD-123) | [OK] 2026-07-16 | per-serial CRC32 哈希端口分配 + 线性探测 (minitouch [11111, 11611), maatouch [13113, 13613)); 同 serial 同端口 |
| DXGI per-window crop (Spec E / TD-124) | [OK] 2026-07-16 | `DXGICapture.capture_window(hwnd)` — GetWindowRect + DesktopCoordinates 平移 + numpy slice + 边界 clip |
| Backend WGC mock 移除 (Spec E / TD-125) | [OK] 2026-07-16 | 删除 `_wgc.py` mock; `_capture_wgc` delegate 到 PrintWindow; `WINDOWS_METHODS` 移除 'WGC'; `MULTI_GAME_SAFE_SCREENSHOT_METHODS` 移除 'wgc' |
| 两套 WebSocket | [OK] 已实施 | agents (同步+ACK) + protocol (异步+帧协议) |
| GameProfile 聚合根 bind/unbind 端点 | [OK] 2026-07-14 | 详情页 4 Tab 管理子资源绑定关系；资源包 Tab 只读（绑 Account，架构 §3.2） |
| ScreenState 移除 | [OK] 2026-07-13 | 死代码清理：ScreenState/ScreenStateTransition 模型 + 前端编辑器全删 |
| 前端 UI 归一化 (C-026) | [OK] 2026-07-13 | 34 个 Navigate → 2 个；ops 9→7 项；system 8→7 项；概念归一化（日志=/ops/logs，LLM 分析=/ai/log-analysis） |

---

## 十一、概念速查与澄清

### 11.1 循环任务 ≠ 监控任务 (OQ-7)

| 概念 | 定义 | 代码实体 |
|------|------|----------|
| **循环任务** | 任务按固定/动态周期重复执行 | `TaskChain` + `LoopNode` / `UnattendedSession.loop_rotation` + `rotation_index` |
| **监控任务** | 持续观测系统/业务指标，触发告警/恢复 | `monitors` app: `MonitorRule`/`MonitorEvent`/`SLAMetric` + `worker/src/monitor/MonitorManager` + Pipeline `monitor` 节点 |

> **澄清**："监控任务" 不是一种任务类型，而是 `monitors` 子系统 + Agent 端 `MonitorManager` + Pipeline 监控触发节点的组合。循环任务与监控不同域，勿混淆。

### 11.2 三块健康面与 Header 标签 (OQ-8)

| 健康面 | 入口 | 语义 |
|--------|------|------|
| **系统综合状态** | `HeaderStatusIndicator` (顶部 Header) | `system_status_view.overall`：全部服务健康 **且** ≥1 Worker/Device online/idle **且** 无 `RecoveryLog` 失败/系统级恢复错误 |
| **基础设施健康** | `InfraHealthPanel` (`/accounts/init/health/`) | `GafDaemon` 健康探针 + 看门狗循环 + 服务矩阵 |
| **服务列表健康** | `ServicesPage` (`/system/services/`) | 各服务 `health_check` 探针聚合 |

> **前端文案**：Header 显示 **"系统综合状态"**（原 "系统运行状态"），纯 UI 文案修改，零 API/代码冲击。`overall` 逻辑不动。

### 11.3 `get_unified_logical_rect` vs `publish_match_pos` (D23②)

| 符号 | 类型 | 说明 |
|------|------|------|
| `get_unified_logical_rect()` | 方法 (坐标转换器) | `coord_transformer.py:454` — 统一逻辑矩形计算 |
| `step=publish_match_pos` | trace step 值 | `target.py:111` — 识别节点发布匹配位置的追踪步名 |

> **澄清**：二者**异物** — 前者是坐标转换方法，后者是识别节点发布匹配位置的 trace step 值。**不应重命名**，仅文档澄清。

### 11.4 三层节点区分 (OQ-9/F2)

| 层 | 结构 | 用途 |
|------|------|------|
| **Backend Pipeline** | `Pipeline` (JSON) + `PipelineNode` (运行时节点) | 任务执行的声明式图 + 运行时节点实例 |
| **Backend TaskChain** | `TaskChain` + `TaskChainNode` (持久化链节点) | 有序任务/子 Pipeline 序列，支持 `is_default` |
| **Agent 端** | `PipelineNode` (`engine/node.py`) | Worker 侧运行时节点实例，**不同层非同物** |

> **可选改名**：Agent 端 `PipelineNode` → `AgentNode` 以消歧（标 NOT DONE，文档已显式区分）。

### 11.5 Worker / Agent(AI) 术语区分 (OQ-10)

| 概念 | 代码实体 | 含义 |
|------|----------|------|
| **Device** | `workers.Device` | 被控设备：Windows 窗口 / 模拟器实例 |
| **Worker** | `workers.Worker` + `worker/` 进程 + `WorkerConnection`/`WorkerSession`/`WorkerToken`/`WorkerStatus`/`WorkerConsumer`/`WorkerViewSet`/`WorkerSelector` | 自动化执行节点/进程；连接后端、持令牌、在 Device 上跑 Pipeline |
| **Agent (AI)** | `backend/gaf_ai.agent` LangGraph agent + `AgentSession` | **未来 AI 智能体**；与 Worker 不同物，会话模型保留 `AgentSession` |

> 三者清晰：**Device** / **Worker** / **Agent(AI)**。所有"执行节点语义"的 `Agent` 已归一化为 `Worker`（批 G），仅 AI 智能体保留 `Agent`。

---

---

> **版本**: 3.4 | **创建日期**: 2026-05-31 | **最后更新**: 2026-08-02 (N197-8: Task↔ResourcePack FK 直接关联; 更新执行组合公式、轮换策略、核心设计原则)
