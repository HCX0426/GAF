# spec-context: 2026-08-18-s39-sync-skills-split

> s39 = TD-365 6/9，大文件拆分治理（sync_skills.py 1064 行）。用户指令："继续"（s38 后 L3-4 连续 2 spec 硬终止点报告，用户授权继续）。

## 1. 用户决策原文

- "继续"（2026-08-18，s38 完成后询问"要继续 s39 吗"，用户授权继续循环）
- 前置（s38 期间，2026-08-17）："剩下任务还有多少" → 展示 TD-365 剩余 3 个 → 用户选 sync_skills.py

## 2. N151 5 步法评估

1. **架构盘点**：
   - 数据：sync_skills.py 1064 行纯脚本，无 DB 依赖
   - 依赖：constants（模块级常量+正则）被 10+ 函数使用；工具函数（_read_text/_write_text/_block_hash 等）被 checks/changelog/timestamps/main 交叉使用；main() 依赖全部域
   - 调用：governance batch（bootstrap.sync_skills main --check）、gaf_init.sh、4 个测试文件（from sync_skills import ... 顶层 hack）、无前端/agent 依赖
   - 历史：s38（sync_ai_memory.py）刚闭环，N202 ⑰⑱ 检查项现成
2. **识别反模式**：单文件 6 域混合（constants/checks/io/inspect/changelog/timestamps/main），无架构缺陷——纯大文件治理（TD-365 范围内）
3. **A/B/C 备选**：
   - A（采纳）：skill_sync/ 域包 5 模块 + 主文件瘦身——子模块零主文件依赖（无循环）+ 相对导入（无双模块）+ re-export（API 不变）
   - B：s38 模式（子模块 `_main.` 运行时常量）——可行但 10+ 常量全走运行时访问，代码更丑；s38 需要是因为工具函数无法独立于主文件，s39 的常量可以移出 → 不需要
   - C：只移 changelog/timestamps 两个命令域（最小拆分）——主文件仍 ~800 行，不达阈值目标，治标不治本
4. **拒绝反模式**：拒绝 C（最小化修补——主文件仍超标）；拒绝"保留双套"（无新旧并存需求）
5. **AI 自决**：A 方案（7 维度评分后自决，见下）

## 3. N167 七维度评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 1 架构长远性 | 5 | 域包边界清晰，后续按域演进 |
| 2 全局归一化 | 5 | 对齐 s38 ai_memory_sync/ 模式（包名风格/注册/re-export 统一） |
| 3 新旧兼容 | 5 | re-export 全符号 → 测试/governance/脚本零改动 |
| 4 现有业务完善 | 5 | CLI/API 行为逐字节不变 |
| 5 性能资源优化 | 4 | import 开销可忽略（模块缓存） |
| 6 安全合规 | 5 | 无新权限面 |
| 7 长期维护成本 | 5 | 457 行主文件 + 域模块各自独立演进 |
| **总分** | **34/35** | ≥ 19 且领先 ≥ 5 → AI 自决 |

## 4. 关键实施决策（D1-D4）

- **D1 parents 层级**：切块复制到子目录后 `Path(__file__).resolve().parents[N]` 需 +1（constants.py `parents[2]`→`parents[3]`）。检查项：拆分后所有 parents 常量重新计算。
- **D2 import 补全**：changelog.py 补 `import re`；checks.py 补 `_read_text`；主文件补 `import hashlib`。检查项：切块后 grep 子模块使用的每个名字。
- **D3 ruff 删 re-export（最深坑）**：裸 `from-import` re-export 被 ruff F401 判定 unused → `ruff check --fix` **直接删除绑定** → 测试 ImportError。s38 幸免因 re-export 在 try 块内（ruff 不报 try 内 import）。修复：`# noqa: E402, F401` 每行标注。检查项：re-export 必须 noqa F401。
- **D4 monkeypatch 持有者**：`from X import Y` 是绑定复制——patch 主文件 re-export 绑定不影响子模块自身绑定。修复：① 消费方改模块属性访问（`from . import constants as _constants` + `_constants.TIMESTAMP_SKILLS`）② 测试 patch `skill_sync.constants`（真实持有者）。检查项：跨文件共享常量被 patch 时目标 = 定义模块。

## 5. 反思（commit 后 §4.6 4 问）

1. **本轮要做什么？** s39 拆分 sync_skills.py（1064 → 457 行）到 skill_sync/ 5 域包，TD-365 6/9。范围：纯结构拆分，零功能变化。
2. **可复用**：N202 ⑰⑱ 检查项（s38）；拆分脚本模式（s38 splitter 的 rfind 定位 + 区间切块）；子模块零依赖设计。
3. **风险与依赖**：① ruff --fix 会删 re-export（D3，实际踩中）② monkeypatch 绑定复制（D4）③ parents 层级（D1）④ governance 上下文 sys.path 差异（bootstrap 段双目录）。
4. **验收标准**：457 行 ✅ / 25 passed ✅ / governance 13/13 ✅ / 580 passed ✅ / re-export 45 符号 ✅ / TD-365 6/9 ✅。
5. **新教训**：D1-D4 全部纳入 N202 ⑲-㉓（5 项新增检查清单）。"无 A 类"检查：已检查 N178-A1 反向论证（无）/A2 评分合理化（A 方案 34/35 客观领先）/A3 过度治理（拆分是 TD-365 明确任务，非扩张）/A4 范围扩张（零功能变化，未引入新依赖）。
