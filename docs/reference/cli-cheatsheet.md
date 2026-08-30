---
maintainer: derived-manual
source: scripts/*.sh, scripts/*.py, backend/manage.py, frontend/package.json
load_when: [调试, 开发]
priority: medium
symptom:
- kb:cli:cheatsheet
- 命令速查
- dev-commands
- gaf-script
solution: 12 GAF scripts + 8 backend manage + 7 frontend npm + 4 agent cli + 5 devops
related_files:
- scripts/gaf_init.sh
- scripts/gaf-commit.sh
- scripts/bootstrap/sync_ai_memory.py
- scripts/bootstrap/sync_docs_index.py
- scripts/bootstrap/sync_skills.py
- scripts/check_big_change.py
- scripts/lessons/promote_lessons.py
- backend/manage.py
- frontend/package.json
created_by: AI
generated: 2026-06-16
auto_updated: 2026-07-22
last_manual_edit: 2026-07-20
---

# GAF CLI Cheatsheet (v8.4)

> **🆕 v8.4 (M1.A.1)** — `derived-manual` 模式 (手写命令速查,自动重生成会破坏)
> 12 GAF scripts + 8 backend manage + 7 frontend npm + 4 agent CLI + 5 devops

## 0. 速查原则

- **路径**: 默认假设 cwd = workspace 根目录（即 `d:\code\GAF`），与 gaf_init.sh 一致
- **conda**: 所有 Python 命令在 `gaf` 环境下 (`conda run -n gaf python ...`)
- **Windows 兼容**: 见 §6
- **跨平台**: Linux/macOS/Windows 11 通用

## 1. GAF scripts (12 个) — 仓库根

### 1.1 入口与初始化

```bash
# gaf_init.sh: 硬约束入口 (M0.A)
# 跑: conda gaf + sync + session active + L1 硬加载 failure-modes
bash scripts/gaf_init.sh

# 验证 conda gaf 环境
bash scripts/gaf_init.sh --check-env
```

### 1.2 同步工具

```bash
# sync_ai_memory.py: 核心 KB 同步器 (M0.B)
# 扫 .ai-memory/ + 按 maintainer 模式处理 + 生成查询索引
python scripts/bootstrap/sync_ai_memory.py                       # 全量同步
python scripts/bootstrap/sync_ai_memory.py --query "popup"       # 模糊查询
python scripts/bootstrap/sync_ai_memory.py --root /path/to/repo  # 跨仓库
python scripts/bootstrap/sync_ai_memory.py --dry-run             # 只看不动
python scripts/bootstrap/sync_ai_memory.py --stats               # 模式分布
python scripts/bootstrap/sync_ai_memory.py --index               # 索引

# sync_docs_index.py: docs/ 文件 frontmatter 索引
python scripts/bootstrap/sync_docs_index.py
python scripts/bootstrap/sync_docs_index.py --check              # pre-commit 模式

# sync_skills.py: 5 skills + 1 rule 双根同步
python scripts/bootstrap/sync_skills.py
python scripts/bootstrap/sync_skills.py --check
```

### 1.3 校验工具

```bash
# check_session_active.py: 跨平台 session binding (M0.A)
python scripts/bootstrap/check_session_active.py --create
python scripts/bootstrap/check_session_active.py --check

# check_3step_evidence.py: 验证 3 步 evidence 完整 (M0.J)
python scripts/hooks/check_3step_evidence.py

# check_lessons_updated.py: lessons frontmatter 校验 (M0.B)
python scripts/hooks/check_lessons_updated.py

# check_spec_consistency.py: 跨 spec/tasks/checklist 一致性 (M0.B)
python scripts/hooks/check_spec_consistency.py

# check_git_status_after_hook.py: N105 MM 状态阻断 (M1.A)
python scripts/hooks/check_git_status_after_hook.py
python scripts/hooks/check_git_status_after_hook.py --auto-only
python scripts/hooks/check_git_status_after_hook.py --warn-only
```

### 1.4 提交与提升

```bash
# gaf-commit.sh: --no-verify 拦截 + audit log (M0.J)
bash scripts/gaf-commit.sh -m "fix: ..."
GAF_BYPASS_REASON="emergency fix" bash scripts/gaf-commit.sh --no-verify -m "..."

# promote_lessons.py: 高频 lessons 自动提议提升 (M0.M)
python scripts/lessons/promote_lessons.py --dry-run
python scripts/lessons/promote_lessons.py --apply
```

### 1.5 辅助

```bash
# check_env.py: 验证 Python 环境
python scripts/bootstrap/check_env.py

# symptom_synonyms.py: symptom 同义词字典 (L3 query 用)
python scripts/symptom_synonyms.py --list
```

## 2. Backend Django (8 个 manage.py 命令)

```bash
cd backend

# 启动开发服务器
python manage.py runserver 0.0.0.0:8000
python manage.py runserver --noreload   # 不热重载

# 启动 ASGI (含 WebSocket)
daphne -b 0.0.0.0 -p 8000 config.asgi:application

# 数据库
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
python manage.py sqlmigrate <app> <num>
python manage.py dbshell

# 超级用户
python manage.py createsuperuser
python manage.py changepassword <user>

# 测试
python manage.py test                  # Django test runner
pytest                                 # pytest (有 conftest.py)
pytest --cov=backend --cov-report=html

# 静态文件
python manage.py collectstatic --noinput

# Django shell
python manage.py shell
python manage.py shell_plus            # django-extensions

# 自定义命令
python manage.py seed_data             # 初始数据
python manage.py migrate_resource_pack # 资源包迁移

# Celery
celery -A config worker -l info
celery -A config beat -l info
celery -A config flower                # Web UI
```

## 3. Frontend npm (7 个)

```bash
cd frontend

# 开发
npm run dev                  # vite dev server (port 5173)
npm run build                # tsc + vite build
npm run preview              # 预览构建产物
npm run lint                 # eslint

# 测试
npm run test                 # vitest run (一次性)
npm run test:watch           # vitest watch
npm run test:coverage        # vitest + c8

# 工具
npm install                  # 安装依赖
npm install <pkg>            # 加依赖
npm install -D <pkg>         # 加 dev dep
npm outdated                 # 看过期依赖
npm audit                    # 安全审计
```

## 4. Agent CLI (4 个)

```bash
cd agent
pip install -e .

# 主入口 (从 src/main.py)
python -m src --help
python -m src run --pipeline <yaml> --device <id>
python -m src run --pipeline <yaml> --config <json>

# 单独模块测试
python -m pytest tests/ -v
python -m pytest tests/test_pipeline_engine.py -v

# OCR 引擎注册
python -c "from recognition.ocr.registry import OCREngineRegistry; print(OCREngineRegistry.list())"

# 录制
python -m src record --device <id> --output <file>
```

## 5. DevOps (5 个)

```bash
# Docker Compose
docker-compose up -d              # 启动全部
docker-compose down               # 停止
docker-compose logs -f backend
docker-compose ps

# 单容器
docker build -t gaf-backend backend/
docker build -t gaf-frontend frontend/
docker build -t gaf-agent agent/

# Nginx
docker-compose exec nginx nginx -s reload

# 数据库 (SQLite)
sqlite3 /path/to/db.sqlite3 "SELECT * FROM sqlite_master;"
sqlite3 /path/to/db.sqlite3 ".backup /backup/db_backup.sqlite3"

# 证书
pwsh backend/certs/generate_dev_cert.ps1
```

## 6. Windows 11 兼容 (PowerShell 7)

**默认终端**: PowerShell 7.x（`pwsh.exe`，路径 `C:\Users\hcx\AppData\Local\Microsoft\WindowsApps\pwsh.exe`）

**PowerShell 7 支持** `&&` / `||` 链式执行（PS 5.1 不支持）:

```powershell
# ✅ PowerShell 7 正确
bash scripts/gaf_init.sh && python backend/manage.py migrate

# ✅ 也兼容（PS 5.1 风格）
bash scripts/gaf_init.sh; python backend/manage.py migrate
```

**多行 python -c** 仍不支持,改用临时脚本:
```powershell
# ❌ 错误
python -c "
import django
django.setup()
"

# ✅ 正确 (本仓库默认就用此模式)
Set-Content -Path '_temp.py' -Value 'import django; django.setup()'
python _temp.py
Remove-Item _temp.py
```

**环境变量** (PowerShell 用 `$env:VAR` 而非 `VAR=`):
```powershell
$env:GAF_BYPASS_REASON = "emergency"; bash gaf-commit.sh --no-verify -m "..."
```

**conda run** 不支持多行 `-c`:
```powershell
# ❌ 错误
conda run -n gaf python -c "
from accounts.models import User
print(User.objects.count())
"

# ✅ 正确
Set-Content -Path '_temp.py' -Value 'from accounts.models import User; print(User.objects.count())'
conda run -n gaf python _temp.py
Remove-Item _temp.py
```

## 7. 调试速查

```
后端 500?
  → 看 backend/logs/ 找 trace_id
  → python backend/manage.py shell --traceback

Agent 节点失败?
  → 看 agent/logs/ + step 节点 error_code
  → 跑 worker/src/engine/nodes/<node>.py 单独测试

前端页面空白?
  → F12 console → 看 network 找 4xx/5xx
  → npm run dev (不要 npm run preview)

WebSocket 断?
  → wscat -c ws://localhost:8000/ws/protocol/agents/?token=<jwt>
  → backend/logs/daphne.log

跨域 CORS?
  → backend/config/settings/base.py: CORS_ALLOWED_ORIGINS
```

## 8. AI 速查决策树

```
AI 接到新任务? (load cli-cheatsheet.md)
├─ 跑 sync? → §1.2 (sync_ai_memory / sync_docs / sync_skills)
├─ 验证状态? → §1.3 (check_*)
├─ 提交? → §1.4 (gaf-commit.sh)
├─ 后端开发? → §2 (manage.py + daphne)
├─ 前端开发? → §3 (npm run dev)
├─ Agent 开发? → §4 (python -m src)
├─ 部署? → §5 (docker-compose)
├─ Windows 兼容? → §6 (PowerShell 7)
└─ 调试? → §7 (按错误码定位)
```

## 9. 已知实现问题 (N93)

- **N93**: AI 倾向把命令甩给用户 → 必须自跑 (gaf_init.sh 全面自包含)
- **N92**: PowerShell 中文乱码 → `_encoding_safe.py` + `PYTHONIOENCODING=utf-8`
- **N105**: `--no-verify` 透传 bug → 用 `git commit --no-verify` 直绕

## 10. 维护期修复 (M1.A 待办)

- [ ] makefile / task runner 集中 (M1.G)
- [ ] agent CLI help 完善 (M1.G)

---

**derived-manual 标记** (不会被 sync_ai_memory 自动重生成):
- ❌ `<!-- end of auto-generated section -->` 标记缺失
- ✅ 完整手写命令清单
- ✅ AI 修改后必须 review 全文

**新命令加进表前必跑**: 验证命令真能跑通 → 再加到对应章节
