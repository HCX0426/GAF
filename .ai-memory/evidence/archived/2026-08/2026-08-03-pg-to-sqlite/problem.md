# Problem: GAF 默认走 PostgreSQL, 单机部署场景性能过剩且增加部署复杂度

## 背景

GAF 启动配置 dev=SQLite, prod=PostgreSQL, 但实际部署场景是单机多用户多设备
(< 100 并发, 峰值 ~80 TPS), 完全在 SQLite + WAL 性能范围内。

## 痛点

1. **部署复杂度**: PG 需要单独装、建库、配用户、迁移
2. **dev/prod 差异**: 同一份 ORM 代码在两个 DB 上行为可能不一致 (e.g. JsonField 高级查询)
3. **Dockerfile 依赖**: 引入 libpq-dev + psycopg2-binary, 镜像变大
4. **健康检查特殊化**: accounts/views.py:473 单独检查 PG 状态

## 量化评估

- GAF 峰值并发: ~80 (10 用户 + 10 任务 + 5 调度 + 5 LLM + 10 WS 心跳)
- SQLite WAL 写性能: ~1000 TPS
- SQLite WAL 读性能: ~10万 QPS
- 余量: 写 12x, 读 1000x
