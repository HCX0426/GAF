# Spec-Context: Service Orchestration Health-Aware (2026-08-29)

## 用户决策原文
- "我这个项目不可能之启动一个服务就能用了 都评估下架构级解决方法" — 要求评估服务编排架构
- "按方案 A 出实施计划" — 选定 A（健康感知 daemon 编排器），spec 已批准

## N151 5 步法评估
1. **架构盘点**: gaf_daemon 仅 poll 进程存活（redis_ping / port_listen / process），不感知服务健康；
   backend apps.py 保留 agent 自启分支（GAF_AUTO_START_AGENT）与 daemon 双 Owner 冲突；
   agent 心跳经 AgentConsumer → update_agent_heartbeat/set_agent_offline 无 channel 仲裁；
   前端状态灯读 monitors/status 但无服务级数据。已有资产：SystemHealthView、agent_runtime
   _is_agent_connected_via_db、depends_on 拓扑、watchdog 撞车保护。
2. **识别反模式**: (a) 探活仅"进程/端口"无服务健康语义 → 僵尸/假死无感知; (b) agent 双 Owner → 僵尸连接;
   (c) 状态灯无服务健康数据 → 假离线无人察觉; (d) 僵尸 consumer 无自愈 → 写共享状态竞态。
3. **备选方案**: A) 完善 daemon 为健康感知编排器（复用现有） B) 容器化混合（docker-compose + agent 留宿主机）
   C) 成熟管理器（PM2/Supervisor + nginx）。
4. **拒绝反模式**: 拒绝 B（agent 需控本机 GUI 不能容器化，收益打折）、C（Windows 支持弱、侵入大）；
   选 A（增量最小、复用 depends_on/重启机制，N167 18 分领先）。
5. **AI 自决边界**: agent 留宿主机必然，daemon 保持唯一 Owner; active_channel 仲裁为纯增量模型字段
   （migration 0018 可回滚）；healthz 端点 AllowAny 只暴露 db/redis pass/fail 无敏感信息。

## N167 七维度评分
| 方案 | ①架构 | ②归一 | ③兼容 | ④完善 | ⑤性能 | ⑥安全 | ⑦维护 | 总分 |
|------|------|------|------|------|------|------|------|------|
| A 健康感知 daemon | 3 | 2 | 3 | 3 | 2 | 2 | 3 | 18 |
| B 容器化混合 | 3 | 3 | 2 | 2 | 2 | 3 | 2 | 17 |
| C PM2/Supervisor | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 13 |
- **⑤ 性能理由**: 探针每 15s 一次 HTTP/DB 查询，开销极低；agent DB 探针复用现有 ORM 一次 exists。
- **⑥ 安全理由**: healthz 仅返 pass/fail + 非敏感 detail；channel 仲裁防僵尸写入无安全面。
- **反向论证**: 不选 B — agent 需访问本机 GUI（截图/输入）无法容器化，且生产 nginx 超出当前单人自用范围；
  不选 C — Supervisor 在 Windows 依赖 MSYS、PM2 对 python 进程管理弱，侵入大。
- **硬场景 ③ 业务语义判定**: 影响数据保留/业务流程？N → 可自决。
- **硬场景检查**: FK 无 / schema 分裂无 / 业务语义无 / 不可逆无（0018 迁移可回滚）→ 自决 A。

## 关键实施决策
- **P1 探针层**: `scripts/services/health.py`（新包），4 服务应用级探针 + `--check` CLI + 快照写入
  `debug/health-status.json`；backend 新增 `/api/v2/system/healthz/`（HealthzView, AllowAny, db+redis 只读）。
- **P2 daemon 健康感知**: `DaemonRunner._run_health_checks()` 每轮（15s）探针 → 快照 → 应用假死自动重启
  （撞车保护 MAX_RESTART_COUNT 复用）；`status --health/--json` 输出健康详情。
- **P3 状态矩阵**: `monitors/status` 响应加 `services` 数组（读快照，缺失返回 []）；整体判定
  services 不健康 → warning；前端 HeaderStatusIndicator Popover "服务健康" 2 列网格。
- **P4 active_channel 仲裁**: Agent 模型加 `active_channel`（migration 0018）；connect() CAS 接管
  （记录不存在放行，测试 MagicMock 兼容）；update_agent_heartbeat / set_agent_offline 带 channel 守卫
  （非现任 0 行）；_heartbeat_checker 每轮 `_db_am_i_active_owner` 自查，过期自愈退出；
  backend apps.py 移除 agent 自启分支（daemon 唯一 Owner）。
- **P5 回归**: protocol 127 / agents+monitors 50 / accounts+gaf_core+tasks 435 passed
  （1 预存失败 test_analytics_views recovery_triggered 无关）；前端 tsc 0 错误 + vitest 47 文件 366 passed；
  N216 lesson 补"治本已落地"。

## 已知限制（spec 记录，非本次实现）
- 容器化迁移（方案 B）不实施，docker-compose 现状保留。
- 生产 nginx 部署不实施。
- Redis 持久化/主从不实施。

## N173 用时字段
- start_ts: 2026-08-29T00:30:00+08:00
- end_ts: 2026-08-29T01:10:00+08:00
- duration_min: ~40
- within_baseline: true（大修改基线 < 60 min）