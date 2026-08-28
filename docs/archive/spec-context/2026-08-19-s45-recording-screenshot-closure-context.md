# s45 spec-context 承载体 — 录制截图真实闭环 (2026-08-19)

> 关联 spec: docs/specs/archived/2026-08/2026-08-19-s45-recording-screenshot-closure.md
> B2 大修改 evidence: 跨 3 层（backend + agent + frontend），diff > 500 行

## 1. 用户决策原文

- "2"（三选一中选择方案 2：接真截图——对接后端，截图落盘 + 前端展示）

## 2. N151 5 步法评估过程

- **架构盘点**: RecordingStepper 占位 → 根因链 4 环（agent 本地截图路径 / RecordingAPIClient 死代码无鉴权 / backend 无存储 serve 端点 / 前端 demo 假数据）
- **识别反模式**: (a) agent HTTP API 无鉴权（recording_api.py 全方法裸调）；(b) 跨层数据契约断链（screenshot_path agent 本地 → 前端不可达）；(c) 死代码堆积（RecordingAPIClient 无人调用）
- **A/B/C 备选**:
  - 后端 serve 方式: A=DRF action FileResponse（带权限，越权 404）; B=static() 挂 MEDIA_URL（无权限隔离）; C=nginx 静态直出。选 A
  - agent 认证: A=Token scheme 自定义认证类（与 JWT 共存）; B=复用用户 JWT（agent 无用户身份，不可行）; C=无认证（不安全）。选 A
  - 上传粒度: A=一次一张（event_index+file，失败可重试）; B=批量 zip; C=base64 内嵌 JSON（大 JSON 上限）。选 A
- **拒绝反模式**: 拒绝"只改前端占位文案"（最小化修补，链路仍断）; 拒绝"agent 直连 MEDIA 目录"（跨机部署失效）
- **AI 自决边界**: 用户已选方案 2 授权实施；RecordingPanel demo 改造超出 scope（用户未决策真实录制 UI）

## 3. N167 七维度评分细节

| 维度 | 评分 | 说明 |
|------|------|------|
| 1 架构长远性 | 5/5 | 认证类可复用于其他 agent HTTP 端点；上传/下载端点独立可扩展 |
| 2 全局归一化 | 4/5 | token 优先级对齐 main() 既有模式；MEDIA_URL 双向兼容 |
| 3 新旧兼容 | 5/5 | 无 url 时前端保留占位；demo 数据行为不变；新增端点不影响既有 |
| 4 现有业务完善 | 5/5 | 录制回放从占位到真实截图；agent CLI 录制进入 backend 闭环 |
| 5 性能资源优化 | 3/5 | 一次一张上传，无批量内存峰值 |
| 6 安全合规加固 | 5/5 | agent token 哈希校验 + 越权 404/403 + 文件名 basename 防穿越 |
| 7 长期维护成本 | 4/5 | 认证类集中；上传逻辑单点 |

总分 31/35 ≥ 19 → AI 自决 ✓

## 4. 关键实施决策

- **Token scheme 冲突实测**: 最初用 Bearer + 双认证类，JWT 认证对 agent token 抛 401 中断（认证类异常不降级）→ 改 Token scheme 实测通过。教训：**同 scheme 双认证类不可共存，必须错开 scheme**
- **MEDIA_URL 双斜杠 bug**: dev settings MEDIA_URL='/media/'（带前导斜杠），base 'media/'（无）→ `f"/{MEDIA_URL.rstrip('/')}"` 产生 `//media` → 用 `strip('/')` 双向兼容
- **DRF 无认证行为**: 无 successful_authenticator → 401（非 403），测试断言修正
- **FileResponse 测试**: `resp.content` 为空（streaming），需 `b''.join(resp.streaming_content)` 校验 PNG 魔数
- **screenshot_file 尾斜杠**: DRF action 路由带尾斜杠，GET 必须 `/1.png/`
- **Recording.save update_fields**: Recording 无 updated_at 字段（仅 created_at），update_fields=["recording_data"]
- **预存错误当场修复**: frontend Marketplace 测试断言过时（fetchMarketItems → /skills/market/）；pipeline/views.py:229 SIM105

## 5. N173 用时字段

- start_ts: 2026-08-19T19:05:00+08:00
- end_ts: 2026-08-19T19:55:00+08:00
- duration_min: 50
- within_baseline: true（大修改基线 < 60min）
- root_cause_if_over: -