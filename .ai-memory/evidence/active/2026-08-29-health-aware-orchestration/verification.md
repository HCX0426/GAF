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
## Verification（验证）

$ D:\code\environment\conda\envs\gaf\python.exe scripts/services/health.py --check --write

预期: [OK] redis / [OK] backend / [OK] agent / [OK] frontend

$ D:\code\environment\conda\envs\gaf\python.exe scripts/gaf_daemon.py status --health

预期: Daemon 运行中 + 5 项 [OK]

$ 手动 Stop backend 进程 → 等待 40s

预期: daemon 自动拉起新 daphne (端口 8000 有新 PID), health-status.json updated_at 持续刷新

$ conda run -n gaf python -c "from agents.models import Agent; print(Agent.objects.first().status, Agent.objects.first().active_channel)"

预期: idle + channel 值 (CAS 接管生效)

$ conda run -n gaf python -m pytest backend/protocol/tests/test_protocol.py -q

预期: 127 passed