---
maintainer: manual
source: GAF 内部专有名词 + 跨领域术语统一
load_when:
- AI 任务开工
- 文档阅读
- 代码 review
priority: medium
symptom:
- kb:terminology
- 术语表
- glossary
- 专有名词
solution: 50+ 术语分类 (架构/任务/设备/AI/平台) + 跨域映射 + 易混淆辨析
related_files:
- docs/reference/tech-stack.md
- .ai-memory/meta/auto-kb/agent-protocol.md
- docs/architecture/overview.md
created_by: AI
generated: 2026-06-16
last_manual_edit: 2026-06-16
---
# Terminology (术语表) - AI 速查

> **适用场景**: AI 阅读文档/代码时查术语, 避免歧义
> **维护者**: manual (术语需人类确认, AI 仅整理)

## 1. 架构类 (10 个)

| 术语 | 全称 | 含义 | 易混淆 |
|------|------|------|--------|
| **GAF** | Game Automation Framework | 游戏自动化框架, 本项目 | vs "GAF International" 鞋业 |
| **PC** | Personal Computer | Windows/macOS/Linux 桌面 | vs "游戏机" (console) |
| **ADB** | Android Debug Bridge | 安卓调试桥, 控制模拟器/真机 | vs "API" |
| **REST** | Representational State Transfer | HTTP + JSON API 风格 | vs "RESTful" (形容词) |
| **WS / WSS** | WebSocket / WebSocket Secure | 全双工实时通信协议 | vs "Web Service" |
| **DRF** | Django REST Framework | Django 的 REST 库 | vs "Django" 本身 |
| **MFA** | Multi-Factor Authentication | 多因素认证 | vs "2FA" (2 因素是 MFA 子集) |
| **JWT** | JSON Web Token | 无状态 token | vs "Session" (有状态) |
| **CRUD** | Create/Read/Update/Delete | 增删改查 | - |
| **M2M** | Many-to-Many | 多对多关系 (Django) | vs "Machine-to-Machine" |

## 2. 任务类 (10 个)

| 术语 | 全称 | 含义 | 易混淆 |
|------|------|------|--------|
| **Task** | 任务 | 一次游戏自动化操作定义 | vs "Job" (执行实例) |
| **TaskExecution** | 任务执行实例 | Task 的具体一次运行 | vs "Task" (定义) |
| **Pipeline** | 管道 | 节点组成的有向图 | vs "Pipeline" (CI/CD) |
| **Node** | 节点 | Pipeline 的一个操作单元 | vs "DOM node" |
| **Step** | 步骤 | Node 的一次执行 | - |
| **Stage** | 阶段 | Pipeline 内的逻辑分组 | - |
| **Branch** | 分支 | 条件节点 (if/else) | vs "Git branch" |
| **Loop** | 循环 | 重复节点 | - |
| **SubPipeline** | 子管道 | Pipeline 内嵌的另一个 Pipeline | - |
| **Recording** | 录制 | 用户操作录制数据 | vs "Recording" (音视频) |

## 3. 设备类 (10 个)

| 术语 | 全称 | 含义 | 易混淆 |
|------|------|------|--------|
| **Device** | 设备 | 模拟器或真机实例 | vs "Agent" (控制器) |
| **Agent** | 代理 | 控制设备的 Python 进程 | vs "AI Agent" |
| **Emulator** | 模拟器 | 虚拟机 (LDPlayer/BlueStacks) | vs "真机" (real device) |
| **Window** | 窗口 | 模拟器/真机的可视化窗口 | vs "OS Window" |
| **Hwnd** | Window Handle | Windows 窗口句柄 | - |
| **Serial** | 序列号 | ADB 设备唯一标识 | vs "IMEI" |
| **WGC** | Windows Graphics Capture | Win10 1903+ 截图 API | vs "GDI" |
| **DXGI** | DirectX Graphics Infrastructure | DirectX 截图 API | - |
| **BitBlt** | Bit Block Transfer | GDI 截图 API (兜底) | - |
| **PostMessage** | 消息投递 | Windows 输入 API | vs "SendMessage" |

## 4. AI/ML 类 (8 个)

| 术语 | 全称 | 含义 | 易混淆 |
|------|------|------|--------|
| **LLM** | Large Language Model | 大语言模型 (GPT/Claude/通义) | vs "SLM" (小模型) |
| **RAG** | Retrieval-Augmented Generation | 检索增强生成 | - |
| **Embedding** | 嵌入 | 文本向量化表示 | - |
| **Prompt** | 提示词 | 给 LLM 的输入 | - |
| **Token** | 令牌 | LLM 处理的最小单元 | vs "Auth Token" |
| **Skill** | 技能 | AI 可调用的能力单元 | vs "前端组件" |
| **MCP** | Model Context Protocol | AI 工具调用协议 | - |
| **Tool Call** | 工具调用 | LLM 调用外部函数 | - |

## 5. 平台/操作系统类 (8 个)

| 术语 | 全称 | 含义 | 易混淆 |
|------|------|------|--------|
| **Win** | Windows | 微软桌面 OS | - |
| **macOS** | macOS | 苹果桌面 OS (旧称 OS X) | - |
| **Linux** | Linux | 开源 OS (Ubuntu/CentOS) | - |
| **NTFS** | NT File System | Windows 文件系统 | vs "FAT32" |
| **APFS** | Apple File System | macOS 文件系统 | - |
| **ext4** | Fourth Extended Filesystem | Linux 主流文件系统 | - |
| **X11** | X Window System | Linux 图形协议 | vs "Wayland" |
| **Cocoa** | Cocoa Framework | macOS 原生 UI 框架 | - |

## 6. GAF 专有 (5 个)

| 术语 | 含义 | 出处 |
|------|------|------|
| **FramePool** | 截图帧缓存池, 避免重复截图 | `agent/src/devices/windows/frame_pool.py` |
| **DCache** | 窗口 DeviceContext 缓存 | `agent/src/devices/windows/dccache.py` |
| **BatchOCR** | 批量 OCR 识别 (避免单次调用开销) | `agent/src/core/batch_ocr.py` |
| **PipelineEngine** | Pipeline 解释执行器 | `agent/src/engine/engine.py` |
| **ConfigMigrator** | 配置文件版本迁移器 | `agent/src/core/config_migrator.py` |

## 7. 易混淆辨析 (5 对)

### 7.1 Task vs Job vs Execution

- **Task**: 持久化定义 (DRAFT → SUCCESS/FAILED)
- **TaskExecution**: 一次执行的运行时实例 (含 retry_count, started_at, result)
- **Job** (Celery): 异步任务队列的一个工作单元

关系: `Task (1) ──── (*) TaskExecution`; `TaskExecution (1) ──── (*) Job`

### 7.2 Agent vs Device

- **Device**: 物理/虚拟硬件 (模拟器/真机)
- **Agent**: 控制设备的 Python 进程, 一个 Agent 可管理多 Device

关系: `Agent (1) ──── (*) Device`

### 7.3 Recording vs Pipeline

- **Recording**: 录制数据 (按时间序列的原始输入事件)
- **Pipeline**: 节点图 (转换为可编辑的结构)

关系: `Recording ──converter──► Pipeline` (one-way, 不可逆)

### 7.4 Hwnd vs PID

- **Hwnd (Window Handle)**: 窗口标识, 用于 PostMessage/SendMessage
- **PID (Process ID)**: 进程标识, 用于进程管理

关系: `PID (1) ──── (*) Hwnd` (一个进程可有多窗口)

### 7.5 WGC vs DXGI vs BitBlt

- **WGC**: Win10 1903+, 高性能, 截屏含 GPU 内容
- **DXGI**: Win8+, 中性能, 需 DirectX
- **BitBlt**: WinXP+, 低性能, 兼容性最好

降级链: `WGC → DXGI → BitBlt` (高性能 → 低性能)

## 8. 缩略词表 (10 个)

| 缩略词 | 全称 |
|--------|------|
| API | Application Programming Interface |
| CLI | Command Line Interface |
| SDK | Software Development Kit |
| UI | User Interface |
| UX | User Experience |
| DB | Database |
| ORM | Object-Relational Mapping |
| CI | Continuous Integration |
| CD | Continuous Deployment |
| SLA | Service Level Agreement |

## 9. 反思 (Reflection)

- **术语不统一 = 沟通成本**: AI 读错术语 = 改错代码
- **5 分类便于检索**: 架构/任务/设备/AI/平台, 按场景查
- **易混淆辨析是关键**: Task vs Job, Agent vs Device, WGC vs DXGI
- **GAF 专有名词要补**: FramePool / DCache / BatchOCR / PipelineEngine
- **维护者**: manual (AI 仅整理, 新术语需人类确认)
