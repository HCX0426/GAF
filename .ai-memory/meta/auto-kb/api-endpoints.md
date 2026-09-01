---
maintainer: auto
source: backend/config/urls.py, backend/*/urls.py
load_when:
- 新功能
- Bug修复
priority: high
symptom:
- kb:api:endpoints
- api-routing
- DRF-viewset
- REST-endpoint
solution: 22 个 Django app 路由表 + 1 个 /api/v2/analytics 路由组 + Swagger UI 入口
related_files:
- backend/config/urls.py
- backend/config/app_info.py
- backend/workers/urls.py
- backend/tasks/urls.py
- backend/pipeline/urls.py
created_by: AI
generated: 2026-06-16
auto_updated: 2026-07-26
---

        # Auto-generated knowledge entry

        <!-- source: backend/config/urls.py, backend/*/urls.py -->
        <!-- generated: 2026-08-30 -->

        ## Symptom

        kb:api:endpoints, api-routing, DRF-viewset, REST-endpoint

        ## Solution

        22 个 Django app 路由表 + 1 个 /api/v2/analytics 路由组 + Swagger UI 入口

        ## Related files

        - `backend/config/urls.py`
- `backend/config/app_info.py`
- `backend/workers/urls.py`
- `backend/tasks/urls.py`
- `backend/pipeline/urls.py`

        <!-- end of auto-generated section -->
