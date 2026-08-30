# verification.md — P3 验收证据

## 提交
- 符号子提交: `9fd0085` (G-4/G-5/G-10/G-11, 16 文件, 207 passed)
- 目录+引用提交: `b34d183` (277 renames + 875± 行改写, 治理 18 项 17 PASS + 1 WARN)

## 测试
| 套件 | 结果 |
|------|------|
| `pytest worker/tests -p no:django -o addopts=""` | 2278 passed / 3 skipped / 0 failed |
| backend 切片 (workers+device_bridge+protocol+test_llm+hook 测试) | 490 passed / 0 failed |
| `test_sync_error_codes_i18n + test_sync_conflict` | 23 passed |
| `makemigrations --check --dry-run` | No changes detected |
| log_rotation 专项 | 2 passed (level fix 后) |

## ruff 基线对比 (HEAD vs now, 内容级修改文件)
agent_runtime 3→0, tasks_rag 1→0, settings/views 1→0, test_llm 1→0, recognition 1→0 (编辑顺带清掉部分); sync_ai_memory 60=60, sync_docs_index 12=12, sync_error_codes 37=37, gaf_daemon 18=18, health 1=1, N187-related 文件持平。**无新增违规** (check_schema_unification 2 条 invalid-syntax 由缩进丢失导致, 已修复归零)。

worker/src 预存 N801/N802 等 133-194 条 ruff 债为既有基线 (hook 不拦 worker/src lint; R100 rename 内容未动), 不构成本轮新增。

## 治理
b34d183: 18 项检查 17 PASS + 1 WARN (doc-path-drift 7 条缓存命中, 白名单跳过) — B2 evidence (.cache/b2_acknowledged.json, is_big=true, 4 个 app 跨模块)。