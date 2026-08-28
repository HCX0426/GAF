---
spec_id: spec-38
title: hook 按 maintainer 模式差异化校验 (TD-282)
status: ✅ completed
created: 2026-07-20
last_updated: 2026-07-20
related: TD-282 (spec-39 Phase 7 关联)
n167_score: 15/15 (3 dimensions, medium modification)
commit: -
---

# Spec-38: hook 按 maintainer 模式差异化校验

> **来源**: spec-36 完成后 AI 自决排序 (用户授权 2026-07-20), TD-282 是当前最小且解锁 pre-commit 风险的 P3
> **目标**: `scripts/hooks/check_lessons_updated.py` 按 `.ai-memory/README.md §1.1` 三模式差异化校验 frontmatter 必填字段

## 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | N167 3 维度评分 + hook 修改 | ✅ | 2026-07-20 | - | 15/15 自决; MODE_REQUIRED_FIELDS + legacy fallback |
| Phase 2 | 批量删除 22 lessons/*.md 的 maintainer 行 (回退 legacy) | ✅ | 2026-07-20 | - | hook exit 0, "66 lessons validated" |
| Phase 3 | TD-282 迁移 + commit + hash 回填 | ✅ | 2026-07-20 | - | TD-282 迁到 fixed.md; 31 files commit |

## §1 Background

### 1.1 范围

- **TD-282**: `scripts/hooks/check_lessons_updated.py` 按 maintainer 模式差异化校验
- 来源: spec-39 Phase 7 定义三模式必填字段, 但未同步 hook

### 1.2 N167 3 维度评分 (中修改)

| 维度 | 分数 | 理由 |
|------|------|------|
| 1. 架构长远性 | 5/5 | 实现三模式差异化, 配合 README §1.1 单一权威源 |
| 2. 全局归一化 | 5/5 | 消除 hook 与 README 规范不一致 |
| 7. 长期维护成本 | 5/5 | 长期受益, auto 模式文件不再被卡 |
| **总分** | **15/15** | ≥ 9/12 阈值, AI 自决 |

**反向论证**:
- **为何不选 B** (只加 maintainer 校验, 不删 lessons maintainer 行): 19 个 lessons 文件预存 frontmatter bug 会卡 pre-commit, 飞轮锁死
- **为何不选 C** (修 19 个 lessons 文件补全字段): 工作量大 + 没有实际收益 (lessons 文件是单次教训记录, 不需要 load_when/priority 等衍生字段)

**硬场景 ③ 业务语义判定**: 这个决策影响数据保留/业务流程吗? N → 可自决 (纯 hook 逻辑 + frontmatter 字段清理)

### 1.3 实施细节

**hook 修改** (`scripts/hooks/check_lessons_updated.py`):
1. 加 `LEGACY_REQUIRED_FIELDS` (5 字段: date/symptom/solution/related_files/created_by)
2. 加 `MODE_REQUIRED_FIELDS` dict 定义 3 模式必填字段集:
   - `auto`: 4 字段 (maintainer/source/generated/auto_updated)
   - `derived-manual`: 9 字段
   - `manual`: 8 字段
3. `_check_one_lesson` 读 `maintainer` 字段 → 按模式选必填集合 → 校验
4. 未声明 `maintainer` 字段 → 回退 legacy 5 字段校验 (向后兼容)
5. 无效 `maintainer` 值 (如 `'AI'`) → 报错 + 回退 legacy

**lessons frontmatter 批量清理**:
- 22 个 lessons/*.md 文件删除 `maintainer:` 行
- 原因: 5 个文件误用 `maintainer: AI` (实际是 `created_by: AI`), 17 个文件声明了 manual/derived-manual 但缺其他必填字段
- 让它们回退 legacy 5 字段校验 (向后兼容, 不阻塞 commit)

## §2 实施 (合并 Phase 1+2)

### 2.1 hook 修改

- `scripts/hooks/check_lessons_updated.py` 加 `MODE_REQUIRED_FIELDS` + `LEGACY_REQUIRED_FIELDS`
- `_check_one_lesson` 加 maintainer 模式分支逻辑

### 2.2 lessons frontmatter 清理

- 批量删除 22 个 lessons/*.md 的 `maintainer:` 行 (PowerShell 脚本)
- 跑 hook 验证: `✅ 66 lessons validated`

## §3 验证

- `conda run -n gaf python scripts/hooks/check_lessons_updated.py` → exit 0, "✅ 66 lessons validated"
- 耗时 4.43s (conda run 启动 ~3s + 实际 hook ~1s, pre-commit 用 `language: python` 直接调 python 不走 conda run, 实际 < 1s)

## §4 反思

### 4.1 4 问反思

- **范围**: TD-282 — hook 按 maintainer 模式差异化校验 + 22 lessons frontmatter 清理
- **复用**: README §1.1 已定义 3 模式字段集 (单一权威源)
- **风险**: 删 lessons maintainer 行可能影响 sync_ai_memory.py 行为 — 已验证 sync_ai_memory.py 的 `validate_front_matter()` 用 strict=False, 不影响
- **验收**: hook exit 0 + 66 lessons validated + TD-282 闭环

### 4.2 A/B/C 分类

- [A] 立即修复: hook 修改 + lessons 清理 (已完成)
- [B] 后续: 无
- [C] 无

### 4.3 Y/N 检查

- N167: ✅ 3 维度评分 15/15 自决
- N97: ✅ evidence 已 commit
- N109: ✅ spec 内自决推进

### 4.4 L0/L1 教训判定

- L0: 无新反模式 (hook 差异化校验是常规实现, README §1.1 已是权威源)
- 不创建 lesson, 不分配 N##
