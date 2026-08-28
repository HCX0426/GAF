---
summary: 账户管理 — 用户/游戏账户/分组/轮换/API Key/OAuth/2FA
applies_to: ['backend', 'frontend', 'design']
key_decisions:
  - User 三级角色 viewer/operator/admin
  - GameAccount 密码 AES-256-GCM 加密存储
  - GameAccountRotation 4 策略 sequential/random/by_stamina/by_last_executed
  - OAuth 仅支持 GitHub + Google, state nonce 防 CSRF
  - TOTP 2FA + UserSession 踢下线
last_updated: 2026-07-29
---

# 账户管理

> 模块路由 `/accounts`，对应前端侧边栏"账户"。覆盖用户管理、游戏账户管理、多账号轮换、OAuth/2FA、API Key。

## 1. 数据模型

### 1.1 User（系统用户）
- 继承 `AbstractUser`，增加字段：
  - `role`: `viewer` / `operator` / `admin`
  - `oauth_provider` / `oauth_uid`: 第三方登录标识
  - `totp_secret` / `totp_enabled`: 2FA
  - `must_change_password`: 首次登录强制改密
- 反向关联：`game_accounts` / `account_groups` / `api_keys` / `login_history` / `sessions` / `audit_logs` / `rotation_rules` / `unattended_sessions`

### 1.2 GameAccount（游戏账户）
| 字段 | 用途 |
|---|---|
| `username` / `encrypted_password` | 凭证（密码 AES-256-GCM 加密） |
| `game_profile` | FK → `gamestate.GameProfile` |
| `login_method` | `password` / `qr_scan` / `token` / `steam` |
| `status` | `unknown`（默认）/ `ok` / `warn` / `error` |
| `group` | FK → `GameAccountGroup` |
| `resource_pack` | FK → `resources.ResourcePack` |
| `last_login_at` / `login_count` / `execution_count` | 统计 |
| `owner` | FK → User（unique_together: owner + game_name + username） |

### 1.3 GameAccountGroup（分组）
- 字段：`name` / `slug`（unique_together: owner + slug）
- 预设分组：Main / Alt / Farm / Event

### 1.4 GameAccountRotation（轮换规则）
> 定义于 [scheduler/models.py](file:///d:/code/GAF/backend/scheduler/models.py#L4)，不在 accounts app

| 策略 | 含义 |
|---|---|
| `sequential` | 顺序循环 A→B→C→A（默认） |
| `random` | 随机选 |
| `by_stamina` | 体力多的优先 |
| `by_last_executed` | LRU 最久未执行优先 |

字段：`accounts` (M2M) / `switch_interval_seconds` (默认 10) / `auto_skip_blocked` (默认 True)

### 1.5 其他模型
- **APIKey**: `key_hash` / `permissions` / `ip_whitelist` / `expires_at`，明文 key 仅创建时返回
- **LoginHistory**: `ip_address` / `user_agent` / `location`
- **UserSession**: `refresh_token_jti` / `device_type` / `last_activity` / `is_active`，支持踢下线
- **AuditLog**: `action` / `resource_type` / `resource_id` / `details` (JSON)

## 2. API 端点

前缀 `/api/v2/accounts/`，详见 [accounts/urls.py](file:///d:/code/GAF/backend/accounts/urls.py)。

### 2.1 认证（`auth/`）
| 路径 | 方法 | 用途 |
|---|---|---|
| `auth/login/` | POST | JWT 登录（注入 session_jti） |
| `auth/refresh/` / `auth/logout/` | POST | 刷新 / 拉黑 token |
| `auth/register/` | POST | 注册 |
| `auth/change-password/` | PUT | 改密 |
| `auth/password-reset/` / `auth/password-reset/confirm/` | POST | 密码重置 |
| `auth/login-2fa/` | POST | TOTP 二次校验 |
| `auth/2fa/setup/` / `auth/2fa/verify-setup/` / `auth/2fa/disable/` | POST | 2FA 管理 |
| `auth/sessions/` | GET | 活跃会话列表 |
| `auth/sessions/<pk>/` | DELETE | 踢下线 |
| `auth/sessions/logout-all-others/` | POST | 批量踢下线 |
| `auth/agent-tokens/` | GET/POST | Agent Token CRUD |

### 2.2 OAuth（`auth/oauth/`）
- `github/` + `github/callback/` — GitHub OAuth（scope: `read:user user:email`）
- `google/` + `google/callback/` — Google OAuth（scope: `openid email profile`）
- state nonce 防 login CSRF，回调后签 JWT 通过 URL fragment 传到前端

### 2.3 资源 ViewSet
| 路径 | 用途 |
|---|---|
| `users/` / `users/me/` / `users/<pk>/reset-password/` | 用户 CRUD（仅 admin） |
| `game-accounts/` | 游戏账户 CRUD |
| `game-accounts/game-options/` | 游戏列表（从 GameProfile） |
| `game-accounts/<pk>/test-login/` | 测试登录（指定在线设备） |
| `game-accounts/batch-check/` | 批量状态检测 |
| `game-accounts/batch-import/` | CSV/TXT 批量导入 |
| `game-accounts/<pk>/bind-resource/` | 绑定资源包 |
| `groups/` | 分组 CRUD |
| `rotation-rules/` | 轮换规则 CRUD |
| `api-keys/` | API Key CRUD（仅 manage） |
| `login-history/` / `login-history/all/` | 登录历史 |
| `audit-logs/` | 审计日志只读 |

## 3. 凭证加密

文件：[accounts/crypto.py](file:///d:/code/GAF/backend/accounts/crypto.py)

- **算法**: AES-256-GCM（认证加密）
- **密钥派生**: PBKDF2-HMAC-SHA256，输入 `SECRET_KEY`，salt=`b"gaf_v2_game_account_encryption_salt"`，iterations=100000
- **Nonce**: 每次加密 `os.urandom(12)`
- **存储格式**: `base64(nonce):base64(ciphertext+tag)`
- **API**: `encrypt_password(plaintext)` / `decrypt_password(encrypted)`（失败抛 `DecryptionError`）

## 4. 前端页面

目录：[frontend/src/pages/Accounts/](file:///d:/code/GAF/frontend/src/pages/Accounts/)

| 组件 | 用途 |
|---|---|
| `GameAccountsPage.tsx` | 主页面：账户列表 + 7 个工具栏按钮 |
| `GameAccountEditor.tsx` | 账户创建/编辑 Modal |
| `UserManagePage.tsx` | 用户管理（独立页） |
| `AccountAutoHandler.tsx` | 异常自动处理配置（autoRemove/inAppNotify/trayNotify） |
| `AccountBatchChecker.tsx` | 批量检测 Modal（selected/all 模式） |
| `AccountBatchImport.tsx` | 批量导入两步式（CSV 上传 → 预览确认） |
| `AccountGroupManager.tsx` | 分组管理 Drawer（拖拽分配） |
| `AccountLoginTester.tsx` | 登录测试 Modal（选设备 → testing → success/error） |
| `AccountRotationRules.tsx` | 轮换规则 CRUD |
| `AccountStatusPanel.tsx` | 状态面板 Drawer（30s 自动刷新） |

## 5. OAuth 安全机制

- **state nonce**: session 存 `oauth_state_<provider>`，回调时 `secrets.compare_digest` 比对，消费后不可重放
- **email_verified 限制**: 仅当 provider 返回 verified email 时才允许绑定现有本地账号（防接管）
- **统一会话建立**: `_post_login_setup` 镜像密码登录流程 — 签 RefreshToken + 注入 session_jti + 创建 UserSession + 写 LoginHistory
- **用户创建策略**: 按 (provider, oauth_uid) → verified email → 新建（默认 viewer 角色）
- **JWT 传递**: URL fragment（`#access=...`），不会发送到服务端，减少泄漏到 referrer/log

## 6. 已知限制

- 前端 `AccountRotationRules.tsx` 策略选项为 `sequential/random/weighted`，与后端 `sequential/random/by_stamina/by_last_executed` 不完全对齐（`weighted` 后端不存在，`by_stamina/by_last_executed` 前端未暴露）
- `GameAccount.game_name` 字段已废弃（TD-259 #23），保留兼容
