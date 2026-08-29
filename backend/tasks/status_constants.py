"""任务执行域状态值常量 — 单一权威源 (归一化, 2026-08-29).

TaskExecution / TaskStep / ExecutionStep 三个模型此前各自在 TextChoices 里
重复散落字符串字面量 ('pending'/'running'/...). 此处统一定义共享值常量,
枚举引用同一来源, 防拼写漂移; 标签 (label) 仍由各枚举自行声明.

审核域状态 (MarketplaceItem/SkillMarket 的 待审核 pending) 语义不同,
刻意不纳入本域.
"""

EXEC_STATUS_PENDING = "pending"
EXEC_STATUS_RUNNING = "running"
EXEC_STATUS_PAUSED = "paused"
EXEC_STATUS_SUCCESS = "success"
EXEC_STATUS_FAILED = "failed"
EXEC_STATUS_SKIPPED = "skipped"
EXEC_STATUS_CANCELLED = "cancelled"
EXEC_STATUS_FORCE_TERMINATED = "force_terminated"
