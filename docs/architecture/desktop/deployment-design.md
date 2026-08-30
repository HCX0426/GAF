---
summary: GAF 部署方案
applies_to: ['architecture', 'design']
key_decisions:
  - 数据备份策略
  - Desktop Electron 一体化分发
  - 运行形态 × 服务必要性矩阵 (§7, 与 overview §15 同步)
last_updated: 2026-08-30
---

# GAF 部署方案

> 版本：1.3 | 日期：2026-05-17 (初版) / 2026-08-04 (移除 PostgreSQL 依赖, dev/prod 统一 SQLite+WAL) / 2026-08-30 (术语归一: Worker / WorkerToken / WorkerConsumer + GafDaemon 权威 + 新增 §7 运行形态×服务矩阵) | SubTask 1.9

## 1. 概述

GAF 支持三种部署模式，覆盖从个人开发者到企业级团队的不同需求：

| 部署模式 | 适用场景 | 数据库 | 缓存 | 复杂度 |
|----------|---------|--------|------|--------|
| 本地单机 | 个人开发者/测试 | SQLite + WAL | 本地 Redis | 低 |
| Docker Compose | 团队开发/演示 | SQLite + WAL | Redis 容器 | 中 |
| 远程多机 | 生产环境/多设备 | SQLite + WAL | Redis 集群 | 中 |

> **术语约定（OQ-10 归一 2026-08-30）**：部署形态中的"Agent"一词已统一为 **Worker**（自动化执行节点/进程）。以下 URL 与参数名属 **legacy wire 契约，保留不改**（OQ-9/OQ-10）：`ws://…/ws/protocol/agents/`（Worker WS 路径，`GAF_WS_AGENT_PATH` 可覆盖）、`/api/v2/agents/<id>/generate-token/`（Worker 令牌端点）、`--agent-token`（wire 参数，语义为 WorkerToken）。
>
> **部署形态 ≠ 运行形态**：本节"本地单机 / Docker / 远程多机"是**部署形态**；"单机单设备 / 单机多设备 / 多机多设备"是**运行（设备）形态**，与**服务必要性**的关系见 §7（与 overview §15 同步）。

---

## 2. 本地单机部署（默认）

### 2.1 架构图

```
┌──────────────────────────────────────────────────────────┐
│                     用户电脑                               │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Client     │  │   Server     │  │    Worker    │  │
│  │   (React)    │  │   (Django)   │  │   (Python)   │  │
│  │   :5173      │  │   :8000      │  │   (本地)      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │           │
│         │ HTTP/WS         │ WebSocket        │           │
│         └────────►        │◄─────────────────┘           │
│                           │                              │
│                    ┌──────┴──────┐                       │
│                    │    Redis    │                       │
│                    │   :6379     │                       │
│                    └──────┬──────┘                       │
│                           │                              │
│                    ┌──────┴──────┐                       │
│                    │   SQLite    │                       │
│                    │  db.sqlite3 │                       │
│                    └─────────────┘                       │
└──────────────────────────────────────────────────────────┘
```

### 2.2 系统要求

| 组件 | 最低要求 | 推荐配置 |
|------|---------|---------|
| 操作系统 | Windows 10 64-bit | Windows 11 64-bit |
| Python | 3.11 | 3.11 |
| Node.js | 20 LTS | 20 LTS |
| Redis | 7.0+ | 7.2+ |
| Miniconda | 最新版 | 最新版 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 2 GB | 10 GB |

> **环境隔离**：Windows 下一键部署脚本会把 Git、Redis、Miniconda、Node.js 以及所有缓存、envs、包都放到 `D:\code\environment`，不污染 C 盘。

### 2.3 一键启动

**权威入口（D19 归一 2026-08-30）**：服务编排权威为 **GafDaemon**（`scripts/gaf_daemon.py`，Python 守护进程）；`scripts/gaf_services.ps1` 为 Windows 启停兼容层（委托 GafDaemon 逻辑）。两者均确保唯一实例，避免多 instance 导致的 WS 消息路由错乱（N194）：

| 平台 | 启动 | 停止 | 说明 |
|------|------|------|------|
| Windows | `scripts/gaf_services.ps1 start` | `scripts/gaf_services.ps1 stop` | **推荐** — 启动前自动杀已有实例，确保唯一；兼容层，底层逻辑见 GafDaemon |
| 跨平台 | `python scripts/gaf_daemon.py start` | `python scripts/gaf_daemon.py stop` | GafDaemon 权威实现（看门狗 + 重启 + 健康探针） |
| Linux / macOS | `bash scripts/start_gaf_unix.sh` | (手动 pkill) | 不保证唯一实例，推荐 Docker Compose 部署 |

启动后会拉起（取决于 `GAF_CELERY_MODE`，见下）：
- Redis (`:6379`)
- Django 后端 (`:8000`, daphne)
- Worker 进程 (conda gaf, `python -m src`；原 Agent)
- Vite 前端 (`:5173`)

**Celery 模式（`GAF_CELERY_MODE`，默认 `eager`）**：
- 默认 `eager`：异步任务同步化执行（`CELERY_TASK_ALWAYS_EAGER=True`），**不启动 celery_worker / celery_beat 进程** —— 单机/单设备/纯手动的最简形态（§7）。
- 切换 `GAF_CELERY_MODE=celery`：额外拉起 celery_worker（`--pool=threads --concurrency=4`）+ celery_beat。**无人值守 / 夜间模式 / 循环轮换 / 5 层恢复 / 定时备份 / rag-auto-index** 依赖 beat，需 celery 模式（§7）。

> `gaf_services.ps1` 替代了原来的 `start.bat` / `start.ps1` / `stop.bat` / `stop.sh`（已删除）。当前环境统一使用 conda `gaf`（原 `gaf-agent` 已归一化，N199）。

**Worker 进程单例保护** (TD-339, 2026-07-23 + N194 增强):
- `gaf_services.ps1` / GafDaemon 启动 worker 前会先杀已有实例 (按命令行匹配)，并清理 `%TEMP%\gaf_worker_lock\standalone.pid` 残留锁（原 `gaf_agent_lock`）
- worker `__main__.py` 自带 PID 文件锁，检测到已有 worker 进程存活则 exit(1)
- 手动启动场景同理：直接 `python -m src` 也会被单例锁保护
- 调试场景可用 `--skip-singleton-check` 绕过（不推荐生产使用）
- 与 backend 端 `worker_runtime.py`（TD-217, 原 `agents/agent_runtime.py`）互补：backend 自启 worker 由 backend 管理，手动启动由 worker 自身兜底

### 2.4 环境初始化

#### Windows（推荐）

以管理员身份打开 PowerShell，进入项目根目录，运行一键部署脚本：

```powershell
cd d:\code\GAF
powershell -ExecutionPolicy Bypass -File scripts\setup-dev-env.ps1
```

脚本会自动完成：
- 安装 Git、Redis、Miniconda、Node.js 到 `D:\code\environment`
- 创建 conda 环境 `gaf`（Python 3.11）
- 安装 backend / worker / frontend / desktop 所有依赖到 conda gaf 环境 (N199 环境归一化: 取消 venv gaf-agent 双环境)
- 配置所有缓存目录到 D 盘

**环境归一化说明** (N199, 2026-08-02):

2026-08-02 归一化: 所有服务统一使用 `conda gaf` 环境，取消 `venv gaf-agent` 双环境设计。

| 环境 | 路径 | 安装的依赖 | 用途 |
|------|------|----------|------|
| conda `gaf` | `D:\code\environment\conda\envs\gaf\` | `backend/requirements/base.txt` + dev.txt + `worker/requirements.txt` | backend Django 服务器 + Worker 客户端 + 脚本 |

归一化原因:
- 原双环境设计基于 opencv 差异（backend headless vs worker full GUI），实际 worker 代码未使用任何 GUI 函数（imshow/waitKey 等），`opencv-python-headless` 完全满足需求
- 双环境导致 worker 启动入口不统一（conda vs venv），多次出现多进程冲突
- 依赖维护成本高：新增依赖需同步两份 requirements 文件

旧 `venv gaf-agent` 目录已废弃，不再使用。

部署完成后，按 [2.3 一键启动](#23-一键启动) 启动即可。

#### Linux / macOS

暂未提供一键脚本，按以下步骤手动初始化：

```bash
# 1. 克隆项目
git clone https://github.com/xxx/GAF.git
cd GAF

# 2. 创建 conda 环境
conda env create -f environment.yml
conda activate gaf

# 3. 初始化后端
cd backend
pip install -r requirements/dev.txt
python manage.py migrate
python manage.py create_default_user
cd ..

# 4. 初始化前端
cd frontend
npm install
cd ..

# 5. 启动 Redis
redis-server

# 6. 一键启动
bash scripts/start_gaf_unix.sh
```

---

## 3. Docker Compose 部署

### 3.1 架构图

```
┌──────────────────────────────────────────────────────────┐
│  Docker Compose                                          │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ frontend │  │ backend  │  │  worker  │              │
│  │ :5173    │  │ :8000    │  │          │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       │             │             │                      │
│       │    ┌────────┼─────────────┘                      │
│       │    │        │                                    │
│       │  ┌─▼──┐  ┌────────┐                                │
│       │  │Redis│  │ SQLite │                                │
│       │  │:6379│  │ +WAL   │                                │
│       │  └────┘  └────────┘                                │
│       │                                                 │
│  ┌────▼────┐                                            │
│  │  Nginx  │                                            │
│  │  :80    │                                            │
│  └─────────┘                                            │
└──────────────────────────────────────────────────────────┘
```

### 3.2 docker-compose.yml

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
    depends_on:
      - backend
      - frontend
    restart: always

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    expose:
      - "5173"
    environment:
      - VITE_API_BASE_URL=/api
    restart: always

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    expose:
      - "8000"
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.prod
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      - redis
    restart: always

  # 仅 GAF_CELERY_MODE=celery 时需要以下两项；默认 eager 可直接省略（§7）
  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A config worker --loglevel=info --concurrency=2
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.prod
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    restart: always

  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A config beat --loglevel=info
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.prod
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    restart: always

  worker:                     # 原 "agent"，OQ-10 归一
    build:
      context: ./worker
      dockerfile: Dockerfile
    environment:
      - GAF_SERVER_URL=ws://backend:8000/ws/protocol/agents/   # URL 契约保留 (GAF_WS_AGENT_PATH 可覆盖)
      - GAF_AGENT_TOKEN=${GAF_AGENT_TOKEN}                     # wire 契约保留 (语义 WorkerToken, OQ-10)
    depends_on:
      - backend
    restart: always

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    restart: always

volumes:
  redis_data:
```

### 3.3 注意事项

- Docker Compose 部署延后到正式发布阶段
- Worker 容器需要访问宿主机设备（模拟器/窗口），需要特殊配置
- Windows 下 Docker 对 Win32 API 的支持有限，**Worker 层建议直接运行在宿主机**（Worker 是 Win32/ADB 执行载体，不适合容器化执行；Docker 版主要承载 Server 端）

---

## 4. 远程多机部署

### 4.1 架构图

```
┌──────────────┐     ┌──────────────────────────┐     ┌──────────────┐
│  用户电脑     │     │       服务器              │     │  目标机器 A  │
│              │     │                          │     │              │
│  ┌────────┐  │     │  ┌────────────────────┐  │     │  ┌────────┐  │
│  │ Client │◄─┼─────┼─►│   Nginx :80/443   │  │     │  │ Worker │  │
│  │(React) │  │     │  └────────┬───────────┘  │     │  │        │  │
│  └────────┘  │     │           │              │     │  └───┬────┘  │
│              │     │  ┌────────▼───────────┐  │     │      │       │
└──────────────┘     │  │   Django :8000     │◄─┼─────┼──────┘       │
                     │  │   (Daphne)         │  │     │              │
                     │  └────────┬───────────┘  │     └──────────────┘
                     │           │              │
                     │  ┌────────▼───────────┐  │     ┌──────────────┐
                     │  │ Celery Workers     │  │     │  目标机器 B  │
                     │  └────────┬───────────┘  │     │              │
                     │           │              │     │  ┌────────┐  │
                     │  ┌────────▼───────────┐  │     │  │ Worker │  │
                     │  │ SQLite + WAL       │  │     │  │        │  │
                     │  └────────────────────┘  │     │  └───┬────┘  │
                     │  ┌────────────────────┐  │     │      │       │
                     │  │ Redis :6379        │◄─┼─────┼──────┘       │
                     │  └────────────────────┘  │     └──────────────┘
                     └──────────────────────────┘
```

> **多机设备形态**：每台目标机器运行 **1 个 Worker 进程**（单例锁 §2.3），Worker 自动发现并注册本机所有设备（§7.1）；中央 Server 只承载认证/调度/执行记录/AI。远程多设备的并发是本机 Worker 内多 Device 并行，不是多进程。

### 4.2 Server 端配置

> **默认 (2026-08-03 spec)**: dev/prod 统一 SQLite + WAL（单机部署 < 100 并发）；`config/settings/base.py` 已配置 SQLite + WAL + busy_timeout + `synchronous=NORMAL`。如下 `USER/PASSWORD/HOST/PORT` 字段仅当 `DB_ENGINE` 切换为 PG/MySQL 时生效（建议不切换）。

```python
# config/settings/base.py — 默认 SQLite + WAL
DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.getenv("DB_NAME", BASE_DIR / "db.sqlite3"),
        "OPTIONS": {  # WAL + busy_timeout + synchronous=NORMAL
            # ...
        },
    }
}

# 仅当 DB_ENGINE 非空时启用 PG/MySQL 字段（USER/PASSWORD/HOST/PORT/CONN_MAX_AGE），prod.py 不再默认 PG

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(os.environ.get("REDIS_HOST", "localhost"), 6379)],
            "CAPACITY": 1500,
            "GROUP_EXPIRY": 86400,
        },
    }
}

CELERY_BROKER_URL = f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:6379/1"
```

### 4.3 Worker 远程连接

```bash
# Worker 连接远程 Server
cd d:\code\GAF\worker
python -m src \
    --server-url wss://gaf.example.com/ws/protocol/agents/ \
    --agent-token YOUR_WORKER_TOKEN \
    --hostname "Game-PC-01"
```

> `--server-url` / `--agent-token` 为 **wire 契约参数名，保留不改**（OQ-10：语义均为 Worker 侧；WS 路径 `ws/protocol/agents/` 由 `GAF_WS_AGENT_PATH` 可覆盖）。

**本地开发场景获取 Worker token** (TD-338, 2026-07-23):

`backend/protocol/middleware.py` 的 `GAF_ALLOW_LOCALHOST_BYPASS` **默认禁用**（`settings/base.py` 默认 `"0"`，TD-037 安全硬化）。本地开发手动启动 worker 需 3 步:

```bash
# 1. 登录 backend 拿 JWT (默认账号 admin/admin123, 首次登录后可改)
curl -X POST http://127.0.0.1:8000/api/v2/accounts/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
# 返回: {"access":"<JWT>", "refresh":"..."}

# 2. 调 generate-token 拿 Worker token (URL 契约保留: /agents/{id}/generate-token/, 语义 WorkerToken)
curl -X POST http://127.0.0.1:8000/api/v2/agents/<worker_id>/generate-token/ \
  -H "Authorization: Bearer <JWT>"
# 返回: {"token":"<WORKER_TOKEN>", "preview":"..."}

# 3. 用 token 启动 worker
cd d:\code\GAF\worker
D:\code\environment\conda\envs\gaf\python.exe -m src \
    --agent-token <WORKER_TOKEN>
```

**一键开发模式（GafDaemon）**：`gaf_daemon.py` 启动的 backend 会显式设置 `GAF_ALLOW_LOCALHOST_BYPASS=1`（仅限本地一键启动），此时 127.0.0.1 来源 + `is_local=True` 的 worker 可免 token 连接（等价于 TD-037 硬化前的旧行为，仅限开发机）。

### 4.4 安全配置

| 配置项 | 说明 |
|--------|------|
| HTTPS | Nginx 配置 SSL 证书 |
| WSS | WebSocket Secure |
| 防火墙 | 仅开放 80/443 端口 |
| Worker Token | 每个 Worker 独立 Token，可吊销（`/api/v2/agents/<id>/generate-token/`，语义 WorkerToken） |
| IP 白名单 | 限制 Worker 连接 IP 范围 |
| 数据库 | 禁止远程访问，仅 Server 内网可达 |

---

## 5. Nginx 反向代理配置

### 5.1 配置文件

```nginx
upstream backend_http {
    server backend:8000;
}

upstream frontend_dev {
    server frontend:5173;
}

server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # 前端
    location / {
        proxy_pass http://frontend_dev;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # REST API
    location /api/ {
        proxy_pass http://backend_http;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # WebSocket (Client)
    location /ws/client/ {
        proxy_pass http://backend_http;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # WebSocket (Worker) — 原 "Agent" 长连接, URL 契约保留
    location /ws/agent/ {
        proxy_pass http://backend_http;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # 静态文件
    location /static/ {
        alias /app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 媒体文件
    location /media/ {
        alias /app/media/;
        expires 7d;
    }

    # 上传限制
    client_max_body_size 100m;
}
```

### 5.2 WebSocket 超时配置

| 路径 | 超时时间 | 说明 |
|------|---------|------|
| `/ws/dashboard/` | 86400s (24h) | 前端 Dashboard 长连接 (FrontendConsumer) |
| `/ws/logs/` | 86400s (24h) | 日志流 (LogStreamConsumer) |
| `/ws/notifications/` | 86400s (24h) | 通知推送 |
| `/ws/protocol/agents/` | 86400s (24h) | Worker 长连接 (WorkerConsumer, URL 契约保留, GAF_WS_AGENT_PATH 可覆盖) |
| `/ws/devices/{id}/adb-logs/` | 86400s (24h) | ADB 日志流 |
| `/api/` | 120s | REST API 请求 |

---

## 6. 数据备份策略

### 6.1 备份对象

| 备份对象 | 备份方式 | 频率 | 保留策略 |
|----------|---------|------|---------|
| SQLite 数据库 | 文件复制 (WAL checkpoint 后) | 每日 | 保留 7 天 |
| Redis 数据 | RDB + AOF | 实时 + 每小时 | 保留 3 天 |
| 资源包文件 | 目录压缩 | 每周 | 保留 4 周 |
| 日志文件 | 归档压缩 | 每日 | 保留 90 天 |
| 配置文件 | Git 版本控制 | 实时 | 永久 |

### 6.2 SQLite 备份脚本 (Python)

```python
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

def backup_sqlite(db_path: str, backup_dir: str) -> str:
    """备份 SQLite 数据库"""
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"gaf_backup_{timestamp}.sqlite3"

    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(str(backup_path))
    source.backup(dest)
    dest.close()
    source.close()

    return str(backup_path)

def cleanup_old_backups(backup_dir: str, keep_days: int = 7) -> int:
    """清理过期备份"""
    backup_dir = Path(backup_dir)
    cutoff = datetime.now().timestamp() - keep_days * 86400
    removed = 0
    for f in backup_dir.glob("gaf_backup_*.sqlite3"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    return removed
```

### 6.3 SQLite 备份脚本 (Bash)

```bash
#!/bin/bash
# sqlite_backup.sh

BACKUP_DIR="/var/backups/gaf"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/gaf_backup_$TIMESTAMP.db"

mkdir -p $BACKUP_DIR

# 先执行 WAL checkpoint，确保数据一致性
sqlite3 /path/to/db.sqlite3 "PRAGMA wal_checkpoint(TRUNCATE);"
# 复制数据库文件
cp /path/to/db.sqlite3 $BACKUP_FILE

# 保留 7 天
find $BACKUP_DIR -name "gaf_backup_*.db" -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE"
```

### 6.4 自动备份配置

```python
# Celery Beat 定时任务 (需 GAF_CELERY_MODE=celery, §7)
CELERY_BEAT_SCHEDULE = {
    "daily-database-backup": {
        "task": "tasks.tasks.database_backup",
        "schedule": crontab(hour=3, minute=0),  # 每天凌晨 3 点
    },
    "weekly-resource-backup": {
        "task": "tasks.tasks.resource_backup",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),  # 每周日凌晨 4 点
    },
}
```

### 6.5 灾难恢复流程

```
1. 停止所有服务 (Server + Worker + Celery)
2. 恢复数据库备份
   - SQLite: 直接复制 .db 文件恢复（需同时复制 WAL + SHM 文件）
3. 恢复资源包文件
4. 恢复 Redis 数据（如需要）
5. 启动服务
6. 验证数据完整性
```

---

## 7. 运行形态 × 服务必要性矩阵（与 overview §15 同步）

> **核心结论**：**"单设备模式"并不减少服务数量** —— 服务骨架（redis/backend/worker/frontend）在所有形态下都必需；可缩减的是调度（celery）、AI/LLM、打包（Electron）、守护进程（GafDaemon）类服务。代码事实：`scripts/gaf_daemon.py build_services()`（基础 4 服务 + `GAF_CELERY_MODE` 默认 `eager` 可插 2 服务）。

### 7.1 设备形态（设备 ≠ 进程）

| 形态 | 进程拓扑 | 适用 |
|------|---------|------|
| **单机单设备** | 1 台机器 + 1 Worker 进程 + 1 Device | 个人使用/单窗口 |
| **单机多设备（多开）** | 1 台机器 + **1 个 Worker 进程** 内多 Device 并发 | 多开模拟器各跑不同账户（不增加进程数，靠线程池并行） |
| **多机多设备** | 每机 1 Worker 进程 + 中央 Server | 分布式/机房（远程部署形态，Redis 集群） |

> 单机无论设备多少都只跑 **1 个 Worker 进程**（"一台机器一个 Worker" + PID 单例锁 §2.3）。

### 7.2 服务清单与必要性

| 服务 | 进程 | 单机单设备/纯手动 | 单机多设备 | 无人值守/循环 | 远程多机 | 可缩减性 |
|------|------|:-----------------:|:-----------:|:-------------:|:--------:|----------|
| **redis** | redis-server :6379 | ✅ 必需 | ✅ 必需 | ✅ 必需 | ✅ 必需（集群） | 不可省（Channels WS layer + Celery broker + 缓存） |
| **backend** | daphne :8000 | ✅ 必需 | ✅ 必需 | ✅ 必需 | ✅ 必需 | 不可省 |
| **worker** | `python -m src` | ✅ 必需（派发后执行） | ✅ 必需（1 进程多设备） | ✅ 必需 | ✅ 每机 1 个 | 不可省（执行载体） |
| **frontend** | vite dev :5173 | ✅ 必需（UI） | ✅ 必需 | ✅ 必需 | ✅ 必需 | 生产可 `build` 静态托管（省 dev server） |
| **celery_worker** | `celery -A config worker` | —（默认不启） | — | ✅ 推荐 | ✅ 必需 | ✅ **默认已缩减**（`GAF_CELERY_MODE=eager` 异步同步化） |
| **celery_beat** | `celery -A config beat` | — | — | ✅ 无人值守/夜间/循环轮换/5 层恢复必需 | ✅ 必需 | ✅ 纯手动/无定时调度可关 |
| **AI/LLM + RAG** | gaf_ai app（进程内）+ rag-auto-index beat | ⚪ 可选 | ⚪ 可选 | ⚪ 可选 | ⚪ 可选 | ✅ FeatureFlag 关 / 不配 LLM key / 停 rag 周期 = 省 |
| **GafDaemon** | `scripts/gaf_daemon.py` | ⚪ 可选（推荐） | ⚪ 可选（推荐） | ✅ 推荐 | ✅ 必需（多机编排） | ✅ 手动起服务可省 |
| **Desktop Electron** | desktop/ | ⚪ 可选 | ⚪ 可选 | ⚪ 可选 | ⚪ 可选 | ✅ 浏览器访问即可，不打包 |

### 7.3 缩减建议

1. **单机单设备 + 纯手动线性任务**：只保留 **redis + backend + worker + frontend** 4 个进程；`GAF_CELERY_MODE` 保持默认 `eager`（不启 celery_worker/beat）；不配 LLM key + 关 AI FeatureFlag；GafDaemon 可手动启动（或 `gaf_services.ps1 start` 兼容层）。
2. **无人值守/循环/夜间**：增量启动 `celery_worker` + `celery_beat`（由 `GAF_CELERY_MODE=celery` 控制；beat 承载无人值守 tick / recovery_engine / 循环轮换 / 定时备份 / rag-auto-index）。
3. **多机多设备**：中央 Server（redis+backend+celery+frontend）+ 每机 worker；Redis 用集群；GafDaemon 负责各机服务编排。
4. **可放心裁掉的**：celery 双进程（eager 默认已省）、AI/LLM+RAG（关 FeatureFlag）、vite dev server（生产 build）、Electron 壳（不打包）、GafDaemon（手动起服务）。
5. **不可裁的骨架**：redis（WS layer + broker）、backend、worker、frontend —— 这 4 个是所有形态的基础，与单/多设备无关。

---