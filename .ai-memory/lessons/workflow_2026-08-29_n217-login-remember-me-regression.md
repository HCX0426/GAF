---
date: 2026-08-29
symptom: [login-remember-me-broken, form-item-indirect-child, login-not-persisted, base-flow-regression-blindspot, antd-checkbox-detached]
solution: 跨功能迭代时把"用户高频基础流程"（登录/注册/鉴权恢复）纳入每轮回归清单；antd Form.Item 直接子元素必须是受控组件（含 name + valuePropName 的 Checkbox/Input），否则 value/onChange 不注入该组件，UI 显示与表单值脱节
related_files:
  - frontend/src/pages/Login/index.tsx
  - frontend/src/utils/tokenStore.ts
  - frontend/src/api/auth.ts
created_by: AI
priority: high
n_id: N217
diff_keywords: ["remember_me", "getRememberMeDefault", "Form.Item", "valuePropName", "login", "记住我"]
---

# 登录"记住我"失效：基础流程回归盲区 + antd Form.Item 间接子元素坑

## 症状（2026-08-29, 用户反馈"不是可以记住账号吗，为啥每次都要登录"）

连续多轮迭代（服务管理/日志收口/通知中心）期间，用户每次打开浏览器都要重新登录，勾选"记住我"也不生效。排查发现两个叠加根因：

1. **默认未勾选**：`remember_me` 默认 `false` → refresh token 存 sessionStorage → 浏览器关闭即丢 → 每次重登。用户不手动勾选就等于没有免登录。
2. **更隐蔽**：登录页 `<Form.Item name="remember_me" valuePropName="checked">` 的直接子元素是 `<div>`（内嵌 Checkbox + 忘记密码按钮），antd 的 `value/onChange` 只注入**直接子元素**，`<div>` 收不到，Checkbox 实际不受表单控制 → **UI 勾选状态与表单值脱节**（表单提交值 true，界面显示未勾选，反之亦然）。排查时看到"函数返回 true 但页面不勾选"的矛盾现象，绕了 vite 缓存/antd 渲染等弯路才定位。

## 根因

1. **回归盲区**：GAF 每轮 spec 都聚焦"新功能/被检出的问题"，没有任何机制周期性检查**用户高频基础流程**（登录/记住我/鉴权恢复）。这类流程一旦被历史改动悄悄破坏（或从未验证过），几轮迭代无人察觉。N135 要求"重构后浏览器实测登录"，但只覆盖"能登录"，没覆盖"记住我持久化/免登录恢复"。
2. **antd Form 原理**：`Form.Item` 通过 cloneElement 把 `value/onChange` 注入**直接子元素**。若直接子元素是非受控容器（div/span），受控组件（Checkbox）就不在表单管辖内。正确写法是受控组件本身做 Form.Item 直接子元素，或用字段包一层。

## 解决方案

1. **修复（commit e004db3）**：
   - `tokenStore.getRememberMeDefault()`：首次访问（无 stored flag）默认 `true` → refresh token 落 localStorage → 30 天免登录。
   - `apiLogin/login2FA` 无条件 `setRememberMe(data.remember_me ?? false)`（显式取消也要持久化，避免旧 '1' 残留）。
   - Checkbox 改为 `Form.Item` 直接子元素 + `initialValue={getRememberMeDefault()}`：`<Form.Item name="remember_me" valuePropName="checked" initialValue={...}><Checkbox>...</Checkbox></Form.Item>`，布局用外层 div 包住 Form.Item 与按钮。
   - 单测断言更新：默认提交 remember_me=true。
2. **防回归**：把"登录 → 勾选记住我 → 关浏览器重开 → 自动进主界面"加入每轮功能回归手测清单；vitest 增加默认值断言。
3. **排查方法论**：遇到"运行时代码返回正确、UI 不反映"的矛盾，优先怀疑 **UI 层绑定**（Form 注入/事件绑定/受控性），而非数据层——先检查直接子元素是否是受控组件。

## 验证

- tsc 0 / vitest Login 4 passed
- 浏览器实测：登录勾选 → localStorage 写入 remember_me='1' + refresh_token → 清空 sessionStorage（模拟浏览器重启）→ 刷新直接进 dashboard，无需重新输入
- 修复后 checkbox 初始勾选（`ant-checkbox-checked` class 存在）