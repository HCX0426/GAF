# CNB（Cloud Native Build）平台配置

> 本文档从 `chinese-git-workflow/SKILL.md` 提取，包含 CNB 的远程仓库（仅 HTTPS）、凭据配置以及 .cnb.yml 流水线配置。

## 远程仓库与凭据配置

```bash
# CNB 仓库地址（仅支持 HTTPS，不提供 SSH 协议）
git remote add origin https://cnb.cool/<org>/<repo>.git

# HTTPS 认证：用户名固定为 cnb，密码为个人访问令牌（Access Token）
# 在 CNB 平台 → 个人设置 → 访问令牌 中生成
git config credential.helper store
```

## CNB CI（.cnb.yml）

```yaml
# .cnb.yml — branch-first 结构，直接指定 Docker 镜像跑流水线
main:
  push:
    - docker:
        image: node:20
      stages:
        - npm ci
        - npm test
        - npm run build
  pull_request:
    - docker:
        image: node:20
      stages:
        - npm run lint
        - npm test
```

**特点：**
- 每个流水线独立指定 Docker 镜像，天然云原生
- 支持 `push` / `pull_request` 触发
- 同一事件可并行多条流水线
- `stages` 也支持 `- name: xxx` + `script:` 的展开形式，复杂场景见官方文档
