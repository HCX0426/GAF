# s40 solution — 测试文件拆分 (10 平铺 + 外部耦合更新)

## 拆分设计

```
scripts/tests/test_doc_health_check.py (1279 行) 删除
├── test_doc_health_common.py        201 行  issue_id/report/run_all + 尾部变体
├── test_doc_health_d2_bloat.py       69 行  + _make_md helper
├── test_doc_health_d3_count.py      173 行  + 2 回归 (L1184-1239)
├── test_doc_health_d4_path.py       272 行
├── test_doc_health_d5_frontmatter.py 99 行  + _fm_md helper
├── test_doc_health_d7_index.py      284 行  + 6 回归 (L1015-1182)
├── test_doc_health_d8_yaml.py        54 行
├── test_doc_health_d1_overlap.py     58 行
├── test_doc_health_d6_staleness.py   97 行
└── test_doc_health_integration.py    97 行  full pipeline + performance + read-only
```

**关键决策**：
1. **平铺命名**（test_doc_health_<dim>.py）：pytest 收集 test_*.py；禁止建 test_doc_health_check/ 目录（与源文件同名 → pytest 文件 vs 目录冲突警告）。
2. **回归测试按维度归入对应文件**：d3/d7 的 TD 回归（L1184-1239 / L1015-1182）进各自维度文件，不堆 integration → 每个维度文件 = 主测试 + 回归测试。
3. **每文件自带头部**：docstring + future + 按需 import + SCRIPTS_DIR hack + pytestmark。共享 fixture（repo_root）来自 scripts/conftest.py，不复制。
4. **局部 import 随区段带走**：原文件各维度区段自带 `from governance.check_dimensions import dX_...` → 切块时保留。
5. **外部耦合更新**（拆分必查，测试文件特有）：
   - `doc_health_patch.py._map_dimension_to_test_file`：dict 映射 7 维 → 各自文件（**行为改进**：run_relevant_pytest 原来 7 维全跑 1279 行文件 → 现在只跑对应维度文件；docstring 同步更新）
   - `check_doc_path_drift.py` FORBIDDEN_PATTERNS 白名单：旧条目保留历史 + 新增 10 个新文件（含旧路径 fixture 数据）

## 实施过程发现的问题（D1-D3）

### D1 — 切块区间含源文件头部 → future import 重复 SyntaxError

common 切块 (1,165)/(3,165) 把源文件 L1 docstring + L2 future + L4-8 import 块带入 body，与生成 header 重复 → `SyntaxError: from __future__ imports must occur at the beginning of the file`。

**修复**：common 切块点改 (21, 165)（跳过原头部 L1-20 全部：docstring/future/imports/hack/pytestmark/report_schema import），header 模板补 `from governance.report_schema import Issue, ReportSummary, DocHealthReport`。

**检查项（N202 ㉔）**：测试文件切块区间**必须跳过源文件头部**（L1 docstring + L2 future + import 块 + pytestmark + 常量区），否则与生成 header 重复（future import 直接 SyntaxError；import 块重复是 F401 隐患）。最稳：区间从第一个 def/test 前的空行开始，header 显式承载全部头部内容。

### D2 — 源文件删除后拆分脚本不可重跑

物理 Remove-Item 源文件 → 拆分脚本 `read_text` FileNotFoundError。

**修复**：`git checkout -- scripts/tests/test_doc_health_check.py` 恢复 → 重跑 → 再删（N202 ⑪ 幂等性：重跑前先恢复源文件）。

### D3 — 区段自带预存 F401（tempfile）

d2 区段 `import tempfile` 在原文件就是未用（预存）→ ruff 报 F401。

**修复**：ruff --fix 当场清理（测试文件无 re-export 风险，F401 --fix 安全；N150 预存错误当场处理）。

## 最终状态

- 10 文件全部 < 300 行；62 test 全数迁移无丢失
- doc_health_patch 映射 + docstring 更新；check_doc_path_drift 白名单 +10
- 源文件删除（git 追踪，commit 时确认删除）