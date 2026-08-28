---
source: GAF/.ai-memory/lessons/N144-r37-p3-c5-antd-deprecation-and-fetch-on-mount.md
load_when: [antd bodyStyle deprecation, antd 5.x Card styles, fetchDevices on mount, empty dropdown direct navigation, zustand store not populated, HMR timing bug]
priority: low
symptom: [kb:lesson:n144, antd-bodystyle-deprecated, fetch-on-mount, store-empty-direct-nav]
solution: 'antd 5.x Card bodyStyle 已弃用, 改用 styles={{ body: {...} }}。直接进子页面时 zustand store 可能未被其他页触发 fetch, 子页面需在 mount 时 useEffect 主动 fetch (devices.length === 0 guard)。Playwright 验证时注意 antd 5.x 用 .ant-select-placeholder 而非 .ant-select-selection-placeholder。'
related_files:
  - frontend/src/pages/Resources/TemplateAnnotation/LiveAnnotationTab.tsx
  - frontend/src/stores/useDeviceStore.ts
created_by: AI
date: 2026-07-05
generated: 2026-07-05
l2_candidate: true
level: L1
n_id: N144
topic: version-compat
---

# N144: R37-P3 C5 — antd 5.x bodyStyle 弃用 + 直接进子页 store 空 (L0 历史记录)

> **触发**: "继续吧, 但五层分发是不是有点太多了..." (用户要求评估 5 层分发简化 + 继续 R37-P3)
> **时间**: 2026-07-05 | **commit**: `-` (C5 修复)
> **影响**: antd Console 警告 bodyStyle deprecated; 直接进 /template-annotation 时设备 Select 下拉为空

## 1. 问题 (Problem)

R37-P3 C5 Playwright 验证发现两个回归:

### 1a. antd 5.x bodyStyle 弃用警告

Console 输出:
```
Warning: [antd: Card] `bodyStyle` is deprecated. Please use `styles.body` instead.
```

原代码 (`LiveAnnotationTab.tsx` L729):
```tsx
<Card size="small" style={{ width: 400, flexShrink: 0 }}
  className="gaf-overflow-auto"
  bodyStyle={{ padding: 0 }}>
```

### 1b. 直接进 /template-annotation 时设备 Select 为空

导航到 `http://localhost:5173/template-annotation` 时, 设备 Select 显示 placeholder "选择设备" 但无选项。API 返回 200 (devices 存在), 但 `useDeviceStore.devices` 仍为空数组。

## 2. 根因 (Root Cause)

### 2a. antd 5.x API 变更

antd 5.x 中 `Card.bodyStyle` 已弃用, 改用 `styles.body`。这是公开 API 变更, 无可复用 Y/N 价值 (antd 升级时统一处理)。

### 2b. zustand store 未被触发 fetch

`useDeviceStore.fetchDevices` 只在其他页面 (如 DeviceCenterPage) mount 时调用。直接进 `/template-annotation` 时, 没有其他页触发 fetch, store 为空。

**HMR 时机**: C5 修复刚写入时, Vite HMR 未立即应用, 导致前一会话 Playwright 验证仍见空。本会话重跑 (文件已保存) 即通过。

## 3. 修复 (Fix)

### 3a. bodyStyle → styles.body

```tsx
// Before
<Card bodyStyle={{ padding: 0 }}>

// After
<Card styles={{ body: { padding: 0 } }}>
```

### 3b. mount 时主动 fetchDevices

```tsx
const devices = useDeviceStore((s) => s.devices);
const fetchDevices = useDeviceStore((s) => s.fetchDevices);

// Ensure device list is loaded when this tab mounts (R37-P3 C5 fix).
// Without this, navigating directly to /template-annotation shows an empty device dropdown
// because no other page has populated the store yet.
useEffect(() => {
  if (devices.length === 0) {
    void fetchDevices();
  }
}, [devices.length, fetchDevices]);
```

## 4. 验证 (Verification)

Playwright 脚本 (`临时验证脚本 (已删除)`) 重跑结果:
- ✅ Login OK
- ✅ Device Select placeholder='选择设备', **2 options available** (BrownDust II + LDPlayer)
- ✅ Selected device: BrownDust II
- ✅ Device Ops Tab 渲染 DeviceOperationPanel 9 子 Tab (点击/按键/文本/滑动/滚动/模板匹配/应用/信息/历史)
- ✅ Console errors: 1 (仅 manual probe 的 401, 已过滤)
- ✅ PASS: No real console errors

**Playwright 脚本踩坑**: antd 5.x 用 `.ant-select-placeholder` 类, 不是 `.ant-select-selection-placeholder`。脚本原用后者导致找不到 placeholder, 无法打开下拉。已修复脚本 selector。

## 5. N95 v8.5 分级分发判定

本教训按 N95 v8.5 判定流程分级:

| 问题 | 影响全局硬约束? | 能转化为 Y/N 检查清单? | 分级 |
|------|:---:|:---:|:---:|
| antd bodyStyle 弃用 | ❌ (公开 API 变更) | ❌ (一次性升级) | **L0** |
| fetchDevices mount | ❌ (常规 React 模式) | ❌ (case-by-case) | **L0** |
| Playwright selector | ❌ | ❌ (antd 版本特定) | **L0** |

**结论**: 全部 L0, 仅写 lessons/ 一层。

**不做的分发** (N95 v8.5 简化核心):
- ❌ 不更新 `.ai-memory/summaries/architecture-mistakes.md`
- ❌ 不更新 `.ai-memory/meta/yn-matrices.md`
- ❌ 不更新 `project_rules.md` §6.4 索引表
- ❌ 不更新 SKILL.md

## 6. 关联 (Related)

- **N95 v8.5**: 分级分发简化 (commit `-`) — 本教训是 v8.5 上线后首次走 L0 路径的实例
- **N142**: copy-paste 重命名 (前一会话) — 同批 R37-P1 C6 教训
- **N143**: 认证图片 blob fetch (前一会话) — 同批 R37-P1 C6 教训
- **R37-P3**: P-005 设备操作迁移到标注界面 (本批 C1-C5)
