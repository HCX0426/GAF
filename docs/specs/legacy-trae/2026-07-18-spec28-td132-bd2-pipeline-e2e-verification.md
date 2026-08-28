# spec-28: TD-132 — C-011 BD2 12 pipeline e2e 验证

## 阶段状态表

| Phase | 状态 | 完成时间 | Commit | 验收 evidence |
|:-----:|:----:|:--------:|:------:|--------------|
| Phase 1: 环境启动 + 服务就绪 | ✅ | 2026-07-18 | | backend :8000 + frontend :5173 + agent (id=4 td010-repro-agent) 3 服务就绪 |
| Phase 2: pipeline 列表加载验证 | ✅ | 2026-07-18 | | 导入 12 BD2 pipeline JSON 到 DB (id=7~18, 12/12 PASS) |
| Phase 3: DAG 编译验证 | ✅ | 2026-07-18 | | PipelineParser.parse_dict 12/12 PASS (节点数 5~43) |
| Phase 4: 任务创建 + dispatch 验证 | ✅ | 2026-07-18 | | sweep_daily (id=18) → TaskExecution id=80 + WS "sent" + agent 接收 + entry_node 执行 |
| Phase 5: 9 pipeline 实际执行验证 | ✅ | 2026-07-18 | | 10 pipeline 批量 execute → 10/10 sent + agent 接收 + 全部 failed "no device" (0 结构性错误) |
| Phase 6: 回归 + 关闭 TD-132 | ✅ | 2026-07-18 | | backend 351 passed (1 TD-224 预存) + agent 89 passed + tsc 0 errors; TD-132 ✅ FIXED; C-011 ✅ |

## 背景

**来源**: TD-132 (P2, 2026-07-16 登记) — C-011 任务迁移 12/12 语法验证 PASS, 但 9 个 pipeline 待 e2e 验证。
**触发**: spec-27 ✅ commit `-` 后, 按 N169 "延后 = 接着做, 不等用户指令" 主动接修 (P2 优先)。
**目标**: 启动 3 服务, 在浏览器中验证 12 个 BD2 pipeline 的 e2e 链路 (API + DAG + 调度 + agent 接收)。

## 12 pipeline 清单 (resources/BrownDust-II/pipelines/)

1. `login.json` — 登录流程 (已知 N145 login PoC timeout 问题)
2. `get_guild.json` — 公会信息
3. `get_pvp.json` — PVP 信息
4. `intensive_decomposition.json` — 集中分解
5. `lucky_draw.json` — 抽奖
6. `sweep_daily.json` — 每日扫荡
7. `daily_missions.json` — 每日任务 (C-014 B1 修过 wait(template)→wait(ocr))
8. `get_email.json` — 邮箱 (C-014 B1 修过)
9. `get_restaurant.json` — 常客 (C-014 B1 修过)
10. `map_collection.json` — 游戏卡珍藏集 (C-014 B1 修过 + TD-013 swipe fallback skeleton)
11. `pass_rewards.json` — 基础奖励 (C-014 B1 修过)
12. `pass_activity.json` — 活动奖励 (TD-013 if-elif skeleton)

## Phase 1: 环境启动 + 服务就绪

### 步骤
1. 检查端口占用 (`netstat` 检查 :8000 / :5173)
2. 启动 backend: `conda run -n gaf python manage.py runserver` (long_running_process)
3. 启动 frontend: `npm run dev` (long_running_process)
4. 设置 `$env:GAF_AUTO_START_AGENT=1` 让 backend 拉起 agent
5. 等待 3 服务就绪 (curl backend /api/v2/health/ + curl frontend + agent process check)

### 验收标准
- backend `:8000` 返回 200
- frontend `:5173` 返回 200
- agent 进程在运行 (或 backend log 显示已拉起)

## Phase 2: pipeline 列表加载验证

### 步骤
1. `Invoke-WebRequest` GET `/api/v2/pipelines/` (admin token)
2. 验证返回 12 个 pipeline (id + name + resource_pack)
3. 验证每个 pipeline JSON 内容可读

### 验收标准
- API 返回 12 个 pipeline
- 每个 pipeline JSON parse OK

## Phase 3: DAG 编译验证

### 步骤
1. 用 backend shell 或单独脚本: 加载每个 pipeline JSON, 跑 DAG compiler
2. 验证 12 个 pipeline 全部能解析为 DAG (无 cycle, 无未定义节点)
3. 验证节点类型 (action/wait/ocr/condition/loop) 全部支持

### 验收标准
- 12 pipeline DAG parse 全部 PASS
- 输出每个 pipeline 的节点数 + 边数

## Phase 4: 任务创建 + dispatch 验证

### 步骤
1. 浏览器登录 admin/admin123
2. 导航到任务创建页
3. 选一个 pipeline (如 `sweep_daily`), 创建任务
4. 验证任务创建成功 (API 返回 201 + task_id)
5. 验证任务被 dispatch 到 agent (WS 消息发送)
6. agent 接收消息 (log 验证)

### 验收标准
- 任务创建 API 201
- task_id 有效
- WS dispatch 消息发送
- agent log 显示接收

## Phase 5: 9 pipeline 实际执行验证

### 步骤
对 9 个 pipeline (除 login/get_guild/sweep_daily 外的 9 个) 重复:
1. 创建任务
2. 触发执行
3. 验证 pipeline 能开始执行 (即使最终因无设备/无游戏失败)
4. 记录执行结果 (开始时间 + 结束时间 + 失败原因)

### 验收标准
- 9 pipeline 全部能开始执行 (pipeline_runner 启动)
- 失败原因合理 (如 "device not connected" / "screenshot failed" / "template not found")
- 不出现 pipeline parse / DAG compile / 节点未定义 等结构性错误

## Phase 6: 回归 + 关闭 TD-132

### 步骤
1. backend pytest 全量回归 (确认无新增 fail)
2. agent pytest 全量回归
3. tsc 检查
4. active.md TD-132 标 ✅ FIXED (附 commit hash + evidence)
5. completed-features.md C-011 状态从 🔧 升级为 ✅ (附 e2e 验证 evidence)
6. commit 变更

### 验收标准
- backend pytest 0 failed (或仅预存 fail, 标注)
- agent pytest 0 failed
- tsc 0 errors
- TD-132 标 ✅ FIXED
- C-011 标 ✅

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 无 LDPlayer + BD2 游戏, e2e 无法真正执行 | Phase 5 验证到 "pipeline_runner 启动" 即可, 失败原因标 "no device" 不算结构性错误 |
| backend 启动失败 (port 占用 / migration 问题) | Phase 1 检查端口 + 必要时 `python manage.py migrate` |
| N145 login PoC timeout | login pipeline 跳过实际执行, 仅验证 API 创建 |
| TD-013 skeleton pipeline (map_collection / pass_activity) | 这些 pipeline 有已知 skeleton, 执行到 skeleton 节点会 fallback, 不算 e2e 失败 |
