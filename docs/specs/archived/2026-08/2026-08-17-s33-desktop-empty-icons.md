# s33 — desktop 空图标实装 (icon.ico / icon.png / tray-icon.png 0 字节)

> **类型**: fix (功能缺陷) | **日期**: 2026-08-17 | **来源**: 用户"继续" → monthly_health_check 扫描发现 n1_empty 维度报 3 个 0 字节图标文件
> **状态**: ✅ 已归档 (2026-08-17, commit -) | **归档位置**: `docs/specs/archived/2026-08/2026-08-17-s33-desktop-empty-icons.md`
> **关联**: monthly_health_check.py n1_empty 维度 (2026-08 引入) / desktop Electron (tray.ts / window.ts / electron-builder.yml)

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit hash | 验收 evidence |
|------|------|---------|------------|--------------|
| Phase 1 生成 icon.png (256) + tray-icon.png (32) + icon.ico (多尺寸) | ✅ | 2026-08-17 | - | 3 文件非零 (4457/577/15339 bytes); PIL 可打开; ICO 6 尺寸 (16-256) |
| Phase 2 验证图标有效 | ✅ | 2026-08-17 | - | 中心白 G + 品牌紫 #863bff + 圆角透明; 托盘 96% 非透明; 引用路径匹配 (tray.ts/window.ts/electron-builder.yml) |
| Phase 3 commit + 归档 | ✅ | 2026-08-17 | - | 6 文件 76+/1-; pre-commit 10 hooks 全过; TD-365 登记 (9 个大文件拆分治理) |

## 背景与根因

**现象**: `monthly_health_check.py` n1_empty 维度报 3 个 0 字节文件:
- `desktop/resources/icon.ico` (0 bytes)
- `desktop/resources/icon.png` (0 bytes)
- `desktop/resources/tray-icon.png` (0 bytes)

**根因**: desktop Electron 应用搭建时创建了占位图标文件但从未实装内容 (git 追踪的空文件)。

**影响面** (代码引用验证):
- `desktop/src/main/tray.ts:12` — `tray-icon.png` → `new Tray(icon)` 加载空文件 → 托盘图标空白
- `desktop/src/main/window.ts:19` — `icon.png` → BrowserWindow icon → 窗口图标空白
- `desktop/electron-builder.yml:25,30-32` — `icon.ico` (build/installer/uninstaller/header icon) → 打包时 0 字节 ICO 导致 electron-builder 失败或无图标 exe
- `icon.ico` 无代码引用 (仅打包配置引用)

**品牌源**: `frontend/public/favicon.svg` 有 GAF 品牌标识 (紫色 `#863bff` G 形 logo)。SVG 含复杂 mask/filter/ellipse, cairosvg 在 Windows 缺 cairo DLL 无法渲染。采用**简化品牌图标**: 紫色圆角方块 + 白色 G 字母 (PIL + Arial Bold)。

## Phase 1 详细任务

生成 3 个文件 (脚本放 `.trash/`, 一次性):
1. `desktop/resources/icon.png` — 256x256 RGBA: 品牌紫 `#863bff` 圆角方块 + 白色粗体 G
2. `desktop/resources/tray-icon.png` — 32x32 (tray.ts resize 到 16x16, 32 源更清晰)
3. `desktop/resources/icon.ico` — 多尺寸 (16/32/48/64/128/256)

## 验收标准

1. 3 文件均非零字节; PIL 可打开且尺寸正确
2. `git status` 显示 3 文件 Modified (0 → N bytes)
3. monthly_health_check n1_empty 维度不再报这 3 个文件
4. 引用路径验证: tray.ts/window.ts/electron-builder.yml 指向的文件均已实装

## 已知限制

- 图标为简化版 (非 favicon.svg 精确复刻) — SVG 含 mask/filter 效果, PIL 无法精确重现; 未来若引入 SVG 渲染管线可替换
- 不引入新依赖 (cairosvg 缺 Windows cairo DLL; svglib 不在环境) — 纯 PIL + 系统字体
- `n1_empty` 维度本身无缺陷 (正确报出空文件), 不修改检查器