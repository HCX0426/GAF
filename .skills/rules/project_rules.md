# GAF 项目开发规则

> **瘦身版 (TD-369)**: 只保留"宪法"级硬约束 + 索引指针；背景/根因外迁 lessons/failure-modes.md/yn-matrices。禁止写回背景。
> **注入预算**: 本文件 ≤ 14KB + env-hardrules.md ≤ 4KB，超限由 governance hook 阻塞。

## AI 元规则文件导航
**5 层**: rules=宪法+指针 / handbook=L2 / failure-modes=N## 索引 / yn-matrices=Y/N / lessons=历史；决策树权威源=`gaf-orchestrator/SKILL.md`（加载顺序见 handbook Part 1）。
## 0. 执行宪法

| 任务规模 | 三份核心文档 | 教训文档 | 通用规范 | 七维度评估 | 反思分级 | 测试分级 | 加载分级 | 用时测量 |
|---------|------------|---------|---------|-----------|--------|--------|--------|----------|
| **小修改** (typo/1-3 行/配置调整) | 跳过 | 跳过 | 跳过 | 豁免 | 豁免 | pytest + lint (<60s) | 跳过 L1/L2 | 豁免 |
| **中修改** (加 API/组件/修 bug) | 读相关章节 | lessons/README + summaries 按需 | 读对应 1 份 | 跑 3 维 (1/2/7) | 5 项反思 | 加集成 (<120s) | L2 按需 + L3 按需 | commit 时测 |
| **大修改** (跨模块/架构/新功能) | 完整阅读 | lessons/README + summaries | 读对应规范 | 跑 7 维 + 架构盘点 | 全套 + L1 分发 | 全套 `-n 8` (<600s) | L1 + L2 硬加载 + L3 按需 | commit 时测 |

> **规模分级单一权威源**: §0 上表唯一权威源（§4.6 反思/§4.9 测试/N177/N179 行数判定均引用来），禁止别处重定义阈值（行数 50/500、文件数 1-3/4-10/>10）。

**小修改快速路径**: 决策树 step_1 → 改码 + `git add`+`git commit`+`git log --oneline -1` → 完成（跳过加载/评估/反思）。
**三份核心文档**: docs/architecture/ 下 optimal-solution（为什么）/ features-overview（做什么）/ overview（怎么做）。

**核心约束**:
- GAF 只控制 PC 窗口（Win/macOS/Linux）+ 模拟器（ADB），不需要手机端
- 新模块必须定义跨平台抽象接口，Windows 专用代码封装在 `worker/src/platforms/windows/` 和 `backend/device_bridge/platforms/windows/`；禁止业务逻辑直接调用 Win32 API
- 禁止自行发明截图/输入/任务引擎方案；状态标记诚实：✅可用 / 🔧代码存在 / ❌未实现
- 技术债务不堆积：发现违背约束的既有代码当次任务内迁移/修复；教训入口 `.ai-memory/lessons/`

**通用规范** (写码前必读对应): 前端 `docs/standards/frontend-conventions.md` / 后端 `backend-conventions.md` / API `api-contract.md` / 测试 `testing-conventions.md`。
**开发工作流（强制）**: 任何代码/功能/Bug 修复/测试任务开始前，必须先调用 `Skill(name="gaf-orchestrator")` 加载决策树。不可跳过。

## 0.5 计划制定流程（大修改强制，中小修改豁免）

8 步: 决策树入口 → 文档审视 → 架构盘点(N151) → 识别反模式 → A/B/C 备选 → 七维度评分(N167, 总分≥19 且领先≥5 自决, 否则问用户) → 拒绝双套/最小化, KEEP 合法 → Plan 批准(大改确认/中改 todo/小改直接做)。

## 1. 项目环境

> conda gaf 环境硬约束权威源在 `env-hardrules.md`。本节仅速查。

- conda 环境 `gaf`；始终用 `main` 分支；backend :8000 / frontend :5173（代理指向 8000）
- 测试账号 `admin`/`admin123`；默认终端 PowerShell 7.x
- 后端和前端**独立终端**分别启动，不可合并
- 打开 GAF 界面必启动 console_monitor.py（`scripts/e2e/scenarios/`）+ 每 2-5min Read log
- Agent 默认关闭由 backend 自动拉起；测试时 `$env:GAF_AUTO_START_AGENT=1`；backend .py 编辑不需确认
- Vite dev proxy 用 `127.0.0.1`；worker 单例锁/heartbeat 见 lessons/N186-agent-standalone-process-no-pid-lock.md
- 所有服务统一 conda gaf 环境；禁止手动 `python -m src`，必须 `gaf_services.ps1` 管理
- 临时文件 → `.trash/`；工具缓存 → `.cache/`；pytest/mypy/ruff 从仓库根目录跑

## 2. 代码规范

- 注释英文；保持现有风格；避免硬编码；文件名禁带 `v1/v2/v3`
- **质量三原则**: 扩展性 / 逻辑正确性 / 命名正确性
- **硬约束**: 改动范围由正确性决定 / 反模式根因修复 / ❌ 下游 workaround / ❌ 测试用非法 choices
- **URL 路由约定**: app 多资源挂 `f"{API_PREFIX}/"`；单资源且 app 名=资源名挂 `f"{API_PREFIX}/<app>/"`；禁止挂载前缀与资源路径重复

### 2.0.x 强制原则（详细矩阵见 yn-matrices 对应分片）

- **大修改架构视角（N151）**: >500 行 diff/架构变更/跨模块/DB 迁移/API 契约变更前必跑 5 步；禁止双套并存、最小化修补自决
- **七维度评估（N167）**: 小豁免 / 中跑 3 维 (1 架构长远性/2 全局归一化/7 长期维护成本)，bug 修复跑 1/2/4/7 / 大跑 7 维；不得默认"最小改动"。清单见 `_refactor-dimensions.md`
- **节点截图归一化 + 契约文档化（spec-88/TD-336）**: 识别节点自给自足（节点内 `device.capture_screen()`，context 仅 override），context 依赖节点须 device fallback，wait 截图写回 context；节点类型明示截图模式/前置要求/能力边界三项契约，新增节点必更新，详见 `docs/business/tasks/pipeline-authoring-guide.md` §2.8

### 2.1 文档分层与归属（强制 — N200）

| 层级 | 路径 |
|:----:|------|
| AI 元规则 | `.skills/rules/` |
| AI skills | `.skills/skills/`（只允许 SKILL.md，❌ spec/plan/design） |
| AI 工作产物 | `docs/specs/active/`、`docs/architecture/` |
| AI 记忆 | `.ai-memory/`；项目级跨 app → `docs/`；后端子 app 约定 → `backend/<app>/README.md` |

创建新文档前自问归属（Skill 定义 → `.skills/skills/`；执行产物 → `docs/specs/active/`）。Spec 完成即归档 `docs/specs/archived/YYYY-MM/` + 更新状态 + Skill 引用。

## 3. Git 操作规范（强制）

### 3.1 禁止（destructive 永远禁止）
- 禁止 AI 主动 git 回退（reset/revert/回退 checkout 只能用户手动）；禁止 force push；禁止 amend 已 push commit；禁止读旧版本覆盖当前文件；AI 不可 push 到远程（除用户显式要求）

### 3.2 允许（AI 可自执行）
- `git add` + `git commit`（按 §3.4 粒度）；只读命令；`git stash` / `stash pop` / `checkout -b`
- `--no-verify` 仅限透传 bug 场景；禁止绕过其他 pre-commit 失败

### 3.3 pre-commit 失败处理（强制）
- 必须根因修复后重试；预存错误当场处理（修复或登记 active-tech-debt）
- 修 bug 时检查同类问题其他文件 + 上下游链路归一化评估
- GAF Python hooks 必须 `language: python`；manual-stage lint hooks 用 `language: system`

### 3.4 提交纪律
- 按 spec 粒度提交：同一 spec 全部阶段完成后 1 次 commit；各阶段只 add 不 commit；**spec 完成即 commit（自决不问用户），commit 后停下等用户再开下一 spec**——"完成即提交 vs 完成后停下"唯一定义
- 分段提交（>500 行/跨模块/DB 迁移/API 契约）保证回滚精度
- commit 前必本地验证（lint + test + sync 或显式标注已知问题）；必 `git status` 二次确认无未暂存残留
- message 格式 `<type>(<scope>): <subject>`（type ∈ feat/fix/refactor/docs/test/chore/perf/build/ci）；单行 `-m` 优先，多行多个 `-m` flag，禁 `-F <file>`；commit 后必 `git log --oneline -1` 验证
- ❌ 空 commit / 敏感文件 commit（先加 .gitignore）/ message 写 N## 声称（M2 核验 diff 证据，无证据阻塞）
- **N176**: 一次对话内多 spec 合并 1 次 commit；hash 回填 spec 文件；message 含所有 spec 名
- **TD-380 元数据 commit 收敛**: 每 spec ≤1 条 metadata commit — 归档+hash 回填+状态表更新+active 副本移除合为 1 条 `docs(sXX): archive + hash backfill + features record` commit（紧邻功能 commit 后）；禁止拆多条 docs commit；`auto_archive_specs.py` 仅检查不自动提交

### 3.5 需用户授权 vs 自决
- ❓ 授权: push 远程 / pull --rebase 跨分支 / remote add / 不可逆删除（branch -D / tag -d / stash drop / clean -f / API DELETE / DB DROP）
- ✅ 自决: 重写 history（需无未保存变更+执行后验证）；本地文件删除（git 追踪可恢复；`.trash/`+`.cache/` 直接删；未追踪重要文件先问）

### 3.6 AI 自决范围
> 权威源: handbook Part 2 自治边界段；详细 Y/N 见 `_ai-autonomy.md`

- 计划内任务完全自治（选任务/拆子任务/写代码/commit/推进下一段）；spec 内自决推进；完成后默认停下等用户（报告 hash+evidence+候选下一个）
- ≥2 个独立任务主动并行 subagent；落地检查：数量一致 + 抽查 1 文件 + prompt 含 3 条规则摘要
- spec 内偏离阈值：Phase 数 +50% 或 diff +30% 必更新 deviation log；+100% 不更新 → 停下问用户

### 3.7 L3 循环模式（被动触发）
- 流程: 扫描 9 维度 → 分级 [A]立即修/[B]登记 TD/[C]wontfix → [A] 开 spec → 终止判定 → 实测验证 → 七维度评估
- 终止条件: 连续 2 轮无新增 [A]+[B] / ≥15 轮上下文告警 / 用户叫停 / 连续 2 spec 强制停下 / 弱触发 1 spec 后停
- 涉及 UI/WS/Agent 修改才启动浏览器实测；纯逻辑跑 pytest 即可

### 3.8 沉淀纪律: 判定（1 问）: 下次对话 AI 是否需遵守？→ 是 → 立即落盘，非必要不沉淀
- 沉淀位置: 工作模式/流程 → rules+handbook；反模式 → failure-modes+lessons+yn-matrices（仅 L1-大）；架构原则 → rules §2.0.x；命令用法 → handbook Part 2
- ❌ 只写 lessons 不更新 rules / 先执行再沉淀 / 假沉淀

## 4. 变更操作规范

### 4.1 删除 / 文档驱动 / 浏览器测试
- 删除优先 Move-Item 到 `.trash/`（已 gitignore）；删除前评估影响范围
- 重构/新功能前读三份核心文档相关章节；文档与代码不一致以文档为准；严格遵循 api-contract + frontend-conventions
- browser-use 测试必须点击全部交互元素，每类至少一次；结果表格记录 ✅/❌ + JS 错误数

### 4.5 同步检查（强制）
- 修改完成后必跑同步更新检查（引用路径/计数/状态标记/TD 状态迁移）
- 同步三层次: 立即同步（引用/计数/状态/TD 迁移出 active.md）→ 同 spec 内（跨文件引用/索引）→ 跨 spec 待办（登记 active-tech-debt）
- TD 修复 commit 时必把段落从 active.md 剪切到 fixed.md/wontfix.md；禁止原地标 ✅ 不迁出
- 工具: `sync_ai_memory.py` / `sync_skills.py --check` / `check_yn_matrices_index.py` / `check_path_consistency.py`

### 4.6 反思分级（强制）
- 反思分级见 §0 执行宪法规模表（小豁免 / 中 5 项反思 / 大 全套 + L1 分发）；行数口径: 小 <50 / 中 50-500 / 大 >500 行；"无 A 类"必填"已检查 X 项反模式均不适用"
- 问题分类 [A]/[B]/[C] 必落地；大修改后更新 completed-features + pending-roadmap
- M2 复盘: REVIEW_TRIGGERED 或激活率 <50% → 必按 Q1-Q4 模板复盘写回 claimed-activation.md，否则 pre-commit 阻塞（详见 handbook Part 2）

### 4.8 技术债务（强制）
- 范围外 TD 必登记 active-tech-debt.md（症状/根因/影响/修复方案/**验证标准**/何时修/三维根因评估/登记时间）；编号分配前 grep 三文件确认未占用
- 修复后 ✅ FIXED + hash + evidence 并迁出；debt 留 🔧 不超 3 轮，每轮 plan 后挑 1-2 个推进
- Debug 模式节点失败先穷尽自动修复再通知用户；"延后"= 完成上一 spec 立即接着做

### 4.9 阶段验收 + 测试分级（强制）
- 大阶段完成必跑阶段验收（3 步验证）；全部完成必跑全量回归；evidence 落地 completed-features.md
- 用时测量: 必记 start_ts/end_ts/duration 对照基线（小<5/中<15/大<60 min），超基线根因检查
- 测试分级见 §0 执行宪法规模表（小 pytest + lint / 中加集成 / 大全套 `-n 8`）；agent chain e2e 至少 1 冒烟；循环模式每 2 spec 全套回归

### 4.10 Spec 分阶段（复杂修复 >1500 行 diff 时）
- 拆多阶段（单阶段 <1500 行 diff）+ spec 首部"阶段状态表"；单文件多阶段不拆多文件
- 每阶段完成更新: 状态表 + completed-features + pending-roadmap；新对话续接从第一个 ⏳ 开始
- 上下文预算: `--tb=short -q`；E2E 调试 ≤2 轮；≥15 轮提示新对话

### 4.11 元评估闭环（强制）
- 元评估弱项必须二选一: 开 spec 修复（≤5 项且 <500 行）或登记 TD（何时修必填明确触发点）；报告必填弱项/根因/建议/闭环路径
- 触发: 用户显式要求 / 连续 2 spec 强制停下时 / 月度 health-check

### 4.12 N## 出清机制（强制 — v9.2 Spec A）
- **Active 硬上限 35 条**（promote_lessons.py `ACTIVE_N_CAP`）：超限时机械出清最陈旧条目到 archived-lessons.md
- 出清判据（全满足）: last_triggered >30 天 && trigger_count ≤5 && 未被 rules 层引用（调参: 60→30 / 3→5）；棘轮语义——有候选未清则 check-cap 阻塞 commit，无可候选放行；编号永不复用
- **新增门槛（强制 — 治理瘦身 gate-1）**: 新 N## 入库前必问"未来 30 天会触发 ≥3 次吗?"；不会 → 只进 lessons/，不进 rules + Active 索引；防"一次性事故 → 永久规则"膨胀；退役判据同 §4.12

## 5. 工具使用规范
- HTTP 用 `Invoke-WebRequest`；单行命令用 `;` 连接；多行 Python 写临时 .py 执行
- 教训加载/收集: `gaf-lesson-router load: <scope>` / `collect`
- 命令/脚本/性能测量完整细节见 handbook Part 2（命令使用 N111/N153/N160 + 脚本性能测量 N171 段）

## 6. 教训分发机制（指针）
> 权威源 = handbook Part 1（加载机制 + 分级分发表 + promote 闭环 + N## 归档流程）。查 N## → failure-modes.md；查 Y/N → yn-matrices；新 L1 按 handbook 分发。
- spec-context 承载体（B2 大修改）: 必写 `docs/archive/spec-context/<spec-name>-context.md`（用户决策/N151 评估/N167 评分/关键决策/用时），pre-commit 强制；豁免小修改/纯文档/hotfix
