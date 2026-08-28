---
source: GAF/.ai-memory/lessons/N143-authenticated-image-blob-fetch.md
load_when: [图片加载 401, IsAuthenticated 端点图片, <img> JWT, axios blob 图片, objectURL 图片, baseURL 双重前缀]
priority: medium
symptom: [kb:lesson:n143, img-tag-401, authenticated-image, blob-objecturl, axios-baseurl-double-prefix]
solution: 后端 IsAuthenticated 图片端点不能用 `<img src=URL>` 加载 (浏览器不附 JWT)。改为 axios.get(url, {responseType:'blob'}) → URL.createObjectURL(blob) → 传 objectURL 给 img。注意 axios baseURL 已含 /api/v2，image_url 是绝对路径时要 strip 前缀避免双重 /api/v2/api/v2/。
related_files:
  - frontend/src/pages/Resources/TemplateAnnotation/TemplateAnnotationTab.tsx
  - frontend/src/components/Canvas/GafCanvasOverlay.tsx
  - backend/resources/views.py
  - frontend/src/api/client.ts
created_by: AI
date: 2026-07-05
generated: 2026-07-05
level: L1
n_id: N143
topic: cross-layer-sync
---

# N143: 认证图片端点不能用 `<img src>` 加载 — 必须 axios blob + objectURL

> **触发**: R37-P1 C5 TemplateAnnotationTab 用 `imageUrl={template.image_url}` 加载模板图片
> **时间**: 2026-07-05 | **commit**: `-` (C6 修复)
> **影响**: 模板图片 401 Unauthorized，Tab 2 无法显示模板背景图，无法画标注

## 1. 问题 (Problem)

后端 `template_file_view` (`/api/v2/resources/templates/files/<pack_id>/<file_path>`) 装饰器：
```python
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def template_file_view(request, pack_id, file_path):
    ...
```

前端 `TemplateAnnotationTab.tsx` 直接把 `template.image_url` 传给 `GafCanvasOverlay` 的 `imageUrl` prop，组件内部：
```ts
const img = new Image();
img.src = imageUrl;  // 浏览器发请求，不带 Authorization header
```

结果：`401 Unauthorized`，图片加载失败。

## 2. 症状 (Symptom)

- Console: `[error] Failed to load resource: the server responded with a status of 401 (Unauthorized)`
- Network: `GET /api/v2/resources/templates/files/2/get_email/空邮箱标识.png 401`
- Tab 2 canvas 区域空白，无模板背景图

## 3. 根因 (Root Cause)

1. **`<img>` 标签不能附 JWT**：浏览器原生 `<img>` 和 `new Image()` 发的 GET 请求只带 cookies，不带 `Authorization: Bearer <token>` header。后端 `IsAuthenticated` 装饰器拒绝。
2. **TemplateGallery 用 fallback SVG 掩盖了问题**：`<Image src={thumbnail_url} fallback="data:image/svg+xml..." />` —— 401 时显示 "No Image" SVG，用户以为图片本来就空。
3. **axios baseURL 双重前缀陷阱**：`image_url` 是绝对路径 `/api/v2/resources/...`，但 `client` 的 `baseURL='/api/v2'`，直接 `client.get(image_url)` 会变成 `/api/v2/api/v2/resources/...` 404。

## 4. 修复 (Fix)

```ts
// TemplateAnnotationTab.tsx — fetch blob via authenticated axios
useEffect(() => {
  if (!selectedTemplate?.image_url) {
    setTemplateImageUrl(undefined);
    return;
  }
  // Strip API_PREFIX because axios baseURL already includes it
  const stripped = selectedTemplate.image_url.replace(/^\/api\/v2/, '');
  let revoked = false;
  let createdUrl: string | null = null;
  client
    .get(stripped, { responseType: 'blob' })
    .then((res) => {
      if (revoked) return;
      createdUrl = URL.createObjectURL(res.data);
      setTemplateImageUrl(createdUrl);
    })
    .catch(() => { if (!revoked) setTemplateImageUrl(undefined); });
  return () => {
    revoked = true;
    if (createdUrl) URL.revokeObjectURL(createdUrl);  // 防内存泄漏
  };
}, [selectedTemplate]);

// Pass objectURL to GafCanvasOverlay
<GafCanvasOverlay imageUrl={templateImageUrl} ... />
```

## 5. 验证 (Verification)

- 修复前：Tab 2 console `[error] 401 Unauthorized` + 空白 canvas
- 修复后：Playwright Tab 2 `0 console errors, 0 failed responses`，3 个 ant-select 渲染正常

## 6. 教训 (Lesson)

**认证图片端点加载模式**：
- ❌ `<img src={api_url}>` — 浏览器不带 JWT，401
- ❌ `fetch(api_url)` 默认不带 Authorization header
- ✅ `axios.get(stripped_url, { responseType: 'blob' })` — axios 拦截器自动附 JWT
- ✅ `URL.createObjectURL(blob)` — 生成 `blob:http://...` URL，可传给 `<img src>`
- ✅ Cleanup 时 `URL.revokeObjectURL(url)` 防内存泄漏

**axios baseURL 陷阱**：
- `client.baseURL = '/api/v2'`
- 若 `api_url = '/api/v2/resources/...'` (绝对路径)，`client.get(api_url)` → `/api/v2/api/v2/resources/...` 404
- 修复：`api_url.replace(/^\/api\/v2/, '')` strip 前缀
- 或用 `axios.get(window.location.origin + api_url, {...})` 绕过 baseURL

**验证清单**：
1. 改图片加载方式后必跑 Playwright (catch 401/404 that tsc 不报)
2. Network tab 检查实际请求 URL (避免双重前缀)
3. Cleanup useEffect revoke objectURL (Chrome DevTools Memory tab 查 blob 泄漏)

## 7. 适用范围 (Scope)

- ✅ TemplateAnnotationTab (本 fix)
- 🔧 TemplateGallery (`<Image fallback=SVG>` 掩盖问题，可后续也改 blob 模式以显示真实图片)
- 🔧 任何后端 `IsAuthenticated` 图片/文件端点 + 前端 `<img>`/`<a download>` 场景

## 8. 分级分发 (L1 可复用经验 — v8.5 修订)

> **级别判定**: N143 有 Y/N 检查清单价值 (IsAuthenticated 图片端点 + axios blob 模式), 但不是 AI 全局硬约束 → **L1 (3 层)**
> **修订历史**: 初版误判为 L2 (5 层), v8.5 修订降级为 L1, 移除 ③ spec/tasks + ⑤ project_rules 索引行

| 层 | 路径 | 内容 | L1 |
|:--:|------|------|:--:|
| ① lessons | `.ai-memory/lessons/N143-authenticated-image-blob-fetch.md` (本文件) | 完整教训 | ✅ |
| ② architecture-mistakes | `.ai-memory/summaries/architecture-mistakes.md` | 摘要：认证图片端点必须 axios blob + objectURL | ✅ |
| ③ spec/tasks | — (L1 不进 spec/tasks) | — | — |
| ④ yn-matrices | `.ai-memory/meta/yn-matrices.md` §6 ㉗ | Y/N 矩阵: 图片加载 401 时改 blob 模式 | ✅ |
| ⑤ project_rules | — (L1 不进 §6.4 索引表) | — | — |
