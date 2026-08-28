---
date: 2026-08-28
symptom: [window-device-stale-hwnd, title-changes, browser-restart-hwnd, no-window-handle]
solution: 浏览器/游戏窗口设备不能靠固定 title 或固定 hwnd 锚定——执行时实时匹配（子串/进程名）+ 缓存 hwnd 失效即强制重连重绑
related_files:
  - agent/src/client/handler.py
  - agent/src/platforms/windows/window.py
  - agent/tests/test_handler_window_reconn.py
created_by: AI
priority: medium
n_id: N211
diff_keywords: ["window", "hwnd", "window_title", "窗口", "重连", "device"]
---

# 窗口设备动态绑定：页面标题会变、句柄随重启变

## 症状（2026-08-28 用户提问引发）

GAF 的 Chrome 窗口设备曾出现"uia: no window handle on device"：Chrome 标题是 UI 快照（每次页面导航都变）、hwnd 每次重启浏览器都变，**静态记录必然过期**。

## 根因

设备缓存保存的是"上一次看到"的 window_title 与 hwnd；agent 匹配到缓存设备后若认为仍 CONNECTED 就不重连，于是拿着失效句柄执行 → 任何 UIA/截图节点都失败。窗口查找本身没问题（EnumWindows + 子串匹配能命中），问题在**缓存与现实的失效同步缺失**。

## 解决方案（已实现，commit -）

1. **title 刷新**：`_resolve_target_device` 命中缓存设备时，用后端下发的最新 window_title 覆盖缓存（页面导航后仍能按新标题找到窗口）
2. **hwnd 失效重连**：`_ensure_device_connected` 对 Windows 设备检查 `is_window(cached_hwnd)`，失效则 `disconnect()` → 重新 `connect()`（按当前 title 重绑）
3. 匹配支持多锚：window_title（子串）/ name / hwnd / process_name / class（window.py `find_window` 已具备；设备绑定可从 title 演进到 process_name 更稳）
4. 单测：`test_handler_window_reconn.py` 覆盖 stale-hwnd 重连 / 新鲜 hwnd 不重连 / 标题刷新 4 场景

## 泛化原则

凡"快照式绑定"（按创建时看到的静态 key 定位运行时对象）都要有失效检测：运行时对象可变化（标题/hwnd/pid/会话），绑定时需记录 + 校验 + 重绑三步，不能只验一次。