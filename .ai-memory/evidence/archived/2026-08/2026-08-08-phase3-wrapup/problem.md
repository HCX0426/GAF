# B2: Phase 3 架构重构收尾

## 问题描述

架构重构 Phase 3 涉及多个子任务（TD-350~TD-354）的收尾工作，包括：
- 引擎边界统一（ChainManager + TaskExecutor）
- Pipeline ghost click 修复
- GAF Daemon 进程守护
- TaskExecution 归档策略
- 节点元数据注册机制

## 触发条件

- 任务完成后的代码提交阶段，diff 超过 500 行阈值
- 跨 10+ backend app 修改
- 包含 DB 迁移文件