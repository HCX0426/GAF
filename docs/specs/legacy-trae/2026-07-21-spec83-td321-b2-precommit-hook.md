---
spec_id: spec-83
title: TD-321 — B2 大修改 pre-commit hook 强制
created: 2026-07-21
status: ✅ done
commit: -
related_td: [TD-321]
related_n: [N151]
depends_on: []
blocks: []
priority: P1
size: 中 (pre-commit hook + 8 tests, ~350 行)
---

# spec-83: TD-321 — B2 大修改 pre-commit hook 强制

## 背景与问题

`scripts/check_big_change.py` 是 B2 治本机制 (N151 触发条件客观化)，量化 4 维度判定大修改：
1. diff 行数 > 500
2. 跨 backend app ≥ 2
3. DB 迁移文件
4. API 契约文件

但无强制调用，AI 可跳过 B2 直接执行大修改 commit，N151 5 步流程退化为虚设。

## 修复方案

加 pre-commit hook `scripts/hooks/check_big_change_hook.py`，在 commit 时强制：
1. 跑 check_big_change --staged 检查 staged 改动
2. 如果 is_big=true，要求 `.cache/b2_acknowledged.json` 存在且有效（timestamp < 30 min + is_big=true）
3. 否则 commit 失败，提示 "大修改需先跑 N151 5 步 + B2 acknowledge"

AI 工作流：
- AI 跑 N151 5 步流程 → 跑 `python scripts/check_big_change.py --staged --acknowledge` → commit

## 实施清单

- [x] 改造 `scripts/check_big_change.py`:
  - 新增 `--staged` 模式（检查 staged 改动而非 HEAD vs HEAD~1）
  - 新增 `--acknowledge` 模式（写 `.cache/b2_acknowledged.json` 含 timestamp + is_big + dimensions）
  - 抽取 `_evaluate_big_change()` 共享逻辑（HEAD 模式与 staged 模式复用）
  - 新增 `read_b2_evidence()` / `is_b2_evidence_valid()` 辅助函数
  - `B2_EVIDENCE_TTL_SECONDS = 30 * 60` (30 分钟有效期)
- [x] 新建 `scripts/hooks/check_big_change_hook.py`:
  - 调用 `check_big_change_staged()` 评估 staged 改动
  - 若 is_big=true → 读 evidence + 验证 TTL + is_big 一致
  - 失败时给出 4 步修复提示 + 紧急 bypass 说明 (--no-verify)
- [x] 注册到 `.pre-commit-config.yaml`（pre-commit stage）
- [x] 新建 `scripts/tests/test_check_big_change_hook.py` (8 tests: small/big-no-evidence/big-fresh/big-expired/no-fail/mismatch/ttl-constant/write-evidence)

## 验证标准

1. 小修改（< 500 行 + 单 app + 无 migration + 无 API contract）commit 通过
2. 大修改 commit 时若无 `.cache/b2_acknowledged.json` → commit 失败
3. 大修改 commit 时若有 evidence 但 timestamp > 30 min → commit 失败
4. 大修改 commit 时若有 evidence 且 fresh + is_big=true → commit 通过
5. `--no-fail` 模式仅警告不阻塞
6. `test_check_big_change_hook.py` ≥ 3 tests 全通过 (实际 8/8 passed in 0.16s, conda gaf env)

## 关联文件

- `scripts/check_big_change.py` (改造)
- `scripts/hooks/check_big_change_hook.py` (新建)
- `scripts/tests/test_check_big_change_hook.py` (新建)
- `.pre-commit-config.yaml` (注册 hook)

## N176 hash 回填

本 spec 完成后 commit hash 立即回填到此 frontmatter (TD-303 N176 规则)。
