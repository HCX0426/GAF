# Coding.net 平台配置

> 本文档从 `chinese-git-workflow/SKILL.md` 提取，包含 Coding.net 的远程仓库（HTTPS/SSH）配置以及 Coding CI（Jenkinsfile 语法）流水线配置。

## 远程仓库配置

```bash
# Coding 的仓库地址格式
git remote add origin https://e.coding.net/<team>/<project>/<repo>.git

# Coding 支持的 SSH 地址
git remote add origin git@e.coding.net:<team>/<project>/<repo>.git
```

## Coding CI（Jenkinsfile 语法）

```groovy
// Jenkinsfile（Coding CI 支持 Jenkinsfile 语法）
pipeline {
    agent any

    stages {
        stage('安装依赖') {
            steps {
                sh 'npm ci'
            }
        }

        stage('单元测试') {
            steps {
                sh 'npm test'
            }
        }

        stage('构建') {
            steps {
                sh 'npm run build'
            }
        }

        stage('部署到测试环境') {
            when {
                branch 'dev'
            }
            steps {
                sh './scripts/deploy-staging.sh'
            }
        }

        stage('部署到生产环境') {
            when {
                branch 'main'
            }
            steps {
                sh './scripts/deploy-production.sh'
            }
        }
    }

    post {
        failure {
            // 企业微信/钉钉通知
            sh './scripts/notify-failure.sh'
        }
    }
}
```
