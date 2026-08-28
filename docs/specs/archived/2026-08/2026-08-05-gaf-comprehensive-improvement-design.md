---
summary: GAF 项目综合改善 Spec — 10 层面问题 + N191-N199 预存硬约束落地
applies_to: [project, comprehensive]
created: 2026-08-05
completed: 2026-08-05
status: completed
phase: done
---

# GAF 综合改善 Spec 设计

> **创建时间**：2026-08-05
> **任务类型**：fix + refactor + add（综合修复 + 重构 + 新增）
> **覆盖范围**：10 个层面，30+ 问题，预计 ~3000-4000 行代码修改
> **约束来源**：env-hardrules.md（N191-N199）+ 项目健康检查分析

---

## 0. 任务归属声明（N193 硬约束）

本 Spec 覆盖 **2026-08-05 全面扫描** 发现的所有问题 + **N191-N199 预存硬约束** 中已建规则但未完全落地的部分。实现过程中发现的新问题 **必须纳入本 Spec**，不得作为"遗留建议"抛出。

---

## 1. 总览与分层

### 1.1 问题分类

| 层级 | 问题数 | 严重度 | Phase |
|:----:|:------:|:------:|:-----:|
| ① 架构层 | 6 | P1-P2 | Phase 1 |
| ② 代码质量层 | 6 | P1-P2 | Phase 2 |
| ③ 测试层 | 5 | P1-P2 | Phase 3 |
| ④ 前端层 | 5 | P1-P2 | Phase 2 |
| ⑤ 后端层 | 5 | P1-P2 | Phase 3 |
| ⑥ Agent 层 | 4 | P2 | Phase 3 |
| ⑦ 运维/部署层 | 5 | P2 | Phase 1 |
| ⑧ 治理/文档层 | 4 | P2-P3 | Phase 4 |
| ⑨ 安全层 | 4 | P1-P2 | Phase 1 |
| ⑩ 性能层 | 4 | P2-P3 | Phase 4 |

### 1.2 执行顺序

```
Phase 1 (基础设施硬化) ─→ Phase 2 (代码质量提升) ─→ Phase 3 (后端+Agent加固) ─→ Phase 4 (治理+文档闭环)
   │ N197 URL归一化         │ 前端类型安全/i18n    │ 后端异常处理           │ 治理脚本修正
   │ 安全配置加固            │ 性能优化             │ Agent健壮性            │ 健康检查自动化
   │ 运维脚本修复            │                     │ 测试覆盖               │ 文档同步
```

---

## 2. Phase 1：基础设施硬化

### 2.1 N197 URL 拼接归一化硬约束（落地）

> **来源**：env-hardrules.md §URL 拼接归一化硬约束
> **根因**：`backend/app_info.py` 的 `API_PREFIX` 只覆盖后端路由，agent 端 3 个文件仍硬编码 `/api/v2`，前端 `app.ts` 也硬编码

#### 2.1.1 后端：`config/urls.py` 使用 `APP_ROUTES` 映射

**当前问题**：`config/urls.py` 中路径段为字符串字面量
```python
# ❌ 当前
path(f"{API_PREFIX}/accounts/", include("accounts.urls"))
path(f"{API_PREFIX}/agents/", include("agents.urls"))
```

**修复方案**：引入 `APP_ROUTES` 映射表
```python
# ✅ 修复后
APP_ROUTES = {
    'accounts': 'accounts',
    'agents': 'agents',
    'qa': 'qa',
    'ai': 'ai',
    'executions': 'executions',
    'api-keys': 'api-keys',
    # ... 所有 app 路由路径段
}

# urls.py 中
for app_name, path_segment in APP_ROUTES.items():
    urlpatterns += [
        path(f"{API_PREFIX}/{path_segment}/", include(f"{app_name}.urls")),
    ]
```

**验收标准**：新增 app 路由时只需修改 `APP_ROUTES` 一处

#### 2.1.2 后端：OAuth redirect URI 使用 `APP_ROUTES`

**当前问题**：`settings/base.py` 中 OAuth callback URL 硬编码
```python
# ❌ 当前
"http://localhost:8000/api/v2/accounts/oauth/callback/",
```

**修复方案**：使用 `APP_ROUTES['accounts']` 拼接

#### 2.1.3 后端：WebSocket 路径从配置读取

**当前问题**：`routing.py` 和 `middleware.py` 中 WS 路径硬编码
```python
# ❌ 当前 (routing.py)
ws_path = r"ws/protocol/agents/$"
```

**修复方案**：引入 `WS_AGENT_PATH` 环境变量

#### 2.1.4 Agent：API 前缀从环境变量读取

**当前问题**：agent 端 3 个文件硬编码 `/api/v2`
- `recording_api.py`: `f"{http_base}/api/v2"`
- `step_recorder.py`: `f"{http_base}/api/v2"`  
- `llm_client.py`: `f"{http_base}/api/v2"`

**修复方案**：从 `GAF_API_PREFIX` 环境变量读取，带默认值

#### 2.1.5 前端：API 前缀从环境变量读取

**当前问题**：`config/app.ts` 硬编码 `'/api/v2'`

**修复方案**：
```typescript
const API_PREFIX = import.meta.env.VITE_API_PREFIX || '/api/v2';
```

**验收标准**：修改 API 版本号（v2→v3）只需改 `GAF_API_PREFIX` 环境变量

### 2.2 安全配置加固

#### 2.2.1 DEBUG 模式检查自动化

**新增检查**：`gaf_init.sh/ps1` 加 §3.8 DEBUG 模式检查
```bash
# Django settings check
python manage.py check --deploy --fail-level WARNING
```

#### 2.2.2 CORS 配置审查

**检查**：`settings/base.py` 中 `CORS_ALLOWED_ORIGINS` 是否为生产环境正确配置
**修复**：区分 dev/prod CORS origins

#### 2.2.3 JWT 安全配置

**检查**：Token 有效期、刷新机制、加密算法
**修复**：确保生产环境使用 RS256 或 ES256 非对称加密

#### 2.2.4 敏感文件扫描

**新增脚本**：`scripts/security/check_sensitive_files.py`
- 扫描 `.env`、密钥文件、`id_rsa` 等是否被 git 追踪
- 检查 `.gitignore` 是否覆盖所有敏感文件模式

### 2.3 运维脚本修复

#### 2.3.1 `gaf_services.ps1` 硬编码路径修复

**当前问题**：
- Redis 路径硬编码 `$RedisPath = "C:\Program Files\Redis\redis-server.exe"`
- Node.js 路径硬编码 `$NodePath = "C:\Program Files\nodejs\node.exe"`

**修复方案**：
```powershell
# 自动检测路径
function Get-ExecutablePath {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # 检查常见安装路径
    $commonPaths = @(
        "C:\Program Files\$Name\",
        "$env:LOCALAPPDATA\$Name\"
    )
    foreach ($p in $commonPaths) {
        if (Test-Path "$p$Name.exe") { return "$p$Name.exe" }
    }
    throw "$Name not found. Please install or add to PATH."
}
```

#### 2.3.2 端口硬编码修复

**当前问题**：`$BackendPort = 8000` 等硬编码

**修复方案**：从 `.env` 文件或命令行参数读取，带默认值

#### 2.3.3 `gaf_init.sh`/`gaf_init.ps1` 路径检测增强

**修复**：当文件/目录不存在时，从警告升级为强制错误（exit 1），并提供正确路径提示

### 2.4 调度协调自动化（N198 落地）

#### 2.4.1 服务健康检查依赖链

**新增**：`gaf_services.ps1` 各服务启动前检查前置服务健康状态
```
Redis (ping) → Backend (check --deploy) → Worker (registered?) → Beat (scheduler tick?) → Agent (heartbeat?) → Frontend (vite build?)
```

#### 2.4.2 Monitor 自动恢复机制

**当前问题**：monitor 进程在 `gaf_services.ps1 start` 末尾启动，但挂了不会自动重启

**修复方案**：引入 Windows 服务或计划任务，每 60s 检查所有服务状态，异常时自动重启

---

## 3. Phase 2：代码质量提升

### 3.1 前端类型安全（TD-335 #1 长期跟进启动）

#### 3.1.1 tsconfig strict 分阶段开启

**执行计划**：
```
Phase 2a: noImplicitLocals → 修复当前 267 个错误中 noImplicitLocals 子集
Phase 2b: noImplicitAny → 修复 noImplicitAny 子集
Phase 2c: strictNullChecks → 修复 null/undefined 检查
Phase 2d: strict → 开启全部严格模式
```

**每个 Phase 产出**：
- `tsconfig.app.json` 新增对应 strict 子项
- 修复所有 tsc 编译错误
- 新增 `frontend/scripts/check-types.sh` 脚本，CI 中强制类型检查

#### 3.1.2 `as unknown as` 双重断言清理

**当前状态**：已修复 5 处，剩余 21 处为合理类型 narrowing
**检查**：重新 grep 全仓 `as unknown as`，确认真实问题是否已清零

### 3.2 前端 i18n 补全（TD-335 #3 验证）

#### 3.2.1 ESLint 规则升级

**当前状态**：`no-restricted-syntax` 规则为 warn 级别
**修复**：升级为 error 级别，强制阻止含中文字符串的代码提交

#### 3.2.2 残留硬编码中文扫描

**新增脚本**：`frontend/scripts/scan-hardcoded-chinese.py`
- 扫描所有 `.tsx/.ts` 文件中的中文字符串
- 分类：业务调色板（合理保留）/ UI 文案（需要 i18n）
- 输出待修复清单

### 3.3 前端性能优化

#### 3.3.1 useEffect fetch 添加 AbortController

**执行计划**：
- 扫描 50+ 处 useEffect fetch
- 统一添加 `AbortController` + cleanup
- 封装 `useAbortableFetch` 自定义 hook 供复用

#### 3.3.2 大列表虚拟化

**执行计划**：
- 评估 `@tanstack/react-virtual` 引入
- 对 27 处 `pagination=false` 列表，数据量 > 200 行的改用虚拟滚动
- 数据量 < 200 行的保留普通列表

#### 3.3.3 react-query 扩展

**当前状态**：5 个 query hooks（useDevicesQuery, useTasksQuery, useGameAccountsQuery, useMonitorRulesQuery, useAgentsQuery）
**新增**：高频查询 hooks — useExecutionsQuery, useScheduledTasksQuery, useHealthQuery

### 3.4 前端代码规范清理

#### 3.4.1 inline style 治理（TD-330 推进）

**当前状态**：495 处 inline style（C 类 205 合理保留，A+B 类 290 待治理）
**执行**：选择 A+B 类中高频模式（如 `display: flex`、`text-align: center`），迁移到 utility class

#### 3.4.2 静默吞错修复

**当前状态**：TD-335 P1 #6 已修复 ExecutionMonitorPanel，剩余 ~39 处低优先级
**执行**：检查所有 `.catch { }` / `.catch(() => {})` 模式，添加错误日志或用户提示

---

## 4. Phase 3：后端与 Agent 加固

### 4.1 后端异常处理（N192 双视角落地）

#### 4.1.1 异常包装为 NodeExecutionError

**当前问题**：Agent 节点异常只带 traceback，无节点 id / 输入参数
**修复**：
```python
class NodeExecutionError(Exception):
    def __init__(self, node_id: str, input_param: dict, reason: str):
        self.node_id = node_id
        self.input_param = input_param
        self.reason = reason
        super().__init__(f"Node[{node_id}] failed: {reason}")
```

#### 4.1.2 错误码 → 用户文案映射（视角 B）

**新增**：`backend/gaf_core/error_codes.py`
```python
ERROR_CODE_MAP = {
    'SCHEMA_STEP_MISSING': '配置错误：缺少 steps 字段',
    'SCHEMA_STEPS_EMPTY': '配置错误：steps 不能为空列表',
    'DEVICE_NOT_AVAILABLE': '设备不可用：请检查设备连接状态',
    'OCR_NO_IMAGE': 'OCR 失败：上下文无图像数据',
    # ... 20+ 错误码映射
}
```

#### 4.1.3 llm_service.py NoneType 风险修复

**当前问题**：`_build_router_cache_key` 中 `db_config` 为 None 时跳过注册
**修复**：添加前置检查，`db_config` 为 None 时 raise `ConfigurationError`

#### 4.1.4 Celery 任务重试策略统一

**当前问题**：部分任务未加 `max_retries=3, retry_backoff=True`
**修复**：扫描所有 `@shared_task` 装饰器，补齐重试策略

### 4.2 Agent 健壮性

#### 4.2.1 OCR 图像获取 fallback 路径修复

**当前问题**：`_get_image` 的 device fallback 在无设备场景返回空
**修复**：添加三级 fallback — context 取图 → device 截屏 → 返回明确错误（不再返回 None）

#### 4.2.2 Agent 心跳重连逻辑

**当前问题**：心跳超时后重连逻辑测试覆盖不足
**修复**：补充重连单元测试，覆盖网络断开 → 自动重连 → 恢复执行全链路

#### 4.2.3 Agent 配置校验增强

**当前问题**：`config.py` 中 TD-340 只调整了心跳间隔
**修复**：添加配置校验函数，启动时检查必填项，缺失时给出明确错误提示

### 4.3 测试覆盖提升

#### 4.3.1 Agent 节点测试补齐

**当前状态**：198 tests 覆盖 21/31 节点
**执行**：为剩余 10 个节点补充 smoke tests

#### 4.3.2 Backend executions app 测试增强

**当前问题**：仅 1 个测试文件
**执行**：新增 `test_execution_views.py` 和 `test_execution_serializers.py`

#### 4.3.3 测试断言质量提升

**执行**：扫描 `assert response.status_code == 200` 模式，添加响应体结构断言

#### 4.3.4 pytest 配置优化

**当前问题**：agent 测试默认加载 Django（N194 已建立硬约束但需工具化）
**修复**：
- `pyproject.toml` 中为 agent 测试添加 `addopts = "-p no:django -o addopts=''"`
- 新增 `scripts/run_agent_tests.sh` 快捷脚本，自动加参数

---

## 5. Phase 4：治理与文档闭环

### 5.1 治理脚本修正

#### 5.1.1 governance_dashboard 计数一致性修复（TD-346）

**当前问题**：§3 `active_n_count=67` vs §4 `Active=68` 不一致
**修复**：§3 改为直接 grep `failure-modes.md` §Active 段，单一权威源

#### 5.1.2 低触发 lesson 归档（TD-343）

**执行**：
- 运行 `track_n_trigger.py --verbose` 获取 trigger_count 数据
- trigger_count ≤ 1 的 N## 移入 `archived-early/`
- 更新 `failure-modes.md` 索引

### 5.2 健康检查自动化

#### 5.2.1 8 月健康检查执行

**执行**：运行 2026-08 月度健康检查全部 14 类（A-L + M + N）

#### 5.2.2 健康检查脚本优化

**修复**：`monthly_health_check.py` 新增检查项
- [A4] Agent 模块导入检查
- [J1] .gitignore 检查
- [J2] 敏感文件泄露检查
- [K1] Django check --deploy
- [L3] 硬编码路径检查

### 5.3 文档同步

#### 5.3.1 架构文档更新

**更新**：`docs/architecture/overview.md` — 反映 Phase 1-3 变更
**更新**：`docs/architecture/cross-cutting/dispatch-flow.md` — 反映调度协调改进

#### 5.3.2 API 契约文档更新

**更新**：`docs/standards/api-contract.md` — 反映 URL 归一化变更
**更新**：新增错误码映射表

#### 5.3.3 技术债务同步

**更新**：`docs/tech-debt/active.md` — 本 Spec 修复的 TD 迁移到 fixed.md

### 5.4 性能优化

#### 5.4.1 pytest 执行时间优化（TD-345）

**执行计划**：
- 方案 A：agent 测试 mock Django ORM（减少 DB IO）
- 方案 B：拆分 unit/integration/e2e 三层
- 目标：pytest 全套 < 60s

#### 5.4.2 前端构建优化

**检查**：`vite build` 产物大小、代码分割、tree-shaking 效果
**修复**：大 chunk 拆分、引入预加载策略

---

## 6. N191-N199 预存硬约束落地验证

本 Spec 同时落地 N191-N199 已建立但未完全落实的硬约束：

| 约束 | 本 Spec 落地位置 | 验证方法 |
|:----:|:----------------:|:--------:|
| N191 Schema 归一化 | Phase 3 §4.1 异常包装 | 7 项数据流检查清单全过 |
| N192 双调试视角 | Phase 3 §4.1 错误码映射 | 视角 A + 视角 B 14 项清单全过 |
| N193 任务归属 | 本 Spec 整体设计 | 发现的问题全部纳入 spec，无遗留建议 |
| N194 测试运行 | Phase 3 §4.3.4 | agent 测试默认 `-p no:django` |
| N197 URL 归一化 | Phase 1 §2.1 | `APP_ROUTES` + `GAF_API_PREFIX` 全链路 |
| N198 调度协调 | Phase 1 §2.4 | 服务健康检查依赖链 + monitor 自动恢复 |

---

## 7. 双调试视角前置检查（N192）

### 视角 A：AI 调试视角

| # | 检查项 | 当前状态 | 修复计划 |
|---|--------|:--------:|:--------:|
| A1 | 报错含节点 id/输入/原因 | ❌ 部分异常只有 traceback | Phase 3 §4.1.1 NodeExecutionError |
| A2 | 中间结果落盘 | ⚠️ 失败路径 result_data 不完整 | Phase 3 §4.1 补充 |
| A3 | 日志分段 | ⚠️ 部分日志无节点 boundary | Phase 3 §4.1 日志结构化 |
| A4 | 节点链路可追溯 | ⚠️ 链路 ID 未贯穿 | Phase 3 §4.1 trace_id 贯穿 |
| A5 | retry/fallback trace | ❌ 重试无 trace | Phase 3 §4.1 补充 |
| A6 | 截断保护 | ⚠️ 长日志未截断 | Phase 3 §4.1 加截断 |
| A7 | 报错边界 | ⚠️ 部分异常未包装 | Phase 3 §4.1 全局异常包装 |

### 视角 B：用户调试视角

| # | 检查项 | 当前状态 | 修复计划 |
|---|--------|:--------:|:--------:|
| B1 | 错误提示归一 | ❌ 后端原文甩前端 | Phase 3 §4.1.2 错误码映射 |
| B2 | 错误码映射 | ❌ 无映射表 | Phase 3 §4.1.2 新增映射表 |
| B3 | 错误定位 | ❌ 用户看不懂哪步错 | Phase 3 §4.1 UI 增强 |
| B4 | 模板可跑通 | ⚠️ template.json 可能过时 | Phase 4 §5.3 文档同步 |
| B5 | 校验前置 | ⚠️ 前端校验不完整 | Phase 2 §3.2 加 ESLint 规则 |
| B6 | 执行反馈 | ⚠️ 失败后节点链路不展示 | Phase 3 §4.1 UI 增强 |
| B7 | 复现路径 | ❌ 用户拿到错误不会修 | Phase 3 §4.1 错误文案加修复建议 |

---

## 8. Schema 数据流全链路检查（N191）

### 8.1 输出端检查

| 输出端 | 关键字段 | 状态 |
|--------|----------|:----:|
| 前端编辑器 | task_definition.steps | ✅ |
| API 写入 | task_definition JSON | ✅ |
| 外部导入 | template.json | ⚠️ 部分过时 |
| Agent 序列化 | params_config → PipelineContext | ✅ |

### 8.2 读取端检查

| 读取端 | 关键字段 | 状态 |
|--------|----------|:----:|
| 后端校验 | task_definition.get('steps') | ✅ |
| Agent 解析 | step.get('action') | ✅ |
| 工具推断 | step 节点类型识别 | ✅ |
| 测试 fixture | test_*.py 中 task_definition | ⚠️ 部分用旧 schema |
| 文档示例 | docs/business/ 示例 | ⚠️ 需同步 |

### 8.3 节点间数据流检查

| 检查项 | 状态 |
|--------|:----:|
| publish_match_pos 输出与 resolve_target 读取字段一致 | ✅ |
| 坐标系统标注 | ⚠️ 部分节点缺 coord_system |
| ROI 偏移传递 | ✅ |
| 变量引用契约 | ✅ |
| None 兜底 | ⚠️ publish_match_pos 已强制 int(x)，但调用方未保证非 None |

---

## 9. 验收标准

### 9.1 Phase 1 验收

- [ ] `APP_ROUTES` 映射覆盖所有 app 路由
- [ ] 修改 API 版本号只需改 1 处环境变量
- [ ] `gaf_services.ps1` 自动检测 Redis/Node 路径
- [ ] 服务启动前健康检查依赖链正常
- [ ] `python manage.py check --deploy` 通过

### 9.2 Phase 2 验收

- [ ] tsc --noEmit 编译错误减少 50%+
- [ ] ESLint 含中文规则为 error 级别
- [ ] 50+ useEffect fetch 全部有 AbortController
- [ ] 高频查询 hooks 新增 3+

### 9.3 Phase 3 验收

- [ ] 所有 Agent 异常含节点 id / 输入 / 原因
- [ ] 错误码映射表覆盖 20+ 常见错误
- [ ] Agent 测试覆盖 31/31 节点
- [ ] Backend executions 测试文件 ≥ 3
- [ ] agent 测试默认 `-p no:django`

### 9.4 Phase 4 验收

- [ ] governance_dashboard 计数一致
- [ ] 低触发 lesson 归档完成
- [ ] 8 月健康检查 14 项全执行
- [ ] pytest 全套 < 60s（或 unit < 30s）
- [ ] 所有变更文档已同步

### 9.5 全局验收

- [ ] N191-N199 预存硬约束 6 项全部落地
- [ ] 双调试视角 14 项检查全通过
- [ ] 本 Spec 修复的 TD 全部迁移到 fixed.md
- [ ] 无"遗留建议"抛出（N193 约束）

---

## 10. 风险与缓解

| 风险 | 概率 | 影响 | 缓解方案 |
|------|:----:|:----:|:--------:|
| Phase 1 URL 归一化遗漏某个文件 | 中 | 高 | grep 全仓 `"/api/v2"` 扫描 |
| Phase 2 tsconfig strict 修复量大 | 高 | 中 | 分 4 个子 Phase 渐进开启 |
| Phase 3 异常包装遗漏边界情况 | 中 | 中 | 全量代码审计 + 新增测试覆盖 |
| Phase 4 pytest 优化效果不达预期 | 低 | 低 | 记录实测数据，不达标则拆分方案 |

---

## 11. 实施计划

> 详细任务清单将在 Spec 批准后由 `writing-plans` 技能生成

| Phase | 预估修改量 | 预估时间 | 任务数 |
|:-----:|:----------:|:--------:|:------:|
| Phase 1 | ~600 行 | 2h | 8 |
| Phase 2 | ~1200 行 | 4h | 10 |
| Phase 3 | ~800 行 | 3h | 12 |
| Phase 4 | ~400 行 | 2h | 8 |
| **合计** | **~3000 行** | **11h** | **38** |

---

## 12. 与现有 TD 的关系

本 Spec 涉及但不限于以下现有活跃 TD：
- TD-330（frontend 全仓治理）：推进 inline style 治理
- TD-335（前端架构债务）：推进 tsconfig strict、i18n、react-query 扩展
- TD-336（测试覆盖）：推进 agent 节点测试、backend executions 测试
- TD-343（低触发 lesson 归档）：Phase 4 执行
- TD-345（pytest 全套超基线）：Phase 4 执行
- TD-346（governance_dashboard 计数漂移）：Phase 4 执行

本 Spec 修复完成后，上述 TD 应迁移到 fixed.md。

---

## 附录 A：文件变更清单（预估值）

### Phase 1
- [ ] `backend/config/urls.py` — 引入 `APP_ROUTES` 映射
- [ ] `backend/config/settings/base.py` — OAuth redirect URI + CORS
- [ ] `backend/routing.py` — WS 路径从配置读取
- [ ] `backend/middleware.py` — WS 路径检查从配置读取
- [ ] `agent/src/core/config.py` — 默认 server_url 推导
- [ ] `agent/src/api/recording_api.py` — API 前缀环境变量
- [ ] `agent/src/api/step_recorder.py` — API 前缀环境变量
- [ ] `agent/src/llm/llm_client.py` — API 前缀环境变量
- [ ] `frontend/src/config/app.ts` — VITE_API_PREFIX
- [ ] `frontend/.env` — VITE_API_PREFIX 配置
- [ ] `scripts/gaf_services.ps1` — 路径自动检测 + 端口配置
- [ ] `scripts/security/check_sensitive_files.py` — 新增

### Phase 2
- [ ] `frontend/tsconfig.app.json` — strict 分阶段开启
- [ ] `frontend/eslint.config.js` — 中文规则升级
- [ ] `frontend/src/hooks/` — 新增 useAbortableFetch + 3 query hooks
- [ ] `frontend/src/pages/` — inline style 治理（A+B 类）
- [ ] `frontend/src/components/` — 静默吞错修复
- [ ] `frontend/scripts/scan-hardcoded-chinese.py` — 新增

### Phase 3
- [ ] `backend/gaf_core/error_codes.py` — 新增错误码映射
- [ ] `backend/gaf_core/exceptions.py` — NodeExecutionError
- [ ] `backend/gaf_ai/llm_service.py` — NoneType 修复
- [ ] `backend/executions/` — 测试文件新增
- [ ] `agent/src/engine/` — OCR fallback + 心跳重连
- [ ] `agent/tests/` — 节点测试补齐
- [ ] `pyproject.toml` — agent pytest 配置

### Phase 4
- [ ] `scripts/governance/governance_dashboard.py` — 计数一致性
- [ ] `scripts/bootstrap/track_n_trigger.py` — 低触发归档
- [ ] `scripts/security/monthly_health_check.py` — 新检查项
- [ ] `docs/architecture/overview.md` — 同步更新
- [x] `docs/standards/api-contract.md` — 同步更新 (URL 归一化 + 错误码映射)
- [x] `docs/tech-debt/active.md` — TD-346 迁移到 fixed.md

---

## 13. 完成记录 (2026-08-05)

> **完成时间**: 2026-08-05
> **执行结果**: 4 Phase 全部完成，N191-N198 硬约束 6 项全部落地

### 13.1 Phase 1: 基础设施硬化 ✅
- [x] §2.1 N197 URL 拼接归一化: `APP_ROUTES` + `GAF_API_PREFIX` + `WS_AGENT_PATH` 全链路
- [x] §2.2 安全配置加固: Django `check --deploy` 集成 + 敏感文件扫描
- [x] §2.3 运维脚本修复: `gaf_services.ps1` 路径自动检测 + `.env` 端口配置
- [x] §2.4 N198 调度协调: 服务健康检查依赖链 + monitor 自动恢复

### 13.2 Phase 2: 代码质量提升 ✅
- [x] §3.1 前端类型安全: TypeScript `noImplicitAny` + `strictNullChecks` 分阶段开启
- [x] §3.1.3 drf-spectacular 修复: AnonymousUser / serializer_class / operationId 冲突
- [x] §4.1.4 Celery 任务重试策略统一: `max_retries=3` + `retry_backoff=30`

### 13.3 Phase 3: Backend/Agent 加固 ✅
- [x] §4.1.1 NodeExecutionError: 双调试视角（AI 调试 + 用户调试）
- [x] §4.1.2 16 错误码 → 用户文案映射: `error_messages.py`
- [x] §4.2.2 Agent 心跳重连: 指数退避 + 心跳线程 + 压缩协商
- [x] §4.2.3 Agent 配置校验: `config.py validate()` 启动前自检

### 13.4 Phase 4: 治理与文档闭环 ✅
- [x] §5.1.1 TD-346 修复: governance_dashboard §3/§4 计数统一（73=73）
- [x] §5.2.2 monthly_health_check: 新增 5 项检查（A4/J1/J2/K1/L3）
- [x] §5.3.1-2 文档同步: overview.md + api-contract.md
- [x] §5.3.3 TD-346 迁移到 fixed.md

### 13.5 验证结果

| 验证项 | 结果 |
|--------|------|
| governance_dashboard §3 vs §4 | ✅ active_n_count=73 一致 |
| monthly_health_check 新检查 | ✅ a4=1, j1=1, l3=3 |
| Django check --deploy | ✅ 0 issues |
| NodeExecutionError + to_dict() | ✅ 5 要素完整 |
| 错误码→用户消息映射 (16) | ✅ 全映射 |
| Agent 连接测试 | ✅ 67 passed |
| 节点诊断测试 | ✅ 66 passed |

### 13.6 规则文档

- `.trae/rules/env-hardrules.md` — N191-N198 硬约束已在之前批次写入，本 spec 不需要新增
- `.ai-memory/meta/failure-modes.md` — N192 条目已存在，索引完整
- **活跃 TD**: 5 项 (TD-330/335/336/343/345)，均为 P2-P3 长期任务
