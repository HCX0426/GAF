---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, problem-step, evidence-problem]
solution: Problem 模板 — 描述症状/触发条件/影响范围;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/solution.md
  - .ai-memory/evidence/templates/verification.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-08-24
---
## Problem（症状 / 触发条件）

路径一致性检查器 `scripts/hooks/check_path_consistency.py` 在本轮健康检查中暴露两类缺陷：

1. **缓存陈旧误报**：扫描报出 186 条 warning，但真实扫描仅 139 条（且删除缓存后进一步降到 5 条）。根因是 mtime 缓存 manifest 只收录被扫文件与 `.gitignore`，**不含检查器脚本自身**——脚本逻辑变更（如 `SKIP_DIRS`、豁免正则）后缓存不失效，沿用旧计数。
2. **合法路径误报**：139 条 warning 全为 `abs` 类误报，主体是模拟器/ADB/OS 安装路径发现代码（`emulator_discovery.py`/`health_checker.py`/`ld_opengl.py` 等）、文档内示例路径、`.ai-memory` 内路径，并非 GAF 项目内部硬编码绝对路径。

同期对 AI 思维链规则（N167/N178/N172/N182-N185）做语义复核，并评估预提交 hook 接线完整性。

触发条件：完整套件负载下跑 `scripts/hooks/check_path_consistency.py`；提交阶段触发 `gaf-governance-batch` 的 `check_3step_evidence`（要求当日 evidence 目录）。
