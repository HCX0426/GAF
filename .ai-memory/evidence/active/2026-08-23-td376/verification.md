# TD-376 verification

- **代码实证**: `scripts/hooks/check_claimed_rules.py:321-351` `check_unclosed_review` 已实现重估逻辑 (`check_review_trigger` 调用, 陈旧标记返回 0, 真实触发返回 1), 函数 docstring 标注 `TD-376 (2026-08-20)`。
- **测试实证**: `pytest scripts/tests/test_check_claimed_rules.py` 含 TD-376 相关断言 (line 340/352/364); 该测试文件此前 29 passed (TD-383 修复时), 重估逻辑稳定。
- **结论**: TD-376 修复已落地 (hook 强制 + 触发条件重估 + 陈旧标记自然闭环); 仅 debt 登记状态由 🔧 待修迁 ✅ FIXED。无需新代码改动。
