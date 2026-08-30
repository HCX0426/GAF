# GAF - General Automation Framework

通用桌面自动化框架，支持 Windows 窗口控制和 Android 模拟器控制。

## 项目结构

```
GAF/
├── backend/          # Django 后端（REST API + WebSocket, 22 个 app）
├── frontend/         # React 前端（Web, 42 页面）
├── agent/            # Agent 客户端（设备控制、任务执行、录制）
├── desktop/          # Electron 桌面客户端
├── docs/             # 项目文档
│   ├── general/      #  通用文档（pre-commit 规范）
│   └── standards/    #  开发规范（API 契约/前后端约定）
├── .ai-memory/       # AI 记忆库（lessons/ops/plan/meta/knowledge）
├── .skills/           # AI 技能+规则唯一权威源（skills/ + rules/，多 IDE 兼容）
│   ├── skills/        #  25+ 个 Skill（gaf-* + superpowers）
│   └── rules/         #  AI 行为约束（project_rules / env-hardrules）
├── .trae/             # Trae 入口（skills+rules 为 junction → .skills/）
├── .opencode/         # opencode 入口（skills+rules 为 junction → .skills/）
├── scripts/          # 开发脚本（gaf_services.ps1 统一服务管理 / gaf_init / setup-dev-env 等）
├── deploy/           # 部署配置（nginx/systemd）
├── resources/        # 资源包示例（Arknights/BrownDust-II）
└── .env.example      # 环境配置模板
```

### 为什么会有三个 agent 目录？

| 目录 | 复数/单数 | 职责 | 是否 Django app | 典型文件 |
|------|----------|------|----------------|----------|
| `GAF/agent/` | 单数 | **独立的 Agent 进程**。实际执行设备控制（截图/输入）、Pipeline 任务、录制回放。通过 WebSocket 与 backend 通信。 | 否 | `worker/src/devices/`, `worker/src/engine/` |
| `GAF/backend/device_bridge/` | 单数 | **后端内部的 agent 辅助模块**。负责设备发现、模拟器生命周期、MAA 转换、平台注册等后台逻辑。 | 否（辅助包） | `backend/device_bridge/discovery/`, `backend/device_bridge/handlers/` |
| `GAF/backend/agents/` | 复数 | **Django app**。管理 Agent/Device 数据模型、REST API、WebSocket consumers、迁移文件。 | 是 | `backend/agents/models.py`, `backend/agents/views.py` |

命名约定：
- `agent/`（单数）= 可独立运行的 Agent 客户端进程。
- `agents/`（复数）= Django app 名称，遵循 Django "复数形式 app 名" 的惯例，表示管理多个 Agent/设备记录。
- `backend/device_bridge/`（单数）= 后端内部辅助包，复数已被 Django app 占用，故用单数避免冲突。

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
# 启动 Redis + Backend + Agent + Frontend (启动前自动杀已有实例, 确保唯一)
powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 start

# 停止全部 (反向: Frontend → Agent → Backend → Redis)
powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 stop

# 重启全部
powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 restart

# 查看状态
powershell -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 status
```

Linux/macOS 可用 `bash scripts/start_gaf_unix.sh` 启动 (不保证唯一实例, 推荐用 Docker Compose 部署).

### AI 工作流入口 (gaf_init)

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

# 3. Agent（新终端）
cd d:\code\GAF\agent
conda activate gaf
# TD-338: 本地开发需先生成 agent token (GAF_ALLOW_LOCALHOST_BYPASS 默认禁用)
#   curl -X POST http://127.0.0.1:8000/api/v2/accounts/auth/login/ \
#     -H "Content-Type: application/json" \
#     -d '{"username":"admin","password":"admin123"}'  # 拿 JWT
#   curl -X POST http://127.0.0.1:8000/api/v2/agents/<id>/generate-token/ \
#     -H "Authorization: Bearer <JWT>"                  # 拿 agent token
# TD-339: agent 自带单例锁, 已有 agent 在跑会 exit(1), 调试用 --skip-singleton-check 绕过
python -m src --agent-token <AGENT_TOKEN>

# 4. 前端（新终端）
cd d:\code\GAF\frontend
npm run dev

# 5. 桌面客户端（新终端）
cd d:\code\GAF\desktop
npm run dev
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Django 5.2 + DRF + Django Channels + Celery + Redis |
| 前端 | React 19 + TypeScript + Vite + Ant Design + Zustand |
| 桌面客户端 | Electron |
| 数据库 | SQLite + WAL（零配置，单机部署 < 100 并发） |
| Agent | Python 3.11 + Win32 API + OpenCV + adbutils + RapidOCR (TD-337) |

## License

MIT
