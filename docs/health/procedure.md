---
summary: GAF 月度健康检查指南 — 全面 19 类可执行检查项 (G 类已迁自动 spec-41, C1/H1/I1/N1 已迁自动 spec-45, 月度跑 74 项)
applies_to: [backend, frontend, agent, project]
last_updated: 2026-08-28
---

> **spec-44 迁移说明 (2026-07-20)**: G 类 (文档与 AI 记忆一致性) 8 项已迁自动,
> 由 `scripts/governance/doc_health_check.py` (spec-41) 7 维度静态检查覆盖,
> 通过 `gaf_init.sh` 在每次对话开头自动跑。月度检查时**跳过 G 类**, 只跑其他 18 类 (76 项)。
>
> 迁移映射 (G 项 → spec-41 维度):
> - G1 (docs/ 索引校验) → d7_index_consistency + d5_frontmatter
> - G2 (AI 记忆同步校验) → sync_ai_memory.py (gaf_init.sh 自动跑)
> - G3 (Skills 副本一致性) → sync_skills.py (pre-commit 自动跑)
> - G4 (lessons/ front-matter 完整性) → d5_frontmatter
> - G5 (failure-modes.md 索引完整性) → d7_index_consistency + d3_count_drift
> - G6 (规则/文档引用 skill 存在性) → d4_path_drift
> - G7 (规则/文档引用 path 存在性) → d4_path_drift
> - G8 (docs/ 引用脚本存在性) → d4_path_drift
>
> 详见 `docs/specs/legacy-trae/2026-07-20-spec44-monthly-check-slimming.md`。

> **spec-45 迁移说明 (2026-07-20)**: C1/H1/I1/N1 4 项已迁自动,
> 由 `scripts/governance/monthly_health_check.py` (spec-45) 4 项项目卫生检查覆盖。
> 月度检查时**跑** `monthly_health_check.py` 后跳过这 4 项手动检查。
>
> 迁移映射 (项 → spec-45 检查):
> - C1 (活跃 TD 数量) → check_c1_active_td (active.md 统计)
> - H1 (Git 工作树状态) → check_h1_git_status (git status + 敏感文件)
> - I1 (巨型文件检测) → check_i1_large_files (per_dir 阈值, 跳过 .generated.)
> - N1 (空目录扫描) → check_n1_empty_dirs (含空文件检测, N2 合并到 N1)
>
> 跑法: `python scripts/governance/monthly_health_check.py` (输出 `.cache/monthly_health_report.json`)
>
> 详见 `docs/specs/legacy-trae/2026-07-20-spec45-monthly-check-automation.md`。

# GAF 月度健康检查指南 (Monthly Health Check)

> **目的**：每月对项目做一次全面体检，及早发现漂移、堆积和退化，防止小问题滚成大问题。
>
> **适用场景**：月度例行检查 / 季度深度审计 / 版本发布前验收。
>
> **执行者**：AI（收到本文件作为任务时）或开发者手动执行。
>
> **输出**：检查报告追加到 `docs/health/YYYY-MM.md`。

## 执行流程

1. AI 收到"执行月度健康检查"指令时，加载本文件
2. 按 A-S 顺序逐类执行检查，每项记录 ✅ / ❌ / ⚠️ + 实测数据 (**跳过 G 类, 已由 gaf_init.sh 自动跑; C1/H1/I1/N1 跑 monthly_health_check.py 后跳过**)
3. 对 ❌ / ⚠️ 项附根因初判和修复建议
4. 统计汇总（通过率 / 失败项 / 需关注项）
5. 输出报告到 `docs/health/YYYY-MM.md`（不存在则创建）
6. 在对话中输出摘要（总项数 / 通过 / 失败 / 需关注 + 关键风险）
7. **迭代回顾**：检查完成后，回顾本次发现的所有 ❌ / ⚠️ 项，评估是否有新的问题类型需要加入检查项（见下方"迭代机制"）

## 迭代机制 (Iterative Mechanism)

> **核心原则**：检查项不是固定的，每次检查后应根据发现的新问题类型动态扩充。

### 迭代流程

1. **检查完成** → 回顾所有 ❌ / ⚠️ 项
2. **根因分类** → 每个问题的根因是否属于已有检查项的覆盖范围？
3. **补充检查项** → 如果根因是已有检查项未覆盖的新类型，添加新检查项到本文件
4. **记录历史** → 在"检查项变更历史"段记录本次新增的检查项 + 触发原因
5. **更新计数** → 更新"检查项总览"表的总数

### 新增检查项判定标准

| 判定 | 说明 | 示例 |
|------|------|------|
| ✅ 应新增 | 问题根因是已有检查项未覆盖的模式，未来可能重复出现 | 测试 URL 路径与 API 路径不一致 → 新增 B5 |
| ❌ 不新增 | 问题是一次性事件或已有检查项已覆盖 | 单个 typo 导致的 import 错误 → 已被 B1 覆盖 |

### 检查项变更历史

| 日期 | 新增项 | 触发原因 |
|------|--------|----------|
| 2026-07-11 | B5, B6, B7, I5, I6, I7 | 首次月度检查发现：测试 URL 路径不一致、测试导入路径过期、mock 属性缺失、base64 路径误判、资源未释放、重试装饰器与状态标志冲突 |
| 2026-07-11 | M1-M5, N1-N2, O1-O3 | 用户反馈：需要架构检查（平台抽象层、模块依赖方向、路由挂载规范、文档同步）、空目录/空文件检查、真实设备验证（雷电模拟器替代 mock） |
| 2026-07-11 | P1-P6 | 日志架构修复（dedup + 7天TTL + 实时广播 + 死代码清除）后，新增日志健康检查项，覆盖总量/保留期/dedup 有效性/TTL 任务/广播链路/高频错误聚集/死代码残留 |
| 2026-07-13 | Q1-Q3, R1-R5, S1-S2, F5, G6-G8, J5-J6 | 用户反馈：已删除的 ScreenStateEditor 英文硬编码、详情页编辑按钮跳回列表、Chrome 占不满浏览器、URL 双前缀、antd 弃用 prop、规则引用不存在 skill、记住账号 30 天失效 — 7 个问题均需界面点击才暴露，月度检查应前置拦截 |
| 2026-08-28 | M6, M7 | docs 全量逐模块内容级对拍 + 冲突标记清理（40+ 处事实断言偏差）暴露：d1-d8 / check_doc_code_sync / M5 只查结构/存在性/变更绑定，不查正文事实断言 — app 数 (16→17)、QA 端点 (sessions→qa-sessions)、hook 数、React 版本、WS 路径、status 枚举等长期漂移漏检 |

## 环境约定

- **conda 环境**：`gaf`（位于 `D:\code\environment\conda\envs\gaf`）
- **默认终端**：PowerShell 7.x
- **后端目录**：`backend/`
- **前端目录**：`frontend/`
- **Agent 目录**：`agent/`
- 命令中 `conda run -n gaf` 用于在 gaf 环境中执行 Python
- 前端命令需先 `cd frontend`

## 检查项总览

| 类别 | 名称 | 项数 | 预估耗时 |
|:----:|------|:----:|:--------:|
| A | 构建与类型检查 | 4 | 2 min |
| B | 测试套件 | 7 | 8-15 min |
| C | 技术债务状态 ✅ C1 已迁自动 (spec-45) | 4 (月度跑 3) | 1 min |
| D | 依赖管理 | 4 | 3 min |
| E | 数据库健康 | 3 | 2 min |
| F | API 契约一致性 | 5 | 6 min |
| G | 文档与 AI 记忆一致性 ✅ 已迁自动 (spec-41, 月度跳过) | 8 | 5 min |
| H | Git 卫生 ✅ H1 已迁自动 (spec-45) | 4 (月度跑 3) | 1 min |
| I | 代码质量 ✅ I1 已迁自动 (spec-45) | 7 (月度跑 6) | 6 min |
| J | 安全检查 | 6 | 4 min |
| K | 部署就绪度 | 3 | 2 min |
| L | 跨平台一致性 | 3 | 3 min |
| M | 架构一致性 | 5 | 5 min |
| N | 项目卫生 (空目录/空文件) ✅ N1 已迁自动 (spec-45) | 2 (月度跑 1) | 1 min |
| O | 真实设备验证 | 3 | 5 min |
| P | 日志健康 | 6 | 5 min |
| Q | 前端 i18n 完整性 | 3 | 5 min |
| R | 前端交互冒烟测试 | 5 | 7 min |
| S | 前端组件库兼容性 | 2 | 3 min |
| **合计** | | **86 (月度跑 74)** | **~90-105 min (月度 ~75-90 min)** |

---

## A. 构建与类型检查

### A1. Backend Django check
```powershell
cd D:\code\GAF\backend
conda run -n gaf python manage.py check
```
- ✅ 0 errors
- ❌ 记录错误数 + 具体错误信息

### A2. Frontend TypeScript 类型检查
```powershell
cd D:\code\GAF\frontend
npx tsc --noEmit
```
- ✅ 0 errors
- ⚠️ 有 errors 但能 `vite build`（记录数量，标注"预存错误"）

### A3. Frontend 生产构建
```powershell
cd D:\code\GAF\frontend
npx vite build
```
- ✅ 构建成功
- ❌ 构建失败（记录错误）
- ⚠️ `npm run build`（含 tsc）失败但 `npx vite build` 成功 = 预存 TS 错误

### A4. Agent 模块导入检查
```powershell
cd D:\code\GAF
conda run -n gaf python -c "import worker.src.core.orchestrator; print('OK')"
```
- ✅ 导入成功
- ❌ 导入失败（记录 ImportError / ModuleNotFoundError）

---

## B. 测试套件

### B1. Backend 测试
```powershell
cd D:\code\GAF\backend
conda run -n gaf python manage.py test --verbosity 1
```
- ✅ 全部通过
- ❌ 记录失败数 + 失败的测试名
- ⚠️ 有 skipped 测试（记录数量，检查是否应该 unskip）

### B2. Frontend 测试
```powershell
cd D:\code\GAF\frontend
npx vitest run
```
- ✅ 全部通过
- ❌ 记录失败数

### B3. Agent 测试
```powershell
cd D:\code\GAF
conda run -n gaf python -m pytest worker/tests/ -q
```
- ✅ 全部通过
- ❌ 记录失败数

### B4. 测试执行时间趋势
- 记录 B1/B2/B3 的执行时间
- 与上月报告对比（`docs/health/` 上月文件）
- ⚠️ 执行时间增长 > 20% 标注

### B5. 测试 URL 路径与 API 路径一致性
> **新增于 2026-07**：skills 测试用 `my_published` 但 API 用 `my-published` 导致 404

```powershell
# Grep 后端 @action url_path 声明
cd D:\code\GAF\backend
# 搜索 @action.*url_path 模式，提取 url_path 值
# 然后对比测试文件中的 URL 路径
```
- 检查所有 `@action(url_path='...')` 声明的 `url_path` 值
- 对比 `tests/` 目录中测试代码使用的 URL 路径
- ❌ 测试 URL 与 `url_path` 不一致（如 `my_published` vs `my-published`）= 404 bug
- 规范：DRF `url_path` 默认用方法名（下划线），自定义时统一用 kebab-case

### B6. 测试导入路径有效性
> **新增于 2026-07**：Devices 测试导入 `@/pages/Devices/index` 但文件已被拆分为多个页面

```powershell
# 检查前端测试文件中的 import 路径是否指向实际存在的文件
cd D:\code\GAF\frontend
# 搜索测试文件中的 import ... from '@/pages/...' 和 from '@/components/...'
```
- 逐个验证测试文件中的 import 路径对应的文件是否存在
- ❌ import 指向不存在的文件 = 页面重构后测试未同步更新
- 重点检查：页面拆分/合并后、组件目录调整后的测试导入

### B7. Store/Provider Mock 完整性
> **新增于 2026-07**：Dashboard 测试 mock useDeviceStore 缺少 `devices` 属性导致 `undefined.forEach` 报错

- 检查测试中 `vi.mock('...store...')` 返回的 mock 对象
- 对比被测组件从 store 中解构的所有属性
- ❌ mock 缺少组件访问的属性 = `TypeError: Cannot read properties of undefined`
- 检查清单：`agents` / `devices` / `groups` / `loading` / `fetchXxx` 等常见属性

---

## C. 技术债务状态

### C1. 活跃 TD 数量 ✅ 已迁自动 (spec-45, 2026-07-20)

> **✅ 已迁自动 (spec-45)**: check_c1_active_td (monthly_health_check.py)
> 跑法: `python scripts/governance/monthly_health_check.py`
> 阈值: >5 P2 warning, >10 P1 critical (thresholds.yaml `monthly_checks.c1_active_td`)

```powershell
# 读取 docs/archive/active-tech-debt.md，统计 🔧 待修 + 🚧 进行中 条目数
```
- 记录活跃 TD 数量
- ⚠️ 活跃数 > 5 需关注
- ❌ 活跃数 > 10 需立即清理

### C2. 超 3 轮未处理的 🔧 待修项
- 逐条检查 active-tech-debt.md 中每个 🔧 条目的"登记时间"
- ❌ 任何条目登记超过 3 轮（约 3 个月）未处理 = 违反 project_rules.md §4.8.1

### C3. 本月 TD 变动统计
- 统计 `fixed-tech-debt.md` 中本月新增的 ✅ 条目数
- 统计 `active-tech-debt.md` 中本月新增的 🔧 条目数
- 计算"修复率" = 本月修复 / (本月修复 + 本月新增)

### C4. TD-046 长期遗留项状态
- 检查 `docs/archive/wontfix-tech-debt.md` 中 TD-046（tasks/migrations squash 评估）状态
- 如仍为 ❌ EVALUATED，确认是否有新的 squash 时机

---

## D. 依赖管理

### D1. Python 过期依赖
```powershell
conda run -n gaf pip list --outdated --format=columns
```
- 记录过期依赖数量
- ⚠️ 安全相关依赖（cryptography / pyotp / requests）过期需优先更新

### D2. npm 过期依赖
```powershell
cd D:\code\GAF\frontend
npm outdated
```
- 记录过期依赖数量
- ⚠️ React / antd / vite 大版本落后需关注

### D3. npm 安全漏洞
```powershell
cd D:\code\GAF\frontend
npm audit
```
- ✅ 0 vulnerabilities
- ❌ 记录 high / critical 漏洞数
- ⚠️ low / moderate 漏洞记录但可推迟

### D4. 库版本冲突检查
- 对照 `.ai-memory/summaries/library-conflicts.md` 检查是否有新的冲突
- 确认 `backend/requirements/base.txt` 与 `worker/requirements.txt` 的共享依赖（如 cryptography / opencv-python）版本范围是否一致

---

## E. 数据库健康

### E1. Migration 应用状态
```powershell
cd D:\code\GAF\backend
conda run -n gaf python manage.py showmigrations
```
- ✅ 所有 migration 标记 `[X]`
- ❌ 有 `[ ]` 未应用的 migration

### E2. Migration drift 检测
```powershell
cd D:\code\GAF\backend
conda run -n gaf python manage.py makemigrations --dry-run
```
- ✅ "No changes detected"
- ❌ 有未生成的 migration（模型与 migration 不一致）

### E3. 迁移文件数量趋势
- 统计各 app 的 migration 文件数
- 与上月对比
- ⚠️ 单个 app migration > 30 个需评估 squash

---

## F. API 契约一致性

### F1. Serializers 与前端类型同步
```powershell
# 检查 frontend/src/types/api.generated.ts 是否存在且最近生成
cd D:\code\GAF\frontend
npm run generate:api-types
git diff src/types/api.generated.ts
```
- ✅ 无 diff（类型已是最新）
- ⚠️ 有 diff（类型已过期，需提交）

### F2. URL 路由冲突检查
```powershell
# Grep 检查每个 app 的 urls.py，确认显式 path() 在 include(router.urls) 之前
# 搜索模式：include\(router.urls\) 之前的 path() 声明
```
- 抽查 `pipeline/urls.py`（TD-074 修复点）、`tasks/urls.py`、`agents/urls.py`
- ❌ 发现 `include(router.urls)` 在显式 `path()` 之前 = 潜在 405 bug

### F3. 权限矩阵一致性
- 检查所有 ViewSet 是否有 `get_permissions` 覆写
- 对照 `PipelineViewSet` / `RecordingViewSet` / `TaskChainViewSet` 模式（viewer 可读，operator+ 可写）
- ❌ 发现 ViewSet 对所有 action 用同一权限 = 潜在权限过严 bug（TD-078 模式）

### F4. DRF 分页配置
- Grep 检查所有 ViewSet 是否显式声明 `pagination_class`（N152 教训）
- 或确认全局 `DEFAULT_PAGINATION_CLASS` 已配置
- ❌ ViewSet 返回数组但前端期望 dict（分页不匹配）

### F5. URL 双前缀自动扫描
> **新增于 2026-07**：gamestate app URL 双前缀 `/api/v2/gamestate/gamestate/rules/`（TD-100）

```powershell
cd D:\code\GAF\backend
# Find URL patterns where app name matches the prefix (double prefix anti-pattern)
# Pattern: path('appname/', include('appname.urls'))
rg "path\(['\"](\w+)/['\"],\s*include\(['\"]\1\." --type py
# Also check router.register with redundant prefix
rg "router\.register\(r'(\w+)/" --type py
```
- ✅ 0 matches (no double prefixes)
- ❌ Any match = URL like `/api/v2/gamestate/gamestate/rules/` (app name + router prefix duplicate)
- Fix: remove redundant prefix from `router.register(r'appname/...')` → `router.register(r'...')`

---

## G. 文档与 AI 记忆一致性 ✅ 已迁自动 (spec-41, 2026-07-20)

> **spec-44 迁移说明**: G 类 8 项已由 `scripts/governance/doc_health_check.py` (spec-41) 7 维度静态检查覆盖,
> 通过 `gaf_init.sh` 在每次对话开头自动跑。月度检查时**跳过 G 类**。
> 以下保留原内容作为历史参考 + 迁移映射证据。

### G1. docs/ 索引校验

> **✅ 已迁自动 (spec-41)**: d7_index_consistency + d5_frontmatter (gaf_init.sh 自动跑)
> 月度检查时跳过本项, 仅在 doc_health_check.py 报告 P0/P1 issue 时触发 spec-42 飞轮 patch

```powershell
cd D:\code\GAF
conda run -n gaf python scripts/bootstrap/sync_docs_index.py --check --strict
```
- ✅ 0 stale, 0 missing
- ❌ 记录报错数

### G2. AI 记忆同步校验

> **✅ 已迁自动 (spec-41)**: sync_ai_memory.py (gaf_init.sh 自动跑)

```powershell
cd D:\code\GAF
conda run -n gaf python scripts/bootstrap/sync_ai_memory.py --stats
```
- ✅ 0 conflict, 0 read-only
- ⚠️ 记录 warnings 数（预存 evidence 模板问题可接受）

### G3. Skills 副本一致性

> **✅ 已迁自动 (spec-41)**: sync_skills.py (pre-commit 自动跑)

```powershell
cd D:\code\GAF
conda run -n gaf python scripts/bootstrap/sync_skills.py --check
```
- ✅ 4 skills + 1 rule 副本一致
- ❌ 副本不一致

### G4. lessons/ front-matter 完整性

> **✅ 已迁自动 (spec-41)**: d5_frontmatter (gaf_init.sh 自动跑)

- Grep `.ai-memory/lessons/*.md` 检查每个文件是否有 front-matter
- ❌ 缺失 front-matter 的文件需补齐

### G5. failure-modes.md 索引完整性

> **✅ 已迁自动 (spec-41)**: d7_index_consistency + d3_count_drift (gaf_init.sh 自动跑)

- 统计 `failure-modes.md` 中的 N## 索引行数
- 统计 `.ai-memory/lessons/` 实际文件数
- ⚠️ 索引行数与文件数不匹配需同步

### G6. 规则/文档引用 skill 存在性

> **✅ 已迁自动 (spec-41)**: d4_path_drift (gaf_init.sh 自动跑)

> **新增于 2026-07**：project_rules.md §4.7 引用 `frontend-design` skill 但该 skill 不存在（TD-101，✅ 已修复 2026-07-14，P1 瘦身时改为引用 `docs/standards/frontend-conventions.md`）

```powershell
cd D:\code\GAF
# Extract all Skill(name='...') references from rules/docs
rg "Skill\(name=['\"](\w+)['\"]\)" .skills/rules/ docs/ --type md
# For each skill name found, verify it exists
# Test-Path .skills/skills/<name>/SKILL.md
```
- ✅ All referenced skills exist in `.skills/skills/`
- ❌ Any referenced skill missing = AI will fail when calling it
- ✅ TD-101 已闭环: frontend-design/web-design-guidelines 引用已从 project_rules.md 移除，§4.7 改为引用 `docs/standards/frontend-conventions.md`（单一权威源）

### G7. 规则/文档引用 path 存在性

> **✅ 已迁自动 (spec-41)**: d4_path_drift (gaf_init.sh 自动跑)

> **新增于 2026-07**：规则文档引用 `docs/frontend/design-system/theme-guidelines.md` 但整个 `docs/frontend/` 目录不存在（TD-101，✅ 已修复 2026-07-14，引用已从 project_rules.md 移除）

```powershell
cd D:\code\GAF
# Extract backtick-quoted paths from rules/docs
rg '`(docs/|\.ai-memory/|scripts/)[^`]+`' .skills/rules/ docs/ --type md
# For each path found, Test-Path to verify existence
```
- ✅ All referenced paths exist
- ❌ Any missing path = stale reference after refactoring/migration
- 重点检查：lesson 迁移后旧路径、文件移动后旧位置、目录重命名后旧名
- ✅ TD-101 已闭环: `docs/frontend/design-system/theme-guidelines.md` 引用已移除，§4.7 改为引用 `docs/standards/frontend-conventions.md`（已存在）

### G8. docs/ 引用脚本存在性

> **✅ 已迁自动 (spec-41)**: d4_path_drift (gaf_init.sh 自动跑)

```powershell
cd D:\code\GAF
# Extract script paths referenced in docs
rg '`scripts/[^`]+`' docs/ --type md
# For each script path, Test-Path to verify
```
- ✅ All referenced scripts exist
- ❌ Any missing script = doc references deleted/moved script

---

## H. Git 卫生

### H1. 工作树状态 ✅ 已迁自动 (spec-45, 2026-07-20)

> **✅ 已迁自动 (spec-45)**: check_h1_git_status (monthly_health_check.py)
> 跑法: `python scripts/governance/monthly_health_check.py`
> 阈值: 敏感文件 (.env / *.key / *.pem / *credentials* / *.pfx) → P0; >20 uncommitted → P2

```powershell
cd D:\code\GAF
git status
```
- ✅ "nothing to commit, working tree clean"
- ⚠️ 有未提交改动（记录文件数）
- ❌ 有未跟踪的敏感文件（.env / *.key / *.pem）

### H2. 未合并分支
```powershell
cd D:\code\GAF
git branch --no-merged main
```
- 记录未合并分支数
- ⚠️ 分支超过 2 周未合并需评估删除

### H3. commit message 规范
```powershell
cd D:\code\GAF
git log --oneline -30
```
- 检查最近 30 个 commit 是否遵循 `<type>(<scope>): <subject>` 格式
- type ∈ feat / fix / refactor / docs / test / chore / perf / build / ci
- ❌ 不规范的 commit 超过 3 个需标注

### H4. 未 push 的 commit
```powershell
cd D:\code\GAF
git log origin/main..main --oneline
```
- ✅ 无未 push commit（或用户已知晓）
- ⚠️ 有未 push commit 需确认是否需推送

---

## I. 代码质量

### I1. 巨型文件检测 ✅ 已迁自动 (spec-45, 2026-07-20)

> **✅ 已迁自动 (spec-45)**: check_i1_large_files (monthly_health_check.py)
> 跑法: `python scripts/governance/monthly_health_check.py`
> 阈值: backend=2000 / frontend/src=1500 / worker/src=1500 / scripts=1000 行 (thresholds.yaml `monthly_checks.i1_large_files`)
> 跳过: .generated. 文件 / __pycache__ / node_modules / .venv / debug 目录

```powershell
# 查找 > 500 行的源码文件（排除生成文件 / migrations / 测试）
```
- 抽查 backend/ frontend/src/ worker/src/ 下 .py / .ts / .tsx 文件
- ⚠️ > 500 行的文件需评估拆分
- 重点检查：`backend/resources/views.py`（历史 1129 行）、`backend/agents/views.py`

### I2. ESLint 警告
```powershell
cd D:\code\GAF\frontend
npx eslint src/ --quiet
```
- ✅ 0 warnings
- ⚠️ 记录 warning 数

### I3. Ruff 检查（后端）
```powershell
cd D:\code\GAF\backend
conda run -n gaf ruff check . --exclude migrations
```
- ✅ 0 errors
- ⚠️ 记录 warning 数

### I4. 死代码检测
- 前端：Grep 未被 import 的组件文件（`frontend/src/pages/` / `frontend/src/components/`）
- 后端：检查未被 URL 引用的 ViewSet
- ⚠️ 发现死代码需登记 TD 或删除

### I5. Base64 字符串路径误判检测
> **新增于 2026-07**：template_match.py 用 `'/' in template_config` 判断文件路径，但 base64 字符串可包含 `/`

```powershell
# 搜索代码中 '/' in ... 或 os.path.sep in ... 等路径检测逻辑
cd D:\code\GAF
# 检查 worker/src/ 中是否有用 '/' 字符判断路径的代码
```
- 搜索使用 `'/' in` 或 `os.path.sep in` 做路径类型判断的代码
- ❌ 对可能包含 base64 字符串的输入用 `/` 判断路径 = 误判 bug
- 修复模式：先尝试 base64 decode，失败后再当文件路径处理

### I6. 资源句柄释放完整性
> **新增于 2026-07**：screenshot.py `set_hwnd` 只释放 WGC 不释放 DXGI，导致资源泄漏

```powershell
# 搜索 _release_ / .release() / .close() / .cleanup() 等资源释放方法
cd D:\code\GAF\worker\src
# 检查 set_xxx / switch_xxx / update_xxx 方法是否释放所有关联资源
```
- 检查所有 `set_xxx()` / `switch_xxx()` / `update_xxx()` 方法
- 确认方法内释放了所有关联资源（不只是当前活跃的那一个）
- ❌ 切换上下文时只释放部分资源 = 资源泄漏
- 重点检查：`screenshot.py` / `connection.py` / `input_handler.py`

### I7. 重试装饰器与状态标志兼容性
> **新增于 2026-07**：connection.py `send_message` 在 except 中设 `_connected=False`，导致重试装饰器提前返回

```powershell
# 搜索 @retry 装饰器修饰的方法
cd D:\code\GAF\worker\src
# 检查被修饰方法内是否有状态标志修改（if not self._connected: return）
```
- 检查所有 `@retry_network` / `@retry` 装饰的方法
- 确认 except 块中的状态标志修改不会阻止重试装饰器重新进入
- ❌ except 块设 `_connected=False` + 方法开头 `if not self._connected: return` = 重试无效
- 修复模式：except 块中只对不可重试的异常设 `_connected=False`

---

## J. 安全检查

### J1. 敏感文件在 .gitignore
```powershell
cd D:\code\GAF
# 检查 .gitignore 是否包含 .env / *.key / *.pem / *credentials*
```
- ✅ 全部包含
- ❌ 缺失任何一项需立即补齐

### J2. 密钥文件泄露检查
```powershell
cd D:\code\GAF
git ls-files | Select-String -Pattern "\.env$|\.key$|\.pem$|credentials"
```
- ✅ 无敏感文件被追踪
- ❌ 发现敏感文件需 `git rm --cached` 并加入 .gitignore

### J3. DEBUG 模式配置
- 检查 `backend/settings.py`（或 settings 模块）的 `DEBUG` 值
- ✅ 生产配置 DEBUG=False
- ⚠️ 开发环境 DEBUG=True 可接受但需确认不会部署到生产

### J4. JWT / CORS 配置
- 检查 `SIMPLE_JWT` 配置的 token 过期时间（ACCESS_TOKEN_LIFETIME 建议 ≤ 1 小时）
- 检查 `CORS_ALLOWED_ORIGINS` 是否过于宽松（生产不应含 `*`）
- ⚠️ 配置过于宽松需收紧

### J5. "记住账号"与 JWT 配置一致性
> **新增于 2026-07**：前端承诺"30 天自动登录"但后端 REFRESH_TOKEN_LIFETIME 默认 7 天

```powershell
cd D:\code\GAF\backend
# Check JWT refresh token lifetime
conda run -n gaf python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.dev'); import django; django.setup(); from django.conf import settings; print(f'REFRESH_TOKEN_LIFETIME={settings.SIMPLE_JWT[\"REFRESH_TOKEN_LIFETIME\"]}'); print(f'GAF_REMEMBER_ME_DAYS={getattr(settings,\"GAF_REMEMBER_ME_DAYS\",\"NOT SET\")}')"
# Check frontend remember_me promise
cd D:\code\GAF\frontend
rg 'remember|记住|30' src/ --type tsx -i | Select-String -NotMatch 'comment'
```
- ✅ GAF_REMEMBER_ME_DAYS (30) ≤ REFRESH_TOKEN_LIFETIME when remember_me=true overrides exp
- ❌ Frontend promises 30 days but backend refresh < 30 days = "记住账号"提前失效
- Note: Backend overrides refresh exp to GAF_REMEMBER_ME_DAYS when remember_me=true (accounts/serializers.py)

### J6. refresh token 流程实测
```powershell
cd D:\code\GAF\backend
# Start backend if not running
# Login to get refresh token
$body = @{ username='admin'; password='admin123'; remember_me=$true } | ConvertTo-Json
$r = Invoke-WebRequest -Uri "http://localhost:8000/api/v2/accounts/auth/login/" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
$refresh = ($r.Content | ConvertFrom-Json).refresh
# Test refresh endpoint
$rb = @{ refresh=$refresh } | ConvertTo-Json
$rf = Invoke-WebRequest -Uri "http://localhost:8000/api/v2/accounts/auth/refresh/" -Method POST -Body $rb -ContentType "application/json" -UseBasicParsing
$newAccess = ($rf.Content | ConvertFrom-Json).access
Write-Host "Refresh OK: new access token obtained"
# Test that old refresh token is blacklisted (ROTATE_REFRESH_TOKENS=True)
try {
  $rf2 = Invoke-WebRequest -Uri "http://localhost:8000/api/v2/accounts/auth/refresh/" -Method POST -Body $rb -ContentType "application/json" -UseBasicParsing
  Write-Host "WARN: old refresh token still valid after rotation (BLACKLIST_AFTER_ROTATION may be off)"
} catch {
  Write-Host "OK: old refresh token blacklisted as expected"
}
```
- ✅ Refresh returns new access token
- ✅ Old refresh token blacklisted after rotation (if BLACKLIST_AFTER_ROTATION=True)
- ❌ Refresh returns 401 = refresh token invalid/expired
- ❌ Old refresh still valid after rotation = BLACKLIST_AFTER_ROTATION not working

---

## K. 部署就绪度

### K1. Django 部署检查
```powershell
cd D:\code\GAF\backend
conda run -n gaf python manage.py check --deploy
```
- ✅ 0 warnings
- ⚠️ 记录 warning 数（开发环境可接受，生产需修复）

### K2. 静态文件收集
```powershell
cd D:\code\GAF\backend
conda run -n gaf python manage.py collectstatic --dry-run
```
- ✅ 收集成功
- ❌ 收集失败（记录错误）

### K3. 生产依赖完整性
- 确认 `backend/requirements/prod.txt` 存在且能安装
- 确认 `frontend/package.json` 的 dependencies 完整（无 missing）

---

## L. 跨平台一致性

### L1. Windows 专用代码封装
```powershell
# Grep 检查业务逻辑中是否直接调用 Win32 API
cd D:\code\GAF
# 搜索 backend/ 和 worker/src/ 中的 win32api / win32con / ctypes.windll 直接调用
```
- ✅ 所有 Win32 调用封装在 `worker/src/platforms/windows/` 或 `backend/device_bridge/platforms/windows/`
- ❌ 业务逻辑中有直接 Win32 调用 = 违反 project_rules.md §0 核心约束

### L2. 平台抽象接口完整性
- 检查 `worker/src/platforms/` 下是否有 Windows / macOS / Linux 三个目录
- 确认每个平台都实现了抽象接口（ScreenshotHandler / InputHandler 等）
- ⚠️ 缺失平台实现需登记

### L3. 硬编码路径检查
- Grep 检查是否有硬编码的 Windows 路径（如 `C:\` / `D:\` / `\Users\`）散落在业务逻辑中
- ✅ 路径通过配置或 `pathlib.Path` 管理
- ⚠️ 硬编码路径需提取为配置

---

## M. 架构一致性

> **新增于 2026-07**：检查代码实际架构与设计文档是否一致，防止架构漂移

### M1. 平台抽象层完整性
```powershell
# 检查 platforms/ 目录结构
cd D:\code\GAF
# worker/src/platforms/ 应有 base.py (抽象接口) + windows/ (实现)
```
- 检查 `worker/src/platforms/base.py` 是否定义了所有抽象接口（ScreenshotHandler / InputHandler / DeviceDiscoverer）
- 检查 `worker/src/platforms/windows/` 是否实现了所有抽象方法
- ❌ 抽象接口与实现不匹配 = 架构违反
- ⚠️ macOS/Linux 目录缺失需登记（项目当前仅支持 Windows 可接受）

### M2. 业务逻辑与平台代码隔离
```powershell
# Grep 检查 backend/ 和 worker/src/ (非 platforms/) 中是否直接调用平台 API
cd D:\code\GAF
# 搜索 ctypes.windll / win32api / win32con 在 platforms/ 之外的引用
```
- ❌ `platforms/` 之外的代码直接调用 Win32 API = 违反 project_rules.md §0 核心约束
- 检查范围：`backend/`、`worker/src/`（排除 `platforms/`）
- 白名单：`backend/agent_client.py` 中通过平台抽象层间接调用是允许的

### M3. 模块间依赖方向
```powershell
# 检查是否有循环导入
cd D:\code\GAF\backend
conda run -n gaf python -c "import importlib; [importlib.import_module(app) for app in ['accounts','agents','tasks','pipeline','resources','skills','protocol','device_bridge']]"
```
- ✅ 所有 app 可独立导入
- ❌ 循环导入 = 架构设计问题
- 依赖方向应遵循：`accounts` ← `agents` ← `tasks` ← `pipeline` ← `protocol`
- `device_bridge` 应作为独立基础设施层，不被业务 app 反向依赖

### M4. API URL 路由挂载规范
```powershell
# 检查每个 app 的 urls.py 是否遵循 URL 路由约定
cd D:\code\GAF\backend
# 搜索 include(router.urls) 和 path() 的顺序
```
- 检查所有 `urls.py` 中显式 `path()` 是否在 `include(router.urls)` 之前
- 检查 app 名与 URL 前缀是否会产生双重路径（如 `/api/v2/agents/agents/`）
- ❌ `include(router.urls)` 在显式 `path()` 之前 = 潜在 405 bug
- 规范见 `docs/standards/backend-conventions.md` §5.2

### M5. 设计文档与代码同步
```powershell
# 检查 architecture-overview.md 中描述的模块是否都存在
cd D:\code\GAF
# 对比 docs/architecture/overview.md 中的模块列表与实际代码
```
- 检查 `docs/architecture/overview.md` 中描述的模块在代码中是否存在
- 检查代码中的主要模块是否在文档中有描述
- ⚠️ 文档与代码不一致 = 架构漂移
- 重点关注：新增模块是否已更新到设计文档

### M6. 文档事实性断言对拍
> **新增于 2026-08-28**：docs 全量逐模块内容级对拍暴露 40+ 处正文事实断言与代码不一致（app 计数 16→17、QA 端点 `qa/sessions`→`qa/qa-sessions`、hook 数量、React 版本 18→19.2、WS 路径 `/ws/agents/`→`/ws/protocol/agents/`、status 枚举、重试扫描时间 5min→1min）
>
> 背景：d1-d8 / check_doc_code_sync / M5 只查结构、path 存在性与"变更驱动"绑定，不查文档正文里**既有事实断言**是否与代码一致 — 代码长期不变而文档早已漂移时永远漏检。本项按月对拍。

```powershell
cd D:\code\GAF
# 权威源对照抽查（每月至少 1 个模块集群，优先最近变更过的模块）
# ① app 计数 vs INSTALLED_APPS
rg 'Django App|个后端 app|个 Django app' docs/architecture/
rg '"' backend/config/settings/base.py | Select-String -Pattern 'apps[0-9]'  # 手动数 INSTALLED_APPS 本地 app 行
# ② API 端点名 vs 各 app urls.py router 注册名（2026-08-28 已校准 qa-sessions/llm-usage-logs）
rg 'qa/[a-z-]+' docs/architecture/features-overview.md
# ③ WS 路径 vs config/app_info.py WS_AGENT_PATH
rg '/ws/[a-z/]+' docs/ | Select-String -NotMatch '已删除|legacy'
# ④ hook 数量/检查项 vs .pre-commit-config.yaml + gaf_governance_batch.py CHECKS
rg 'Hook \(|项检查|检查项' docs/architecture/cross-cutting/pre-commit-stages.md
# ⑤ 版本号 vs package.json / requirements/*.txt / app_info.py APP_VERSION
rg 'React \d|版本必须|^\|.*\d\.\d' docs/reference/tech-stack.md
# ⑥ 状态枚举 vs models / serializers 定义
rg 'enum|枚举' docs/business/ | Select-String -Pattern 'status|State'
```

- ✅ 抽查项全部与代码一致
- ❌ 文档事实断言 ≠ 代码 = 文档漂移 → 修正文档；若系代码改动未同步文档，登记 doc-code 断链
- 依据权威源：`INSTALLED_APPS` / 各 app `urls.py` / `config/app_info.py` / `.pre-commit-config.yaml` + `gaf_governance_batch.py CHECKS` / `package.json`+`requirements/*.txt` / models+serializers

### M7. Git 冲突标记残留扫描
> **新增于 2026-08-28**：`docs/reference/performance-baseline.md` 残留未解决的 `<<<<<<< Updated upstream` 合并/stash 冲突标记被提交（已于 2026-08-28 清理并合并两侧时间线）

```powershell
cd D:\code\GAF
rg '^<<<<<<<|^=======$|^>>>>>>>' docs/ .ai-memory/ .skills/ --type md
```

- ✅ 0 matches
- ❌ 任何匹配 = 冲突标记被提交，内容被污染 → 手工合并两侧记录、移除标记，`git add` 后 `git status` 确认无 MM/MD 残留

---

## N. 项目卫生 (空目录/空文件)

> **新增于 2026-07**：检查项目中的空目录和空文件，防止残留垃圾

### N1. 空目录扫描 ✅ 已迁自动 (spec-45, 2026-07-20)

> **✅ 已迁自动 (spec-45)**: check_n1_empty_dirs (monthly_health_check.py)
> 跑法: `python scripts/governance/monthly_health_check.py`
> 覆盖: 空目录 + 空文件 (N2 合并到 N1)
> 跳过: .git / .cache / node_modules / __pycache__ / .venv / .trash / MagicMock / debug 目录
> 跳过空文件: .gitkeep / .keep / __init__.py / *.lock (intentional)

```powershell
# 扫描项目中的空目录（排除 .git, node_modules, __pycache__, .gitignore 的目录）
cd D:\code\GAF
conda run -n gaf python scripts/scan_empty.py D:\code\GAF
```
- ✅ 无空目录（gitignore 的运行时目录如 logs/、media/ 可接受）
- ❌ 有空目录 = 残留垃圾或缺失 .gitkeep
- 处理规则：
  - 运行时目录（logs/、media/、plugins_data/）→ 添加 `.gitkeep`
  - 残留目录（重构后的孤儿目录）→ 删除
  - 占位目录（未来要用的）→ 添加 `.gitkeep` + README 说明

### N2. 空文件扫描
```powershell
# 扫描项目中的空文件（排除 __init__.py, .gitkeep, .keep 等）
cd D:\code\GAF
conda run -n gaf python scripts/scan_empty.py D:\code\GAF
```
- ✅ 无意外空文件
- ❌ 有空文件 = 残留 scaffold 或未完成的文件
- 处理规则：
  - 空 scaffold 文件（如 `serializers.py` 从未使用）→ 删除
  - 空占位文件（如 icon 文件被引用但无数据）→ 保留并标注 TODO
  - 空测试文件 → 添加 TODO stub 或删除

---

## O. 真实设备验证

> **新增于 2026-07**：用真实设备（非 mock）验证核心功能，确保测试反映真实运行状态

### O1. 雷电模拟器连通性验证
```powershell
# 检查雷电模拟器是否运行、ADB 是否可连接
cd D:\code\GAF
# 检查 ADB 设备列表
adb devices
# 雷电模拟器默认 ADB 端口: 5555 (LDPlayer) / 5554 (标准模拟器)
```
- ✅ ADB 能检测到雷电模拟器
- ❌ ADB 无法连接 = 模拟器未启动或 ADB 端口不对
- ⚠️ 模拟器未运行时跳过此项（标注"模拟器未启动"）

### O2. 设备扫描 API 真实测试
```powershell
# 启动后端，调用设备扫描 API，验证能发现真实模拟器
cd D:\code\GAF\backend
conda run -n gaf python manage.py runserver
# 另一终端：
$token = (Invoke-WebRequest -Uri "http://localhost:8000/api/v2/accounts/auth/login/" -Method POST -Body '{"username":"admin","password":"admin123"}' -ContentType "application/json" -UseBasicParsing).Content | ConvertFrom-Json | Select -ExpandProperty access
Invoke-WebRequest -Uri "http://localhost:8000/api/v2/devices/scan/?type=all" -Headers @{Authorization="Bearer $token"} -UseBasicParsing
```
- ✅ API 返回真实设备列表（包含雷电模拟器）
- ❌ API 返回空列表或 mock 数据 = 扫描逻辑有问题
- ❌ API 返回 500 = 后端代码有 bug

### O3. 截图功能真实测试
```powershell
# 对在线设备执行截图测试，验证截图链路完整
# 通过前端设备中心页面的"截图测试"按钮，或直接调用 API
$token = ... # 登录获取 token
$deviceId = 1 # 已注册的雷电模拟器设备 ID
Invoke-WebRequest -Uri "http://localhost:8000/api/v2/devices/$deviceId/screenshot/" -Method POST -Headers @{Authorization="Bearer $token"} -UseBasicParsing
```
- ✅ 截图成功返回 base64 图片数据
- ❌ 截图失败 = 截图链路有 bug（WGC/DXGI/ADB 截图方法问题）
- ⚠️ 模拟器离线时跳过此项

---

## P. 日志健康

> **新增于 2026-07**：日志架构修复（dedup + 7天TTL + 实时广播 + 死代码清除）后，月度检查日志系统健康状态，防止日志管道断裂、堆积或退化

### P1. 日志总量与保留期

```powershell
cd D:\code\GAF\backend
# 写临时脚本查询 LogEntry 总量 + 按天分布 + 最早记录
Set-Content -Path '_check_logs.py' -Value @'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()
from core.models import LogEntry
from django.utils import timezone
from datetime import timedelta
total = LogEntry.objects.count()
threshold = timezone.now() - timedelta(days=7)
overdue = LogEntry.objects.filter(last_seen__lt=threshold).count()
earliest = LogEntry.objects.order_by('first_seen').first()
print(f"total={total} overdue(>7d)={overdue}")
if earliest:
    print(f"earliest_first_seen={earliest.first_seen}")
@
conda run -n gaf python _check_logs.py
Remove-Item _check_logs.py
```
- ✅ overdue = 0（TTL 清理任务正常工作）
- ⚠️ total > 10000 需关注（日志产生过快，可能 dedup 失效或系统有异常）
- ❌ overdue > 0 = TTL 清理任务未执行（celery beat 未配置或 worker 未运行）
- ❌ earliest_first_seen 超过 7 天 = 清理任务失效

### P2. Dedup 有效性

```powershell
cd D:\code\GAF\backend
Set-Content -Path '_check_dedup.py' -Value @'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()
from core.models import LogEntry
from django.db.models import Sum
total = LogEntry.objects.count()
aggregated = LogEntry.objects.aggregate(total_occ=Sum('occurrence_count'))
deduped = LogEntry.objects.filter(occurrence_count__gt=1).count()
print(f"rows={total} total_occurrences={aggregated['total_occ'] or 0} deduped_rows={deduped}")
ratio = (aggregated['total_occ'] or 0) / total * 100 if total else 0
print(f"dedup_ratio={ratio:.1f}%")
@
conda run -n gaf python _check_dedup.py
Remove-Item _check_dedup.py
```
- ✅ deduped_rows > 0（dedup 机制在工作）
- ⚠️ dedup_ratio > 80% 需关注（同一错误高频重复，系统有持续性问题）
- ❌ deduped_rows = 0 + total_occurrences = total = dedup 未生效（fingerprint 计算或查询有 bug）

### P3. TTL 清理任务状态

```powershell
cd D:\code\GAF\backend
# 1. 检查 celery beat 是否注册了 cleanup-old-logs 任务
conda run -n gaf python -c "from config.celery import app; print([name for name in app.conf.beat_schedule if 'log' in name])"
# 2. 检查 LOG_RETENTION_DAYS 配置
conda run -n gaf python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev'); import django; django.setup(); from django.conf import settings; print(getattr(settings, 'LOG_RETENTION_DAYS', 'NOT SET'))"
```
- ✅ celery beat 输出含 `cleanup-old-logs`
- ✅ LOG_RETENTION_DAYS 输出 7（或配置值）
- ❌ celery beat 无 `cleanup-old-logs` = beat_schedule 未注册
- ❌ LOG_RETENTION_DAYS 输出 NOT SET = 配置丢失

### P4. 实时广播链路完整性

```powershell
cd D:\code\GAF
# 1. 检查 DatabaseLogHandler 是否广播到 LOGS_GROUP
# Grep handlers.py 中 LOGS_GROUP 引用
# 2. 检查 LogStreamConsumer 是否加入 LOGS_GROUP
# Grep consumers.py 中 LOGS_GROUP 引用
# 3. 检查 routing.py 中 /ws/logs/ 路由是否存在
```
- 检查 `backend/core/handlers.py` 的 `DatabaseLogHandler` 是否有 `_broadcast_to_logs_group()` 方法
- 检查 `backend/protocol/consumers.py` 的 `LogStreamConsumer` 是否 join `LOGS_GROUP`
- 检查 `backend/protocol/routing.py` 是否有 `ws/logs/` 路由
- ❌ 任一环节缺失 = 实时广播链路断裂（日志中心页面不会实时更新）

### P5. 高频错误日志聚集分析

```powershell
cd D:\code\GAF\backend
Set-Content -Path '_check_top.py' -Value @'
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()
from core.models import LogEntry
top = LogEntry.objects.filter(level__in=['ERROR','CRITICAL']).order_by('-occurrence_count')[:10]
for e in top:
    print(f"occ={e.occurrence_count} level={e.level} source={e.source} msg={e.message[:100]}")
if not top:
    print("no error logs")
@
conda run -n gaf python _check_top.py
Remove-Item _check_top.py
```
- 列出 occurrence_count 最高的 10 条 ERROR/CRITICAL 日志
- ⚠️ 单条 occurrence_count > 100 = 持续性错误未修复，需登记 TD
- ⚠️ 同一 source 的高频错误 = 模块级问题
- 重点排查：`agent` 来源（agent 连接问题）、`protocol` 来源（WebSocket 断连）、`device_bridge` 来源（ADB 调用失败）

### P6. 死代码残留检查

```powershell
cd D:\code\GAF
# 1. AgentLogger 已删除，检查是否还有引用
# Grep "AgentLogger" in agent/ 和 backend/
# 2. LOG_STREAM 消息类型已删除，检查是否还有引用
# Grep "LOG_STREAM" in backend/ 和 frontend/
# 3. _handle_log_stream 已删除，检查是否还有引用
# Grep "_handle_log_stream" in backend/
```
- ✅ 无 AgentLogger 引用
- ✅ 无 LOG_STREAM 引用
- ✅ 无 _handle_log_stream 引用
- ❌ 发现任何残留引用 = 死代码清除不完整或回归

---

## Q. 前端 i18n 完整性

> **新增于 2026-07**：前端组件属性面板英文硬编码（历史触发源：已删除的 ScreenStateEditor），需界面点击才暴露

### Q1. 硬编码英文字符串扫描
```powershell
cd D:\code\GAF\frontend
# Scan for hardcoded English strings in JSX (excluding comments/imports/types)
# Match patterns like: placeholder="Enter..." / label="Name" / >Save<
rg '(placeholder|label|title|aria-label)="[A-Z][a-z]+' src/ --type tsx
rg '>[A-Z][a-z]+ [A-Z]?[a-z]+<' src/ --type tsx
```
- ✅ 0 matches (all user-visible strings go through i18n)
- ❌ Any match = hardcoded English that should use `tt('...')` or `t('...')`
- Exclude: comments (`//` / `/* */`), `import` statements, `interface`/`type` declarations, `console.log` strings

### Q2. i18n key 四语言对齐
```powershell
cd D:\code\GAF\frontend
# Export key sets from each locale and diff
conda run -n gaf python -c "
import re, sys
files = ['src/i18n/locales/zh.ts','src/i18n/locales/en.ts','src/i18n/locales/ja.ts','src/i18n/locales/ko.ts']
keys = {}
for f in files:
    with open(f, encoding='utf-8') as fh:
        content = fh.read()
    lang = f.split('/')[-1].replace('.ts','')
    keys[lang] = set(re.findall(r\"'([a-zA-Z_.]+)':\", content))
base = keys['zh']
for lang, ks in keys.items():
    missing = base - ks
    extra = ks - base
    if missing: print(f'{lang} missing {len(missing)} keys: {list(missing)[:5]}')
    if extra: print(f'{lang} extra {len(extra)} keys')
"
```
- ✅ All 4 locales have identical key sets
- ❌ Any locale missing keys = fallback to default language for those keys

### Q3. useTranslation 导入来源验证
```powershell
cd D:\code\GAF\frontend
# GAF uses custom @/i18n, not react-i18next directly
rg "from ['\"]react-i18next['\"]" src/
```
- ✅ 0 matches (all imports from @/i18n)
- ❌ Any match = incorrect import source (project uses custom i18n wrapper)

---

## R. 前端交互冒烟测试

> **新增于 2026-07**：详情页编辑按钮跳回列表、Chrome 占不满浏览器，需界面点击才暴露
> **前置条件**：后端 `localhost:8000` + 前端 `localhost:5173` 运行中

### R1. Playwright 登录冒烟测试
```powershell
cd D:\code\GAF
conda run -n gaf python -m playwright install chromium
conda run -n gaf python scripts/e2e/run_all.py browser_login
```
- ✅ Login scenario passes (login → dashboard redirect → token set)
- ❌ Login fails = authentication API broken or login form changed

### R2. Playwright 关键导航冒烟（全场景）
```powershell
cd D:\code\GAF
conda run -n gaf python scripts/e2e/run_all.py
# Runs all 5 scenarios: browser_login / console_verify / console_monitor / ai_qa_chat / devices_control_mode
```
- ✅ All scenarios pass
- ❌ Any scenario fails = UI navigation/interaction broken
- ⚠️ Record which scenarios failed and the error type

### R3. Playwright console 错误扫描
（含在 R2 运行中）检查所有场景的 `page.on("console", ...)` 收集的 error：
- ✅ 0 console errors across all scenarios
- ❌ Any `console.error` = JS runtime error, API 404, or component crash
- 重点排查：`TypeError` / `Cannot read properties of undefined` / `Failed to fetch`

### R4. Playwright 关键 Modal 打开/关闭
（含在 R2 的 ai_qa_chat 场景中）验证 Modal 打开/关闭无报错：
- ✅ Modal opens and closes without console errors
- ❌ Modal `destroyOnHidden` config error / Form not cleared / state leak

### R5. Playwright 配置完整性
```powershell
cd D:\code\GAF
# Check viewport/launch params in scenario files
rg 'viewport|launch|headless|no_viewport' scripts/e2e/scenarios/ --type py
# Verify Chromium installed
conda run -n gaf python -m playwright install --dry-run chromium
```
- ✅ Scenarios use `no_viewport=True` (Chrome 134+ compatible) or reasonable viewport
- ❌ `viewport=None` (doesn't work on Chrome 134+) / viewport too small / Chromium not installed

---

## S. 前端组件库兼容性

> **新增于 2026-07**：antd 5.x→6.x 弃用 prop（`destroyOnClose` / `Space.direction` 等 13 处，TD-100）

### S1. antd 6 弃用 prop 扫描
```powershell
cd D:\code\GAF\frontend
# antd 5.x -> 6.x deprecated props:
# destroyOnClose -> destroyOnHidden
# <Space direction> -> wrap or split rows
# bordered on Card -> variant="borderless"
# dropdownClassName -> popupClassName
# visible on Modal/Drawer -> open
rg 'destroyOnClose|<Space direction=|bordered=|dropdownClassName|visible=' src/ --type tsx
```
- ✅ 0 matches (all using antd 6.x props)
- ❌ Any match = deprecated prop that triggers console warning, will break in future antd version
- Fix mapping: `destroyOnClose`→`destroyOnHidden` / `Space direction`→`wrap` or rows / `bordered`→`variant="borderless"` / `dropdownClassName`→`popupClassName` / `visible`→`open`

### S2. antd/React 版本兼容性
```powershell
cd D:\code\GAF\frontend
npm ls antd react
# Check peer deps
npm info antd peerDependencies
```
- ✅ antd and React versions satisfy peer dependency ranges
- ❌ Peer dep conflict = potential runtime issues
- ⚠️ antd major version behind latest = review upgrade changelog

---

## 报告输出格式

报告输出到 `docs/health/YYYY-MM.md`，格式如下：

```markdown
# GAF 月度健康检查报告 — YYYY-MM

> **执行时间**：YYYY-MM-DD HH:MM
> **执行者**：AI / 开发者
> **总项数**：86 | **通过**：XX | **失败**：XX | **需关注**：XX
> **通过率**：XX%
> **预估风险等级**：低 / 中 / 高

## 汇总

| 类别 | 项数 | 通过 | 失败 | 需关注 |
|:----:|:----:|:----:|:----:|:------:|
| A 构建与类型 | 4 | | | |
| B 测试套件 | 7 | | | |
| ... | | | | |
| P 日志健康 | 6 | | | |
| Q 前端 i18n 完整性 | 3 | | | |
| R 前端交互冒烟测试 | 5 | | | |
| S 前端组件库兼容性 | 2 | | | |

## 关键风险（失败 + 高优先级需关注项）

1. [类别-编号] 描述
   - 根因初判：...
   - 修复建议：...
   - 建议优先级：P0/P1/P2/P3

## 详细结果

### A. 构建与类型检查

- [A1] Backend Django check: ✅ 0 errors
- [A2] Frontend tsc: ⚠️ 12 errors（预存，非本轮引入）
- ...

（每类按此格式列出）

## 与上月对比

| 指标 | 上月 | 本月 | 变化 |
|------|------|------|------|
| 活跃 TD 数 | | | |
| 测试通过率 | | | |
| 测试执行时间 | | | |
| npm 漏洞数 | | | |
| 巨型文件数 | | | |

## 建议行动项

1. [P0] ...
2. [P1] ...
3. [P2] ...

## 迭代回顾

- **本次新增检查项**：无 / B5, B6, ...
- **触发原因**：（如适用，说明每个新增项的触发原因）
- **未新增但需关注**：（如有，说明哪些问题类型已被现有检查项覆盖，无需新增）
```

## 注意事项

- **不修复，只报告**：月度检查的目的是发现问题，修复需走正式的 bug_fix / refactor 流程
- **诚实标记**：✅ 必须基于实测命令输出，禁止主观断言（N126/N128）
- **历史可追溯**：报告按月归档，可对比趋势
- **聚焦可行动项**：报告末尾的"建议行动项"应可直接转为 TD 登记或 plan 子任务
