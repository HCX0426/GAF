# Problem: 技能/规则双份维护漂移 — .trae/ 被 Trae IDE 独占

## 现象
1. **`.trae/` 被 Trae IDE 独占**: 技能 (skills/) 与规则 (rules/) 目录被绑定到 `.trae` 名字, opencode 等其它 IDE 无任何入口, 技能体系不可移植。
2. **双份维护漂移**: 若为每个 IDE 各放一份 skills/rules, 两处内容必然漂移, 规则/技能更新无法保证同步生效。
3. **路径铁律冲突**: 文档内部引用技能/规则时写入 `.trae/...` 或绝对路径, 违反"禁止 IDE 目录名"铁律, 且 IDE 迁移后全部引用失效。

## 影响范围
- `.trae/skills/` + `.trae/rules/` 全部技能与规则文件 (5 skills + 1 rule + 1 索引)
- 全仓库文档 (2415 个 markdown 文件) 中的 `.trae/` 引用
- opencode 等非 Trae IDE 的入口配置 (opencode.json)