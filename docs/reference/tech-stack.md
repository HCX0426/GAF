---
maintainer: manual
source: backend/requirements/base.txt, frontend/package.json, agent/requirements.txt, environment.yml, pyproject.toml, .pre-commit-config.yaml
load_when: [L2 硬加载 (每次对话), 新功能, refactor]
priority: high
symptom:
- kb:tech-stack
- 技术栈
- stack-versions
- version-mismatch
- 开发环境
- pre-commit
- pytest
- conda
solution: 4 栈 (Python/Django/React/ADB) 版本速查 + 依赖清单 + Platform 栈 + 开发环境速查 (pre-commit/pytest/gaf_init); 版本兼容问题见 version-compat.md (v9.2 归一化)
related_files:
- backend/requirements/base.txt
- backend/requirements/dev.txt
- backend/requirements/prod.txt
- frontend/package.json
- agent/requirements.txt
- environment.yml
- pyproject.toml
- .pre-commit-config.yaml
- scripts/gaf_init.sh
- scripts/hooks/gaf_governance_batch.py
- docs/reference/version-compat.md
created_by: AI
generated: 2026-06-15
auto_updated: 2026-06-16
last_manual_edit: 2026-08-24
---

# GAF Tech Stack (v9.5 完整版 — L2 硬加载)

> **🆕 v9.5 (2026-07-21, spec-65)** — 从 L3 按需加载升级为 L2 硬加载 (每次对话 AI 必读)
> 用户反馈 "ai 每次都要找技术环境" → 升级 L2 + 补"开发环境速查"段 (§9-§12)
> AI 任务开工 L2 硬加载 → 答 stack versions + 开发环境 + 已知冲突

## 0. 4 栈结构总览

| 栈 | 语言/运行时 | 框架/库 | 关键版本 | 配置文件 |
|----|-----------|--------|----------|----------|
| **Backend** | Python 3.11 | Django 5.2 + DRF 3.15 + Channels 4.1 | 见下 | `backend/requirements/base.txt` |
| **Frontend** | TypeScript 6.0 | React 19.2 + Vite 8.0 + Ant Design 6.4 | 见下 | `frontend/package.json` |
| **Agent** | Python 3.11 | 自研 (Pipeline Engine + Device Abstraction) | 见下 | `agent/requirements.txt` |
| **Platform** | ADB / Win32 API / Cocoa / X11 | adbutils / pywin32 / comtypes / Xlib | 见下 | `agent/src/platforms/windows/` (agent 侧 Win) + `backend/device_bridge/platforms/{windows,macos,linux}/` (backend 侧抽象, P-028 ✅) + `agent/src/devices/adb/` (Android) |

**公共约束**:
- Python 版本必须 3.11+ (跨 backend + agent)
- Node 版本必须 20+ (vite 8 要求)
- conda 环境名固定为 `gaf` (Windows + Linux 同名)

## 1. Backend 栈 (Django 5.2 + DRF 3.15)

### 1.1 关键依赖 (`backend/requirements/base.txt`)

| 包 | 版本范围 | 用途 |
|----|---------|------|
| `django` | `>=5.2,<5.3` | Web 框架 |
| `djangorestframework` | `>=3.15,<4.0` | REST API |
| `djangorestframework-simplejwt` | `>=5.3,<6.0` | JWT 鉴权 |
| `django-cors-headers` | `>=4.4,<5.0` | CORS |
| `django-filter` | `>=24.0,<25.0` | DRF 过滤 |
| `django-celery-beat` | `>=2.6,<3.0` | 周期任务 |
| `channels` | `>=4.1,<5.0` | WebSocket |
| `channels-redis` | `>=4.2,<5.0` | Channels layer |
| `daphne` | `>=4.1,<5.0` | ASGI server |
| `celery` | `>=5.4,<6.0` | 异步任务 |
| `redis` | `>=5.0,<6.0` | 缓存 + 队列 |
| `python-dotenv` | `>=1.0,<2.0` | .env 加载 |
| `Pillow` | `>=10.4,<11.0` | 图像处理 |
| `drf-spectacular` | `>=0.27,<1.0` | OpenAPI/Swagger |
| `cryptography` | `>=43.0,<44.0` | 加密 |
| `rapidocr-onnxruntime` | `>=1.3` | OCR (默认) |
| `paddleocr` | `>=2.9` | OCR (高精度备选) |
| `opencv-python-headless` | `>=4.10` | 图像处理 (no GUI) |
| `chromadb` | `>=0.4.0` | 向量数据库 (RAG) |
| `pyotp` | `>=2.9,<3.0` | OTP (2FA) |
| `requests` | `>=2.31,<3.0` | HTTP client |

### 1.2 dev.txt / prod.txt 差异

| 文件 | 额外依赖 | 用途 |
|------|---------|------|
| `dev.txt` | `pytest` `pytest-django` `pytest-cov` `django-debug-toolbar` `ipython` | 开发 |
| `prod.txt` | `gunicorn` `whitenoise` `sentry-sdk` | 生产 (SQLite+WAL, 无需 PG) |

### 1.3 Django 5.2 关键变化

- **N86**: `DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'` — 必设
- **N91**: `MIDDLEWARE` 中 `tasks.trace_middleware.TracingMiddleware` 注入 trace_id
- **DRF 3.15**: `DEFAULT_THROTTLE_CLASSES` 支持 scope-based
- **Channels 4**: `AsyncWebsocketConsumer` 替代旧 `JsonWebsocketConsumer`

## 2. Frontend 栈 (React 19.2 + Vite 8.0 + Antd 6.4)

### 2.1 关键依赖 (`frontend/package.json` dependencies)

| 包 | 版本 | 用途 |
|----|------|------|
| `react` | `^19.2.6` | UI 框架 |
| `react-dom` | `^19.2.6` | DOM renderer |
| `react-router-dom` | `^7.15.1` | 路由 |
| `antd` | `^6.4.2` | UI 组件库 |
| `@ant-design/icons` | `^6.2.3` | 图标 |
| `axios` | `^1.16.1` | HTTP client |
| `@tanstack/react-query` | `^5.100.10` | 数据获取 (替代 SWR) |
| `zustand` | `^5.0.13` | 状态管理 |
| `@xyflow/react` | `^12.10.2` | Pipeline 编辑器 |
| `@monaco-editor/react` | `^4.7.0` | 代码编辑器 |
| `react-intl` | `^10.1.7` | i18n |
| `dayjs` | `^1.11.20` | 日期 |
| `recharts` | `^3.8.1` | 图表 |
| `monaco-editor` | `^0.55.1` | 编辑器核心 |
| `@fullcalendar/*` | `^6.1.20` | 日历 |
| `react-resizable-panels` | `^4.11.1` | 布局 |
| `zxcvbn` | `^4.4.2` | 密码强度 |

### 2.2 devDependencies

| 包 | 版本 | 用途 |
|----|------|------|
| `typescript` | `~6.0.2` | 类型系统 |
| `vite` | `^8.0.12` | 构建工具 |
| `vitest` | `^3.1.0` | 测试 |
| `@testing-library/react` | `^16.3.0` | 组件测试 |
| `eslint` | `^10.3.0` | 代码检查 |
| `typescript-eslint` | `^8.59.2` | TS lint |

### 2.3 关键 scripts

```json
{
  "dev": "vite",                  // 开发服务器
  "build": "tsc -b && vite build",// 生产构建
  "lint": "eslint .",
  "test": "vitest run",           // 一次性测试
  "test:watch": "vitest",         // 监视模式
  "test:coverage": "vitest run --coverage"
}
```

### 2.4 Vite 8 关键变化

- **N86**: 端口默认 5173,可通过 `vite.config.ts` 改
- **N91**: HMR 在 `frontend/src/api/*.ts` 修改不触发,需重启 dev server
- **Antd 6**: 主题 token API 变更 (从 v5 升级必看)

## 3. Agent 栈 (Python 3.11 自研)

### 3.1 关键依赖 (`agent/requirements.txt`)

| 包 | 版本范围 | 用途 |
|----|---------|------|
| `websockets` | `>=12.0` | WebSocket 客户端 (与 backend 通信) |
| `opencv-python` | `>=4.8.0` | 图像处理 (与 backend headless 共存需隔离) |
| `numpy` | `>=1.24.0` | 数组 |
| `adbutils` | `>=1.2.0` | ADB 高级封装 |
| `Pillow` | `>=10.0.0` | 图像 |
| `mss` | `>=9.0.0` | 跨平台截图 |
| `scrcpy` | `>=2.0.0` | Android 屏幕投屏 |
| `comtypes` | `>=1.2.0` | Windows COM (WGC) |
| `cryptography` | `>=41.0` | 加密 |
| `pywin32` | `>=305` | **Windows only** (Win32 API) |
| `pynput` | `>=1.7.6` | 全局键盘/鼠标事件监听 (C2 录制功能) |
| `rapidocr-onnxruntime` | `>=1.3,<2.0` | OCR 引擎 (TD-337, pipeline OCR 节点默认引擎, 与 backend/base.txt 对齐) |
| `msgpack` | `>=1.0.0` | WS 大帧压缩 (spec-42/TD-287) |

### 3.2 自研模块 (无外部依赖)

| 模块 | 路径 | 职责 |
|------|------|------|
| Pipeline Engine | `agent/src/engine/` | 节点注册 + DAG 执行 |
| Device Abstraction | `agent/src/devices/` | 跨平台统一接口 |
| Recognition | `agent/src/recognition/` | OCR + template + feature |
| Monitor | `agent/src/monitor/` | CPU/内存/截图 |
| Client | `agent/src/client/` | WebSocket 客户端 |

## 4. Platform 栈 (跨平台抽象)

> **v9.4 (2026-07-19, spec-39 Phase 8)** — 同步 TD-281 路径漂移修复: macOS/Linux 实际在 `backend/device_bridge/platforms/` (非 `agent/src/devices/`)

| 平台 | 截图 | 输入 | 实现位置 (实际代码) |
|------|------|------|------|
| **Windows** | WGC (Windows Graphics Capture) / BitBlt / PrintWindow / DXGI / LDOpenGL | Win32 SendInput / PostMessage / RegisterHotKey / minitouch | `agent/src/platforms/windows/` (agent 侧, 完整) + `backend/device_bridge/platforms/windows/` (backend 抽象) |
| **macOS** | CGWindowListCreateImage (Quartz) + screencapture CLI | CGEventPost (Quartz Event) | `backend/device_bridge/platforms/macos/` (P-028 ✅, backend 侧; agent 侧暂无 macOS 实现) |
| **Linux** | XGetImage + xdg_portal (grim/gnome-screenshot); XShmGetImage 回退到 XGetImage | XTest (python-xlib) | `backend/device_bridge/platforms/linux/` (P-028 ✅, backend 侧; agent 侧暂无 Linux 实现) |
| **Android 模拟器** | ADB screencap | ADB input | `agent/src/devices/adb/` (agent 侧) |
| **Android 真机** | scrcpy | ADB input | `agent/src/devices/adb/` (agent 侧) |
| **iOS 模拟器** | idb | idb | (待 M2) |
| **Web 浏览器** | Playwright | Playwright | (待 M2) |

**Platform Capabilities API**:
- `backend/agents/urls.py: devices/platform-capabilities/`
- 返回当前 Agent 支持的平台 + 能力清单 (截图/输入/OCR)
- 跨平台兼容性检查 `devices/check-compatibility/`

## 5. 数据库与中间件

| 组件 | 版本 | 用途 | 配置文件 |
|------|------|------|----------|
| SQLite (WAL) | `>=3.8` | 主库 (dev/prod 统一) | `backend/config/settings/base.py` |
| Redis | `>=6.0` | 缓存 + Celery + Channels | `CELERY_BROKER_URL` |
| MinIO / S3 | (latest) | 对象存储 | `AWS_*` env vars |
| Nginx | `>=1.20` | 反向代理 | `frontend/nginx.conf` |

## 6. 版本兼容问题 (v9.2 归一化到 version-compat.md)

> **v9.2 归一化 (2026-07-15)**: 本节原含"AI 用错版本 5 种情况" + "速查决策树" + "已知实现问题" + "维护期修复", 与 `version-compat.md` §5/§6/§8/§9 重复。已删除, 单一权威源在 `version-compat.md`。
> **加载时机**: 涉及版本/依赖决策时 L3 按需加载 `version-compat.md` (N137/N144 等版本坑)。

## 7. conda 环境 (Windows 11 + Linux 通用)

```yaml
# environment.yml
name: gaf
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - nodejs=20
  # 2026-08-03 spec: dev/prod 统一 SQLite + WAL, 不再需要 PG 服务
  # 保留 redis (Celery broker + Channel Layer + cache)
  - redis=6
```

**激活**:
```bash
conda activate gaf
# 或
conda run -n gaf <command>
```

## 8. 维护期修复 (M1.A 待办)

- [ ] 自动从 requirements 文件重生成 (但本文件已改 manual,不再自动)
- [ ] 升级 Django 6 时重写本表 (M2.H)
- [ ] Antd 7 升级测试 (M2.H)

---

## 9. 开发环境速查 (v9.5 新增 — AI 每次对话必读)

> **来源**: spec-65 (2026-07-21) 用户反馈 "现在没地方说明 gaf 用的技术环境, 为啥 ai 每次都要找"
> **目的**: AI 任务开工前不用 Glob/Read 探索 pyproject.toml / package.json / .pre-commit-config.yaml, 直接读本段即可

### 9.1 Python 环境 (conda gaf)

```bash
# 激活环境
conda activate gaf
# 或显式调用 (跨平台)
D:\code\environment\conda\envs\gaf\python.exe -m <command>

# Python 版本约束: 3.11+ (backend + agent 共用)
# Node 版本约束: ^20.19.0 || >=22.12.0 (vite 8 要求, engines 字段在 frontend/package.json)
```

### 9.2 pytest 配置 + 命令

**配置位置**: `pyproject.toml [tool.pytest.ini_options]`

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings.test"
python_files = ["tests.py", "test_*.py", "*_tests.py"]
pythonpath = ["backend"]  # N150 fix: 让 Django settings 可导入
cache_dir = ".cache/pytest"
```

**关键命令** (按 N177 分级测试策略):

| 改动规模 | 命令 | 基线 |
|---------|------|------|
| 小修改 (1-3 文件, 单 app) | `pytest backend/<app>/` | < 60s |
| 中修改 (4-10 文件, 跨 app) | `pytest backend/<app1>/ backend/<app2>/ backend/tests/test_integration.py` | < 120s |
| 大修改 (>10 文件 / DB 迁移 / API 契约) | `pytest backend/ -n 8` | < 600s |
| 循环模式每 2 spec 全套回归 | `pytest backend/ -n 8` | < 600s |

**pytest-xdist 并行化** (spec-65 / TD-308-A, 2026-07-21):
- dep: `pytest-xdist>=3.5,<4.0` (在 `pyproject.toml [project.optional-dependencies] dev`)
- `-n 8` 固定 8 workers 并行 (spec-70 TD-314: `-n auto` 16 workers 触发 screenshot tests MemoryError, 改 `-n 8` 内存可控, 4-4.5x 加速)
- 大修改 + 循环模式必加 `-n 8`, 小/中修改不必加 (启动开销 1-2s)

**测试文件统计**: backend 108 + agent 65 + frontend 11 = 184 个 test_*.py

### 9.3 前端测试 + lint

```bash
cd frontend
npm run test          # vitest run (一次性)
npm run test:watch    # vitest (监视模式)
npm run test:coverage # vitest + coverage
npm run test:e2e      # playwright test --config=e2e/playwright.config.ts
npm run lint          # eslint .
npx tsc -b --noEmit   # 类型检查 (修改 .tsx 后必跑)
```

### 9.4 pre-commit hook 清单

**配置**: `.pre-commit-config.yaml`
**hook 类型分层** (M2.D + TD-377 折叠):
- `pre-commit` stage: 2 GAF hooks (gaf-governance-batch + gaf-git-status-check)
- `manual` stage: 5 hooks (eslint/prettier/ruff/mypy + gaf-audit-scripts) — CI 跑, 本地不阻塞
- `pre-push` stage: 2 hooks (gaf-skip-rate 30% bypass 红线 + gaf-governance-batch-push 6 重型校验兜底)
- `post-commit` stage: 2 hooks (gaf-post-commit-batch 含 M2 claimed-rules + gaf-lesson-diff-trigger M3)

**gaf-governance-batch** (TD-377 折叠为单进程, 按需 import): pre-commit 热路径跑 **17 checks** (旧 §9.4 "10 checks" 清单已随 TD-377 过时; 6 个重型纯校验模块移出到 pre-push 兜底). Batch 内已折叠 **M1 code-rules** (check_code_rules, R001-R005) 与 **M2 复盘闭环** (check_unclosed_review). 全量 24 checks 在 pre-push 阶段执行.

**post-commit stage** (advisory, 不阻塞):
- `gaf-post-commit-batch` 内含 M2 `check_claimed_rules` (声称-激活率回执) + reflection/P4 checklist
- `gaf-lesson-diff-trigger` (M3 diff→lesson 触发式检索)

**commit 时间**: ~2-5s (TD-377 后 17-check 热路径; ~22s 描述已过时)

### 9.5 gaf_init.sh 工作流入口

**位置**: `scripts/gaf_init.sh`
**触发**: AI 任务开工前 (硬约束入口)
**两种模式**:
- `bash scripts/gaf_init.sh` (默认 --fast): L1 硬加载 + session active, < 1s
- `bash scripts/gaf_init.sh --full`: + pre-commit install + sync_ai_memory + sync_skills + docs-index + doc_health_check, ~10s

**fast mode 步骤** (v9.0):
1. UTF-8 强制 (N92 CJK garble fix) — `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`
   (Python UTF-8 Mode, 等价 `-X utf8`; 覆盖 stdin/stdout/stderr + file IO,
   对齐 TEST_SFCAPI_LANGUAGE 三防线, 2026-08-15)
2. conda gaf 环境校验
3. dep 校验 (yaml/watchdog/click)
4. **L1 硬加载 failure-modes.md** (grep N## entries, ≥ 5 才通过, exit 1 fallback)
5. **L2 量化校验 ai-operating-handbook.md** (红线模式 ≥ 20 行, 警告非阻塞)
6. **P5 治本机制**: failure-modes.md 正文 ≤ `p5_max_lines` (frontmatter 字段, 默认 170)
7. evidence 目录创建 (3-step templates)
8. session active 创建 (24h TTL, 跨平台 binding)

**full mode 额外步骤** (在 fast 之前跑):
- pre-commit 自动安装 + hook 自动安装
- sync_ai_memory 自动跑
- sync_skills --check (5 skills + 1 rule 分发校验)
- sync_session_context 自动生成 .ai-memory/ref/session-context.md
- build_memory_index (C1 hybrid search, chromadb)
- sync_docs_index --check (90 天 stale 警告)
- doc_health_check (7 维度扫描, < 2s)
- L2 file existence check

### 9.6 AI 任务工作流 (gaf-orchestrator 决策树)

```
1. bash scripts/gaf_init.sh (硬约束入口)
2. gaf-orchestrator 决策树 step_1: 判定 task_type (new_feature/bug_fix/documentation/refactor/unknown)
3. L2 硬加载 (v9.5): ai-operating-handbook.md + tech-stack.md (本文件)
4. 路由到对应 skill (gaf-task-execution / gaf-reflect-and-evolve / gaf-knowledge-base)
5. L3 按需加载: sync_ai_memory.py --query <symptom> + version-compat.md + docs-index.md
6. 执行: 写代码 + 3 步 evidence + lessons (如新坑)
7. commit: 按 §3.4 spec 粒度自决 commit (普通 git commit, 不用 gaf-commit.sh wrapper)
8. 反思: §3.2 反思清单 (小/中/大分级)
```

### 9.7 关键路径速查 (AI 不用 Glob 找)

| 用途 | 路径 |
|------|------|
| AI 入口 (决策树) | `.skills/skills/gaf-orchestrator/SKILL.md` |
| AI 操作手册 (L2 硬加载) | `.ai-memory/meta/ai-operating-handbook.md` |
| 失败模式索引 (L1 硬加载) | `.ai-memory/meta/failure-modes.md` |
| 项目规则 | `.skills/rules/project_rules.md` |
| Y/N 矩阵索引 | `.ai-memory/meta/yn-matrices.md` |
| 项目状态 | `docs/project-status.md` |
| 活跃 TD | `docs/archive/active-tech-debt.md` |
| 已修 TD | `docs/archive/fixed-tech-debt.md` |
| spec 文件 | `docs/specs/archived/` (全部已归档) |
| pytest 配置 | `pyproject.toml [tool.pytest.ini_options]` |
| 前端依赖 | `frontend/package.json` |
| pre-commit | `.pre-commit-config.yaml` |
| Django settings | `backend/config/settings/dev.py` |
| Django urls | `backend/config/urls.py` + 各 app `urls.py` |
| 后端 conftest | `backend/conftest.py` |

---

**manual 模式标记** (与 v8.4 之前 auto 模式对比):
- ❌ `<!-- end of auto-generated section -->` 标记缺失
- ✅ AI 修改后必查 front matter `last_manual_edit` 字段
- ✅ 加新依赖时,本表手动同步
- ✅ 不再被 sync_ai_memory 自动覆盖为 stub (M1.A.1 修复)
- ✅ **v9.5 升级 L2 硬加载**: AI 每次对话必读本文件 (不用 Glob 探索 pyproject.toml 等)
