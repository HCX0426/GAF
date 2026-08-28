# s39 problem — sync_skills.py 1064 行拆分

## 触发

TD-365（i1_large_files，P2）：`scripts/bootstrap/sync_skills.py` 1064 行 > 1000 阈值（2026-08-17 monthly_health_check 扫描）。

## 症状

- 单文件 1064 行，6 个清晰功能域混合（常量/检查/工具/inspect/sync/changelog/timestamps/main）
- 新 AI 上下文读取成本高；维护性差
- 与 s38（sync_ai_memory.py）同属 TD-365 大文件治理批次

## 影响范围

- 调用方：governance batch（`("bootstrap.sync_skills", "main", ["--check"], ...)`）、gaf_init.sh、test_decision_tree_sync.py / test_sync_skills_timestamps.py / test_sync_changelog.py / test_bootstrap_gaf.py
- 外部 API 契约：全部符号（常量 + 私有函数）必须从 `sync_skills` 模块继续可访问（测试用 `from sync_skills import ...` + monkeypatch 常量）
- 拆分必须保持 4 种加载上下文可用（__main__ / scripts.bootstrap.sync_skills / bootstrap.sync_skills / sys.path-hack 顶层）

## 目标

- 主文件 1064 → < 550 行（验收：457）
- 零功能变化（CLI/API/governance 行为不变）
- 复用 N202 ⑰⑱ 检查项（s38 闭环经验）
