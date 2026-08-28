# Gitee 平台配置

> 本文档从 `chinese-git-workflow/SKILL.md` 提取，包含 Gitee 的远程仓库、SSH、镜像同步配置以及 Gitee Go CI/CD 流水线配置。

## 远程仓库与 SSH 配置

```bash
# 设置 Gitee 远程仓库
git remote add origin https://gitee.com/<org>/<repo>.git

# Gitee 的 SSH 配置
# ~/.ssh/config
Host gitee.com
    HostName gitee.com
    User git
    IdentityFile ~/.ssh/gitee_rsa
    PreferredAuthentications publickey

# 同时推送到 Gitee 和 GitHub（镜像同步）
git remote set-url --add --push origin https://gitee.com/<org>/<repo>.git
git remote set-url --add --push origin https://github.com/<org>/<repo>.git
```

## Gitee Go CI/CD

```yaml
# .gitee/pipelines/pipeline.yml
name: 构建与测试
displayName: '构建与测试流水线'

triggers:
  push:
    branches:
      include:
        - main
        - dev

stages:
  - name: 测试
    jobs:
      - name: 单元测试
        steps:
          - step: npmbuild@1
            name: install_and_test
            displayName: '安装依赖并执行测试'
            inputs:
              nodeVersion: 20
              commands:
                - npm ci
                - npm test
```
