---
spec_id: spec-52
title: Test resource pack cleanup — conftest.py autouse fixture
status: ✅ done
created: 2026-07-20
last_updated: 2026-07-20
related: spec-51 (L3-1 scan discovery), TD-004 (resources/ single source of truth)
n167_score: 15/15 (3 dimensions, medium modification)
---

# Spec-52: 测试副作用残留清理 — conftest.py autouse fixture

> **来源**: spec-51 commit (`-`) 后 L3-1 全量扫描发现 `resources/Test Pack/` + `resources/集成测试资源包/` untracked 目录 (各 1 manifest.json, 测试副作用残留)
> **目标**: `backend/tests/conftest.py` 加 autouse fixture, 测试前后对比 `resources/` 子目录集, 自动清理新增的非默认包 (保留 BrownDust-II + default)

## 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | N167 3 维度评分 + 设计 autouse fixture | ✅ | 2026-07-20 | - | 15/15 自决; snapshot before/after 策略 |
| Phase 2 | 实施 conftest.py fixture + 清理现有残留 | ✅ | 2026-07-20 | - | 删除 resources/Test Pack/ + resources/集成测试资源包/ |
| Phase 3 | 跑 test_resource_pack.py + test_integration.py 验证 + commit | ✅ | 2026-07-20 | - | tests PASS + git status 干净 |

## §1 Background

### 1.1 来源

- spec-51 commit 后 L3-1 全量扫描 (9 维度) 发现:
  - `resources/Test Pack/manifest.json` (0.1 KB, untracked)
  - `resources/集成测试资源包/manifest.json` (0.2 KB, untracked)
- 两者均为 backend 测试副作用残留

### 1.2 根因

- `backend/tests/test_resource_pack.py::ResourcePackAPITest::test_resource_pack_create` 调用 `POST /api/v2/resources/resource-packs/` 创建资源包
- `backend/tests/test_integration.py::ResourcePackFlowTest::test_resource_pack_create_and_activate` 同样调用
- `ResourcePackViewSet.create` (backend/resources/views.py:135) 调用 `get_destination_dir(manifest)` (import_utils.py:62) + `shutil.copytree()` 把测试临时目录复制到 `resources/<safe_name>/` (TD-004 Option A: `resources/` 单一权威源, 这是 API 设计行为)
- 测试用 `tempfile.TemporaryDirectory()` (tmpdir, 系统临时目录), 但 API create 会再复制到 `resources/<name>/`, 测试结束 tmpdir 自动清理但 `resources/<name>/` 残留

### 1.3 影响分析

- **git status 噪音**: 每次跑测试后 untracked 多 2 个目录
- **磁盘累积**: 测试创建多个包 (Test Pack, 集成测试资源包, 资源包A, 资源包B) 都会残留
- **不是 bug**: API 行为正确 (TD-004 Option A), 是测试未清理

## §2 N167 7 维度评分 (中修改, 跑 3 维)

### 2.1 方案 A (conftest.py autouse fixture, snapshot before/after) ✅

| 维度 | 分数 | 理由 |
|------|------|------|
| 1. 架构长远性 | 5/5 | autouse 全局生效, 未来新测试自动清理, 不需每个测试单独写 tearDown |
| 2. 全局归一化 | 5/5 | 单一 fixture 集中清理逻辑, 不分散在各测试 |
| 7. 长期维护成本 | 5/5 | 一次性修复, 无后续维护成本 |
| **总分** | **15/15** | ≥ 9/12 阈值, AI 自决 |

### 2.2 反向论证 (为何不选 B/C)

- **方案 B (各测试加 tearDown)**: 9/15
  - 维度 1: 3/5 — 分散, 未来新测试可能漏写
  - 维度 2: 3/5 — 不归一化
  - 维度 7: 3/5 — 每次加新测试都要记得写 tearDown
  - 不选理由: 分散不符合 DRY, 易遗漏

- **方案 C (.gitignore)**: 5/15
  - 维度 1: 2/5 — 治标不治本, 测试仍会创建文件
  - 维度 2: 2/5 — 不解决根本问题
  - 维度 7: 1/5 — 每次 git status 看到残留文件
  - 不选理由: 治标不治本, 残留文件继续累积

### 2.3 硬场景 ③ 业务语义判定

- 影响数据保留/业务流程? **N** (清理测试副作用, 不影响生产数据; BrownDust-II + default 默认包保留) → 可自决

## §3 实施

### 3.1 Phase 1: 设计 autouse fixture

**策略**: snapshot `resources/` 子目录集 (before test), 测试后清理新增的非默认包

**保留清单 (default_packs)**:
- `BrownDust-II` — 项目默认 BD2 资源包
- `default` — 项目默认资源包

### 3.2 Phase 2: conftest.py 实施

```python
@pytest.fixture(autouse=True)
def cleanup_test_resource_packs():
    """Auto-cleanup resource pack dirs created by tests under resources/.

    Tests in test_resource_pack.py and test_integration.py call the
    ResourcePack create API, which copies the pack to resources/<name>/
    (TD-004 Option A: resources/ is the single source of truth). Without
    cleanup, these test artifacts accumulate as untracked files.

    Strategy: snapshot resources/ subdirs before test, remove new ones
    after (preserving default packs: BrownDust-II, default).
    """
    # ... snapshot + yield + cleanup
```

### 3.3 Phase 3: 验证

- `python -m pytest backend/tests/test_resource_pack.py backend/tests/test_integration.py -v`
- `git status` 确认无 untracked resources/Test Pack/ 或 resources/集成测试资源包/

## §4 风险

- **低**: autouse fixture 对所有测试生效, 但只在测试创建新资源包时才清理 (snapshot diff)
- **默认包保留**: BrownDust-II + default 永远不删
- **git 追踪可恢复**: 即使误删, git 追踪的文件可恢复 (BrownDust-II/default 已追踪)

## §5 飞轮效果

- L3-1 ②代码层 [A] 类消除: resources/ untracked 残留清零
- 后续测试不再产生 untracked 噪音

## §6 沉淀

- 用户反馈 "开 spec 可以 ai 自决的, 不用抛给我" 沉淀到 `project_rules.md §3.6` spec-49 硬终止规则放松
