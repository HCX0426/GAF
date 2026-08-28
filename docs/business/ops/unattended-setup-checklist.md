---
summary: 从零配置到无人值守循环挂机（多号轮换活动脚本）可复用检查清单 — GameProfile/TaskChain/账户/轮换/设备/会话 6 步
applies_to: [project, backend, frontend, agent]
last_updated: 2026-08-26
---

# 无人值守循环挂机 — 从零准备检查清单

> **目标场景**: 个人在多号小号上循环跑"简单活动脚本（重复点击）"，无人值守、自动轮换。
> **适用版本**: 2026-08-26 之后（含 `loop_rotation` 循环轮换 + 轮换规则 UI 对齐后端契约）。
> **快速定位**: 本文是基于真实代码契约核对过的配置顺序；遇到失败先看 §5 失败模式表。

## 0. 30 秒理解架构挂点

GAF 采用 Window-centric 资源树：**GameProfile（游戏档案）** 下挂 5 类子资源（Device / GameAccount / Task / TaskChain / ResourcePack）。
无人值守派发的**关键挂点**:

```
device.game_profile.default_routine   ← tick/启动时派发的是"设备的默认任务链"
session.rotation_rule                 ← 轮换：选下一个未派发账户
session.loop_rotation=True            ← 循环：链完成后账户归还池子，持续下一轮
```

👉 所以配置顺序必须先有 GameProfile，一切（设备绑定、默认链、账户归属）都挂在它下面。

## 1. 六步检查清单（按顺序，每项含通过标准）

### STEP 1 — 游戏档案 GameProfile
- [ ] 创建 GameProfile（前端顶层菜单 `/game-profiles`，已提升为一级菜单）
- [ ] 建议设置 `device_type_hint=emulator`（活动手游几乎都跑模拟器）
- [ ] （多运行模式时）确认截图/输入/控制模式；ADB 控制不依赖窗口前台，最小化也能跑
- 通过标准: 档案可打开，5 个子资源 Tab 可见

### STEP 2 — 任务链 TaskChain + 默认任务链
- [ ] 录制一遍活动流程（或手搭 Pipeline 重复点击节点）→ 生成 Pipeline
- [ ] 新建 TaskChain，把 Pipeline 节点加入链（`chain_nodes` 至少 1 个）
- [ ] **链 `is_enabled=True`**（否则所有设备被静默跳过！）
- [ ] 回 GameProfile 设置 `default_routine=该链`
- 通过标准: Profile 详情页 default_routine 有值；链列表 is_enabled 显示启用

### STEP 3 — 游戏账户 GameAccount
- [ ] 创建 N 个账户（建议先用可牺牲的小号，别挂唯一大号）
- [ ] 必填: `username` / `encrypted_password`（AES-256-GCM 自动加密）/ `server_region` / `login_method` / `status`（建议置 `ok`，默认 `unknown`；轮换仅跳过 `error`）
- [ ] 失效/封号账户把 `status` 改为 `error`（轮换 `auto_skip_blocked` 自动跳过）
- 通过标准: 账户列表无红状态；可测试登录通过

### STEP 4 — 轮换规则 RotationRule
- [ ] 账户页 → 轮换规则 → 新建
- [ ] `rotation_strategy`: `sequential`（顺序循环最常用）/ `random` / `by_stamina` / `by_last_executed`
- [ ] `accounts` **至少选 1 个账户**（后端校验，少选直接 400）
- [ ] `switch_interval_seconds`（秒，默认 10）、`auto_skip_blocked=True`
- 通过标准: 规则保存成功；列表含所选账户数量

### STEP 5 — 设备（多开模拟器）
- [ ] 雷电多开启动 N 个窗口；Agent 在线 → 自动发现注册为 Device
- [ ] 每个设备绑定 `game_profile`（tick 只派发 `profile.default_routine` 的设备）
- [ ] 确认设备 status=online 且 agent 在线（心跳 10s）
- 通过标准: 设备中心显示在线设备，且已绑 profile

### STEP 6 — 无人值守会话 + 预检
- [ ] `/ops/unattended` 启动区: 选 GameProfile
- [ ] **选「轮换规则」**（STEP 4 建的）+ 开 **「循环轮换」开关**（TD-400）
- [ ] 建议先配: 时间窗口 / 自动停止条件（`consecutive_failures` 阈值）/ 通知渠道
- [ ] 跑 **Preflight 5 项**: device_online / account_valid / resource_ready / agent_connection / scheduler_rules
- [ ] **先 1 号 1 轮试跑** → 确认链条完整走通 → 再开全量循环
- 通过标准: Preflight 无 fail；会话 RUNNING；执行队列有派发记录

## 2. 字段契约速查（与代码一致）

| 对象 | 关键字段 | 约束 |
|------|---------|------|
| GameProfile | `default_routine` FK→TaskChain, `device_type_hint` | 无默认链的设备不参与派发 |
| TaskChain | `is_enabled` | False = 静默跳过 |
| GameAccount | `username/encrypted_password/server_region/login_method/status` | status=error 会被轮换跳过 |
| GameAccountRotation | `rotation_strategy`(4值) / `switch_interval_seconds`(秒) / `accounts`(M2M, ≥1) / `auto_skip_blocked` / `is_active` | 前端已对齐，无 `weighted` |
| UnattendedSession(启动参数) | `game_profile_id`（必填）+ `rotation_rule_id?` + `loop_rotation?` | 同 profile 仅一个 RUNNING/PAUSED |
| AutoStopCondition | `condition_type`(consecutive_failures/device_offline/all_completed/window_end/manual_stop/resource_insufficient) | **循环模式不触发 all_completed** |

> 轮换/无人值守更多细节: [ops/scheduler.md](./scheduler.md) · [accounts/accounts.md](../accounts/accounts.md) · [game-profiles.md](../game-profiles/game-profiles.md)

## 3. 维护节奏

| 频率 | 事项 |
|------|------|
| 游戏活动更新 | **重录活动页面改动的点击路径**（主要维护成本） |
| 每次挂机前 | Preflight + 1 号 1 轮试跑 |
| 周/半月 | 检查 `consecutive_failures` 停止是否被触发过、账户状态、通知渠道通畅 |
| 账号变动 | 新号进轮换规则；封号改 status=error |
| 版本/故障后 | 设备健康检查、模拟器升级后重绑、磁盘（截图/日志自动归档） |

## 4. 常见失败模式

| # | 现象 | 根因 | 排查 |
|---|------|------|------|
| 1 | 挂机无任何派发 | Profile 缺 `default_routine` 或链 `is_enabled=False` | STEP 2 |
| 2 | 会话启动 400 | 轮换规则未选账户；或同 profile 已有 RUNNING | STEP 4 / 现状 |
| 3 | 部分号不跑 | 设备未绑 profile / 不在线 | STEP 5 |
| 4 | 跑一轮就停 | session 未开 `loop_rotation`（或误配 all_completed 期望停） | STEP 6 |
| 5 | 循环挂了无感知 | 无通知渠道 / consecutive_failures 阈值过大 | 监控配置 |

## 5. 参考

- 架构: [docs/architecture/overview.md](../../architecture/overview.md)
- 无人值守: [docs/business/ops/scheduler.md](./scheduler.md)
- 账户/轮换: [docs/business/accounts/accounts.md](../accounts/accounts.md)
- Pipeline 编辑: [docs/business/tasks/pipeline-authoring-guide.md](../tasks/pipeline-authoring-guide.md)