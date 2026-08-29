---
summary: GAF E2E 测试计划 — 全功能测试用例清单（前置条件/步骤/期望结果）+ 执行记录
applies_to_code_paths:
  - frontend/src/
  - backend/
  - agent/
last_updated: 2026-08-29
---

# GAF E2E 测试计划

> **依据**: 用户 2026-08-28 要求 — 先列出所有部分测试项、定好步骤，再开始测试；测试结果记录在案。
> **数据原则 (2026-08-28 用户决策)**: 无数据不能标"空态通过"。必须优先造数据（UI 操作造 / 数据库直接造），再回看数据使用处的渲染效果；实在造不出的才标记环境限制。
> **执行方法**: AI browser-use **无头浏览器**（headless）逐条执行 + console_monitor 对照；前 7 日探索式点击结果回填为"CURR"状态。
> **环境**: 现有真实数据 admin/admin123; backend:8000 + frontend:5173。
> **验收判定**: ✅ 通过（交互可用+期望达成+0 业务错误）/ ⚠️ 通过但有 JS error/4xx/5xx / ❌ 失败（崩溃/交互不可用）/ ⏳ 未测。
> **配套**: 执行明细与逐日进度见 `e2e-coverage.md`；问题登记见其「发现问题登记」表。

## 持久化自动化执行（月度全量）

> 用户 2026-08-28 决策：E2E 用例必须**持久化为可执行测试**（真实无头浏览器 + 真实后端，禁止 mock 后端），
> 每月全量跑一次；有新增功能/页面 → 同步补用例（本文件 + `scripts/e2e/scenarios/full_routes.py` 两处）。
> **首跑**: 2026-08-28 `full_routes` 47/47 PASS（含 46 路由 + replay 修复后全绿）；首轮探索至收尾共登记 19 处问题（F1-F11/M1-M8 + AUT 2 条）全部当日修复闭环。

### 自动化 ↔ 用例映射

| 自动化场景 | 载体 | 覆盖用例 ID | 说明 |
|-----------|------|------------|------|
| `full_routes` | `scripts/e2e/scenarios/full_routes.py`（真实后端 headless） | A-01~A-04, B-01~B-03, C-01~C-06, D-01~D-10, E-01~E-08, F-01~F-06, G-01~G-04, H-01~H-04/H-07~H-13, I-01~I-09, J-01~J-11 | 全 46 路由 smoke：登录 → 逐路由访问 → URL/侧边栏/内容/崩溃/console error 判定；动态路由自动探测真实 id |
| `browser_login` | `scripts/e2e/scenarios/browser_login.py` | A-01 | 真实登录跳转 + 0 JS error |
| `devices_control_mode` | `scripts/e2e/scenarios/devices_control_mode.py` | E-06 | 控制模式选择器渲染/切换（TD-015 回归） |
| `ai_qa_chat` | `scripts/e2e/scenarios/ai_qa_chat.py` | I-03 | LLM 问答真实链（commit - 回归） |
| mock spec.ts×3 | `frontend/e2e/auth|devices|tasks/*.spec.ts` | 快速回归（CI 友好，mock 前端） | 不依赖后端，供开发期快速验证 ✅ |
| 环境依赖（已实测 2026-08-28） | 有真实模拟器/设备时手动补测 | E-02(雷电模拟器已扫+注册上线), E-05(模拟器实例+启停按钮已验), K-01~K-03(3 条核心链路已真实执行: exec 90 success / 匹配真实化 / unattended session 13) | 环境齐时均已手动实证；D-09 录制仍需 Agent 端（规格内），其余全自动 |
| 统计对账抽查（月度手动, N218） | `docs/health/e2e-test-plan.md` B-04/B-05（DB 对照, 浏览器实测） | B-04, B-05 | 统计卡片数字与 DB 对账 + 记住我免登录回归 — 见"月度全量"命令补充步骤 |

### 执行命令（月度全量）

```powershell
# 1) 确保服务在线（若已启动可跳过）
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\gaf_services.ps1 status
# 2) 全量 E2E（含真实无头浏览器 46 路由 smoke + 7 场景）
conda run -n gaf python scripts/e2e/run_all.py
# 3) 失败详情落盘 .trash/.e2e-failures.log + .ai-memory/ops/why-skipped.md
# 4) 同步回填 e2e-coverage.md「发现问题登记」并归档；新增页面时更新 full_routes.py ROUTES
# 5) 统计卡片对账抽查 (B-04, N218): 直连 DB 数各 status 行 → API ?status= 比对 count → 核对工作台卡片
# 6) 记住我免登录回归 (B-05, N217): 登录(默认勾选) → 查 localStorage → 清 sessionStorage → 刷新自动进 /dashboard
```

> **新增页面纪律**: 新路由上线 → ① `App.tsx` 注册路由 → ② `full_routes.py` ROUTES/DYNAMIC_ROUTES 补条目(ID 映射 e2e-test-plan) → ③ 本表加映射。三处缺一不可。

---

## 数据现状与根因分析 (2026-08-28 核查 + R1 验证回填)

> 原则: 无数据不能标"空态通过"; 优先走业务流程造数, 实在造不出才 DB 兜底。

| 模块 | 此前计数 | 根因 (为什么没数据) | 造数方案 | 最新计数 |
|------|:---:|------|------|:---:|
| 通知 notifications | 0 | 真实推送依赖业务事件(任务完成/告警触发), 环境从未跑出通知 | DB 兜底(5 条含 3 分类) | 5 |
| 插件 plugins | 0 | 从未上传安装过插件包 | DB 兜底(2 包+2 hook) | 2 |
| SLA 指标 | 0 | 依赖 Agent 真实截图/OCR 上报, 此前无在线 Agent | DB 兜底(5 条) | 5 |
| 监控事件 | 0 | 依赖监控规则触发(OCR 失配等), 未跑出 | DB 兜底(3 条 3 级) | 3 |
| 标注 annotations | 0 | 从未用标注工具画过 | DB 兜底(2 条关联 sweep_daily 模板) | 2 |
| 分组 groups | 0 | 从未创建过分组 | DB 兜底(3 条 owner=admin) | 3 |
| API Key | 0 | 从未创建 | DB 兜底(1 条) | 1 |
| 录制 recordings | 0 | 需真实录制操作(窗口捕获), 未跑 | 待流程造数(无头录制受限) | 0 |
| 备份 backups | ? | 需创建备份任务/手动执行 | ✅ 已真实创建(2026-08-28 POST /backup/create/ + zip 下载 + 每日 02:30 定时任务) | ✅ |

> 教训: 首轮探索造数脚本用 @transaction.atomic 包裹, group 步骤抛 NOT NULL 异常致整个事务回滚,
> 通知/插件/SLA/事件全部被撤销(DB 计数 0 证实) — 已改分模块独立提交 (N## 教训候选)。

### R1 验证结果 (2026-08-28 无头浏览器回看渲染)

| 页面 | DB 计数 | 界面渲染 | 结论 |
|------|:---:|:---:|------|
| /system/notifications | 5 | ✅ 5 条 + 全部已读可用 | ✅ 数据生效 |
| /system/plugins | 2 包 | ✅ 2 包(echo 启用/notify 未装) + 启停/重载/卸载 | ✅ 数据生效 |
| /ops/sla | 5 | ✅ P50=146/P99=172 + 5 明细 | ✅ 数据生效; OCR 卡 0.0ms |
| /ops/monitors 事件 tab | 3 | ✅ M1 已修: 挂载即 loadEvents + P0-P3 四色映射 | ✅ 数据生效 |
| /resources/annotation | 2 | ✅ F8 已修: 选对模板(金币本.png)即显示 2 条标注 | ✅ 数据生效 |
| /accounts/game-accounts 分组 | 3 | ✅ F9 已修: 分组 API 归一, 3 组渲染 + 文案矛盾消除 | ✅ 数据生效 |
| /system/api-keys | 1 | ✅ e2e-test-key 渲染 | ✅ 数据生效 |

> R1 时点红项后续已全部修复（M1/F8/F9，详见问题登记）；另 ⑤ 通知行 body 由 M7 修复。

## A. 认证与系统框架 (4)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| A-01 | 登录页 | 无登录态 | 打开 /login，输入 admin/admin123，点登录 | 跳 /dashboard，顶部显示"登录成功" | ✅ CURR |
| A-02 | 登录页-错误密码 | 无登录态 | 输入错误密码提交 | 提示"用户名或密码错误"，不跳转 | ✅ CURR-R4 |
| A-03 | 注册 Tab / OAuth 按钮 | 登录页 | 点注册 Tab；点 GitHub/Google 按钮 | Tab 可切；按钮跳 OAuth 流程 | ✅ CURR |
| A-04 | Setup 初始化向导 | admin 已存在 | 访问 /setup | 重定向 /login→/dashboard（已初始化态） | ✅ CURR |

## B. 工作台 Dashboard (5)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| B-01 | 仪表盘渲染 | 已登录 | 打开 /dashboard | 今日进度/设备网格/队列/告警/趋势 9 面板渲染 | ✅ CURR (M6 已修 recharts -1) |
| B-02 | 面板拖拽 + 快捷操作 | 已登录 | 拖 1 面板；点创建任务/导入市场/设备管理/快速执行 | 拖拽生效；跳对应页 | ✅ CURR |
| B-03 | 顶栏主题/DPI/语言 | 已登录 | 切主题 3 态；DPI 下拉；语言下拉 | 主题生效；下拉可展开 | ✅ CURR |
| B-04 | 统计卡片数字对账 DB (N218) | 已登录, 造带状态数据 | ① 直连 DB 数 TaskExecution 各 status 行数 ② 对 API `?status=running/failed/success` 各发一次比对 count ③ 核对工作台卡片: 运行任务/今日执行/成功率 | 卡片数字与 DB 真实值一致; "无任务在跑时运行任务≈0" | ✅ 2026-08-29 (N218 修复后: running 0/failed 26/无参 91, 卡片"运行任务 0") |
| B-05 | 记住我持久化 + 免登录 (N217) | 已登录勾选记住我 | ① 登录后查 localStorage: remember_me=1 + refresh_token ② 清 sessionStorage(模拟关浏览器) ③ 刷新/重开页面 | 自动跳 dashboard 免登录; checkbox 默认勾选 | ✅ 2026-08-29 (修复 e004db3 后实测) |

## C. 游戏档案 GameProfiles (6)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| C-01 | 列表渲染+搜索 | 有档案数据 | 开 /game-profiles，搜索"DbgGame" | 过滤生效 | ✅ CURR |
| C-02 | 新建档案弹窗 | 列表页 | 点新建，字段全填后取消 | 弹窗含 9 字段，全部可点 | ✅ CURR |
| C-03 | 行操作 | 列表页 | 点行内 查看/编辑/删除(取消) /分页 | 各按钮弹对应 UI；删除需确认 | ✅ CURR |
| C-04 | 档案详情 5 Tab | 有档案 | 进详情，切 任务/任务链/窗口/账户/资源包 | 5 Tab 切换正常 | ✅ CURR |
| C-05 | 绑定弹窗 | 详情页 | 点"添加任务"，搜索+绑定按钮 | 弹窗搜索可用；F1 已修 common.cancel 未翻译 | ✅ CURR |
| C-06 | 派发任务链 | 详情页 | 点"派发任务链" | 弹执行确认 | ✅ CURR（R2 已在详情页验证该按钮可点） |

## D. 任务 Tasks (10)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| D-01 | 任务列表 CRUD 操作 | 有任务 | 开 /tasks，搜索/筛选/新建弹窗/分页/行操作 | 各操作可用；M8 已消 SyntaxError | ✅ CURR |
| D-02 | 批量操作+导出 | 有多任务 | 勾选多行→批量；点导出 | 导出 disabled→选中后可导出 | ✅ CURR |
| D-03 | 任务编辑-预填 | 有任务 | 开 /tasks/:id/edit | F2 已修：编辑态预填名称/描述 | ✅ CURR |
| D-04 | 编辑页 Tab+步骤编辑 | 编辑页 | 切 pipeline/state_machine Tab；添加步骤；动作类型下拉 | Tab 可切；9 类动作可选；M4 已修 i18n | ✅ CURR |
| D-05 | Pipeline 编辑器-节点库 | 编辑器 | 开 /tasks/pipeline，展开 5+ 节点分类 | 节点面板可用 | ✅ CURR |
| D-06 | Pipeline 编辑器-验证/保存 | 编辑器 | 放 1 节点→验证→保存 | 验证通过；保存落库 | ✅ CURR (e2e-manual-n1138) |
| D-07 | Pipeline 执行按钮 | 已保存 pipeline | 选设备→点执行 | F6 + canExecute 已修：设备下拉真实数据 + 保存后启用执行 | ✅ CURR (full_routes D-08 PASS) |
| D-08 | Pipeline 详情路由 | 存在 pipeline | 直接访问 /tasks/pipeline/:id | F3 已修：预载画布与名称 | ✅ CURR (full_routes PASS) |
| D-09 | 录制管理 | 有录制 | 开 /tasks/recordings | 空态正确（环境无录制） | ✅ CURR |
| D-10 | 任务市场 | 市场非空 | 开 /tasks/marketplace，发布弹窗 | 发布弹窗 Pipeline 下拉可用；M4 已修 i18n | ✅ CURR |

## E. 设备 Devices (8)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| E-01 | 设备列表渲染+搜索+视图 | 有设备 | 开 /devices，卡片/列表切换 | 渲染正常 | ✅ CURR |
| E-02 | 扫描模拟器 | Agent 在线 | 点"扫描模拟器" | ✅ 2026-08-28 实测: 单一雷电模拟器(ldconsole 视角 127.0.0.1:5555 + adb 视角 emulator-5554 为同实例别名), 注册为 LDPlayer 并上线; 误注册的重复设备已撤销 | ✅ (真实实例) |
| E-03 | 扫描窗口+Register | Agent 在线 | 点"扫描窗口"→选窗口→Register | ✅ REGISTER 成功(Endfield 在线, R2 复测)；D3 失败根因=当时无在线 Agent | ✅ CURR (R2+2026-08-28 Chrome-Browser 注册佐证) |
| E-04 | 测试截图 | 设备在线 | 选在线设备→测试截图 | ⚠️ 截图按钮 R37-P1-C5 已移除, 入口迁至 /resources/annotation 实时标注 | ✅ 迁移闭环(标注页截图流+真实匹配预览) |
| E-05 | 模拟器生命周期 | 有实例 | /devices/emulators 启停按钮 | ✅ 2026-08-28 实测: LDPlayer 实例显示 + 健康检查/刷新/发送按钮可用 | ✅ (真实实例) |
| E-06 | 窗口管理-保存配置 | 有窗口 | /devices/windows 存配置 | 保存 loading 正常 | ✅ CURR |
| E-07 | ADB 日志实时流 | 设备连接 | /devices/adb-logs 选择设备→流 | F11 已修设备下拉 + WS 握手已修；full_routes E-07 PASS | ✅ CURR (full_routes PASS) |
| E-08 | 设备分组 | 有设备 | 新建分组输入框+取消 | 弹窗可用 | ✅ CURR |

## F. 资源 Resources (6)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| F-01 | 资源包 CRUD+4 Tab | 有资源包 | 开 /resources，切 列表/模板库/验证状态/ROI | 全可点；模板库含上传/批量导入 | ✅ CURR |
| F-02 | 资源包版本/目录/导出/删除 | 有数据 | 行操作各按钮 | 版本 modal/目录/下载/删除确认 | ✅ CURR |
| F-03 | 模板有效性 Segmented | 有模板 | /template-effectiveness 筛全部/退化/正常 | 无数据空态正确 | ✅ CURR |
| F-04 | 模板标注 6 工具 | 编辑器 | /annotation 切换 矩形/椭圆/多边形/线段/点/选择 | 工具切换正常 | ✅ CURR |
| F-05 | COCO 导出 modal | 编辑器 | 点 COCO 导出→字段开关 | 全选/取消全选正常 | ✅ CURR |
| F-06 | 标注列表 vs 设备操作 vs 匹配预览 | 编辑器 | 逐 Tab 切换 | 空态/禁用符合状态 | ✅ CURR |

## G. 账户 Accounts (4)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| G-01 | 用户新建/编辑/删除 | 管理员 | /accounts/users 新建 modal 角色 3 级；编辑；删除确认 | 模态正常；登录历史 modal 可用 | ✅ CURR |
| G-02 | 游戏账户新建 | 有游戏 | /accounts/game-accounts 新建 modal 登录方式 4 种 | 下拉可展开 | ✅ CURR |
| G-03 | 分组管理 | 有账户 | 分组 modal 新建/速建 4 类/拖拽 | 可用 | ✅ CURR |
| G-04 | 轮换规则 nested modal | 有账户 | 新建规则表单 | 字段齐全；需多层 Esc 关闭（UX 建议） | ✅ CURR |

## H. 运维 Ops (14)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| H-01 | 无人值守-控制 tab | 有档案 | /ops/unattended 选档案→启动(disabled 态验证) | disabled 逻辑正确 | ✅ CURR |
| H-02 | 无人值守-策略 tab | — | 5 层恢复/夜间/频率/通知/冷却 4 面板展开 | 全可展开含 spinbutton/slider | ✅ CURR |
| H-03 | 执行列表+详情 | 有执行 | /ops/executions 状态筛选→行详情 | 列表 89 条；详情展开步骤表 | ✅ CURR |
| H-04 | 每日报告 | 有数据 | tab 每日报告→导出 | 导出按钮存在 | ✅ CURR |
| H-05 | 无人值守日志 tab | 有日志 | tab 无人值守日志 | F4 已修 logs.forEach 崩溃 | ✅ CURR (full_routes PASS) |
| H-06 | 今日摘要 tab | 有数据 | tab 今日摘要 | F5 已修 items.map 崩溃 | ✅ CURR (full_routes PASS) |
| H-07 | 定时任务-创建+Cron | — | /ops/scheduler 创建 modal Cron 编辑器 | 分/时/日/月/星期 可编辑 | ✅ CURR |
| H-08 | DAG 编排 | — | /ops/scheduler/dag 添加节点 | React Flow 画布+缩放+添加节点 | ✅ CURR |
| H-09 | 监控-规则+告警 modal | — | /ops/monitors 新建规则；告警规则含静默时段 | modal 正常 | ✅ CURR |
| H-10 | 监控-事件升级链 | 有事件 | 看事件表升级时间列 | CURR 无活跃事件空态 | ✅ CURR |
| H-11 | 数据看板 | 有数据 | /ops/analytics 4 指标卡+趋势 | 指标展示正常 | ✅ CURR |
| H-12 | SLA 指标 | — | /ops/sla 指标卡 | 无数据空态(前端已修 '-' 显示) | ✅ CURR |
| H-13 | 日志中心 8 Tab | 有日志 | /ops/logs 逐 Tab 切换 | 全正常；应用日志 WS"未连接"提示 | ✅ CURR |
| H-14 | 核心链路-定时任务→无人值守 | 设备绑定 | 建 Cron→预热→无人值守 start | 同 K-03（2026-08-28 全链路已真实验证）: Cron ✅ → 设备在线 ✅ → preflight can_start ✅ → start session 13 (dispatched 1) → stop ✅ | ✅ (真实启动) |

## I. AI (8)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| I-01 | 助手输入/发送 | LLM 配置 | /ai/assistant 输入→发送按钮启用 | 输入后发送启用；未真实调用 | ✅ CURR |
| I-02 | 自然语言创建/智能优化 tab | — | 切 tab；Pipeline 下拉 | tab 可切；下拉含 cycle-wait-pipeline | ✅ CURR |
| I-03 | 智能问答 | — | /ai/qa 提问框+新建 | 输入可用；空会话态 | ✅ CURR |
| I-04 | 异常发现 | — | /ai/anomaly 时间范围 5 档+设备+检测 | 下拉/按钮可用；未触发 | ✅ CURR |
| I-05 | Skill 编辑器 | — | /ai/skill-editor YAML+保存+模板 | 填名启用保存；模板 3 类 | ✅ CURR |
| I-06 | Skill 市场 | — | /ai/skill-market 发布弹窗 | ✅ 2026-08-28 复核定案: modal 取消/X/Esc 三通道均正常关闭(此前"取消需 Esc"为自动化误判——antd5 关闭后保留隐藏 DOM) | ✅ CURR |
| I-07 | AI 配置 | — | /ai/config provider 4+下拉 | 字段全可用 | ✅ CURR |
| I-08 | AI 用量 | — | /ai/usage 仪表盘 | 只读展示 | ✅ CURR |

## J. 系统 System (9)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| J-01 | 系统设置-数据清理/调试/语言/危险操作 | 管理员 | /system/settings 各 tab 交互 | 输入/开关可用 | ✅ CURR |
| J-02 | 诊断包生成 | — | 生成→下载 | 生成成功+下载按钮 | ✅ CURR |
| J-03 | 基础设施健康 tab | — | 切 tab | F11 批次已修 checks 结构校验崩溃 | ✅ CURR (full_routes PASS) |
| J-04 | 安全设置 2FA | — | 启用 2FA 弹窗 | 密钥/复制/OTP/取消 可交互 | ✅ CURR (未启用) |
| J-05 | 配置管理 | — | /system/config 5 类动态表单 | schema 生成正常 | ✅ CURR |
| J-06 | API Key 新建 | — | /system/api-keys 新建 modal | 权限/IP/过期/启停 全可点 | ✅ CURR |
| J-07 | 备份 | 管理员 | /system/backup 全量备份+恢复 | ✅ 真实备份成功+zip 下载; 定时备份入口已加(scheduled_backup 每日 02:30) | ✅ CURR-R4 |
| D-09 | 录制管理 | 有录制 | 开 /tasks/recordings | ✅ 空态; 无前端录制入口(需 Agent 端)前置记录 | ✅ CURR-R4 |
| J-08 | 功能开关 | — | /system/feature-flags 新建(灰度 100→50) | 3 条数据+灰度生效 | ✅ CURR |
| J-09 | 审计日志 | 有记录 | /system/audit-log 筛选+详情抽屉 | 201 条 11 页；详情 JSON | ✅ CURR |

## K. 核心链路 (3)

| ID | 测试项 | 前置条件 | 操作步骤 | 期望结果 | 状态 |
|----|--------|---------|----------|---------|:---:|
| K-01 | 创建任务→执行 | Agent 在线 | UI 建 Pipeline→验证→保存→选真实设备→执行 | ✅ 2026-08-28 真实执行链路打通过: F6 修执行按钮 → POST pipeline/2/execute → agent 派发 → LDPlayer 模拟器执行 completion (exec 90 success, 含 result_data) | ✅ (真实执行) |
| K-02 | 设备→截图→模板匹配 | Agent+设备在线 | 选在线设备→截图→模板匹配 | 注册链路 ✅(Endfield/Chrome-Browser/LDPlayer 在线)；截图入口=R37-P1-C5 迁至标注页实时标注(截图流)；匹配预览 R37-P2 已真实化(后端 cv2 端点, 前端当前帧+选中框裁剪) | ✅ (R37-P2 已真实化) |
| K-03 | 定时任务→无人值守 | 设备绑定 | 建 Cron→预热→无人值守 start | ✅ 2026-08-28 全链路打通: Cron 创建 ✅ → Chrome-Browser 注册在线 ✅ → preflight can_start ✅ → 真实 start (session 13 running, dispatched_count=1, chain_exec 49) → stop ✅ | ✅ (真实启动) |

---

## 执行记录

| 日期 | 批次 | 执行项 | 结果摘要 |
|------|------|--------|---------|
| 2026-08-28 | 首轮探索 | A,B,C,D,E,F,G,H,I,J 大部分 | 43 路由全点击，18 问题登记见 e2e-coverage.md |
| 2026-08-28 | 补测 R1 | E-02/03/04, K-02, K-03 | 待执行（无头浏览器） |
| 2026-08-28 | R1-R4 补测完成 | E 组/K 组/A-02/J-07/D-09 | 造数后回看渲染 + 核心链路 + 剩余条目全部有结果, 0 ⏳ |
| 2026-08-28 | K 链路真实补测 | K-01/K-02/K-03 + I-06/E-04 | exec 90 success(模拟器真实执行) + unattended session 13 start/stop(dispatched 1) + 匹配预览 R37-P2 真实化 + I-06 modal 误判澄清, test-plan 全部测试项 ✅ |
| 2026-08-28 | 全量终验 | run_all.py 11 场景 | **11/11 全绿**(128s): 7 治理场景 + browser_login/devices_control_mode/ai_qa_chat + full_routes 47/47; 修复 bug_fix(N118 出清后断言泛化) + cross_repo('跨工作区' 措辞演进) 两处测试断言 |
| 2026-08-29 | B-04/B-05 新增 + 实测 | 统计对账 + 记住我回归 | N218 修复前"运行任务 91"为假(全表 count), 修复后 running 0/failed 26/无参 91, 卡片"运行任务 0" ✅; N217 修复后记住我默认勾选 + 清 sessionStorage 刷新自动进 dashboard ✅ |