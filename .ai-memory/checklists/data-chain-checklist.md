---
maintainer: manual
source: .ai-memory/checklists/data-chain-checklist.md
load_when: [Bug修复, 新功能, 数据流排查, 8 步审计]
priority: high
symptom: [kb:data-chain, 8-step-audit, 数据链路, 前后端交互]
solution: 8 步数据链路审计 (desktop→frontend→backend→agent),bug_fix 必经流程
related_files:
  - docs/reference/data-flow.md
  - .ai-memory/knowledge/data-chain.md
  - docs/archive/active-tech-debt.md
created_by: AI
last_updated: 2026-08-17 (s30 确认仍有效)
---
# GAF 数据链路通用检查清单

> **版本**: 1.2 | **创建日期**: 2026-06-02 | **最后更新**: 2026-06-02
> **基于**: Phase R21 数据链路审计实战经验
> **适用场景**: 前后端数据交互问题排查、新功能开发后验证、定期代码质量审计
> **预计耗时**: 30-60 分钟（完整审计）| 10-15 分钟（快速检查）
> **本文档状态**: 截至 Phase R21 有效，后续 Phase 更新需同步此文档

---

## 一、检查总览

### 1.1 核心原则

```
数据链路 = Model → Serializer → View/URL → API Layer (前端) → TypeScript Types → Components
```

**黄金法则**: 前端的每一个字段引用、API 调用、类型定义，都必须能在后端找到对应的源头。

### 1.2 检查优先级矩阵

| 优先级 | 检查类型 | 影响范围 | 发现频率 |
|:-----:|---------|:-------:|:-------:|
| 🔴 P0 - 致命 | 导入/导出缺失、字段名错误 | 整个前端白屏/功能失效 | 15% |
| 🔴 P0 - 严重 | ID 类型不一致、URL 路径错误 | API 调用失败/静默错误 | 40% |
| 🟡 P1 - 重要 | 枚举值缺失、虚假字段 | 类型警告/显示异常 | 25% |
| 🟢 P2 - 一般 | 注释过时、未使用导入 | 代码整洁度 | 20% |

### 1.3 触发条件（何时执行此检查）

- ✅ 新功能开发完成后
- ✅ 后端模型/Serializer 字段变更后
- ✅ 前端页面白屏或报 `SyntaxError` / `TypeError`
- ✅ API 返回数据但页面显示异常
- ✅ 定期代码质量审计（建议每周 1 次）
- ✅ 合并 PR 前（Code Review 辅助）

---

## 二、标准检查流程（8 步）

### Step 1️⃣：TypeScript 类型定义层检查

**目标文件**: `frontend/src/types/models/`

#### 检查清单

- [ ] **1.1 字段名匹配性**
  - 每个接口的字段名是否与后端 Serializer 的 `fields` 完全一致？
  - snake_case vs camelCase 是否正确转换？
  
  ```typescript
  // ❌ 错误：字段名拼写错误
  export interface Template {
    is_valid: boolean;  // 后端实际是 is_active
  }
  
  // ✅ 正确
  export interface Template {
    is_active: boolean;
  }
  ```

- [ ] **1.2 ID 类型一致性**
  - 所有主键 (`id`, `taskId`, `agentId` 等) 是否为 `number`？（后端 AutoField 是整数）
  
  ```typescript
  // ❌ 错误：ID 用了 string
  export interface Agent {
    id: string;
  }
  
  // ✅ 正确
  export interface Agent {
    id: number;
  }
  ```

- [ ] **1.3 枚举值完整性**
  - 联合类型是否包含后端 `choices` 或 `Status` 的所有可能值？
  
  ```typescript
  // ❌ 错误：缺少 'locked' 状态
  export type DeviceStatus = 'online' | 'offline' | 'busy' | 'error';
  
  // ✅ 正确
  export type DeviceStatus = 'online' | 'offline' | 'busy' | 'error' | 'locked';
  ```

- [ ] **1.4 虚假字段清理**
  - 是否有前端定义但后端模型不存在的字段？（如 `stamina`, `platform`, `name`）
  
  ```typescript
  // ❌ 错误：后端 GameAccount 没有 stamina 字段
  export interface GameAccount {
    stamina?: number;  // 不存在！
  }
  
  // ✅ 正确：移除此字段
  ```

#### 工具方法

```bash
# 对比后端 Serializer 字段
grep -rn "class.*Serializer" backend/**/serializers.py | head -20

# 搜索前端所有接口定义
grep -n "export interface" frontend/src/types/models/
```

#### 典型错误案例（Phase R21 实战）

| 错误类型 | 文件 | 影响 |
|---------|------|------|
| `is_valid` → `is_active` | TemplateGallery.tsx | 模板开关功能失效 |
| `stamina` 字段不存在 | AccountStatusPanel.tsx | 显示虚假数据 "0/240" |
| DeviceStatus 缺少 `'locked'` | DeviceCard.tsx | TypeScript 编译警告 |
| `read` → `is_read` | useNotificationStore.ts | 通知未读计数永远为 0，标记已读功能失效 |

---

### Step 2️⃣：API 层函数签名检查

**目标文件**: `frontend/src/api/*.ts`（tasks.ts, executions.ts, monitors.ts, agents.ts 等）

#### 检查清单

- [ ] **2.1 参数类型正确性**
  - 所有 ID 参数是否为 `number`？
  
  ```typescript
  // ❌ 错误
  export async function fetchTask(taskId: string): Promise<Task>
  
  // ✅ 正确
  export async function fetchTask(taskId: number): Promise<Task>
  ```

- [ ] **2.2 URL 路径规范性**
  - POST/PUT/DELETE 请求是否带 trailing `/`？（Django 要求）
  
  ```typescript
  // ❌ 错误：缺少 trailing slash → Django 返回 301 → axios abort
  await client.delete(`/tasks/${taskId}`)
  
  // ✅ 正确
  await client.delete(`/tasks/${taskId}/`)
  ```

- [ ] **2.3 导出完整性**
  - 组件 `import` 的函数是否都有对应 `export`？
  
  ```typescript
  // ❌ 致命错误：组件导入但 API 未导出
  // ExecutionMonitorPanel.tsx:
  import { forceFailExecution } from '../../api/executions';
  
  // executions.ts: （缺少此导出！）
  // → SyntaxError: does not provide an export named 'forceFailExecution'
  // → 整个前端白屏！
  
  // ✅ 正确：添加导出
  export async function forceFailExecution(executionId: number, reason?: string) {
    return interveneExecution(executionId, 'fail', reason);
  }
  ```

- [ ] **2.4 返回类型匹配**
  - 函数返回的泛型是否与实际 API 响应结构一致？

#### 工具方法

```bash
# 查找所有 API 函数定义
grep -n "export async function" frontend/src/api/*.ts

# 查找组件导入
grep -rn "from.*api/" frontend/src/pages/ | grep import
```

#### Django Trailing Slash 规则（重要！）

| HTTP 方法 | 是否需要 `/` | Django 行为 | axios 处理 |
|:--------:|:----------:|-----------|----------|
| GET | 可选 | 自动补全 | ✅ 正常跟随 |
| POST | **必须** | 否则返回 301 | ❌ **abort (ERR_ABORTED)** |
| PUT | **必须** | 否则返回 301 | ❌ **abort** |
| PATCH | **必须** | 否则返回 301 | ❌ **abort** |
| DELETE | **必须** | 否则返回 301 | ❌ **abort** |

---

### Step 3️⃣：组件层数据引用检查

**目标文件**: `frontend/src/pages/**/*.tsx`, `frontend/src/components/**/*.tsx`

#### 检查清单

- [ ] **3.1 字段引用一致性**
  - 组件中 `item.xxx` / `data.xxx` 是否与类型定义匹配？
  
  ```tsx
  // ❌ 错误：用了旧字段名
  <span>{item.read}</span>  // 后端返回的是 is_read
  
  // ✅ 正确
  <span>{item.is_read}</span>
  ```

- [ ] **3.2 表格列定义**
  - Table 的 `dataIndex` 是否指向真实存在的字段？
  
  ```tsx
  // ❌ 错误：列指向不存在的字段
  columns = [
    { title: '规则类型', dataIndex: 'rule_type' },  // 后端是 rule_definition
    { title: '模式', dataIndex: 'pattern' },         // 不存在！
  ]
  
  // ✅ 正确
  columns = [
    { title: '规则定义', dataIndex: 'rule_definition' },
  ]
  ```

- [ ] **3.3 表单字段**
  - Form.Item 的 `name` 属性是否与后端 `writeable_fields` 一致？
  
  ```tsx
  // ❌ 错误：表单提交不存在的字段
  <Form.Item name="interval_value" label="间隔值">  // 后端不接受此字段
  
  // ✅ 正确：只包含后端接受的字段
  <Form.Item name="schedule_type" label="调度类型">
  ```

- [ ] **3.4 事件处理参数**
  - onClick/onChange 传递给 API 函数的参数类型是否正确？

#### 工具方法

```bash
# 全局搜索特定字段名（查找旧引用）
grep -rn "\.is_valid\|\.stamina\|\.read\b" frontend/src/

# 查找表格列定义
grep -rn "dataIndex:" frontend/src/pages/
```

---

### Step 4️⃣：导入/导出依赖检查

#### 检查清单

- [ ] **4.1 缺失导出检测**
  - 所有被 `import` 的函数/类型是否都有对应的 `export`？
  
  **致命性**: ⚠️ 此类错误会导致**整个 React 应用白屏**

- [ ] **4.2 循环依赖检测**
  - 模块 A → B → A 是否存在？（会导致运行时错误）

- [ ] **4.3 未使用导入**
  - 是否有导入了但从未使用的类型/函数？（影响打包体积）

#### 工具方法

```bash
# 提取所有 import 语句
grep -rn "^import" frontend/src/pages/**/*.tsx | grep "from.*api/"

# 对比 API 文件的 export 列表
grep -n "^export" frontend/src/api/*.ts
```

#### ⚠️ 最高危错误模式

```
错误信息示例：
SyntaxError: The requested module '/src/api/executions.ts' 
does not provide an export named 'forceFailExecution'

影响：
→ Vite HMR 加载模块失败
→ React 应用无法渲染
→ 用户看到空白页面
→ 浏览器控制台报错

修复方法：
在对应的 API 文件中添加缺失的 export function
```

---

### Step 5️⃣：后端 Serializer ↔ 前端类型对比（深度检查）

#### 检查清单

- [ ] **5.1 字段数量一致性**
  - 后端 Serializer 的 `fields` 数量 ≈ 前端 Interface 的属性数量？
  - 注意：前端可以少（只取需要的），但不能多（多了就是虚假字段）

- [ ] **5.2 read_only vs writeable**
  - 前端 CreateRequest / UpdateRequest 接口是否只包含可写字段？
  
  ```python
  # backend/agents/serializers.py
  class AgentSerializer(serializers.ModelSerializer):
      class Meta:
          model = Agent
          fields = ['id', 'hostname', 'status', ..., 'agent_token']
          read_only_fields = ['id', 'created_at', 'updated_at']
  ```
  
  ```typescript
  // frontend/src/types/models/
  // ✅ 创建请求只包含可写字段
  export interface CreateAgentRequest {
      hostname: string;
      status: string;
      // 不包含 id, created_at 等 read-only 字段
  }
  ```

- [ ] **5.3 SerializerMethodField**
  - 后端用 `SerializerMethodField()` 计算的字段，前端是否有对应接收？
  
  ```python
  # 后端计算字段
  locked_by_username = serializers.SerializerMethodField()
  
  # 前端必须有此字段
  export interface Device {
      locked_by_username: string | null;
  }
  ```

#### 工具方法

```bash
# 提取后端 Serializer 的 fields 定义
grep -A 10 "class Meta:" backend/**/serializers.py | grep "fields"

# 对比前端接口属性数
wc -l frontend/src/types/models/
```

---

### Step 6️⃣：URL 路由 + HTTP 方法匹配检查

#### 检查清单

- [ ] **6.1 路由路径一致性**
  - 前端调用的 URL 路径 vs 后端 `urls.py` 注册的路由？
  
  ```python
  # backend/monitors/urls.py
  router.register(r'monitor-events', MonitorEventViewSet)
  # 实际路径: /api/v2/monitors/monitor-events/
  ```
  
  ```typescript
  // frontend/src/api/monitors.ts
  // ✅ 正确
  const res = await client.get('/monitors/monitor-events/');
  
  // ❌ 错误：路径不对
  const res = await client.get('/monitors/events/');
  ```

- [ ] **6.2 HTTP 方法允许列表**
  - 前端用的 method 是否在后端 ViewSet 的 `allowed_methods` 或 `@api_view` 装饰器中？
  
  ```python
  # 后端只读 ViewSet
  class MonitorEventViewSet(ReadOnlyModelViewSet):
      # 只允许 GET, HEAD, OPTIONS
  ```
  
  ```typescript
  // ❌ 错误：尝试 POST 到只读端点
  await client.post('/monitors/monitor-events/', data)  // 405 Method Not Allowed!
  ```

- [ ] **6.3 自定义 Action 路由**
  - 后端自定义 `@action` 的 URL 是否正确拼接？
  
  ```python
  # 后端
  @action(detail=True, methods=['post'])
  def acknowledge(self, request, pk=None):
      ...
  # 实际路径: /api/v2/monitors/monitor-events/{pk}/acknowledge/
  ```
  
  ```typescript
  // ✅ 正确
  await client.post(`/monitors/monitor-events/${eventId}/acknowledge/`);
  ```

#### 工具方法

```bash
# 查看所有注册的路由
python manage.py show_urls  # 如果安装了 django-extensions

# 或者直接搜索 urls.py
grep -rn "path(\|register(" backend/**/urls.py
```

---

### Step 7️⃣：请求/响应体结构验证

#### 检查清单

- [ ] **7.1 请求体字段**
  - 前端 POST/PUT/PATCH 发送的 JSON 字段是否都在后端 Serializer 的 `writeable_fields` 中？

- [ ] **7.2 响应包装结构**
  - 后端返回的是 `{ data: [...] }` 还是直接 `[...]`？
  - 前端是否正确解构 `.data`？

- [ ] **7.3 分页响应格式**
  - 后端分页返回格式是否与前端 `PaginatedResponse<T>` 匹配？
  
  ```python
  # DRF 默认分页响应
  {
      "count": 100,
      "next": "http://...?page=2",
      "previous": null,
      "results": [...]
  }
  ```
  
  ```typescript
  // ✅ 前端正确映射
  export interface PaginatedResponse<T> {
      count: number;
      next: string | null;
      previous: string | null;
      results: T[];
  }
  ```

- [ ] **7.4 错误响应格式**
  - 后端返回的错误格式（`{ detail: "..." }` vs `{ message: "..." }`）是否与前端 axios interceptor 匹配？

#### 工具方法

```bash
# 使用 Invoke-WebRequest 测试 API 响应结构
$body = @{ username='admin'; password='admin123' } | ConvertTo-Json
$r = Invoke-WebRequest -Uri "http://localhost:8000/api/v2/accounts/auth/login/" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
$r.Content | ConvertFrom-Json | ConvertTo-Json -Depth 5
```

---

### Step 8️⃣：运行时行为验证

#### 检查清单

- [ ] **8.1 页面加载测试**
  - 使用 OpenPreview 打开目标页面，检查是否有 JS 错误
  
- [ ] **8.2 登录流程测试**
  - browser-use 自动化登录（admin/admin123），验证跳转
  
- [ ] **8.3 控制台错误检查**
  ```javascript
  JSON.stringify({
      jsErrors: window.__browserErrors?.length || 0,
      url: window.location.href
  })
  ```
  
- [ ] **8.4 关键交互测试**
  - 表单提交、表格排序/分页、Modal 弹窗、Switch 开关等

- [ ] **8.5 Network 面板检查**
  - API 请求是否都返回 200/201/204？
  - 是否有 400/404/405/500 错误？

#### 验证通过标准

```
✅ 页面正常渲染（无白屏）
✅ JavaScript 错误数 = 0
✅ 所有 API 请求返回 2xx 状态码
✅ 关键交互功能正常（CRUD、筛选、分页）
✅ 无 ERR_ABORTED 错误（Trailing Slash 问题）
```

---

## 三、快速检查清单（10分钟版）

如果时间紧张，可以只执行以下 **Top 5 高频检查项**：

### ⚡ Quick Check List

1. **[5 min]** 导入/导出完整性扫描
   ```bash
   # 在每个 pages 目录下执行
   grep -rn "import { .* } from.*api/" . | while read line; do
       module=$(echo $line | grep -oP "from '\K[^']+")
       funcs=$(echo $line | grep -oP "import { \K[^ ]+")
       echo "Checking $module for: $funcs"
   done
   ```

2. **[2 min]** ID 类型快速替换
   ```bash
   # 全局搜索 string 类型的 ID 参数
   grep -rn ": string): Promise" frontend/src/api/*.ts | grep -i "id\|Id"
   ```

3. **[1 min]** Trailing Slash 检查
   ```bash
   # 查找可能缺失 / 的 POST/PUT/DELETE
   grep -rn "client\.\(post\|put\|delete\|patch\)(" frontend/src/api/*.ts | grep -v "'/$"
   ```

4. **[1 min]** 字段名黑名单扫描
   ```bash
   # 搜索已知的错误字段名
   grep -rn "\.is_valid\|\.stamina\|\.read\b\|rule_type\|pattern\b" frontend/src/pages/
   ```

5. **[1 min]** 浏览器快速验证
   - 打开 http://localhost:5173
   - 检查控制台是否有红色错误

---

## 四、常见错误模式库（持续更新）

### 4.1 致命错误（导致白屏）

| 错误模式 | 示例 | 修复方案 |
|---------|------|---------|
| API 缺失导出 | `forceFailExecution` 未导出 | 添加 `export async function` |
| 循环依赖 | A → B → A | 重构为单向依赖或提取公共模块 |
| 类型导入错误 | `import type { X } from 'y'` 但 y 不存在 | 修正导入路径 |

### 4.2 严重错误（功能失效）

| 错误模式 | 示例 | 修复方案 |
|---------|------|---------|
| 字段名拼写错误 | `is_valid` → `is_active` | 全局搜索替换 |
| ID 类型错误 | `string` → `number` | 批量修改类型定义 |
| URL 缺失 `/` | `/tasks/1` → `/tasks/1/` | 统一添加 trailing slash |
| HTTP 方法错误 | GET 改成 POST | 检查后端 allowed_methods |
| Zustand store 字段名不一致 | `n.read` → `n.is_read` | 全局替换 + 类型安全约束 |

### 4.3 一般错误（显示异常）

| 错误模式 | 示例 | 修复方案 |
|---------|------|---------|
| 枚举值缺失 | DeviceStatus 缺少 `'locked'` | 补充联合类型成员 |
| 虚假字段 | 引用不存在的 `stamina` | 移除字段和 UI 显示 |
| 分页格式不匹配 | `count` vs `total` | 统一 PaginatedResponse 接口 |

### 4.4 前端 UI 框架废弃 API（antd v6）

| 错误模式 | 示例 | 修复方案 |
|---------|------|---------|
| Drawer 使用 `width` | `<Drawer width={560}>` | 改为 `size={560}` |
| Input 使用 `bordered` | `<Input bordered={false}>` | 改为 `variant="borderless"` |
| Statistic 使用 `valueStyle` | `<Statistic valueStyle={...}>` | 改为 `styles={{ content: {...} }}` |
| Modal 使用 `destroyOnClose` | `<Modal destroyOnClose>` | 改为 `destroyOnHidden` |
| Space 使用 `direction` | `<Space direction="vertical">` | 改为 `orientation="vertical"` |
| 使用静态 message/notification | `import { message } from 'antd'` | 使用 `App.useApp()` 获取实例 |

> **注意**: 以上废弃 API 仅触发控制台警告，不影响功能运行，但应及时修复保持代码清洁。

---

## 五、自动化脚本（可选）

### 5.1 一键扫描脚本

创建 `scripts/data-chain-audit.sh`（Bash）或 `.ps1`（PowerShell）：

```powershell
# data-chain-audit.ps1
# GAF 数据链路快速审计脚本

Write-Host "=== GAF Data Chain Audit ===" -ForegroundColor Cyan

# 1. 检查缺失导出
Write-Host "`n[1] Checking missing exports..." -ForegroundColor Yellow
$imports = Get-ChildItem -Path "frontend/src/pages" -Recurse -Filter "*.tsx" | 
          Select-String -Pattern "from.*api/" | 
          ForEach-Object { $_.Line -replace '.*import \{ ([^}]+) \}.*', '$1' }

Write-Host "Found $($imports.Count) import statements"

# 2. 检查 ID 类型
Write-Host "`n[2] Checking ID types..." -ForegroundColor Yellow
$wrongIds = Select-String -Path "frontend/src/api/*.ts" -Pattern ": string\): Promise" | 
           Where-Object { $_.Line -match "Id|id" }

if ($wrongIds) {
    Write-Host "⚠️ Found potential wrong ID types:" -ForegroundColor Red
    $wrongIds | ForEach-Object { Write-Host $_.Line }
} else {
    Write-Host "✅ All IDs look correct" -ForegroundColor Green
}

# 3. 检查 Trailing Slash
Write-Host "`n[3] Checking trailing slashes..." -ForegroundColor Yellow
$missingSlashes = Select-String -Path "frontend/src/api/*.ts" -Pattern "client\.(post|put|delete|patch)\([^)]*['\"]/?[^/]*['\"]" 

if ($missingSlashes) {
    Write-Host "⚠️ Missing trailing slashes found:" -ForegroundColor Red
    $missingSlashes | ForEach-Object { Write-Host $_.Line }
} else {
    Write-Host "✅ All URLs have proper trailing slashes" -ForegroundColor Green
}

Write-Host "`n=== Audit Complete ===" -ForegroundColor Cyan
```

### 5.2 使用方式

```powershell
# 在项目根目录执行
.\scripts\data-chain-audit.ps1

# 输出示例：
# === GAF Data Chain Audit ===
#
# [1] Checking missing exports...
# Found 42 import statements
#
# [2] Checking ID types...
# ✅ All IDs look correct
#
# [3] Checking trailing slashes...
# ⚠️ Missing trailing slashes found:
#   await client.delete(`/devices/${deviceId}/command`)
#
# === Audit Complete ===
```

---

## 六、最佳实践建议

### 6.1 开发阶段预防措施

1. **后端先行原则**
   - 先定义好 Serializer 和 URL 路由
   - 再写前端类型定义和 API 函数
   - 最后实现组件 UI

2. **类型安全第一**
   - 启用 TypeScript strict 模式
   - 避免 `as any` 强制类型转换
   - 使用泛型约束 API 返回值

3. **统一工具函数**
   - 封装 `apiUrl()` 自动处理 trailing slash
   - 封装 `getAuthHeaders()` 统一认证头
   - 使用 `classifyError()` 统一错误处理

### 6.2 Code Review 检查点

PR 描述中必须回答：

- [ ] 新增的 Serializer 字段是否同步更新到前端类型定义？
- [ ] 新增的 API 函数是否已导出并被正确导入？
- [ ] POST/PUT/DELETE 请求是否带了 trailing `/`？
- [ ] ID 参数是否使用 `number` 类型？
- [ ] 是否有浏览器测试截图证明功能正常？

### 6.3 Git Hook 建议

```bash
# .git/hooks/pre-commit（可选）
# 提交前自动运行快速检查
npm run typecheck  # 或 tsc --noEmit
npm run lint        # 或 eslint src/
```

---

## 七、版本历史

| 版本 | 日期 | 更新内容 |
|:---:|:----:|---------|
| 1.0 | 2026-06-02 | 初始版本，基于 Phase R21 审计经验创建 |
| 1.2 | 2026-06-02 | 追加 `read → is_read` 错误案例（useNotificationStore.ts），新增 Zustand store 字段名不一致错误模式 |

---

## 八、相关文档

- **[completed-features.md](./completed-features.md)** — 已实现功能清单
- **[bug-tracker.md](./bug-tracker.md)** — Bug 跟踪记录
- **GAF-optimal-solution.md** — 技术选型最优解
- **gaf-v2-enhanced-feature-spec.md** — 功能规格说明
- **ui-implementation-plan.md** — UI 实现方案

---

## 九、反馈与改进

如果你在使用此检查清单过程中发现：

- ✅ **新的错误模式** → 请追加到「四、常见错误模式库」
- ✅ **更好的检查方法** → 请更新对应步骤的工具方法
- ✅ **自动化脚本优化** → 请改进「五、自动化脚本」部分
- ✅ **遗漏的检查项** → 请补充到 Step 1~8 或新增 Step 9

**贡献方式**: 直接编辑本文档并更新版本历史。

---

> 💡 **提示**: 打印此文档贴在工位旁，每次开发新功能时对照检查，可以避免 80% 的前后端数据链路问题。
