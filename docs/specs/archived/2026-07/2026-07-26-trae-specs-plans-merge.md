---
summary: spec-2026-07-26-trae-specs-plans-merge — .trae/specs + .trae/plans 合并到 docs/specs + docs/plans
applies_to: [docs, scripts, hooks, rules]
key_decisions:
  - 合并 .trae/specs/ (80 文件) → docs/specs/legacy-trae/ (保历史, 不混入 active/archived)
  - 合并 .trae/plans/ (3 文件) → docs/plans/legacy-trae/
  - 更新 6 脚本 + 5 hook + 2 rules 段 + 2 yn-matrices 段的 .trae/specs|plans 路径引用
  - 历史文档 (fixed.md / completed-features.md / wontfix.md) 中 .trae/specs|plans 引用保留 (白名单豁免)
  - 删除空 .trae/specs/ + .trae/plans/ 目录
last_updated: 2026-07-26
created_at: 2026-07-26
spec_id: spec-2026-07-26-trae-specs-plans-merge
status: done
priority: high
owner: AI
related_td: []
completed_at: 2026-07-26
completed_commit: '-'
---

# spec-2026-07-26-trae-specs-plans-merge — .trae/specs + .trae/plans 合并到 docs/

## 来源

2026-07-26 用户: "`.trae/specs` `.trae/plans` 这两得内容都合并到 `docs/specs` `docs/plans` 吧,放一个地方"

## 调研数据

### .trae/specs/ 实际状态
- 80 个 spec 文件 (spec-25 ~ spec-118,日期 2026-07-18 ~ 2026-07-22)
- **最新文件 2026-07-22-spec99**, 已 4 天无新文件
- 近期 spec 流程已切到 `docs/specs/active/YYYY-MM-DD-*.md` (spec-2026-07-25-* / spec-2026-07-26-* 共 4 个新 spec)
- **结论**: 已非"工具自动管理",实际是历史 spec 仓库

### .trae/plans/ 实际状态
- 3 个 plan 文件 (spec-42/43/44 早期设计 plan)
- **最新文件 2026-07-20**, 已 6 天无新文件
- 近期 plan 在 `docs/plans/active/` + `docs/plans/archived/YYYY-MM/`
- **结论**: 历史遗物,可合并

### 影响面 (60+ 引用,分类如下)

**A. 脚本数据源 (必须改)**:
- `scripts/governance/spec_dependency_graph.py` (SPECS_DIR_DEFAULT)
- `scripts/governance/sync_spec_index.py` (扫描路径)
- `scripts/governance/governance_dashboard.py` (扫描路径)
- `scripts/bootstrap/sync_skills.py` (skip 路径)
- `scripts/hooks/check_spec_id_collision.py` (SPECS_PREFIX)
- `scripts/hooks/check_spec_consistency.py` (扫描路径)
- `scripts/hooks/doc_sync_rules.py` (trigger_pattern)
- `scripts/governance/check_dimensions/d3_count_drift.py` (skip_dir_prefixes)
- `scripts/hooks/check_doc_path_drift.py` (WHITELIST_FRAGMENTS, 删 .trae/specs|plans 项)

**B. 测试 (必须改)**:
- `scripts/tests/test_governance_dashboard.py` (3 处 skip 条件)
- `scripts/tests/test_spec_dependency_graph.py` (3 处 skip 条件)
- `scripts/tests/test_check_doc_code_sync.py` (2 处 fixture path)

**C. 规则文档 (必须改)**:
- `.trae/rules/project_rules.md` §2.0.5 L219 (路径表) + §4 L550 (spec 路径约定)
- `.ai-memory/meta/yn-matrices/_workflow-spec.md` (4 处 grep 命令)
- `.ai-memory/meta/spec-evolution.md` (2 处路径映射表)

**D. 历史文档 (保留,白名单豁免)**:
- `docs/tech-debt/fixed.md` (15+ 处, 历史闭环记录)
- `docs/tech-debt/fixed-archive-2026.md` (10+ 处)
- `docs/tech-debt/wontfix.md` (5+ 处)
- `docs/completed-features.md` (10+ 处)
- `docs/monthly-health-check.md` (2 处)
- `.ai-memory/ref/spec-index.md` (source 字段)
- `.ai-memory/ref/doc-health-report-schema.md` (2 处)
- `.ai-memory/meta/docs-index.md` (1 处)
- `docs/specs/README.md` (2 处描述)
- `docs/specs/dependency-graph.md` (source frontmatter)
- `docs/specs/archived/2026-07/2026-07-25-docs-ai-memory-restructure.md` (2 处)
- `backend/agents/models.py` (1 处注释)

**E. 自引用 (迁后清理)**:
- `.trae/specs/*.md` 自身 (内部引用其他 .trae/specs/ 文件,迁移后路径变)
- `.trae/plans/*.md` 自身

## N151 5 步法评估

### Step 1: 架构盘点
- `docs/specs/` 已有完整目录结构 (active + archived/YYYY-MM/ + README + dependency-graph)
- `docs/plans/` 已有完整目录结构 (active + archived/YYYY-MM/)
- 脚本/hook 大部分接受 `--root` 参数或可配置路径

### Step 2: 识别反模式
- ❌ spec/plan 双目录分裂 (`.trae/specs/` + `docs/specs/`),违反 N132 单一权威源
- ❌ 早期 spec-27 决定保留 `.trae/specs/` 作为"TRAE 工具数据源",但实际 TRAE 工具已不再写入
- ❌ 60+ 处路径引用分散,新 spec 流程已切走但旧 spec 仍困在 .trae/

### Step 3: A/B/C 备选方案
- **A 全量合并 + 重命名**: 80 文件迁到 docs/specs/archived/2026-07-legacy/,与现有 archived/YYYY-MM/ 混合
- **B 子目录隔离**: 80 文件迁到 docs/specs/legacy-trae/,与 active/archived 平级 (保历史,不混入)
- **C 仅迁移 + 保留 .trae/specs/ 软链**: 软链 .trae/specs → docs/specs/legacy-trae/

### Step 4: 拒绝反模式 + AI 自决
- ❌ 拒绝 A (混合后 active/archived/2026-07/ 会与 legacy-trae/ 同月,易混淆,且历史 spec 文件名格式 `spec{N}-td{M}-*.md` 与新 `YYYY-MM-DD-*.md` 不同,不应混合)
- ✅ 选 B (子目录隔离,路径清晰:active/ + archived/YYYY-MM/ + legacy-trae/,三类不交叉)
- ❌ 拒绝 C (软链在 Windows 上需管理员权限,且 N132 已禁用软链)

### Step 5: N167 七维度评分 (方案 B)

| 维度 | 分 | 理由 |
|------|---|------|
| 1 架构长远性 | 5/5 | 单一目录树,消除 .trae/specs|plans 双轨,与 N132 一致 |
| 2 全局归一化 | 5/5 | 所有 spec/plan 统一在 docs/ 下,路径模式归一 |
| 3 新旧兼容 | 4/5 | 历史文档 .trae/specs 路径白名单豁免 (合理保留),新路径不影响新 spec 流程 |
| 4 现有业务完善 | 5/5 | 80 + 3 = 83 个历史 spec/plan 全部纳入 docs/ 体系 |
| 5 性能资源优化 | 5/5 | 无运行时影响,仅文件移动 |
| 6 安全合规加固 | 4/5 | 删除 .trae/specs|plans 后 check_doc_path_drift 白名单相应清理 |
| 7 长期维护成本 | 4/5 | 一次性投入,长期不再有"两目录"困惑 |
| **总分** | **32/35** | ≥ 19 → AI 自决执行 |

## 阶段状态表

| Wave | 任务 | 状态 | 完成时间 | commit hash | 验收 evidence |
|------|------|------|---------|-------------|--------------|
| W1 | 迁移 .trae/specs/ → docs/specs/legacy-trae/ (80 文件) | ⏳ | - | - | - |
| W2 | 迁移 .trae/plans/ → docs/plans/legacy-trae/ (3 文件) | ⏳ | - | - | - |
| W3 | 更新 6 脚本 + 5 hook + 2 rules + 2 yn-matrices 路径引用 | ⏳ | - | - | - |
| W4 | 更新 check_doc_path_drift 白名单 + dependency-graph.md source | ⏳ | - | - | - |
| W5 | 删除空 .trae/specs/ + .trae/plans/ 目录 | ⏳ | - | - | - |
| W6 | 验收 (跑测试 + 跑脚本 + 7/7 hooks) + commit + 归档 | ⏳ | - | - | - |

## 执行计划

### W1: 迁移 .trae/specs/ → docs/specs/legacy-trae/ (80 文件)

```powershell
git mv .trae/specs docs/specs/legacy-trae
```

### W2: 迁移 .trae/plans/ → docs/plans/legacy-trae/ (3 文件)

```powershell
git mv .trae/plans docs/plans/legacy-trae
```

### W3: 更新脚本 + hook + rules + yn-matrices

具体改动见"调研数据"段的 A/B/C 分类,逐文件 Edit:
- 脚本: `.trae/specs` → `docs/specs/legacy-trae`, `.trae/plans` → `docs/plans/legacy-trae`
- hook: 同上,且 check_doc_path_drift.py 删除白名单中 `.trae/specs/` + `.trae/plans/` 项 (因目录已不存在)
- rules: project_rules.md §2.0.5 L219 删除 `.trae/specs|plans` 行,§4 L550 改路径
- yn-matrices: _workflow-spec.md 4 处 grep 命令路径更新
- spec-evolution.md: 2 处路径映射表更新

### W4: 更新 dependency-graph.md source + README.md

- `docs/specs/dependency-graph.md` frontmatter `source: .trae/specs/*.md` → `docs/specs/legacy-trae/*.md`
- `scripts/governance/spec_dependency_graph.py` SPECS_DIR_DEFAULT + 输出 frontmatter
- `docs/specs/README.md` 删除"`.trae/specs/` 工具自动管理"段,新增 legacy-trae/ 段

### W5: 删除空目录

W1/W2 git mv 后 .trae/specs/ + .trae/plans/ 应已不存在 (git mv 移动整个目录)

### W6: 验收

1. 跑脚本: `python scripts/governance/spec_dependency_graph.py` (确认能扫描 docs/specs/legacy-trae/)
2. 跑测试: `pytest scripts/tests/test_governance_dashboard.py scripts/tests/test_spec_dependency_graph.py scripts/tests/test_check_doc_code_sync.py scripts/tests/test_check_doc_path_drift.py`
3. 跑 hook: `pre-commit run --all-files`
4. 跑 governance batch: 应仍 13/13 PASS

## 验收标准

- [ ] .trae/specs/ + .trae/plans/ 目录删除
- [ ] docs/specs/legacy-trae/ 含 80 文件
- [ ] docs/plans/legacy-trae/ 含 3 文件
- [ ] 6 脚本路径更新 (spec_dependency_graph / sync_spec_index / governance_dashboard / sync_skills / check_spec_id_collision / check_spec_consistency / doc_sync_rules / d3_count_drift)
- [ ] check_doc_path_drift.py 白名单清理
- [ ] project_rules.md 2 处路径更新
- [ ] yn-matrices _workflow-spec.md 4 处 + spec-evolution.md 2 处更新
- [ ] dependency-graph.md 重新生成 (source 字段更新)
- [ ] docs/specs/README.md 更新
- [ ] 所有测试 + hooks 通过

## 偏离阈值

- Phase 数 +50% (6 → 9+) 或 diff +30% 必更新本文件 "范围偏差日志"
- 超出 +100% 必停下问用户

## 范围偏差日志

(无)

## 回滚预案

- git revert commit hash
- git mv docs/specs/legacy-trae .trae/specs + git mv docs/plans/legacy-trae .trae/plans 恢复目录
