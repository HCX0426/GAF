---
date: 2026-06-14
symptom: [agent:capability:mismatch, 能力, 匹配, capability-error, version-mismatch]
solution: 握手时双向能力声明
related_files:
  - backend/protocol/schemas.py
  - worker/src/core/config.py
created_by: AI
priority: medium
diff_keywords: ["capability", "mismatch", "handshake", "version-drift"]
---

# Agent 能力不匹配 Backend 期望

## 症状

Backend 收到 Agent 注册时返回"unsupported capability"，但 Agent 日志显示能力已声明。

## 触发条件

- Backend 升级后新增 capability 字段
- Agent 是旧版本未升级
- 部署环境前后端版本不匹配

## 根因

能力声明用枚举值，未定义"未知 capability"的处理逻辑。

## 解决步骤

1. 后端 `schemas.py` 用 `Literal["ocr", "click", ...]` 严格枚举
2. Agent 端 `config.py` 同步枚举
3. 握手时：能力缺失 → 警告 + 降级，不直接拒绝

## 验证

- 后端 v1 + Agent v2 通信：缺失 capability 警告，连接成功
- 后端 v2 + Agent v1 通信：缺失 capability 拒绝，提示升级

## 预防

- CI 加版本兼容性矩阵测试
- 任何新增 capability 必须后端先发版
