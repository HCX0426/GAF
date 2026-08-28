---
date: 2026-08-28
symptom: [e2e-script-all-skip, urljoin-path-swallow, context-request-401, antd-modal-hidden-dom]
solution: Playwright E2E 三坑——URL 拼接禁用 urljoin（吞目录段）；context.request 不共享前端 localStorage JWT（手动带 Authorization）；antd5 Modal 关闭后保留隐藏 DOM（用 :visible 非 count 判定）
related_files:
  - scripts/e2e/scenarios/full_routes.py
  - frontend/src/pages/AI/SkillMarket.tsx
  - backend/agents/view_sets/scan_register.py
created_by: AI
priority: high
n_id: N212
diff_keywords: ["urljoin", "context.request", "ant-modal", ":visible", "localStorage", "access_token", "full_routes"]
---

# Playwright E2E 脚本三坑：URL 拼接 / 探针鉴权 / Modal 可见性判定

## 症状（2026-08-28 full_routes 首跑 + I-06 复核）

1. `full_routes` 动态路由 probe 全部 `SKIP no env data`，但同一端点用浏览器访问都 200 有数据。
2. 标注页/其它页面走 API 探针时 4xx。
3. I-06 Skill 市场弹窗被误判"取消需 Esc 才关闭"，实际功能正常。

## 根因

1. **urljoin 吞路径段**：`urljoin("http://host/api/v2", "tasks/?page_size=1")` → `http://host/api/tasks/...`（base 无尾斜杠时最后一段 `v2` 被替换）。探针 URL 全错 → 404/空。
2. **context.request 不共享页面鉴权**：前端 JWT 在 `sessionStorage['access_token']`，axios 走 `Authorization: Bearer` 头；`page.context.request` 是独立上下文，不带该头 → 401/403。
3. **antd Modal 关闭后 DOM 保留**：antd5 默认 `destroyOnClose=false`，`open=false` 后 modal 节点仍存在但 `display:none`。用 `.ant-modal` 的 `count()` 判定"是否关闭"永远是 ≥1 → 误判按钮无效；只有 `:visible` 才算。

## 解决方案（已实现）

1. URL 拼接用 f-string 直拼：`f"{base}/api/v2/{path.strip('/')}?page_size=1"`，不用 urljoin。
2. 探针手动带头：`page.evaluate("sessionStorage.getItem('access_token')")` → `headers={"Authorization": f"Bearer {token}"}`。
3. 可见性判定：`page.locator(".ant-modal:visible").count() == 0`。

## 泛化原则

写浏览器自动化脚本三查：① URL 直接拼接并打印验证；② 任何"页面外的请求"（request/probe/fetch）默认不带页面态，鉴权/ cookie/ storage 都要显式传递；③ DOM 判定用"可见性"而非"存在性"（隐藏 toast/空态/关闭动画后 DOM 都还在）。