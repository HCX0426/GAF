---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, problem-step, evidence-problem]
solution: Problem 模板 — 描述症状/触发条件/影响范围;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/solution.md
  - .ai-memory/evidence/templates/verification.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-09-05
---
## Problem（症状 / 触发条件）

2026-09-05 全仓架构与代码评审（docs/analysis/2026-09-05-architecture-code-review.md）发现并实测确认了一批单机器模式相关缺陷：插件 entry_point 路径穿越可 RCE（plugins/views.py:77-85,457-461）、资源包导入可复制任意本地目录（resources/views.py:256）、SQLite 下 select_for_update 静默失效致设备锁无互斥（workers/view_sets/lock_stats.py:51）、评分聚合非原子丢更新（tasks/resource_views.py:299-308）、执行链路 except:pass 静默吞异常（protocol/services.py:762,873）、前端 npm run build 退出码 2 且 CI 类型门禁空跑（ci.yml:126）、refresh token 长期落 localStorage（tokenStore.ts:95,200）、read-file IPC 无路径校验（desktop/src/main/ipc.ts:73）、生产部署三处均为纯 WSGI 无 WebSocket（docker-compose.yml/systemd/Dockerfile）、whitenoise 未在 pyproject 声明（裸机 prod 首请求 500）、STATICFILES_STORAGE 在 Django 5.2 被静默忽略（prod.py:58）。
触发条件：静态审查 + 可执行验证（pytest/tsc/自写校验脚本）。
影响范围：backend 17 app、frontend 构建、desktop IPC、deploy 三条路径、CI 门禁。
