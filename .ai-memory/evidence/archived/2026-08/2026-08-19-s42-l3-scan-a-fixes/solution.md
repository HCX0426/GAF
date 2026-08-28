# s42 solution — 枚举补全 + 契约测试 + fetch 修复

## 修复 1: ALL_NODE_TYPES 补全（46 种）

- 基准：agent @register_node 42 种（执行真相，覆盖前端 38 种）+ legacy 4 种保留
- legacy 4 种（login_account/switch_account/switch_resource/captcha_detect）**非死类型**：
  validators.py:112-115 字段映射 + estimator.py:25-28 耗时表 + check_code_rules/check_schema_unification 白名单仍消费 → 保留 + deprecated 注释（BD2-AUTO 兼容，防已持久化 pipeline 校验失败）

## 修复 2: 跨层契约测试（防再漂移）

scripts/tests/test_pipeline_node_contract.py（文本扫描不 import，4 断言）：
- agent 注册名 ⊆ backend 枚举
- 前端 PipelineNodeType ⊆ backend 枚举
- backend − agent == legacy 4 种（防"悄悄加类型不进枚举"）
- backend ⊇ agent ∪ frontend（兜底）

提取方式：agent 正则 @register_node("...")（含多行形式）；前端 PipelineNodeType union；后端 ALL_NODE_TYPES 列表。

## 修复 3: DailySummaryCarousel

- fetch('/api/unattended/progress/') → client.get('/scheduler/unattended/progress/')
- import client from '@/api/client'（interceptor 自动带 token，删 buildAuthHeaders import）
- 全文件残留扫描：无裸 fetch / buildAuthHeaders 引用

## 关键决策

- 契约测试放 scripts/（跨层文本扫描 = s40 拆分后 scripts 测试定位；backend 测试无法读 agent/frontend）
- 枚举不改结构（list + jsonschema enum 用法不变），只补内容