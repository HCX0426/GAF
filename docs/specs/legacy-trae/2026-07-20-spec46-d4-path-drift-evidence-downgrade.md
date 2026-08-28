---
spec_id: spec-46
title: d4_path_drift evidence/ 降级 + GAF/ 前缀批量修复
status: ✅ done
created: 2026-07-20
owner: AI
n167_score: 21/21 (AI 自决)
related: spec-41 (doc_health_check), spec-42 (飞轮 patch)
---

# Spec-46: d4_path_drift evidence/ 降级 + GAF/ 前缀批量修复

## 阶段状态表 (TD-137 / §4.10)

| Phase | 标题 | 状态 | 完成时间 | commit hash | 验收 evidence |
|:-----:|------|:----:|:---------:|:-----------:|---------------|
| Phase 1 | d4_path_drift 检查器降级 evidence/ 到 P2 + 测试 | ✅ | 2026-07-20 | - | 3 新测试 PASS + 8 原有 PASS, d4_path_drift P0 343→181 (evidence/ 降级) |
| Phase 2 | 批量修复 GAF/ 前缀错误 + 全量回归 | ✅ | 2026-07-20 | - | 174 GAF/ 前缀 strip from 44 files, P0 181→173, 317 passed / 9 预存 failed |

> 全量回归: 317 passed / 9 failed in 144.52s (9 失败全为预存: 5 e2e + 4 extract_lessons, 与 spec-46 无关); 比基线 +4 passed -1 failed (改善)
> 改动范围: scripts/governance/check_dimensions/d4_path_drift.py (加 evidence_severity 配置) + scripts/governance/thresholds.yaml (+ evidence_severity: "P2") + scripts/tests/test_doc_health_check.py (+3 tests) + 44 个 evidence/lessons 文件 (批量 strip GAF/ 前缀)
> 风险: 低 (检查器改动有向后兼容性测试; 批量脚本只改 frontmatter list item, regex 锚定; 真实漂移 173 P0 登记为 TD-279 后续处理)

## 1. 背景

### 1.1 问题描述

spec-45 commit 后跑 `doc_health_check.py` 报 **404 issues**,其中 **d4_path_drift P0 = 343**。
这是飞轮读侧的严重阻塞 — spec-42 飞轮 patch 应该处理 P0,但 343 个 P0 全是 evidence/lessons
的 `related_files` frontmatter 引用了已删除/迁移的历史文件,飞轮 patch 不知道如何修复
(不是规则文档路径漂移,是 evidence 文件路径漂移)。

### 1.2 P0 分布 (L3-1 扫描结果)

| 类别 | 数量 | 性质 | 修复策略 |
|------|:----:|------|----------|
| `.ai-memory/evidence/` | 162 | 历史快照 (代码后续重构不应追溯更新) | **降级到 P2** (Phase 1) |
| lessons/ GAF/ 前缀错误 | 8 | 路径前缀错误 (写了 `GAF/scripts/...`) | **批量 strip GAF/** (Phase 2) |
| evidence/ GAF/ 前缀错误 | 156 | 同上,但 evidence/ 已降级 | **批量 strip GAF/** (Phase 2, 保持历史快照整洁) |
| lessons/summaries/platforms 真实漂移 | 171 | 文件已删除/移动,引用过期 | **登记为 TD** (Phase 3, 后续 spec 处理) |
| **合计** | **343** | | |

### 1.3 根因

`d4_path_drift.py` 注释 (line 64-65):
> "Frontmatter `related_files` is always scanned (it is a contract, not a historical mention)."

这个假设对 lessons/summaries 是合理的 (它们是"当前有效的教训/总结"),
但对 **evidence/ 是不合理的** — evidence 是"历史快照",记录当时改了哪些文件,
后续代码重构/删除不应追溯更新 evidence 的 `related_files`。

## 2. 架构决策

### 2.1 方案对比 (N167 七维度评分)

| 方案 | ① 架构 | ② 归一化 | ③ 兼容 | ④ 完善 | ⑤ 性能 | ⑥ 安全 | ⑦ 维护 | 总分 | 自决? |
|------|:----:|:------:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
| A: Phase 1 (降级 evidence/) + Phase 2 (批量修复 GAF/ 前缀) | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 21 | ✅ |
| B: 只 Phase 1 (降级 evidence/) | 3 | 3 | 3 | 2 | 3 | 3 | 3 | 20 | ❌ |
| C: 不开 spec,登记 TD | 1 | 1 | 3 | 1 | 1 | 3 | 1 | 11 | ❌ |

**自决决策**: A (总分 21/21 ≥ 19, 领先 B 1 分,但 Phase 2 工作量极小 — 8 个文件批量脚本,
合并到 spec-46 是自然组合,不需要 AskUserQuestion 弹窗)

**硬场景检查** (§7.4): ① FK 绊住? N ② schema 分裂? N ③ 业务语义? N ④ 不可逆? N

### 2.2 模块边界

- **d4_path_drift.py**: 加目录级 severity 配置 (evidence/ 用 P2, 其他保持 P0)
- **thresholds.yaml**: `d4_path_drift.evidence_severity: "P2"` (新增字段,与现有 `severity: "P0"` 平级)
- **批量修复脚本**: `.trash/strip_gaf_prefix.py` (临时脚本,跑完即删,不持久化)

### 2.3 不修复真实漂移的理由

Phase 3 (真实漂移 171 P0) 涉及 ~30 个文件,需要逐个分析 (是文件被删除/移动了,需要更新引用或转换为描述性文字)。
工作量大,超出 spec-46 范围。登记为 TD,后续 spec 处理。

## 3. Phase 1: d4_path_drift 检查器降级 evidence/ 到 P2

### 3.1 改动

#### `scripts/governance/check_dimensions/d4_path_drift.py`

`check()` 函数加目录级 severity 配置:

```python
def check(repo_root: Path, thresholds: dict) -> list[Issue]:
    issues: list[Issue] = []
    default_severity = thresholds.get("severity", "P0")
    evidence_severity = thresholds.get("evidence_severity", default_severity)
    scan_dirs = [repo_root / "docs", repo_root / ".ai-memory", repo_root / ".trae"]
    body_scan_prefixes = (".ai-memory/lessons/", ".ai-memory/summaries/")

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            rel = md_file.relative_to(repo_root).as_posix()
            try:
                content = md_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            # Determine severity for this file (evidence/ uses P2 — historical snapshot)
            if rel.startswith(".ai-memory/evidence/"):
                severity = evidence_severity
            else:
                severity = default_severity

            # Check frontmatter related_files (always — it is a contract)
            # ... (existing logic, but use `severity` variable instead of fixed `severity`)
```

#### `scripts/governance/thresholds.yaml`

```yaml
d4_path_drift:
  severity: "P0"
  evidence_severity: "P2"  # Spec-46: evidence/ is historical snapshot, not a contract
```

### 3.2 测试

新增 2 个测试 in `scripts/tests/test_doc_health_check.py`:

1. `test_d4_path_drift_evidence_dir_uses_p2_severity`:
   - 在 `.ai-memory/evidence/test/solution.md` 写 frontmatter 引用不存在的文件
   - 跑 `d4_path_drift.check(tmp_path, {"severity": "P0", "evidence_severity": "P2"})`
   - 断言: issue.severity == "P2" (不是 P0)

2. `test_d4_path_drift_lessons_dir_uses_default_severity`:
   - 在 `.ai-memory/lessons/test.md` 写 frontmatter 引用不存在的文件
   - 跑 `d4_path_drift.check(tmp_path, {"severity": "P0", "evidence_severity": "P2"})`
   - 断言: issue.severity == "P0" (lessons/ 保持 P0,因为是契约)

### 3.3 验收

- 2 个新测试 PASS
- 现有 d4_path_drift 测试全 PASS (无回归)
- `doc_health_check.py` 跑通: d4_path_drift P0 从 343 降到 181 (162 evidence 降级)
- `doc_health_check.py` 耗时 < 1s (不退化)

## 4. Phase 2: 批量修复 GAF/ 前缀错误

### 4.1 改动

写临时脚本 `.trash/strip_gaf_prefix.py`:

```python
"""Strip GAF/ prefix from frontmatter related_files entries."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [REPO_ROOT / ".ai-memory" / "evidence", REPO_ROOT / ".ai-memory" / "lessons"]

def strip_gaf_prefix(content: str) -> tuple[str, int]:
    """Strip GAF/ prefix from related_files entries. Returns (new_content, count)."""
    if not content.startswith("---"):
        return content, 0
    parts = content.split("---", 2)
    if len(parts) < 3:
        return content, 0
    fm = parts[1]
    # Match lines like:  - GAF/scripts/...  or  - GAF/.pre-commit-config.yaml
    pattern = re.compile(r"^(\s*-\s+)GAF/(.+)$", re.MULTILINE)
    new_fm, count = pattern.subn(r"\1\2", fm)
    if count == 0:
        return content, 0
    return "---" + new_fm + "---" + parts[2], count

total = 0
for scan_dir in SCAN_DIRS:
    for md_file in scan_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        new_content, count = strip_gaf_prefix(content)
        if count > 0:
            md_file.write_text(new_content, encoding="utf-8")
            print(f"  {md_file.relative_to(REPO_ROOT)}: stripped {count} GAF/ prefixes")
            total += count
print(f"Total: stripped {total} GAF/ prefixes")
```

跑脚本 → 验证 d4_path_drift P0 减少 164 (162 evidence + 8 lessons — 但 evidence 已降级,实际 P0 减少 8)。

### 4.2 验收

- 脚本跑通,输出 "Total: stripped N GAF/ prefixes"
- `doc_health_check.py` 跑通: d4_path_drift P0 从 181 降到 ~173 (8 lessons/ GAF/ 前缀修复)
- evidence/ 的 GAF/ 前缀也修复 (保持历史快照整洁,虽然已降级到 P2)
- 脚本跑完即删 (不持久化)

## 5. 风险

- **风险 1**: d4_path_drift 检查器改动可能影响现有测试
  - 缓解: 新增 2 个测试 + 跑现有全量测试
- **风险 2**: 批量脚本可能误改非 frontmatter 的 GAF/ 字符串
  - 缓解: 脚本只匹配 frontmatter 内的 `- GAF/...` 模式 (regex 锚定 `^(\s*-\s+)GAF/`)
- **风险 3**: 真实漂移 171 P0 仍在,飞轮读侧仍有阻塞
  - 缓解: 登记为 TD, P0 从 343 降到 ~173 已是重大改善 (飞轮 patch 可聚焦处理)

## 6. 落地清单

- [ ] Phase 1: d4_path_drift.py 加目录级 severity 配置
- [ ] Phase 1: thresholds.yaml 加 `evidence_severity: "P2"`
- [ ] Phase 1: 新增 2 个测试
- [ ] Phase 1: 跑 doc_health_check.py 验证 P0 从 343 降到 181
- [ ] Phase 2: 写 `.trash/strip_gaf_prefix.py` 脚本
- [ ] Phase 2: 跑脚本批量修复
- [ ] Phase 2: 跑 doc_health_check.py 验证 P0 从 181 降到 ~173
- [ ] Phase 2: 跑全量回归 (313 passed baseline)
- [ ] Phase 2: 删除临时脚本
- [ ] 登记 TD: 真实漂移 171 P0 (Phase 3, 后续 spec 处理)
- [ ] evidence 3 文件 (problem/solution/verification)
- [ ] 更新 completed-features.md (C-073)
- [ ] 更新 pending-roadmap.md (P-014)
- [ ] 更新状态表 + commit hash 回填

## 7. 一致性检查

- ✅ 不集成到 gaf_init.sh (检查器改动自动生效,无需额外集成)
- ✅ 复用 spec-41 Issue schema (无新 schema)
- ✅ 与 spec-41 7 维度检查平级 (d4_path_drift 是维度 4)
- ✅ 与 spec-45 月度检查无冲突 (不同检查器,不同维度)

## 8. Open Questions

- Q1: Phase 3 (真实漂移 171 P0) 是否开 spec-47?
  - A1: 登记为 TD, 评估后决定。如果飞轮 patch 能自动处理,就不开 spec; 否则开 spec-47。
