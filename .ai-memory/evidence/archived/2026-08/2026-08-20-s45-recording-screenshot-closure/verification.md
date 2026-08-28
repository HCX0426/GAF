# s45 Verification — 录制截图真实闭环

## Verification

```bash
pytest backend/pipeline/tests/test_views.py -q          # 89 passed (含 9 新)
pytest backend/pipeline/tests/test_converter.py -q      # + test_models: 179 passed
pytest backend/agents/tests/test_token_api.py -q        # + test_agent_core: 15 passed
pytest agent/tests/test_recording_api.py -q             # 10 passed (新)
pytest agent/tests/test_recording.py -q                 # + test_target_resolution: 67 passed
npm test                                                # 347 passed (frontend)
npx vite build                                          # built in 17.30s
ruff check backend/agents/auth.py backend/pipeline/views.py backend/pipeline/tests/test_views.py agent/src/core/recording_api.py agent/tests/test_recording_api.py   # All checks passed
```

| 层 | 命令 | 结果 |
|----|------|------|
| backend pipeline | pytest backend/pipeline/tests/test_views.py（含 RecordingScreenshotTests 9 个新测试）| 89 passed |
| backend pipeline 全 | test_views + test_converter + test_models | 179 passed |
| backend agents | test_token_api + test_agent_core | 15 passed |
| agent | test_recording_api.py（新 10 测试）+ test_recording + test_target_resolution | 67 passed |
| frontend | npm test | 347 passed（含修复的 Marketplace 断言）|
| frontend build | npx vite build | 通过 |
| lint | ruff check（5 改动文件）| All checks passed（N806 为 __main__.py:57 既有命名，非本 spec）|

## RecordingScreenshotTests 覆盖（9 项）
- JWT owner 上传 → 200 + 文件落盘 + recording_data.screenshot_url 写库
- agent token 上传 → 200（Token scheme）
- 无认证 → 401（DRF WWW-Authenticate）
- 非 owner JWT → 403
- event_index 越界 → 400 / 缺 file → 400
- owner 下载 → 200 image/png + PNG 魔数
- 非 owner 下载 → 404（user 过滤）
- 文件缺失 → 404

## 关键实现细节验证
- MEDIA_URL dev 实际为 `/media/`（带前导斜杠）——`strip('/')` 双向兼容，URL 无 `//media` 双斜杠（实测修复）
- Token scheme 与 JWT Bearer 共存：JWT 用户上传（Bearer）+ agent 上传（Token）双路径均通过