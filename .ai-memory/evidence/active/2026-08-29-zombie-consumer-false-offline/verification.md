---
maintainer: manual
source: GAF
load_when: [evidence]
priority: high
symptom: [zombie-consumer, agent-false-offline, stale-websocket]
solution: 重启后端清僵尸 consumer 后 agent 状态稳定 idle, 状态灯恢复"运行中"
created_by: AI
last_updated: 2026-08-28
---
## Verification（验证）

$ D:\code\environment\conda\envs\gaf\python.exe scripts/gaf_daemon.py restart

$ conda run -n gaf python -c "import os, django, time; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup(); from agents.models import Agent; from django.utils import timezone; [print(i, Agent.objects.first().status, round((timezone.now()-Agent.objects.first().last_heartbeat).total_seconds())) or time.sleep(3) for i in range(12)]"

预期：12 行全部 `idle`，hb_age ≤10（无 offline 跳变）

$ GET /api/v2/monitors/status/ (带 token)

预期：`overall=running devicesIdle=1`