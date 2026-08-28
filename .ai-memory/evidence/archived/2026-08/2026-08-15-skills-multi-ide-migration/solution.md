# Solution: .skills/ 唯一权威源 + junction 多 IDE 接入

## 方案
1. **`.skills/` 设为唯一权威源**: skills/ + rules/ 迁移到仓库根 `.skills/`, 全部文档引用改写为 `.skills/...` 相对路径。
2. **junction 接入各 IDE**: `.trae/skills` `.trae/rules` 与 `.opencode/skills` `.opencode/rules` 均以 junction 指向 `.skills/` 下对应目录, 各 IDE 只读同一份文件, 消除漂移。
3. **opencode.json 入口**: 为 opencode 新增配置, 指向 `.skills/` 并注册 gaf-orchestrator 主 agent。
4. **历史保留**: 迁移采用 git 改名 (77 个 R 保留历史), 不复制新文件; junction 说明写入 `.skills/README.md` 与 `.trae/` 残留说明。

## 关键决策
- 引用一律相对路径, 禁止出现 IDE 目录名 (路径铁律)
- 历史记录 (lessons/ 正文、docs/ 归档) 中 `.trae` 引用作为历史叙述保留不改写, 仅修复 frontmatter 元数据 (related_files)
- junction 用 `New-Item -ItemType Junction` 创建, 非符号链接 (Windows 无需管理员权限)