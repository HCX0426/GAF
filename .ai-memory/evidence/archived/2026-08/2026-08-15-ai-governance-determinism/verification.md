# Verification: 3 机制验证

## M1 代码铁律 (check_code_rules.py)
- ruff: All checks passed (check_code_rules.py + test_check_code_rules.py)
- pytest: 15 passed (含 5 条规则正反例 + diff 行过滤 + --no-fail + SyntaxError 跳过)
- 端到端: `git add backend/evil/demo.py` (裸 except) → pre-commit run gaf-code-rules → Failed
  (exit 1, R001 命中); 正常文件 → Passed
- 测试文件已清理 (backend/ 恢复, git status 0 changes)

## M3 diff 触发检索 (match_lessons_by_diff.py)
- ruff: All checks passed
- pytest: 9 passed (parser/load/score/main)
- 端到端: staged 含 `# sql-injection: never use f-string in cursor.execute` +
  `cursor.execute(...)` 的临时文件 → 命中 `archived-early/N168-backup-restore-security-fix.md`
  (kw=sql-injection,cursor.execute, +6)
- 真实 commit 回测: `--base HEAD~1 --head HEAD` 对 Phase 1 commit → 命中 N150/N112/N168
- check_lessons_updated.py: 143 lessons validated (回填后仍绿)

## M2 声称-激活率 (check_claimed_rules.py)
- ruff: All checks passed
- pytest: 9 passed
- 回测 commit - (声称 N197 + body 引用 N150/N157/N195/N196):
  声称 5 条, positive=4 (N150/N157/N195/N196), unknowable=1 (N197), 正向激活率 80%
- 记录文件正确生成 claimed-activation.md (幂等 + 首次建表)

## 全量钩子
- pre-commit run: 全部 Passed (governance batch / M1 code-rules / auto-archive /
  B2 evidence / spec-context / spec_id / evidence completeness / git-status)
- 3 次提交均正常走 hooks: - / - / -

## 已知观察项 (未处理, 非本次范围)
- 15 个 lesson 存在 root + archived-early 双副本 (- 迁移事故造成,
  root 为权威; 本次只回填 root 副本 + N168 归档副本)
- 18 个 pytest 失败为环境/数据相关, 在干净 HEAD 上同样失败 (非本次改动引起)