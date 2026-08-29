---
spec: 2026-08-29-naming-f-device-bridge
title: 命名归一化 F 批：Device 抽象 + device_bridge 命名归一（含 AgentConsumer 位置校正）
status: active
created: 2026-08-29
estimated_effort: 1 day
risk: medium
depends_on: []
source: docs/analysis/concept-naming-normalization.md（三 agent 目录审计 2026-08-29） / 探索代理 audit 报告
---

# 命名归一化 F 批：Device 抽象 + device_bridge 命名归一

## 1. 背景与动机 (Background)

对三个 "agent" 目录（`agent/` 进程、`backend/device_bridge/`、`backend/agents/` Django app）的深入审计（2026-08-29）发现：批 E 仅覆盖 agent 进程的 `Agent*` 符号；而 `backend/device_bridge/`（后端设备平台抽象层）与 `backend/agents/` app 的 **Device 抽象三义 / `consumers.py` 名不副实 / `GAME_PROCESS_NAMES` 重复 / docstring 错称** 等命名冲突完全未被覆盖。本批收口这些 device 侧命名，并校正 E-6 中 `AgentConsumer` 的位置误述。

## 2. 核心问题 (Problem)

| # | 项 | 现状 | 目标 | 级 |
|---|----|------|------|----|
| F-1 | `DeviceInfo` 三义 | `device_bridge/platforms/base.py:32` DTO / `agent/src/devices/discovery/base.py:13` DTO / `backend/agents/view_sets/app_info.py:406` `DeviceInfoView` 端点 | 端点 `DeviceInfoView`→`DeviceDetailView`；两 DTO 文档区分（或后端 DTO→`BridgeDeviceInfo`） | med |
| F-2 | 双发现架构 | backend `device_bridge.discovery`(`scan_all_emulators`/`enum_windows`)+`EmulatorInfo`/`WindowInfo` vs `PlatformDeviceDiscoverer`+`DeviceInfo`；agent `DeviceCenter`/`EmulatorDiscovery`/`WindowDiscovery` | 使 `device_bridge.discovery.*` 为单一扫描源；文档显式区分 bridge(后端)/center(agent 进程) 两层发现 | med |
| F-3 | `GAME_PROCESS_NAMES` 重复 | `device_bridge/discovery/windows.py:17` 与 `platforms/windows/discovery.py:14` 两份 | 单一来源（去重） | low |
| F-4 | device_bridge docstring 错称 | `device_bridge/__init__.py:2` "GAF Agent 模块" | 改为设备抽象/桥接层说明；文档注明 "bridge" 仅为包名（无 `Bridge` 类） | low(文档) |
| F-5 | `consumers.py` 名不副实 + AgentConsumer 位置 | `backend/agents/consumers.py` 仅 `AdbLogStreamConsumer`（无 AgentConsumer）；`AgentConsumer` 实际在 `backend/protocol/consumers.py:123` | `agents/consumers.py`→`adb_log_consumers.py`（需路由更新）；E-6 文本校正：AgentConsumer 属 protocol app | med |
| F-6 | `agent_service.py` vs `DeviceService` 类不一致 | `agent_service.py`(函数模块) vs `services/device_service.py`(类) + `AgentViewSet` 重叠 token 生命周期 | 统一 service 形态（文档/可选合并） | low |
| F-7 | `_check_single_device` 跨层耦合 | `agent_runtime.py:458` 调 `DeviceViewSet()._check_single_device()` 私有方法 | 迁入 `DeviceService`（去 ViewSet 私有依赖） | low-med |
| F-8 | `EmulatorLifecycleView` vs `emulator_lifecycle.py` | 端点 vs 模块同名 | 文档注明关系 | low |
| F-9 | `DeviceStats*` 三义 | `DeviceStatsView`/`DeviceStatsSchema`/`Device.device_stats` | 文档区分 | low |
| F-10 | 双设备发现权威（设计） | backend `DeviceScanView` 与 agent `DeviceCenter.auto_discover()` 均写 `agents.Device` | **设计决策**（非重命名）：定 source-of-truth/触发时机，单独立项（OQ-9） | high(设计) |

## 3. 目标 (Goals)

1. F-1~F-9 命名/doc/低危代码收口。
2. F-5 校正 E-6 中 AgentConsumer 位置（protocol app，非 agents app）。
3. F-10 作为设计决策登记 OQ-9，不在本次重命名范围。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | F-1 `DeviceInfoView`→`DeviceDetailView` + DTO 文档 | ⏳ |
| P2 | F-2 单一发现源 + 文档区分两层 | ⏳ |
| P3 | F-3 `GAME_PROCESS_NAMES` 去重 / F-4 docstring | ⏳ |
| P4 | F-5 `consumers.py`→`adb_log_consumers.py` + 路由 + E-6 校正 | ⏳ |
| P5 | F-6/F-7/F-8/F-9 一致性清理 + 文档 | ⏳ |

（各任务代码映射见审计 file:line；F-10 单独立项。）

## 5. 测试与验收

- `pytest backend/agents backend/device_bridge agent/tests` 通过。
- grep `DeviceInfoView`(→`DeviceDetailView`)/`GAME_PROCESS_NAMES` 单源/`AgentConsumer` 位置正确。
- 评估稿标记 F 批完成。

## 6. 回滚

- 端点/文件改名有路由/导入影响，需同步迁移；其余纯文档/低危，git revert。
