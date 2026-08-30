---
spec: 2026-08-30-oq9-device-discovery-authority
title: 设备发现权威统一（OQ-9 / F-10）：agent WS 为 Device 生命周期单一权威
status: done
created: 2026-08-30
estimated_effort: 1 day
risk: medium
depends_on: [2026-08-29-naming-g-worker-rename, 2026-08-29-naming-f-device-bridge]
source: docs/analysis/concept-naming-normalization.md §9(OQ-9)/§7 F 批(F-10)/naming-f-device-bridge §2(F-2)
---

# 设备发现权威统一（OQ-9 / F-10）：agent WS 单一权威

> 方案决策（2026-08-30 用户确认）：**A — agent WS 为 Device 生命周期单一权威**；
> `DeviceRegisterView`（HTTP）收敛为手动设置/校正渠道；统一设备身份键两端复用。

## 1. 背景与动机 (Background)

OQ-9（F-10）双设备发现权威：当前写 `workers.Device` 表有两条独立写入源：

| 写入源 | 触发 | 路径 | 身份查找 |
|--------|------|------|---------|
| **agent WS `device.sync`** | agent 连接建立（自动） | `worker` `connection.py:_sync_devices` → 帧 `device.sync` → `protocol/consumers.py:_handle_device_sync` → `_db_register_device` | `protocol/services.py:lookup_device_id_by_agent`（7 策略） |
| **HTTP `DeviceRegisterView`** | 前端扫描后用户点注册（手动） | `workers/view_sets/scan_register.py` POST `/devices/register/` | 内联 5 步 dedup（hwnd > adb_serial > emulator+空serial > window_title > name+type） |

两条路径各自 upsert，身份键不共享（7 策略 vs 5 步）→ 同一物理设备可能被以不同键匹配/新建记录（重复或字段丢失），且自动发现（`DeviceCenter.auto_discover()` → `DeviceManager` → sync）与手动注册语义重叠。

`DeviceScanView`（GET `/devices/scan/`）本身**只读**（返回扫描预览），不作为写入源，无需改动。

## 2. 核心问题 (Problem)

| # | 项 | 现状 | 目标 |
|---|----|------|------|
| P-1 | 身份键不共享 | HTTP 5 步 dedup vs agent 7 策略 `lookup_device_id_by_agent` 独立实现 | 抽取单一 `resolve_device_identity()` 两端复用 |
| P-2 | 双写入源语义重叠 | 自动 sync 与手动 register 均创建/更新 Device，互不知晓对方已登记的设置 | agent WS 为创建/生命周期权威；HTTP register=设置/校正渠道（保留手动创建 fallback） |
| P-3 | 冲突无仲裁 | 自动 sync 可能覆盖用户手动命名/绑定；手动 register 可能覆盖 agent 上报的 serial/hwnd | 仲裁：基础字段（status/serial/hwnd）以 agent 上报为准；个性化字段（name/绑定/方法）以最后手动写入为准，agent sync 不 touch |
| P-4 | 触发时机未定义 | 仅 connect 时 sync 一次；断线重连后新出现设备不自动入库 | 定义：connect + 重连自动 sync（现状保留）；可选周期重扫 `GAF_AUTO_RESCAN_INTERVAL`（默认 0 = 关闭，只做 connect sync） |

## 3. 目标 (Goals)

1. **统一设备身份键**：新增 `backend/workers/services/device_identity.py::resolve_device_identity()`，合并两端查找（优先级：window_handle/hwnd > adb_serial > window_title > name+type，附 emulator_brand 消歧），`DeviceRegisterView` 与 `_handle_device_sync`/`_db_register_device` 均改调它。
2. **agent WS 为生命周期权威**：`device.sync` 为设备创建/更新的默认路径；`DeviceRegisterView` 收敛为设置/校正（manual 创建保留，`extra_info.registered_via` 标记 `manual`/`agent`）。
3. **冲突仲裁规则**（见 §4.3）：基础字段 agent 优先；个性化字段手动优先。
4. **触发时机**：保留 connect/重连 sync；新增可选周期重扫配置（默认关）。
5. **文档**：F-2 两层发现边界 + OQ-9 权威结论进 overview「概念速查」与 `device_bridge/discovery/__init__.py` 已有说明的补充（指向本 spec）。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 身份键模块 `resolve_device_identity()` + backend 两端接入（register/sync） | ✅ 2026-08-30（`device_identity.py::find_device_by_identity`；wire：HTTP register 5 步内联删除，`register_agent_device` 4 分支统一；并修复 C 批漏改 `emulator`→`emulator_brand` ×2） |
| P2 | `registered_via` 标记 + register 收敛（基础/个性化字段分离更新） | ✅ 2026-08-30（manual/agent 标记；sync 不再覆盖 name——P-3） |
| P3 | 冲突仲裁单测 + agent sync 补全基础字段不覆盖个性化 | ✅ 2026-08-30（`test_device_identity.py` 4 例；`_agent_scope_q` 兼容未归属设备） |
| P4 | 可选周期重扫（`GAF_AUTO_RESCAN_INTERVAL`，默认 0）+ 文档同步 | ✅ 2026-08-30（`WorkerConfig.auto_rescan_interval` + `__main__._auto_rescan_loop`；`.env.example`；overview §11.6；评估稿 OQ-9 ✅） |

#### Task P1.1: 身份键模块（新建）

- 新建 `backend/workers/services/device_identity.py`：

```python
def resolve_device_identity(device_type, *, hwnd="", adb_serial="", emulator_brand="",
                            window_title="", name="") -> list[Q]:
    """返回 Device 查找的折取查询列表（按优先级排序）。

    优先级（合并 HTTP 5 步 + agent 7 策略）：
      1. windows+window_handle  2. adb_serial  3. emulator_brand+空serial
      4. windows+window_title  5. name+type
    """
```

- 内部实现逐项构建 `Device.objects.filter(device_type=..., window_handle__iexact=hwnd)` 等，
  顺序查首个命中（与现存 dedup 语义一致）。

#### Task P1.2: 两端接入

- `workers/view_sets/scan_register.py` `DeviceRegisterView.post`：替换 5 步内联 dedup → `resolve_device_identity`。
- `protocol/consumers.py` `_handle_device_sync` → `_db_register_device`：其内部身份查找改调 `resolve_device_identity`（注意 `lookup_device_id_by_agent` 的 agent_device_id/path 前缀策略并入新模块的兜底）。

#### Task P2.1: registered_via 标记

- `DeviceRegisterView` 创建路径：`extra_info['registered_via'] = 'manual'`（现状已是 `'scan'` → 改 `'manual'`）。
- `_db_register_device` 创建路径：`extra_info['registered_via'] = 'agent'`。

#### Task P2.2: register 收敛（基础/个性化分离）

- `DeviceRegisterView`：基础字段（adb_serial/window_handle/emulator_brand/status/resolution）当新值有效且设备缺失时才更新（现状已大体如此，保持）；
  个性化字段（name/game_profile/screenshot_method/input_method/bindings）以请求为准更新。
- 不破坏现有 5 步兜底；agent 未发现时仍可手动创建（打 `manual` 标记）。

#### Task P3.1: 冲突仲裁测试

- 新增 `backend/workers/tests/test_device_identity.py`：
  - 同物理设备经两种 payload（sync 与 register）解析出同一 Device pk（不重复创建）；
  - sync 补全 serial/hwnd 不覆盖已保存的 name；
  - register 更新 name/绑定不覆盖 agent 上报的 status。
- 复跑 `pytest backend/workers backend/protocol`。

#### Task P4.1: 可选周期重扫（agent）

- `worker/src/__main__.py`：`GAF_AUTO_RESCAN_INTERVAL`（秒，默认 0=关闭）>0 时，启动一个定时线程周期执行 `DeviceCenter.auto_discover()` + `connection._sync_devices()`；0 时维持现状（仅 connect sync）。文档注 `worker/README` 或 `.env.example`。

#### Task P4.2: 文档同步

- `docs/architecture/overview.md`「概念速查」/发现章节补充 OQ-9 权威结论（agent WS sync 权威 + register 设置渠道 + 触发时机）；
- `docs/analysis/concept-naming-normalization.md` §9 OQ-9 行标 ✅（本 spec 完成时）。

## 5. 测试与验收

- `pytest backend/workers backend/protocol` 全绿；新增 `test_device_identity.py` 覆盖 P-1/P-2/P-3。
- grep：`DeviceRegisterView` 内不再有内联 5 步 dedup（改调 identity 模块）；`registered_via` ∈ {manual, agent}。
- 冒烟：本地起 backend+agent，connect 后设备列表自动出现（sync 路径，无手动注册）；ScanModal 手动注册同设备 → 更新而非重复创建。
- makemigrations --check clean（无模型字段变更，仅 extra_info dict 内容语义）。

## 6. 回滚

- 身份键模块为纯新增函数；两端接入为调用替换（git revert 恢复内联）。
- `registered_via` 为 extra_info dict 值语义，无迁移。周期重扫默认关闭，无运行时影响。