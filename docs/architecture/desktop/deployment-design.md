---
summary: GAF 部署方案
applies_to: ['architecture', 'design']
key_decisions:
  - 数据备份策略
  - Desktop Electron 一体化分发
last_updated: 2026-08-08
---

# GAF 部署方案

> 版本：1.2 | 日期：2026-05-17 (初版) / 2026-08-04 (移除 PostgreSQL 依赖, dev/prod 统一 SQLite+WAL) | SubTask 1.9

## 1. 概述

GAF 支持三种部署模式，覆盖从个人开发者到企业级团队的不同需求：

| 部署模式 | 适用场景 | 数据库 | 缓存 | 复杂度 |
|----------|---------|--------|------|--------|
| 本地单机 | 个人开发者/测试 | SQLite + WAL | 本地 Redis | 低 |
| Docker Compose | 团队开发/演示 | SQLite + WAL | Redis 容器 | 中 |
| 远程多机 | 生产环境/多设备 | SQLite + WAL | Redis 集群 | 中 |

---

## 2. 本地单机部署（默认）

### 2.1 架构图

```
┌──────────────────────────────────────────────────────────┐
│                     用户电脑                               │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Client     │  │   Server     │  │    Agent     │  │
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

### 2.3 一键启动脚本

`scripts/` 下提供统一的 GAF 服务管理脚本 (N194, 2026-07-28)，确保唯一实例避免多 instance 导致的 WS 消息路由错乱：

| 平台 | 启动 | 停止 | 说明 |
|------|------|------|------|
| Windows | `scripts/gaf_services.ps1 start` | `scripts/gaf_services.ps1 stop` | **推荐** — 启动前自动杀已有实例, 确保唯一 |
| Linux / macOS | `bash scripts/start_gaf_unix.sh` | (手动 pkill) | 不保证唯一实例, 推荐 Docker Compose 部署 |

启动后会拉起：
- Redis (`:6379`)
- Django 后端 (`:8000`)
- Agent 进程 (conda gaf)
- Vite 前端 (`:5173`)

> `gaf_services.ps1` 替代了原来的 `start.bat` / `start.ps1` / `stop.bat` / `stop.sh` (已删除)。该脚本会根据当前环境自动使用 conda 环境 `gaf`（原 `gaf-agent` 已归一化）。

**Agent 进程单例保护** (TD-339, 2026-07-23 + N194 增强):
- `gaf_services.ps1` 启动 agent 前会先杀已有实例 (按命令行匹配), 并清理 `%TEMP%\gaf_agent_lock\standalone.pid` 残留锁
- agent `__main__.py` 自带 PID 文件锁, 检测到已有 agent 进程存活则 exit(1)
- 手动启动场景同理: 直接 `python -m src` 也会被单例锁保护
- 调试场景可用 `--skip-singleton-check` 绕过 (不推荐生产使用)
- 与 backend 端 `agent_runtime.py` (TD-217) 互补: backend 自启 agent 由 backend 管理, 手动启动由 agent 自身兜底

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
- 安装 backend / agent / frontend / desktop 所有依赖到 conda gaf 环境 (N199 环境归一化: 取消 venv gaf-agent 双环境)
- 配置所有缓存目录到 D 盘

**环境归一化说明** (N199, 2026-08-02):

2026-08-02 归一化: 所有服务统一使用 `conda gaf` 环境，取消 `venv gaf-agent` 双环境设计。

| 环境 | 路径 | 安装的依赖 | 用途 |
|------|------|----------|------|
| conda `gaf` | `D:\code\environment\conda\envs\gaf\` | `backend/requirements/base.txt` + dev.txt + `agent/requirements.txt` | backend Django 服务器 + agent 客户端 + 脚本 |

归一化原因:
- 原双环境设计基于 opencv 差异（backend headless vs agent full GUI），实际 agent 代码未使用任何 GUI 函数（imshow/waitKey 等），`opencv-python-headless` 完全满足需求
- 双环境导致 agent 启动入口不统一（conda vs venv），多次出现多进程冲突
- 依赖维护成本高：新增依赖需同步两份 requirements 文件

旧 `venv gaf-agent` 目录已废弃，不再使用。

部署完成后，按 [2.3 一键启动脚本](#23-一键启动脚本) 启动即可。

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
│  │ frontend │  │ backend  │  │  agent   │              │
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
version: "3.8"

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

  agent:
    build:
      context: ./agent
      dockerfile: Dockerfile
    environment:
      - GAF_SERVER_URL=ws://backend:8000/ws/protocol/agents/
      - GAF_AGENT_TOKEN=${AGENT_TOKEN}
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
- Agent 容器需要访问宿主机设备（模拟器/窗口），需要特殊配置
- Windows 下 Docker 对 Win32 API 的支持有限，Agent 层建议直接运行在宿主机

---

## 4. 远程多机部署

### 4.1 架构图

```
┌──────────────┐     ┌──────────────────────────┐     ┌──────────────┐
│  用户电脑     │     │       服务器              │     │  目标机器 A  │
│              │     │                          │     │              │
│  ┌────────┐  │     │  ┌────────────────────┐  │     │  ┌────────┐  │
│  │ Client │◄─┼─────┼─►│   Nginx :80/443   │  │     │  │ Agent  │  │
│  │(React) │  │     │  └────────┬───────────┘  │     │  │        │  │
│  └────────┘  │     │           │              │     │  └───┬────┘  │
│              │     │  ┌────────▼───────────┐  │     │      │       │
└──────────────┘     │  │   Django :8000     │◄─┼─────┼──────┘       │
                     │  │   (Daphne)         │  │     │              │
                     │  └────────┬───────────┘  │     └──────────────┘
                     │           │              │
                     │  ┌────────▼───────────┐  │     ┌──────────────┐
                     │  │ Celery Workers     │  │     │  目标机器 B  │
                     │  └────────┬───────────┘  │     │  ┌────────┐  │
                     │           │              │     │  │ Agent  │  │
                     │  ┌────────▼───────────┐  │     │  │        │  │
                     │  │ SQLite + WAL  │  │     │  └───┬────┘  │
                     │  └────────────────────┘  │     │      │       │
                     │  ┌────────────────────┐  │     │      │       │
                     │  │ Redis :6379        │◄─┼─────┼──────┘       │
                     │  └────────────────────┘  │     └──────────────┘
                     └──────────────────────────┘
```

### 4.2 Server 端配置

```python
# config/settings/prod.py
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",  # 或通过 DB_ENGINE 环境变量切换
        "NAME": os.environ.get("DB_NAME", "gaf"),
        "USER": os.environ.get("DB_USER", "gaf"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}

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

### 4.3 Agent 远程连接

```bash
# Agent 连接远程 Server
python -m src \
    --server-url wss://gaf.example.com/ws/protocol/agents/ \
    --agent-token YOUR_AGENT_TOKEN \
    --hostname "Game-PC-01"
```

**本地开发场景获取 agent token** (TD-338, 2026-07-23):

`backend/protocol/middleware.py` 的 `GAF_ALLOW_LOCALHOST_BYPASS` 默认禁用（TD-037 安全硬化），本地开发手动启动 agent 需 3 步:

```bash
# 1. 登录 backend 拿 JWT (默认账号 admin/admin123, 首次登录后可改)
curl -X POST http://127.0.0.1:8000/api/v2/accounts/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
# 返回: {"access":"<JWT>", "refresh":"..."}

# 2. 调 generate-token 拿 agent token
curl -X POST http://127.0.0.1:8000/api/v2/agents/<agent_id>/generate-token/ \
  -H "Authorization: Bearer <JWT>"
# 返回: {"token":"<AGENT_TOKEN>", "preview":"..."}

# 3. 用 token 启动 agent
cd d:\code\GAF\agent
D:\code\environment\conda\envs\gaf\python.exe -m src \
    --agent-token <AGENT_TOKEN>
```

替代方案（不推荐生产使用）: 设置环境变量 `GAF_ALLOW_LOCALHOST_BYPASS=1` 可让 127.0.0.1 来源 + `is_local=True` 的 agent 免 token 连接（TD-037 安全硬化前的旧行为）。

### 4.4 安全配置

| 配置项 | 说明 |
|--------|------|
| HTTPS | Nginx 配置 SSL 证书 |
| WSS | WebSocket Secure |
| 防火墙 | 仅开放 80/443 端口 |
| Agent Token | 每个 Agent 独立 Token，可吊销 |
| IP 白名单 | 限制 Agent 连接 IP 范围 |
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

    # WebSocket (Agent)
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
| `/ws/protocol/agents/` | 86400s (24h) | Agent 长连接 (AgentConsumer) |
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

### 6.2 SQLite 备份脚本

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

### 6.3 SQLite 备份脚本

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
# Celery Beat 定时任务
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
1. 停止所有服务 (Server + Agent + Celery)
2. 恢复数据库备份
   - SQLite: 直接复制 .db 文件恢复（需同时复制 WAL + SHM 文件）
3. 恢复资源包文件
4. 恢复 Redis 数据（如需要）
5. 启动服务
6. 验证数据完整性
```
