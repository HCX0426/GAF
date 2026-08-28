// Task 4.34 (P2-19, 2026-07-28): 全部 17 个 *Config.tsx 文件已删除。
//
// 这些 Config 组件 (ClickConfig/SwipeConfig/KeyPressConfig/.../SubPipelineConfig)
// 在 Phase 2.6 之后就不再被 NodePropertyPanel.tsx 引用 — NodePropertyPanel 改用
// 内嵌 case 渲染字段, 这些独立 Config 组件成为死代码。
//
// 第四轮 N191 评估发现 8 个 Config 文件字段名仍用 camelCase (与 NodePropertyPanel
// 内嵌 case 的 snake_case 不一致), 经全量 grep 验证 17 个文件全部无外部引用,
// 一并清理避免后续维护者混淆。
//
// 字段渲染逻辑现位于 NodePropertyPanel.tsx 的 renderFields() 方法内,
// 与后端 validators.py 的 node_required dict (snake_case canonical) 对齐。
//
// 已删除文件清单 (17 个):
// - ClickConfig / SwipeConfig / KeyPressConfig / TextInputConfig
// - TemplateMatchConfig / OcrConfig / ColorDetectConfig / FeatureMatchConfig
// - WaitConfig / BranchConfig / LoopConfig / RandomDelayConfig
// - NotifyConfig / DeviceControlConfig / MonitorConfig / SubPipelineConfig / GotoConfig
export {};
