# s45 Solution — 录制截图真实闭环

## 架构决策

### 认证：AgentTokenAuthentication（backend/agents/auth.py）
- `Authorization: Token <agent-token>`（**Token scheme 而非 Bearer**——JWT 占用 Bearer，两认证类共存会冲突，实测 JWT 认证对非 JWT Bearer 头抛 401 中断）
- `hash_token(token)` 查 `Agent.agent_token_hash` → `request.agent`，返回 (AnonymousUser, None)
- 上传 action 用自定义 `IsAgentOrRecordingOwner`（agent 过 / JWT owner 过）

### backend 端点（RecordingViewSet）
- `POST /api/v2/pipeline/recordings/{id}/screenshots/`：multipart `event_index` + `file` → 存 `MEDIA_ROOT/screenshots/recordings/<id>/<event_index>.png`（覆盖写）→ 更新 `recording_data.events[i].screenshot_url` 写库（RecordingSerializer 直接输出 recording_data → detail 自动带出）
- `GET /api/v2/pipeline/recordings/{id}/screenshots/<filename>/`：FileResponse，user 过滤（越权 404）
- URL 构造用 `settings.MEDIA_URL.strip('/')`（dev 实际 `/media/` 带前导斜杠，base 无——双向兼容）

### agent（recording_api.py + __main__.py run_record）
- token 优先级：CLI --agent-token > env GAF_AGENT_TOKEN > TokenStore(server_url)
- `upload_screenshots(recording_id, events)`：逐个 screenshot 事件上传，失败 warn 不中断，返回统计
- run_record 停止后自动上传（无 token 时提示跳过，不影响本地保存）

### 前端（RecordingStepper.tsx）
- `RecordingEvent.screenshot_url?: string`
- 有 url → `<img>` + overlay 按图片真实尺寸（onLoad naturalWidth/Height，替代写死 1920x1080）
- 无 url → 保留占位

## 修复的伴随问题
- ruff SIM105（pipeline/views.py:229 既有 try/except/pass → contextlib.suppress）
- frontend api-paths.test.ts Marketplace 断言过时（fetchMarketItems 已改 /skills/market/，断言仍期望 /tasks/marketplace/——pre-existing 失败当场修复）

## 已知限制（写入 spec）
- RecordingPanel demo 假数据不改造（需产品决策）
- agent 录制上传 user 绑定 superuser（Agent 无 user FK，多用户环境待完善）
- 前端无组件测试基建，Stepper 靠 vite build + 手工验证