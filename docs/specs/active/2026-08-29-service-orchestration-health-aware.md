---
spec_id: 2026-08-29-service-orchestration-health-aware
status: active
created: 2026-08-29
type: refactor
scope: scripts/gaf_daemon.py, backend/monitors, backend/protocol
prev: N/A
next: N/A
---

# Spec: 服务编排健康感知化（方案 A）

> **背景**：2026-08-28 用户反馈状态灯显示"未启动"但 agent 正常——根因是 backend 积累僵尸
> WS consumer（15161s 无心跳仍每 10s 写离线），暴露核心缺陷：gaf_daemon 只做"进程 alive"
> 检测，不感知"服务健康"。用户确认按方案 A（健康感知编排器）出实施计划。

## 1. 目标

把 `gaf_daemon.py` 从"进程看门狗"升级为**健康感知服务编排器**，让右上角状态灯真实反映
各服务健康度，并能自动处置僵尸/假死服务。

## 2. 阶段状态表

| Phase | 内容 | 状态 |
|-------|------|------|
| P1 | 服务健康探针层（backend healthz + agent hb probe + frontend http） | ✅ 完成 (health.py + HealthzView, 4 探针全过) |
| P2 | daemon 健康检查循环 + 自动重启 + 状态上报 | ✅ 完成 (杀 backend 后 40s 内自动拉起, 快照自动写) |
| P3 | 前端状态灯接入服务健康矩阵（monitors/status 扩展） | ✅ 完成 (5 服务全绿对勾, API+浏览器双验证) |
| P4 | agent 生命周期单一 Owner 收敛（daemon 唯一管理） | ✅ 完成 (active_channel CAS + 写入仲裁 + 僵尸自愈, 40s 无 offline 跳变) |
| P5 | 全量回归 + 文档同步 + 沉淀 | ⏳ |

## 3. N151 架构盘点

### 3.1 现状

```
gaf_daemon (看门狗, 仅 poll 进程)
 ├── redis (6379, redis_ping 探活) ✅ 已有应用级探针
 ├── backend (8000, port_listen 探活) ❌ 仅端口探活
 ├── agent (process poll 探活) ❌ 仅进程存活
 └── frontend (5173, port_listen 探活) ❌ 仅端口探活
```

### 3.2 反模式识别

| 反模式 | 位置 | 后果 |
|--------|------|------|
| 探活仅限"进程/端口"，无服务健康语义 | gaf_daemon.verify_service | 僵尸/假死无感知 |
| agent 生命周期双 Owner | backend/apps.py ready() + daemon | 双重管理冲突 → 僵尸连接 |
| 前端状态灯读 monitors/status 但无服务级健康数据 | backend/monitors/views.py | 假离线无人察觉 |
| 僵尸 consumer 无自愈/清理机制 | protocol/consumers.py | 写共享状态竞态 |

### 3.3 可复用资产

- **SystemHealthView**（`/api/v2/accounts/init/health/`）：已检查 DB+Redis+Celery，无需认证 → 直接用作 backend 探针
- **Agent 心跳 DB 查询**（agent_runtime._is_agent_connected_via_db）：已有 last_heartbeat 新鲜度判断 → 提取为 agent 健康探针
- **depends_on 拓扑排序**（gaf_daemon.startup_order）：复用
- **watchdog 重启节奏/撞车保护**（MAX_RESTART_COUNT/RESTART_WINDOW）：复用

## 4. 实施设计

### P1: 服务健康探针层（scripts/services/health.py 新文件）

为每个服务定义应用级健康检查函数（统一返回 `{healthy: bool, detail: str, ts: float}`）：

```python
def check_backend(cfg) -> Health       # GET /api/v2/accounts/init/health/ → db+redis pass 且 HTTP 200
def check_agent(cfg) -> Health         # DB 查询 Agent.last_heartbeat 距今 < 30s 且 status ∈ {idle,online}
def check_frontend(cfg) -> Health      # GET http://127.0.0.1:5173 返回 200（vite 200 目录页）
def check_redis(cfg) -> Health         # 复用现有 _redis_ping
```

- `verify_service` 拆两档：`verify="healthz"`（应用级，用于看门狗决策）vs `verify="port_listen"`（快速启动判定）
- backend/agent/frontend 全部切换到 `healthz`

### P2: daemon 健康检查循环（gaf_daemon.py 修改）

- 看门狗循环每 `HEALTH_CHECK_INTERVAL`（默认 15s，与 WATCHDOG_INTERVAL 对齐）执行：
  1. 每个服务跑 `check_*` 健康探针
  2. 不健康 → 走现有重启流程（撞车保护不变）
  3. **新增**：健康快照写入 `debug/health-status.json`（供状态接口读取）
- 新增 `gaf_daemon.py status --json` 输出含健康详情，便于脚本集成

### P3: 服务健康矩阵接入状态接口（backend/monitors/views.py + frontend）

- `system_status_view` 增加读取 `debug/health-status.json`（不存在则每字段 N/A），
  返回 `services: {redis, backend, agent, frontend, daemon}` 数组
- 前端 `HeaderStatusIndicator` Popover 新增"服务健康"小节：每服务绿/红点 + 详情
- overall 判定更新：`devices_idle>0 且 services 均 healthy` → running；
  任一服务 unhealthy → warning/error（而非仅看 device）

### P4: agent 生命周期单一 Owner（backend/apps.py + gaf_daemon.py）

- backend `apps.py ready()` 删除 agent 自启分支（保留 heartbeat loop + signals）
- daemon `build_services` 的 agent 服务配置改为：启动前清理僵尸 agent 进程（复用
  `agent_runtime._kill_stale_agent_processes`），daemon 成为唯一 agent 管理器
- **僵尸 consumer 治本**（N216 闭环）：`protocol/consumers.py` 的 `set_agent_offline` /
  `update_agent_heartbeat` 改为带 channel 归属校验：
  - Agent 模型加 `active_channel` 字段（migration）
  - `connect()` 时 CAS 抢占；heartbeat/offline 写入带 `WHERE active_channel=<self.channel>`
  - `_heartbeat_checker` 每次检查前读 DB 判自己是否过期，过期则自 canc本任务

### P5: 回归 + 文档 + 沉淀

- 后端：pytest 全量（backend 单测 + protocol WS 测试）
- 脚本：`gaf_daemon.py status` / `restart` 冒烟
- 前端：tsc + vitest（HeaderStatusIndicator 相关）
- 文档：gaf_daemon.py 模块 docstring + tech-stack + procedure 健康段
- 教训：更新 N216（补"active_channel 治本已落地"）或归档

## 5. N167 七维度评分（方案 A vs B 容器化 vs C 现成管理器）

| 方案 | ①架构 | ②归一 | ③兼容 | ④完善 | ⑤性能 | ⑥安全 | ⑦维护 | 总分 |
|------|------|------|------|------|------|------|------|------|
| A 健康感知 daemon | 3 | 2 | 3 | 3 | 2 | 2 | 3 | 18 |
| B 容器化混合 | 3 | 3 | 2 | 2 | 2 | 3 | 2 | 17 |
| C PM2/Supervisor | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 13 |

**A 选择理由**：复用现有 daemon 与博客已确认的 depends_on/重启机制（③⑤⑦最高），增量最小、
不引入新外部依赖（② 部分因 agent 留在宿主机无法全容器，B 此维度优势有限）；agent 控制本机
GUI 决定其必留宿主机，容器化收益打折。
**硬场景检查**：FK 无 / schema 分裂无 / 业务语义无 / 不可逆无（P4 迁移可回滚）→ 自决 A。

## 6. 验收标准

| P0 | 判据 |
|----|------|
| P1 | `health.py --check` 对 4 服务均返回正确 healthy/detail |
| P2 | 手动 kill backend 进程 → 15s 内 daemon 检测 unhealthy 并重启；health-status.json 更新 |
| P3 | 状态灯 Popover 显示 5 项服务健康点；杀 agent 后灯转 warning |
| P4 | 重启后无新僵尸 consumer（日志无递增超时）；agent 状态稳定 idle>5min |
| P5 | 全量 pytest 通过；tsc 0 错误；N216 文档更新 |

## 7. 不做（本 spec 范围外）

- 容器化迁移（方案 B）不实施，仅保留 docker-compose 现状
- 生产 nginx 部署不实施
- Redis 持久化/主从不实施