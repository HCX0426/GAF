# s39 solution — sync_skills.py 拆分到 skill_sync/ 域包

## 拆分设计

```
scripts/bootstrap/sync_skills.py (1064 → 457 行)  +  scripts/bootstrap/skill_sync/
├── skill_sync/__init__.py      包标记 + 模块说明
├── skill_sync/constants.py     全部常量 + 正则 (原 L56-125 + L348-369)    103 行, 零依赖
├── skill_sync/io_utils.py      文件/文本工具 + frontmatter 函数 (L371-417 + L445-480)  96 行, 依赖 constants
├── skill_sync/checks.py        5 个 check_* 一致性检查 (L127-345)        233 行, 依赖 constants + io_utils
├── skill_sync/changelog.py     --changelog 域 6 函数 (L578-780)          225 行, 依赖 constants + io_utils
└── skill_sync/timestamps.py    --update-timestamps (L782-847)            81 行, 依赖 constants + io_utils
```

**关键决策**：
1. **子模块零主文件依赖**（N202 ⑱ 简化版）：s38 需要 `_main.` 运行时常量（子模块 import 主文件会循环）；s39 通过把常量全部移入 constants.py + 工具移入 io_utils.py，子模块**无需 import 主文件** → 无循环风险。
2. **相对导入**（`from .constants import`）：skill_sync 永远作为包加载（有 __init__.py）→ 相对导入在顶层和包路径两种加载方式下都解析到同一模块对象，避免"双模块"分裂（顶层 skill_sync vs bootstrap.skill_sync）。
3. **主文件 bootstrap 段双目录**（parents[0] + parents[1]）：子模块包在 scripts/bootstrap/ 下，顶层 `from skill_sync...` 需要 scripts/bootstrap/ 在 sys.path；governance 只加 scripts/ → 主文件自身把两个目录都注入。
4. **re-export 段插在 `if __name__ == "__main__":` 之前**（N202 ⑰）+ **`# noqa: E402, F401`**：re-export 是模块公开 API，ruff F401 会误删（见 D3）。

## 实施过程发现的问题（D1-D4）

### D1 — constants.py 的 parents 层级 +1（REPO_ROOT 漂移）

切块复制后 constants.py 位于 `scripts/bootstrap/skill_sync/`，比主文件深一层：`parents[2]`（主文件正确值）→ 需要 `parents[3]`。未改时 `REPO_ROOT_DEFAULT = scripts/` → CLI 报 "仓库内无任何源文件: D:\code\GAF\scripts\.skills\skills"。

**检查项**：拆分后所有 `Path(__file__).resolve().parents[N]` 常量必须按新层级重新计算。

### D2 — 子模块 import 依赖不全（NameError）

- changelog.py 缺 `import re`（_read_changelog_last_hash 用 re.findall）
- checks.py 缺 `from .io_utils import _read_text`（check_l2_consistency 读文件）
- 主文件缺 `import hashlib`（inspect_skill/inspect_rule 算 hash）

**检查项**：切块后全仓 grep 每个子模块使用的名字，import 补全；主文件删除区间后剩余代码的 import 重新核对（删多 = NameError，留多 = F401）。

### D3 — ruff --fix 删除 re-export 绑定（F401 误判）★ 最深坑

主文件 re-export 段 `from skill_sync.io_utils import (...)` 中**未在主文件内使用**的名字（如 `update_frontmatter_updated`）被 ruff F401 判定 unused → `ruff check --fix` **直接删除绑定** → 测试 `from sync_skills import update_frontmatter_updated` → ImportError。

s38 幸免的原因：s38 re-export 在 `try/except` 块内（ruff 对 try 块内 import 不报 F401）；s39 是裸 from-import → 被删。

**修复**：re-export 段每行 `# noqa: E402, F401`（注释明确"these bindings ARE the public API"）。

**检查项**：re-export 段必须带 `# noqa: F401`（裸 from-import 会被 ruff --fix 删除）；s38 的 try 块形态不需要但 s39 需要。

### D4 — monkeypatch 常量目标必须指向真实持有者

测试 `monkeypatch.setattr(sync_skills, "TIMESTAMP_SKILLS", [...])`（patch 主文件 re-export 绑定）→ cmd_update_timestamps 在 timestamps.py 用 `from .constants import TIMESTAMP_SKILLS`（**绑定复制**）→ patch 主文件绑定不影响 timestamps 模块绑定 → 测试失败。

**修复（两层）**：
1. timestamps.py 改为 `from . import constants as _constants` + 函数内 `_constants.TIMESTAMP_SKILLS`（**模块属性访问**，patch constants 模块即生效）
2. 测试改为 `monkeypatch.setattr(skill_sync.constants, "TIMESTAMP_SKILLS", [...])`

**检查项**：跨文件共享常量被测试 monkeypatch 时，patch 目标 = 常量**实际定义模块**（不是 re-export 绑定）；被 patch 的消费方用**模块属性访问**而非 from-import 绑定复制。

## 最终结构（457 行主文件）

- docstring + bootstrap 双目录 + 无条件顶层注册（N202 ⑱）
- imports（argparse/hashlib/subprocess/sys/Path/typing）
- get_skill_last_commit_date / inspect_skill / inspect_rule / sync_skill / sync_rule / detect_workspace_root（留主文件：main 直接使用 + git 子进程逻辑）
- main() + 入口点
- re-export 段（45 个符号，noqa: F401）
