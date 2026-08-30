---
maintainer: derived-manual
source: backend/requirements/*.txt, frontend/package.json, worker/requirements.txt
load_when: [版本升级, 依赖变更, TS 严格选项, Antd 升级, Django 升级, 跨文件版本同步, 多文件版本漂移, spec-code 版本漂移, L3 按需]
priority: medium
symptom:
- kb:version-compat
- kb:version-sync
- 版本兼容
- version-mismatch
- deprecation
- version-drift
- multi-file-version
- spec-code-version-mismatch
solution: 版本兼容矩阵 + 升级风险 + N137/N144 版本坑 + 6 类版本同步规则 + 漂移修复流程 (spec-38 Phase 6 合并 version-sync.md; v9.2 降 L3 按需)
related_files:
- docs/reference/tech-stack.md
- .ai-memory/summaries/architecture-mistakes.md
- .ai-memory/meta/spec-evolution.md
- .ai-memory/meta/failure-modes.md
- backend/requirements/base.txt
- backend/requirements/dev.txt
- backend/requirements/prod.txt
- frontend/package.json
- worker/requirements.txt
created_by: AI
generated: 2026-06-15
auto_updated: 2026-07-19
last_manual_edit: 2026-07-19
---

# GAF Version Compatibility (v9.2 L3 按需版)

> **v9.4 (2026-07-19, spec-38 Phase 6)** — 合并 `meta/version-sync.md` 进本文件 (§10-§14), 原 version-sync.md 已删除; 单一权威源消除双文件冗余
> **v9.2 (2026-07-15)** — 降为 L3 按需加载 (原 L2 硬加载); tech-stack.md §6/§8/§9/§10 已归一化到本文件 (单一权威源)
> **v8.4 (M1.A.1)** — 修复 auto 模式被 sync_ai_memory 误覆盖为 stub, 改为 derived-manual
> AI 涉及版本/依赖决策或跨文件版本同步时 L3 按需加载 → 答版本不兼容 + 已知实现问题 + N137/N144 版本坑 + 6 类版本同步规则

## 0. 当前版本快照 (2026-07-19, spec-39 Phase 8 更新)

| 组件 | 当前版本 | 下一升级 | 不兼容风险 |
|------|----------|----------|-----------|
| Python | 3.11 | 3.12 | 极低 |
| Django | 5.2 | 6.0 | 中 (REST framework 必升) |
| DRF | 3.15 | 4.0 | 中 (SimpleJWT 5.3 升 6) |
| Channels | 4.1 | 5.0 | 中 (inmemory 变 redis-first) |
| React | 19.2 | 20.0 | 低 (Antd 6 兼容) |
| Vite | 8.0 | 9.0 | 低 (Node 20+ 即可) |
| Antd | 6.4 | 7.0 | 高 (token API 变) |
| TypeScript | 6.0 | 7.0 | 中 (类型系统变) |
| Node | 20 | 22 | 低 |

## 1. Python 包版本不兼容

### 1.1 Django 5.x → 6.0

| 改动 | 影响范围 | 修复 |
|------|----------|------|
| `DEFAULT_AUTO_FIELD` 默认改 `BigAutoField` | 所有 models | 已在 `settings/base.py` 显式设 |
| `USE_THOUSAND_SEPARATOR` 默认 True | 模板数字显示 | 检查 admin 模板 |
| `STORAGES` 替代 `DEFAULT_FILE_STORAGE` | 媒体文件 | 改 `settings/base.py` STORAGES dict |
| async ORM 稳定 | views/tasks | 用 `async def` + `database_sync_to_async` |

**N86**: 升级前必读 https://docs.djangoproject.com/en/5.2/releases/6.0/

### 1.2 DRF 3.15 → 4.0

| 改动 | 影响范围 | 修复 |
|------|----------|------|
| `Serializer.Meta` 强类型 | 所有 serializers | 改用 `class Meta: model = X; fields = "__all__"` 显式 |
| `APIView` 异步支持 | views | 改 `async def get` |
| `OpenAPI` schema 必填 | 视图集 | drf-spectacular 0.28+ |

### 1.3 Channels 4.1 → 5.0

| 改动 | 影响范围 | 修复 |
|------|----------|------|
| InMemoryChannelLayer 弃用 | dev settings | 必用 channels-redis |
| `AsyncWebsocketConsumer` 默认 reconnect | consumers | 已有 reconnect logic |

### 1.4 Python 3.11 → 3.12

| 改动 | 影响范围 | 修复 |
|------|----------|------|
| `typing` 重命名 (PEP 695) | type hints | 改 `class X[T]` 而非 `Generic[T]` |
| `asyncio` 性能提升 | 所有 async | 无需改 |
| `f-string` 限制放宽 | 全部 | 无需改 |

## 2. JavaScript/TypeScript 不兼容

### 2.1 React 19.2 → 20.0 (预估)

| 改动 | 风险 |
|------|------|
| Server Components 强制 | 中 (需要 SSR) |
| Suspense 重构 | 低 |
| `useEffect` cleanup 时机变化 | 中 |

### 2.2 Vite 8.0 → 9.0

| 改动 | 风险 |
|------|------|
| ESM 强制 (CJS 弃用) | 中 (老库不兼容) |
| `import.meta.env` 类型强化 | 低 |
| `vite.config.ts` 必填 type | 低 |

### 2.3 Antd 6.4 → 7.0 (预估)

| 改动 | 风险 |
|------|------|
| Token API 重构 (`theme.token` → `theme.config`) | **高** — 全局影响 |
| 移除 `legacy` 组件 | 中 |
| React 19 strict mode 强制 | 低 |

**N91 family**: Antd 升级必跑 `frontend/src/__tests__/` 全部视觉回归

### 2.4 TypeScript 6.0 → 7.0

| 改动 | 风险 |
|------|------|
| `infer` 关键字语义化 | 中 |
| `--noUncheckedIndexedAccess` 默认开 | 中 |
| decorator 标准化 | 中 |

### 2.4.1 TypeScript 6.0 迁移已知问题 (N137, 2026-06-30)

> 当前 frontend 已在 TS 6.0.3。以下是启用 TS 6.0 新严格选项时踩到的坑。

| 选项/改动 | 症状 | 修复 |
|-----------|------|------|
| `erasableSyntaxOnly` (TS 5.8+) | `enum` 报 "不允许使用此语法"; `namespace` 带运行时代码同报 | `enum` → `const` object + `as const` + union type (见 N137) |
| `baseUrl` 弃用 (TS 6.0) | 需 `ignoreDeprecations: "6.0"` 转义; IDE 内置 TS 5.x 报值无效 | 删 `baseUrl`, `paths` 改相对 `"./src/*"`, 删 `ignoreDeprecations` (治根因不转义) |
| IDE 内置 TS 滞后 | IDE 报 `tsc` 不报的配置错误 | 可选: `.vscode/settings.json` 加 `"typescript.tsdk": "frontend/node_modules/typescript/lib"` |

**N137 硬约束**:
- ✅ 启用 `erasableSyntaxOnly` 前, 审计所有 `enum` 并转为 `const` object + union type
- ✅ TS 6.0+ `paths` 用相对模式 (`"./src/*"`), 不加 `baseUrl`
- ✅ 弃用选项优先**删除根因**, 不靠 `ignoreDeprecations` 转义
- **Lesson**: `lessons/version-compat_2026-06-30-n137-ts60-erasable-syntax-and-baseurl-deprecation.md`

## 3. 跨语言不兼容

### 3.1 Backend (Python 3.11) ↔ Agent (Python 3.11)

| 项 | 风险 |
|----|------|
| Protocol 协议 (WebSocket frame) | **必须**保持 `protocol/constants.py: MESSAGE_FRAME_SCHEMA` 与 Agent 端 `worker/src/client/handler.py` 一致 |
| TaskState 枚举 | **必须**保持 `protocol/schemas.py: TaskState` 与 Agent 端状态机一致 |
| error_code 字符串 | 4 层分发必查 (`failure-modes.md` + lessons) |

### 3.2 Backend (Django 5.2) ↔ Frontend (React 19.2)

| 项 | 风险 |
|----|------|
| API 路径 `/api/v2/` | **单点真相** 在 `backend/config/app_info.py: API_PREFIX` |
| CORS | `settings/base.py: CORS_ALLOWED_ORIGINS` |
| JWT token 格式 | `accounts/crypto.py` 必查 |

### 3.3 Frontend (Vite 8) ↔ Desktop (Electron) (待 M2)

| 项 | 风险 |
|----|------|
| IPC 通道 | `desktop/src/main/ipc.ts` |
| File 协议 | Electron version 匹配 |

## 4. 数据库迁移不兼容

| 改动 | 风险 |
|------|------|
| SQLite 3.8 → 3.45 | 低 (WAL 模式兼容) |
| `BigAutoField` 加列 | 中 (大表慢) |
| Drop column 大表 | **高** — 分批迁移 |

**N86**: 所有 migration 必在 staging 跑通再 prod

## 5. AI 用错版本 5 种情况 (N86 / N91 / N58 family)

| # | 错误模式 | 触发 | 修复 |
|---|----------|------|------|
| 1 | `python -c "..."` 多行 (PowerShell 5) | `NotImplementedError` | 用临时 .py 文件 |
| 2 | `conda run -n gaf python -c "..."` 多行 | 同上 | 用临时 .py 文件 |
| 3 | PowerShell `cmd1 && cmd2` | 语法错 | 用 `cmd1; cmd2` |
| 4 | `frontend` HMR 不刷新 `.env` | API URL 不变 | `npm run dev` 重启 |
| 5 | `agent` 与 `backend` 同端口 (8000) | 启动冲突 | Agent 用随机端口 |

## 6. 已知实现问题清单 (跨版本)

| # | 编号 | 描述 | 触发场景 | 修复 |
|---|------|------|----------|------|
| 1 | **N47** | `gaf-commit.sh` `--no-verify` 透传 bug | 用 `gaf-commit.sh --no-verify` 期望跳过 hook | 改用 `git commit --no-verify` |
| 2 | **N50** | evidence 5 步应付化 | 提交时 evidence 走过场 | 已简化为 3 步 |
| 3 | **N52** | skip rate 10% 误伤开发期 | 早期 commit 多 | 已改滚动 30 + 30% |
| 4 | **N58** | Windows NTFS inode 不支持 | session binding 失败 | 用 `(size, mtime, ctime)` 替代 |
| 5 | **N82** | 同事签字 + 每日限额冲突 AI 全权 | bypass 流程不工作 | 已改为 `GAF_BYPASS_REASON` 自签 |
| 6 | **N86** | DRF 3.15 + SimpleJWT 5.3 token 滚动 | token 过期 | 已在 `accounts/views.py` 加刷新 |
| 7 | **N91** | Channels 4 vs 3 异步 API | consumer async 报错 | 已在 `protocol/consumers.py` 用新 API |
| 8 | **N92** | PowerShell 5 中文乱码 | stdout 输出中文 | `_encoding_safe.py` + `PYTHONIOENCODING=utf-8` |
| 9 | **N93** | AI 把命令甩给用户 | 需用户手动跑命令 | 全面自包含 (gaf_init.sh) |
| 10 | **N95** | AI 学习只分发到 1-2 层 | 反思不闭环 | 4 层分发硬约束 |
| 11 | **N96** | AI 跳过 L2 软指导 | 不读 .ai-memory/ | 4 文件硬加载 |
| 12 | **N100** | AI 误覆盖 auto 文件为 stub | 长期 sync 后文件变 39 行 | N105 修复: hook 阶段 read-only |
| 13 | **N101** | AI 状态不诚实 (跳过不标) | commit 信息模糊 | audit log 强制 |
| 14 | **N103** | 旧 `skills/` YAML 重复维护 | 双源不一致 | 已删 (M0.N) |
| 15 | **N104** | AI 不知 docs 有什么 | 找不到设计文档 | docs/standards/ + docs-index |
| 16 | **N105** | gaf-commit 透传 + sync 误改 docs-index | commit 后文档被回滚 | 已修 (本轮) |

## 7. 版本升级决策树

```
要升级 X? (load version-compat.md)
├─ X 必升? (安全 CVE) → 跑迁移测试 + 备份
├─ X 可选升? → 评估收益 vs 风险
│  ├─ 收益 > 风险 → 升 + 改 lessons 记录
│  └─ 收益 < 风险 → 延后
├─ 升 X 影响其他? → 查本表第 1-4 节
└─ 升 X 触发 N##? → 写新 lessons/ + 4 层分发
```

## 8. AI 速查决策树

```
bug_fix? (load version-compat.md)
├─ ImportError / AttributeError → 版本不匹配 → 查本表第 1-2 节
├─ Channel/WebSocket 异常 → 查 §1.3
├─ React 渲染异常 → 查 §2.x
└─ 跨语言协议不匹配 → 查 §3.x

refactor? (load version-compat.md)
├─ 升级 Python 包 → 必查对应小节
├─ 升级 Node 包 → 必查 §2.x
├─ 跨语言改动 → 必查 §3.x + 必跑 e2e
└─ 数据库迁移 → 必查 §4
```

## 9. 维护期修复 (M1.A 待办)

- [ ] 自动化版本检测脚本 (CI: `pip list --outdated`)
- [ ] Antd 7 升级准备 (M2.H)
- [ ] Django 6 升级预研 (M2.H)

---

**derived-manual 标记** (与 v8.4 之前 auto 模式对比):
- ❌ `<!-- end of auto-generated section -->` 标记缺失
- ✅ AI 修改后必查 `last_manual_edit` 字段
- ✅ 升级前 AI 必读本表 + 4 层分发 (N95)
- ✅ 不再被 sync_ai_memory 自动覆盖 (M1.A.1 修复)

---

## 10. 跨文件版本同步规则 (spec-38 Phase 6 合并自 meta/version-sync.md)

> **用途**: 改一处版本号时知道要同步改哪些文件
> **原则**: 版本号 = single source of truth, 改时必须连带改所有引用
> **风险**: 漂移会让 sync_ai_memory 误判, hook 误报, 用户混淆

### 10.1 6 类版本同步规则

#### 10.1.1 [顶层版本] — 1 个文件, 全局权威

**定义**: `GAF/.ai-memory/lessons/` 或 `docs/` 顶层的版本声明
**示例**: spec 顶部 `> **版本**: 5.3`, README 顶部
**同步范围**: 仅自身
**改后必做**: 跑 `python scripts/bootstrap/sync_docs_index.py` 重新生成索引

#### 10.1.2 [双根版本] — 2 份必须哈希一致

**定义**: GAF 内部 + 工作区根的副本 (sync_skills.py 管)
**示例**: `GAF/.skills/rules/project_rules.md` ↔ `.skills/rules/project_rules.md`
**同步范围**: 2 份必须一致
**改后必做**: `python scripts/bootstrap/sync_skills.py` 同步
**检查**: `gaf-decision-tree-sync` hook 校验哈希

#### 10.1.3 [衍生版本] — 多个文件引用同一源

**定义**: 文档顶部 `> **版本**: 5.3` + 内嵌 `> Phase R23 完成` 状态
**示例**: pending-roadmap.md 顶部 + §5 Phase 表 + §二 待实现清单状态
**同步范围**: 3+ 处
**改后必做**: 手动同步所有引用, 跑 `python scripts/bootstrap/sync_ai_memory.py` 看 warning

#### 10.1.4 [约束版本] — Python/Node 库版本

**定义**: `requirements.txt` / `package.json` / `pyproject.toml`
**示例**: Django==4.2.7 / React==18.2.0
**同步范围**: requirements.txt + requirements-dev.txt + Dockerfile
**改后必做**: `pip-compile` 或 `npm install` 重新锁定
**检查**: CI 跑 `pip check` / `npm audit`

#### 10.1.5 [兼容版本] — 多版本共存

**定义**: 同时支持 v8.3 + v8.4
**示例**: API 端点 `/api/v1/...` + `/api/v2/...` 共存
**同步范围**: 路由表 + 文档 + 测试
**改后必做**: 加 deprecation warning, 更新迁移指南

#### 10.1.6 [标记版本] — 状态标记 (✅/🔧/❌)

**定义**: completed-features.md / pending-roadmap.md / bug-tracker.md 顶部状态
**示例**: `> **当前阶段**: Phase R28 ✅` / `> **状态**: ❌ 未实现`
**同步范围**: 跨 3+ 文档
**改后必做**: N101 修复: 状态必须诚实, 跑通 ≠ 可用

### 10.2 版本同步检查清单 (AI 必跑)

#### 10.2.1 改版本号前

- [ ] 我要改的是哪类版本? (顶层/双根/衍生/约束/兼容/标记)
- [ ] 同步范围有哪几个文件?
- [ ] 有没有跨工作区引用 (`.skills/` 父级目录)?
- [ ] 改完跑哪些 sync 工具?

#### 10.2.2 改版本号后

- [ ] 所有同步范围文件已改
- [ ] `python scripts/bootstrap/sync_skills.py` (双根类)
- [ ] `python scripts/bootstrap/sync_ai_memory.py` (衍生类)
- [ ] `python scripts/bootstrap/sync_docs_index.py` (顶层类)
- [ ] `pip check` / `npm audit` (约束类)
- [ ] `git log --oneline -1` 验证 commit (防 N82 错觉)

#### 10.2.3 跨文件一致性检查

```bash
# 1. 顶层版本号一致性
grep -r "版本.*[0-9]\+\.[0-9]\+" .ai-memory/ docs/

# 2. Phase R## 状态一致性
grep -r "Phase R[0-9]\+ ✅\|Phase R[0-9]\+ ❌" docs/archive/pending-roadmap.md

# 3. 双根副本哈希
python scripts/bootstrap/sync_skills.py --check
```

### 10.3 已记录漂移案例 (5 项)

| # | 漂移类型 | 现象 | 根因 | 修复 | 教训 |
|:-:|:--------|------|------|------|------|
| 1 | 路径 | `sync-state.json` 在仓库根 (N106) | inline 拼路径, 缺模块级常量 | 用 `SYNC_STATE = AI_MEMORY / "sync-state.json"` | N107 hook 防漂移 |
| 2 | 双根 | `project_rules.md` 哈希不一致 (v8.4) | gaf-sync 改了一边没改另一边 | `python scripts/bootstrap/sync_skills.py` | 改前必跑 sync |
| 3 | 衍生 | `pending-roadmap.md` Phase R23 ✅ vs completed-features.md 还没标 | 多文件手动改漏 | 写脚本自动同步 | N95 4 层分发 |
| 4 | 标记 | `✅可用` vs `🔧代码存在(不可用)` 混用 | 状态不诚实 (N101) | 浏览器验证后才标 ✅ | 必须实测 |
| 5 | 约束 | Django 4.2 → 5.0 升级, DRF 不兼容 | 没跑 `pip check` | 锁回 4.2.7, 等 DRF 升级 | 升级前必跑依赖检查 |

### 10.4 漂移修复流程 (AI 必读)

#### 10.4.1 发现漂移 (5 步)

1. **跑 sync 工具**: `sync_ai_memory` / `sync_skills` / `sync_docs_index`
2. **看 warning**: sync 工具会列出漂移文件
3. **读 git log**: `git log --oneline -- <file>` 看上次改谁
4. **对照 spec**: spec vs code 双向 (N95)
5. **决定主从**: 谁错? 一般以 spec 为准 (project_rules.md §4.2)

#### 10.4.2 修复漂移 (4 步)

1. **改错的一边**: 让错的对上对的
2. **跑 sync 工具**: 验证一致
3. **写 N## 教训**: 5 维根因 + 4 层分发
4. **加 hook 防漂移**: 缺机制就补 (N107 案例)

#### 10.4.3 反思检查

- [ ] 漂移根因是什么? (inline 拼?手动改漏?缺 hook?)
- [ ] 有没有同类漂移? (Grep 全仓库)
- [ ] 需不需要加 hook? (N107 已为路径漂移加 hook)
- [ ] 4 层分发了没? (N95)

### 10.5 版本号命名约定

| 类型 | 格式 | 示例 | 改时机 |
|------|------|------|--------|
| **spec** | `5.3` / `v8.4` | `> **版本**: 5.3` | Phase 完成 |
| **skill** | `v1.0` | `---\nversion: 1.0` | 重大重构 |
| **rule** | `v8.4` | `> **版本**: v8.4` | 改 §3+ 时 |
| **lesson** | 日期 | `2026-06-16-n108-...` | 写新教训时 |
| **commit** | `<type>(<scope>): <subject>` | `feat(ai-memory): ...` | 每次 commit |
| **Python lib** | `==X.Y.Z` | `Django==4.2.7` | 升级时 |
| **Node lib** | `^X.Y.Z` | `react@^18.2.0` | 升级时 |

### 10.6 禁止事项 (硬规则)

❌ **NEVER** 改版本号不跑 sync 工具 (违反 §10.2.2)
❌ **NEVER** 双根副本不一致提交 (gaf-decision-tree-sync hook 阻断)
❌ **NEVER** 状态标记不诚实 (N101 修复: 跑通 ≠ 可用, 必须浏览器验证)
❌ **NEVER** 跨文件漂移不写 N## 教训 (N95 4 层分发)
❌ **NEVER** 升 Python/Node 库不跑 `pip check` / `npm audit` (违反 §10.2.2)
❌ **NEVER** 改 spec 不更新本节 §10.3 漂移表 (违反 §10.4 反思)
