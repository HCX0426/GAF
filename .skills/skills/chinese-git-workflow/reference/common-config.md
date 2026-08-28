# 常用 Git 配置

> 本文档从 `chinese-git-workflow/SKILL.md` 提取，包含国内环境下的 Git 全局配置优化以及 .gitignore 国内项目常见配置。

## 国内环境优化

```bash
# 设置用户信息
git config --global user.name "张三"
git config --global user.email "zhangsan@company.com"

# commit message 编辑器设置为 VS Code
git config --global core.editor "code --wait"

# 解决中文文件名显示为转义字符的问题
git config --global core.quotepath false

# 设置默认分支名
git config --global init.defaultBranch main

# 代理设置（如果需要同时使用 GitHub）
git config --global http.https://github.com.proxy socks5://127.0.0.1:7890

# NPM 使用国内镜像
npm config set registry https://registry.npmmirror.com
```

## .gitignore 国内项目常见配置

```gitignore
# IDE
.idea/
.vscode/
*.swp

# 依赖
node_modules/
vendor/

# 构建产物
dist/
build/
*.exe

# 环境配置
.env
.env.local
.env.*.local

# 系统文件
.DS_Store
Thumbs.db
desktop.ini

# 国内平台特有
.coding/
```
