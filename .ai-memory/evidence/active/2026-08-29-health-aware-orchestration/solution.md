---
maintainer: manual
source: GAF
load_when: [evidence]
priority: high
symptom: [health-aware-orchestration, daemon, active-channel, zombie]
solution: gaf_daemon 健康感知编排 + active_channel 连接仲裁
created_by: AI
last_updated: 2026-08-29
---
## Solution（解决步骤）

1. P1: `scripts/services/health.py` (4 服务应用级探针 + --check CLI + 快照) + `backend/gaf_core/views.py` HealthzView (/api/v2/system/healthz/ AllowAny)
2. P2: `scripts/gaf_daemon.py` — DaemonRunner._run_health_checks() 每轮探针+快照+健康感知重启; status 支持 --health/--json
3. P3: `backend/monitors/views.py` `_load_service_health()` 读快照 → 响应加 services; `frontend/src/components/Layout/HeaderStatusIndicator.tsx` Popover 服务健康小节
4. P4: `backend/agents/models.py` active_channel 字段 + migration 0018; `backend/protocol/consumers.py` connect CAS/_db_am_i_active_owner/自愈; `backend/protocol/services.py` heartbeat/offline channel 守卫; `backend/agents/apps.py` 移除 backend 自启 (单一 Owner)
5. P5: 回归 + N216 lesson 更新"治本已落地"