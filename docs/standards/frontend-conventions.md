---
summary: 前端通用规范 — 组件命名/Props/状态/样式/错误处理/测试，约束 AI 写出格式一致的代码
applies_to: [frontend, react, typescript, vite]
last_updated: 2026-07-18
key_decisions:
  - 组件命名 PascalCase，文件名同名（DeviceCard.tsx → DeviceCard）
  - Props 用 interface（不用 type alias），可选字段加 ?
  - 状态用 Zustand store（不用 Redux/Context），按业务域拆分（authStore/deviceStore/taskStore）
  - 样式用 utility classes (gaf-*) + 全局 token（不用 inline style + 不用 styled-components；CSS Modules 仅用于复杂组件级样式）
  - API 调用统一走 src/api/ 封装层（不用 axios 直接调用）
  - 错误用 ErrorBoundary 包裹页面 + axios interceptor 统一 toast
  - 测试用 Vitest + React Testing Library，组件 __tests__/ 同级目录
  - 遵循 Vercel Web Interface Guidelines（焦点/表单/动画/排版/触摸/暗色模式/文案，见 §12.2-12.10）
tech_debt:
  - 现状 (2026-07-18 TD-177 重新统计): src/pages 下 74 文件仍用 inline style（共 589 处，多为动态值保留），src/components 下 62 文件（共 351 处），未抽到 CSS Modules（动态值除外）
  - 已清：2026-06-26 自动迁移 107 文件 435 处静态 inline style → gaf-* utility classes（commit -）
  - 现状 (2026-07-18 TD-177 重新统计): src/pages 下 88 个页面（不含 __tests__）中 35 个用 PageWrapper，其余仍裸 div+Card
  - 已清：src/ 下相对路径已全部迁移到 @/ alias（225 文件 490 处，2026-06-25）
  - 已清：i18n 示例已修正为 @/i18n（非 react-i18next，2026-06-25）
  - 已清：key={index} 已全部替换为复合 keys（16 文件，2026-06-25）
  - 已清：非测试代码中的 any 已清理（10 文件 26 处，2026-06-25）
  - 原则：新代码必须遵循规范；不堆积新债；存量债按批次清理
---

# GAF Frontend Conventions

> **强制**：AI 写前端代码前必读。所有 React/TypeScript/Vite 代码必须遵循本文规范，否则 pre-commit hook 会拒绝。

## 1. 文件与目录组织

```
src/
├── api/                  # 后端接口封装（每资源一个 .ts）
├── components/           # 业务组件（按功能子目录）
│   ├── Common/           # 通用组件（PageWrapper, StatusBadge, ErrorBoundary）
│   ├── Dashboard/        # 仪表盘子组件
│   ├── Layout/           # 布局（AppLayout, Sidebar, Header）
│   ├── [Domain]/         # 业务域（Device/Task/Pipeline/AI/...）
│   └── guards/           # 路由守卫（AuthGuard, PermissionGuard, RoleGuard）
├── hooks/                # 自定义 React hooks
├── pages/                # 页面级组件（与路由一一对应）
├── stores/               # Zustand 状态（按业务域拆）
├── styles/               # 全局 CSS（components.css, acrylic.css）
├── types/                # TypeScript 类型定义
├── utils/                # 工具函数
├── websocket/            # WebSocket 客户端
├── theme/                # 主题切换
├── i18n/                 # 国际化
└── providers/            # React Context providers
```

**规则**：
- ✅ 一个文件一个组件（主组件 + 子组件不超过 3 个）
- ✅ 业务组件按域分目录（Device/Task/Pipeline），不放散文件
- ❌ 不在 `components/` 根目录直接放组件

## 2. 组件命名与导出

```typescript
// ✅ PascalCase + 同名文件名
// DeviceCard.tsx
export function DeviceCard({ device, onSelect }: DeviceCardProps) { ... }
export default DeviceCard;

// ❌ camelCase 文件名
// deviceCard.tsx
// ❌ 默认导出 + 命名导出混用
export default function DeviceCard() { ... }
export const DeviceCardHelper = () => ...;
```

**规则**：
- 文件名 = 组件名 = PascalCase
- 优先命名导出（便于 tree-shaking）
- 页面级组件：`index.tsx` 作为默认入口（如 `pages/Dashboard/index.tsx`）
- 业务子组件：`ComponentName.tsx`

## 3. Props 类型定义

```typescript
// ✅ interface（可扩展），可选字段加 ?
interface DeviceCardProps {
  device: Device;
  onSelect?: (device: Device) => void;
  showActions?: boolean;  // 默认值在解构时给
}

// ❌ type alias（不可扩展）
type DeviceCardProps = { ... };

// ❌ 必填字段没标 ? 但函数内用 ? 链式
function DeviceCard({ device, onSelect }) {
  onSelect?.(device);  // 不一致，必填
}
```

**规则**：
- 用 `interface` 不用 `type`（除联合类型/工具类型外）
- 可选 Props 加 `?`，默认值在解构时给
- 事件回调命名：`on[Event]`（`onSelect`, `onChange`, `onSubmit`）
- 必传 children：`children: React.ReactNode` 显式声明

## 4. 状态管理（Zustand）

```typescript
// ✅ src/stores/deviceStore.ts
import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

interface DeviceState {
  devices: Device[];
  selectedId: string | null;
  fetchDevices: () => Promise<void>;
  select: (id: string) => void;
}

export const useDeviceStore = create<DeviceState>()(
  devtools((set) => ({
    devices: [],
    selectedId: null,
    fetchDevices: async () => {
      const res = await api.devices.list();
      set({ devices: res.data });
    },
    select: (id) => set({ selectedId: id }),
  }))
);

// ❌ Redux / Context / 组件内 useState 跨页面共享
```

**规则**：
- 全局状态用 Zustand（不用 Redux/Context）
- 按业务域拆 store（authStore/deviceStore/taskStore/pipelineStore/...）
- 异步 action 内置在 store 里（不用 thunk/saga）
- 组件订阅用 selector：`const devices = useDeviceStore(s => s.devices)`

## 5. 样式规范

> **F008 修订（2026-06-28）**：原规范以 CSS Modules 为首选样式机制，但代码库实际采用 utility classes (`gaf-*`) + 全局 token 体系（`src/styles/components.css` 定义 40+ 工具类，已迁移 435+ 处 inline style）。现将 utility classes 提升为首选，CSS Modules 降级为"复杂组件级样式的可选方案"。

```typescript
// ✅ 首选：utility classes (gaf-*) + 全局 token
// DeviceCard.tsx
<div className="gaf-flex-col gaf-gap-md gaf-p-md">...</div>

// ✅ 可选（仅复杂组件级样式）：CSS Modules
// DeviceCard.tsx
import styles from './DeviceCard.module.css';
<div className={`${styles.card} gaf-flex-col`}>...</div>

// DeviceCard.module.css
.card {
  background: var(--color-bg-card);
  padding: var(--spacing-md);
  border-radius: var(--radius-sm);
}

// ❌ inline style（静态值）
<div style={{ background: '#fff', padding: 16 }}>

// ❌ styled-components / emotion
const Card = styled.div`background: #fff;`;
```

**全局 token**（`src/styles/acrylic.css` `:root` 定义）：
- 间距：`--spacing-xs/sm/md/lg/xl/2xl/3xl`（4/8/12/16/24/32/48px）
- 圆角：`--radius-sm/md/lg/xl/full`（4/8/12/16/9999px）
- 阴影：`--shadow-sm/md/lg/xl`
- 过渡：`--transition-fast/base/slow`（0.15s/0.2s/0.3s）
- 层级：`--z-dropdown/sticky/overlay/modal/tooltip`
- 颜色：用 Ant Design token（`theme.useToken()` 取 `token.colorBgContainer` / `token.colorPrimary` / `token.colorText` / `token.colorBorder` 等；CSS 中用 `var(--colorBgLayout, #fafafa)` 形式，无独立颜色 token）

**Utility classes**（`src/styles/components.css` 定义，inline style 迁移首选）：
- 布局：`gaf-flex` / `gaf-flex-col` / `gaf-flex-center` / `gaf-flex-between` / `gaf-flex-wrap` / `gaf-flex-1`
- 间距：`gaf-gap-xs/sm/md/lg/xl` / `gaf-mb-xs/sm/md/lg/xl` / `gaf-mt-xs/sm/md/lg/xl`
- 尺寸：`gaf-w-sm/md/lg/full` / `gaf-hidden`
- 文字：`gaf-text-sm/md/lg` / `gaf-font-medium/semibold/bold`
- 其他：`gaf-m-0`
- 页面容器：`gaf-page` / `gaf-page-header` / `gaf-page-title` / `gaf-page-actions`
- 工具栏：`gaf-toolbar` / `gaf-toolbar-group` / `gaf-toolbar-divider` / `gaf-toolbar-spacer`

**规则**：
- 样式优先级：utility classes（gaf-*） > CSS Modules（Component.module.css，仅复杂组件级样式） > 全局 token（var） > 动态 inline style（仅动态值）
- ❌ 不用静态 inline style（用 utility class 或 CSS Module）
- ✅ 动态值（基于 props/state/theme 的条件颜色、计算尺寸）可用 inline style
- ❌ 不用 styled-components / emotion / tailwind
- ✅ 复用 `PageWrapper`（页面容器）/ `gaf-toolbar`（工具栏）
- ✅ CSS Modules 仅在 utility classes 无法表达复杂样式时使用（如伪类、媒体查询、keyframe 动画）

**现状债**（见头部 `tech_debt`）：`src/pages` + `src/components` 仍有 916 处 inline style（87+62 文件），多为动态值保留（基于 props/state/theme 的条件颜色、计算尺寸）。新增页面/组件不得使用静态 inline style。CSS Modules 试点暂缓，待有复杂组件级样式需求时再引入。

## 6. API 调用

```typescript
// ✅ src/api/devices.ts
import client from './client';

export const devicesApi = {
  list: () => client.get<Device[]>('/devices/'),
  get: (id: string) => client.get<Device>(`/devices/${id}/`),
  create: (data: DeviceCreate) => client.post<Device>('/devices/', data),
  update: (id: string, data: Partial<Device>) =>
    client.patch<Device>(`/devices/${id}/`, data),
  delete: (id: string) => client.delete(`/devices/${id}/`),
};

// 组件内使用
const devices = await devicesApi.list();

// ❌ 直接用 axios
import axios from 'axios';
const res = await axios.get('/api/devices/');

// ❌ 散落在组件里的 fetch
```

**规则**：
- 每个后端资源一个 `src/api/[resource].ts`（devices.ts, tasks.ts, agents.ts...）
- 走 `client`（default export）统一封装（已带 token 注入 + 错误拦截）
- 命名：`[resource]Api.list/get/create/update/delete`（不用 CRUD 中文）
- 路径以 `/` 结尾（Django 习惯）

## 7. 错误处理

```typescript
// ✅ 页面级 ErrorBoundary 包裹
import { ErrorBoundary } from '@/components/Common/ErrorBoundary';

<ErrorBoundary fallback={<PageError />}>
  <DeviceList />
</ErrorBoundary>

// ✅ API 错误统一在 apiClient interceptor 处理（toast）
// 业务代码不需要 try-catch（除非要做重试/降级）

// ❌ 组件内每处都写 try-catch + toast
const handleClick = async () => {
  try {
    await devicesApi.delete(id);
  } catch (e) {
    toast.error('删除失败');
  }
};
```

**规则**：
- 顶层用 `<ErrorBoundary>` 包裹页面
- API 错误统一在 `apiClient` 拦截器处理（toast/通知中心）
- 业务代码不写 `try-catch`（除非要降级/重试）
- 表单错误用 AntD Form `form.setFields([{ name, errors }])`

## 8. 路由与页面

```typescript
// ✅ src/App.tsx 中配置路由
<Route path="/devices" element={<DevicesPage />} />
<Route path="/devices/:id" element={<DeviceDetailPage />} />

// ✅ 页面文件：src/pages/Devices/index.tsx
export default function DevicesPage() { ... }

// ✅ 页面内部用 PageWrapper 统一布局
import PageWrapper from '@/components/Common/PageWrapper';

<PageWrapper
  title="设备管理"
  extra={<DeviceFilterBar />}
>
  <DeviceList />
</PageWrapper>
```

**规则**：
- 路由配置集中在 `App.tsx`
- 页面文件名 = 路由名（PascalCase + 后缀 Page 或目录 `index.tsx`）
- 所有页面用 `PageWrapper` 包裹（统一 title/面包屑/工具栏）

**现状债**（见头部 `tech_debt`，2026-07-18 TD-177 重新统计）：`src/pages` 下 88 个页面（不含 __tests__）中 35 个用 `PageWrapper`，其余页面仍裸 `<div style={{ padding: 16 }}><Card title=...>`。修改对应页面时必须迁移到 `PageWrapper`，工具栏放 `PageWrapper.extra` 而非 Card.extra，避免标题被按钮遮挡。

**PageWrapper 豁免清单**（spec-36 Phase 4 确认, 2026-07-20）: 以下 5 个全屏编辑器/特殊布局页面**不应**强加 PageWrapper, 会破坏 100vh/100% 全屏布局:
- `pages/Tasks/PipelineEditor/PipelineEditorPage.tsx` — ReactFlow 100vh 全屏编辑器
- `pages/Ops/ScheduledTasks/DagEditorPage.tsx` — ReactFlow 100% DAG 编辑器
- `pages/AI/AiAssistantPanel.tsx` — 左右分栏 100% 高度 (280px sidebar)
- `pages/AI/QAPanel.tsx` — 全高度 Tabs 布局
- `pages/AI/CustomSkillEditor.tsx` — 左右分栏 100% 高度 (300px sidebar)

判断标准: 若页面根容器用 `style={{ height: '100vh' }}` 或 `style={{ height: '100%' }}` + 内部依赖 flex 左右分栏, 则豁免 PageWrapper (`.gaf-page` 的 padding + overflow 会破坏全屏布局)。

## 9. 测试

```
src/
├── components/
│   └── Common/
│       ├── ErrorBoundary.tsx
│       └── __tests__/
│           └── ErrorBoundary.test.tsx
├── pages/
│   └── Dashboard/
│       ├── index.tsx
│       └── __tests__/
│           └── Dashboard.test.tsx
└── hooks/
    └── useAuth.ts
    └── __tests__/
        └── useAuth.test.ts
```

**规则**：
- 测试文件放 `__tests__/` 子目录，与源文件同级
- 框架：Vitest + React Testing Library
- 组件测试：渲染 + 关键交互（点击/输入/异步）
- Hook 测试：`renderHook` from `@testing-library/react`
- 覆盖率：核心业务组件 ≥ 70%

## 10. 导入路径

```typescript
// ✅ 用 @ alias 指向 src/
import { DeviceCard } from '@/components/Device/DeviceCard';
import { useDeviceStore } from '@/stores/deviceStore';
import type { Device } from '@/types/models';

// ❌ 相对路径 ../../../components/...
import { DeviceCard } from '../../../components/Device/DeviceCard';
```

**配置**：`tsconfig.json` paths + `vite.config.ts` resolve.alias 都设 `"@" → "src"`

**已清**：`src/` 下相对路径已全部迁移到 `@/` alias（2026-06-25）。新增文件不得使用 `../../` 相对路径（除同目录兄弟文件）。

## 11. i18n 国际化

```typescript
// ✅ 用项目自研的 src/i18n（不是 react-i18next）
import { useTranslation } from '@/i18n';

function DeviceCard() {
  const t = useTranslation();
  return <div>{t('devices.card.title')}</div>;
}

// 翻译文件: src/i18n/locales/<domain>.ts 导出 Record<string, string>
// 中/英/日/韩四语言都需补齐

// ❌ 硬编码中文字符串
return <div>设备卡片</div>;

// ❌ 从 react-i18next 导入（项目未用 react-i18next）
import { useTranslation } from 'react-i18next';
```

**规则**：
- 用户可见字符串必须走 i18n
- 命名空间按业务域分（devices/tasks/auth/...）
- 缺失翻译 key 用 `t('key', { defaultValue: 'fallback' })`
- 语言/主题/DPI 等用户偏好提供 `system`/`auto` 选项并置顶，默认值为跟随系统
- **必须从 `@/i18n` 导入 `useTranslation`**，不要从 `react-i18next` 导入

## 12. 性能与可访问性

- 列表渲染：`key={item.id}`（不用 index）
- 重渲染控制：`React.memo` / `useMemo` / `useCallback` 用于 props 稳定的子组件
- 图片：`loading="lazy"` + 宽高声明 + `width`/`height` 属性（防 CLS）
- 无障碍：交互元素加 `aria-label`，表单加 `name` 属性
- 大列表（>1000 行）：用 `react-window` / `react-virtual`
- 大列表（>50 项）：虚拟化或 `content-visibility: auto`

**已清**：`key={index}` 已全部替换为复合 keys（2026-06-25，见 §13 禁止清单）。

### 12.1 实时数据面板

实时刷新面板（如 Agent 健康面板、设备状态看板）必须避免整屏闪烁：

- 卡片/数字子组件用 `React.memo` 包裹，复杂 props 提供自定义 `areEqual` 只比较影响渲染的字段
- 列表排序、设备映射等计算用 `useMemo` 缓存
- WebSocket 心跳回调做节流（throttle），避免高频触发重新请求
- 数据标签统一走 i18n，避免文案硬编码导致后期不一致

### 12.2 焦点状态（Web Interface Guidelines）

- ✅ 交互元素必须有可见焦点：`focus-visible:ring-*` 或等效 Ant Design focus 样式
- ❌ 禁止 `outline: none` / `outline-none` 不提供替代焦点
- ✅ 用 `:focus-visible` 优先于 `:focus`（避免点击时显示焦点环）
- ✅ 复合控件用 `:focus-within` 分组焦点

### 12.3 表单规范（Web Interface Guidelines）

- ✅ 输入框必须加 `autocomplete` + 有意义的 `name`
- ✅ 用正确的 `type`（`email` / `tel` / `url` / `number`）和 `inputmode`
- ❌ 禁止阻止粘贴（`onPaste` + `preventDefault`）
- ✅ `label` 可点击（`htmlFor` 或包裹控件）
- ✅ 邮箱/验证码/用户名输入禁用拼写检查（`spellCheck={false}`）
- ✅ 提交按钮在请求开始前保持可用，请求中显示 spinner
- ✅ 错误信息显示在字段旁边，提交时聚焦第一个错误字段
- ✅ Placeholder 以 `…` 结尾并展示示例格式
- ✅ 非认证字段用 `autocomplete="off"` 避免密码管理器触发
- ✅ 未保存变更离开页面前警告（`beforeunload` 或路由守卫）

### 12.4 动画规范（Web Interface Guidelines）

- ✅ 遵守 `prefers-reduced-motion`（提供减弱版或禁用动画）
- ✅ 只动画 `transform` / `opacity`（合成器友好）
- ❌ 禁止 `transition: all`（明确列出属性）
- ✅ 设置正确的 `transform-origin`
- ✅ SVG 变换用 `<g>` 包裹 + `transform-box: fill-box; transform-origin: center`
- ✅ 动画可中断（响应用户输入中途停止）

### 12.5 排版规范（Web Interface Guidelines）

- ✅ 用 `…` 不用 `...`
- ✅ 用弯引号 `"` `"` 不用直引号 `"`
- ✅ 不换行空格：`10&nbsp;MB`、`⌘&nbsp;K`、品牌名
- ✅ 加载状态以 `…` 结尾：`"Loading…"` / `"Saving…"`
- ✅ 数字列/对比用 `font-variant-numeric: tabular-nums`
- ✅ 标题用 `text-wrap: balance` 或 `text-pretty`（防孤行）

### 12.6 内容处理（Web Interface Guidelines）

- ✅ 文本容器处理长内容：`truncate` / `line-clamp-*` / `break-words`
- ✅ Flex 子元素需 `min-w-0` 以允许文本截断
- ✅ 处理空状态（空字符串/空数组不渲染破坏 UI）
- ✅ 用户生成内容：预期短、中、超长输入

### 12.7 触摸与交互（Web Interface Guidelines）

- ✅ `touch-action: manipulation`（防双击缩放延迟）
- ✅ `-webkit-tap-highlight-color` 有意设置
- ✅ 模态/抽屉/弹层中 `overscroll-behavior: contain`
- ✅ 拖拽中禁用文本选择，拖拽元素加 `inert`
- ⚠️ `autoFocus` 仅桌面端单一主输入使用，移动端避免

### 12.8 暗色模式与主题（Web Interface Guidelines）

- ✅ 暗色主题在 `<html>` 设 `color-scheme: dark`（修复滚动条/输入框）
- ✅ `<meta name="theme-color">` 匹配页面背景色
- ✅ 原生 `<select>`：显式 `background-color` + `color`（Windows 暗色模式）

### 12.9 悬停与交互状态（Web Interface Guidelines）

- ✅ 按钮/链接必须有 `hover:` 状态（视觉反馈）
- ✅ 交互状态增加对比度：hover/active/focus 比静止态更突出

### 12.10 文案规范（Web Interface Guidelines）

- ✅ 主动语态："安装 CLI" 不用 "CLI 将被安装"
- ✅ 标题/按钮用 Title Case（Chicago 风格）
- ✅ 计数用数字："8 个部署" 不用 "八个"
- ✅ 按钮标签具体化："保存 API Key" 不用 "继续"
- ✅ 错误消息包含修复/下一步，不只描述问题
- ✅ 第二人称，避免第一人称

## 13. 禁止清单

- ❌ `any` 类型（必须 `unknown` + 类型守卫或显式 interface）
- ❌ `console.log` 调试代码（提交前删）
- ❌ 注释掉的代码（删）
- ❌ 在 `useEffect` 里发请求（用 React Query / SWR / store action）
- ❌ 嵌套三元运算符（用 `if` 或拆组件）
- ❌ 直接修改 props（用 callback 通知父组件）
- ❌ `outline: none` 不提供替代焦点（见 §12.2）
- ❌ `transition: all`（明确列出属性，见 §12.4）
- ❌ `<div onClick>` 做交互（用 `<button>` / `<a>`，见 §12.2）
- ❌ 图片无 `width`/`height`（防 CLS，见 §12）
- ❌ `user-scalable=no` / `maximum-scale=1`（禁止禁用缩放）
- ❌ `onPaste` + `preventDefault`（禁止阻止粘贴，见 §12.3）

## 14. 模式约束 UI 模式 (Multi-game 模式参考, Spec A)

**背景**: Spec A 引入 `FeatureFlag unattended_multi_game_mode`, multi 模式下需禁选非 hwnd-isolated 的截图/输入方法。此 UI 模式可复用于未来类似场景 (如不同权限角色可选方法不同)。

### 14.1 Segmented 开关切换模式

```tsx
// UnattendedControlBar 顶部 Segmented 开关, 绑定 FeatureFlag
<Segmented
  value={isMultiGameMode ? 'multi' : 'single'}
  onChange={(v) => updateFeatureFlag('unattended_multi_game_mode', v === 'multi')}
  options={[
    { label: t('unattended.modeSingle'), value: 'single' },
    { label: t('unattended.modeMulti'), value: 'multi' },
  ]}
/>
```

### 14.2 Select.Option disabled 约束 + Tooltip 提示

```tsx
// WindowManagementPage DeviceForm 的方法选择器
// buildMethodOptions helper 根据 allowed_*_methods 字段决定是否 disabled
<Select>
  {METHOD_OPTIONS.map((opt) => {
    const disabled = isMultiMode && !allowedMethods.includes(opt.value);
    return (
      <Select.Option
        key={opt.value}
        value={opt.value}
        disabled={disabled}
        title={disabled ? t('device.methodBlockedInMultiMode') : undefined}
      >
        {opt.label}
      </Select.Option>
    );
  })}
</Select>
```

### 14.3 硬约束

- ✅ 模式切换必须通过 FeatureFlag API (`/api/v2/settings/feature-flags/{name}/`), 不允许前端本地 state 单独维护
- ✅ `allowed_*_methods` 列表从 API `DeviceSerializer` 返回, **不在前端硬编码** (避免与 backend `MULTI_GAME_SAFE_*` 常量漂移)
- ✅ 'auto' 选项始终允许 (handler 自动选最佳, 会在 multi 模式下降级到 safe 方法)
- ❌ 禁止在前端做方法合法性判断 (应依赖 backend `resolve_device_methods` 结果)
- ❌ 禁止 disabled 的 Option 可通过键盘 / 命令行选中

### 14.4 i18n keys

新增 4-locale 翻译 keys (zh-CN / en-US / ja-JP / ko-KR):
- `unattended.modeSingle` / `unattended.modeMulti`
- `device.methodBlockedInMultiMode` (Tooltip 提示)

参考: `frontend/src/pages/UnattendedControlBar.tsx` + `frontend/src/pages/WindowManagementPage.tsx` 的 `buildMethodOptions` helper

---

**维护者**：AI（不人工维护）
**变更触发**：修改任何前端代码 → 检查本规范是否需要更新 → 同步 `last_updated`
**验证**：`npm run lint` + `npx tsc --noEmit` + `npm test`
