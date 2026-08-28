# s45: 录制截图真实闭环 — agent 上传 + backend 存储 serve + 前端展示

> 状态: ✅ 已归档（-） | spec_id: 2026-08-19-s45-recording-screenshot-closure
> 来源: L3-1 扫描 [B]（s42）剩余项 → 用户决策方案 2（接真截图，对接 backend + 自动落盘）
> 创建: 2026-08-19 | 归档: 2026-08-20 | 基线: N173 大修改 < 60min
> 实现产物: backend/agents/auth.py（新）+ backend/pipeline/views.py（上传/下载 action）+ agent/src/core/recording_api.py（重写）+ agent/src/__main__.py（run_record 串联）+ frontend RecordingStepper.tsx（真图展示）+ 19 新测试（backend 9 + agent 10）

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit | 验收 evidence |
|------|------|---------|--------|--------------|
| P1 backend: AgentTokenAuthentication + 上传/下载 action | ✅ | 2026-08-19 | - | 9 新测试 + 179 passed |
| P2 agent: recording_api 鉴权 + upload_screenshots + run_record 串联 | ✅ | 2026-08-19 | - | 10 新测试 + 67 passed |
| P3 frontend: screenshot_url 类型 + Stepper 真图展示 | ✅ | 2026-08-19 | - | 347 passed + vite build |
| P4 验证 + evidence + 归档 | ✅ | 2026-08-20 | - | 见归档 |

## 背景与事实

L3-1 扫描（s42）发现 `RecordingStepper.tsx` 截图占位（"截图需通过后端 URL 访问"）。根因链：

1. **agent 录制**（`python -m src --record <name>`）：截图写 `./recordings/screenshots/<name>/*.png`（agent 本地），`recording_data.events[].screenshot_path` 存 **agent 本地路径**（前端无法访问）
2. **`RecordingAPIClient`（agent/src/core/recording_api.py）是死代码**：`upload_recording/list_recordings/delete_recording` 无任何调用方；无鉴权 header（backend 全部端点要求 JWT/agent token）
3. **backend 无录制截图存储/serve 端点**；MEDIA_URL 配了但 urls.py 无 static() 挂载
4. **前端** `RecordingPanel.tsx` 是 demo 假数据（随机 click，`screenshot_path: ''`，注释明示 "Demo"）——Stepper 显示占位的对象是 demo 录制流

**用户决策**（方案 2）：接真截图——对接 backend，截图落盘 + 前端展示。

## 设计决策

- **认证**：新增 `AgentTokenAuthentication` DRF 认证类（`Authorization: Token <agent-token>` → `hash_token` 查 Agent → `request.agent`）。**Token scheme 而非 Bearer**——JWT 认证类已占用 Bearer，同 scheme 双认证类共存时 JWT 认证对非 JWT 头抛 401 中断（实测），错开 scheme 解决。上传 action 用自定义 permission `IsAgentOrRecordingOwner`（agent 通过 / JWT 用户是 recording.user 通过）。下载 action 走 RecordingViewSet 既有 user 过滤（仅 viewer）。
- **上传**：`POST /api/v2/pipeline/recordings/{id}/screenshots/`（multipart: `event_index` + `file`，一次一张）→ 存 `MEDIA_ROOT/screenshots/recordings/<id>/<event_index>.png`（覆盖写）→ 更新 `recording_data.events[event_index].screenshot_url` 写库 → 返回 `{event_index, url}`。RecordingSerializer 直接输出 recording_data → detail 接口自动带出 screenshot_url ✓
- **下载**：`GET /api/v2/pipeline/recordings/{id}/screenshots/<filename>`（re_path action，FileResponse，越权 404）
- **agent 上传 user 绑定**：agent 无 user FK → recording.user 绑定第一个 superuser（服务账户语义，注释说明；admin/admin123 即 superuser，本地开发闭环成立）。**已知限制**：多用户环境 agent 录制归 admin，后续可在 Agent 模型加 user FK 完善
- **前端**：`RecordingEvent` 加 `screenshot_url?: string`；Stepper 有 url → `<img>` + 真实尺寸 overlay（onLoad naturalWidth/Height，替代写死 1920x1080）；无 url → 保留占位文字
- **demo 数据**：RecordingPanel 保持 demo（注释已明示），超出本 spec 范围

## 任务清单

### P1: backend — 认证类 + 上传/下载 action

- [ ] 1. `backend/agents/auth.py`（新）: `AgentTokenAuthentication`（Bearer → hash_token 匹配 Agent.agent_token_hash → request.agent；否则 raise AuthenticationFailed）
- [ ] 2. `backend/pipeline/views.py` RecordingViewSet 加 2 actions:
  - `upload_screenshot`（POST, url_path="screenshots"）: 校验 event_index 合法 + file 存在 → 存 MEDIA_ROOT/screenshots/recordings/<id>/<event_index>.png → 更新 recording_data.events[i].screenshot_url → 返回 url
  - `screenshot_file`（GET, re_path `screenshots/(?P<filename>[^/]+)`）: FileResponse，get_object() user 过滤
- [ ] 3. permission: `IsAgentOrRecordingOwner`（request.agent 非空 → 过；否则 user == recording.user）
- [ ] 4. 测试 `backend/pipeline/tests/test_views.py`（RecordingCRUDTests 扩展）: JWT 上传成功 / agent token 上传成功 / 无认证 401 / 越权 404 / 下载成功 / 非法 event_index 400

### P2: agent — 鉴权 + 上传 + 串联

- [ ] 5. `recording_api.py`: `__init__(server_url, token="")` + Authorization header；新方法 `upload_screenshots(recording_id, events)`（只传 screenshot 且文件存在，逐个 POST，失败 warn 不中断）
- [ ] 6. `__main__.py run_record`: stop 后串联：upload_recording → 拿 id → upload_screenshots → 打印结果（token 复用现有优先级：CLI --agent-token > env GAF_AGENT_TOKEN > TokenStore）
- [ ] 7. 测试 `agent/tests/test_recording_api.py`（新）: mock requests → upload_screenshots 读文件 + 断言 POST 调用；文件缺失跳过

### P3: frontend — 类型 + 展示

- [ ] 8. `frontend/src/api/recordings.ts`: `RecordingEvent` 加 `screenshot_url?: string`
- [ ] 9. `RecordingStepper.tsx`: screenshot_url 存在 → `<img src>`（antd Image，真实尺寸 overlay 用 naturalWidth/Height）；无 → 保留占位
- [ ] 10. vite build 验证

### P4: 验证 + evidence + 归档

- [ ] 11. 验证: backend pipeline 相关测试 + agent 测试 + ruff + vite build
- [ ] 12. evidence 三件套 + spec-context 承载体（B2）
- [ ] 13. 归档 spec

## 已知限制

- RecordingPanel demo 假数据不改造（注释明示，需产品决策真实录制 UI）
- agent 录制上传 user 绑定 superuser（多用户环境待 Agent.user FK）
- 前端无组件测试基建（仅 api tests），Stepper 靠 vite build + 手工验证