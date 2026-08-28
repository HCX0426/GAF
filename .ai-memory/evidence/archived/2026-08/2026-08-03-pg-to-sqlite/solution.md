# Solution: dev/prod 统一 SQLite + WAL, 保留 PG 可选入口

## 实施步骤

### Step 1: base.py SQLite WAL 配置
```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;",
            "transaction_mode": "IMMEDIATE",
        },
    }
}
```

### Step 2: prod.py 默认 DB 改 SQLite
- 移除默认 PG 行为
- 保留 DB_ENGINE 环境变量入口 (供未来扩展)

### Step 3: accounts/views.py health check 适配
- 替换 PostgreSQL 检查为通用 database 检查
- 查询 `PRAGMA journal_mode` 验证 WAL

### Step 4: Dockerfile 移除 PG 依赖
- 移除 libpq-dev
- 注释更新

### Step 5: requirements/prod.txt 移除 psycopg2
- 移除 psycopg2-binary

## 风险评估

- **低风险**: SQLite 单机写性能已覆盖 GAF 需求
- **可恢复**: 保留 DB_ENGINE 入口, 紧急时切回 PG
- **零迁移成本**: Django 内置 SQLite migration 支持
