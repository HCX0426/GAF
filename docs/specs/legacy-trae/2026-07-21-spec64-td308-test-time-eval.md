---
spec_id: spec-64
title: TD-308 backend 全套测试 526s 逼近 N177 <600s 阈值 — 评估 (A pytest-xdist vs B 拆分套件)
status: ✅ done
created: 2026-07-21
completed: 2026-07-21
owner: AI
task_type: documentation
td_refs: [TD-308]
---

# spec-64: TD-308 backend 测试时间评估

## 背景

backend 全套 pytest 时间趋势: 361s (C-100) → 465s (spec-56 C-092) → 526s (spec-57 C-093), +45.7%。
距 N177 大修改基线 <600s 仅余 74s 余量。N177 "循环模式每 2 spec 必跑全套回归" 即将不可行。

## 现状

- pytest 配置: pyproject.toml [tool.pytest.ini_options], 无并行化
- dev deps: pytest 8.x / pytest-django 4.8 / pytest-asyncio 0.23, **无 pytest-xdist**
- 测试文件: backend 108 个 test_*.py
- pre-commit hook: 无 pytest hook (pytest 仅 N177 全套回归时手动跑)

## 方案评估

### 方案 A: pytest-xdist 并行化

- **改动**: 加 `pytest-xdist` 到 dev deps + 改 N177 全套回归命令 `pytest backend/` → `pytest backend/ -n auto`
- **预期效果**: 526s → 150-200s (3-4x 加速, CPU 核数依赖)
- **优点**:
  - 改动小 (3-5 行)
  - 见效快 (安装即用)
  - 不改测试代码
- **缺点**:
  - 并行可能引入 flaky (DB transaction 隔离 / 共享资源竞争 / 文件锁)
  - 依赖 CPU 核数 (4 核 → 4x, 8 核 → 8x)
  - 某些测试可能无法并行 (端口冲突 / 全局状态)
  - 测试输出顺序乱 (调试困难)

### 方案 B: 拆分套件 fast/slow 分层

- **改动**: 加 `@pytest.mark.slow` 标记 slow 测试 + 改 N177 大修改策略为"跑 fast 套件 + 涉及模块 slow" + pyproject.toml markers 配置
- **预期效果**: fast 套件 < 60s 跑每次, slow 全套跑循环模式
- **优点**:
  - 长期可扩展
  - 标记清晰, 可细粒度控制
  - 无并行 flaky 风险
- **缺点**:
  - 改动大 (需要标记 108 个测试文件中的 slow 测试)
  - 短期不见效 (需先识别 slow 测试)
  - 维护成本 (新测试需标记)

### 方案 A+B 组合 (推荐)

- **Phase 1**: 先实施 A (pytest-xdist), 立即生效 3-4x 加速
- **Phase 2**: 后续实施 B (slow 标记), 让 slow 测试单独跑
- **优点**: 短期见效 + 长期治理

## 七维度评分 (N167)

| 维度 | A pytest-xdist | B 拆分套件 | A+B 组合 |
|------|----------------|------------|----------|
| 1 业务正确性 | 5/5 | 5/5 | 5/5 |
| 2 用户体验 (开发提速) | 5/5 (3-4x) | 3/5 (有限) | 5/5 |
| 3 性能 | 5/5 (3-4x) | 3/5 (分级) | 5/5 |
| 4 安全 | 5/5 | 5/5 | 5/5 |
| 5 可维护性 | 3/5 (flaky 风险) | 4/5 (标记清晰) | 4/5 |
| 6 可扩展性 | 4/5 (CPU 限制) | 5/5 (无限制) | 5/5 |
| 7 长期收益 | 3/5 (只解决时间) | 5/5 (根本治理) | 5/5 |
| **总分** | **30/35** | **30/35** | **34/35** |

A 与 B 平局 (30/30), A+B 组合最优 (34/35, 领先 4 分)。

按 N167 自决规则: 总分 ≥ 19 且领先第二名 ≥ 5 分 → AI 自决; A+B 领先 4 分, 不满足 ≥5 分阈值 → AskUserQuestion。

## 评估结论

- A 与 B 单独方案平局 (30/30)
- A+B 组合最优 (34/35), 但领先 4 分未达 N167 ≥5 分阈值
- 推荐 A+B 组合 (先 A 短期见效, 后 B 长期治理)
- 实施由 spec-65 (A) + spec-66 (B) 完成

## Phase 1: 评估

- [x] 1.1 跑 sync_ai_memory.py --query "pytest parallel xdist test suite slow" → 2 命中 (failure-modes N160/N177)
- [x] 1.2 评估 A/B/A+B 方案利弊
- [x] 1.3 七维度评分 → A=30, B=30, A+B=34
- [x] 1.4 AskUserQuestion 让用户选方案 → 用户选 **A+B 组合 (推荐)**

## Phase 2: 推荐方案实施 (待用户决策)

- [x] 2.1 用户决策: A+B 组合 (先 spec-65 实施 A pytest-xdist, 后 spec-66 实施 B slow 标记)

## 反思 (评估型 spec, 跑 ① 4 问 + ④ 状态标记)

### ① 4 问反思

1. **解决什么问题**: TD-308 评估方案, 不实施代码
2. **根因**: 测试时间 526s 逼近 N177 <600s 阈值, 需要评估修复方案
3. **方案选择**: A pytest-xdist (30/35) vs B 拆分套件 (30/35) vs A+B 组合 (34/35, 推荐) → 用户选 A+B
4. **验证**: 七维度评分完成, 用户决策完成

### ④ 状态标记

- spec-64: 🔄 in_progress → ✅ done (评估完成, 不修代码)
- TD-308: 🔧 待修 → 🚧 评估完成, A+B 组合选定, 待 spec-65/66 实施
- 后续 spec-65 实施 A (pytest-xdist)
- 后续 spec-66 实施 B (slow 标记)
