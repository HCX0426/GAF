# 中文 Commit Message 规范

> 本文档从 `chinese-git-workflow/SKILL.md` 提取，包含约定式提交（Conventional Commits）中文版的类型清单、好/坏示例。

## 约定式提交（Conventional Commits）中文版

```
<类型>(<范围>): <简要描述>
                                    ← 空行
<正文（可选）>
                                    ← 空行
<脚注（可选）>
```

## 类型清单

| 类型 | 说明 | emoji（可选） |
|------|------|--------------|
| feat | 新增功能 | ✨ |
| fix | 修复 Bug | 🐛 |
| docs | 文档更新 | 📝 |
| style | 代码格式（不影响逻辑） | 💄 |
| refactor | 重构（不是新功能也不是修 Bug） | ♻️ |
| perf | 性能优化 | ⚡ |
| test | 测试相关 | ✅ |
| build | 构建系统或外部依赖 | 📦 |
| ci | CI/CD 配置 | 👷 |
| chore | 其他杂项 | 🔧 |
| revert | 回滚 | ⏪ |

## 好的 commit message

```
feat(购物车): 支持批量删除商品

- 新增全选/反选功能
- 删除操作增加二次确认弹窗
- 批量删除接口使用 POST /cart/batch-delete

关联需求：TAPD-12345
```

```
fix(支付): 修复微信支付在 iOS 16 上无法唤起的问题

原因：微信 SDK 8.0.33 版本在 iOS 16 上 Universal Links 校验逻辑变更，
导致 openURL 回调失败。

方案：升级 SDK 至 8.0.38，并更新 Associated Domains 配置。

Closes #567
```

## 不好的 commit message

```
# 太笼统
update code
fix bug
修改了一些东西

# 没有上下文
fix: 修复问题
feat: 新增功能

# 中英混杂无规范
fix：修复了一个bug，因为user login的时候会crash
```
