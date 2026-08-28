# spec-72: TD-306 why-skipped.md 加 24h dedup 机制 + 清理历史

> **触发**: spec-71 ✅ 后循环模式 N166 L3-2 主动接修 (不问"继续?")
> **循环模式第 13 spec**
> **规模**: 小修改 (run_all.py +30 行 + why-skipped.md 清理 233→7 行 + active/fixed 文档)
> **七维度评分**: 豁免 (小修改 < 50 行)

## 一、问题根因

### why-skipped.md 累积重复
- **症状**: `.ai-memory/ops/why-skipped.md` 233 行, 4 类相同错误 (cold_start/browser_login/devices_control_mode/ai_qa_chat) 重复 20+ 次, 每次只是时间戳不同
- **根因**: `scripts/e2e/run_all.py:_write_why_skipped` 函数纯 append 模式, 写入前不检查 24h 内是否已有同 scenario 记录
- **影响**: 文件膨胀但不阻塞功能; 真正可修复的失败被淹没在重复日志中

### "真实可修复的失败转 lessons/" 评估
- 评估结论: **wontfix** — 现有 why-skipped.md 中的失败全部是环境问题 (服务未启动/索引未生成/session 缺失), 不是代码 bug
- cold_start: session not found — 环境问题 (跑 gaf_init.sh 即可)
- browser_login/devices_control_mode/ai_qa_chat: ERR_CONNECTION_REFUSED — 环境问题 (前端未启动)
- 无真实可修复的失败需转 lessons/

## 二、修复方案

### 方案 A: 加 24h dedup 机制 + 清理历史 ✅ 采用
- 加 `WHY_SKIPPED_DEDUP_HOURS = 24` 常量
- 加 `_recent_why_skipped_scenarios(target, hours)` 辅助函数: 解析 why-skipped.md, 返回最近 `hours` 内已记录的 scenario 集合
- 修改 `_write_why_skipped`: 写入前调用 dedup, 过滤掉 24h 内已有的 scenario, 若 new_failures 为空则跳过 append
- 清理现有 why-skipped.md: 233 行 → 7 行 (保留文件头说明, 删除全部历史记录)

### 方案 B: 用 (scenario, detail_hash) 双 key dedup — 未采用
- 更精确 (同 scenario 不同 detail 也记录), 但 detail 包含时间戳/路径, hash 不稳定
- 权衡: scenario 级 dedup 已足够 (环境问题同 scenario 重复是主要问题)

### 方案 C: 加 --clean CLI 参数一次性清理 — 未采用
- run_all.py main 是 e2e 运行器, 不适合加 --clean 参数
- 清理现有文件用一次性 Write 即可

## 三、修改清单

### 3.1 scripts/e2e/run_all.py (+30 行)

**新增 imports**:
- `import datetime`
- `import re`

**新增常量**:
- `WHY_SKIPPED_DEDUP_HOURS = 24`

**新增函数**:
- `_recent_why_skipped_scenarios(target, hours=24)`: 解析 why-skipped.md, 返回最近 `hours` 内已记录的 scenario 集合

**修改函数**:
- `_write_why_skipped`: 写入前调用 `_recent_why_skipped_scenarios` 过滤, 若 new_failures 为空则跳过 append

### 3.2 .ai-memory/ops/why-skipped.md (清理 233→7 行)

- 删除全部历史记录 (233 行, 2026-06-17 ~ 2026-07-20)
- 保留文件头说明 + TD-306 dedup 机制说明

### 3.3 文档

**`docs/general/tech-debt/active.md`**:
- TD-306 段落迁出 (迁移到 fixed.md)
- 顶部计数: `3 (TD-294/305/306)` → `2 (TD-294)`
- 下一 spec 触发: TD-306 → TD-294

**`docs/general/tech-debt/fixed.md`**:
- 追加 TD-306 ✅ FIXED 段落 (含根因 + 修复方案 + wontfix 评估 + 验证 + 教训)

## 四、验证 (Phase 2 ✅)

```powershell
# 1. 导入测试
PS> conda run -n gaf python -c "from scripts.e2e.run_all import _write_why_skipped, _recent_why_skipped_scenarios, WHY_SKIPPED_DEDUP_HOURS; ..."
recent (should be empty): set()
DEDUP_HOURS: 24
OK imports + function callable

# 2. 真实 e2e 跑 (服务未启动, 4 failed 但 _write_why_skipped 被调用)
PS> conda run -n gaf python -m pytest scripts/tests/test_e2e_run_all.py -q
4 failed, 13 passed in 17.11s
(failures written to .trash/.e2e-failures.log + ops/why-skipped.md)

# 3. dedup 验证 (第二次调用同 scenario, 文件未改变)
PS> conda run -n gaf python -c "..."
recent scenarios (should have 4): ['ai_qa_chat', 'browser_login', 'cold_start', 'devices_control_mode']
file unchanged (dedup worked): True
```

- why-skipped.md: 233 行 → 7 行 (清理后) ✅
- dedup 机制: 同 scenario 24h 内只记 1 次 ✅
- "真实可修复的失败转 lessons/": wontfix (无代码 bug) ✅

## 五、反思 (§4.6 反思矩阵)

### ① 循环模式 N166 L3-2 ✅
spec-71 ✅ 后主动接修 spec-72 (TD-306), 未问"继续?", 符合 spec-68 强化的循环模式规则。

### ② TD 描述行数不准确 ①
- **症状**: TD-306 原描述"365+ 行", 实际 233 行
- **根因**: TD 登记时未用 `wc -l` 精确计数, 凭印象写"365+"
- **教训**: TD 描述涉及具体数字时必须用命令验证, 不凭印象。已在 fixed.md TD-306 段落修正为"233 行 (原描述 365+ 行, 实际 233 行)"

### ③ "真实可修复的失败转 lessons/" wontfix 评估 ✅
- TD-306 原修复方案第 3 项"真实可修复的失败转 lessons/ 归档"
- spec-72 评估: 现有失败全是环境问题 (服务未启动/索引未生成), 无代码 bug
- 评估结论 wontfix, 在 fixed.md TD-306 段落明确记录, 避免后续 spec 重复评估

### ④ append 模式必须配 dedup ①
- **症状**: _write_why_skipped 纯 append 模式导致 233 行重复
- **根因**: append 模式设计时未考虑重复触发场景 (e2e 多次跑同 scenario 失败)
- **教训**: 任何 append 模式的日志/记录文件, 必须配 dedup 机制 (时间窗口或内容 hash), 否则环境问题重复触发会无限膨胀
- **沉淀**: 已在 fixed.md TD-306 段落记录教训

### ⑤ 反思清单 24 项 Y/N
- ✅ 改动范围由正确性决定 (加 dedup 是核心需求, 非最小改动)
- ✅ 根因修复 (加 dedup 机制, 非仅清理历史)
- ✅ 验证通过 (导入 + 真实 e2e + dedup 验证 3 重)
- ✅ 文档同步 (active/fixed 顶部计数 + 段落迁移)
- ✅ 教训沉淀 (append 模式必须配 dedup)
- 其余 19 项 N/A (本次为工具脚本 + 文档, 不涉及 DB/迁移/API 契约)

## 六、commit

```
fix(spec-72): TD-306 why-skipped.md 加 24h dedup 机制 + 清理 233 行历史 (run_all.py +30 行 + 文件清理 233→7 行)
```

文件清单:
- `scripts/e2e/run_all.py` (+30 行: import datetime/re + WHY_SKIPPED_DEDUP_HOURS + _recent_why_skipped_scenarios + _write_why_skipped dedup)
- `.ai-memory/ops/why-skipped.md` (清理 233 行历史 + 加文件头说明)
- `docs/general/tech-debt/active.md` (TD-306 迁出 + 顶部计数 3→2 + 下一 spec TD-294)
- `docs/general/tech-debt/fixed.md` (追加 TD-306 ✅ FIXED 段落)
- `.trae/specs/2026-07-21-spec72-td306-why-skipped-dedup.md` (本 spec 文件)
