---
spec_id: spec-84
title: TD-322 — spec 编号归一 (同号多版本歧义)
created: 2026-07-21
status: ✅ done
commit: '-'
related_td: [TD-322]
related_n: []
depends_on: []
blocks: []
priority: P1
size: 中 (sync_spec_index.py + check_spec_id_collision.py + 9 tests, ~610 行)
---

# spec-84: TD-322 — spec 编号归一 (方案 B: wontfix + 索引脚本)

> **用户决策 (2026-07-21)**: 选方案 B — 现有 16 同号多版本保留 (历史文件不动), 新建索引脚本 + pre-commit hook 防止新增冲突. TD-322 wontfix+mitigation.

## 背景与问题

`.trae/specs/` 下 spec-36/38/39/41/42/43/44/45 各有 2 个不同主题文件 (8 组 16 文件), 同 spec 号被复用为不同主题, 引用 "spec-36" 时指代不清, 有歧义风险.

## 同号多版本清单 (按 commit 时间先后定 a/b)

| 旧 spec_id | 新 spec_id | 文件名 | commit |
|:---:|:---:|---|:---:|
| spec-36 | spec-36a | 2026-07-19-spec36-ai-memory-ops-cleanup-and-n170-dedup.md | (07-19) |
| spec-36 | spec-36b | 2026-07-20-spec36-a11y-governance.md | (07-20) |
| spec-38 | spec-38a | 2026-07-19-spec38-docs-ai-memory-full-governance.md | (07-19) |
| spec-38 | spec-38b | 2026-07-20-spec38-hook-maintainer-mode-differentiation.md | (07-20) |
| spec-39 | spec-39a | 2026-07-19-spec39-docs-content-sync-and-rule-conflict-fix.md | (07-19) |
| spec-39 | spec-39b | 2026-07-20-spec39-small-td-batch.md | (07-20) |
| spec-41 | spec-41a | 2026-07-19-spec41-doc-health-checker-design.md | (07-19) |
| spec-41 | spec-41b | 2026-07-20-spec41-accounts-agents-decouple.md | (07-20) |
| spec-42 | spec-42a | 2026-07-19-spec42-self-evolution-flywheel-design.md | (07-19) |
| spec-42 | spec-42b | 2026-07-20-spec42-td287-message-compressor-wiring.md | (07-20) |
| spec-43 | spec-43a | 2026-07-20-spec43-forgetting-mechanism-design.md | - |
| spec-43 | spec-43b | 2026-07-20-spec43-td289-silent-swallow-logger.md | - |
| spec-44 | spec-44a | 2026-07-20-spec44-monthly-check-slimming.md | - |
| spec-44 | spec-44b | 2026-07-20-spec44-td273-phase2-enum-migration.md | - |
| spec-45 | spec-45a | 2026-07-20-spec45-monthly-check-automation.md | - |
| spec-45 | spec-45b | 2026-07-20-spec45-td290-wontfix-td291-screenshot-retention.md | - |

## 方案评估

### 方案 A: 重命名 + 全量引用更新 (原 TD-322 修复方案)

**操作**:
1. `git mv` 重命名 16 个 spec 文件 (文件名 + 文件内 `# spec-NN:` 标题)
2. 更新所有引用 `spec-NN` 的文档:
   - `docs/general/tech-debt/{active,fixed,wontfix}.md` (~75 处)
   - `.ai-memory/meta/failure-modes.md` (~2 处)
   - `.ai-memory/lessons/*.md` (~10 处)
   - `.trae/specs/*.md` 互相引用 (~50 处)
   - `.trae/plans/*.md` (~40 处)
   - `.ai-memory/evidence/*/` (~30 处)
   - scripts/ 下脚本注释 (~10 处)
3. 跑 `sync_skills.py --check` + `check_path_consistency.py` 验证

**优点**: 彻底消除歧义, 符合 TD-322 验收标准
**缺点**:
- 改动量大 (~200+ 处引用, 触发 B2 大修改)
- 遗漏风险高 (引用形式多样: spec-NN / spec-NN Phase X / "spec-NN commit" / 文件名等)
- 破坏 git blame 历史 (虽然 git mv 保留, 但引用更新 commit 会污染)
- evidence 文件改动后, 后续 N176 hash 回填会混乱

### 方案 B: 保留现状 + 加 spec_id 索引脚本 (wontfix 候选)

**操作**:
1. 新建 `scripts/governance/sync_spec_index.py`:
   - 扫描 `.trae/specs/*.md` frontmatter `spec_id:` 字段
   - 检测同号多版本 (spec-NN 出现 >1 次)
   - 生成 `.ai-memory/spec-index.md` (spec-NN → 文件全名 + 主题 + commit hash 映射表)
   - `--check` 模式: 同号多版本时 WARN (不阻塞)
2. 加 pre-commit hook `check_spec_id_collision.py`:
   - 检测新 spec 文件 spec_id 是否与已有冲突
   - 冲突时 exit 1 + 提示 "用 spec-NN-a/b 后缀或下一个空闲 spec-NN"
3. TD-322 wontfix: 现有同号多版本保留 (历史文件不动), 但新增 spec 强制唯一

**优点**:
- 改动量小 (~150 行脚本 + 5 tests)
- 不破坏 git blame / evidence 历史
- 解决新增 spec 冲突 (治本)
- 索引脚本提供消歧查询 (治标)

**缺点**: 不符合 TD-322 原验收标准 ("无同号多版本文件")

### 方案 C: 混合 — 重命名 16 文件 + 索引脚本 (引用更新分批)

**操作**:
1. 阶段 1 (本 spec): `git mv` 重命名 16 文件 + 更新文件内 `# spec-NN:` 标题 + frontmatter spec_id
2. 阶段 2 (后续 spec): 批量更新 active.md / fixed.md / wontfix.md 引用 (用脚本辅助)
3. 阶段 3 (后续 spec): 批量更新 lessons/ + evidence/ 引用
4. 同步加方案 B 的索引脚本 (防止新增冲突)

**优点**: 分阶段降低风险, 每阶段可独立验证
**缺点**: 跨多 spec/commit, 中间状态不一致

## 推荐: 方案 B (wontfix + 索引脚本)

**理由**:
1. **任务规模失衡**: 16 文件重命名 + 200+ 处引用更新 vs TD-322 收益 (消除"潜在歧义", 非现存 bug)
2. **git blame 污染**: 大量引用更新 commit 会污染文件历史, 影响后续考古
3. **evidence 完整性**: `.ai-memory/evidence/2026-07-20-spec42-self-evolution-flywheel/` 等目录名改动后, N176 hash 回填会混乱
4. **上下文消歧**: 现有引用虽用 spec-NN 简写, 但周围通常有日期/主题/commit hash 上下文, 实际歧义可消解
5. **治本优先**: 索引脚本 + pre-commit hook 防止新增冲突, 比追溯历史更值得

## 实施清单 (方案 B)

- [x] 新建 `scripts/governance/sync_spec_index.py` (~260 行):
  - 扫描 `.trae/specs/*.md` frontmatter `spec_id:` + `commit:` 字段
  - fallback 从文件名提取 spec-NN (兼容早期无 frontmatter 格式)
  - 生成 `.ai-memory/spec-index.md` (表格: spec_id | 文件名 | 标题 | commit | 日期 | 来源)
  - `--check` 模式: 同号多版本 → WARN (列出冲突, 不 exit 1)
  - `--dry-run` 模式: 只报告不写文件
- [x] 新建 `scripts/hooks/check_spec_id_collision.py` (~180 行):
  - pre-commit hook: 检测 staged spec 文件 spec_id 是否与已有冲突
  - 冲突 → exit 1 + 提示 "用 spec-NN-a/b 后缀或下一个空闲 spec-NN"
  - 历史 spec-36/38/39/41/42/43/44/45 同号多版本 wontfix (不阻塞, 仅防止新增)
  - `--force` / `--no-fail` 调试模式
- [x] 新建 `scripts/tests/test_sync_spec_index.py` (9 tests, 0.23s):
  - parse_frontmatter (提取所有字段 + 无 frontmatter 返回空)
  - extract_spec_id_from_filename (文件名 fallback)
  - scan_specs + detect_collisions (集成 + 冲突检测)
  - render_index (markdown 表格生成)
  - render_collisions_section (冲突段渲染)
  - hook 无 staged → exit 0
  - hook --force 模式
  - integration: 真实 repo 8 组 16 文件冲突检测
- [x] 注册 `gaf-spec-id-collision` hook 到 `.pre-commit-config.yaml` (pre-commit stage, 在 `gaf-b2-evidence` 之后)
- [x] TD-322 wontfix 评估 + 迁移到 wontfix.md (附方案 B 索引脚本作为 mitigation)
- [x] 生成 `.ai-memory/spec-index.md` (11616 bytes, 70 spec + 8 组 16 文件冲突 WARN)
- [x] sync_tech_debt_counts.py 同步 (active 16→15, wontfix 29→30, fixed 291 不变)

## 验证标准

1. ✅ `sync_spec_index.py` 生成 `.ai-memory/spec-index.md` 含 70 spec + 8 组 16 文件冲突 WARN
2. ✅ `check_spec_id_collision.py` 检测新增 spec_id 冲突 → exit 1 (历史 wontfix 不阻塞)
3. ✅ 9 tests 全通过 (0.23s, conda gaf env)
4. ✅ TD-322 wontfix 评估文档化 (附方案 B 索引作为 mitigation)
5. ✅ `.pre-commit-config.yaml` 注册 `gaf-spec-id-collision` hook (pre-commit stage)
6. ✅ Commit 时新 hook 正确通过 (commit -, 3 hooks 全 Passed)

## N176 hash 回填

本 spec 完成后 commit hash 立即回填到此 frontmatter (TD-303 N176 规则).
