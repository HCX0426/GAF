# spec-71: TD-305 session-context.md 数据陈旧 + 缺 stale 校验

> **触发**: spec-70 ✅ 后循环模式 N166 L3-2 主动接修 (不问"继续?")
> **循环模式第 12 spec**
> **规模**: 中修改 (sync_session_context.py +60 行 + session-context.md 重新生成 + active/fixed 文档)
> **七维度评分**: 跑核心 3 维 — 1 架构长远性 ✅ / 2 全局归一化 ✅ / 7 长期维护成本 ✅ (加 stale 校验防再次陈旧)

## 一、问题根因 (spec-71 重新评估)

### 原描述 vs 实际根因
- **原描述**: "sync_session_context.py app 枚举逻辑 bug (未排除 core/docs + 未加 gaf_ai/device_bridge)"
- **实际根因**: 文件陈旧 — 2026-07-12 生成后, 经历 `core`→`gaf_core` 重命名 + `docs` app 删除 + `gaf_ai` 新增, 但 sync_session_context.py 未重新运行
- **代码验证**: `_backend_apps()` 函数动态扫描 `backend/*/apps.py`, 无硬编码 app 列表, 没有"未排除/未加" bug

### device_bridge 评估
- TD-305 原描述"缺 device_bridge 2 个真实 app"不准确
- `backend/device_bridge/` 没有 `apps.py`, 不在 `INSTALLED_APPS`, 是工具模块集合而非 Django app
- 不应出现在 session-context.md 的 Backend Apps 列表中

### 真正缺失
- 无 last_updated stale 校验机制, 文件陈旧无法自动报警
- gaf_init.sh --full 才会重新生成, 日常开发不跑 gaf_init.sh 时文件会持续陈旧

## 二、修复方案

### 方案 A: 重新生成 + 加 --check-stale CLI 参数 ✅ 采用
- 重新运行 `sync_session_context.py` 基于当前文件系统生成正确 app 列表
- 加 `--check-stale` 参数: CI 友好的 stale 检测 (> 7 天 → exit 1), 不写文件
- 默认行为加 stale warning: 生成新文件前检测旧文件, 若 > 7 天 stale, 打印 WARNING
- 加 `STALE_THRESHOLD_DAYS = 7` 常量 + 3 个辅助函数 (`_parse_last_updated` / `_existing_file_age_warning` / `_check_stale_only`)

### 方案 B: 加 pre-commit hook 自动同步 — 未采用
- 每次 commit 自动跑 sync_session_context.py
- 权衡: 增加 commit 耗时, 且非所有 commit 都影响 session-context.md 内容

### 方案 C: 加 CI 定时任务 — 未采用
- GitHub Actions 每天跑 `sync_session_context.py --check-stale`
- 权衡: GAF 项目无 CI 流水线, 不适用

## 三、修改清单

### 3.1 sync_session_context.py (+60 行)

**新增**:
- `import argparse`
- `STALE_THRESHOLD_DAYS = 7` 常量
- `main()` 改为 argparse + `--check-stale` 分支
- `_parse_last_updated(text)`: 从 frontmatter 解析 last_updated 日期
- `_existing_file_age_warning()`: 检测旧文件 stale 状态, 返回 warning 字符串
- `_check_stale_only()`: CI 友好的 stale 检测, exit 1 if stale/missing

### 3.2 .ai-memory/session-context.md (重新生成)

- last_updated: 2026-07-12 → 2026-07-21
- Backend Apps: 移除 `core`/`docs`, 加入 `gaf_ai`/`gaf_core` (22 apps)
- Active Tech Debt: TD-085/086/087 → TD-294/305/306 (3 active)
- Recent Commits: 更新为 spec-65~70 commit 链

### 3.3 文档

**`docs/general/tech-debt/active.md`**:
- TD-305 段落迁出 (迁移到 fixed.md)
- 顶部计数: `4 (TD-294/305/306)` → `3 (TD-294/305/306)` (修正 spec-70 Phase 4 计算错误)
- 下一 spec 触发: TD-305 → TD-306

**`docs/general/tech-debt/fixed.md`**:
- 追加 TD-305 ✅ FIXED 段落 (含根因重新评估 + device_bridge 评估 + 修复方案 + 验证 + 教训)

## 四、验证 (Phase 2 ✅)

```powershell
PS> conda run -n gaf python scripts/bootstrap/sync_session_context.py
✅ session-context.md generated: D:\code\GAF\.ai-memory\session-context.md
   - branch: main
   - backend apps: 22
   - active TD: 3
   - active roadmap: 0

PS> conda run -n gaf python scripts/bootstrap/sync_session_context.py --check-stale
✅ D:\code\GAF\.ai-memory\session-context.md is fresh (last_updated: 2026-07-21, 0 days old).
```

- session-context.md app 列表: 22 apps, 无 core/docs, 含 gaf_ai/gaf_core ✅
- session-context.md Active TD: TD-294/305/306 (与 active.md 一致) ✅
- last_updated: 2026-07-21 (当天) ✅
- `--check-stale` exit 0 ✅

## 五、反思 (§4.6 反思矩阵)

### ① 循环模式 N166 L3-2 ✅
spec-70 ✅ 后主动接修 spec-71 (TD-305), 未问"继续?", 符合 spec-68 强化的循环模式规则。

### ② TD 描述基于表象而非根因 ①
- **症状**: TD-305 原描述"app 枚举逻辑 bug (未排除 core/docs + 未加 gaf_ai/device_bridge)", 实际 `_backend_apps()` 是动态扫描, 无硬编码
- **根因**: TD 登记时基于表象 (看到 core/docs 出现 + gaf_ai 缺失) 推测代码 bug, 未读代码验证
- **教训**: spec 修复时必须重新评估根因, 不盲目按原描述修。本次通过读 sync_session_context.py 代码发现原描述不准确, 修正为"文件陈旧 + 缺 stale 校验"
- **沉淀**: 已在 fixed.md TD-305 段落记录教训

### ③ device_bridge 评估 ✅
- TD-305 原描述"缺 device_bridge 真实 app", 实际 device_bridge 无 apps.py, 不是 Django app
- 通过 `INSTALLED_APPS` 检查 + 文件系统结构确认, device_bridge 是工具模块集合
- 避免了"强行给 device_bridge 加 apps.py"的错误修复

### ④ N167 七维度 (3 维核心) ✅
- 1 架构长远性: `--check-stale` 提供长期 stale 检测能力, 不依赖人工记忆
- 2 全局归一化: sync_session_context.py 与 session-context.md 保持一致 (动态扫描 + 重新生成)
- 7 长期维护成本: 消除"文件陈旧误导 AI L2 加载"风险, stale warning 提示开发者重新生成

### ⑤ 反思清单 24 项 Y/N
- ✅ 改动范围由正确性决定 (加 stale 校验是核心需求, 非最小改动)
- ✅ 根因修复 (重新生成 + 加检测, 非仅重新生成)
- ✅ 验证通过 (2 命令均 exit 0)
- ✅ 文档同步 (active/fixed 顶部计数 + 段落迁移)
- ✅ 教训沉淀 (TD 描述基于表象的教训记入 fixed.md)
- 其余 19 项 N/A (本次为工具脚本 + 文档, 不涉及 DB/迁移/API 契约)

## 六、commit

```
fix(spec-71): TD-305 session-context.md 数据陈旧修复 (重新生成 + 加 --check-stale 校验) + 修正 active.md 计数 4→3
```

文件清单:
- `scripts/bootstrap/sync_session_context.py` (+60 行: argparse + --check-stale + 3 辅助函数)
- `.ai-memory/session-context.md` (重新生成: 22 apps + 3 active TD + 2026-07-21)
- `docs/general/tech-debt/active.md` (TD-305 迁出 + 顶部计数 4→3 + 下一 spec TD-306)
- `docs/general/tech-debt/fixed.md` (追加 TD-305 ✅ FIXED 段落)
- `.trae/specs/2026-07-21-spec71-td305-session-context-stale.md` (本 spec 文件)
