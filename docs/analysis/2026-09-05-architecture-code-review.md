---
summary: GAF 全量架构与代码评审报告 — 架构梳理/文档一致性/缺陷排查/风险建议
applies_to: [backend, frontend, worker, desktop, deploy, docs]
last_updated: 2026-09-05
review_scope: 全仓（backend 17 app / frontend / worker / desktop / scripts / deploy / docs）
---

# GAF 架构与代码评审报告

> 评审日期：2026-09-05　评审方式：静态审查 + 可执行验证（lint / pytest / tsc 实测）
> 严重程度定义：**高** = 可导致生产事故、安全入侵或构建失败；**中** = 功能正确性/一致性受损，需排期修复；**低** = 可维护性/规范性问题。

---

## 0. 结论摘要

**整体判断：这是一个工程量很大、工程质量中上、但"质量门禁存在系统性盲区"的项目。**

> **范围声明（按用户最新约束：仅保证「单机器模式」完整可用）**
> 单机器模式启动链已确认：`scripts/gaf_services.ps1` → `scripts/gaf_daemon.py` → **`python -m daphne config.asgi:application`**（`gaf_daemon.py:299`，**ASGI，WebSocket 可用**）+ **`python -m src`**（Worker，`:316`）+ **`npm run dev`**（前端 Vite 开发服务器，`:325`）+ redis；后端环境默认 **`config.settings.dev`**（`asgi.py:6`），并默认开启 `GAF_ALLOW_LOCALHOST_BYPASS=1`（`:311`）。
> 因此：**D1（生产不跑 ASGI）/ D2（whitenoise 裸机）/ D3–D7 / P0-6（nginx HTTPS）均为「生产部署域」问题，不阻塞单机器模式，本期单列跟踪、不优先**。单机器模式的真实风险集中在：SQLite 行锁静默失效（C1/C2）、插件 RCE（S1）、执行链路静默吞异常（E1）、Celery eager 默认与定时调度（P3）、两个真实 TS 类型缺陷，以及用户点名的「架构归一化」（A1/A3/A5/Q4）。下文 §4 已用 `【单机】/【部署】/【文档】/【CI】/【归一化】` 标注每项范围，并以归一化为主线重排优先级。

值得肯定的部分（实测）：后端 `ruff check backend/` **零告警**；核心模块 pytest **546 passed / 2 skipped**；ZIP 解压已在两处正确实现 zip-slip 防护；Worker 侧 token 用 Fernet 加密 + ACL 收权，且全仓 subprocess 无 `shell=True`；Electron 主进程 `contextIsolation: true / nodeIntegration: false`；systemd 单元以非 root 运行且带 `NoNewPrivileges`；SQLite、`.env`、`dump.rdb`、`db.sqlite3` 均未被 git 跟踪。

必须立即处理的部分（按严重度）：

1. **生产部署没有运行 ASGI 进程**——`docker-compose.yml:43` 与 `deploy/systemd/gaf-backend.service:13` 都只启动 `config.wsgi:application`（纯 WSGI），而全部 WebSocket 路由只挂在 `config/asgi.py`。这意味着 **Worker 进程在生产环境根本连不上后端，整个自动化执行链路不成立**（详见 §3.7 D1）。这是本次评审发现的最高危问题。
2. **前端生产构建当前是失败的**（`npm run build` 退出码 2），而 CI 的类型检查门禁因 `tsconfig.json` 配置问题在空跑通过——"绿灯 CI"与"可发布构建"已经脱钩（§3.1 B1/B2）。
3. **`whitenoise` 未在 `pyproject.toml` 声明**，导致裸机部署走 prod 配置时首个请求即 500（§3.7 D2）。

| 维度 | 评级 | 说明 |
|:---|:---:|:---|
| 架构分层 | 中 | 边界大致清晰，但 `gaf_core` 反向依赖业务层，17 app 间存在大量双向依赖 |
| 代码质量（后端） | 良 | ruff 零告警；但存在 8 个千行级文件、9 个 app 无 service 层 |
| 代码质量（前端） | 中 | **构建失败**；3 个 1200+ 行组件；测试文件类型错误未纳入门禁 |
| 文档一致性 | 中 | 强制契约文档 `api-contract.md` 有 3 处与代码相反/脱节 |
| 安全性 | 中 | 2 处高危（插件 RCE、部署明文 HTTP）+ 5 处中危 |
| 测试有效性 | 中 | 后端测试扎实但**密度严重失衡**；**前端类型门禁失效**；CI 不跑构建 |
| **部署配置** | **差** | **无 ASGI 进程（WS 全线不可用）**、生产依赖缺声明、后端绕过 nginx 直曝、镜像以 root 运行 |

### 实测证据（本次评审亲自执行）

| 检查项 | 命令 | 结果 |
|:---|:---|:---|
| 后端静态检查 | `ruff check backend/` | **0 error** ✅ |
| Worker 静态检查 | `ruff check worker/` | 5 error（均为 F401/I001/W292，低） |
| 脚本静态检查 | `ruff check scripts/` | 1090 error（dev 工具链，中） |
| 后端核心测试 | `pytest tasks pipeline scheduler -q` | **546 passed, 2 skipped**, 139 deselected（2m12s）✅ |
| 前端构建类型检查 | `npx tsc -b`（`npm run build` 第一步） | **退出码 2，6 个错误** ❌ |
| CI 类型检查门禁 | `npx tsc --noEmit`（ci.yml:126 实际执行） | 退出码 0，0 error —— **但实际未检查任何文件** ❌ |
| SQLite 行锁行为 | Django 5.2.15 实测 | `has_select_for_update=False`，`skip_locked=True` **静默降级为空操作，不抛异常** |
| 生产配置可加载性 | 在 CI 同款环境（dev.txt）解析 `config.settings.prod` 中间件链 | `django.setup()` **成功**（中间件惰性解析），但第 2 个中间件 `whitenoise.middleware.WhiteNoiseMiddleware` **ModuleNotFoundError** ❌ |
| 生产 WSGI/ASGI 进程 | grep `daphne\|asgi:application` 于 docker-compose / deploy / workflows | **仅 `setup-dev-env.ps1:432` 提及 daphne，生产零 ASGI 进程** ❌ |
| 覆盖率门禁 | `pyproject.toml:184` | `fail_under = 30`（过低） |
| 依赖漏洞扫描 | grep `npm audit\|pip-audit\|dependabot\|safety` | **无任何配置** |

---

## 1. 架构梳理

### 1.1 总体架构

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  React Web   │  │ Electron 桌面 │  │  Python CLI  │
│  (frontend)  │  │  (desktop)   │  │   (worker)   │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │ REST /api/v2/   │ REST      │ WS ws/protocol/agents/
       │ (JWT Bearer)    │           │ (Agent Token)
       └─────────────────┴─────┬─────┴───────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Django Backend     │
                    │  (daphne ASGI)      │
                    │  17 个业务 app       │
                    └────┬──────────┬─────┘
                         │          │
              ┌──────────▼──┐  ┌────▼─────────┐
              │ SQLite +WAL │  │ Redis        │
              │ (业务数据)   │  │ Channel/Celery│
              └─────────────┘  └──────────────┘
                                      │
                          ┌───────────▼──────────┐
                          │ Celery Worker / Beat │
                          │ (docker-compose)     │
                          └──────────────────────┘
```

- **前端**：React 19 + TS + Vite + Ant Design + Zustand，24 个按域拆分的 api 文件 + 统一 `client.ts`（含并发 refresh 互斥、响应包解包、trace_id 透传），9 个 Zustand store。组织良好。
- **后端**：Django 5.2 + DRF + Channels + Celery，`config/settings/` 分 dev/prod/test/base 四档，路由前缀 `/api/v2/`（`config/app_info.py:12`）。
- **Worker**：独立 Python 进程，Win32 API / OpenCV / adbutils / RapidOCR，通过 WebSocket 与 backend 通信，自带单例锁。
- **数据层**：SQLite + WAL（PRAGMA 经 `init_command` 下发，已实测 Django 5.2 会执行该参数），Redis 承载 Channel Layer 与 Celery。

### 1.2 模块职责与规模

| App | 模型数 | py/LOC | 职责 |
|:---|:---:|:---:|:---|
| gaf_core | 1 | 41 / 4721 | 横切核心：日志、审计 mixin、i18n、search、trace、统一响应中间件（**入度 85，最热枢纽**） |
| accounts | 7 | 18 / 4747 | 用户/游戏账号/APIKey/审计日志（入度 68） |
| workers | 3 | 31 / 7738 | Worker 节点、Device、DeviceGroup 注册/心跳（入度 67） |
| tasks | 11 | 30 / 7648 | 任务定义/执行/步骤/市场（入度 65，出度 78，**耦合最重**） |
| gaf_ai | 7 | 45 / 7911 | AI/QA/LLM 评估/Agent 会话 |
| device_bridge（非 app） | — | 33 / 9832 | 跨平台设备桥接：发现/截图/输入 |
| scheduler | 7 | 14 / 4153 | 账号轮转/无人值守会话/恢复引擎 |
| protocol | 2 | 16 / 5164 | Agent WebSocket 会话与消息帧 |
| resources | 7 | 13 / 3474 | 资源包/模板/识别基准 |
| pipeline | 6 | 17 / 3466 | 流水线/任务链/录制 |
| monitors | 3 | 11 / 2098 | SLA 指标/规则/事件 |
| gamestate | 4 | 7 / 976 | 游戏档案/状态规则/快照 |
| notifications | 4 | 9 / 759 | 通知/Webhook/告警 |
| settings | 4 | 9 / 1611 | 策略/LLM 配置/特性开关 |
| skills | 3 | 10 / 1185 | 技能定义与市场 |
| plugins | 3 | 6 / 715 | 插件钩子/包/沙箱 |
| executions | 0 | 5 / 1271 | 执行分析/报表（复用 tasks 模型） |
| debug | 4 | 9 / 1131 | 调试归档/LLM 分析/崩溃报告 |

### 1.3 架构问题（按严重度）

| # | 问题 | 定位 | 严重度 | 影响 |
|:--|:---|:---|:---:|:---|
| A1 | **核心层反向依赖业务层（层级倒置）** | `gaf_core/audit_constants.py:34`、`gaf_core/views.py:33,212,246,283,310,338,578`、`gaf_core/search/views.py:27,50,73,98,123`、`gaf_core/mixins/audit.py:135,196` | 中 | `gaf_core` 名义上是底层核心，实际 import accounts/tasks/workers/protocol/scheduler/settings/gaf_ai/debug 七个业务 app。任何业务模型变更都会回压核心层，且 `plugins/views.py:53` 的注释已明写"避免 gaf_core ↔ accounts 循环导入风险"——说明团队已知此问题并用延迟 import 打补丁 |
| A2 | **app 间大量循环依赖** | accounts ↔ gaf_core / gamestate / monitors / notifications / protocol / resources / scheduler / settings / tasks / workers；gaf_core ↔ debug / gaf_ai / pipeline 等 | 中 | 415 行跨 app import 中双向边占比高，只能通过函数内延迟 import 规避。模块无法独立测试与复用 |
| A3 | **9 个 app 无 service 层，业务逻辑堆在 ViewSet** | 有 services 的仅 accounts/debug/gaf_ai/pipeline/protocol + scheduler/tasks/workers；缺 resources、monitors、skills、notifications、gamestate、plugins、settings、executions、gaf_core | 中 | 见 §1.4 巨型 ViewSet |
| A4 | **千行级上帝文件** | `protocol/consumers.py` **2236**、`accounts/views.py` **1879**、`resources/views.py` **1567**、`executions/views.py` **1215**、`device_bridge/platforms/windows/_dxgi.py` 1185、`monitors/views.py` 1084、`tasks/models.py` 1021；Worker 侧 `core/orchestrator.py` 1379、`client/handler.py` 1373 | 中 | 单文件承载过多职责，改动风险高、review 困难 |
| A5 | **术语归一化未收尾** | 目录 `workers/` 但 REST 路由 `/api/v2/agents/`（`workers/urls.py:27`）、CLI 参数 `--agent-token`、`pyproject.toml:98` 的 isort `known-first-party` 仍列 `agents`/`ai`/`metrics`/`qa`/`tracing`，却**未列** `workers`/`pipeline`/`scheduler`/`executions`/`gaf_ai`/`plugins`/`settings` | 低 | 新代码按 app 名 import 时被 isort 误判为第三方包；新人/AI 按目录名找路由必然找错 |
| A6 | **横切能力重复实现** | 异常类 ≥15 个自定义 Exception 分散各 app（`accounts/crypto.py:21`、`gaf_ai/llm_router.py:60,64`、`protocol/services.py:39`、`tasks/services/exceptions.py:4`、`pipeline/services.py:30,129`、`skills/loader.py:233`…）；`isoformat()` 内联 ≥30 处（`executions/views.py:86,260,397,429,440,668,680,761,804,840,841,905,1138,1139` 等） | 低 | 错误建模与时间格式不统一，前端解析易漂移 |

### 1.4 巨型 ViewSet（业务逻辑未下沉的典型）

| 定位 | 函数/类 | 行数 | 严重度 |
|:---|:---|:---:|:---:|
| `resources/views.py:125` | `ResourcePackViewSet` | **699** | 中 |
| `gamestate/views.py:21` | `GameProfileViewSet` | 454 | 中 |
| `tasks/views.py:49` | `TaskViewSet` | 433 | 中 |
| `pipeline/views.py:41` | `PipelineViewSet` | 254 | 低 |
| `accounts/views.py:1223` | `GameAccountViewSet` | 249 | 低 |

---

## 2. 文档一致性评估

### 2.1 吻合度总表

| 文档 | 声称 | 实际（实测） | 一致 | 严重度 |
|:---|:---|:---|:---:|:---:|
| `README.md:9` | 后端 17 个 app | `base.py:25-62` 恰 17 个 | ✅ | — |
| `README.md:22` | `.skills/` 含 15 个 Skill | 实测 15 个 | ✅ | — |
| `README.md:25-26` | `.trae`/`.opencode` 的 skills+rules 为 junction → `.skills/` | `fsutil` 确认重解析标签 `0xa0000003` | ✅ | — |
| `README.md:144` | 数据库 SQLite + WAL | `base.py:100-113`，`db.sqlite3-wal` 存在 | ✅ | — |
| `README.md:10` | 前端 **44** 页面 | `frontend/src/pages/` 实有 **75** 个页面组件（排除 `__tests__`/components），55 个二级页面 | ❌ | 中 |
| `docs/standards/api-contract.md:8,67` | `GAF_UNIFIED_RESPONSE_ENABLED` 默认 **False** | `base.py:303-305` 默认 **True**，且注释明写"default changed from False to True" | ❌ | **高** |
| `docs/standards/api-contract.md:115` | 最大 `page_size=100`（超出返回 400） | 全局 `base.py:193-194` 仅 `PAGE_SIZE=20`，**未设 max_page_size**；`gaf_core/views.py:181` 自定义分页用 500 | ❌ | 中 |
| `docs/standards/api-contract.md:340,355` | `UserRateThrottle` = **300/min** | `base.py:215` = **600/min** | ❌ | 低 |
| `docs/standards/api-contract.md:9` | 错误码范围仅 1xxx–4xxx | `gaf_core/error_codes.py:41-43` 含 5xxx（5001/5010） | ❌ | 低（文档内部亦矛盾） |
| `backend/config/settings/base.py:330-332` | 注释称 "P2-7: **30min** access token (was 15min)" | 同文件 `:320-323` 实际为 **15 分钟**；`api-contract.md:163` 亦为 15 分钟 | ❌ | 中 |
| `backend/settings/models.py:38-43` | docstring 称 LLMConfig "**Upsert 单例模式，全局只有一条记录**" | `settings/views.py:81` `order_by('-created_at')` + `:87-96` `set-active` action + `is_active` 排他更新 → 已支持**多 provider** | ❌ | 中 |
| `docs/specs/active/2026-08-31-ai-tab-agent-learning-spec.md:7` | 关联 TD-423 为待实施 | `docs/archive/fixed-tech-debt.md:27,177` 已标 **✅ FIXED 于 2026-09-01** | ❌ | 中 |
| `docs/project-status.md:24,250` | 活跃 Spec / Plan = **0** | `docs/specs/active/` 实有 **1** 个（2026-08-31，晚于该文件 last_updated 2026-08-28） | ❌ | 中 |
| 同上 | 活跃待办 = **0** | `docs/archive/active-tech-debt.md:15` 自述 "🔧 3 项待修 (TD-424/426/427)"，与"0 待办"口径冲突 | ❌ | 低 |
| `docs/specs/active/...spec.md` Phase 1 | 新增 `LLMProvider` 模型 + `/llm-providers/` 路由 | 全仓无 `LLMProvider` 模型；路由为 `llm-config`（`settings/urls.py:26`）；但 `settings/tests/test_llm_provider.py:43` 类名仍为 `TestLLMProviderMultiRow` | ❌ | 低 |
| `docs/architecture/overview.md:741` | `class PlatformBase(ABC)` | 全仓无 `PlatformBase`；实际为 `device_bridge/platforms/base.py:42,74` 的 `PlatformScreenshotHandler(ABC)` / `PlatformInputHandler(ABC)` | ❌ | 低 |
| 全 `docs/` | — | `TODO`/`FIXME`/`待办`/`deprecated`/`已废弃` 命中 **296 处** | ⚠️ | 低 |

### 2.2 一致性结论

- **量词级声明（17 app / 15 skill / junction / 脚本存在性 / WAL）全部准确** —— README 的基础事实可信度高。
- **真正的风险在"强制契约文档"**：`api-contract.md` 开篇即标"**强制：AI 写接口（前后端）前必读**"（`:20`），但其对**全局响应开关默认值**的描述与代码**完全相反**（False vs True）。由于该项目高度依赖 AI 生成代码，一份错误的强制契约会被系统性放大——AI 按文档写出的新客户端/新测试将默认按 DRF 裸格式解析，与服务端实际返回的 `{code,message,data}` 信封不符。
- **状态看板与 spec 状态双轨脱节**：`project-status.md` 自居"项目状态唯一权威入口"（`:8`），却未反映 2026-08-31 新增的 active spec 与 2026-09-01 已完成的 TD-423。
- **代码注释自相矛盾**（JWT 30min）说明存在"注释写了但改动没落地"的情况，属于技术债登记流程的漏网。

### 2.3 功能完成度

| 能力 | 文档声称 | 实测状态 | 完成度 |
|:---|:---|:---|:---:|
| 多 LLM provider 配置 | active spec Phase 1 | `LLMConfig` 多行列 + `set-active` 排他激活已实现（`settings/views.py:87-96`） | ✅ 90%（命名与 spec 不符） |
| LangGraph 手写图 / MCP / RAG rerank / Agent 评测 | active spec Phase 2/3 | `gaf_ai/agent/langgraph_graph.py`、`gaf_ai/agent/mcp/`、`tool_registry.py`、`scripts/ai/rag_eval.py`、`gaf_ai/urls.py` 均存在 | ✅ 已落地 |
| 插件沙箱执行 | — | `plugins/views.py:439-490` 已实现子进程沙箱 + 审计 | ⚠️ 有安全缺陷（见 S1） |
| 无人值守调度 | — | `scheduler/tasks.py:34` tick 已实现 | ⚠️ 锁失效（见 C1） |
| 统一响应信封 | 契约称默认关 | 实际默认开，前端 `client.ts` 透明解包 | ✅ 功能正常，文档错 |
| 前端生产构建 | — | **失败** | ❌ 0%（见 B1） |

---

## 3. 问题排查

### 3.1 【P0】构建与质量门禁

| # | 问题 | 定位 | 严重度 | 影响 |
|:--|:---|:---|:---:|:---|
| **B1** | **前端生产构建失败**：`npm run build`（= `tsc -b && vite build`）第一步即以**退出码 2** 失败，6 个类型错误 | `frontend/src/components/Layout/Sidebar.tsx:206`（TS2322，`children` 缺失）、`frontend/src/pages/AI/LogAnalysisPanel.tsx:153`（TS2345，`AgentAnalysisResult` 缺 `trajectory`）、`frontend/src/pages/AI/__tests__/AiConfigPage.test.tsx:56,104,139`（TS2339）、`__tests__/QAPanel.test.tsx:38`（TS2304） | **高** | **当前代码无法产出前端生产包**。Docker Compose 的 `frontend` 服务与 nginx 部署的根路径 `/opt/gaf/frontend/dist` 均依赖该构建产物 |
| **B2** | **CI 类型检查门禁空跑**：ci.yml 执行 `npx tsc --noEmit`，但根 `tsconfig.json` 为 `{"files": [], "references": [...]}`——无 `files`/`include`，`tsc --noEmit` **不检查任何文件**，恒返回 0 | `frontend/tsconfig.json:2-4` + `.github/workflows/ci.yml:126` | **高** | CI 的 `typecheck-frontend` job 与 `playwright-e2e`（`needs: typecheck-frontend`）**永远绿灯**，B1 因此长期未被发现。这正是"绿灯 CI + 红色构建"脱钩的根因 |
| B3 | CI 未包含构建验证 | `.github/workflows/ci.yml` 全篇无 `npm run build` / `vite build` | 中 | 即便修好 B2，仍无门禁能拦住"类型通过但打包失败" |
| B4 | 测试文件类型错误未隔离 | `AiConfigPage.test.tsx:56,104,139`、`QAPanel.test.tsx:38` 的类型错误会阻塞 `tsc -b` | 低 | 测试代码类型缺陷升级为构建阻塞项；建议 `tsconfig.app.json` 排除 `__tests__`，`tsconfig.node.json` 单独管 |

> **B1/B2 修复方向**：① 把 ci.yml:126 改为 `npx tsc -b --noEmit`（或直接 `npm run build`）；② 修 `Sidebar.tsx:206`（`translateMenuItems` 返回类型改为可区分联合，`type: 'group'` 分支须带 `children`）；③ 修 `LogAnalysisPanel.tsx:153`（补 `trajectory: []` 或将 `AgentAnalysisResult.trajectory` 改为可选）。

### 3.2 安全隐患

| # | 问题 | 定位 | 严重度 | 影响 |
|:--|:---|:---|:---:|:---|
| **S1** | **插件 `entry_point` 路径穿越 → 任意代码执行**：`entry_point` 直接取自上传包的 manifest，`_validate_manifest`（`plugins/views.py:77-85`）**只校验 `name`/`version`，完全不校验 `entry_point`**；随后 `os.path.join(extract_dir, entry_point)` 拼接并以服务端权限 `Popen(['python', entry_path])` | `backend/plugins/views.py:457-464`（校验缺口 `:77-85`） | **高** | manifest 中写入 `entry_point: "../../../../Users/x/evil.py"` 即可执行 `plugins_data/` 之外的任意 `.py`。配合 `RoleBasedPermission` 的 manage 权限，可导致服务端 RCE。注：ZIP 解压本身已有正确的 zip-slip 防护（`plugins/views.py:29-44`） |
| **S2** | **部署默认明文 HTTP**：仅 `listen 80`，HTTPS server 整段注释，HTTP→HTTPS 跳转亦注释 | `deploy/nginx/gaf.conf:16`、`:19-20`、`:107-119` | **高** | 按此配置部署，JWT、密码、Agent Token 全部明文传输可被嗅探 |
| S3 | **资源包 `directory_path` 为服务端本地路径，可被 `copytree` 到对外可下载目录**：仅校验目录存在性与包结构（`:256-267`），未限制路径范围；复制结果落在 `resources_root` 下，而 nginx 将 `/media/` 对外暴露（`gaf.conf:86-91`） | `backend/resources/views.py:155`、`:256`、`:271-285` | 中 | 具备 `manage` 权限的认证用户可令服务端复制任意本地目录（如 `C:\Users\...\.ssh`）内容并下载 → 服务器文件泄露 |
| S4 | **SSRF**：`base_url` 由 LLM Provider 配置（admin 可设）直接拼装后发起请求，无内网地址/协议白名单 | `backend/gaf_ai/qa_llm_client.py:64,77` | 中 | admin 可将 base_url 指向云元数据服务或内网管理端，探测内网 |
| S5 | **WebSocket 鉴权旁路开关**：`GAF_ALLOW_LOCALHOST_BYPASS=1` 时 127.0.0.1 来源免 Token 直接获得 `local_agent` 全权限 | `backend/protocol/middleware.py:85-93`（开关定义 `base.py:385`） | 中 | 默认关闭且已有 C1 修复（无 local Agent 时拒绝，`:95-103`），但生产误开则本机任意进程可伪装 Agent 控制设备 |
| S6 | **refresh token 明文存 localStorage**：`remember_me=true` 时 refresh token 落 localStorage；多账号切换的 refresh token 亦存 localStorage | `frontend/src/utils/tokenStore.ts:15`、`:95`、`:200` | 中 | 任一 XSS 即可窃取长期有效的 refresh token（30 天），access token 的内存/sessionStorage 保护被绕过 |
| S7 | **Electron `read-file` IPC 无路径校验**：渲染进程传入任意 `filePath` 即 `fs.readFileSync`，无白名单/根目录约束 | `desktop/src/main/ipc.ts:73-80` | 中 | 渲染进程一旦被注入即可读取本机任意文件（`.env`、密钥、token 文件）。`contextIsolation` 为真可缓解，但属深度防御缺失 |
| S8 | `_safe_extract_zip` 用 `startswith` 做前缀判断，未补分隔符 | `backend/resources/views.py:55`、`backend/plugins/views.py:39` | 低 | 若 dest 为 `/data/pack`，则 `/data/pack-other/...` 亦通过校验。当前目录名由 manifest 决定，实际利用需构造特定 name，风险有限 |
| S9 | `open-external` 无协议白名单 | `desktop/src/main/ipc.ts:69-71` | 低 | 可拉起非 http(s) 协议 |

**已核实为安全正面项**（避免误报）：`base.py:17-18` 有生产 SECRET_KEY fail-fast 守卫；全仓无 `eval`/`exec`/`pickle.loads`/`yaml.load`（均用 `safe_load`）/ `subprocess(shell=True)`；Worker token 经 Fernet 加密 + ACL 收权且日志不打印 token；`cursor.execute` 均为静态 SQL；ZIP 解压有 zip-slip 防护；`db.sqlite3`/`dump.rdb`/`.env` 均未被 git 跟踪。

### 3.3 异常处理缺失

| # | 问题 | 定位 | 严重度 | 影响 |
|:--|:---|:---|:---:|:---|
| E1 | **执行步骤持久化异常被静默吞掉**：`except Exception: pass`，注释标 "Best-effort" | `backend/protocol/services.py:762-763`、`:873-874`；`backend/protocol/consumers.py:300-301` | 中 | 步骤落库失败不会报错也不重试，任务可能被判定成功但执行链路缺失，排障时无法回溯。这是**最热的数据一致性路径**，静默失败危害最大 |
| E2 | 非原子读改写：先 `update_or_create` 评分，再 `count()`+`sum()` 全表聚合后 `save`，未加事务与行锁 | `backend/tasks/resource_views.py:299-308` | 中 | 并发评分时 `rating_count`/`rating_avg` 丢失更新，统计数据漂移 |
| E3 | 文件句柄未随响应关闭：`FileResponse(open(path, "rb"))` 无 `with` | `backend/pipeline/views.py:910` | 低 | 长周期下 fd 泄漏 |
| E4 | 全仓 `except ... pass` 共 25 处（backend，排除 tests/migrations） | 集中于 `device_bridge/discovery/emulator.py:123,167,241,361,363,387,389,588,652`、`device_bridge/platforms/linux/*:111,242`、`macos/discovery.py:165`、`executions/views.py:564`、`gaf_ai/views.py:75`、`accounts/views.py:1802` | 低 | 其中 device_bridge 的多为可选依赖/超时降级，设计上可接受；`executions/views.py:564`（日期解析失败）与 `gaf_ai/views.py:75`（JSON 解析失败）应返回 400 而非静默忽略 |

### 3.4 性能瓶颈

| # | 问题 | 定位 | 严重度 | 影响 |
|:--|:---|:---|:---:|:---|
| P1 | **请求线程内同步 subprocess**：探测 adb/node 设备 | `backend/monitors/views.py:872,1028`；`backend/accounts/views.py:335,435,456` | 中 | Django 工作线程被阻塞，adb 冷启动可达数秒；并发探测时线程池迅速耗尽 |
| P2 | **请求线程内同步 LLM 调用**：`requests.post`（含 stream） | `backend/gaf_ai/qa_llm_client.py:77,120` | 中 | LLM 首 token 延迟直接转化为请求延迟，且无超时保护时线程长期占用 |
| P3 | **Celery 默认 eager 模式**：`CELERY_TASK_ALWAYS_EAGER=True` | `backend/config/settings/base.py:356-357` | 中 | ① 重任务（debug 归档、截图处理、LLM）在请求/进程内同步执行；② Beat 不独立运行，无人值守 tick 不会自动触发；③ 与 CI/prod 的 `celery-worker`/`celery-beat` 容器行为不一致（`docker-compose.yml:46-80`），dev 与 prod 存在行为分叉 |
| P4 | 序列化循环内逐对象处理 | `backend/plugins/views.py:121-125`（`prefetch_related` 后 Python 循环 `_serialize_plugin`） | 低 | prefetch 已做，风险可控，建议 profiling 复核 |
| P5 | 前端超大组件导致重渲染 | `components/Device/DeviceOperationPanel.tsx` **1531 行**、`components/Pipeline/NodePropertyPanel.tsx` **1461**、`pages/Resources/TemplateAnnotation/LiveAnnotationTab.tsx` **1297**、`pages/Tasks/PipelineEditor/PipelineEditorPage.tsx` **1237**、`pages/Ops/Monitors/index.tsx` **1121** | 中 | 状态与列表耦合在单组件，局部更新触发整树重渲染；设备面板/流水线编辑器为高频交互页 |
| P6 | 列表 `key` 使用索引 | `frontend/src/pages/Tasks/Editor.tsx:362`、`pages/Ops/Logs/LogCenterPage.tsx:414`、`pages/System/ServicesPage.tsx:275` | 低 | 列表增删/重排时组件状态错位 |
| P7 | 悬挂 Promise 抑制报错：`return new Promise(() => {})` | `frontend/src/api/client.ts:193,306,333` | 低 | 重定向期间错误被静默吞掉，线上问题难以定位 |

### 3.5 并发与数据一致性

| # | 问题 | 定位 | 严重度 | 影响 |
|:--|:---|:---|:---:|:---|
| C1 | **SQLite 下 `select_for_update()` 静默失效**：全仓 8 处依赖行锁做并发互斥，但 Django 5.2.15 实测 SQLite `has_select_for_update=False`，`FOR UPDATE` 子句被整体跳过 | `backend/executions/views.py:171`、`backend/tasks/execution_views.py:272`、`backend/tasks/views.py:607`、`backend/pipeline/tasks.py:261`、`backend/scheduler/tasks.py:48,265`、`backend/scheduler/unattended_views.py:114`、`backend/workers/view_sets/lock_stats.py:51,145` | 中 | 行锁是**空操作**：并发抢占设备锁（`lock_stats.py`）、批量改任务状态（`tasks/views.py:607`）、无人值守会话互斥（`scheduler/tasks.py:48`）均失去保护，存在 TOCTOU 与双写竞争。WAL 只序列化写锁，不防应用层"检查后写" |
| C2 | 同上，`scheduler/tasks.py:48` 的 `skip_locked=True` | `backend/scheduler/tasks.py:48-50` | 中 | 实测**不会抛异常**（与"SQLite 会报 NotImplemented"的常见认知相反），而是静默降级。开发者会误以为互斥已生效——**这类"静默成功"比显式报错更危险** |
| C3 | 多表写入无事务保护（先写 DB 再调外部服务） | 插件执行（`plugins/views.py:472-490`）、评分累加（`tasks/resource_views.py:299-308`） | 中 | 依赖最终一致性，中途失败留下部分成功状态 |

> **说明**：评审中一度怀疑 `scheduler/tasks.py:48` 会因 `skip_locked` 在 SQLite 上抛 `NotSupportedError` 导致调度器崩溃。经 Django 5.2.15 实测，**该假设不成立**——`skip_locked` 与 `select_for_update` 均被静默忽略，不抛异常。真实风险是"锁无效"而非"崩溃"，严重度由高下调为中。此处特别记录以避免误判误导修复优先级。

### 3.6 代码质量

| # | 问题 | 定位 | 严重度 | 影响 |
|:--|:---|:---|:---:|:---|
| Q1 | `ruff check scripts/` 报 **1090 个错误**（E741/B033/C401/UP032/C420/N806/SIM115…） | `scripts/` 下 199 个 py 文件 | 中 | dev 工具链与生产代码质量差距悬殊；脚本多为 AI 生成且未纳入同等级门禁，出错时会误导排查 |
| Q2 | `ruff check worker/` 报 5 个错误（F401 ×2、I001 ×2、W292 ×1） | `worker/src/` | 低 | 轻微 |
| Q3 | 弃用脚本未清理 | `scripts/_archive/`（`migrate_*_p1.py`、`cleanup_traces.py`、`execution_rate.py`、`hooks/`） | 低 | 易误执行旧版脚本 |
| Q4 | isort 配置漂移：仍列已不存在的 `agents`/`ai`/`qa`/`metrics`/`tracing`，未列 `workers`/`pipeline`/`scheduler`/`executions`/`gaf_ai`/`plugins`/`settings` | `pyproject.toml:98` | 低 | 新代码 import 这些 app 时被判为第三方包，需人工维护 import 顺序 |

### 3.7 部署与配置缺陷（**最高危，原报告遗漏，本轮补查**）

| # | 问题 | 定位 | 严重度 | 影响 |
|:--|:---|:---|:---:|:---|
| **D1** | **生产部署不运行 ASGI 进程 → WebSocket 全线不可用**：Docker 与裸机两条路径均只启动 WSGI 应用，而全部 WebSocket 路由只挂在 `config/asgi.py:35-52`（agents + notifications + protocol 三组）。`daphne` 虽在 `INSTALLED_APPS` 首位，但仅被开发脚本 `setup-dev-env.ps1:432` 使用 | `docker-compose.yml:43`、`deploy/systemd/gaf-backend.service:13`（均 `config.wsgi:application`）；对照 `backend/config/asgi.py:35-52`、`gunicorn.conf.py:31` | **高** | **Worker 进程无法通过 `ws/protocol/agents/` 连接后端，自动化执行链路在生产环境完全不成立**；前端实时通知（`/ws/notifications/`）亦失效。nginx 已配置 `/ws/` 代理并设 `proxy_read_timeout 86400s`（`gaf.conf:64-75`），说明配置者预期 WS 会走这里，但实际后端无法完成 WS 升级握手，请求会失败或超时 |
| **D2** | **`whitenoise` 未声明在 `pyproject.toml`**：仅存在于 `backend/requirements/prod.txt:3`。而 `environment.yml` → `requirements/dev.txt` 不含该包，CI 环境因此**从未成功导入过 `config.settings.prod`** | 声明缺口：`pyproject.toml`（8-43 行依赖段）；引用点：`config/settings/prod.py:55`（中间件）、`:58`（`STATICFILES_STORAGE`）；环境来源：`environment.yml:8` | **高** | 裸机部署（按 README `setup-dev-env.ps1` 建 conda 环境）走 prod 配置时，`whitenoise.middleware.WhiteNoiseMiddleware` 解析失败 → **首个请求即 500**；`collectstatic` 亦失败。**隐蔽点**：`django.setup()` 不解析中间件类，配置"加载成功"的假象会掩盖该缺陷，直到有请求进来才暴露。**这是团队第二次踩同一类坑**——`pyproject.toml:39-42` 的注释已记录 APScheduler 因同样的"requirements 有、pyproject 无"导致环境缺依赖 |
| D3 | **后端绕过 nginx 直接暴露**：gunicorn 绑定 `0.0.0.0:8000`，而非 `127.0.0.1`；Docker 又将 8000 端口映射到宿主 | `backend/gunicorn.conf.py:13`；`docker-compose.yml:28-29` | 中 | 外部可直接访问 8000 端口，完全绕过 nginx 的 `X-Frame-Options`/`nosniff`/CSP/限流与 HTTPS 终止，安全头形同虚设 |
| D4 | **镜像构建吞掉 collectstatic 失败，且无 USER 指令** | `backend/Dockerfile:21`（`collectstatic ... \|\| true`）；整份 Dockerfile 无 `USER` | 中 | ① `\|\| true` 使静态文件收集失败时构建仍"成功"，运行时表现为静态资源 404，故障被推迟到上线后；② 容器以 root 运行，与 systemd 侧 `User=gaf` 的非 root 实践不一致 |
| D5 | **ASGI 入口硬编码 dev 兜底**：`os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")` | `backend/config/asgi.py:6` | 中 | 一旦按 D1 修复而改用 `daphne config.asgi:application` 启动，若部署时漏设环境变量，生产将以 **DEBUG=True + 默认 SECRET_KEY** 运行。（注：gunicorn 因 `gunicorn.conf.py:31` 的 `raw_env` 强制 prod，此路径暂不受影响） |
| D6 | **HSTS 策略过于激进**：默认 `SECURE_HSTS_SECONDS=31536000` + `includeSubDomains` + `preload` 全开，而 `SECURE_SSL_REDIRECT` 默认 `False` | `backend/config/settings/prod.py:17,22-24` | 中 | 当前因 Django 仅在 `request.is_secure()` 时下发 HSTS 头而暂时无害（nginx 走 HTTP 时不发）。但按 P0-4 启用 HTTPS 后，`preload` 会把域名推入浏览器内置列表，**回滚极其困难**；`includeSubDomains` 还会连带强制所有子域名 HTTPS。建议启用 HTTPS 时先关 preload、缩短 max-age 观察，稳定后再提升 |
| D7 | **`ALLOWED_HOSTS` 生产默认空列表**（fail-closed） | `backend/config/settings/prod.py:9` | 低 | 安全上是正确取向，但裸机部署若漏配 `ALLOWED_HOSTS` 会导致全部请求 400 且报错信息不明显。建议部署文档中显式列出该必填项，并在启动时做 fail-fast 校验 |

---

## 4. 风险建议（按优先级）

### 4.0 范围划分与归一化主线（按「仅单机器模式」约束重排）

单机器模式启动链已确认：`gaf_services.ps1` → `gaf_daemon.py` → `python -m daphne config.asgi:application`（`gaf_daemon.py:299`，**ASGI，WebSocket 可用**）+ `python -m src`（Worker，`:316`）+ `npm run dev`（前端 Vite 开发服务器，`:325`）+ redis；后端默认 `config.settings.dev`（`asgi.py:6`），并默认开启 `GAF_ALLOW_LOCALHOST_BYPASS=1`（`:311`）。

由此范围结论：

| 范围 | 覆盖项 | 是否阻塞单机器模式 |
|:---|:---|:---:|
| 【单机】单机器正确性 | C1/C2（SQLite 锁失效）、S1（插件 RCE）、E1（执行链路静默吞异常）、P1-5（评分聚合无事务）、P1-6（Celery eager 与定时调度）、两个真实 TS 类型缺陷、S5（本机 bypass 默认开） | **是，需修** |
| 【归一化】架构归一化 | A1（`gaf_core` 层级倒置）、A3（9 app 缺 service 层）、A5（术语 workers/agents 漂移）、Q4（isort 漂移）、A6（异常/时间格式不统一） | 不阻塞运行，但降低单机长期可维护性 |
| 【文档】契约/状态 | P1-1（`api-contract.md` 与代码相反）、P1-8（状态看板脱节） | 间接（影响 AI 生成代码正确性） |
| 【部署】生产部署域 | **P0-1（生产 ASGI）、P0-2（whitenoise 裸机）、P0-6（nginx HTTPS）、D3–D7** | **否，本期单列跟踪、不优先** |
| 【CI】流水线门禁 | P0-3b（构建门禁）、P0-4（CI build job）、B2（tsc 空跑） | 否（不影响本地运行，建议补） |

> **归一化主线回答用户提问**：是的——在「只保单机器模式」约束下，修改建议应以**架构归一化**为骨架，范围收窄到真正命中单机器运行链的那几项运行时缺陷。生产部署域高危项（D1/D2/P0-6）虽真实，但对单机器目标不阻塞，故降为跟踪项而非本期 P0。

### 4.0.1 修复落地记录（2026-09-05 第二轮，Agent 模式执行）

| 项 | 状态 | 落地内容 | 验证 |
|:---|:---:|:---|:---|
| **P0-5**（S1 插件 RCE） | ✅ | `_validate_manifest` 增加 `entry_point` 相对路径/禁 `..`/禁绝对路径校验；`PluginSandboxExecView` 执行前 `realpath` + 前缀断言防御 | `pytest plugins` ✅；ruff ✅ |
| **P0-3a**（TS 缺陷） | ✅ | `Sidebar.tsx:206` 改为推断类型 + `as MenuItemType`（group 类型联合缺失问题）；`LogAnalysisPanel.tsx:153` 补 `trajectory: []` | `tsc -b` 退出码 0 ✅ |
| B4（测试文件类型隔离） | ✅ | `tsconfig.app.json` 增加 `exclude: __tests__ / *.test.* / *.spec.*` | `tsc -b` 退出码 0，**前端生产构建恢复** ✅ |
| **P1-3**（SQLite 锁失效） | ✅ 部分 | `DeviceLockView` 改为原子条件 `UPDATE`（`Q(locked_by__isnull=True) \| Q(locked_by=user)`），SQLite WAL 行写锁下实现真互斥；其余 7 处 `select_for_update` 均加 C1 注释说明 no-op 与现有缓解 | `pytest workers` ✅ |
| **P1-4**（静默吞异常） | ✅ | `protocol/services.py` 两处、`consumers.py` 一处 `except: pass` → `logger.warning/debug` | `pytest protocol` ✅ |
| **P1-1**（契约文档） | ✅ | `api-contract.md`：统一响应默认改 True（`:8,:67`）、分页上限改"未设全局硬上限/自定义分页 500"（`:115`）、限流 300→600/min（`:340`） | 与 `base.py:194,215,303` 逐项核对 ✅ |
| **P1-2**（S3 目录白名单） | ✅ | `_import_from_directory` 限制导入源在项目根内（可用 `GAF_RESOURCE_IMPORT_ROOTS` 扩展，os.pathsep 分隔） | `pytest resources` ✅ |
| **P1-5**（E2 评分聚合） | ✅ | `tasks/resource_views.py` review 改为事务内 `aggregate(Count/Avg)` | `pytest tasks` ✅ |
| **P1-6**（调度路径） | ✅ 文档化 | `gaf_daemon.py` celery_mode 处加注释：eager 默认无 beat、定时调度需 `GAF_CELERY_MODE=celery` | — |
| **P1-7**（token/IPC） | ✅ 部分 | S7：`read-file` IPC 增加 `GAF_DESKTOP_READ_ROOTS` + userData 白名单（渲染层当前未调用，无破坏）；S9：`open-external` 限 http(s)。**S6（refresh token 移出 localStorage）未动**——需后端改发 httpOnly Cookie，涉及认证链路，单列待办 | desktop 待构建验证 |
| **P1-8**（状态看板） | ✅ | `project-status.md`：活跃待办 0→3（TD-424/426/427）、活跃 Spec 0→1。注：2026-08-31 spec 仍含 Phase 2/3，**不归档** | 与 active-tech-debt.md / specs/active/ 核对 ✅ |
| P0-3b（CI 门禁） | ✅ | ci.yml:126 `tsc --noEmit`（空跑）→ `npx tsc -b`（真检查）；新增 `build-frontend` job 跑 `npm run build`；`playwright-e2e` 改依赖 `[typecheck-frontend, build-frontend]` | ci.yml YAML 结构核对 ✅ |
| **S6**（refresh token localStorage） | ✅ | `tokenStore.ts`：refresh token 与多账号凭据全部移入 sessionStorage（**关浏览器即失效**，消除 30 天持久窃取窗口），含一次性 localStorage 旧值清理；语义变化：跨 tab 登出不再自动同步、记住登录不再跨浏览器重启（httpOnly Cookie 方案仍为远期正解） | `tsc -b` ✅；`vitest` useAuthStore/client 共 13 tests passed ✅ |
| **P0-1/D1**（生产无 ASGI） | ✅ | `docker-compose.yml` backend 与 `backend/Dockerfile` CMD 均改 `daphne config.asgi:application`；`deploy/systemd/gaf-backend.service` 同步改 daphne 并绑 `127.0.0.1`（D3 一并收敛），**`Type=notify`→`Type=simple`**（daphne 不发 sd_notify，notify 会被 systemd 误杀） | 配置核对 ✅（Docker/裸机需重新部署生效） |
| **P0-2/D2**（whitenoise 漂移） | ✅ | `pyproject.toml` dependencies 补 `whitenoise>=6.7,<7.0`（与 APScheduler 同类漂移第二次发生，已注明）；daphne 已在 base.txt 无需处理 | grep 核对 ✅ |
| **D4**（collectstatic 吞错） | ✅ | `backend/Dockerfile` 移除 `\|\| true`，collectstatic 失败即构建失败 | — |
| P0-6（HTTPS/安全头） | ✅ 部分 | `gaf.conf` 加 `server_tokens off` + `X-Frame-Options`/`X-Content-Type-Options`/`Referrer-Policy`（不依赖 TLS 即生效）；**TLS 启用仍需证书，保持注释** | — |
| **D6**（HSTS 激进默认） | ✅ | `prod.py`：`SECURE_HSTS_PRELOAD` 默认改 **False**（env 可覆盖；preload 入浏览器内置列表后不可逆），`INCLUDE_SUBDOMAINS` 亦改 env 可覆盖；`SECURE_PROXY_SSL_HEADER` 原已有 | ruff ✅ |
| **P0-2**（CI 校验 prod 配置） | ✅ | 新增 `check-prod-config` job（装 whitenoise 后跑校验脚本）+ `scripts/check_prod_settings.py`（django.setup 后逐个 import 中间件与静态存储）。**本地实测**：未装 whitenoise 时 `FAIL: ModuleNotFoundError`（退出 1，成功复现 D2 漂移），安装后 `prod settings OK: 13 middleware`（退出 0） | 实测 ✅ |
| **D8**（新发现，本轮实测暴露） | ✅ | **Django 5.1 已移除 `STATICFILES_STORAGE`**，prod.py 原写法在 5.2.15 下被静默忽略 → WhiteNoise CompressedManifest 存储自升级 5.2 起从未生效（又一处"配置加载成功"假象）。改用 `STORAGES` dict（`django.conf.global_settings.STORAGES` 为底）；注意裸机更新代码后必须跑 `collectstatic` | check 脚本实测 `staticfiles backend = whitenoise...Manifest` ✅ |

> **httpOnly Cookie（S6 正解）维持远期**：多账号切换依赖客户端持有各账号 refresh token（`tokenStore.saveAccount`），浏览器 cookie 每路径只能持一个 refresh —— 贸然实现会直接破坏多账号功能；做默认关闭的 feature flag 又属投机性死代码。sessionStorage 迁移已消除 30 天持久窃取窗口（S6 的核心危害），故正解方案待多账号认证重设计时一并处理。

> 验证基线：`pytest workers plugins protocol` **385 passed**；`pytest resources tasks` **230 passed**；`ruff check`（改动文件）**All checks passed**；`npx tsc -b` **退出码 0**（前端生产构建恢复）。

### P0 — 立即修复（本周内，仅单机相关）

| 优先级 | 范围 | 动作 | 定位 | 预期收益 |
|:---|:---:|:---|:---|:---|
| **P0-5** | 【单机】 | **修复插件 `entry_point` 路径穿越（S1）**：在 `_validate_manifest` 强制 `entry_point` 为相对路径、不含 `..`、不以 `/` 开头；执行前 `Path(extract_dir).resolve()` 与 `Path(entry_path).resolve()` 做 `is_relative_to` 断言 | `backend/plugins/views.py:77-85` + `:457-461` | 消除本地安装插件时的 RCE 面（单机也是受害者） |
| **P0-3a** | 【单机】 | **修两个真实 TS 类型缺陷**：`Sidebar.tsx:206`（`type:'group'` 分支补 `children`）、`LogAnalysisPanel.tsx:153`（补 `trajectory: []` 或把 `AgentAnalysisResult.trajectory` 置可选）。注：单机器走 `npm run dev`（Vite/esbuild 不校验类型，故不阻塞启动），但属真实正确性缺陷 | `frontend/src/components/Layout/Sidebar.tsx:206`、`frontend/src/pages/AI/LogAnalysisPanel.tsx:153` | 消除潜在运行时数据缺失/渲染异常 |
| P0-3b | 【CI】 | **修 CI 类型门禁空跑（B2）+ 补构建门禁（B3/P0-4）**：ci.yml:126 改 `npx tsc -b --noEmit`；新增 `npm run build` job；`tsconfig.app.json` 排除 `__tests__` | `.github/workflows/ci.yml:126`、`frontend/tsconfig.json` | 让 CI 真正拦类型错误（不阻塞本地运行，建议补） |
| P0-1 | 【部署】 | 生产跑 ASGI（D1）——**单机已用 daphne，不阻塞，单列跟踪** | `docker-compose.yml`、`deploy/systemd/gaf-backend.service:13` | 生产 WS 恢复 |
| P0-2 | 【部署】 | whitenoise 声明（D2）——**单机走 dev 静态服务，不阻塞，单列跟踪** | `pyproject.toml` | 裸机部署修复 |
| P0-6 | 【部署】 | nginx HTTPS（S2/D6）——**单机无 nginx，不阻塞，单列跟踪** | `deploy/nginx/gaf.conf` | 明文传输修复 |

### P1 — 近期排期（本月内）

| 优先级 | 范围 | 动作 | 定位 |
|:---|:---:|:---|:---|
| **P1-3** | 【单机】 | **处理 SQLite 行锁失效（C1/C2）**：在 8 处 `select_for_update` 补应用层幂等/乐观锁（`Device.lock_version`），至少 `scheduler/tasks.py:48` 加注释说明 SQLite 下无锁。单机器模式以 SQLite 为存储，这是当前最影响"完整使用"的缺陷——设备锁抢占、任务状态批量改、无人值守会话互斥均失去保护 | 见 C1 表 |
| P1-1 | 【文档】 | **修订 `api-contract.md` 三处与代码相反/脱节**（统一响应默认 True、分页上限、限流 600/min）。该文件是 AI 写接口强制必读，错误会被系统化放大 | `docs/standards/api-contract.md:8,67,115,340` |
| P1-2 | 【单机】 | 资源包 `directory_path` 增加目录白名单，移除"任意本地目录可复制" | `backend/resources/views.py:256,271-285` |
| P1-4 | 【单机】 | `protocol/services.py:762,873` 与 `protocol/consumers.py:300` 的 `except: pass` 改为"失败计数+告警+写 error 字段"，避免执行链路静默丢失 | `backend/protocol/services.py`、`backend/protocol/consumers.py` |
| P1-5 | 【单机】 | 评分聚合改事务内 `select_for_update` + 数据库聚合（`aggregate(Avg/Sum)`）或增量更新 | `backend/tasks/resource_views.py:299-308` |
| P1-6 | 【单机】 | **明确单机器定时调度路径**：默认 `GAF_CELERY_MODE=eager` 时无 beat，无人值守 tick 不自动触发；需在单机器启用调度时设 `GAF_CELERY_MODE=celery`（daemon 自动起 celery_worker+beat）。请求内同步 subprocess/LLM 改 Celery 任务+超时 | `base.py:356`、`gaf_daemon.py:266,335`、`monitors/views.py`、`accounts/views.py`、`gaf_ai/qa_llm_client.py` |
| P1-7 | 【单机】 | refresh token 移出 localStorage（httpOnly Cookie）；`read-file` IPC 增加根目录白名单 | `frontend/src/utils/tokenStore.ts`、`desktop/src/main/ipc.ts:73` |
| P1-8 | 【文档】 | 修正状态看板与 spec 状态脱节 | `docs/project-status.md` 等 |

### P2 — 技术债（下季度）

| 优先级 | 范围 | 动作 | 定位 |
|:---|:---:|:---|:---|
| **P2-1** | 【归一化】 | **解开 `gaf_core` 的层级倒置**：将 `search/views.py` 对 tasks/workers/accounts/scheduler/settings 的延迟 import 改为注册表/插件式扩展（各 app 自注册 search provider），`audit_constants.py:34` 的 `AuditLog` 依赖改为反向（accounts 注册到 gaf_core） | `backend/gaf_core/search/views.py:27,50,73,98,123`、`gaf_core/audit_constants.py:34`、`gaf_core/views.py:33,212,246,283,310,338,578` |
| P2-2 | 【可维护】 | **拆分上帝文件**：`protocol/consumers.py`（2236 行）按消息类型拆分为 handler 模块；`accounts/views.py`（1879）、`resources/views.py`（1567）按资源拆分为 ViewSet 模块包 | 见 A4 |
| **P2-3** | 【归一化】 | **补齐 9 个 app 的 service 层**，把 `resources`（699 行 ViewSet）、`gamestate`（454）、`tasks`（433）的业务逻辑下沉 | 见 A3/A1.4 |
| P2-4 | 【归一化】 | 统一错误建模（以 `gaf_core/exceptions.py:29 BusinessException` 为基类收敛 15 个分散异常类）与时间格式化工具（消除 ≥30 处内联 `isoformat()`） | 见 A6 |
| P2-5 | 【CI】 | 清理 `scripts/_archive/`，将 `scripts/` 纳入与 backend 同级的质量门禁（当前 1090 个 ruff 错误） | `scripts/` |
| **P2-6** | 【归一化】 | 完成术语归一化收尾：同步 `pyproject.toml:98` isort 配置；在 `workers/urls.py:27` 增加 `/api/v2/workers/` 别名路由，`/agents/` 保留为 deprecated 兼容 | `pyproject.toml:98`、`backend/workers/urls.py:27` |
| P2-7 | 【可维护】 | 拆分前端 5 个 1200+ 行组件；修 3 处 `key={index}`；处理 `client.ts:193,306,333` 悬挂 Promise | 见 P5/P6/P7 |
| P2-8 | 【文档】 | 清理 `docs/` 中 296 处 TODO/待办标记，明确哪些仍是有效待办、哪些已过期 | `docs/` |

> **归一化主线（用户点名）**：P2-1（层级倒置）、P2-3（service 层）、P2-4（异常/时间统一）、P2-6（术语/isort）四项即"架构归一化"核心。它们在单机器模式稳定后作为下阶段主线推进——不阻塞单机运行，但能从根本上降低 A1/A3/A5 反复引发的缺陷面与 AI 生成代码的误用率。

---

## 5. 附录：复现命令

```bash
# 后端静态检查（应 0 error）
cd /d/code/GAF && python -m ruff check backend/

# Worker / scripts 静态检查
python -m ruff check worker/ --statistics
python -m ruff check scripts/ --statistics

# 后端核心测试（实测 546 passed, 2 skipped, 139 deselected）
cd backend && python -m pytest tasks pipeline scheduler -q

# 前端构建类型检查（当前退出码 2 —— 生产构建已失败）
cd frontend && npx tsc -b --pretty false; echo "exit=$?"

# CI 实际执行的命令（恒返回 0，但因 tsconfig.json files:[] 而未检查任何文件）
cd frontend && npx tsc --noEmit --pretty false; echo "exit=$?"

# SQLite 行锁行为实测（验证 select_for_update 为静默空操作）
python -c "
import django;from django.conf import settings
settings.configure(DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}},
                  INSTALLED_APPS=['django.contrib.contenttypes','django.contrib.auth'],USE_TZ=True)
django.setup()
from django.db import connection;print('has_select_for_update =', connection.features.has_select_for_update)"
```

---

## 6. 评审方法说明

- 覆盖范围：`backend/`（17 app + device_bridge）、`frontend/`、`worker/`、`desktop/`、`scripts/`、`deploy/`、`.github/workflows/`、`docs/`、`pyproject.toml`、`docker-compose.yml`。
- 所有"高"级别结论均经过**可执行验证**（lint/pytest/tsc 实测或源码精读），未采用"看起来像问题"的推测性判断。
- 已明确排除的误报：SQLite 上 `skip_locked` 抛异常（实测不抛）、`dump.rdb` 未 gitignore（实际已覆盖，`.gitignore:96`）、`init_command` 在 SQLite 上无效（Django 5.2 确实执行该参数）。
