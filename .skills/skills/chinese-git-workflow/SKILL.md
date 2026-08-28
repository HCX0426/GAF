---
name: chinese-git-workflow
description: 国内 Git 平台配置参考——Gitee、Coding.net、极狐 GitLab、CNB 的 SSH/HTTPS/凭据/CI 接入差异与镜像同步配置。仅在用户显式 /chinese-git-workflow 时调用，不要根据上下文自动触发。
version: "1.0.0"
license: MIT
metadata:
  hermes:
    tags: [git, chinese]
---

# 国内 Git 工作流规范

## 概述

国内团队用 Git 经常踩的坑：GitHub 访问不稳定、CI/CD 方案照搬国外水土不服、commit message 中英混杂没有规范。本技能提供一套**完整适配国内平台和团队习惯的 Git 工作流**。

**核心原则：** 工作流服务于团队效率，不是为了流程而流程。选适合团队规模的，别硬套大厂方案。

## 国内 Git 平台适配

### 平台对比

| 特性 | Gitee | Coding.net | 极狐 GitLab | CNB | GitHub |
|------|-------|------------|-------------|-----|--------|
| 国内访问 | 快 | 快 | 快 | 快 | 不稳定 |
| 免费私有仓库 | 有 | 有 | 有 | 有 | 有 |
| CI/CD | Gitee Go | Coding CI | 内置 GitLab CI | 内置（.cnb.yml） | GitHub Actions |
| 代码审查 | PR | MR | MR | MR | PR |
| 制品库 | 有限 | 完整 | 完整 | 完整 | Packages |
| 适合场景 | 开源/小团队 | 中大型团队 | 企业私有化 | 云原生 / Docker 流水线 | 国际项目 |

### 各平台 SSH/HTTPS/凭据/CI 配置

每个平台的远程仓库地址、SSH/HTTPS 认证、CI/CD 流水线配置差异较大，详细配置见对应平台文件：

> Gitee 配置（远程仓库 + SSH + 镜像同步 + Gitee Go）：见 `platforms/gitee.md`

> Coding.net 配置（远程仓库 + SSH + Coding CI Jenkinsfile）：见 `platforms/coding.md`

> 极狐 GitLab 配置（jihulab / 企业内部部署 + GitLab CI）：见 `platforms/gitlab-jihu.md`

> CNB 配置（仅 HTTPS + Access Token + .cnb.yml）：见 `platforms/cnb.md`

**关键差异速查：**
- Gitee：支持 SSH，可镜像同步到 GitHub
- Coding.net：支持 HTTPS 和 SSH，CI 用 Jenkinsfile 语法
- 极狐 GitLab：支持私有化部署，CI 用 .gitlab-ci.yml
- CNB：**仅支持 HTTPS**（无 SSH），用户名固定为 `cnb`，密码为 Access Token

## CI/CD 平台适配

各平台 CI/CD 详细配置见上方 `platforms/` 目录对应文件。

### GitHub Actions 国内替代方案对照

| GitHub Actions 功能 | Gitee Go | Coding CI | 极狐 GitLab CI | CNB |
|---------------------|----------|-----------|----------------|-----|
| 触发条件 | triggers | Jenkinsfile triggers | only/rules | push / pull_request |
| 缓存依赖 | cache step | stash/unstash | cache | 见官方文档 |
| 制品存储 | artifacts | 制品库 | artifacts | 见官方文档 |
| 环境变量 | env | environment | variables | env |
| 密钥管理 | 环境变量配置 | 凭据管理 | CI/CD Variables | Access Token |
| 手动触发 | 手动运行 | 手动触发 | when: manual | 页面手动运行 |

## 工作流选择与分支命名

三种国内团队常用工作流模式（主干开发 / Git Flow / 简化流程）以及分支命名规范属于详细参考材料。

> 工作流模式图解、规则与分支命名规范：见 `reference/workflow-and-branching.md`

**快速选择建议：**
- 小团队（2-8 人）+ 快速迭代 → 主干开发（Trunk-Based）
- 中大团队 + 固定版本发布节奏 → Git Flow
- 大多数国内中小团队 → 简化流程（main 受保护 + dev 测试环境）

**分支命名核心规则：** 全小写 + `-` 连接 + 类型前缀（`feat/`、`fix/`、`hotfix/`、`release/`）+ 可选任务编号（如 `feat/TAPD-12345-description`）

## 中文 Commit Message 规范

约定式提交（Conventional Commits）中文版的类型清单、好/坏示例属于详细参考材料。

> 类型清单（feat/fix/docs/refactor 等）与示例：见 `reference/commit-message.md`

**核心格式：**
```
<类型>(<范围>): <简要描述>

<正文（可选）>

<脚注（可选）>
```

**关键要求：** 类型准确、范围明确、描述具体、关联任务编号（TAPD/JIRA 等）。

## PR/MR 描述模板

各平台 PR/MR 模板文件路径与中文模板内容属于详细参考材料。

> PR/MR 中文模板（变更说明/类型/测试情况/影响范围/部署注意事项）：见 `reference/pr-mr-templates.md`

**模板文件位置：**
- Gitee：`.gitee/PULL_REQUEST_TEMPLATE.md`
- Coding / GitLab：`.gitlab/merge_request_templates/default.md`

## 常用 Git 配置

国内环境下的 Git 全局配置优化（中文文件名、代理、镜像源）以及 .gitignore 国内项目常见配置属于详细参考材料。

> 国内环境优化配置与 .gitignore 模板：见 `reference/common-config.md`

**关键配置项：**
- `core.quotepath false` — 解决中文文件名显示为转义字符
- `init.defaultBranch main` — 设置默认分支名
- NPM 国内镜像：`https://registry.npmmirror.com`

## 检查清单

在推送代码前，确认：

- [ ] 分支命名符合团队规范
- [ ] commit message 格式正确，类型和范围准确
- [ ] 关联了对应的需求/Bug 编号
- [ ] PR/MR 描述填写完整
- [ ] CI 流水线通过
- [ ] 已请求相关同事 Review
