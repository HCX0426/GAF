#!/usr/bin/env bash
# GAF bare-metal deployment script for Linux (systemd + nginx).
#
# Usage:
#   sudo bash deploy/deploy.sh install   # First-time install
#   sudo bash deploy/deploy.sh update    # Update code + restart services
#   sudo bash deploy/deploy.sh restart   # Restart services only
#   sudo bash deploy/deploy.sh status    # Show service status
#   sudo bash deploy/deploy.sh logs      # Tail logs
#
# Prerequisites:
#   - Ubuntu 22.04+ / Debian 12+ / RHEL 9+
#   - Redis 7+ running (SQLite + WAL 内置, 无需额外安装)
#   - Node.js 20+ (for frontend build)
#   - Python 3.11+ (for venv)

set -euo pipefail

# Configuration (override via environment)
INSTALL_DIR="${INSTALL_DIR:-/opt/gaf}"
SERVICE_USER="${SERVICE_USER:-gaf}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

# Paths
BACKEND_DIR="$INSTALL_DIR/backend"
FRONTEND_DIR="$INSTALL_DIR/frontend"
VENV_DIR="$INSTALL_DIR/venv"
NGINX_CONF_SRC="$(dirname "$0")/nginx/gaf.conf"
NGINX_CONF_DST="/etc/nginx/sites-available/gaf.conf"
SYSTEMD_DIR="$(dirname "$0")/systemd"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        err "This script must be run as root (use sudo)."
        exit 1
    fi
}

ensure_service_user() {
    if ! id -u "$SERVICE_USER" &>/dev/null; then
        log "Creating service user: $SERVICE_USER"
        useradd --system --create-home --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
    fi
}

install_system_deps() {
    log "Installing system dependencies..."
    apt-get update -qq
    apt-get install -y -qq \
        python3.11 python3.11-venv python3-pip \
        nodejs npm \
        nginx \
        redis-tools \
        build-essential \
        >/dev/null
    log "System dependencies installed."
}

setup_venv() {
    log "Setting up Python venv at $VENV_DIR..."
    sudo -u "$SERVICE_USER" "$PYTHON_BIN" -m venv "$VENV_DIR"
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --upgrade pip wheel setuptools
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements/prod.txt"
    log "Python venv ready."
}

build_frontend() {
    log "Building frontend..."
    pushd "$FRONTEND_DIR" >/dev/null
    sudo -u "$SERVICE_USER" npm ci --prefer-offline
    sudo -u "$SERVICE_USER" npx vite build
    popd >/dev/null
    log "Frontend built to $FRONTEND_DIR/dist."
}

django_migrate() {
    log "Running Django migrations..."
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" "$BACKEND_DIR/manage.py" migrate --noinput
}

django_collectstatic() {
    log "Collecting static files..."
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" "$BACKEND_DIR/manage.py" collectstatic --noinput --clear
}

install_nginx_config() {
    log "Installing nginx config..."
    mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
    cp "$NGINX_CONF_SRC" "$NGINX_CONF_DST"
    ln -sf "$NGINX_CONF_DST" /etc/nginx/sites-enabled/gaf.conf
    # Remove default site if present
    rm -f /etc/nginx/sites-enabled/default
    nginx -t
    systemctl reload nginx
    log "nginx config installed and reloaded."
}

install_systemd_units() {
    log "Installing systemd units..."
    cp "$SYSTEMD_DIR"/gaf-*.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable gaf-backend gaf-celery-worker gaf-celery-beat
    log "systemd units installed and enabled."
}

restart_services() {
    log "Restarting GAF services..."
    systemctl restart gaf-backend
    systemctl restart gaf-celery-worker
    systemctl restart gaf-celery-beat
    log "Services restarted."
}

show_status() {
    systemctl status gaf-backend --no-pager || true
    systemctl status gaf-celery-worker --no-pager || true
    systemctl status gaf-celery-beat --no-pager || true
    systemctl status nginx --no-pager || true
}

tail_logs() {
    journalctl -u gaf-backend -f &
    journalctl -u gaf-celery-worker -f &
    journalctl -u gaf-celery-beat -f &
    wait
}

cmd_install() {
    require_root
    ensure_service_user
    install_system_deps
    setup_venv
    build_frontend
    django_migrate
    django_collectstatic
    install_nginx_config
    install_systemd_units
    restart_services
    log "GAF installation complete. Visit http://localhost (or your domain)."
}

cmd_update() {
    require_root
    setup_venv
    build_frontend
    django_migrate
    django_collectstatic
    restart_services
    log "GAF update complete."
}

cmd_restart() {
    require_root
    restart_services
}

case "${1:-}" in
    install) cmd_install ;;
    update) cmd_update ;;
    restart) cmd_restart ;;
    status) show_status ;;
    logs) tail_logs ;;
    *)
        echo "Usage: $0 {install|update|restart|status|logs}"
        exit 1
        ;;
esac
