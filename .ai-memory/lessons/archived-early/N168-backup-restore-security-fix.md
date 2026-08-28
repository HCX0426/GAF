---
n_id: N168
topic: architecture
title: backup/restore 双套反模式 + cursor.execute SQL 注入漏洞
date: 2026-07-17
priority: high
category: architecture
severity: P0
symptom: create_backup 用 call_command('dumpdata') 输出 JSON fixture, restore_backup 却用 cursor.execute(f.read()) 当 SQL 执行; 文件名 database.sql 与 dumpdata JSON 输出不一致; restore 路径完全无法工作 + 恶意 ZIP 可执行任意 SQL
solution: create/restore 对称化 — 文件名 database.sql→database.json + restore 改用 call_command('loaddata', db_file) 替代 cursor.execute; 新建 test_backup_restore.py 6 个测试覆盖 round-trip + 恶意 SQL 拒绝 + 源码回归守卫
diff_keywords: [sql-injection, cursor.execute, backup-restore, dumpdata]
related_files:
  - backend/tasks/backup_views.py
  - backend/tasks/tests/test_backup_restore.py
  - backend/tasks/urls.py
  - docs/archive/active-tech-debt.md
created_by: AI
cross_refs:
  - N167
  - N151
  - N166
related_rules:
  - project_rules.md §2.0 三原则 (扩展性/逻辑正确性/命名正确性)
  - project_rules.md §2.0.5 七维度评估 (维度 2 全局归一化 + 维度 6 安全合规加固)
  - project_rules.md §3.7 L3 持续评估循环 (L3-1 ③ 架构层扫描发现)
status: active
level: L1
---

# N168 — backup/restore 双套反模式 + cursor.execute SQL 注入

## 触发原话 (L3-1 ③ 架构层扫描 agent 报告)

> "[A] backup_views.py 双套反模式 + 安全漏洞 + 逻辑错误
> - create 用 dumpdata 输出 JSON, restore 却用 cursor.execute 当 SQL 执行 — 双套反模式
> - cursor.execute(f.read()) 执行用户上传 ZIP 内的 database.sql 文件内容 — 任意 SQL 执行漏洞
> - 即使文件是 JSON fixture, cursor.execute 也会语法错误 — restore 路径完全无法工作
> - 文件名 database.sql 与 dumpdata 输出的 JSON 内容不一致 — 命名错误"

## 根因

`backend/tasks/backup_views.py` 备份功能初次实现时, create/restore 不对称设计:
- create 用 Django 标准 `call_command('dumpdata', ...)` 输出 JSON fixture 到 `database.sql` 文件
- restore 用 `cursor.execute(f.read())` 直接执行该文件内容当 SQL
- 文件名 `database.sql` 误导 (实际内容是 JSON, 不是 SQL)
- restore 路径**从未被实际测试过** (无单测覆盖), 长期累积为 P0 安全漏洞

3 个反模式同时存在 (违反 §2.0 三原则):
1. **逻辑正确性**: dumpdata 输出 JSON, cursor.execute 期望 SQL — 永远失败
2. **命名正确性**: 文件名 database.sql 与 JSON 内容不一致
3. **安全合规** (§2.0.5 维度 6): cursor.execute 执行用户上传内容 = SQL 注入漏洞

## 解决方案

按 N167 七维度评分 (方案 B 总分 20/21, AI 自决):
1. 文件名 `database.sql` → `database.json` (create + restore 两处, 与 dumpdata JSON 输出一致)
2. `restore_backup` 用 `call_command('loaddata', db_file)` 替代 `cursor.execute(f.read())`
   - 对称 create 的 dumpdata (Django 标准对称命令对)
   - 安全: loaddata 解析 JSON, 非 JSON 内容触发 DeserializationError, 不会执行任意代码
3. 删除 `from django.db import connection` 导入 (不再需要)
4. 新建 `backend/tasks/tests/test_backup_restore.py` 6 个测试:
   - `test_create_backup_returns_zip` — create 返回 ZIP 含 database.json + backup_info.json
   - `test_restore_backup_round_trip` — create → restore round-trip 成功
   - `test_restore_backup_rejects_malicious_sql` — 恶意 SQL 内容被 loaddata 拒绝 (500, 非执行)
   - `test_restore_backup_missing_db_file` — 缺 database.json 时跳过 restore 返回 200
   - `test_restore_backup_rejects_non_zip` — 非 ZIP 上传返回 400
   - `test_no_cursor_execute_in_backup_views` — 源码回归守卫 (grep 验证生产代码无 cursor.execute + 无 database.sql)

## 防错机制 (Y/N 检查清单)

新增/修改备份恢复功能时必跑:
- ❌ create 用 dumpdata 但 restore 用 cursor.execute → ✅ create/restore 对称 (dumpdata/loaddata)
- ❌ 文件名 .sql 但内容是 JSON → ✅ 文件名与内容格式一致 (.json)
- ❌ restore 路径无单测 → ✅ 至少 1 个 round-trip 测试 + 1 个恶意输入拒绝测试
- ❌ cursor.execute 执行用户上传内容 → ✅ 用 Django 管理 command (loaddata) 替代
- ❌ 备份功能无源码回归守卫 → ✅ grep 验证生产代码无危险模式

## 验证

- [x] backup_views.py 生产代码无 `cursor.execute` (grep 验证仅命中注释)
- [x] backup_views.py 生产代码无 `database.sql` (grep 验证仅命中注释)
- [x] test_backup_restore.py 6 tests pass
- [x] `ruff check backend/tasks/backup_views.py backend/tasks/tests/test_backup_restore.py` 0 errors
- [x] active.md TD-216 标记 ✅ FIXED
- [x] failure-modes.md N168 索引行已追加
- [x] 本 lesson 已创建 (L1 4 层分发)

## 关联

- **N167 七维度评估** — 本修复用七维度评分自决 (方案 B 20/21, 维度 2/4/6/7 满分)
- **N151 大修改架构视角** — P0 安全漏洞 + 双套反模式, 走架构视角判定 (拒绝"最小化修补", 走"对称归一")
- **N166 L3 循环** — 本问题由 L3-1 ③ 架构层扫描发现, 验证 L3 持续评估价值
- **§2.0 三原则** — 同时违反扩展性 (restore 无法扩展) + 逻辑正确性 (cursor.execute JSON 失败) + 命名正确性 (.sql 文件名)
