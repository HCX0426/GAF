# s38 spec-context — sync_ai_memory.py 拆分（TD-365 batch 5）

> 承载体（TD-342 硬约束）：用户决策 + N151/N167 评估 + N173 用时 + 实施决策 + 教训。

## 1. 用户决策原文

- "继续"（循环模式强触发，s37 完成后直接推进下一个 TD）→ 本轮 TD-365 剩余 4 个中选 `sync_ai_memory.py`（1384 行，scripts 层第一个，调用契约最复杂——先啃硬骨头）。

## 2. N151 5 步法评估

1. **架构盘点**：sync_ai_memory.py = 6 功能域（frontmatter/collect/semantic/state/mtime_cache/counters/main），35 函数 + 15 常量；3 条调用契约（CLI/importlib/governance batch）；测试以 sys.path hack 导入 + patch 2 个模块属性。
2. **识别反模式**：1384 行超阈值；域间耦合仅 collect → parse_front_matter 单向；mtime_cache/counters 完全独立（可整域移出）。
3. **A/B/C 备选**：
   - A（采纳）：整域移出 3 个独立域（15 函数）+ 主文件 re-export + try 双路径 import + 无条件模块名注册。主文件 910 行。
   - B：全部 6 域都拆（含 frontmatter/state/semantic）→ patch 契约破坏（yaml/REPO_ROOT_DEFAULT 移出后 patch 失效），需重写测试 → 高风险。
   - C：只拆 counters 一个域（3 函数）→ 主文件 ~1280 行仍超阈值，不达标。
4. **拒绝反模式**：拒绝 B（patch 契约优先，测试为契约的一部分）；拒绝 C（不达标）。
5. **AI 自决边界**：A 方案总分最高（见 §3），AI 自决采纳。

## 3. N167 七维度评分

| 维度 | A | B | C |
|------|---|---|---|
| 1 架构长远性 | 5（域边界 = 调用图边界） | 3（过度拆分） | 2 |
| 2 全局归一化 | 5（子包模式与 s35/s36 一致） | 2 | 2 |
| 3 新旧兼容 | 5（函数名/signature 不变 + re-export） | 1（patch 失效） | 4 |
| 4 现有业务完善 | 5（行为零变化） | 2 | 5 |
| 5 性能资源优化 | 4（import 开销 ~0.1s 一次性） | 2 | 5 |
| 6 安全合规加固 | 3（不涉及） | 3 | 3 |
| 7 长期维护成本 | 5（主文件 910 达标） | 2（测试重写成本） | 3 |
| **总分** | **32** | 15 | 24 |

A 总分 32 ≥ 19 且领先 B（15）+17 分 → AI 自决（§0.5 step 6）。

## 4. 关键实施决策（D1-D3）

- **D1（N202 ⑰）**：re-export 段必须插在 `if __name__ == "__main__"` 入口点**之前**——拆脚本最初把段追加到文件末尾（在入口点之后）→ main() 先执行 → NameError `_sync_lessons_readme_count`。修复：`rfind` 定位入口点块插入。
- **D2（N202 ⑱）**：两层根因——① 同一文件 4 种模块名加载上下文（__main__/scripts.bootstrap/bootstrap/顶层），collect.py 检查顶层名不全 → governance 上下文触发第二 module 对象 → partial-init 循环；② 主文件 `from scripts.bootstrap.ai_memory_sync import` 依赖顶层 scripts 包，governance 环境（file-run 无 cwd）`import scripts` 命中 **pywin32 win32/scripts**（同名 namespace 包冲突）→ ModuleNotFoundError。修复：① 主文件头部无条件注册顶层名 `sys.modules.setdefault("sync_ai_memory", sys.modules[__name__])`；② 改用 `from bootstrap.ai_memory_sync import`（不依赖顶层 scripts）。定位方法：单路径探测 `PathFinder.find_spec('scripts', [p])` 逐条 sys.path + 打印 `scripts.__path__`。
- **D3**：benchmark 失败（1.05s vs 1.0s）经 stash 基线对比确认非拆分引入（抖动）。

## 5. N173 用时

- start 20:30 / end 20:52 / duration 22min / within_baseline true（大修改 < 60min）
- 说明：D1/D2 两轮循环导入修复（~10min），无超时

## 6. 反思

- 全量回归在 CLI 上下文才暴露 D1——import 上下文测试无法覆盖 __main__ 路径，三上下文冒烟必须显式跑（N202 ⑰ 已记）
- ruff 预存风格（UP006/UP035）不修——避免无关 diff（与 s35/s36 一致）