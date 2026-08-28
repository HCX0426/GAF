# s40: 拆分 test_doc_health_check.py (1279 行 → 10 平铺测试文件, TD-365 7/9)

- **spec_id**: s40
- **状态**: ✅ 已归档 (2026-08-18, 归档于 `docs/specs/archived/2026-08/2026-08-18-s40-doc-health-test-split.md`)
- **来源**: TD-365 (i1_large_files, P2) — scripts/tests/test_doc_health_check.py 1279 行
- **任务类型**: refactor (大文件拆分, 循环模式 s39 后用户"继续"授权)
- **commit**: -

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit | 验收 evidence |
|------|------|---------|--------|--------------|
| P1 结构分析 + spec | ✅ | 22:30 | - | 9 维分区识别 + 外部耦合扫描 |
| P2 拆分实现 | ✅ | 22:50 | - | 10 文件 + doc_health_patch 映射 + path drift 白名单 |
| P3 验证 | ✅ | 23:05 | - | 62 passed + 580 全量 + governance 13/13 |
| P4 归档 + TD-365 闭环 | ✅ | 23:15 | - | TD-365 7/9 → FIXED 迁移 |

## 背景

test_doc_health_check.py (spec-41 doc_health_check 静态 7 维度的测试, 1279 行) 是 TD-365 最后一个可拆文件。
与源码拆分不同, 测试文件拆分要点:

1. **pytest 收集约定**: 只能拆成平铺 `test_*.py` 文件 (不能拆成非 test 模块 — 不会被收集)
2. **不可建 test_doc_health_check/ 目录**: 与源文件同名冲突 (pytest 警告 file vs directory)
3. **每文件必须自带**: docstring + `from __future__ import annotations` + 按需 import +
   SCRIPTS_DIR sys.path hack + `pytestmark = pytest.mark.unit`
4. **局部 import 模式**: 原文件各维度区段自带 `from governance.check_dimensions import dX_...`
   (区段级 import, 切块时随区段带走)
5. **共享 fixture**: `repo_root` 来自 scripts/conftest.py (已存在, 无需复制)

## 实现

### 拆分设计 (10 平铺文件, 源文件删除)

| 新文件 | 行数 | 内容 (源文件行号) |
|--------|------|------------------|
| test_doc_health_common.py | 201 | header 之后 L21-165 (issue_id 2 + report 5 + run_all 3) + L1242-1279 (run_all 变体 + issue_id 变体) |
| test_doc_health_d2_bloat.py | 69 | L166-219 (4 tests + _make_md helper) |
| test_doc_health_d3_count.py | 173 | L221-321 (5 tests) + L1184-1239 (2 回归) |
| test_doc_health_d4_path.py | 272 | L323-579 (13 tests) |
| test_doc_health_d5_frontmatter.py | 99 | L581-664 (4 tests + _fm_md helper) |
| test_doc_health_d7_index.py | 284 | L666-766 (5 tests) + L1015-1182 (6 回归) |
| test_doc_health_d8_yaml.py | 54 | L768-806 (3 tests) |
| test_doc_health_d1_overlap.py | 58 | L808-850 (3 tests) |
| test_doc_health_d6_staleness.py | 97 | L852-933 (4 tests) |
| test_doc_health_integration.py | 97 | L935-1013 (3 tests: full pipeline + performance + read-only) |

**关键决策**:
1. **回归测试按维度归入对应文件** (d3/d7 回归 → 各自维度文件), 不堆进 integration —
   保证每个维度文件 = 主测试 + 回归测试, 文件间无共享状态
2. **外部耦合同步更新** (拆分必查):
   - `doc_health_patch.py._map_dimension_to_test_file`: 7 维 → 各自文件
     (**行为改进**: run_relevant_pytest 原来 7 维全跑 1279 行单文件, 现在只跑对应维度)
   - `check_doc_path_drift.py` FORBIDDEN_PATTERNS 白名单: 源文件条目保留历史 +
     新增 10 个新文件 (均含旧路径 fixture 数据)

### 拆分脚本

`.trash/s40_split_doc_health.py` (幂等: 重跑前 `git checkout -- scripts/tests/test_doc_health_check.py`)

## Deviation Log

- **D1 (N202 ㉔)**: 切块区间包含源文件头部 (L1 docstring + L2 future import + L4-8 import 块)
  → 与生成 header 重复 → `SyntaxError: from __future__ imports must occur at the beginning`
  → common 切块点改 L21 (跳过原头部全部), header 模板补 report_schema import
- **D2 (N202 ㉕)**: 源文件物理删除后拆分脚本无法重跑 (FileNotFoundError)
  → `git checkout --` 恢复源文件再重跑 (N202 ⑪ 幂等性要求, 先恢复再拆)
- **D3 (N202 ㉖)**: d2 区段的 `import tempfile` 是原文件预存 F401 (切块带入)
  → ruff --fix 当场清理 (N150 预存错误当场处理)

## 验收

- ✅ 主文件删除, 10 文件全部 < 300 行
- ✅ 62 passed (10 新文件, 原文件 62 test 全数迁移, 无丢失)
- ✅ 35 passed (test_doc_health_patch 20 + test_doc_health_consumed 15)
- ✅ scripts 全量 580 passed + 2 skipped (与 s39 基线一致; e2e 环境性 5173 未启动排除)
- ✅ governance batch 13/13
- ✅ ruff F401 清零 (1 fixed: 预存 tempfile)
- ✅ TD-365 9 项全部处理完毕 (7 拆分 + 2 排除) → FIXED 迁移