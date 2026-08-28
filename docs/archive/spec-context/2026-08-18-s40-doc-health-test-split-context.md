# spec-context: 2026-08-18-s40-doc-health-test-split

> s40 = TD-365 7/9（最后一个可拆文件），用户"继续"授权（s39 后询问"继续吗"，用户回答"继续"）。

## 1. 用户决策原文

- "继续"（2026-08-18，s39 闭环后）

## 2. N151 5 步法评估

1. **架构盘点**：
   - 数据：test_doc_health_check.py 1279 行纯测试文件，无 DB；9 域测试混合
   - 依赖：各维度区段自带局部 import（`from governance.check_dimensions import dX_...`）；共享 repo_root fixture 来自 scripts/conftest.py；helper _make_md（d2 独用）/ _fm_md（d5 独用）
   - 调用：pytest 收集（test_*.py 约定）；doc_health_patch._map_dimension_to_test_file（运行时路径映射）；check_doc_path_drift 白名单
   - 历史：N202 ⑰-㉓ 检查清单现成（源码拆分 6 次经验）；本次为**首次测试文件拆分**
2. **识别反模式**：单文件 9 域混合；doc_health_patch 7 维全指一个 1279 行文件（run_relevant_pytest 每次跑全部维度测试）
3. **A/B/C 备选**：
   - A（采纳）：10 平铺 test_doc_health_<dim>.py + 源文件删除 + 映射每维一文件——符合 pytest 收集约定；映射升级是顺带的行为改进
   - B：test_doc_health_check/ 子目录包——与源文件同名冲突（pytest file vs directory），且违反平铺惯例
   - C：只拆 integration 区（最小拆分）——主文件仍 ~935 行超标，治标不治本
4. **拒绝反模式**：拒绝 B（同名冲突）/ C（不达标）；"保留双套"无需求
5. **AI 自决**：A 方案（7 维度评分后自决）

## 3. N167 七维度评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 1 架构长远性 | 5 | 每维度一文件，run_relevant_pytest 精确验证 |
| 2 全局归一化 | 5 | 平铺命名对齐 test_doc_health_consumed/patch 惯例 |
| 3 新旧兼容 | 5 | 62 test 全数保留；映射更新不破坏调用 |
| 4 现有业务完善 | 5 | run_relevant_pytest 验证粒度提升（7 维分开） |
| 5 性能资源优化 | 4 | 单维验证不再跑全 1279 行文件 |
| 6 安全合规 | 5 | 纯测试结构变化 |
| 7 长期维护成本 | 5 | 各维度独立演进 |
| **总分** | **34/35** | ≥ 19 且领先 ≥ 5 → AI 自决 |

## 4. 关键实施决策（D1-D3）

- **D1 切块点跳过源文件头部**：common 切块含 L1-20（docstring/future/imports/hack/pytestmark）→ future import 重复 SyntaxError → 切块点改 L21 + header 补 report_schema import。检查项：测试文件切块区间必须从第一个 test 前空行开始，头部全部由生成 header 承载。
- **D2 源文件删除后脚本不可重跑**：`git checkout --` 恢复再拆（N202 ⑪）。
- **D3 区段预存 F401**：d2 区段 tempfile 原文件就未用 → ruff --fix 当场清理（N150）。

## 5. 反思（commit 后 §4.6 4 问）

1. **本轮要做什么？** s40 拆分 test_doc_health_check.py（1279 → 10 平铺文件，TD-365 7/9 = 最后一项）。
2. **可复用**：N202 检查清单；s39 拆分脚本模式；doc_health 家族平铺命名惯例。
3. **风险与依赖**：① pytest 收集约定（平铺 test_*.py）② 外部运行时映射（doc_health_patch）③ hook 白名单（check_doc_path_drift）④ 切块点含源头部（D1）。
4. **验收标准**：62 passed 全数 ✅ / 580 全量基线一致 ✅ / governance 13/13 ✅ / TD-365 9 项全部处理（7 拆 + 2 排除）→ FIXED ✅。
5. **新教训**：D1-D3 纳入 N202 ㉔-㉖（3 项新增检查清单）。"无 A 类"检查：已检查 N178-A1 反向论证（无）/A2 评分合理化（34/35 客观领先）/A3 过度治理（拆分是 TD-365 明确最后任务）/A4 范围扩张（外部耦合更新是拆分必需，非扩张）。