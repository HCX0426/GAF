# 极狐 GitLab 平台配置

> 本文档从 `chinese-git-workflow/SKILL.md` 提取，包含极狐 GitLab（jihulab.com 或企业内部部署）的远程仓库配置以及 GitLab CI 流水线配置。

## 远程仓库配置

```bash
# 极狐 GitLab 私有化部署常见地址格式
git remote add origin https://jihulab.com/<group>/<repo>.git

# 或者企业内部部署
git remote add origin https://gitlab.yourcompany.com/<group>/<repo>.git
```

## 极狐 GitLab CI

```yaml
# .gitlab-ci.yml
stages:
  - test
  - build
  - deploy

variables:
  NODE_IMAGE: node:20-alpine
  # 使用国内镜像加速
  NPM_REGISTRY: https://registry.npmmirror.com

单元测试:
  stage: test
  image: $NODE_IMAGE
  script:
    - npm config set registry $NPM_REGISTRY
    - npm ci
    - npm test
  coverage: '/Lines\s*:\s*(\d+\.?\d*)%/'

构建:
  stage: build
  image: $NODE_IMAGE
  script:
    - npm config set registry $NPM_REGISTRY
    - npm ci
    - npm run build
  artifacts:
    paths:
      - dist/

部署测试环境:
  stage: deploy
  script:
    - ./scripts/deploy-staging.sh
  only:
    - dev
  environment:
    name: staging

部署生产环境:
  stage: deploy
  script:
    - ./scripts/deploy-production.sh
  only:
    - main
  environment:
    name: production
  when: manual  # 生产环境手动触发
```
