---
maintainer: manual
source: GAF/.ai-memory/ops/bypass-patterns.md
load_when:
- 遇到 lint 警告但必须继续
- hook 失败但确认是 hook bug
- 需要临时绕过同步工具
- 反思 "为什么这样写"
priority: high
symptom:
- kb:bypass-patterns
- lint-bypass
- hook-bypass
- skip-sync
- workaround
solution: 5 类绕过模式 (lint/hook/sync/类型/版本) + 9 项已记录绕过 + 必标 "BYPASS:" 注释 + 后续 Phase 跟踪
related_files:
- .ai-memory/summaries/architecture-mistakes.md
- .ai-memory/meta/failure-modes.md
- scripts/hooks/check_path_consistency.py
- scripts/bootstrap/sync_ai_memory.py
created_by: AI
last_updated: 2026-08-17 (s30 确认仍有效)
---
# GAF 绕过模式 (Bypass Patterns) 速查

> **用途**: 记录所有"明知有规则但主动绕过"的模式
> **原则**: 绕过不等于违规, 但必须显式标注 + 跟踪闭环
> **范围**: lint/hook/sync/类型/版本 5 类

---

## 1. 5 类绕过模式

### 1.1 [Lint Bypass] — 抑制 lint 警告

**触发**: 第三方代码风格冲突 / 类型 hack / 大段遗留代码
**标注**: `# noqa: E501,F401` / `// eslint-disable-next-line`
**风险**: 警告长期掩盖真问题

### 1.2 [Hook Bypass] — 跳过 pre-commit hook

**触发**: hook 误报 / hook bug / 紧急 hotfix
**标注**: `git commit --no-verify` (N105: 不用 gaf-commit.sh --no-verify, 透传 bug)
**风险**: 审计错觉 (N82), 必须 `git log --oneline -1` 二次验证

### 1.3 [Sync Bypass] — 跳过同步工具

**触发**: 紧急改动但 sync 跑通后会回滚
**标注**: `BYPASS-SYNC: <reason>` commit message 前缀
**风险**: 双根副本不一致, 必须手动同步

### 1.4 [Type Bypass] — 抑制类型检查

**触发**: 复杂泛型 / 第三方类型不准 / 临时 hack
**标注**: `# type: ignore[arg-type]`
**风险**: 实际类型 bug 被掩盖

### 1.5 [Version Bypass] — 锁定/跳过版本

**触发**: 升级后依赖冲突 / 锁版本防回归
**标注**: `==X.Y.Z` / `# TODO: upgrade in Q3`
**风险**: 错过安全更新

---

## 2. 已记录绕过清单 (9 项)

| # | 绕过类型 | 位置 | 绕过方式 | 原因 | 后续跟踪 | 记录位置 |
|:-:|:--------|------|---------|------|---------|---------|
| 1 | Hook | `gaf-commit.sh --no-verify` | 改用 `git commit --no-verify` | N105 透传 bug, --no-verify 不真跳过 | M1.A 修 gaf-commit.sh | [lessons/workflow_2026-06-15-n105-commit-bypass-rollback.md](../lessons/workflow_2026-06-15-n105-commit-bypass-rollback.md) |
| 2 | Hook | `gaf-sync` 误回滚 docs-index.md | 加 file lock + 重跑 sync_docs_index.py | N105 同一根因 | 已修 (v8.3.1 file lock) | [lessons/workflow_2026-06-15-n105-commit-bypass-rollback.md](../lessons/workflow_2026-06-15-n105-commit-bypass-rollback.md) |
| 3 | Sync | `sync_ai_memory.py` inline 路径 | 改用 `SYNC_STATE` 模块级常量 | N106 路径漂移 | M1.A 后续加 hook (N107 已实装) | [lessons/cross-layer-sync_2026-06-15-n106-sync-state-path.md](../lessons/cross-layer-sync_2026-06-15-n106-sync-state-path.md) |
| 4 | Hook | 5 lessons 的 `GAF/...` related_files 路径 | 改用 `../.trae/...` 或 `scripts/...` | hook 解析从 GAF 根, 不带 GAF/ 前缀 | 已修 (本批) | [lessons/cross-layer-sync_2026-06-15-n106-sync-state-path.md](../lessons/cross-layer-sync_2026-06-15-n106-sync-state-path.md) |
| 5 | Hook | `evidence/2026-06-16/_template_*.md` 副本 | 删除副本, 仅留空目录 | 模板有 TODO 占位符, hook 强校验 | 已修 (本批) | 本表 §3 |
| 6 | Hook | N82 `git log` 不再翻看 | 用 `git log --oneline -1` 强制 | 审计错觉 | 已修 (N108 流程加二次验证) | [summaries/architecture-mistakes.md #N82](../summaries/architecture-mistakes.md) |
| 7 | Lint | `evidence/templates/` 模板文件 `TODO` 占位符 | hook 仅对 today dir 强校验, 模板放 `templates/` (TD-158 改名后) | 模板就是要保留占位符 | 保留 | [scripts/hooks/check_3step_evidence.py](../../scripts/hooks/check_3step_evidence.py) |
| 8 | Type | `gaf-promote-lessons` 软检查不阻塞 | 仅 print 提议, 不 exit 1 | M0.M soft guidance | M0.L+ 评估是否升级 hard | [scripts/lessons/promote_lessons.py](../../scripts/lessons/promote_lessons.py) |
| 9 | Hook | `gaf-session-check` 过期阻断 | `python scripts/bootstrap/check_session_active.py --create` 续期 24h | session TTL 24h | 保留 (安全设计) | [scripts/bootstrap/check_session_active.py](../../scripts/bootstrap/check_session_active.py) |
| 10 | **Timeout** | `pytest`/`migrate`/`pip install` 跑超预期时间 0 输出 | StopCommand 杀 + 改 `blocking=false` 异步 + CheckCommandStatus 查 | N111 命令超时主动中止 | 保留 (AI 成熟标志) | [lessons/ai-autonomy_2026-06-16-n111-command-timeout.md](../lessons/ai-autonomy_2026-06-16-n111-command-timeout.md) |

---

## 3. 绕过必标 3 件套

任何绕过都必须有:

```python
# BYPASS-HOOK: <type> (N### / 或描述)
# 原因: <why bypass>
# 后续: <follow-up plan>
code_that_bypasses()
```

例:
```python
# BYPASS-LINT: E501 line too long
# 原因: 第三方 long string 必须保留
# 后续: v9.0 重构 (Q3)
LONG_STRING = "..."  # noqa: E501
```

```bash
# BYPASS-HOOK: gaf-3step-evidence (template placeholder)
# 原因: _template_*.md 是空模板, 必有 TODO 占位符
# 后续: 保留 (模板设计)
git commit --no-verify -m "..."
```

```python
# BYPASS-SYNC: auto-maintained file
# 原因: gaf-sync 误回滚, 已加 file lock
# 后续: v8.3.1 已修, 跑 sync_docs_index.py 重新生成
SYNC_STATE = AI_MEMORY / "sync-state.json"  # 不再 inline
```

---

## 4. 反思检查清单 (AI 每周跑一次)

- [ ] 本周有几次 hook bypass? (查 git log --no-verify 次数)
- [ ] bypass 后是否二次验证 (git log --oneline -1)?
- [ ] bypass 注释是否完整 (原因 + 后续)?
- [ ] 后续计划是否在本表 §2 跟踪?
- [ ] 累计 ≥ 3 次同类 bypass → 提议修工具 (N95 promote)

---

## 5. 禁止绕过 (硬规则)

❌ **NEVER** 用 `gaf-commit.sh --no-verify` 期望跳 hook (N105 透传 bug, 必须用 `git commit --no-verify`)
❌ **NEVER** bypass 不加 `BYPASS-XXX:` 注释 (违反 §3 3 件套)
❌ **NEVER** bypass 后忘跟踪后续 (违反 §4 反思清单)
❌ **NEVER** 用 `git push --force` 绕过 CI (destructive 永远禁止, project_rules.md §3.1)
❌ **NEVER** inline 拼 gitignored 路径 (N106, 违反 SYNC_STATE 常量)

---

## 6. 后续 Phase 跟踪 (M1.A 后续)

| 跟踪项 | 来源 | 优先级 | 状态 |
|--------|------|:----:|:----:|
| 修 gaf-commit.sh --no-verify 透传 | N105 | P2 | ❌ 待修 |
| gaf-sync 误改 auto-maintained 文件 | N105 | P2 | ✅ v8.3.1 file lock 已修 |
| sync_ai_memory 改用 SYNC_STATE 常量 | N106 | P1 | ✅ M1.A.1.j 已实装 |
| 5 lessons related_files 路径修 | 本批 | P1 | ✅ 已修 |
| evidence/2026-06-16/ 模板副本 | 本批 | P1 | ✅ 已删 |
| N82 审计错觉 | architecture-mistakes #N82 | P2 | ✅ N108 流程加二次验证 |

## 每周复盘 @ 2026-06-17 13:56 UTC

- **统计窗口**: 2026-05-18 13:56 UTC ~ 2026-06-17 13:56 UTC
- **总 bypass 数**: 2
- **高频原因 Top 2**:
  1. `gaf-sync hook 把 96 行新版 docs-index.md 误回滚为 39 行旧版 (M0.L/N 闭环 bug),手动 add 96 行并 --no-verify 绕过 (N82 audit log 透明化)` — 1 次
  2. `AI ���� --no-verify ���� hook: ���� sync_skills.py --check ��ʱ hash ��һ�� (GAF �ֿ��� �� ������ vs workspace ��δͬ��), pre-commit hook ����ʱ workspace �� .trae/skills/gaf-dev-workflow/SKILL.md ȱ # gaf-dev-workflow marker (�û�ԭ�������� # GAF ����������). �޸�: �����ֶ� sync_skills.py + �� GAF/.trae/skills/gaf-dev-workflow/SKILL.md �� �� ��� hash һ��, - ���� 6 hooks Passed. ��֤: check_lessons_updated.py 7 lessons OK. ͸����: �� entry ���� audit log, commit - ������ȷ�� bypassed pre-commit.` — 1 次

### 转化决策
- `gaf-sync hook 把 96 行新版 docs-index.md 误回滚为 39 行旧版 (M0.L/N 闭环 bug),手动 add 96 行并 --no-verify 绕过 (N82 audit log 透明化)` (1 次) → **继续观察** (见 §2 已记录绕过清单跟踪)
- `AI ���� --no-verify ���� hook: ���� sync_skills.py --check ��ʱ hash ��һ�� (GAF �ֿ��� �� ������ vs workspace ��δͬ��), pre-commit hook ����ʱ workspace �� .trae/skills/gaf-dev-workflow/SKILL.md ȱ # gaf-dev-workflow marker (�û�ԭ�������� # GAF ����������). �޸�: �����ֶ� sync_skills.py + �� GAF/.trae/skills/gaf-dev-workflow/SKILL.md �� �� ��� hash һ��, - ���� 6 hooks Passed. ��֤: check_lessons_updated.py 7 lessons OK. ͸����: �� entry ���� audit log, commit - ������ȷ�� bypassed pre-commit.` (1 次) → **继续观察** (见 §2 已记录绕过清单跟踪)
---
