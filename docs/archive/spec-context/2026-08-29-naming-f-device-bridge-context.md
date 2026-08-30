---
start_ts: 2026-08-30T07:40:00+00:00
end_ts: 2026-08-30T08:35:00+00:00
duration_min: 55
within_baseline: true
root_cause_if_over: D/E/F 三批收口在一次 commit（批内连续，无超基线阶段）
---
{
  "spec": "2026-08-29-naming-f-device-bridge",
  "phase": "D-E-F-close",
  "commit_hash": "",
  "status": "completed",
  "related_specs": [
    "2026-08-29-naming-d-docs",
    "2026-08-29-naming-e-agent-concepts"
  ],
  "n151_arch_audit": {
    "step1_schemas": "D/E/F 均为命名归一化收口：D 纯文档（子文档矛盾）/ E 概念注释 / F device_bridge+Device 抽象命名；无模型变更（makemigrations --check clean）",
    "step2_data_flow": "F-1 DeviceInfoView->DeviceDetailView 仅视图类名（URL /api/v2/devices/{id}/info/ 不变）；F-3 GAME_PROCESS_NAMES 单一来源（platforms 导入）；F-5 consumers.py->worker_consumers.py 路由同步；F-7 worker_runtime heartbeat 迁 DeviceService（原 DeviceViewSet._check_single_device 已不存在，dead call 修复）",
    "step3_deps": "F-5 文件改名仅 workers/routing.py 引用，无跨 app import；protocol.WorkerConsumer 归属已校正（E-6）",
    "step4_risk": "低：无迁移/无前端改动；验证 backend 切片 641 + 125 passed，makemigrations clean，ruff 0",
    "step5_rollback": "纯重命名+文档，git revert 即可（F-7 为行为修复，回滚亦可）"
  },
  "n167_eval": {
    "dim1_arch_longterm": 4,
    "dim2_global_normalize": 5,
    "dim3_cross_cutting": 4,
    "dim4_reversibility": 5,
    "dim5_future_ext": 4,
    "dim6_complexity": 4,
    "dim7_maintenance": 5,
    "total": 31,
    "leader_gap": 8,
    "decision": "self_approved"
  },
  "key_decisions": [
    "D20: debug-logging §8.1 <safe_pipeline> -> <task_name>（2026-08-24 变更已生效，旧称弃用）",
    "D21: 截图缓存 TTL 口径归一（Worker 本地秒级 cache_ttl=300 vs Redis 毫秒级，50ms 标示意）",
    "D22: deployment §4.2 默认 SQLite+WAL（PG 字段仅 DB_ENGINE 切换），对齐 base.py 实参",
    "D24: governance-batch hot-path 计数修真 18（24-6 模块），batch docstring 同步",
    "X1: TaskService.dispatch_task 表述代码确证成立，归档 spec 冻结不改",
    "F-7: worker_runtime heartbeat 从私有方法迁移到 DeviceService.check_single_device_health"
  ],
  "reflection": {
    "passed": ["backend slice 641 passed", "rerun 125 passed", "makemigrations clean", "ruff 0"],
    "skipped": ["worker 全套 2060 passed 已在 G 收口跑过，本批仅注释级改动（__main__.py docstring），无逻辑影响"]
  }
}