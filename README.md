# GAF - General Automation Framework

通用桌面自动化框架，支持 Windows 窗口控制和 Android 模拟器控制。

## 项目结构

```
GAF/
├── backend/          # Django 后端（REST API + WebSocket, 17 个 app）
├── frontend/         # React 前端（Web, 44 页面）
├── worker/           # Worker 进程（设备控制、任务执行、录制）
├── desktop/          # Electron 桌面客户端
├── docs/             # 项目文档
│   ├── architecture/ #  架构总览/最优方案/业务×架构映射
│   ├── business/     #  业务 9 模块（任务/设备/资源/账户/运维/AI/系统等）
│   ├── standards/    #  开发规范（API 契约/前后端约定）
│   ├── specs/        #  spec 索引 + 归档（active/archived）
│   ├── archive/      #  技术债/已完成功能/健康报告/spec-context
│   ├── health/       #  月度健康检查
│   └── reference/    #  技术栈/数据流/CLI 速查
├── .ai-memory/       # AI 记忆库（lessons/ops/plan/meta/knowledge）
├── .skills/           # AI 技能+规则唯一权威源（skills/ + rules/，多 IDE 兼容）
│   ├── skills/        #  15 个 Skill（gaf-* + 通用开发技能）
│   └── rules/         #  AI 行为约束（project_rules / env-hardrules）
├── .trae/             # Trae 入口（skills+rules 为 junction → .skills/）
├── .opencode/         # opencode 入口（skills+rules 为 junction → .skills/）
├── scripts/          # 开发脚本（gaf_services.ps1 统一服务管理 / gaf_init / setup-dev-env 等）
├── deploy/           # 部署配置（nginx/systemd）
├── resources/        # 资源包示例（Arknights/BrownDust-II）
└── .env.example      # 环境配置模板
```

### 目录命名：Device / Worker / Agent

GAF 术语已归一化（OQ-10）：**执行节点/进程改称 Worker**，"Agent" 一词保留给 AI 智能体（`backend/gaf_ai`）。三者清晰：**Device**（被控 PC/模拟器）/ **Worker**（执行节点/进程）/ **Agent**（AI 智能体）。

| 目录                           | 职责                                                                              | 是否 Django app | 典型文件                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------- | ------------- | ---------------------------------------------------------------------- |
| `GAF/worker/`                | **独立的 Worker 进程**。实际执行设备控制（截图/输入）、Pipeline 任务、录制回放。通过 WebSocket 与 backend 通信。   | 否             | `worker/src/devices/`, `worker/src/engine/`                            |
| `GAF/backend/device_bridge/` | **后端设备桥接抽象层**。统一 Device/Window/Emulator 的发现、截图、输入、验证能力；"bridge" 仅为包名，不承载执行节点语义。 | 否（辅助包）        | `backend/device_bridge/platforms/`, `backend/device_bridge/discovery/` |
| `GAF/backend/workers/`       | **Django app**。管理 Worker/Device 数据模型、REST API、WebSocket consumers、迁移文件。         | 是             | `backend/workers/models.py`, `backend/workers/views.py`                |

> 历史路径说明：`workers` app 对外 REST 路由仍为 `/api/v2/agents/`、`/api/v2/devices/`，WebSocket 仍为 `ws/protocol/agents/`，Worker 进程 CLI 参数仍为 `--agent-token`（未随目录改名，保持兼容）。

## 快速开始

### 环境要求

- Windows 10/11

- PowerShell 5.1+

- 至少 20GB 可用空间（D 盘）

### 一键部署开发环境

```powershell
# 以管理员身份打开 PowerShell，进入项目目录
cd d:\code\GAF

# 运行部署脚本（自动安装 Git/Redis/Miniconda/Node.js，创建 conda gaf 环境）
powershell -ExecutionPolicy Bypass -File scripts\setup-dev-env.ps1
```

部署完成后，所有软件都落在 `D:\code\environment`，不会污染 C 盘。

### 一键启动 (唯一实例, N194)

```powershell
# 启动 Redis + Backend + Worker + Frontend (启动前自动杀已有实例, 确保唯一)
powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 start

# 停止全部 (反向: Frontend → Worker → Backend → Redis)
powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 stop

# 重启全部
powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 restart

# 查看状态
powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 status
```

Linux/macOS 可用 `bash scripts/start_gaf_unix.sh` 启动 (不保证唯一实例, 推荐用 Docker Compose 部署).

### AI 工作流入口 (gaf\_init)

AI 开始工作前必跑的硬约束入口（v9.0），用于 L1 硬加载 failure-modes.md + session active + KB 同步。

```powershell
# Windows PowerShell 7.x (推荐, 原生支持)
pwsh scripts/gaf_init.ps1 --fast   # < 1s, 仅 L1 + session
pwsh scripts/gaf_init.ps1 --full   # < 5s, 含 pre-commit / sync_ai_memory / sync_skills / L2 校验

# Linux/macOS 或 Windows git bash
bash scripts/gaf_init.sh --fast
bash scripts/gaf_init.sh --full
```

`.ps1` 版本会自动发现 conda 安装位置并加载 PowerShell hook（无需手动 `conda init powershell`）。

### 手动启动

重新打开 PowerShell 后：

```powershell
# 1. Redis
cd D:\code\environment\redis
.\redis-server.exe

# 2. 后端（新终端）
conda activate gaf
cd d:\code\GAF\backend
python manage.py migrate
python manage.py runserver

# 3. Worker（新终端）
cd d:\code\GAF\worker
conda activate gaf
# TD-338: 本地开发需先生成 worker token (GAF_ALLOW_LOCALHOST_BYPASS 默认禁用)
#   curl -X POST http://127.0.0.1:8000/api/v2/accounts/auth/login/ \
#     -H "Content-Type: application/json" \
#     -d '{"username":"admin","password":"admin123"}'  # 拿 JWT
#   curl -X POST http://127.0.0.1:8000/api/v2/agents/<id>/generate-token/ \
#     -H "Authorization: Bearer <JWT>"                  # 拿 worker token（REST 路由保持 /agents/ 历史路径）
# TD-339: worker 自带单例锁, 已有 worker 在跑会 exit(1), 调试用 --skip-singleton-check 绕过
python -m src --agent-token <AGENT_TOKEN>

# 4. 前端（新终端）
cd d:\code\GAF\frontend
npm run dev

# 5. 桌面客户端（新终端）
cd d:\code\GAF\desktop
npm run dev
```

## 技术栈

| 层      | 技术                                                                           |
| ------ | ---------------------------------------------------------------------------- |
| 后端     | Django 5.2 + DRF + Django Channels + Celery + Redis                          |
| 前端     | React 19 + TypeScript + Vite + Ant Design + Zustand                          |
| 桌面客户端  | Electron                                                                     |
| 数据库    | SQLite + WAL（零配置，单机部署 < 100 并发）                                              |
| Worker | Python 3.11 + Win32 API + OpenCV + adbutils + RapidOCR + mss/pynput/comtypes |

## License

MIT
