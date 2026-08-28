---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-28-e2e-high-prio-fix/
created_by: AI
last_updated: 2026-08-28
---
## Problem（症状 / 触发条件）

E2E 全功能复测发现 9 条高优问题 (M1-M8)：

1. 监控事件 tab 首次挂载不请求数据，且级别背景色仅两态映射（无 P0/P3 区分）。
2. Header 状态灯轮询 monitors/status 受全局 user:300/min 限制偶发 429，console 刷屏。
3. WebSocket 重连失败 10 次后告警，长时间 inactive 后 token 过期导致 WS 认证失败。
4. i18n key (tasks.*) 大量未翻译残留，界面多处显示原始 key。
5. antd 6 弃用告警批量残留：Spin.tip、Alert.message、notification.message、Carousel.dotPosition、InputNumber.addonAfter。
6. recharts ResponsiveContainer 瞬态 0 尺寸导致 width=-1 图表不渲染。
7. 通知行不渲染 body 文本（前端读 content 但后端序列化未暴露）。
8. 控制台 SyntaxError: Unexpected token、扫描模拟器弹窗 ERR_ABORTED、匹配预览 mock。