---
maintainer: manual
source: s35 pipeline_engine.py 拆分 (2121 行 → 7 模块, -) + s34 views.py 拆分 (-) + s36 device.py 拆分 (1976 行 → 5 模块, -) + s37 models.ts 拆分 (1926 行 → models/ 目录, -) + s38 sync_ai_memory.py 拆分 (-) + s39 sync_skills.py 拆分 (1064 行 → skill_sync/ 5 模块) + s40 test_doc_health_check.py 拆分 (1279 行 → 10 平铺测试文件) 共 27 坑
load_when: [large-file, split, refactor, mixin, monkeypatch, patch-point, re-export, TD-365, 大文件拆分, import-contract, multiline-import, typescript, barrel, ts-split]
priority: high
symptom: "大文件拆分踩坑家族: patch 点语义失效最隐蔽 (execute 移出后测试 patch 模块属性注入 fake 失效, 12 测试失败); 方法区间丢装饰器行 (@staticmethod/@dataclass 丢失 → N805/TypeError); header 过滤 set 匹配误伤同字符串行; re-export 被 ruff F401 删 (测试 import 契约断, s36 常量 re-export 重演); 多行括号 import 正则漏扫 (test_adb_device_extended 19 符号 ImportError); mixin super().__init__ 带参数 MRO 到 object TypeError; TS 拆分丢顶层 import (API 命名空间 14 TS2503) + 注释里的类型名生成假跨域 import (16 TS6133) + 类型级联降级 any 误伤组件 (6 TS7053/7006)"
solution: "拆前必跑 23 项检查清单 (13 原项 + 3 TS 新增 + ⑰⑱ s38 + ⑲-㉓ s39): ⑭ TS/JS 拆分脚本必须保留源文件顶层 import (声明正则只匹配 type/interface/const 会漏 import 声明 — s37 丢 `import type { API } from '@/types/api'` 14 TS2503); ⑮ 跨域引用扫描必须排除注释行 (// 与 /* */ 内类型名被 \b名字\b 匹配 → 16 个假 import TS6133); ⑯ TS 类型解析失败有级联效应 (一个模块 TS2503 → 消费者处类型降级 any → 远离拆分的组件文件隐式 any 报错), 修复后级联自动消失 — 基线对比 (git checkout 还原源文件) 判定预存 vs 引入; ⑰ re-export 段插入口点之前 (s38 NameError); ⑱ 多模块名上下文无条件顶层注册 + 顶层包名冲突 (s38 win32/scripts); ⑲ parents[N] 按新层级重算 (s39 constants); ⑳ 切块后子模块 import 补全 + 主文件 import 核对 (s39 re/io_utils/hashlib); ㉑ 裸 from-import re-export 必须 noqa F401 (s39 ruff --fix 删绑定); ㉒ monkeypatch 目标 = 常量实际定义模块 + 消费方模块属性访问 (s39 D4); ㉓ 子包相对导入统一 + 主文件 bootstrap 段 parents[0]"
diff_keywords: ["s35", "split", "pipeline", "s35_split_pipeline", "s37", "models", "s37_split_models", "large", "python", "file", "split_large_python_file", "engine"]
related_files:
  - scripts/refactor/split_large_python_file.py
  - .ai-memory/evidence/archived/2026-08/2026-08-18-s35-pipeline-engine-split/
  - .ai-memory/evidence/archived/2026-08/2026-08-18-s34-agents-views-split/
  - .ai-memory/evidence/archived/2026-08/2026-08-18-s37-models-ts-split/
  - docs/archive/spec-context/2026-08-18-s35-pipeline-engine-split-context.md
  - docs/archive/spec-context/2026-08-18-s37-models-ts-split-context.md
  - .ai-memory/meta/failure-modes.md
created_by: AI
topic: refactor
---


# N202 — 大文件拆分：patch 点语义是隐式契约 (2026-08-18)

> **来源**: s35 pipeline_engine.py 拆分 (2121 行 → 7 模块), commit -; s34 views.py 拆分 (3983 行); s36 device.py 拆分 (1976 行 → adb_constants + 3 mixin, commit -); s37 models.ts 拆分 (1926 行 → models/ 目录 10 域 + barrel, commit -)
> **优先级**: high | **trigger_count**: 4 (s34 + s35 + s36 + s37) | **分类**: L1-大 (新反模式家族, 跨层影响)

## 现象

s34 (views.py) + s35 (pipeline_engine.py) + s36 (device.py) + s37 (models.ts) 四次大文件拆分, 共踩 16 个坑, 其中 **patch 点语义失效** 是最隐蔽的:

s35 把 execute() 从 `pipeline_engine.py` 移到 `pipeline_execution.py` 后, 12 个 JSONL 测试失败 — 测试用 `engine_mod.get_structured_logger = lambda...` patch 模块属性注入 fake logger, execute 移出后模块级查找 `get_structured_logger(...)` 落在 pipeline_execution 的全局命名空间, 不再指向 patch 点。

s36 (device.py) 无模块属性 patch (全实例级), 但踩了另外 5 个坑: 常量 re-export 被 ruff F401 自动删 → test ImportError; 多行括号 import 契约正则漏扫; mixin `super().__init__` 带参数 MRO 到 object → TypeError; 测试源码物理位置断言失败; 拆分脚本非幂等。

s37 (models.ts, TS 类型文件) 踩了 3 个 TS 特有坑: 拆分脚本丢顶层 `import type { API }` (分析误判"无 import") → 14 TS2503; 跨域引用正则匹配注释文本 → 16 个假 import (TS6133); 类型级联降级 any → 6 个组件文件报隐式 any (TS7053/TS7006), 修复源头后自动消失。

## 根因

拆分视角只覆盖「代码正确性」(import 链 / 符号引用 / 行数), 没覆盖「测试的 patch 语义」— 测试对**模块属性**的 monkeypatch 依赖「被调函数与该模块在同一命名空间」这一隐式契约。拆文件后模块级查找点变了, patch 就失效。TS 侧同理: 声明提取只按 type/interface/const 定位, 忽略了 import 声明本身也是文件契约的一部分; 且类型解析失败有级联效应, 报错位置远离实际修改点。

## 检查清单 (大文件拆分前必跑)

```text
□ 1. patch 点扫描: grep 测试里 `模块名.属性 = ...` / `monkeypatch.setattr(模块, ...)` 赋值模式,
     列出被 patch 的模块属性 (实例属性 patch device._device = ... 不受拆分影响, 可忽略)
□ 2. 被 patch 属性若在拆分源文件 → 拆后目标模块的调用必须「运行时查原模块属性」
     (转发函数: def _f(*a, **k): from engine import pipeline_engine as m; return m.attr(*a, **k))
□ 3. import 契约扫描: **用 AST 级扫描** (正则 `from X import ([^\n]+)` 漏多行括号 import —
     s36 test_adb_device_extended 19 符号 ImportError 根因) → X 必须保留在源模块 re-export
□ 4. re-export 符号必须入 __all__: 主文件 `from .xxx import <符号>` 若未使用会被 ruff --fix F401
     自动删除 (s36 常量 re-export 重演 s35 反模式) → __all__ 含全部 re-export 名
□ 5. mixin 继承基类: mixin 内 super().__init__(带参) 时 MRO 到 object → TypeError (s36);
     mixin 全部继承 BaseDevice + 主类继承所有 mixin + BaseDevice
□ 6. 方法区间提取: AST 用 decorator_list[0].lineno (丢装饰器 → @staticmethod 丢失 → ruff N805)
□ 7. dataclass 类提取: 同样用 decorator_list (丢 @dataclass → TypeError: X() takes no arguments)
□ 8. header 过滤: 删块用顺序匹配 (set 匹配会误伤内容相同的行, 如两处 `from utils.x import (`)
□ 9. logger 位置: 统一放所有 imports 之后 (E402; ruff --fix 不修多行块)
□ 10. 源码位置断言适配: 测试读 `模块.__file__` 源码断言方法/常量物理位置 (s36 test_ldopengl 3 处)
      → 拆后断言改读 主文件 + 目标模块 拼接源码
□ 11. 拆分脚本幂等性: 重跑前 `git checkout -- <源文件>` 恢复 (脚本第二次跑源已变 → StopIteration)
□ 12. 拆后验证: 全量测试 (非仅相关文件) — patch 失效类失败只影响特定测试类
□ 13. 附带修复: 拆分搬运的预存 R001 空 except → 当场补 logger.debug (N150, 不进 commit 再返工)
□ 14. TS/JS 顶层 import 保留: 声明定位正则只匹配 type/interface/const/export 会漏 import 声明 —
     s37 丢 `import type { API } from '@/types/api'` → 14 TS2503 (API.components['schemas'] 全失效)
□ 15. 跨域引用扫描排除注释: refs 正则 `\b名字\b` 匹配注释文本 (如 "migrated to
     API.components['schemas']['X']") → 16 个假 import (TS6133) — 先删注释行再扫引用
□ 16. 类型级联 + 基线对比: 模块内 TS2503 → 消费者类型降级 any → 远离拆分的组件文件隐式 any
      (s37: DeviceCard/TaskDetailDrawer/DetailPage/TaskFormModal 6 处 TS7053/7006);
      修复源头后级联自动消失, 组件零改动 — 判定预存 vs 引入用基线对比 (git checkout 还原源文件跑 tsc)
□ 17. re-export 段必须插在入口点之前: 拆脚本把 re-export 追加到文件末尾, 但
      `if __name__ == "__main__": sys.exit(main())` 原本就在末尾 → main() 先执行,
      re-export 绑定永远未执行 → NameError (_sync_lessons_readme_count is not defined);
      s38 CLI --stats 全量回归才暴露 (import 上下文测试不触发 __main__ 路径)
□ 18. 多模块名上下文循环 + 顶层包名冲突: 同一文件可能以 4 种模块名加载 (__main__ /
      scripts.bootstrap.sync_ai_memory / bootstrap.sync_ai_memory / sys.path-hack 顶层
      sync_ai_memory), 子模块检查 `"sync_ai_memory" in sys.modules` 只覆盖顶层名 →
      governance 上下文走 else 分支触发第二 module 对象加载 → partial-init AttributeError;
      s38 解法: 主文件头部**无条件** `sys.modules.setdefault("sync_ai_memory", sys.modules[__name__])`
      (任何上下文都注册顶层名, 子模块永远绑定同一对象, 永不二次加载)
      **深坑 (s38 真根因)**: 主文件 `from scripts.bootstrap.ai_memory_sync import` 依赖顶层
      `scripts` 包, 但 sys.path 里 `D:\code\GAF\scripts` 条目是给 `import bootstrap` 用的 —
      file-run 环境 (governance batch, sys.path 无 cwd) `import scripts` 命中 pywin32 的
      `site-packages\win32\scripts` (namespace 包, 同名冲突!) → ModuleNotFoundError
      'scripts.bootstrap'; 判定方法: 单路径探测 `PathFinder.find_spec('scripts', [p])`
      + 打印 `scripts.__path__` (win32/scripts vs 项目 scripts); 修复: 改用
      `from bootstrap.ai_memory_sync import` (scripts/ 在 path 时直接可用, 不依赖顶层 scripts)
□ 19. 切块复制的 parents[N] 必须按新层级重算: 文件移入子包目录后
      `Path(__file__).resolve().parents[N]` 少一层 (s39: constants.py `parents[2]` → `parents[3]`,
      未改时 REPO_ROOT_DEFAULT = scripts/ → CLI 报"仓库内无任何源文件")
□ 20. 切块后子模块 import 依赖补全 + 主文件剩余 import 核对: 移出的函数可能引用
      未移出的工具 (s39: checks.py 用 _read_text; changelog.py 用 re) → 拆后
      grep 子模块引用的每个名字补 import; 主文件删区间后剩余代码的 import
      重新核对 (删多 = NameError, 留多 = ruff F401)
□ 21. 裸 from-import re-export 必须 `# noqa: F401`: ruff --fix 会把 re-export 中
      "主文件内未使用" 的绑定当 unused 删除 (s39: io_utils 的 update_frontmatter_updated
      等被删 → 测试 `from sync_skills import` ImportError); s38 幸免是因 re-export 在
      try 块内 (ruff 不报 try 内 import); 修复: 每行 `# noqa: E402, F401` + 注释
      "these bindings ARE the public API"; 修完 I001 排序后**必须重跑测试** (排序可能改动)
□ 22. 跨文件共享常量被 monkeypatch 时: patch 目标 = 常量**实际定义模块** (非 re-export
      绑定 — `from X import Y` 是绑定复制, patch 主文件绑定不影响子模块绑定);
      被 patch 的消费方用**模块属性访问** (`from . import constants as _constants` +
      `_constants.TIMESTAMP_SKILLS`) 而非 from-import 绑定 (s39 D4: 测试
      `monkeypatch.setattr(sync_skills, "TIMESTAMP_SKILLS", ...)` 改 patch
      `skill_sync.constants` 后生效)
□ 23. 子包相对导入统一 (`from .constants import`): 子模块永远作为包加载 (有 __init__.py)
      → 相对导入在顶层和包路径两种加载方式下解析到**同一模块对象**, 避免双模块分裂
      (顶层 skill_sync vs bootstrap.skill_sync 各自独立 = monkeypatch 双份绑定陷阱);
      主文件 bootstrap 段加 parents[0] (子包所在目录) 保证顶层 `from skill_sync...` 可用
□ 24. 测试文件拆分切块点必须跳过源文件头部: 区间含源文件 L1 docstring + L2
      `from __future__ import annotations` + import 块 + pytestmark → 与生成 header
      重复 → `SyntaxError: from __future__ imports must occur at the beginning`
      (s40 D1: common 切 (1,165)/(3,165) 均报错, 改 (21,165) 从第一个 test 前空行开始);
      header 模板显式承载全部头部内容 (含该文件需要的 report_schema import)
□ 25. 测试文件拆分的平铺命名 + 禁止同名目录: 只能拆成 test_*.py 平铺文件 (pytest
      收集约定, 非 test 前缀模块不收集; test_doc_health_check/ 目录与源文件同名 →
      pytest file vs directory 冲突); 回归测试按被测维度归入对应文件
      (s40: d3/d7 回归进各自维度文件, 不堆 integration — 每维度文件 = 主测试+回归)
□ 26. 测试文件拆分的外部运行时耦合: 被测文件路径可能被**运行时映射**引用
      (s40: doc_health_patch._map_dimension_to_test_file 7 维 → 单文件路径, 拆分后
      更新为每维一文件 — 顺带的行为改进: run_relevant_pytest 从跑全 1279 行变为
      只跑对应维度) + **hook 白名单** (check_doc_path_drift FORBIDDEN_PATTERNS:
      旧条目保留历史 + 新增全部新文件, 因均含旧路径 fixture 数据);
      docstring 里的路径表同步更新; 删源文件前先确认无引用残留 (grep 全仓)
□ 27. 测试文件区段自带 import 的预存 F401: 局部 import (如 d2 区段 `import tempfile`)
      在原文件就是未用 → 切块带入新文件被 ruff 标记 → 当场 ruff --fix 清理
      (测试文件无 re-export 风险, F401 --fix 安全; N150 预存错误当场处理)
```

## 反例 vs 正例

- ❌ 只跑相关测试文件 (patch 失效 12 个失败在 test_pipeline_engine.py 内 — 容易被误判为个别测试问题)
- ✅ 全量 agent 测试 (2305 passed) — 才发现是系统性 patch 失效
- ❌ set 匹配删 import 块 (`{...}` not in) — L30 与 L35 同字符串被误删
- ✅ 顺序块匹配 (i, i+1, i+2 连续三行精确判断)
- ❌ 方法区间 m.lineno — 装饰器行丢失
- ✅ decorator_list[0].lineno

## 相关文件

- 拆分脚本: 可重跑模板 (Python 泛化版: `scripts/refactor/split_large_python_file.py` — s36 新增常量块提取 + BaseDevice mixin 继承能力; 各 spec 当时的临时 script 已入 .trash 清理)
- s35 evidence: `.ai-memory/evidence/active/2026-08-18-s35-pipeline-engine-split/` (problem/solution/verification 三件套)
- s36 evidence: `.ai-memory/evidence/active/2026-08-18-s36-adb-device-split/` (D1-D5 五坑记录)
- s37 evidence: `.ai-memory/evidence/active/2026-08-18-s37-models-ts-split/` (D1-D3 三坑记录)
- s38 evidence: `.ai-memory/evidence/active/2026-08-18-s38-sync-ai-memory-split/` (D1-D2 两坑记录)
- s39 evidence: `.ai-memory/evidence/active/2026-08-18-s39-sync-skills-split/` (D1-D4 四坑记录)
- s40 evidence: `.ai-memory/evidence/active/2026-08-18-s40-doc-health-test-split/` (D1-D3 三坑记录)
- s34 evidence: `.ai-memory/evidence/active/2026-08-18-s34-agents-views-split/`
- spec-context: `docs/archive/spec-context/2026-08-18-s35-pipeline-engine-split-context.md` (§4 全部 8 坑记录) + `docs/archive/spec-context/2026-08-18-s36-adb-device-split-context.md` (D1-D5) + `docs/archive/spec-context/2026-08-18-s37-models-ts-split-context.md` (D1-D3) + `docs/archive/spec-context/2026-08-18-s38-sync-ai-memory-split-context.md` (D1-D2) + `docs/archive/spec-context/2026-08-18-s39-sync-skills-split-context.md` (D1-D4) + `docs/archive/spec-context/2026-08-18-s40-doc-health-test-split-context.md` (D1-D3)