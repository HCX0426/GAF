---
date: 2026-08-28
symptom: [e2e-429-false-red, throttle-300, cv2-matchtemplate-flat, ldplayer-dual-view, emulator-5554, device-dedup]
solution: E2E 造数/环境四坑——全量测试自造 429（先查 throttle 额度/调宽或分散节奏）；cv2.matchTemplate 测试图必须带纹理（纯色模板病态 1.0 置信度）；雷电模拟器 ldconsole(127.0.0.1:5555) 与 adb(emulator-5554) 是同一实例别名勿重复注册；清理遗留假设备
related_files:
  - backend/config/settings/base.py
  - scripts/e2e/scenarios/full_routes.py
  - backend/resources/views.py
  - backend/workers/view_sets/scan_register.py
created_by: AI
priority: medium
n_id: N214
diff_keywords: ["throttle", "matchTemplate", "emulator-5554", "ldconsole", "adb_serial", "429", "register"]
---

# E2E 环境造数与测试数据四坑（429 假红 / 纯色模板 / 模拟器双视角 / 设备表卫生）

## 症状（2026-08-28 全量 E2E + 匹配预览 + 模拟器补测）

1. `full_routes` 中途系统页（api-keys/users/me/task-stats 等）批量 429，页面判定 FAIL——**测试自身把后端 throttle 打爆了**。
2. 模板匹配端点第一次实测全部 confidence=1.0 且框乱飞，无法验证坐标召回。
3. 打开一个雷电模拟器，`scan?type=android` 返回**两条**设备（ldconsole 视角 `127.0.0.1:5555` + adb 视角 `emulator-5554`），误当成两台注册 → 多了一条重复在线设备；用户质疑"哪来的真机"。
4. 预检总被一条"离线"遗留设备（dbg-dev，绑定不存在的 dbg-agent）阻塞。

## 根因

1. DRF `DEFAULT_THROTTLE_RATES user=300/min`：full_routes 80s 内遍历 46 页（每页多请求）远超 300 → 尾部被限流。这是**健康测试自造假红**，非产品 bug（M2 已把 monitors/status 429 静默，但其它端点暴露）。
2. `cv2.matchTemplate` 对**恒定/纯色区域**（纯灰背景 + 纯红方块）归一化系数病态：模板方差为 0 → CCOEFF 除以 0 → 全图 1.0。测试图太"干净"。
3. 雷电模拟器同时暴露两个 adb 身份：ldconsole 报告的 adb 端口（`127.0.0.1:5555`）与 `adb devices` 列表名（`emulator-5554`，device 型号 RMX6688 + tag `unicorn`）——**是同一实例**，扫描器把两个来源合并成两条。
4. 历史测试环境残留设备（如绑定已删除 agent 的假设备）一直离线，让"全部设备在线"永远失败。

## 解决方案（已实现）

1. `user: 600/min`（登录仍 5/min 防爆破）+ full_routes 路由间隔 1500→2200ms 分散请求 → 429 消失。教训：跑全量测试前先查 throttle 额度，测试自身超限 = 调宽或放慢，不要当 bug 修产品。
2. 匹配端点造图用随机纹理底 + 嵌入独特纹理块 → 坐标精确召回（120,60 / conf 1.0）。教训：写 cv2 匹配测试用带纹理数据。
3. 设备注册按 `adb_serial` 归一：统一为 `adb devices` 的官方名（emulator-5554）；用 `Device.objects.filter(name+type)` 去重；已误注册的重复设备删除。教训：模拟器"双视角"识别后合并为一条。
4. 删除遗留假设备（dbg-dev）→ 预检 `device_online=pass`。教训：E2E 前清设备表，避免离线假设备阻塞链路。

## 泛化原则

做 E2E 造数/环境准备时四查：① throttle 限额是否可能被测试请求总量打爆（先查设置再开跑）；② 模板匹配/识别类测试数据要有真实纹理；③ 设备扫描的多数据源（ldconsole/adb/窗口枚举）先归一再去重；④ 数据库遗留假记录（绑定已删 agent）定期清理，避免假离线阻塞预检。