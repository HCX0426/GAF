# 工作流选择与分支命名规范

> 本文档从 `chinese-git-workflow/SKILL.md` 提取，包含三种国内团队常用的 Git 工作流模式（主干开发、Git Flow、简化流程）以及分支命名规范。

## 工作流选择

### 方案一：主干开发（Trunk-Based Development）

**适合：** 小团队（2-8 人）、迭代速度快、有完善的自动化测试。

```
main ──●──●──●──●──●──●──●──●──●──
        \   /  \   /       \   /
feat/x  ●─●   ●─●    fix/y ●─●
（短命分支，1-2 天内合回）
```

**规则：**
- 主干（main）始终保持可发布状态
- 功能分支生命周期不超过 2 天
- 每天至少合并一次到主干
- 用 Feature Flag 控制未完成功能的可见性

```bash
# 从 main 拉分支
git checkout -b feat/user-login main

# 开发完成后，rebase 到最新 main
git fetch origin
git rebase origin/main

# 提交 PR/MR，合并后删除分支
```

### 方案二：Git Flow（经典分支模型）

**适合：** 中大团队、版本发布节奏固定（如双周迭代）、需要维护多个版本。

```
main     ──●────────────────●────────────── 生产环境
            \              / \
release     ●──●──●──●──●    ●──●──●──●── 发布分支
            \              /
develop  ──●──●──●──●──●──●──●──●──●──●── 开发主线
             \   /  \       /
feat/x       ●─●    ●─────●               功能分支
                      \   /
                  fix/y ●─●                修复分支
```

**分支说明：**
- `main` — 生产环境代码，只接受 release 和 hotfix 的合并
- `develop` — 开发主线，功能分支从这里拉出，合回这里
- `release/*` — 发布分支，从 develop 拉出，只修 bug 不加功能
- `feat/*` — 功能分支
- `hotfix/*` — 紧急修复，从 main 拉出，同时合回 main 和 develop

### 方案三：国内团队常用简化流程

**适合：** 大多数国内中小团队的实际情况。

```
main     ──●──────●──────●──── 生产环境（受保护）
            \    / \    /
dev      ──●──●─●──●──●─●──── 开发/测试环境
             \  /    \  /
feat/x       ●●      ●●       功能分支
```

**规则：**
- `main` 分支受保护，只能通过 PR/MR 合并
- `dev` 分支对应测试环境，自动部署
- 功能分支从 `dev` 拉出，合回 `dev`
- `dev` 测试通过后，合并到 `main` 进行发布

## 分支命名规范

### 国内团队常用命名

```bash
# 功能分支
feat/user-login              # 新功能
feat/JIRA-1234-order-refund  # 关联任务编号

# 修复分支
fix/payment-callback         # Bug 修复
fix/JIRA-5678-null-pointer   # 关联 Bug 编号

# 发布分支
release/v2.1.0               # 版本发布
release/2024-03-sprint       # 按迭代命名

# 紧急修复
hotfix/v2.0.1                # 线上紧急修复
hotfix/fix-login-crash       # 描述性命名

# 个人分支（部分团队使用）
dev/zhangsan/feat-login      # 个人开发分支
```

### 命名规则

1. 全部小写，用 `-` 连接单词（不用下划线或驼峰）
2. 前缀明确分支类型：`feat/`、`fix/`、`hotfix/`、`release/`
3. 关联任务管理平台的编号（如有）：`feat/TAPD-12345-description`
4. 长度适中，能看出分支目的即可
