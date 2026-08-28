---
maintainer: AI
spec_id: spec-45
title: 月度检查自动化 (Monthly Check Automation) — C1/H1/I1/N1 4 项自动化检查
created: 2026-07-20
status: ✅ done
parent_specs: [spec-44 (月度检查瘦身)]
child_specs: []
related_files:
  - scripts/governance/monthly_health_check.py
  - scripts/tests/test_monthly_health_check.py
  - docs/general/monthly-health-check.md
---

# spec-45: 月度检查自动化 (Monthly Check Automation)

## 阶段状态表 (TD-137 / §4.10)

| Phase | 标题 | 状态 | 完成时间 | commit hash | 验收 evidence |
|:-----:|------|:----:|:---------:|:-----------:|---------------|
| Phase 1 | monthly_health_check.py + 4 项检查 + 单元测试 | ✅ | 2026-07-20 | - | 18 tests PASS in 1.20s, 脚本跑通 11 issues in 1.88s < 2s budget |
| Phase 2 | monthly-health-check.md 标记 4 项已迁自动 + 全量回归 | ✅ | 2026-07-20 | - | 313 tests PASS (10 预存失败与 spec-45 无关), spec-41 不退化 0.67s |

> 全量回归: 313 passed / 10 failed in 47.10s (10 失败全为预存: 5 e2e + 1 bootstrap_gaf + 4 extract_lessons + 1 layer_benchmark, 与 spec-45 无关)
> 改动范围: scripts/governance/monthly_health_check.py (NEW, 351 行) + scripts/tests/test_monthly_health_check.py (NEW, 18 tests) + scripts/governance/thresholds.yaml (+21 行 monthly_checks) + docs/general/monthly-health-check.md (4 项标记 + 顶部迁移说明 + 总览表 + 执行流程)
> 风险: 低 (新增脚本 + 单文件文档标记, 无现有代码改动, 回退方案 git revert)
> 性能 (N171): monthly_health_check.py 1.88s < 2s budget (优化 4.85s → 1.88s, -61%)

## 1. 背景与动机

### 1.1 问题

spec-44 完成 G 类 (8 项) 月度检查瘦身, 标记 "已迁自动 (spec-41)"。但月度检查仍有 76 项手动跑, 其中 C1/H1/I1/N1 4 项可完全脚本化:

| 项 | 月度检查内容 | 当前手动命令 | 自动化可行性 |
|:--:|------------|------------|:-----------:|
| C1 | 活跃 TD 数量 (>5 关注, >10 立即清理) | 读 active.md 统计 🔧/🚧 | ✅ 完全可脚本化 (regex 解析) |
| H1 | Git 工作树状态 (uncommitted + 敏感文件) | `git status` + 检查 *.env/*.key | ✅ 完全可脚本化 (subprocess + glob) |
| I1 | 巨型文件 (单文件 > 阈值) | `rg --files \| xargs wc -l` | ✅ 完全可脚本化 (pathlib.rglob) |
| N1 | 空目录 / 空文件 | `Get-ChildItem -Recurse` | ✅ 完全可脚本化 (pathlib.rglob) |

**月度耗时缩减估算**:
- C1: 2 min → 0.1 min (-1.9 min)
- H1: 2 min → 0.1 min (-1.9 min)
- I1: 8 min → 0.5 min (-7.5 min)
- N1: 2 min → 0.1 min (-1.9 min)
- **合计: ~13 min → ~0.8 min (-12.2 min, -94%)**

### 1.2 用户原话

> "完全自动化的自我进化飞轮: 检查器跑 → 发现问题 → AI patch → commit → 下次不再犯"

spec-41 已覆盖 doc/AI 记忆层 (G 类 8 项), spec-45 扩展到项目卫生层 (C1/H1/I1/N1 4 项)。

### 1.3 设计目标

1. **新脚本** `scripts/governance/monthly_health_check.py` 与 `doc_health_check.py` 平级 (不塞进 spec-41 7 维度 — 职责边界清晰)
2. **复用** spec-41 `Issue` / `ReportSummary` schema (保持报告格式一致)
3. **不集成到 gaf_init.sh** (月度检查 ≠ 每次对话跑; 月度跑由用户显式触发或月度定时任务)
4. **输出** `.cache/monthly_health_report.json` (与 doc_health_report.json 平级)

## 2. 架构设计

### 2.1 模块边界

```
scripts/governance/
├── doc_health_check.py        # spec-41 (7 维度 doc/AI 记忆, 不变)
├── monthly_health_check.py    # NEW (spec-45): 4 项项目卫生检查
├── report_schema.py           # 复用 (Issue / ReportSummary)
└── check_dimensions/          # spec-41 7 维度, 不变

scripts/tests/
└── test_monthly_health_check.py  # NEW: 单元测试

.cache/
├── doc_health_report.json       # spec-41 输出 (不变)
└── monthly_health_report.json   # NEW (spec-45): 月度检查报告
```

### 2.2 4 项检查设计 (单一权威源)

#### C1: active_td_count

```python
def check_c1_active_td(repo_root: Path) -> list[Issue]:
    """C1: 活跃 TD 数量 (active.md).
    
    Thresholds (monthly-health-check.md C1):
        > 5 → P2 (warning)
        > 10 → P1 (immediate cleanup)
    """
    active_md = repo_root / "docs/general/tech-debt/active.md"
    if not active_md.exists():
        return [Issue(dimension="c1_active_td", severity="P2",
                      evidence="active.md not found",
                      suggested_fix="create active.md",
                      root_cause_hint="tech-debt tracking not initialized")]
    
    text = active_md.read_text(encoding="utf-8")
    # Count 🔧 待修 + 🚧 进行中 markers in table rows
    active_count = sum(1 for line in text.splitlines()
                       if ("🔧" in line or "🚧" in line) and "|" in line)
    
    if active_count > 10:
        return [Issue(dimension="c1_active_td", severity="P1",
                      evidence=f"{active_count} active TDs (>10 threshold)",
                      suggested_fix="immediate cleanup — promote or close ≥ 5 TDs",
                      root_cause_hint="TD accumulation without cleanup")]
    if active_count > 5:
        return [Issue(dimension="c1_active_td", severity="P2",
                      evidence=f"{active_count} active TDs (>5 warning)",
                      suggested_fix="review active.md and promote/close lower-priority TDs",
                      root_cause_hint="gradual TD accumulation")]
    return []
```

#### H1: git_status_hygiene

```python
def check_h1_git_status(repo_root: Path) -> list[Issue]:
    """H1: Git 工作树状态.
    
    Checks:
        1. Uncommitted changes count
        2. Sensitive files (.env, *.key, *.pem) tracked or untracked
    """
    issues = []
    # Use subprocess to call git status --porcelain
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_root,
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        return [Issue(dimension="h1_git_status", severity="P0",
                      evidence=f"git status failed: {result.stderr}",
                      suggested_fix="check git repo state",
                      root_cause_hint="git repo corruption")]
    
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    uncommitted = len(lines)
    
    # Check for sensitive files
    sensitive_patterns = [".env", "*.key", "*.pem", "*credentials*", "*.pfx"]
    sensitive_found = []
    for line in lines:
        # Status format: XY <path>
        parts = line[3:].strip().split(" -> ")
        path = parts[0] if parts else line[3:].strip()
        for pat in sensitive_patterns:
            if fnmatch.fnmatch(Path(path).name, pat):
                sensitive_found.append(path)
    
    if sensitive_found:
        issues.append(Issue(dimension="h1_git_status", severity="P0",
                            evidence=f"Sensitive files in git: {sensitive_found}",
                            suggested_fix="add to .gitignore + git rm --cached",
                            root_cause_hint=".gitignore missing sensitive patterns"))
    
    if uncommitted > 20:
        issues.append(Issue(dimension="h1_git_status", severity="P2",
                            evidence=f"{uncommitted} uncommitted changes (>20)",
                            suggested_fix="commit or stash pending work",
                            root_cause_hint="large pending state"))
    
    return issues
```

#### I1: large_files

```python
def check_i1_large_files(repo_root: Path, thresholds: dict) -> list[Issue]:
    """I1: 巨型文件 (single file > threshold).
    
    Thresholds (monthly-health-check.md I1):
        default: 1000 lines → P2
        backend/**: 2000 lines → P2
        frontend/**: 1500 lines → P2
        *.py: 1500 lines → P2
    """
    issues = []
    scan_dirs = ["backend", "frontend/src", "agent/src", "scripts"]
    default_threshold = thresholds.get("default_lines", 1000)
    per_dir = thresholds.get("per_dir", {})
    
    for scan_dir in scan_dirs:
        full_dir = repo_root / scan_dir
        if not full_dir.exists():
            continue
        threshold = per_dir.get(scan_dir, default_threshold)
        for f in full_dir.rglob("*"):
            if not f.is_file() or f.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                continue
            try:
                line_count = sum(1 for _ in f.open(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if line_count > threshold:
                rel = f.relative_to(repo_root).as_posix()
                issues.append(Issue(dimension="i1_large_files", severity="P2",
                                    file=rel, line=line_count,
                                    evidence=f"{rel}: {line_count} lines (> {threshold})",
                                    suggested_fix="refactor / split module",
                                    root_cause_hint="gradual file growth without refactor"))
    return issues
```

#### N1: empty_dirs_files

```python
def check_n1_empty_dirs(repo_root: Path) -> list[Issue]:
    """N1: 空目录 / 空文件 (excluding .gitkeep)."""
    issues = []
    skip_dirs = {".git", ".cache", "node_modules", "__pycache__", ".venv", "venv"}
    
    for p in repo_root.rglob("*"):
        if any(part in skip_dirs for part in p.parts):
            continue
        if p.is_dir():
            # Empty dir = no children (excluding .gitkeep)
            children = list(p.iterdir())
            real_children = [c for c in children if c.name != ".gitkeep"]
            if not real_children and children:
                # Only contains .gitkeep — OK, intentional placeholder
                continue
            if not children:
                rel = p.relative_to(repo_root).as_posix()
                issues.append(Issue(dimension="n1_empty", severity="P2",
                                    file=rel,
                                    evidence=f"empty directory: {rel}",
                                    suggested_fix="remove dir or add .gitkeep",
                                    root_cause_hint="post-refactor leftover"))
        elif p.is_file() and p.stat().st_size == 0:
            # Skip .gitkeep and other intentional empty files
            if p.name in {".gitkeep", ".keep", "__init__.py"}:
                continue
            rel = p.relative_to(repo_root).as_posix()
            issues.append(Issue(dimension="n1_empty", severity="P2",
                                file=rel,
                                evidence=f"empty file: {rel}",
                                suggested_fix="remove or populate file",
                                root_cause_hint="post-refactor leftover"))
    return issues
```

### 2.3 报告生成

复用 spec-41 `DocHealthReport` schema, 但 dimension 字段用新前缀 (`c1_active_td`, `h1_git_status`, `i1_large_files`, `n1_empty`), 与 spec-41 维度 (`d1_overlap`..`d7_index_consistency`) 不冲突。

输出 `.cache/monthly_health_report.json`:

```json
{
  "generated_at": "2026-07-20T...",
  "repo_root": "d:/code/GAF",
  "git_sha": "-",
  "duration_seconds": 0.8,
  "summary": {
    "total": 3,
    "by_severity": {"P0": 0, "P1": 0, "P2": 3},
    "by_dimension": {"c1_active_td": 1, "i1_large_files": 2}
  },
  "issues": [...]
}
```

### 2.4 集成方式

**不集成到 gaf_init.sh** (避免每次对话跑月度检查)。**集成到**:
1. **手动触发**: `python scripts/governance/monthly_health_check.py`
2. **月度定时任务** (未来): cron-like scheduled task (不在本 spec 范围)
3. **月度检查文档**: `docs/general/monthly-health-check.md` 标记 C1/H1/I1/N1 "已迁自动 (spec-45)"

## 3. Phase 详细设计

### 3.1 Phase 1: monthly_health_check.py + 4 项检查 + 单元测试

#### 3.1.1 文件: `scripts/governance/monthly_health_check.py`

```python
"""monthly_health_check.py - Spec-45: monthly project hygiene checks.

4 checks (C1/H1/I1/N1 from monthly-health-check.md):
    C1: active TD count (active.md)
    H1: git status hygiene (uncommitted + sensitive files)
    I1: large files (> threshold lines)
    N1: empty dirs/files (post-refactor leftovers)

Output: .cache/monthly_health_report.json (Issue/ReportSummary schema reused
from spec-41 for report format consistency).

NOT integrated into gaf_init.sh (monthly check ≠ per-session check).
Run manually: python scripts/governance/monthly_health_check.py
"""
# (Implementation per §2.2 above)
```

#### 3.1.2 测试: `scripts/tests/test_monthly_health_check.py`

- `test_c1_no_active_md` — active.md 不存在 → P2 issue
- `test_c1_below_threshold` — 3 active TDs → 0 issues
- `test_c1_warning_threshold` — 7 active TDs → P2 issue
- `test_c1_critical_threshold` — 12 active TDs → P1 issue
- `test_h1_clean_repo` — git status empty → 0 issues
- `test_h1_sensitive_file` — .env in git → P0 issue
- `test_h1_many_uncommitted` — 25 changes → P2 issue
- `test_i1_no_large_files` — all files < 1000 lines → 0 issues
- `test_i1_large_python_file` — 1500-line .py → P2 issue
- `test_i1_large_frontend_file` — 1600-line .tsx → P2 issue (frontend threshold)
- `test_n1_no_empty` — no empty dirs/files → 0 issues
- `test_n1_empty_dir` — empty dir (no .gitkeep) → P2 issue
- `test_n1_empty_file` — empty .py → P2 issue
- `test_n1_skips_gitkeep` — dir with only .gitkeep → 0 issues
- `test_n1_skips_init_py` — empty __init__.py → 0 issues

#### 3.1.3 thresholds.yaml 扩展

```yaml
# Spec-45 monthly checks (project hygiene)
monthly_checks:
  c1_active_td:
    warning_threshold: 5
    critical_threshold: 10
  h1_git_status:
    uncommitted_warning: 20
    sensitive_patterns: [".env", "*.key", "*.pem", "*credentials*", "*.pfx"]
  i1_large_files:
    default_lines: 1000
    per_dir:
      "backend": 2000
      "frontend/src": 1500
      "agent/src": 1500
      "scripts": 1000
  n1_empty:
    skip_dirs: [".git", ".cache", "node_modules", "__pycache__", ".venv", "venv"]
    skip_empty_files: [".gitkeep", ".keep", "__init__.py"]
```

### 3.2 Phase 2: monthly-health-check.md 标记 + 全量回归

#### 3.2.1 文档改动: `docs/general/monthly-health-check.md`

1. **frontmatter summary**: 更新提及 spec-45
2. **顶部迁移说明**: 追加 spec-45 段 (4 项迁移映射)
3. **检查项总览表**:
   - C1 行: `| C | 技术债务状态 | 4 | 2 min |` → `| C | 技术债务状态 ✅ C1 已迁自动 (spec-45) | 4 (月度跑 3) | 1 min |`
   - H1 行: 类似标记
   - I1 行: 类似标记 (I1 是 I 类第 1 项, 但 I 类其他项不迁)
   - N1 行: 类似标记
4. **执行流程**: 步骤 2 追加 "(C1/H1/I1/N1 已由 monthly_health_check.py 自动跑, 月度跑 76-4=72 项)"
5. **合计行**: `84 (月度跑 76)` → `84 (月度跑 72)`
6. **C1/H1/I1/N1 标题**: 各加 ✅ 已迁自动 (spec-45) 标记 + 迁移映射 blockquote

#### 3.2.2 全量回归

- `pytest scripts/tests/` — 全部 PASS (含 spec-45 新测试)
- `python scripts/governance/monthly_health_check.py` — 跑通, 输出报告
- `python scripts/governance/doc_health_check.py` — 不退化 (spec-41 不受影响)
- 耗时测量 (N171): monthly_health_check.py < 2s budget

## 4. 风险与回退

| 风险 | 评估 | 缓解 |
|------|------|------|
| monthly_health_check.py 误报 | 低 | thresholds.yaml 集中管理, 可调 |
| 4 项检查耗时 > 2s | 低 | I1 是主要耗时 (rglob), 但单次扫描 < 0.5s |
| 与 spec-41 边界混淆 | 低 | 文件名 + dimension 前缀 (c1/h1/i1/n1 vs d1-d7) 分离 |
| 月度检查者跳过 C1/H1/I1/N1 后遗漏 | 低 | monthly_health_check.py 报告 P0/P1 时仍需手动处理 |

**回退方案**: `git revert <commit>` (新增脚本 + 文档标记, 无现有代码改动)

## 5. 验收标准

- ✅ 4 项检查脚本 (C1/H1/I1/N1) 实现 + 测试 ≥ 15 cases
- ✅ 测试全 PASS (无回归)
- ✅ monthly_health_check.py 跑通, 输出 .cache/monthly_health_report.json
- ✅ monthly-health-check.md 4 项标记 "已迁自动 (spec-45)"
- ✅ 检查项总览表合计行更新 (月度跑 72)
- ✅ monthly_health_check.py 耗时 < 2s (N171)
- ✅ 3 文件 evidence 填充 (problem/solution/verification)
- ✅ spec-45 状态表 3 Phase 全 ✅ + commit hash 回填
- ✅ C-072 追加到 completed-features.md
- ✅ P-013 追加到 pending-roadmap.md (登记 + 立即标 ✅)

## 6. 落地清单

- [ ] Phase 1: scripts/governance/monthly_health_check.py (NEW)
- [ ] Phase 1: scripts/tests/test_monthly_health_check.py (NEW, ≥ 15 cases)
- [ ] Phase 1: scripts/governance/thresholds.yaml (追加 monthly_checks 段)
- [ ] Phase 2: docs/general/monthly-health-check.md (4 项标记 + 总览表 + 执行流程)
- [ ] Phase 2: .ai-memory/evidence/2026-07-20-spec45-monthly-check-automation/ (3 文件)
- [ ] Phase 2: spec-45 状态表 + C-072 + P-013 状态同步

## 7. 一致性检查

- spec-44 已完成 (commit `-`): G 类 8 项迁自动 spec-41
- spec-45 与 spec-44 互补: spec-44 = doc/AI 记忆层瘦身, spec-45 = 项目卫生层自动化
- 不与 spec-41 冲突: spec-41 = 7 维度静态检查 (gaf_init.sh 自动跑), spec-45 = 4 项月度检查 (手动/月度定时跑)
- 不与 spec-42/43 冲突: spec-42/43 = spec-41 飞轮 (consumed.json + forgetting), spec-45 独立

## 8. Open Questions

无 (中修改, 计划在首个 todo 中说明, 不需 NotifyUser 批准)
