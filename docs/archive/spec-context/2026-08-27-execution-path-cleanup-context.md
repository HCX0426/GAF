---
summary: 执行路径清理与归一化 — 僵尸接口/假功能删除 + TaskChain 派发收敛 dispatch_task
id: 2026-08-27-execution-path-cleanup
applies_to: ['backend', 'frontend', 'architecture']
created: 2026-08-27
status: completed
scale: big
---

# Spec Context: 执行路径清理与归一化

## 用户决策

- 用户要求"检查任务执行路径是否有冗余 + 是否测试通过"，随后明确指示"**都修吧，架构方向优先**"
- 用户质疑维度判断缺失 → 触发 N151 + N167 评估并落盘本文件
- A1 涉及 API 删除（`/api/v2/tasks/execute/{id}/`）：无调用方（前端零引用、零测试），用户已授权"都修"→ 自决删除

## N151 大修改架构评估（5 步）

1. **架构盘点**: 执行入口 6 类（Task/Pipeline/TaskChain/Skill/无人值守/命令行）+ 自动恢复 3 机制；架构文档权威定义见
   `docs/business/tasks/execution-reality.md`（v2.1 执行入口统一到 dispatch_task）+ `docs/architecture/cross-cutting/dispatch-flow.md`
2. **识别反模式**:
   - A1: `TaskExecuteView` 伪执行接口（只算 plan 不 dispatch，违背 v2.1 "统一走 dispatch_task" 决策）
   - A2: 前端单节点调试入口调后端不存在的路由（必然 404 假功能）
   - A3: `run_pipeline` 独立 agent/device 解析（与 view/service 重复）
   - B1: `dispatch_chain_node` 手写第二套 `task.assign` payload（文档声明统一入口实际双套）
   - B2: `_get_online_agent` / task_service / run_pipeline 三处 agent 选择逻辑重复
3. **A/B/C 备选**:
   - 方案 A（收敛统一，采用）: 删僵尸/假功能 + 提取 resolve_online_agent + dispatch_task 加 force_agent_id 收敛 chain
   - 方案 B（最小删除）: 只删 A1/A2，B 类登记 TD
   - 方案 C: 仅文档说明（不满足"架构方向优先"）
4. **七维度评分**: 见下表（N167）
5. **KEEP 合法**: `execution_planner.py` 曾保留（独立单测引用）；**2026-08-27 用户推翻**——仅测试引用 ≠ 生产价值，判定为死代码，已删除 `execution_planner.py` + `test_execution_flow.py` 相关 4 用例；自动恢复 3 机制为架构组件不删

## N167 七维度评分

| 维度 | A（收敛统一） | B（最小删除） | 理由 |
|:---:|:---:|:---:|------|
| 1 架构长远性 | 5 | 2 | A 消除双套派发协议，未来改动集中在 dispatch_task |
| 2 全局归一化 | 5 | 3 | A 三处 agent 解析合一 + payload 单源 |
| 3 新旧兼容 | 5 | 5 | 单人项目一次性切换 |
| 4 现有业务完善 | 5 | 3 | A 让 chain 获得设备串行/并发/ACK/debug 目录兜底 |
| 5 性能资源优化 | 4 | 4 | 非性能专项；A 消除重复 agent 查询与目录构建；无 N+1 引入 |
| 6 安全合规加固 | 5 | 3 | 删除伪执行 API + 假入口缩小攻击面；force_agent_id 仅 Celery 内部调用、仍校验 agent 状态 |
| 7 长期维护成本 | 5 | 3 | payload 单源 + 文档与代码一致 + 测试集中 |
| **总分** | **34/35** | **23/35** | A 领先 11 ≥ 5 → 自决 |

**反向论证（为何不选 B）**:
1. B 保留双套 payload —— dispatch_task 扩字段时 chain 属性 drift（外部事实: spec-2026-08-02 已发生过声明与实现漂移）
2. B 不产生 chain 卡 RUNNING 的修复价值（外部事实: TD-402 暴露过 chain 派发缺 ack 导致永久 RUNNING）
3. B 保留用户点击即 404 的假入口（外部事实: 单节点菜单存在于 UI）

**硬场景 ③ 业务语义判定**: "影响数据保留/业务流程？" → N（删除的 API 无调用方；force_agent_id 为可选参数；chain 语义为增强）→ 可自决，无需 AskUserQuestion。

## 关键决策

1. `dispatch_task` 新增可选参数 `force_agent_id`：非 None 时跳过 AgentSelector，校验 agent 状态（ONLINE/IDLE/BUSY 可派发，OFFLINE 拒绝）后直接派发；retry kwargs 同步透传
2. chain 的 `_dispatch_task_node`/`_dispatch_pipeline_node` 改为: 创建 PENDING execution（绑定 agent/device/game_account/chain FK）→ `dispatch_task.delay(force_agent_id)`；删除 `_send_task_assign`/`_build_device_info_for_device` 双套实现
3. 新增 `tasks/services/agent_resolver.py::resolve_online_agent` 统一三处 agent 选择语义（显式 agent 校验 + 自动选最新心跳在线 agent）
4. 删除 `TaskExecuteView`（含路由）+ 前端单节点测试入口 + 4 处 unused i18n keys + api.generated.ts 旧端点类型
5. 文档同步: dispatch-flow.md 新增 §2.5 chain 归一化；execution-reality.md Backend 入口行补充 chain/force_agent_id；data-flow.md 移除 TaskExecuteView

## 验证

- ruff 全量: backend/tasks + backend/pipeline 0 errors
- pytest: scheduler 539 + tasks/pipeline 全量 + integration 213 共 **539 passed, 2 skipped**（3 次运行全绿）
- eslint 改动文件 0 errors；tsc 全量通过；prettier 全量格式一致

## 用时

- start_ts: 2026-08-27 （会话内连续）
- 规模对照: 16 文件 +200/-480 行（中-大修改区间），主导删除，符合方案 A 预期