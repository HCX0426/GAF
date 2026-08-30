---
summary: 2026-07 月度健康检查报告 — 46 项中通过 28/失败 6/需关注 12; 首次基线检查, 发现 Win32 API 泄露 + npm 高危漏洞 + ruff 错误 + 失败测试
applies_to: [workflow, ai-rules, l3-scan]
last_updated: 2026-07-26
maintainer: manual
source: docs/health/2026-07.md
load_when: [月度健康检查, L3-1 扫描, 历史报告对比]
priority: medium
symptom: [health-check-2026-07, monthly-audit-report, baseline-check]
solution: 2026-07 月度健康检查报告, 46 项中通过 28/失败 6/需关注 12; 首次基线检查, 发现 Win32 API 泄露 + npm 高危漏洞 + ruff 错误 + 失败测试
related_files:
  - docs/health/procedure.md
created_by: AI
---
# GAF 月度健康检查报告 — 2026-07

> **执行时间**：2026-07-11 10:19 ~ 10:55
> **执行者**：AI
> **总项数**：46 | **通过**：28 | **失败**：6 | **需关注**：12
> **通过率**：60.9%
> **预估风险等级**：中

## 汇总

| 类别 | 项数 | 通过 | 失败 | 需关注 |
|:----:|:----:|:----:|:----:|:------:|
| A 构建与类型 | 4 | 4 | 0 | 0 |
| B 测试套件 | 4 | 1 | 2 | 1 |
| C 技术债务 | 4 | 3 | 0 | 1 |
| D 依赖管理 | 4 | 0 | 1 | 3 |
| E 数据库健康 | 3 | 3 | 0 | 0 |
| F API 契约一致性 | 4 | 1 | 0 | 3 |
| G 文档与 AI 记忆 | 5 | 4 | 0 | 1 |
| H Git 卫生 | 4 | 2 | 0 | 2 |
| I 代码质量 | 4 | 0 | 2 | 2 |
| J 安全检查 | 4 | 2 | 1 | 1 |
| K 部署就绪度 | 3 | 1 | 0 | 2 |
| L 跨平台一致性 | 3 | 0 | 2 | 1 |

## 关键风险（失败 + 高优先级需关注项）

1. **[L1] Win32 API 直接调用在业务逻辑中** — `backend/agent_client.py:59-60` 和 `worker/src/utils/screenshot_diagnostic.py:257` 直接调用 `ctypes.windll`，违反 project_rules.md §0 核心约束
   - 根因：平台抽象层建设时遗漏了这两个文件
   - 修复建议：迁移到 `platforms/windows/` 封装
   - 建议优先级：P1

2. **[D3] npm 安全漏洞 3 个 high** — `npm audit` 报告 7 vulnerabilities (3 low, 1 moderate, 3 high)
   - 根因：依赖过期
   - 修复建议：`npm audit fix` 或手动更新
   - 建议优先级：P1

3. **[I3] Ruff 709 errors** — 后端代码质量检查 709 个 ruff 错误（520 个可自动修复）
   - 根因：长期未运行 `ruff check --fix`
   - 修复建议：`ruff check . --fix` 自动修复 + 手动处理剩余 189 个
   - 建议优先级：P2

4. **[I2] ESLint 217 errors** — 前端 217 个 `@typescript-eslint/no-explicit-any` 错误
   - 根因：大量使用 `any` 类型
   - 修复建议：逐步替换为具体类型
   - 建议优先级：P2

5. **[B2] 前端测试 5 failed / 82 passed** — 4 个测试文件失败
   - 根因：待诊断（Dashboard.test.tsx 等）
   - 修复建议：逐个排查失败测试
   - 建议优先级：P2

6. **[B3] Agent 测试 9 failed / 1393 passed** — 9 个测试失败
   - 根因：待诊断（test_screenshot_dxgi 等）
   - 修复建议：逐个排查失败测试
   - 建议优先级：P2

7. **[J1] .gitignore 缺少 `*credentials*` 模式** — 敏感文件保护不完整
   - 根因：.gitignore 遗漏
   - 修复建议：添加 `*credentials*` 到 .gitignore
   - 建议优先级：P1

8. **[B1] skills app 测试发现问题** — `ImportError: 'tests' module incorrectly imported from skills\tests`
   - 根因：Django 测试发现路径冲突
   - 修复建议：检查 skills/tests/__init__.py 导入链
   - 建议优先级：P2

## 详细结果

### A. 构建与类型检查

- [A1] Backend Django check: ✅ 0 errors — `System check identified no issues (0 silenced)`
- [A2] Frontend tsc --noEmit: ✅ 0 errors — 之前的预存 TS 错误已清理
- [A3] Frontend vite build: ✅ 构建成功 — `✓ built in 19.72s`（有 chunk size 警告但非错误）
- [A4] Agent 模块导入: ✅ 导入成功 — `import core.orchestrator` OK（需从 agent/ 目录运行并 insert src/ 到 sys.path）

### B. 测试套件

- [B1] Backend 测试: ⚠️ 449 tests pass (128.99s)，但 `skills` app 有测试发现问题 — `ImportError: 'tests' module incorrectly imported from skills\tests`。排除 skills 后 8 个 app 全部通过
- [B2] Frontend 测试: ❌ 5 failed / 82 passed (87 total, 12.83s) — 4 test files failed (Dashboard.test.tsx 等)
- [B3] Agent 测试: ❌ 9 failed / 1393 passed / 2 skipped (85.78s) — 需 `-p no:django` 禁用 pytest-django（pyproject.toml 全局配置了 DJANGO_SETTINGS_MODULE 导致冲突）
- [B4] 测试执行时间: ⚠️ 首次记录基线 — B1=128.99s, B2=12.83s, B3=85.78s

### C. 技术债务状态

- [C1] 活跃 TD 数量: ✅ 0 — 所有活跃 TD 已清零（本次会话清理了 TD-073~TD-080 + TD-084）
- [C2] 超 3 轮未处理项: ✅ N/A — 活跃 TD 为 0
- [C3] 本月 TD 变动: ✅ 本月修复 9 项 (TD-073~080, TD-084)，新增 0 项，修复率 100%
- [C4] TD-046 长期遗留: ⚠️ 仍为 ❌ EVALUATED 状态，暂无新的 squash 时机

### D. 依赖管理

- [D1] Python 过期依赖: ⚠️ `pip list --outdated` 执行超时（检查每个包与 PyPI 对比很慢），未完成
- [D2] npm 过期依赖: ⚠️ 29 个过期包
- [D3] npm 安全漏洞: ❌ 7 vulnerabilities (3 low, 1 moderate, 3 high)
- [D4] 库版本冲突: ⚠️ 未详细检查（对照 library-conflicts.md 需手动审查）

### E. 数据库健康

- [E1] Migration 应用状态: ✅ 所有 migration `[X]` 已应用
- [E2] Migration drift: ✅ `No changes detected` — 模型与 migration 一致
- [E3] 迁移文件数量: ✅ 未检测到单个 app > 30 个 migration

### F. API 契约一致性

- [F1] Serializers 与前端类型同步: ⚠️ 未运行 `generate:api-types` 对比（需后端服务运行）
- [F2] URL 路由冲突: ⚠️ `tasks/urls.py` 有 8 个显式 `path()` 在 `include(router.urls)` 之后（lines 53-61），虽然当前无冲突但违反 TD-074 安全原则。`pipeline/urls.py` 和 `agents/urls.py` 正确
- [F3] 权限矩阵: ⚠️ 52 个 ViewSet 中 38 个无 `get_permissions` 覆写（依赖全局默认 IsAuthenticated 或类级 permission_classes）
- [F4] DRF 分页: ✅ 全局 `DEFAULT_PAGINATION_CLASS = PageNumberPagination` 已配置，`PAGE_SIZE=20`。仅 RecoveryLogViewSet 显式覆写为 None

### G. 文档与 AI 记忆一致性

- [G1] docs/ 索引: ✅ (动态计数, by sync_docs_index.py auto-stat) docs, 0 stale, 0 missing
- [G2] AI 记忆同步: ⚠️ 1 conflict, 82 warnings, 0 read-only（conflict 需排查）
- [G3] Skills 副本: ✅ 4 skills + 1 rule 副本一致
- [G4] lessons front-matter: ✅ 20 个 lesson 文件全部有 front-matter
- [G5] failure-modes 索引: ✅ 60 条索引行 vs 42 个 lesson 文件（差异来自家族合并和归档，合理）

### H. Git 卫生

- [H1] 工作树状态: ⚠️ 7 个 modified 文件（CRLF/LF 行尾归一化警告，无实际内容 diff）
- [H2] 未合并分支: ✅ 无未合并分支
- [H3] commit message 规范: ⚠️ 1/30 commit 缺 scope（`- docs: add monthly...`, 历史数字, 当前动态计数）
- [H4] 未 push commit: ⚠️ (动态计数, by git auto-stat) 个未 push commit

### I. 代码质量

- [I1] 巨型文件: ⚠️ 55 个文件 > 500 行。最严重：`agents/views.py` 3625 行、`protocol/consumers.py` 1561 行、`types/models.ts` 1547 行（生成文件）、`adb/device.py` 1672 行、`DeviceOperationPanel.tsx` 1397 行、`input_variants.py` 1260 行
- [I2] ESLint: ❌ 217 errors（全部 `@typescript-eslint/no-explicit-any`）
- [I3] Ruff: ❌ 709 errors（520 个可自动修复）
- [I4] 死代码: ⚠️ 未详细检查

### J. 安全检查

- [J1] .gitignore: ❌ 缺少 `*credentials*` 模式（.env / *.key / *.pem 已包含）
- [J2] 敏感文件泄露: ✅ 无敏感文件被 git 追踪
- [J3] DEBUG 模式: ⚠️ base.py 默认 DEBUG=True（prod.py 正确设为 False）
- [J4] JWT/CORS: ✅ JWT ACCESS_TOKEN_LIFETIME=15min + 旋转+黑名单；CORS 限 localhost:5173

### K. 部署就绪度

- [K1] Django check --deploy: ⚠️ 193 warnings（开发环境可接受，生产需修复）
- [K2] collectstatic: ✅ `--dry-run` 成功（未实际收集）
- [K3] 生产依赖: ✅ prod.txt 存在，package.json dependencies 完整

### L. 跨平台一致性

- [L1] Win32 API 封装: ❌ 2 处违规 — `backend/agent_client.py:59-60` 和 `worker/src/utils/screenshot_diagnostic.py:257` 直接调用 `ctypes.windll`，未封装在 `platforms/windows/`
- [L2] 平台抽象接口: ⚠️ 仅 Windows 平台实现完整，macOS/Linux 目录缺失（项目当前仅支持 Windows，可接受但需登记）
- [L3] 硬编码路径: ❌ `backend/device_bridge/discovery/emulator.py:93,96` 硬编码 BlueStacks/MEmu ADB 路径（应使用 env var + fallback 模式，如同文件 lines 478-479）

## 与上月对比

| 指标 | 上月 | 本月 | 变化 |
|------|------|------|------|
| 活跃 TD 数 | 9 | 0 | -9 ✅ |
| 测试通过率 | N/A | B1: 100% / B2: 94% / B3: 99% | 首次基线 |
| 测试执行时间 | N/A | B1: 129s / B2: 13s / B3: 86s | 首次基线 |
| npm 漏洞数 | N/A | 7 (3 high) | 首次基线 |
| 巨型文件数 | N/A | 55 | 首次基线 |

## 建议行动项

1. **[P1]** 修复 L1 — 迁移 `backend/agent_client.py:59-60` 和 `worker/src/utils/screenshot_diagnostic.py:257` 的 Win32 调用到 `platforms/windows/`
2. **[P1]** 修复 J1 — 添加 `*credentials*` 到 `.gitignore`
3. **[P1]** 修复 D3 — `npm audit fix` 处理 3 个 high 漏洞
4. **[P2]** 修复 I3 — `ruff check . --fix` 自动修复 520 个 ruff errors
5. **[P2]** 修复 B1 skills app — 排查 `skills/tests/__init__.py` 导入链问题
6. **[P2]** 修复 B2 — 排查 5 个前端失败测试
7. **[P2]** 修复 B3 — 排查 9 个 agent 失败测试
8. **[P2]** 修复 L3 — 将 `emulator.py:93,96` 硬编码路径改为 env var + fallback
9. **[P2]** 修复 F2 — 将 `tasks/urls.py` 中 8 个 `path()` 移到 `include(router.urls)` 之前
10. **[P3]** 排查 G2 — sync_ai_memory 1 conflict
11. **[P3]** 逐步清理 I2 — 217 个 `@typescript-eslint/no-explicit-any` 替换为具体类型
12. **[P3]** 推送 H4 — 3 个未 push commit（需用户授权）

## 迭代回顾

### 第一轮迭代 (2026-07-11 首次检查)

- **本次新增检查项**：B5, B6, B7, I5, I6, I7（共 6 项，总项数 46 → 52）
- **触发原因**：
  - **B5** (测试 URL 路径一致性)：skills 测试用 `my_published` 但 API `@action(url_path='my-published')` 用 kebab-case → 3 个 404 失败
  - **B6** (测试导入路径有效性)：Devices 测试导入 `@/pages/Devices/index` 但页面已拆分为 DeviceCenterPage 等 4 个文件 → import 失败
  - **B7** (Store Mock 完整性)：Dashboard 测试 mock `useDeviceStore` 缺少 `devices` 属性 → `undefined.forEach` 报错
  - **I5** (Base64 路径误判)：`template_match.py` 用 `'/' in template_config` 判断路径，base64 字符串可含 `/` → 模板加载失败
  - **I6** (资源释放完整性)：`screenshot.py set_hwnd` 只释放 WGC 不释放 DXGI → 资源泄漏
  - **I7** (重试装饰器兼容)：`connection.py send_message` except 块设 `_connected=False` → 重试装饰器提前返回
- **未新增但需关注**：
  - `test_resource_monitor.py` mock 目标错误（`psutil.Process.cpu_percent` vs `psutil.cpu_percent`）— 属于 B1 测试套件覆盖范围
  - `test_device_abstraction.py` mock 不完整 — 属于 B1 测试套件覆盖范围

### 第二轮迭代 (2026-07-11 行动项修复后)

- **本次新增检查项**：M1-M5, N1-N2, O1-O3（共 10 项，总项数 52 → 62）
- **触发原因**：
  - **M1-M5** (架构一致性)：用户反馈需要检查架构方面的问题 — 平台抽象层完整性、业务逻辑与平台代码隔离、模块间依赖方向、URL 路由挂载规范、设计文档与代码同步
  - **N1-N2** (项目卫生)：清理中发现 13 个空目录 + 5 个空文件，表明需要定期扫描防止残留垃圾堆积
  - **O1-O3** (真实设备验证)：用户反馈"不需要保留 mock 的值来扰乱后面的测试，必须用真的数据来测试" — 新增雷电模拟器连通性、设备扫描 API、截图功能三项真实设备测试
- **发现的新问题类型**：
  - **F821/F811 真实 bug**：ruff 检查发现的 undefined-name 和 redefined-class 是真实运行时 bug（registry.py 导入缺失、beat.py NameError、serializers.py 重复类定义），非风格问题 — 已被 I3 (Ruff 检查) 覆盖，无需新增检查项
  - **空 scaffold 文件**：`backend/docs/serializers.py` 是 Django startapp 生成的空文件从未使用 — 被 N2 (空文件扫描) 覆盖
  - **空孤儿目录**：`worker/src/ocr` 是重构后的残留目录 — 被 N1 (空目录扫描) 覆盖
  - **ESLint 实际错误数远低于报告**：原报告称 217 个 `no-explicit-any` 错误，实际只有 8 个 — 说明月度检查的 ESLint 统计方法需要改进，未来应使用 JSON 格式精确统计
- **ESLint 统计修正**：原报告 I2 称 217 errors，实际用 `--format json` 精确统计仅 8 errors（3 files）。差异原因：原统计可能包含了 warnings 或用了不同的 eslint 配置。已修复为 0 errors。

## N## 月度评估 (2026-07-26, 基于 track_n_trigger.py)

> **统计来源**: `conda run -n gaf python scripts/bootstrap/track_n_trigger.py --dry-run --verbose`
> **评估机制**: N181 月度退役评估 (spec-62 TD-311 强化: 季度→月度 + Active N## > 70 硬阈值紧急评估)
> **退役条件**: A 连续 3 spec 未触发 / B 已被新 N## 覆盖 / C AI 默认行为已符合 (退役 ≠ 删除, 迁 §Retired)

### 总览

- **Active N## 总数**: 67 (未触发 N181 硬阈值 > 70 紧急评估)
- **trigger_count > 0 数**: 67 (100%, 无零触发 N##)
- **平均 trigger_count**: 3.8 (总和 253 / 67)
- **trigger_count ≤ 2 数**: 32 (退役候选, 见下)
- **本月新增 N##**: N182-N188 (spec-88, 2026-07-22~25, 三维根因评估体系 + agent/venv/conda 环境)

### Top 10 高频 N##

| N## | count | last_triggered | 主题 |
|-----|-------|---------------|------|
| N167 | 24 | 2026-07-21 | 代码重构 7 维度评估清单 |
| N176 | 19 | 2026-07-22 | spec 完成立即 commit 再回填 hash |
| N126 | 15 | 2026-06-21 | 文档诚实标记 (Mock/Stub 标 🔧, 真实实现标 ✅) |
| N134 | 10 | 2026-07-07 | workflow skill 未被触发 |
| N151 | 9 | 2026-07-16 | 大修改架构视角原则 (5 步架构视角) |
| N166 | 9 | 2026-07-21 | L3 持续评估循环 + 沉淀纪律 |
| N181 | 9 | 2026-07-22 | 规则膨胀无退役 (月度评估机制本身) |
| N150 | 8 | 2026-07-12 | pre-commit 失败根因修复 + 预存错误当场处理 |
| N177 | 7 | 2026-07-21 | 测试时间越来越久 (全套 pytest 分级) |
| N109 | 6 | 2026-06-16 | 计划内任务仍问用户 (AI 自决) |

> **观察**: Top 10 集中在 spec-59 系列 (N166/N167/N176/N177/N181) + 核心红线 (N126/N150/N109) + 工作流机制 (N134/N151), 反映 2026-07 治理体系重构期高活跃特征。

### 退役候选 (N181 条件 A: trigger_count ≤ 2 作代理)

#### A 组 — 新增 N## (spec-88, 2026-07-22~25 新增, 观察期不足 3 spec, 暂不退役)

| N## | count | last_triggered | 主题 |
|-----|-------|---------------|------|
| N183 | 2 | - | bug 修复三维根因评估 |
| N184 | 2 | - | 节点观测性硬约束 |
| N185 | 2 | 2026-07-22 | 测试覆盖盲区 = AI 思维链缺陷 |
| N186 | 1 | 2026-07-23 | agent 独立进程单例锁缺失 |
| N187 | 1 | 2026-07-23 | venv 部署脚本依赖漂移 |
| N188 | 1 | - | conda gaf 环境规则多次未生效 |

#### B 组 — 老旧低频 N## (需逐个核查条件 B 已被覆盖 / 条件 C 默认行为已符合)

| N## | count | last_triggered | 主题 |
|-----|-------|---------------|------|
| N111 | 2 | 2026-07-15 | 命令超时仍死等 (6 步超时应对) |
| N116 | 2 | 2026-06-24 | 并发状态管理 (SyncLock) |
| N122 | 2 | 2026-06-21 | scripts/ 维护 (复用 frontmatter.py) |
| N123 | 1 | 2026-06-21 | ai-memory restructure (结构变更跑 sync) |
| N131 | 2 | 2026-06-22 | Playwright + browser-use 共存 |
| N133 | 2 | 2026-06-30 | 模拟器设备控制 + 测试循环点击 |
| N136 | 2 | 2026-06-30 | URL 路由前缀重复 |
| N137 | 1 | 2026-06-30 | TS 6.0 erasableSyntaxOnly |
| N138 | 1 | 2026-06-30 | ctypes HRESULT 有符号比较 |
| N139 | 1 | 2026-07-02 | Vite proxy localhost 解析歧义 |
| N140 | 1 | 2026-07-03 | 文件命名禁止版本号 (硬约束) |
| N141 | 2 | 2026-07-07 | 截图方法 benchmark 盲区 + DPI awareness |
| N142 | 1 | 2026-07-05 | 复制重命名必须改全部标识符 |
| N143 | 1 | 2026-07-05 | 认证图片 blob fetch |
| N144 | 1 | 2026-07-05 | antd 5.x Card bodyStyle 弃用 |
| N146 | 2 | 2026-07-11 | ctypes.CDLL 热循环单例缓存 |
| N148 | 2 | 2026-07-07 | 双向控制消息路由标识 |
| N149 | 1 | 2026-07-07 | task.dispatch device_info gap |
| N152 | 2 | 2026-07-09 | DRF 分页与前端数组期望不匹配 |
| N157 | 1 | 2026-07-11 | AI memory 文档虚构实现 |
| N159 | 2 | 2026-07-13 | 长任务子 agent 分发 |
| N164 | 1 | 2026-07-14 | L1/L2 不加载教训内容 |
| N168 | 1 | 2026-07-17 | backup/restore 双套反模式 + SQL 注入 |
| N175 | 1 | 2026-07-18 | subagent 并行结果落地不清 |
| N179 | 1 | 2026-07-21 | 反思形式化 (无 A 类就过) |
| N180 | 1 | 2026-07-21 | 元评估死循环 (只列弱项不开 spec) |

### 评估结论

- ✅ **本月无 N## 退役** — 67 个 Active N## 全部 trigger_count > 0, 无零触发项; 未触发 N181 硬阈值 (Active > 70)
- ⏳ **A 组 (N183-N188) 暂不评估** — spec-88 (2026-07-22~25) 新增, 观察期不足 3 spec 周期, 需累计 3 个 spec 后再核查条件 A
- 🔍 **B 组 26 个老旧低频 N## 待下月重点核查**:
  - **standing rule 类不建议退役** (虽低频但仍是硬约束): N140 (文件名禁版本号)、N137 (TS 6.0 语法)、N138 (ctypes HRESULT)、N139 (Vite proxy)、N144 (antd 弃用) — 这些是技术栈特定规则, 低频但不可替代
  - **可能符合条件 B (已被新 N## 覆盖)**: N111 (命令超时) 部分被 N166 (持续评估循环) 覆盖; N175 (subagent 落地) 部分被 N172 (AI 主动 subagent) 覆盖 — 需下月逐个验证
  - **可能符合条件 C (AI 默认行为已符合)**: N123 (ai-memory restructure)、N157 (文档虚构) — 需观察 AI 近期行为是否默认遵守
- 🔧 **本月无新增 N## 建议** — spec-88 (2026-07-22) 已新增 N182-N185 三维根因评估体系 + N186-N188 环境/进程类, 覆盖 2026-07 暴露的主要 gap
- ⏳ **下次评估**: 2026-08-26 (N181 月度机制)

## 行动项修复状态（2026-07-11 更新）

| # | 优先级 | 描述 | 状态 | commit |
|---|--------|------|------|--------|
| 1 | P1 | L1 Win32 API 迁移 | ✅ FIXED | - |
| 2 | P1 | J1 .gitignore *credentials* | ✅ FIXED | - |
| 3 | P1 | D3 npm audit fix | ✅ FIXED | - |
| 4 | P2 | I3 ruff auto-fix | ✅ 709→0 errors | -, -, - |
| 5 | P2 | B1 skills test URL | ✅ FIXED | - |
| 6 | P2 | B2 frontend 5 tests | ✅ FIXED | - |
| 7 | P2 | B3 agent 9 tests | ✅ FIXED | - |
| 8 | P2 | L3 emulator hardcoded path | ✅ FIXED | - |
| 9 | P2 | F2 tasks/urls.py ordering | ✅ FIXED | - |
| 10 | P3 | G2 sync_ai_memory conflict | ✅ AUTO-RESOLVED (0 conflicts) | — |
| 11 | P3 | I2 eslint any errors | ✅ FIXED (8→0 errors, 实际仅 8 个非 217) | - |
| 12 | P3 | H4 push commits | ⏳ 需用户授权 (10 个未 push) | — |
| 13 | P2 | F821/F811 真实 bug | ✅ FIXED (3 bugs: registry.py, beat.py, serializers.py) | - |
| 14 | P2 | 空目录/空文件清理 | ✅ FIXED (13 空目录→2 gitignored, 5 空文件→3 占位) | (本轮) |
| 15 | P2 | 月度检查新增 M/N/O 类别 | ✅ DONE (架构检查+项目卫生+真实设备验证, 52→62 项) | (本轮) |
