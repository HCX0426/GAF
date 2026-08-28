---
maintainer: manual
source: GAF
load_when: [evidence]
priority: high
symptom: [health-aware-orchestration, daemon, active-channel, zombie]
solution: gaf_daemon 健康感知编排 + active_channel 连接仲裁, 根治僵尸假离线
created_by: AI
last_updated: 2026-08-29
---
## Problem（症状 / 触发条件）

用户反馈状态灯"未启动"但 agent 正常 — 根因是 backend 积累僵尸 WS consumer
（15161s 无心跳仍每 10s 写离线），暴露 gaf_daemon 只做"进程 alive"检测、不感知
"服务健康"的架构缺陷。用户要求按方案 A 出实施计划并落地。

## Solution（解决步骤）

1. P1 服务健康探针层: `scripts/services/health.py` (redis PING / backend healthz / agent DB hb / frontend HTTP) + backend 新增 `/api/v2/system/healthz/` (AllowAny, db+redis)
2. P2 daemon 健康感知: 看门狗每轮跑探针 → 写 `debug/health-status.json` → 应用假死服务自动重启 + `status --health/--json`
3. P3 前端服务健康矩阵: `monitors/status` 返回 services 数组, HeaderStatusIndicator Popover 展示 5 服务绿/红点
4. P4 active_channel 仲裁: Agent 表加字段 (migration 0018) → connect() CAS 接管 → heartbeat/offline 带 channel 守卫 → checker 自愈
5. P5 回归: protocol 127 + agents/monitors 50 + accounts/gaf_core/tasks 435 passed (1 预存失败无关)

## Verification（验证）

$ python scripts/services/health.py --check
$ python scripts/gaf_daemon.py status --health
$ python scripts/gaf_daemon.py restart   # 杀 backend 后 40s 内自动拉起
$ conda run -n gaf python -m pytest backend/protocol/tests/test_protocol.py -q

预期：4 探针全 OK；5 服务全绿；自动重启生效；agent 40s 内 idle 稳定无 offline 跳变；127 passed