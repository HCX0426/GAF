"""GAF 应用集中配置
所有版本号、API 前缀、应用名称、超时、分页等统一从此文件读取，避免硬编码。
"""

import os

APP_NAME = 'GAF'
APP_VERSION = '2.0.0'

# API 版本前缀 — 从环境变量读取，修改此处即可同步所有层
# 格式如 "api/v2"，不要带首尾斜杠
API_PREFIX = os.getenv("GAF_API_PREFIX", "api/v2")

# App 路由路径映射 — 各层 app 的 URL 路径段统一在此定义
# 修改此处可同步后端路由、前端 API 调用、Agent 端请求路径
# 此项对稳定性要求高，建议仅通过环境变量覆盖，不推荐运行时修改
APP_ROUTES = {
    'accounts': os.getenv("GAF_ROUTE_ACCOUNTS", "accounts"),
    'agents': os.getenv("GAF_ROUTE_AGENTS", "agents"),
    'tasks': os.getenv("GAF_ROUTE_TASKS", "tasks"),
    'resources': os.getenv("GAF_ROUTE_RESOURCES", "resources"),
    'monitors': os.getenv("GAF_ROUTE_MONITORS", "monitors"),
    'skills': os.getenv("GAF_ROUTE_SKILLS", "skills"),
    'notifications': os.getenv("GAF_ROUTE_NOTIFICATIONS", "notifications"),
    'debug': os.getenv("GAF_ROUTE_DEBUG", "debug"),
    'qa': os.getenv("GAF_ROUTE_QA", "qa"),
    'plugins': os.getenv("GAF_ROUTE_PLUGINS", "plugins"),
    'protocol': os.getenv("GAF_ROUTE_PROTOCOL", "protocol"),
    'metrics': os.getenv("GAF_ROUTE_METRICS", "metrics"),
    'gamestate': os.getenv("GAF_ROUTE_GAMESTATE", "gamestate"),
    'pipeline': os.getenv("GAF_ROUTE_PIPELINE", "pipeline"),
    'scheduler': os.getenv("GAF_ROUTE_SCHEDULER", "scheduler"),
    'executions': os.getenv("GAF_ROUTE_EXECUTIONS", "executions"),
    'analytics': os.getenv("GAF_ROUTE_ANALYTICS", "analytics"),
    'settings': os.getenv("GAF_ROUTE_SETTINGS", "settings"),
    'search': os.getenv("GAF_ROUTE_SEARCH", "search"),
    'ai': os.getenv("GAF_ROUTE_AI", "ai"),
    'i18n': os.getenv("GAF_ROUTE_I18N", "i18n"),
    'logs': os.getenv("GAF_ROUTE_LOGS", "logs"),
    'schema': os.getenv("GAF_ROUTE_SCHEMA", "schema"),
    'docs': os.getenv("GAF_ROUTE_DOCS", "docs"),
    'system': os.getenv("GAF_ROUTE_SYSTEM", "system"),
}

# WebSocket 路径段（Agent 协议通道）
WS_AGENT_PATH = os.getenv("GAF_WS_AGENT_PATH", "ws/protocol/agents/")

# WebSocket 路径段（设备级 ADB 日志流，TD-366: env-driven 与前端 VITE_WS_DEVICES_PATH 同步）
WS_DEVICES_PATH = os.getenv("GAF_WS_DEVICES_PATH", "ws/devices/")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

ADB_COMMAND_TIMEOUT = 10
NODE_COMMAND_TIMEOUT = 10
WEBHOOK_TIMEOUT = 10
OAUTH_REQUEST_TIMEOUT = 15
LLM_REQUEST_TIMEOUT = 120
PREFLIGHT_MAX_WORKERS = 5
PREFLIGHT_HEARTBEAT_CUTOFF_SECONDS = 60
