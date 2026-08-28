# GAF Linux 生产部署指南

> P-038 Linux 服务器部署 — 支持 Docker Compose 和裸机 (systemd + nginx) 两种方案

## 目录结构

```
deploy/
├── README.md                    # 本文档
├── deploy.sh                    # 裸机部署脚本 (install/update/restart/status/logs)
├── env.prod.example             # 生产环境变量模板
├── nginx/
│   └── gaf.conf                 # nginx 反向代理配置 (裸机)
└── systemd/
    ├── gaf-backend.service      # gunicorn WSGI 服务
    ├── gaf-celery-worker.service # Celery worker (异步任务)
    └── gaf-celery-beat.service   # Celery beat (定时任务)
```

## 方案一：Docker Compose 部署 (推荐快速启动)

### 前置条件
- Docker 24+
- Docker Compose v2+

### 步骤

1. **复制环境变量模板并修改**：
   ```bash
   cp .env.example .env
   # 编辑 .env，至少修改 SECRET_KEY / DB_PASSWORD
   ```

2. **启动全部服务**：
   ```bash
   docker compose up -d
   ```

3. **创建超级用户**：
   ```bash
   docker compose exec backend python manage.py createsuperuser
   ```

4. **访问**：`http://localhost` (前端 nginx 反代到后端)

### 服务清单

| 服务 | 端口 | 说明 |
|------|------|------|
| frontend | 80 | nginx 提供 SPA + 反代 /api /ws /admin /static /media |
| backend | 8000 | gunicorn WSGI (内部) |
| celery-worker | - | 异步任务执行 |
| celery-beat | - | 定时任务调度 |
| db | - | SQLite + WAL (无需独立数据库服务) |
| redis | 6379 | 缓存 + 消息队列 |

### 常用命令

```bash
docker compose logs -f backend         # 查看后端日志
docker compose restart backend         # 重启后端
docker compose exec backend python manage.py migrate  # 手动迁移
docker compose down                    # 停止全部
docker compose up -d --build           # 重新构建并启动
```

## 方案二：裸机部署 (systemd + nginx)

### 前置条件

- Ubuntu 22.04+ / Debian 12+ / RHEL 9+
- SQLite 3.8+ (WAL 模式支持)
- Redis 7+ (运行中)
- Python 3.11+
- Node.js 20+

### 一键部署

```bash
# 1. 克隆代码到 /opt/gaf
sudo mkdir -p /opt/gaf
sudo chown $USER:$USER /opt/gaf
git clone <repo-url> /opt/gaf

# 2. 复制环境变量模板
sudo cp /opt/gaf/deploy/env.prod.example /opt/gaf/backend/.env.prod
sudo nano /opt/gaf/backend/.env.prod  # 编辑配置

# 3. 一键安装
sudo bash /opt/gaf/deploy/deploy.sh install
```

### 手动分步部署

#### 1. 创建服务用户

```bash
sudo useradd --system --create-home --home-dir /opt/gaf --shell /usr/sbin/nologin gaf
```

#### 2. 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv nodejs npm nginx redis-tools build-essential
```

#### 3. 创建 Python venv 并安装依赖

```bash
sudo -u gaf python3.11 -m venv /opt/gaf/venv
sudo -u gaf /opt/gaf/venv/bin/pip install --upgrade pip wheel setuptools
sudo -u gaf /opt/gaf/venv/bin/pip install -r /opt/gaf/backend/requirements/prod.txt
```

#### 4. 构建前端

```bash
cd /opt/gaf/frontend
sudo -u gaf npm ci
sudo -u gaf npx vite build
```

#### 5. 数据库迁移 + 静态文件收集

```bash
sudo -u gaf /opt/gaf/venv/bin/python /opt/gaf/backend/manage.py migrate
sudo -u gaf /opt/gaf/venv/bin/python /opt/gaf/backend/manage.py collectstatic --noinput --clear
```

#### 6. 安装 nginx 配置

```bash
sudo cp /opt/gaf/deploy/nginx/gaf.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/gaf.conf /etc/nginx/sites-enabled/gaf.conf
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

#### 7. 安装 systemd 服务

```bash
sudo cp /opt/gaf/deploy/systemd/gaf-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gaf-backend gaf-celery-worker gaf-celery-beat
```

### 部署后操作

```bash
# 创建超级用户
sudo -u gaf /opt/gaf/venv/bin/python /opt/gaf/backend/manage.py createsuperuser

# 查看服务状态
sudo bash /opt/gaf/deploy/deploy.sh status

# 查看日志
sudo bash /opt/gaf/deploy/deploy.sh logs
# 或单独查看
sudo journalctl -u gaf-backend -f
```

### 更新部署

```bash
cd /opt/gaf
git pull
sudo bash /opt/gaf/deploy/deploy.sh update
```

## 配置说明

### 生产环境变量 (.env.prod)

| 变量 | 必填 | 说明 |
|------|------|------|
| `SECRET_KEY` | ✅ | Django 密钥，使用 50+ 字符随机串 |
| `ALLOWED_HOSTS` | ✅ | 允许的域名/IP，逗号分隔 |
| `DB_ENGINE` | ✅ | 生产建议 `django.db.backends.sqlite3` (默认 WAL) |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | ✅ | 数据库凭据 |
| `DB_HOST` / `DB_PORT` | ✅ | 数据库地址 |
| `REDIS_URL` | ✅ | Redis 连接 (缓存 + channels) |
| `CELERY_BROKER_URL` | ✅ | Celery broker (通常 redis) |
| `CORS_ALLOWED_ORIGINS` | ✅ | 前端域名 (逗号分隔) |
| `SECURE_SSL_REDIRECT` | HTTPS 时设 `true` | 强制 HTTPS 重定向 |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | HTTPS 时设 `true` | Cookie 仅 HTTPS 传输 |

### nginx 配置要点

- `/api/` → 反代到 gunicorn (120s 超时)
- `/ws/` → WebSocket 反代 (24h 长连接)
- `/static/` → 后端 collectstatic 输出 (30天缓存)
- `/media/` → 用户上传文件 (7天缓存)
- `/` → 前端 SPA (try_files fallback to index.html)

### gunicorn 配置

- 默认 workers = CPU * 2 + 1
- 默认 threads = 2
- 默认 timeout = 120s
- max_requests = 1000 (防内存泄漏自动重启)
- preload_app = true (降低内存占用)
- 通过环境变量 `GUNICORN_*` 覆盖

## 健康检查

部署后验证：

```bash
# 1. 后端 API 健康
curl http://localhost/api/v2/accounts/auth/login/ -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 2. 静态资源可访问
curl -I http://localhost/static/admin/css/base.css

# 3. WebSocket 端点存在 (应返回 404 而非 502)
curl -I http://localhost/ws/

# 4. 服务状态
sudo systemctl is-active gaf-backend gaf-celery-worker gaf-celery-beat nginx
```

## 故障排查

| 症状 | 排查 |
|------|------|
| 502 Bad Gateway | gunicorn 未启动 → `systemctl status gaf-backend` |
| 静态资源 404 | collectstatic 未执行 → `deploy.sh update` |
| WebSocket 连不上 | nginx `/ws/` 配置缺失或 `Upgrade` 头未透传 |
| Celery 任务不执行 | `systemctl status gaf-celery-worker` + Redis 连通性 |
| 数据库连接失败 | `.env.prod` 中 DB_* 配置 + SQLite 文件权限 |
| 权限错误 | `chown -R gaf:gaf /opt/gaf` |

## 安全建议

1. **修改默认密码**：admin/admin123 仅用于初始登录，立即修改
2. **配置 HTTPS**：使用 Let's Encrypt + certbot 申请免费证书
3. **防火墙**：仅开放 80/443，Redis 不对外暴露
4. **定期备份**：SQLite 文件复制 (WAL checkpoint 后) + 媒体目录备份
5. **日志轮转**：systemd journal 自动轮转，nginx access log 配置 logrotate
