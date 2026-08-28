# Verification: SQLite + WAL 验证

## 测试结果

### 1. backend 全量测试
```
2221 passed, 2 skipped, 3 warnings in 474.08s (0:07:54)
```

### 2. WAL pragma 验证
通过 Django connection 启动后:
```
journal_mode: wal
busy_timeout: 5000
```

### 3. manage.py check
通过 (无报错)

## 健康检查输出

`GET /api/v2/accounts/init/health/`:
```json
{
  "database": {
    "current_version": "SQLite (journal=wal, busy_timeout=5000ms)",
    "required_version": "3.8+ (WAL)",
    "status": "pass",
    "suggestion": null
  }
}
```

## 兼容性

- 保留 `DB_ENGINE` 环境变量入口, 可切回 PG/MySQL
- 业务代码无任何 DB-specific 逻辑依赖
- 所有 migration 在 SQLite 上正常 apply
