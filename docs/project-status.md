---
summary: GAF 项目状态统一追踪 — 活跃待办/已完成功能/技术债务 (唯一入口)
applies_to: [backend, frontend, agent, project]
last_updated: 2026-08-28
---

# GAF 项目状态仪表板 (Project Status Dashboard)

> **📌 本文件是项目状态的唯一权威入口。**
> 
> 所有项目级的"待办"、"已完成"、"技术债务"状态都整合在这里。
> AI 在每轮 plan 实现完成后，必须检查此文件并更新状态。

---

## 📊 概览统计

| 分类 | 数量 | 详情 |
|:---|:---:|:---|
| 🔧 **活跃待办** | 0 | 无 |
| ✅ **已完成项目** | 114 | [查看详情](#已完成项目) |
| ✅ **已修复技术债务** | 147+（截至 TD-414） | [查看详情](#技术债务) |
| ❌ **WONTFIX/INVALIDATED** | 34 | [查看详情](#技术债务) |
| 📋 **活跃 Spec / Plan** | 0 | 无 |
| 🗂️ **归档 Spec** | 57 | `docs/specs/archived/` |
| 📊 **月度健康报告** | 2 | [2026-07](archive/2026-07-health-report.md) / [2026-08 (模板)](archive/2026-08-health-report.md) |

---

## 🔧 活跃待办 (Active Backlog)

> 此处列出所有已登记但未开始/进行中的项目。
> 
> **添加规则**:
> - 任何 plan 中标记为 [B] 后续 Phase 的项必须迁入本节
> - 技术债务 (TD-NNN) 登记到下方「技术债务」段
> - 完成后迁入「已完成项目」段

**当前状态**: 🎉 暂无活跃待办

---

## ✅ 已完成项目

> 此处列出所有已完成的项目功能 (C-NNN)。

<details>
<summary>展开查看已完成项目清单 (114 项)</summary>

| ID | 模块 | 项 | 完成时间 | Commit |
|:---|:----:|---|:--------:|:------:|
| C-001 | 截图 | TD-003 GDI 截不到被遮挡游戏窗口 | 2026-07-05 | `-` |
| C-002 | 截图 | TD-007 Debug 模式 AI auto-heal 集成 | 2026-07-05 | `-` |
| C-003 | 截图 | TD-006 benchmark.py 可靠性维度 | 2026-07-05 | `-` |
| C-004 | 文档 | TD-005 创建 pending-roadmap.md + completed-features.md | 2026-07-05 | `-` |
| C-005 | 截图 | TD-002 DXGI "Python int too large" + AMD 驱动 bug | 2026-07-05 | `-` |
| C-006 | 资源 | TD-004 模板存储双副本漂移 (Option A) | 2026-07-05 | `-` |
| C-007 | 坐标 | TD-008 RuntimeDisplayContext 字段名歧义 | 2026-07-05 | `-` |
| C-008 | 设备/数据治理 | R37-P0 BD2 窗口去重 Bug + DB 清理 | 2026-07-05 | `-` |
| C-009 | 模型架构 | R37-P1 归属 FK 重构 + 模板标注后端打通 | 2026-07-05 | `-` |
| C-010 | 设备操作 UI | R37-P3 设备操作迁移到标注界面 | 2026-07-05 | `-` |
| C-011 | 任务迁移 | R37-P2 BD2 任务迁移 + ROI 管理 UI | 2026-07-05 | `-` |
| C-012 | 截图流 | R37-P2 截图流 per-device 过滤 + 并行截图 | 2026-07-06 | `-` |
| C-013 | 引擎 | R37-P2 wait 节点 OCR 模式扩展 | 2026-07-06 | `-` |
| C-014 | 任务迁移 | R37-P2 BD2 收尾: 5 OCR 迁移 bug 修复 | 2026-07-06 | `-` |
| C-015 | 截图 | TD-011 LDOpenGLCapture 单例缓存修复 | 2026-07-06 | `-` |
| C-016 | 重构基础 | gaf-restructure-foundation spec 全部完成 | 2026-07-07 | `-` |
| C-017 | 文档同步 | TD-020 lesson-router SKILL.md 同步 v8.5 | 2026-07-07 | `-` |
| C-018 | 重构执行 | gaf-restructure-execution Stage 1: 删前端死代码 | 2026-07-07 | `-` |
| C-019 | 重构执行 | gaf-restructure-execution Stage 2: 后端共享模块提取 | 2026-07-07 | `-` |
| C-020 | 重构执行 | gaf-restructure-execution Stage 3: Harness 层简化 | 2026-07-07 | `-` |
| C-021 | 重构执行 | gaf-restructure-execution Stage 4: TD-018/019 接入 | 2026-07-07 | `-` |
| C-022 | 4 维度再评估 | Phase A/B/C/D 全部完成 | 2026-07-07 | `-` |
| C-023 | 重构执行 | R37-P3 backend app 归一化 | 2026-07-08 | `-` |
| C-024 | 架构重构 | TD-061 Pipeline 合并方案 B | 2026-07-09 | `28-stage` |
| C-025 | 架构重构 | TD-060 TraceSpan 迁移 | 2026-07-09 | `-` |
| C-026 | 前端重构 | 前端界面分组全量归一化 | 2026-07-13 | `-` |
| C-027 | GameProfile | GameProfile 详情页绑定/解绑子资源 | 2026-07-14 | `-` |
| C-028 | 文档修复 | TD-120 architecture-mistakes.md 编码乱码修复 | 2026-07-15 | `git history` |
| C-029 | 全栈 | TD-113 GameProfile.routine_path 全栈实现 | 2026-07-15 | `migration 0007` |
| C-030 | 前端 | TD-114 前端 DAG editor 拖拽创建节点 | 2026-07-15 | `vite build` |
| C-031 | 文档治理 | L2 一致性 pre-commit hook | 2026-07-15 | `pre-commit hook` |
| C-032 | AI 架构缺陷修复 S4 | QASession 多轮对话 | 2026-07-14 | `-` |
| C-033 | AI 架构缺陷修复 S5 | FeatureFlag + 工具隔离 + RAG chunk | 2026-07-14 | `-` |
| C-034 | AI 架构缺陷修复 S6 | Skill 注册为 LangGraph Tool | 2026-07-14 | `-` |
| C-035 | 任务调度 | P-009: 无人值守 TaskChain 4 Phase 渐进重构 | 2026-07-14 | `-` |
| C-036 | 任务调度 | TD-110: routine.json → TaskChain 自动转换 | 2026-07-15 | `-` |
| C-037 | 任务调度 | P-010: handle_step_failure 接入 | 2026-07-15 | `-` |
| C-038 | 架构重构 | TD-116: backend/core/ + backend/ai/ 重命名 | 2026-07-15 | `-` |
| C-039 | 任务调度 | P-011: 多 UnattendedSession 并行 | 2026-07-16 | `-` |
| C-040 | 多游戏并行安全 | Spec A: 多游戏并行模式开关 | 2026-07-16 | `-` |
| C-041 | 多游戏并行安全 | Spec B: TD-122 PostMessage 坐标 bug 修复 | 2026-07-16 | `-` |
| C-042 | 多游戏并行安全 | Spec C: TD-121 SendInput 串行化 | 2026-07-16 | `-` |
| C-043 | 多游戏并行安全 | Spec D: TD-123 minitouch 端口动态分配 | 2026-07-16 | `-` |
| C-044 | 多游戏并行安全 | Spec E: TD-124/125 截图降级链优化 | 2026-07-16 | `-` |
| C-045 | 审计 | spec34: AuditLog P0 接入 | 2026-07-19 | `-` |
| C-046 | 协议 | spec-29a: TD-259 cross-app import 归一 | 2026-07-19 | `-` |
| C-047 | 协议 | spec-29b: TD-259 ACK wontfix + P0 回归 | 2026-07-19 | `-` |
| C-048 | 协议 | spec-29c: TD-259 legacy 端点删除 | 2026-07-19 | `-` |
| C-049 | 架构 | spec-29d: TD-259 巨型 views 拆分 | 2026-07-19 | `-` |
| C-050 | 前端 | spec-29e Phase 1: TD-259 models.ts 迁移注释 | 2026-07-19 | `-` |
| C-051 | API | spec-29f: TD-266 DRF Spectacular 嵌套 Serializer | 2026-07-19 | `-` |
| C-052 | 前端 | spec-29j Phase 2: 9 核心类型迁移到 API schema | 2026-07-19 | `-` |
| C-053 | 前端 | spec35: TD-259 .catch 静默吞异常修复 | 2026-07-19 | `-` |
| C-054 | 后端 | spec36: TD-259 scheduler/data 风格归一 | 2026-07-19 | `-` |
| C-055 | 测试 | TD-260 + TD-261: AgentConsumer 集成测试 | 2026-07-19 | `-` |
| C-056 | 后端 | spec-29i / TD-265: tasks/services 跨 app import | 2026-07-19 | `-` |
| C-057 | 协议 | TD-267: protocol AgentConsumer 资源释放 | 2026-07-19 | `-` |
| C-058 | 脚本 | TD-259 #1: scripts/README.md CI 巡检脚本 | 2026-07-19 | `subagent #1` |
| C-059 | API | TD-259 #10: 60 处 @extend_schema 注解补全 | 2026-07-19 | `subagent #10` |
| C-060 | 前端 | TD-259 #13: PageErrorBoundary 页级 ErrorBoundary | 2026-07-19 | `subagent #13` |
| C-061 | 协议 | TD-259 #29: protocol/services.py 下沉 | 2026-07-19 | `subagent #29` |
| C-062 | API | TD-268: DRF Spectacular APIView @extend_schema | 2026-07-19 | `5 batches` |
| C-063 | L3-1 | spec-35: L3-1 全量扫描 [A] 类批量修复 | 2026-07-19 | `4 Phase` |
| C-064 | 文档 | spec-36: .ai-memory/ops/ 清理 + docs-index | 2026-07-19 | `3 Phase` |
| C-065 | 文档治理 | spec-37: docs/ 与 .ai-memory/ 文档治理 | 2026-07-19 | `-` |
| C-066 | 文档 | spec-38: docs/ + .ai-memory/ 全量治理 | 2026-07-19 | `-` |
| C-067 | 文档 | spec-39: docs/ + .ai-memory/ 内容同步 | 2026-07-19 | `-` |
| C-068 | 文档 | spec-41: 文档健康检查器 | 2026-07-19 | `-` |
| C-069 | AI | spec-42: 自我进化飞轮 | 2026-07-19 | `-` |
| C-070 | AI | spec-43: 遗忘机制 | 2026-07-20 | `-` |
| C-071 | 文档 | spec-44: 月度检查瘦身 | 2026-07-20 | `-` |
| C-072 | 文档 | spec-45: 月度检查自动化 | 2026-07-20 | `-` |
| C-073 | 文档 | spec-46: d4_path_drift 降级 | 2026-07-20 | `-` |
| C-074 | 文档 | spec-47: TD-279 lessons 路径漂移修复 | 2026-07-20 | `-` |
| C-075 | 文档 | spec-48: P1 批量修复 | 2026-07-20 | `-` |
| C-076 | AI | spec-49: AI 自决框架加固 | 2026-07-20 | `-` |
| C-077 | 文档 | spec-50: d7 检查器范围修复 | 2026-07-20 | `-` |
| C-078 | 文档 | spec-51: architecture-mistakes.md 清理 | 2026-07-20 | `-` |
| C-079 | 测试 | spec-52: 测试副作用残留清理 | 2026-07-20 | `-` |
| C-080 | AI | spec-53: L3-4 [B] 类纳入 + d4/d7 治理 | 2026-07-20 | `-` |
| C-081 | TD | spec-54: TD-281 迁移 + 5 新 TD 登记 | 2026-07-20 | `-` |
| C-082 | 前端 | spec-36: a11y 治理 | 2026-07-20 | `-` |
| C-083 | 文档 | spec-38: hook 差异化校验 | 2026-07-20 | `-` |
| C-084 | TD | spec-39: 小 TD 批量治理 | 2026-07-20 | `-` |
| C-085 | 后端 | spec-40: TD-288 AgentSelector cleanup | 2026-07-20 | `-` |
| C-086 | 后端 | spec-41: TD-277 accounts→agents 解耦 | 2026-07-20 | `-` |
| C-087 | 后端 | spec-44: TD-273 Phase 2 字符串迁移 | 2026-07-20 | `-` |
| C-088 | 后端 | spec-45: TD-291 screenshot_retention 实施 | 2026-07-20 | `-` |
| C-089 | 协议 | spec-42: TD-287 message_compressor 接入 | 2026-07-20 | `-` |
| C-090 | 后端 | spec-43: TD-289 静默吞异常修复 | 2026-07-20 | `-` |
| C-091 | 后端 | spec-55: TD-293 view 层异常分级治理 | 2026-07-20 | `-` |
| C-092 | 后端 | spec-56: L3-1 [A] 类批量修复 | 2026-07-20 | `-` |
| C-093 | 后端 | spec-57: TD-295 RBAC + DB 性能治理 | 2026-07-20 | `-` |
| C-094 | 后端 | spec-58-A: TD-296 cleanup_view atomic | 2026-07-21 | `-` |
| C-095 | AI | spec-59-A: AI 思维链纠偏 + 反思分级 | 2026-07-21 | `-` |
| C-096 | 后端 | spec-58-B: TD-301 celery task retry 补齐 | 2026-07-21 | `-` |
| C-097 | 文档 | spec-59-B: TD-302 规则文档瘦身 v9.2 | 2026-07-21 | `-` |
| C-098 | 文档 | spec-59-C: TD-303 工作流节奏调整 | 2026-07-21 | `-` |
| C-099 | 文档 | spec-59-D: TD-298 规则退役 | 2026-07-21 | `-` |
| C-100 | 后端 | spec-59-E: TD-297 集成层一致性治理 | 2026-07-21 | `-` |
| C-101 | 文档 | spec-60: TD-307 failure-modes 阈值调整 | 2026-07-21 | `-` |
| C-102 | 前端 | spec-63: TD-304 前端 raw fetch 鉴权 | 2026-07-21 | `-` |
| C-103 | AI 架构 | LangGraph ReAct Agent | 2026-07-14 | (见 detail) |
| C-104 | 仓库治理 | Repo cleanup: scripts/ 重组 | 2026-07-12 | `-` |
| C-105 | 仓库治理 | N150 fix: gaf_init.sh evidence dir | 2026-07-12 | `-` |
| C-106 | 任务调度 | TaskChain 执行器 (TD-096 ✅ FIXED) | 2026-07-12 | `-` |
| C-107 | 窗口中心化 | 窗口中心化 v3 阶段 1-5 | 2026-07-13 | (多 commit) |
| C-108 | AI 架构缺陷修复 S1 | Skill 执行路径 | 2026-07-14 | `-` |
| C-109 | AI 架构缺陷修复 S2 | AgentLLMClient + debug 模式 | 2026-07-14 | `-` |
| C-110 | AI 架构缺陷修复 S3 | RAG 接入 + Celery 异步化 | 2026-07-14 | `-` |
| C-111 | 测试体系 | E2E 用例持久化：full_routes 47 路由真实无头 smoke + run_all 11 场景全绿(128s) | 2026-08-28 | `-`+`-` |
| C-112 | 测试修复 | E2E 首跑修复批（F1-F11/M1-M8 19 项：渲染崩溃×4 / ADB WS 握手 / replay 404 / 分组/标注/通知 / i18n 等） | 2026-08-28 | `-` 等 |
| C-113 | 资源 | R37-P2 模板匹配预览真实化（后端 cv2.matchTemplate 端点 + 标注页当前帧/裁剪接入） | 2026-08-28 | `-` |
| C-114 | 文档治理 | docs/business 全量一致性修复(13 份/40+ 处) + specs 21 份归档(active 清空) + 新教训 4 条(N212-N215) 沉淀 | 2026-08-28 | `-` 等 |

</details>

---

## 🐛 技术债务

<details>
<summary>✅ 已修复技术债务 (147+ 项，截至 TD-414) — 展开查看（节选）</summary>

| TD | 摘要 | 修复时间 |
|:---|:---|:--------|
| [TD-414](archive/fixed-tech-debt.md) | 2026-08-27/28 治理批收尾（含 TD-412/413 等） | 2026-08-28 |
| [TD-362](archive/fixed-tech-debt.md) | 移除 'chain' 执行模式兼容分支 | 2026-08-09 |
| [TD-361](archive/fixed-tech-debt.md) | 全屏检测缺 MonitorFromWindow | 2026-08-09 |
| [TD-360](archive/fixed-tech-debt.md) | ADB 坐标转换不支持旋转/DPI | 2026-08-09 |
| [TD-359](archive/fixed-tech-debt.md) | FramePool 无帧有效性校验 | 2026-08-09 |
| [TD-358](archive/fixed-tech-debt.md) | WindowMonitor 启动时旧线程未停止 | 2026-08-09 |
| [TD-357](archive/fixed-tech-debt.md) | 截图流 start 时旧线程未停止 | 2026-08-09 |
| [TD-356](archive/fixed-tech-debt.md) | 截图流实时性不足 — 固定 1 秒间隔 | 2026-08-09 |
| [TD-355](archive/fixed-tech-debt.md) | Pipeline validate/estimate-time 路由 Bug | 2026-07-11 |
| [TD-353](archive/fixed-tech-debt.md) | PipelineEngine 超时后后台线程仍运行 | 2026-08-08 |
| [TD-352](archive/fixed-tech-debt.md) | 进程管理缺乏守护进程 | 2026-08-08 |
| [TD-351](archive/fixed-tech-debt.md) | TaskExecution 大表无归档策略 | 2026-08-08 |
| [TD-350](archive/fixed-tech-debt.md) | 节点类型硬编码，缺乏元数据注册 | 2026-08-08 |
| [TD-349](archive/fixed-tech-debt.md) | Service 层测试覆盖补全 | 2026-08-08 |
| [TD-348](archive/fixed-tech-debt.md) | 全仓扫描性能优化 | 2026-07-26 |
| [TD-346](archive/fixed-tech-debt.md) | governance_dashboard 计数不一致 | 2026-08-05 |
| [TD-345](archive/fixed-tech-debt.md) | pytest 全套超基线 | 2026-08-06 |
| [TD-344](archive/fixed-tech-debt.md) | governance-batch 性能优化 | 2026-07-26 |
| [TD-343](archive/fixed-tech-debt.md) | 低触发 lesson 归档 | 2026-08-06 |
| [TD-342](archive/fixed-tech-debt.md) | spec-context 承载体机制缺位 | 2026-07-26 |
| [TD-341](archive/fixed-tech-debt.md) | .ai-memory/ref/ 与 docs/ 职责合并 | — |
| [TD-340](archive/fixed-tech-debt.md) | (其他 223 项已修复) | — |

> 📝 完整 147+ 项列表见 [archive/fixed-tech-debt.md](archive/fixed-tech-debt.md)（索引截至 TD-414）

</details>

<details>
<summary>❌ WONTFIX/INVALIDATED/EVALUATED (34 项) — 展开查看</summary>

| TD | 摘要 | 状态 | 评估时间 |
|:---|:---|:---:|:--------|
| [TD-329](archive/wontfix-tech-debt.md) | spec-49 红线全脚本化 | INVALIDATED | 2026-07-22 |
| [TD-328](archive/wontfix-tech-debt.md) | gaf_init.sh 重写为 Python | WONTFIX | 2026-07-22 |
| [TD-322](archive/wontfix-tech-debt.md) | spec 编号归一 | WONTFIX | 2026-07-21 |
| [TD-290](archive/wontfix-tech-debt.md) | agent coord_transformer per-monitor | EVALUATED | 2026-07-20 |
| [TD-276](archive/wontfix-tech-debt.md) | executions list N+1 query | EVALUATED | 2026-07-20 |
| [TD-271](archive/wontfix-tech-debt.md) | 响应式设计缺失 | EVALUATED | 2026-07-20 |
| [TD-001](archive/wontfix-tech-debt.md) | WGC 截图 `E_NOINTERFACE` | WONTFIX | 2026-07-05 |
| [TD-010](archive/wontfix-tech-debt.md) | Backend 截图帧转发层未 dedup | INVALIDATED | 2026-07-06 |
| [TD-017](archive/wontfix-tech-debt.md) | sync_skills.py 漏校验 | INVALIDATED | 2026-07-07 |
| [TD-046](archive/wontfix-tech-debt.md) | tasks/migrations/ 累积 40 个 | EVALUATED | 2026-07-10 |
| [TD-085](archive/wontfix-tech-debt.md) | Agent 截图流 1s 间隔 | WONTFIX | 2026-07-13 |
| [TD-119](archive/wontfix-tech-debt.md) | Git 写命令需用户确认 | WONTFIX | 2026-07-18 |
| [TD-127](archive/wontfix-tech-debt.md) | ruff 剩余 60 处 errors | WONTFIX | 2026-07-18 |
| [TD-147](archive/wontfix-tech-debt.md) | 其他文件吞异常无日志 | WONTFIX | 2026-07-18 |
| [TD-148](archive/wontfix-tech-debt.md) | tasks → agents 反向依赖 | WONTFIX | 2026-07-18 |
| [TD-149](archive/wontfix-tech-debt.md) | migration 文件膨胀 | WONTFIX | 2026-07-18 |
| [TD-151](archive/wontfix-tech-debt.md) | 前端无障碍属性缺失 | WONTFIX | 2026-07-18 |
| [TD-152](archive/wontfix-tech-debt.md) | 前端响应式布局不完整 | WONTFIX | 2026-07-18 |
| [TD-153](archive/wontfix-tech-debt.md) | agent msg_type 裸字符串 | WONTFIX | 2026-07-18 |
| [TD-154](archive/wontfix-tech-debt.md) | 测试 mock 缺注释 | WONTFIX | 2026-07-18 |
| [TD-155](archive/wontfix-tech-debt.md) | 文档 URL drift | WONTFIX | 2026-07-18 |
| [TD-210](archive/wontfix-tech-debt.md) | spec Phase 2/3/4 未完成 | WONTFIX | 2026-07-18 |
| [TD-215](archive/wontfix-tech-debt.md) | L3-1 状态追踪缺位 | WONTFIX | 2026-07-18 |
| [TD-254](archive/wontfix-tech-debt.md) | brainstorming skill 无引用 | WONTFIX | 2026-07-18 |
| [TD-255](archive/wontfix-tech-debt.md) | N166 不进 arch-mistakes | WONTFIX | 2026-07-18 |
| [TD-085](archive/wontfix-tech-debt.md) | Agent 截图流 1s 间隔 | WONTFIX | 2026-07-13 |

> 📝 完整 34 项列表见 [archive/wontfix-tech-debt.md](archive/wontfix-tech-debt.md)

</details>

---

## 📋 活跃 Spec / Plan

<details>
<summary>展开查看</summary>

### 📂 Specs (规格说明)

- **活跃 Specs**: 0
- **最近归档 Specs**: 2026-08-09 [td335-frontend-architecture-remaining.md](specs/archived/2026-08/2026-08-09-td335-frontend-architecture-remaining.md)

> **注意**: Plans 目录已合并到 Specs，所有历史 plan 内容与对应 spec 重复，不再独立维护。

</details>

---

## 📊 月度健康报告

> 月度健康检查的历史报告归档，详见 [检查指南](health/procedure.md)。

| 月份 | 通过率 | 风险等级 | 关键发现 |
|------|--------|----------|----------|
| [2026-07](archive/2026-07-health-report.md) | 60.9% | 中 | 首次基线检查；Win32 API 泄露 2 处 + npm 3 high 漏洞 + ruff 709 errors + 14 个失败测试 |
| [2026-08 (模板)](archive/2026-08-health-report.md) | 待填 | 待填 | 待 2026-08-31 执行月度检查后填充 |

---

## 🔄 维护规则

1. **每轮 plan 实现完成后**，AI 必须检查此文件并更新状态
2. **新功能待办**登记到「活跃待办」段
3. **技术债务**登记到 [archive/active-tech-debt.md](archive/active-tech-debt.md)
4. **完成后**从「活跃待办」移入「已完成项目」，并附 commit hash
5. **技术债务修复后**迁移到 [archive/fixed-tech-debt.md](archive/fixed-tech-debt.md)

---

## 📚 相关文件

- [活跃技术债务](archive/active-tech-debt.md)
- [已修复技术债务](archive/fixed-tech-debt.md)
- [WONTFIX 技术债务](archive/wontfix-tech-debt.md)
- [已归档 Specs](specs/archived/)
- [健康检查指南](health/procedure.md)
- [月度健康报告](archive/)
- [项目历史归档](archive/)