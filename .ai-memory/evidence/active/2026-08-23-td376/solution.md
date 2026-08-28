# TD-376 solution

- **实现位置**: `scripts/hooks/check_claimed_rules.py` `check_unclosed_review(record_path)` (line 321, 函数 docstring 已标注 `TD-376 (2026-08-20)`)。
- **逻辑**: 找到最后一个 `> 🔴 REVIEW_TRIGGERED` 标记行; 其后无 `📋 复盘` 写回时, 调用 `check_review_trigger(load_records(path))` 重估触发条件是否仍成立 (TD-383 2026-08-22 增强):
  - `triggered_now == False` → 陈旧标记自然闭环, 打印 ℹ️ 且返回 0 (不阻塞)
  - `triggered_now == True` → 仍阻塞并打印 🔴, 要求按 Q1-Q4 复盘写回
- **测试覆盖**: `scripts/tests/test_check_claimed_rules.py` 已含断言 (line 340 `check_unclosed_review` 返回 0 陈旧闭环 / line 352 返回 1 真实触发阻塞 / line 364 返回 0 已闭环)。
- **结论**: TD-376 请求修复 (REVIEW_TRIGGERED 升级为 hook 强制 + 重估触发条件) 已在 `check_claimed_rules.py` 落地 (与 TD-383 同源变更), 仅 debt 状态未迁移。
