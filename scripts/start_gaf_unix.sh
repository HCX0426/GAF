#!/usr/bin/env bash
set -e

echo "============================================"
echo "  GAF 一键启动脚本"
echo "============================================"
echo ""

GAF_ROOT="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:---dev}"
START_DESKTOP=false
if [ "$MODE" = "--prod" ]; then
    START_DESKTOP=true
fi
if [ "${2:-}" = "--with-desktop" ]; then
    START_DESKTOP=true
fi
ENV_ROOT="${ENV_ROOT:-/opt/gaf/environment}"

echo "[模式] $MODE"
echo "[桌面] $START_DESKTOP"
echo ""

# 检查 .env 文件
if [ ! -f "$GAF_ROOT/.env" ]; then
    echo "[配置] .env 文件不存在，从模板创建..."
    cp "$GAF_ROOT/.env.example" "$GAF_ROOT/.env"
    echo "[配置] .env 已创建，请按需修改后重新运行"
fi

# 检查 conda 环境
echo "[检查] conda 环境 gaf..."
if ! conda run -n gaf python --version >/dev/null 2>&1; then
    echo "[错误] conda 环境 gaf 不存在，请先运行部署脚本创建环境"
    exit 1
fi

# 检查 Redis
echo "[检查] Redis..."
if command -v redis-server >/dev/null 2>&1; then
    if ! redis-cli ping >/dev/null 2>&1; then
        echo "[启动] Redis 服务..."
        redis-server --daemonize yes
        sleep 2
    else
        echo "[OK] Redis 已运行"
    fi
elif command -v docker >/dev/null 2>&1; then
    echo "[启动] Redis 容器..."
    docker compose -f "$GAF_ROOT/docker-compose.yml" up -d redis 2>/dev/null || echo "[警告] Redis 容器启动失败"
else
    echo "[警告] 未找到 redis-server 或 Docker，Redis 不会启动"
fi

# 数据库迁移
if [ -f "$GAF_ROOT/backend/manage.py" ]; then
    echo "[迁移] 数据库迁移..."
    cd "$GAF_ROOT/backend"
    conda run -n gaf python manage.py migrate --noinput 2>/dev/null || true
    cd "$GAF_ROOT"
fi

# 启动后端
echo "[启动] Django 后端..."
if [ -f "$GAF_ROOT/backend/manage.py" ]; then
    cd "$GAF_ROOT/backend"
    conda run -n gaf python manage.py runserver 0.0.0.0:8000 &
    BACKEND_PID=$!
    cd "$GAF_ROOT"
fi

# 启动 Agent
echo "[启动] GAF Agent..."
if [ -f "$GAF_ROOT/worker/src/__main__.py" ]; then
    cd "$GAF_ROOT/agent"
    # N199: 环境归一化 — 统一 conda env gaf, 废弃 venv gaf-agent
    conda run -n gaf python -m src &
    AGENT_PID=$!
    cd "$GAF_ROOT"
fi

# 启动前端
if [ -f "$GAF_ROOT/frontend/package.json" ]; then
    echo "[启动] React 前端..."
    cd "$GAF_ROOT/frontend"
    [ ! -d "node_modules" ] && npm install
    npm run dev &
    FRONTEND_PID=$!
    cd "$GAF_ROOT"
fi

# 启动桌面（开发模式默认跳过；使用 --with-desktop 启用）
if [ "$START_DESKTOP" = "true" ]; then
    if [ -f "$GAF_ROOT/desktop/package.json" ]; then
        echo "[启动] Electron 桌面..."
        cd "$GAF_ROOT/desktop"
        [ ! -d "node_modules" ] && npm install
        npm run dev &
        DESKTOP_PID=$!
        cd "$GAF_ROOT"
    fi
else
    echo "[跳过] Electron 桌面（开发模式默认跳过，使用 --with-desktop 启用）"
fi

# 从 .env 读取端口（默认 8000 / 5173）
_BACKEND_PORT=$(grep -oP '^BACKEND_PORT=\K\d+' "$GAF_ROOT/.env" 2>/dev/null || echo "8000")
_FRONTEND_PORT=$(grep -oP '^FRONTEND_PORT=\K\d+' "$GAF_ROOT/.env" 2>/dev/null || echo "5173")

echo ""
echo "============================================"
echo "  GAF 启动完成！"
echo "  后端: http://localhost:${_BACKEND_PORT}"
echo "  前端: http://localhost:${_FRONTEND_PORT}"
echo "  桌面: $START_DESKTOP（开发模式使用 --with-desktop 启用）"
echo "  Agent: ws://127.0.0.1:${_BACKEND_PORT}/${GAF_WS_AGENT_PATH:-ws/protocol/agents/}"
echo "============================================"
echo ""
echo "使用 stop.sh 停止服务"
wait
