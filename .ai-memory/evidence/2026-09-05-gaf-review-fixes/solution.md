---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, solution-step, evidence-solution]
solution: Solution 模板 — 列步骤 + 涉及文件 + 命令;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/problem.md
  - .ai-memory/evidence/templates/verification.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-09-05
---
## Solution（解决步骤）

1. 插件 RCE：`backend/plugins/views.py` `_validate_manifest` 校验 entry_point（禁绝对路径/`..`），`PluginSandboxExecView` 执行前 `os.path.realpath` + 前缀断言。
2. 资源导入白名单：`backend/resources/views.py` `_import_from_directory` 限制源目录在项目根内，`GAF_RESOURCE_IMPORT_ROOTS` 可扩展。
3. SQLite 设备锁：`backend/workers/view_sets/lock_stats.py` 改 `Q(locked_by__isnull=True)|Q(locked_by=user)` 原子条件 UPDATE；其余 7 处 select_for_update 加 C1 注释（executions/tasks/pipeline/scheduler）。
4. 评分原子化：`backend/tasks/resource_views.py` review 改事务内 `aggregate(Count/Avg)`；执行链路 `backend/protocol/services.py`/`consumers.py` 三处 except:pass 改 logger。
5. 前端构建：`frontend/tsconfig.app.json` 排除 `__tests__`/`*.test.*`/`*.spec.*`；修 `Sidebar.tsx:206` group/children 类型与 `LogAnalysisPanel.tsx:153` 补 `trajectory: []`。
6. S6：`frontend/src/utils/tokenStore.ts` refresh token 与多账号凭据全部改 sessionStorage 并一次性清理 localStorage 旧值；`frontend/src/api/auth.ts` 注释同步。
7. 部署域：`docker-compose.yml`/`backend/Dockerfile`/`deploy/systemd/gaf-backend.service` 改 `daphne config.asgi:application`（systemd Type=notify→simple，绑 127.0.0.1）；`pyproject.toml` 补 whitenoise；`backend/config/settings/prod.py` HSTS preload 默认 False + 改用 STORAGES dict（D8）。
8. CI/IPC：`.github/workflows/ci.yml` 类型门禁改 `npx tsc -b` 并新增 build-frontend 与 check-prod-config job；新增 `scripts/check_prod_settings.py`；`desktop/src/main/ipc.ts` read-file 白名单 + open-external 限 http(s)。
