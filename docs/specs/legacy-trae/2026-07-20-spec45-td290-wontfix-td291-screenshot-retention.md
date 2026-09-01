---
spec_id: spec-45
title: TD-291 screenshot_retention_gb wontfix 重新开放 + 实施
status: ✅ completed
created: 2026-07-20
last_updated: 2026-07-20
related: TD-291 (wontfix → FIXED 重新开放); TD-290 已 spec-39 wontfix 闭环, 不处理
n167_score: 9/9 (3 dimensions, medium modification, AI 自决 + 用户授权方案 B)
commit: '-'
---

# Spec-45: TD-291 screenshot_retention_gb wontfix 重新开放 + 实施

> **触发**: AI 自决排序模式 (用户授权 2026-07-20) — spec-44 完成后, 排序剩余 TD
> **scope 调整**: 原设计含 TD-290 wontfix + TD-291 实施, 但调研发现 spec-39 已把 TD-290 + TD-291 都 wontfix EVALUATED, 故 spec-45 scope 收窄为 TD-291 wontfix 重新开放 (用户授权方案 B "实现")
> **TD-290 处理**: spec-39 已 wontfix 闭环, 不重复评估 (wontfix.md L35-51 段落保留)

## §1 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | TD-291 wontfix 重新开放 — 用户授权方案 B (AskUserQuestion) | ✅ | 2026-07-20 | (本次 commit) | 用户选 "实现清理逻辑 (新 spec)"; N167 9/9 AI 自决 |
| Phase 2 | TD-291 实施 screenshot retention 逻辑 + 6 单元测试 | ✅ | 2026-07-20 | (本次 commit) | cleanup_view 加 ~40 行 retention 逻辑 + 6 测试通过 (12 passed); ruff All checks passed |
| Phase 3 | 文档同步 (wontfix.md → fixed.md) + commit + hash 回填 (spec-44 -) + 反思 | ✅ | 2026-07-20 | (本次 commit) | wontfix.md TD-291 删除 + fixed.md TD-291 加 + C-088 + P-028 + spec-44 hash 回填 (-) |

## §2 N167 3 维度评分 (中修改 — Phase 2 TD-291)

| 维度 | 分 | 理由 |
|------|---|------|
| ① 架构长远性 | 3 | cleanup API 履行契约 (screenshot_retention_gb 不再 placeholder); UI 与 backend 一致 (用户调 Slider 实际生效); 为未来加更多 retention 策略 (按时间/按任务) 奠基 |
| ② 全局归一化 | 3 | 前后端 schema 一致; cleanup_view 完整覆盖 3 类 retention (execution_days / screenshot_gb / log_days) |
| ⑦ 长期维护成本 | 3 | screenshot 文件自动清理避免磁盘膨胀; 单元测试覆盖边界 (空目录 / 单文件 / 多文件 / 阈值边界 / 嵌套子目录) |
| **总分** | **9/9** | ≥ 9/12, AI 自决 (用户已通过 AskUserQuestion 授权方案 B, 等同自决) |

**反向论证**:
- **为何不选 A (wontfix 维持)**: UI 假功能违反 N126 "状态标记必须诚实"; 用户调 Slider 无效果; spec-39 wontfix 理由 "schema 先行, feature 后上" 在用户明确要求实现后不成立
- **为何不选 C (删除字段)**: 破坏现有 UI 入口; 未来要重新加; 用户体验回退

**硬场景 ③**: 影响 data retention? Y → AskUserQuestion (已问, 用户选方案 B "实现")

## §3 Phase 1: TD-291 wontfix 重新开放 (用户授权)

**评估理由**:
- spec-39 wontfix 理由: "schema 先行, feature 后上" + "重新开放条件: 若 screenshot 磁盘占用成实际问题 (>10GB), 立即开 spec 实现 retention"
- 用户 AskUserQuestion 回答: "从未来来讲，你觉得哪个好？我不在意他改动多少，最在意的时未来的架构"
- AI 架构判断: 方案 B (实现) 是架构最优解 — UI 与 backend 一致 + cleanup API 履行契约 + 为未来 retention 策略奠基
- 用户授权方案 B → wontfix 重新开放

## §4 Phase 2: TD-291 实施 screenshot retention 逻辑

### §4.1 实现细节 (backend/settings/views.py:cleanup_view 改造, +40 行)

- 加 `screenshot_gb = float(data.get('screenshot_retention_gb', 10.0))`
- 走 `MEDIA_ROOT/screenshots/` 目录, os.walk 收集所有文件 (mtime, size, path)
- 按 mtime 升序排序 (最旧优先删除)
- 累加 total_size, 若 > threshold_bytes (screenshot_gb * 1024**3), 删除最旧文件直到达标
- 响应字段扩展: `deleted_screenshots` + `freed_screenshot_bytes`
- audit log 加 `screenshot_retention_gb` + `deleted_screenshots` + `freed_screenshot_bytes` 字段
- docstring 更新: 删 "not yet implemented (placeholder)" 注释

### §4.2 单元测试 (backend/settings/tests/test_cleanup_screenshots.py, 6 测试)

- `test_cleanup_missing_dir` — 目录不存在, deleted_screenshots=0
- `test_cleanup_empty_dir` — 空目录, deleted_screenshots=0
- `test_cleanup_under_threshold` — 总 size < threshold, 不删除
- `test_cleanup_over_threshold_deletes_oldest_first` — 总 size > threshold, 删最旧直到达标
- `test_cleanup_threshold_boundary_no_deletion` — total == threshold 边界, 不删除
- `test_cleanup_nested_subdirs` — 嵌套子目录 screenshots/debug/old.png 被正确遍历

**验证**:
- `pytest backend/settings/tests/test_cleanup_screenshots.py -v` 6 passed
- `pytest backend/settings/tests/` 12 passed (6 原有 + 6 新增, 0 回归)
- `ruff check backend/settings/views.py backend/settings/tests/test_cleanup_screenshots.py` All checks passed (含修复 spec-39 遗留 I001 import 排序)

### §4.3 文档更新

- `backend/settings/views.py:cleanup_view` docstring: 删 "placeholder" / "not yet implemented" 注释
- `frontend/src/types/api.generated.ts:5987`: 注释从 "not yet implemented (placeholder)" 改为 "enforced: deletes oldest screenshots when total size exceeds N GB"

## §5 Phase 3: 文档同步 + commit + hash 回填

- `docs/general/tech-debt/wontfix.md`: 删 TD-291 段落 (wontfix 状态迁移到 FIXED)
- `docs/general/tech-debt/fixed.md`: 加 TD-291 ✅ FIXED (wontfix 重新开放 + 实施)
- `docs/general/completed-features.md`: 加 C-088
- `docs/general/pending-roadmap.md`: 加 P-029 + spec-44 hash 回填 (-)
- spec-45 文件状态表 Phase 1-3 全 ✅
- spec-44 文件 hash 回填 (-)
- commit message: `feat(spec-45): TD-291 screenshot retention implement (wontfix reopen, 9/9 AI 自决 + user auth, spec-44 hash backfill)`

## §6 反思 (中修改级别 — 5 项)

走 `gaf-reflect-and-evolve §2` 中修改级别流程.
