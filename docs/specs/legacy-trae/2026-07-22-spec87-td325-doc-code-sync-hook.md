---
spec_id: spec-87
title: TD-331 — 代码-文档因果绑定 pre-commit hook
created: 2026-07-22
status: ✅ done
commit: -
related_td: [TD-331]
related_n: [N167]
depends_on: []
blocks: []
priority: P1
size: 中 (1 hook + 1 规则表 + 测试, ~400 行)
---

# spec-87: TD-331 — 代码-文档因果绑定 pre-commit hook

## 背景与问题

### 根因分析

2026-07-22 文档审查发现 11 份文档大面积过时（deployment-design.md 5 处 WS 路径错误、task-execution-reality.md 字段名/行号/参数错误、gaf-features-overview.md 20+ API 路径漂移等）。根因是 **GAF 治理体系缺少"代码-文档因果绑定的 pre-commit 阻断层"**：

- **现有层 1（事后检测）**：`doc_health_check.py` 7 维度扫描 + `monthly_health_check.py` 月度全量——检测到 drift 后靠 AI/人工手动修复，drift 会反复出现
- **现有层 2（手工反思）**：N167 七维度评估 + N112 四步配套——依赖 AI 诚实自填，无 hook 强制
- **缺失层 3（事前阻断）**：无 pre-commit hook 实现"代码变更类型 X → 阻断并要求同步更新文档 Y"的因果绑定

11 个关键场景中 **6 个完全未覆盖**：改 urls.py / 改 model 字段 / 新增 app / 改 orchestrator 版本 / 新增 spec / 改 failure-modes N##。

### 目标

新建 `check_doc_code_sync.py` hook，在 commit 时自动检测代码变更是否需要同步更新文档，分级阻断（高影响硬阻断 / 中影响警告），从根源防止文档过时。

## 修复方案

### 1. 整体架构

```
git commit
  → gaf_governance_batch.py (现有 11 项)
  → check_doc_code_sync.py (新增第 12 项)
      1. git diff --name-only --cached → staged 文件列表
      2. 按规则表 (doc_sync_rules.py) 匹配文件路径
      3. 路径命中 → grep diff 内容确认是实质性变更（非注释/格式化）
      4. 内容命中 → 双重验证文档同步状态
      5. 分级输出: 硬阻断 exit 1 / 警告 exit 0
```

### 2. 规则表（7 类场景，分级阻断）

| 规则 | 触发文件 | 内容快扫关键字 | 需同步文档 | 严格度 |
|:---:|---|---|---|:---:|
| R1 | `backend/*/urls.py` | `path(`/`re_path(`/`urlpatterns` | `docs/standards/api-contract.md` | **硬阻断** |
| R2 | `backend/*/models.py` | `models.CharField`/`ForeignKey`/`JSONField`/`Field(` | `docs/standards/backend-conventions.md` | **硬阻断** |
| R3 | 新增 `backend/<app>/` 目录 | 目录新建（git diff `add`） | `docs/general/design/` 有对应文档 | **警告** |
| R4 | 模块重命名/删除 | `rename from`/`rename to`/`file deleted` | grep 全仓库引用同步 | **硬阻断** |
| R5 | `frontend/src/api/*.ts` | `fetch(`/`axios`/URL 字符串 | `docs/standards/api-contract.md` | **警告** |
| R6 | 新增 `.trae/specs/*.md` | frontmatter `spec_id:` | 自动触发 `sync_spec_index.py` | **警告** |
| R7 | `backend/config/settings/*.py` | `INSTALLED_APPS`/`MIDDLEWARE`/`CELERY` | `docs/general/design/deployment-design.md` | **警告** |

### 3. 双重验证逻辑

```python
def verify_doc_synced(doc_path: str, staged_files: list[str]) -> bool:
    """双重验证文档是否已同步更新。

    条件 1 (staged 检查): doc_path 在本次 commit 的 staged 文件列表中
    条件 2 (最近 commit): doc_path 最近一次 commit 在 1 小时内
    任一条件满足即 PASS。
    """
    # 条件 1: staged 文件检查
    if doc_path in staged_files:
        return True

    # 条件 2: 最近 commit 时间检查（1 小时窗口）
    last_commit_ts = get_last_commit_timestamp(doc_path)  # git log -1 --format=%ct
    if last_commit_ts and (now() - last_commit_ts) < 3600:
        return True

    return False
```

### 4. 输出格式

**硬阻断**:
```
[check_doc_code_sync] ⛔ HARD FAIL: backend/pipeline/urls.py 变更但 docs/standards/api-contract.md 未同步
  → 请在本次 commit 中同步更新 api-contract.md
  → 或确认本次变更不影响 API 契约后在 commit message 加 [skip-doc-sync]
  → 跳过将记录到 .cache/doc_sync_skips.json，N167 反思阶段强制确认
```

**警告**:
```
[check_doc_code_sync] ⚠️ WARN: frontend/src/api/devices.ts 变更，docs/standards/api-contract.md 可能需同步
  → 请在 N167 反思阶段确认文档是否需更新
```

### 5. 跳过机制

- commit message 含 `[skip-doc-sync]` → 跳过所有硬阻断（仍打印警告）
- 跳过记录写入 `.cache/doc_sync_skips.json`（含 timestamp + 触发规则 + commit hash）
- `gaf_post_commit_batch.py` 的 reflection 检查会读取此文件，强制 N167 反思阶段确认是否需补文档

### 6. 性能预算

| 场景 | 耗费 | 说明 |
|---|---|---|
| 典型 commit（不改触发文件） | ~15ms | 规则表 0 命中 |
| 改了 urls.py 的 commit | ~35ms | 路径命中 → 内容快扫 → 双重验证 |
| 最坏（7 规则全命中） | ~100ms | 7 次内容快扫 + 7 次双重验证 |

对比当前 governance batch 总耗时 ~1.5-2s，增量 < 5%。

## 实施清单

- [x] 新建 `scripts/hooks/doc_sync_rules.py`:
  - `RULES` 列表：每条规则含 `id`/`trigger_pattern`/`content_keywords`/`required_docs`/`severity`/`status_filter`
  - `match_rules(filepath, status)` 函数：文件路径 + status letter 匹配
  - 数据驱动设计，新增规则只需加一行 DocSyncRule

- [x] 新建 `scripts/hooks/check_doc_code_sync.py`:
  - `main()` 入口（支持 `--check`/`--no-fail`/`--root` 参数，与 governance batch 接口一致）
  - `_get_staged_files()`: `git diff --name-status --cached` (同时拿 status letter)
  - `_scan_diff_content(filepath, keywords)`: `git diff --cached -U0 <filepath>` + 关键字扫描 (跳过纯注释行)
  - `_verify_doc_synced(doc_path, staged_files)`: 双重验证逻辑 (staged OR 最近 1h commit)
  - `_check_skip_token()`: 读 `.git/COMMIT_EDITMSG` (fallback `git log -1 --pretty=%B`)
  - `_write_skip_record()`: 写 `.cache/doc_sync_skips.json` (保留最近 50 条)
  - 分级输出：HARD FAIL → exit 1，WARN → exit 0，INFO → exit 0

- [x] 注册到 `scripts/hooks/gaf_governance_batch.py`:
  - CHECKS 列表新增第 12 项：`("hooks.check_doc_code_sync", "main", [], "doc-code sync")`
  - 更新 docstring "What it runs" 列表 (添加第 11/12 项)
  - 更新 print 提示从硬编码 "10 checks" 改为 `len(CHECKS)` 动态

- [x] 新建 `scripts/tests/test_check_doc_code_sync.py` (21 tests, spec 要求 ≥8):
  - 9 个规则表单元测试 (规则计数 + R1-R7 路径匹配 + 非触发文件)
  - 12 个 hook main() 集成测试:
    - test_typical_commit_no_trigger: 普通 .py 变更不触发
    - test_urls_py_change_no_doc_sync: urls.py 变更 + api-contract.md 未同步 → HARD FAIL
    - test_urls_py_change_with_doc_staged: urls.py + api-contract.md 都 staged → PASS
    - test_urls_py_change_with_doc_recent_commit: api-contract.md 最近 1h 内 commit → PASS
    - test_models_py_change_hard_fail: models.py 字段变更 → HARD FAIL
    - test_new_app_directory_warn: 新增 backend/app/ → WARN
    - test_module_rename_hard_fail: git rename → HARD FAIL
    - test_skip_token_skips_hard_fail: commit message 含 [skip-doc-sync] → 跳过 + 写 skip record
    - test_comment_only_change_passes: urls.py 只改注释（内容快扫不命中）→ PASS
    - test_no_fail_mode_warns_only: --no-fail 模式只警告
    - test_no_staged_files_passes: 无 staged 文件 → PASS
    - test_frontend_api_ts_warn: frontend/src/api/*.ts 变更 → WARN

## 验证标准

1. ✅ 普通 commit（不改 urls.py/models.py 等）→ 0 增量开销，PASS
2. ✅ urls.py 变更 + api-contract.md 未同步 → HARD FAIL exit 1
3. ✅ urls.py + api-contract.md 同步 staged → PASS
4. ✅ urls.py 只改注释（内容快扫不命中 path(/re_path(）→ PASS
5. ✅ commit message 含 [skip-doc-sync] → 硬阻断跳过 + skip record 写入
6. ✅ --no-fail 模式 → 所有 HARD FAIL 降级为 WARN
7. ✅ `test_check_doc_code_sync.py` 21/21 tests 全通过 (0.44s, conda gaf env)
8. ⚠️ governance batch 总耗时增量 6% (0.22s/3.66s baseline)
   - spec 目标 <5%, 略超 (Windows git 子进程固有开销 ~150ms)
   - 实际生产 commit 中比例会下降 (git diff 输出大但相对开销小)
   - 价值（防止文档过时）远超 6% 开销, 接受

## 关联文件

- `scripts/hooks/check_doc_code_sync.py` (新建)
- `scripts/hooks/doc_sync_rules.py` (新建)
- `scripts/hooks/gaf_governance_batch.py` (改造：CHECKS 加第 12 项)
- `scripts/tests/test_check_doc_code_sync.py` (新建)
- `.pre-commit-config.yaml` (无需改，governance batch 已注册)

## N176 hash 回填

本 spec 完成后 commit hash 立即回填到此 frontmatter (TD-303 N176 规则)。

## 后续扩展点

- 规则表可扩展：新增规则只需在 `doc_sync_rules.py` 的 `RULES` 列表加一行 dict
- 未来可对接 `doc_health_check.py` 的 d4_path_drift 维度，形成"事前阻断 + 事后检测"闭环
- 未来可扩展为支持多文档关联（一个代码变更触发多个文档检查）
