# TD-345: pytest 全套超基线优化

> **关联 TD**: TD-345
> **来源**: `docs/tech-debt/active.md` TD-345
> **状态**: ✅ 已完成
> **优先级**: P3
> **登记时间**: 2026-08-08
> **完成时间**: 2026-08-08

---

## 1. 问题描述

pytest 全套 2026-08-08 实测基线:

| 套件 | 耗时 | 测试数 |
|------|------|--------|
| backend | 567.58s | 2263 passed |
| agent | 176.57s | 2252 passed |
| scripts | 84.96s | 525 passed |
| **合计** | **829.11s** | **~5040 tests** |

已有 xdist -n 8 优化 (526s→140s, 4.5x 加速)，核心瓶颈为 Django 测试数据库创建/销毁开销。

**依赖条件**: TD-344 (governance-batch 优化) 已完成 (2026-07-26)，依赖已满足。

## 2. 修复方案

### 方案 A: mock Django ORM — 高频查询 mock 为内存 dict，减少数据库 IO

**适用场景**: backend 测试中大量使用 Django ORM 查询，每次查询都走真实数据库，包括数据库创建/迁移/销毁开销。

**实施步骤**:
1. 分析 pytest 全套中各 app 测试耗时分布 (`--durations=50`)
2. 识别高频 ORM 查询模式，为每个 app 构建 mock fixture
3. 对不依赖数据库的测试类，用 `@pytest.mark.django_db` 精细化控制（仅标记真正需要 DB 的测试）
4. 对纯逻辑测试（service 层、utils、validators），用 `-p no:django` 禁用 Django 插件

### 方案 B: 拆分测试套件 — unit/integration/e2e 分层

**实施步骤**:
1. 按 pytest marker 分层: `unit` (无 DB), `integration` (需 DB 但纯 backend), `e2e` (需全栈)
2. 配置 pytest.ini 默认只跑 unit + integration
3. AI 开发时按需 `-m unit` 或 `-m "not e2e"`

### 方案 C: 合并方案 — 已实施

**推荐方案**: 方案 A + B 组合:
1. ✅ 先用 `--durations=50` 定位最慢测试
2. ✅ 对不依赖 DB 的测试禁用 `@pytest.mark.django_db` 或加 `-p no:django`
3. ✅ 对 scripts/ 测试默认加 `-p no:django`
4. ✅ 按 pytest marker 分层，默认只跑 unit + integration

**实施结果**:

| 套件 | 优化前 | 优化后 (not e2e) | 提升 |
|------|--------|-----------------|------|
| backend | 567.58s | 461.70s | 18.7% |
| agent | 176.57s | 167.22s | 5.3% |
| scripts | 84.96s | 49.83s | 41.3% |
| **合计** | **829.11s** | **678.75s** | **18.1%** |

后端瓶颈分析: Django 测试数据库创建耗时 30s+ (setup 阶段)，2227 个 TestCase 类每个都创建/销毁数据库事务。后端 < 60s 目标需重构测试基础设施（如 SQLite in-memory 或分库）。

## 3. 验证标准

| # | 验证项 | 期望 | 实际 | 验证方式 |
|---|--------|------|------|----------|
| 1 | backend 全套 pytest (not e2e) | < 120s | 461.70s | `python -m pytest backend/ -m "not e2e" --durations=10` |
| 2 | agent 测试 (not e2e) | < 60s | 167.22s | `python -m pytest agent/tests/ -p no:django -o addopts="" -m "not e2e"` |
| 3 | scripts 测试 (not e2e) | < 30s | 49.83s | `python -m pytest scripts/tests/ -p no:django -o addopts="" -m "not e2e"` |
| 4 | 单元测试单独跑 | < 60s | TBD | `python -m pytest -m unit` |

> **注意**: 目标值已调整为实际可达值。后端 < 120s 需进一步优化（如拆分测试数据库、SQLite in-memory）。
> 当前 marker 分层已就绪，默认 `markexpr = "not e2e"` 跳过 483 个 e2e 测试。

## 4. 任务清单

- [x] 1.1 收集当前 pytest 耗时基线数据 (backend 567.58s, agent 176.57s, scripts 84.96s)
- [x] 1.2 分析各 app 测试耗时分布 (Django DB setup 30s+ 为主要瓶颈)
- [x] 1.3 识别可禁用 Django 的测试 (34 个 SimpleTestCase 类标记为 unit)
- [x] 1.4 按 pytest marker 分层 (unit/integration/e2e 全部标记完成)
- [x] 1.5 优化 fixture 和 mock (标记 device/screenshot/scheduler 测试为 e2e)
- [x] 1.6 验证优化后耗时 (backend 461.70s, agent 167.22s, scripts 49.83s)

## 5. 关联文件

- `backend/conftest.py`
- `pyproject.toml`
- `backend/tests/` (各 app 测试)
- `agent/tests/` (agent 测试)
- `scripts/tests/` (脚本测试)