# s31 — lesson frontmatter YAML 损坏修复 + d8 校验维度

> **类型**: refactor (数据修复 + 校验增强) | **日期**: 2026-08-17 | **来源**: 用户第四次"继续" → 轻量 L3-1 扫描发现 sync_ai_memory warning=69 (含 10 个 FrontMatterError)
> **状态**: ✅ 已归档 (2026-08-17, commit -) | **归档位置**: `docs/specs/archived/2026-08/2026-08-17-s31-yaml-frontmatter-fix.md`
> **关联**: sync_ai_memory (L1 warning) / doc_health_check (7 维度) / spec-41 (doc_health 框架) / spec-46 (d4 evidence 语义)

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit hash | 验收 evidence |
|------|------|---------|------------|--------------|
| Phase 1 修复 10 个 lesson frontmatter YAML | ✅ | 2026-08-17 | — | 10 文件 solution/trigger/title/related_td 单引号包裹; lessons 79 个全可 parse; 全仓库 FrontMatterError=0 |
| Phase 2 d8_yaml_frontmatter 维度 | ✅ | 2026-08-17 | — | d8_yaml_frontmatter.py 新建 + 注册 run_all_dimensions (7→8) + thresholds.yaml; 存量 4 个修复 (timeline-design summary / meta-governance related_td / spec68 title / backend-conventions key_decisions 缩进) |
| Phase 3 回归测试 + warning 归零 | ✅ | 2026-08-17 | — | test_doc_health_check.py +3 (d8 检出/合法/skip evidence); 62 passed; sync_ai_memory warning 69→59 (仅剩 evidence 无 frontmatter, 设计如此) |
| Phase 4 commit + 归档 | ✅ | 2026-08-17 | - | 20 文件 217+/15-; pre-commit + post-commit 全过; 已复制到 docs/specs/archived/2026-08/ |

## 背景与根因

`sync_ai_memory.py` 报 warning=69, 其中 10 个是 **FrontMatterError (YAML 解析失败)**:

```
N108/N109/N111/N112/N123/N144/N150-n153/N189/N196/N91-m2b-hook-failure
```

根因两类:
1. **值内含 `: ` (冒号+空格)**: YAML 把 `solution: 6 步超时应对: 5 段判别 → ...` 中 `solution:` 值里的 `key: value` 当作嵌套 mapping 解析 → "mapping values are not allowed here"
2. **N189 值以 `"` 开头但串内含未转义 `"`**: `solution: "AI 主导开发" 模式的治理复杂度...` — YAML 按 quoted string 解析, 串内 `"` 未转义 → 解析中断

影响: sync_ai_memory 无法 parse 这些 lesson (warning 累积); gaf-lesson-router 查询这些 lesson 时可能失败; doc_health 现有 7 维度均不检测 YAML 可 parse 性 (d5 skip lessons/, d4 只查路径)。

## Phase 1 详细任务 (数据修复)

| # | 文件 | 修复方案 |
|---|------|---------|
| 1 | N108-commit-rule-relaxation.md | solution: 加双引号 (值内含 `: `) |
| 2 | N109-decision-relaxation.md | solution: 加双引号 |
| 3 | N111-command-timeout.md | solution: 加双引号 |
| 4 | N112-p024-frontend-sync.md | solution: 加双引号 |
| 5 | N123-ai-memory-restructure.md | solution: 加双引号 |
| 6 | N144-r37-p3-c5-antd-deprecation-and-fetch-on-mount.md | solution: 加双引号 |
| 7 | N150-n153-pre-commit-stash-governance.md | solution: 加双引号 |
| 8 | N189-ai-led-development-governance-necessity.md | trigger: 双引号包裹 + 内部 `"` 转义 (值以 `"` 开头) |
| 9 | N196-real-device-pipeline-test-workflow.md | trigger: 加双引号 (值内含 `: `) |
| 10 | N91-m2b-hook-failure.md | solution: 加双引号 |

加引号原则: 值内含 `: ` 或 `#` 或 `"` 时用双引号包裹; 值内已有 `"` 时用单引号包裹 (YAML 单引号内 `"` 不需转义); 优先最小改动 (仅受影响字段)。

## Phase 2 详细任务 (d8 维度)

新建 `scripts/governance/check_dimensions/d8_yaml_frontmatter.py`:
- 扫描 `.ai-memory/` + `docs/` 下所有 `*.md`
- 以 `---` 开头的文件: split frontmatter → `yaml.safe_load`
- `yaml.YAMLError` → Issue (dimension=d8_yaml_frontmatter, severity=P1, file, evidence 含错误行号)
- thresholds 配置: `severity: "P1"` (可覆盖)

注册到 `doc_health_check.py` run_all_dimensions (7 → 8 维度)。
`thresholds.yaml` 加 `d8_yaml_frontmatter` 段。

## 验收标准

1. `sync_ai_memory.py` 重跑: FrontMatterError = 0 (10 个文件全部可 parse)
2. `doc_health_check.py` 重跑: d8_yaml_frontmatter 报 0 issues (无新增损坏)
3. `test_doc_health_check.py` + 3 测试: d8 检出损坏 YAML / 合法 YAML 无 issue / evidence skip
4. warning 从 69 降到仅剩无 frontmatter 类 (evidence/ 设计如此, 不修)
5. 提交前 `git status` 无未暂存残留; 只 add 明确修改文件

## 已知限制

- evidence/ 下 40+ 文件无 frontmatter (problem/solution/verification 三件套是结构化快照, 设计如此) — d8 只报 YAML 解析失败, 不报"无 frontmatter"
- lessons/archived-early/ 等 20+ 文件缺 maintainer (隐式 manual, sync_ai_memory 合法跳过) — 非本 spec 范围
- 修复后 sync_ai_memory 的 warning 仍可能 >0 (no front matter 类) — 目标是 FrontMatterError=0
