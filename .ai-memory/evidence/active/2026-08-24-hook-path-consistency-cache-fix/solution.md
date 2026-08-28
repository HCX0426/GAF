---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, solution-step, evidence-solution]
solution: Solution 模板 — 列步骤 + 涉及文件 + 命令;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/problem.md
  - .ai-memory/evidence/templates/verification.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-08-24
---
## Solution（解决步骤）

1. `scripts/hooks/check_path_consistency.py` 的 `SKIP_DIRS` 增加 `.ai-memory`，豁免 AI 记忆内路径扫描。
2. 新增 `KNOWN_EXTERNAL_PATH_RE`，豁免模拟器/ADB/OS 安装路径（`ldplayer`/`mumu`/`bluestacks`/`nox`/`memu`/`adb.exe`/`.vbox`/`program files`/`system32`/`leidian`/`\\game\\`）。
3. `abs` 类检查额外豁免 `tests` 目录与 `.md` 文档路径（示例路径非真实硬编码）；`test_path_hooks_cache.py` 样本 `SAMPLE_PY_WITH_ABS_PATH` 改为非豁免路径 `C:\Users\developer\app_config.json` 保真。
4. 同文件 `_build_mtime_manifest` 把检查器脚本自身 `Path(__file__).resolve()` 的 mtime 纳入 manifest，逻辑变更即触发缓存失效重扫（修复 186 陈旧缓存）。
5. 语义复核：读 `.ai-memory/meta/yn-matrices/_refactor-dimensions.md`（N167 七维度表 + N178 A1-A4）与 `failure-modes.md`（N172/N182-N185）确认思维链规则自洽、无矛盾（N178-A2 刻意限定维度 4-7 不默认 5/5，与 N167 维度 3 单人项目 5/5 不冲突；N167 与 N182-N185 为通用框架 vs 专项流程的刻意分层、已交叉引用）。
6. 评估 `.pre-commit-config.yaml`：治理检查器已分 pre-commit/pre-push/post-commit/manual 四阶段接入，M1/M2/M3 机制齐备，架构完整。
