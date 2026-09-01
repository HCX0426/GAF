---
maintainer: derived-manual
source: docs/**/*.md (YAML frontmatter)
load_when: [新功能, Bug修复, 重构]
priority: high
symptom: [docs-index, design-discovery, ai-navigation]
solution: AI 任务开工 L2 硬加载,按 applies_to 决定是否查具体文档
related_files:
  - .ai-memory/meta/failure-modes.md
  - .skills/skills/gaf-orchestrator/SKILL.md
created_by: AI
generated: 2026-08-28
last_manual_edit: 2026-08-28
---

# GAF docs/ 设计文档索引（auto-generated）

> **强制**：AI 任务开工 L2 hard load 必须读本文件。
> 按 `applies_to` 决定是否需要查具体设计文档原文。
> 索引由 `python scripts/bootstrap/sync_docs_index.py` 自动生成。
> 文件 frontmatter 改动后必须重跑脚本更新本索引。

**生成时间**：2026-08-28  
**文档总数**：52  
**过期阈值**：90 天

## ✅ 全部文档新鲜（无过期）

## ❌ 缺少 frontmatter（必须修复）

- `docs/analysis/GAF-vs-Alas-analysis.md`
- `docs/analysis/GAF-vs-BD2-analysis.md`
- `docs/analysis/GAF-vs-MaaFramework-analysis.md`
- `docs/analysis/GAF-vs-ok-script-analysis.md`
- `docs/architecture/cross-cutting/dispatch-flow.md`
- `docs/archive/2026-08-health-report.md`
- `docs/archive/active-tech-debt.md`
- `docs/archive/fixed-tech-debt-details.md`
- `docs/archive/fixed-tech-debt.md`
- `docs/archive/spec-context/2026-08-15-governance-redundancy-consolidation-context.md`
- `docs/archive/spec-context/2026-08-16-s3-rag-revival-and-cost-loop-context.md`
- `docs/archive/spec-context/2026-08-17-s27-agent-interface-recovery-context.md`
- `docs/archive/spec-context/2026-08-17-s27-device-command-executors-context.md`
- `docs/archive/spec-context/2026-08-17-s27-hallucination-guard-strong-context.md`
- `docs/archive/spec-context/2026-08-17-s27-outbox-persistence-context.md`
- `docs/archive/spec-context/2026-08-17-s34-agents-views-split-context.md`
- `docs/archive/spec-context/2026-08-18-s35-pipeline-engine-split-context.md`
- `docs/archive/spec-context/2026-08-18-s36-adb-device-split-context.md`
- `docs/archive/spec-context/2026-08-18-s37-models-ts-split-context.md`
- `docs/archive/spec-context/2026-08-18-s38-sync-ai-memory-split-context.md`
- `docs/archive/spec-context/2026-08-18-s39-sync-skills-split-context.md`
- `docs/archive/spec-context/2026-08-18-s40-doc-health-test-split-context.md`
- `docs/archive/spec-context/2026-08-19-s43-td366-368-batch-context.md`
- `docs/archive/spec-context/2026-08-19-s45-recording-screenshot-closure-context.md`
- `docs/archive/spec-context/2026-08-20-governance-evaluation-fixes-context.md`
- `docs/archive/spec-context/2026-08-22-m2-behavioral-claim-exemption-context.md`
- `docs/archive/spec-context/2026-08-22-td389-recovery-metrics-context.md`
- `docs/archive/spec-context/2026-08-24-canvas-action-type-unification-context.md`
- `docs/archive/spec-context/2026-08-26-windows-ctrl-hardening-and-semantics-context.md`
- `docs/archive/spec-context/2026-08-27-execution-path-cleanup-context.md`
- `docs/archive/spec-context/env-hardrules-l0-split-context.md`
- `docs/archive/wontfix-tech-debt.md`
- `docs/archive/wontfix.md`
- `docs/business/ops/governance-dashboard.md`
- `docs/business/tasks/execution-reality.md`
- `docs/business/tasks/recovery-design.md`
- `docs/health/e2e-coverage.md`
- `docs/health/e2e-test-plan.md`
- `docs/reference/cli-cheatsheet.md`
- `docs/reference/data-flow.md`
- `docs/reference/performance-baseline.md`
- `docs/reference/tech-stack.md`
- `docs/reference/version-compat.md`
- `docs/specs/archived/2026-07/2026-07-25-docs-ai-memory-restructure.md`
- `docs/specs/archived/2026-07/2026-07-25-logging-pipeline-hardening.md`
- `docs/specs/archived/2026-07/2026-07-26-governance-batch-perf-cache.md`
- `docs/specs/archived/2026-07/2026-07-27-dual-debug-perspective-fixes.md`
- `docs/specs/archived/2026-07/2026-07-27-execution-path-unification.md`
- `docs/specs/archived/2026-07/2026-07-28-dual-debug-and-schema-followup.md`
- `docs/specs/archived/2026-08/2026-08-04-architecture-optimization.md`
- `docs/specs/archived/2026-08/2026-08-05-gaf-comprehensive-improvement-design.md`
- `docs/specs/archived/2026-08/2026-08-06-thinking-chain-explicit-and-evidence-simplify.md`
- `docs/specs/archived/2026-08/2026-08-08-architechure-debt-refactor.md`
- `docs/specs/archived/2026-08/2026-08-08-td343-td346-low-trigger-archive-and-dashboard-count.md`
- `docs/specs/archived/2026-08/2026-08-08-td345-pytest-baseline.md`
- `docs/specs/archived/2026-08/2026-08-08-td349-service-layer-test-coverage.md`
- `docs/specs/archived/2026-08/2026-08-08-td350-node-metadata-registry.md`
- `docs/specs/archived/2026-08/2026-08-08-td351-taskexecution-archive-strategy.md`
- `docs/specs/archived/2026-08/2026-08-08-td352-gaf-daemon.md`
- `docs/specs/archived/2026-08/2026-08-08-td353-pipeline-ghost-click.md`
- `docs/specs/archived/2026-08/2026-08-08-td354-engine-boundary-unification.md`
- `docs/specs/archived/2026-08/2026-08-09-pipeline-task-diagnosis-spec.md`
- `docs/specs/archived/2026-08/2026-08-09-td335-frontend-architecture-remaining.md`
- `docs/specs/archived/2026-08/2026-08-15-governance-redundancy-consolidation.md`
- `docs/specs/archived/2026-08/2026-08-16-s1-protocol-reliability.md`
- `docs/specs/archived/2026-08/2026-08-16-s2-recovery-link-wiring.md`
- `docs/specs/archived/2026-08/2026-08-16-s3-rag-revival-and-cost-loop.md`
- `docs/specs/archived/2026-08/2026-08-17-s27-agent-interface-recovery.md`
- `docs/specs/archived/2026-08/2026-08-17-s27-device-command-executors.md`
- `docs/specs/archived/2026-08/2026-08-17-s27-hallucination-guard-strong.md`
- `docs/specs/archived/2026-08/2026-08-17-s27-outbox-persistence.md`
- `docs/specs/archived/2026-08/2026-08-17-s28-ai-brain-index-repair.md`
- `docs/specs/archived/2026-08/2026-08-17-s29-m2-no-claim-coverage.md`
- `docs/specs/archived/2026-08/2026-08-17-s30-doc-health-patch.md`
- `docs/specs/archived/2026-08/2026-08-17-s31-yaml-frontmatter-fix.md`
- `docs/specs/archived/2026-08/2026-08-17-s32-sync-skills-timestamp-fix.md`
- `docs/specs/archived/2026-08/2026-08-17-s33-desktop-empty-icons.md`
- `docs/specs/archived/2026-08/2026-08-17-s34-agents-views-split.md`
- `docs/specs/archived/2026-08/2026-08-18-s35-pipeline-engine-split.md`
- `docs/specs/archived/2026-08/2026-08-18-s36-adb-device-split.md`
- `docs/specs/archived/2026-08/2026-08-18-s37-models-ts-split.md`
- `docs/specs/archived/2026-08/2026-08-18-s38-sync-ai-memory-split.md`
- `docs/specs/archived/2026-08/2026-08-18-s39-sync-skills-split.md`
- `docs/specs/archived/2026-08/2026-08-18-s40-doc-health-test-split.md`
- `docs/specs/archived/2026-08/2026-08-19-s42-l3-scan-a-fixes.md`
- `docs/specs/archived/2026-08/2026-08-19-s43-td366-368-batch.md`
- `docs/specs/archived/2026-08/2026-08-19-s45-recording-screenshot-closure.md`
- `docs/specs/archived/2026-08/2026-08-20-governance-evaluation-fixes.md`
- `docs/specs/archived/2026-08/2026-08-22-m2-behavioral-claim-exemption.md`
- `docs/specs/archived/2026-08/2026-08-24-canvas-action-type-unification.md`
- `docs/specs/dependency-graph.md`
- `docs/specs/legacy-trae/2026-07-18-spec25-td241-250-b-class-tech-debt-cleanup.md`
- `docs/specs/legacy-trae/2026-07-18-spec26-sedimentation-mechanism-and-doc-ownership.md`
- `docs/specs/legacy-trae/2026-07-18-spec27-folder-reorganization.md`
- `docs/specs/legacy-trae/2026-07-18-spec28-td132-bd2-pipeline-e2e-verification.md`
- `docs/specs/legacy-trae/2026-07-18-spec33-ai-workflow-slim.md`
- `docs/specs/legacy-trae/2026-07-19-spec34-auditlog-p0-wire-to-viewsets.md`
- `docs/specs/legacy-trae/2026-07-19-spec35-l3-1-scan-batch-fix.md`
- `docs/specs/legacy-trae/2026-07-19-spec36-ai-memory-ops-cleanup-and-n170-dedup.md`
- `docs/specs/legacy-trae/2026-07-19-spec37-docs-governance-p1-p2.md`
- `docs/specs/legacy-trae/2026-07-19-spec38-docs-ai-memory-full-governance.md`
- `docs/specs/legacy-trae/2026-07-19-spec39-docs-content-sync-and-rule-conflict-fix.md`
- `docs/specs/legacy-trae/2026-07-19-spec41-doc-health-checker-design.md`
- `docs/specs/legacy-trae/2026-07-19-spec42-self-evolution-flywheel-design.md`
- `docs/specs/legacy-trae/2026-07-20-spec36-a11y-governance.md`
- `docs/specs/legacy-trae/2026-07-20-spec38-hook-maintainer-mode-differentiation.md`
- `docs/specs/legacy-trae/2026-07-20-spec39-small-td-batch.md`
- `docs/specs/legacy-trae/2026-07-20-spec40-agent-selector-cleanup-and-constants.md`
- `docs/specs/legacy-trae/2026-07-20-spec43-forgetting-mechanism-design.md`
- `docs/specs/legacy-trae/2026-07-20-spec44-monthly-check-slimming.md`
- `docs/specs/legacy-trae/2026-07-20-spec44-td273-phase2-enum-migration.md`
- `docs/specs/legacy-trae/2026-07-20-spec45-monthly-check-automation.md`
- `docs/specs/legacy-trae/2026-07-20-spec45-td290-wontfix-td291-screenshot-retention.md`
- `docs/specs/legacy-trae/2026-07-20-spec46-d4-path-drift-evidence-downgrade.md`
- `docs/specs/legacy-trae/2026-07-20-spec47-td279-lesson-summary-path-drift-batch-fix.md`
- `docs/specs/legacy-trae/2026-07-20-spec48-p1-batch-fix-frontmatter-count-drift-bloat.md`
- `docs/specs/legacy-trae/2026-07-20-spec49-ai-self-decide-hardening.md`
- `docs/specs/legacy-trae/2026-07-20-spec50-d7-checker-scope-fix.md`
- `docs/specs/legacy-trae/2026-07-20-spec51-architecture-mistakes-dedup.md`
- `docs/specs/legacy-trae/2026-07-20-spec52-test-resource-pack-cleanup.md`
- `docs/specs/legacy-trae/2026-07-20-spec53-l3-b-class-and-d4-d7-residual-governance.md`
- `docs/specs/legacy-trae/2026-07-20-spec54-td281-migration-and-b-class-registration.md`
- `docs/specs/legacy-trae/2026-07-21-spec59b-rule-doc-slim-v92.md`
- `docs/specs/legacy-trae/2026-07-21-spec59c-workflow-rhythm-rule-retirement.md`
- `docs/specs/legacy-trae/2026-07-21-spec59d-n170-n165-retire.md`
- `docs/specs/legacy-trae/2026-07-21-spec59e-integration-layer-consistency.md`
- `docs/specs/legacy-trae/2026-07-21-spec60-td307-failure-modes-p5-threshold.md`
- `docs/specs/legacy-trae/2026-07-21-spec61-td312-promote-lessons-bugfix.md`
- `docs/specs/legacy-trae/2026-07-21-spec62-td311-n181-monthly-eval.md`
- `docs/specs/legacy-trae/2026-07-21-spec63-td304-frontend-raw-fetch-auth.md`
- `docs/specs/legacy-trae/2026-07-21-spec64-td308-test-time-eval.md`
- `docs/specs/legacy-trae/2026-07-21-spec65-td308a-pytest-xdist.md`
- `docs/specs/legacy-trae/2026-07-21-spec66-td308-close-td309-eval.md`
- `docs/specs/legacy-trae/2026-07-21-spec67-td313-redis-ping-timeout.md`
- `docs/specs/legacy-trae/2026-07-21-spec68-td310-wontfix-circular-mode.md`
- `docs/specs/legacy-trae/2026-07-21-spec69-td300-n1-select-related.md`
- `docs/specs/legacy-trae/2026-07-21-spec70-td314-pytest-n8.md`
- `docs/specs/legacy-trae/2026-07-21-spec71-td305-session-context-stale.md`
- `docs/specs/legacy-trae/2026-07-21-spec72-td306-why-skipped-dedup.md`
- `docs/specs/legacy-trae/2026-07-21-spec75-td294-utility-classes.md`
- `docs/specs/legacy-trae/2026-07-21-spec76-td294-inline-style-migration.md`
- `docs/specs/legacy-trae/2026-07-21-spec77-td294-hex-color-governance.md`
- `docs/specs/legacy-trae/2026-07-21-spec78-td294-toolbar-migration.md`
- `docs/specs/legacy-trae/2026-07-21-spec79-td294-toolbar-phase4c.md`
- `docs/specs/legacy-trae/2026-07-21-spec82-td320-gaf-init-powershell.md`
- `docs/specs/legacy-trae/2026-07-21-spec83-td321-b2-precommit-hook.md`
- `docs/specs/legacy-trae/2026-07-21-spec84-td322-spec-id-disambiguation.md`
- `docs/specs/legacy-trae/2026-07-21-spec85-td323-skill-frontmatter-timestamps.md`
- `docs/specs/legacy-trae/2026-07-22-spec105-td330-notifications.md`
- `docs/specs/legacy-trae/2026-07-22-spec106-td330-anomaly-pattern-panel.md`
- `docs/specs/legacy-trae/2026-07-22-spec107-td330-skill-market.md`
- `docs/specs/legacy-trae/2026-07-22-spec108-td330-account-group-manager.md`
- `docs/specs/legacy-trae/2026-07-22-spec109-td330-custom-skill-editor.md`
- `docs/specs/legacy-trae/2026-07-22-spec110-td330-account-batch-import.md`
- `docs/specs/legacy-trae/2026-07-22-spec111-td330-template-effectiveness.md`
- `docs/specs/legacy-trae/2026-07-22-spec112-td330-audit-log-log-center.md`
- `docs/specs/legacy-trae/2026-07-22-spec113-td330-validation-panel.md`
- `docs/specs/legacy-trae/2026-07-22-spec114-td330-specialty-log-tabs.md`
- `docs/specs/legacy-trae/2026-07-22-spec115-td330-step-configure-infra.md`
- `docs/specs/legacy-trae/2026-07-22-spec116-td330-pipeline-editor-page.md`
- `docs/specs/legacy-trae/2026-07-22-spec117-td330-execution-replay-setup-files.md`
- `docs/specs/legacy-trae/2026-07-22-spec118-td330-recording-editor-recordings-logintester-monitors.md`
- `docs/specs/legacy-trae/2026-07-22-spec86-td324-n181-retirement-eval.md`
- `docs/specs/legacy-trae/2026-07-22-spec87-td325-doc-code-sync-hook.md`
- `docs/specs/legacy-trae/2026-07-22-spec88-td336-three-dimensional-root-cause-rules.md`
- `docs/specs/legacy-trae/2026-07-22-spec89-td326-spec-dependency-graph.md`
- `docs/specs/legacy-trae/2026-07-22-spec90-td325-governance-dashboard.md`
- `docs/specs/legacy-trae/2026-07-22-spec91-td335-node-screenshot-strategy-normalization.md`
- `docs/specs/legacy-trae/2026-07-22-spec92-td327-e2e-ci-weekly.md`
- `docs/specs/legacy-trae/2026-07-22-spec93-td330-execution-monitor-panel.md`
- `docs/specs/legacy-trae/2026-07-22-spec94-td330-dag-editor-page.md`
- `docs/specs/legacy-trae/2026-07-22-spec95-td330-device-health-grid.md`
- `docs/specs/legacy-trae/2026-07-22-spec96-td330-daily-summary-carousel.md`
- `docs/specs/legacy-trae/2026-07-22-spec97-td330-alert-history-chart.md`
- `docs/specs/legacy-trae/2026-07-22-spec98-td330-ai-usage-dashboard.md`
- `docs/specs/legacy-trae/2026-07-22-spec99-td330-scheduled-tasks-index.md`

## 文档列表（按 applies_to 分组）

### .ai-memory（1）

- [docs/specs/archived/2026-07/2026-07-26-ai-memory-docs-health-governance.md](docs/specs/archived/2026-07/2026-07-26-ai-memory-docs-health-governance.md) — AI 工作流/规则/思维链综合评估治理 — 修复 evidence 积压/trigger_count 空转/编号冲突/空目录占位等 5 个系统性问题 _(updated 2026-07-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-26`
  - 治理分 4 波 (Wave 1-4), 独立任务用 subagent 并行
  - P0 立即修 (evidence 归档 + trigger_count 统计 + N167 冲突)
  - P1 本月内修 (空目录 + auto-kb + ref maintainer + 架构文档字段)

### .ai-memory/ref（1）

- [docs/specs/archived/2026-07/2026-07-26-td341-ref-docs-merge.md](docs/specs/archived/2026-07/2026-07-26-td341-ref-docs-merge.md) — TD-341 — .ai-memory/ref/ 4 个用户可读文件迁到 docs/reference/, ref/ 仅留 3 个 AI 内部文件 _(updated 2026-07-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-26`
  - 4 个用户可读文件 (tech-stack/data-flow/version-compat/cli-cheatsheet) 迁到 docs/reference/
  - ref/ 仅保留 3 个 AI 内部文件 (spec-index/session-context/doc-health-report-schema)
  - 分 4 波执行: 高风险脚本→规则/AI行为→简单替换→验收

### .ai-memory/spec-context（1）

- [docs/specs/archived/2026-07/2026-07-26-meta-governance-fix.md](docs/specs/archived/2026-07/2026-07-26-meta-governance-fix.md) — spec-2026-07-26-meta-governance-fix — meta 治理三件套 (spec-context 承载体 + fixed.md 分片 + B2 硬约束) _(updated 2026-07-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-17`
  - T1 补 TD-341 spec-context 承载体 (回填, 因 TD-341 已完成但未写承载体)
  - T2 fixed.md 年度分片 + 近 100 项保留 (TD-309 wontfix 重开)
  - T3 spec-context 机制硬约束化 (B2 大修改必写, project_rules.md + hook 强制)

### agent（9）

- [docs/architecture/agent/chain-mode-structured-logging.md](docs/architecture/agent/chain-mode-structured-logging.md) — chain 模式接入 StructuredLogger 的架构决策与多维度分析（已废弃） _(updated 2026-07-27)_
  - `module`: `architecture.agent`
  - `applies_to_code_paths`: `worker/src/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-05`
  - 方案 C：在 TaskOrchestrator 复用 StructuredLogger（与 PipelineEngine 对称接入）
  - chain step.name→node_id / step.action→node_type 字段映射
  - AutoResult 新增 structured_log_path 字段（向后兼容默认空串）
- [docs/architecture/agent/coordinate-transform-pipeline.md](docs/architecture/agent/coordinate-transform-pipeline.md) — GAF 坐标转换全链路文档，以模板匹配节点为例，从任务开始到点击落地经历的每一次坐标系变换 _(updated 2026-07-31)_
  - `module`: `architecture.agent`
  - `applies_to_code_paths`: `worker/src/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-21`
- [docs/architecture/agent/debug-logging-structure.md](docs/architecture/agent/debug-logging-structure.md) — GAF 调试日志记录结构文档，覆盖 agent/backend/frontend 三端 JSONL 结构化日志、系统日志（agent.log/daemon.log/django.log）和标注截图的完整记录时机、字段定义与合理性评估 _(updated 2026-08-09)_
  - `module`: `architecture.agent`
  - `applies_to_code_paths`: `worker/src/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-25`
- [docs/business/ai/input-mode-window-wait.md](docs/business/ai/input-mode-window-wait.md) — 输入模式测试 + 窗口后台等待功能设计 — BD2 get_mailbox 点击不生效问题修复方案 _(updated 2026-07-12)_
  - `module`: `business.ai`
  - `applies_to_code_paths`: `backend/gaf_ai/**`, `backend/skills/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-15`
- [docs/business/devices/dpi-coordinate.md](docs/business/devices/dpi-coordinate.md) — DPI 坐标系统设计 — 不同 DPI 缩放和分辨率下正确截图/匹配模板/点击目标 _(updated 2026-08-01)_
  - `module`: `business.devices`
  - `applies_to_code_paths`: `backend/devices/**`, `worker/src/devices/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-02`
- [docs/business/tasks/debug-mode-design.md](docs/business/tasks/debug-mode-design.md) — 调试模式设计 — 统一 GAF_DEBUG 环境变量控制所有 app 调试行为 _(updated 2026-08-01)_
  - `module`: `business.tasks`
  - `applies_to_code_paths`: `backend/tasks/**`, `frontend/src/pages/Tasks/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-21`
- [docs/business/tasks/timeline-design.md](docs/business/tasks/timeline-design.md) — 调试产物时间链路设计 — 让用户和 AI 都能按时间链追溯问题 (2026-07-29 废弃: timeline_generator/diagnosis_generator/score_curve_generator 三个工具已删除, 改用 JSONL trace + 前端节点详情抽屉) _(updated 2026-07-29)_
  - `module`: `business.tasks`
  - `applies_to_code_paths`: `backend/tasks/**`, `frontend/src/pages/Tasks/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-17`
- [docs/business/tasks/troubleshooting.md](docs/business/tasks/troubleshooting.md) — 任务执行问题排查步骤 — AI 排查任务执行失败时的可复用步骤指南 _(updated 2026-08-01)_
  - `module`: `business.tasks`
  - `applies_to_code_paths`: `backend/tasks/**`, `frontend/src/pages/Tasks/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-21`
- [docs/specs/archived/2026-08/2026-08-26-windows-ctrl-hardening-and-semantics.md](docs/specs/archived/2026-08/2026-08-26-windows-ctrl-hardening-and-semantics.md) — Windows 控制层加固与语义化 — 收敛 TD-396/397/398/399/395 的控制层债务，按架构方向分阶段根治 _(updated 2026-08-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-26`

### architecture（5）

- [docs/architecture/desktop/deployment-design.md](docs/architecture/desktop/deployment-design.md) — GAF 部署方案 _(updated 2026-08-08)_
  - `module`: `architecture.desktop`
  - `applies_to_code_paths`: `desktop/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-05`
  - 数据备份策略
  - Desktop Electron 一体化分发
- [docs/architecture/optimal-solution.md](docs/architecture/optimal-solution.md) — GAF 最优方案选择 — 四方对比与实施路线 _(updated 2026-07-12)_
  - `module`: `architecture`
  - `applies_to_code_paths`: `[]` (待新文档填入)
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-19`
  - 四、混合择优策略
  - 五、关键设计决策
- [docs/architecture/overview.md](docs/architecture/overview.md) — GAF 架构设计文档 _(updated 2026-08-26)_
  - `module`: `architecture`
  - `applies_to_code_paths`: `[]` (待新文档填入)
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-27`
  - 六、轮换策略
  - 九、关键设计决策记录
- [docs/architecture/README.md](docs/architecture/README.md) — architecture/ 架构视角索引（5 层 + 横切） _(updated 2026-07-26)_
  - `module`: `architecture`
  - `applies_to_code_paths`: `[]` (待新文档填入)
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-21`
  - 五层架构：frontend / backend / agent / desktop / cross-cutting
  - 架构根放总览类文档（overview / optimal-solution / features-overview）
  - 跨层文档放 cross-cutting/
- [docs/business/ai/llm-integration.md](docs/business/ai/llm-integration.md) — GAF LLM 集成设计 _(updated 2026-07-04)_
  - `module`: `business.ai`
  - `applies_to_code_paths`: `backend/gaf_ai/**`, `backend/skills/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-16`
  - 上下文收集策略
  - 降级策略
  - Phase 4.3-4.7 实现完成：6 个 builtin Skill YAML + dual-schema loader + LLMRouter 4 级降级链 + ContextCollector + TokenUsageTracker + Agent LLM 客户端

### backend（20）

- [docs/architecture/cross-cutting/concurrency-design.md](docs/architecture/cross-cutting/concurrency-design.md) — GAF 并发与性能设计 _(updated 2026-08-02)_
  - `module`: `architecture.cross-cutting`
  - `applies_to_code_paths`: `backend/protocol/**`, `backend/tracing/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-05`
  - 截图缓存策略
  - 设计稿部分类已实现为 helper，部分尚未接入生产路径
- [docs/archive/completed-features.md](docs/archive/completed-features.md) — GAF 已完成功能清单 — 项目级 status marker 落地点 (C-NNN) _(updated 2026-08-20)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-28`
- [docs/archive/pending-roadmap.md](docs/archive/pending-roadmap.md) — GAF 待办路线图 — 项目级未完成项登记表 (P-NNN) _(updated 2026-07-20)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-26`
- [docs/archive/tech-debt-README.md](docs/archive/tech-debt-README.md) — GAF 技术债务登记表 — 集中记录所有计划外技术债务 (TD-NNN) _(updated 2026-08-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-26`
- [docs/business/accounts/accounts.md](docs/business/accounts/accounts.md) — 账户管理 — 用户/游戏账户/分组/轮换/API Key/OAuth/2FA _(updated 2026-07-29)_
  - `module`: `business.accounts`
  - `applies_to_code_paths`: `backend/accounts/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-31`
  - User 三级角色 viewer/operator/admin
  - GameAccount 密码 AES-256-GCM 加密存储
  - GameAccountRotation 4 策略 sequential/random/by_stamina/by_last_executed
- [docs/business/devices/screenshot-optimization.md](docs/business/devices/screenshot-optimization.md) — GAF 截图优化设计 _(updated 2026-07-04)_
  - `module`: `business.devices`
  - `applies_to_code_paths`: `backend/devices/**`, `worker/src/devices/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-26`
  - 截图降级链策略
  - SSIM 策略检测
  - 现实状态：截图栈已实现，优化层 helpers 已实现（集成待 P3）
- [docs/business/game-profiles/game-profiles.md](docs/business/game-profiles/game-profiles.md) — 游戏档案管理（GameProfile）— 多游戏模式 / 默认 routine / 子资源绑定 _(updated 2026-08-01)_
  - `module`: `business.game-profiles`
  - `applies_to_code_paths`: `[]` (待新文档填入)
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-02`
  - GameProfile 是 Window-centric 架构的顶层组织单元，下绑 Device/Account/Task/TaskChain
  - default_routine FK → TaskChain，一键派发到所有在线设备
  - routine_path 支持 TD-113 多 GameProfile 指向不同 routine.json
- [docs/business/ops/monitor-design.md](docs/business/ops/monitor-design.md) — GAF 监控系统设计 _(updated 2026-07-05)_
  - `module`: `business.ops`
  - `applies_to_code_paths`: `backend/monitors/**`, `backend/notifications/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-26`
  - 概述
  - Phase 1 监控启用：MonitorManager.start() + 规则热更新通道 + monitor 节点接入 PopupHandler
- [docs/business/ops/scheduler.md](docs/business/ops/scheduler.md) — 任务调度 — 无人值守会话 / 时间窗口 / 5 层恢复 / 自动停止 / DAG 任务链 _(updated 2026-07-29)_
  - `module`: `business.ops`
  - `applies_to_code_paths`: `backend/monitors/**`, `backend/notifications/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-26`
  - scheduler 不直接派发任务, 通过 pipeline.services.create_chain_execution_and_dispatch 间接派发
  - UnattendedSession 按 game_profile 边界隔离 (P-011 多 session)
  - 5 层恢复 ActionChain 架构 (step/task/app/device/system)
- [docs/business/resources/resource-pack-design.md](docs/business/resources/resource-pack-design.md) — GAF 资源包规范设计 (合并 v1.0 spec + v1.1 guide) _(updated 2026-07-22)_
  - `module`: `business.resources`
  - `applies_to_code_paths`: `backend/resources/**`, `frontend/src/pages/Resources/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-29`
  - 资源包目录结构 (含 skills/ + custom_tasks/)
  - manifest.json JSON Schema 定义
  - config/tasks/monitors 文件格式规范
- [docs/business/system/system.md](docs/business/system/system.md) — 系统设置 — 无人值守策略 / LLM 配置 / 功能开关 / 调试日志 / 插件 / 审计 _(updated 2026-07-29)_
  - `module`: `business.system`
  - `applies_to_code_paths`: `[]` (待新文档填入)
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-28`
  - settings app 4 模型 + debug app 4 模型, 共 8 个数据模型
  - UnattendedStrategy 单例模式, 5 层恢复策略 + 夜间模式 + 频率限制 + 通知策略 + 冷却
  - LLMConfig api_key AES 加密存储, 响应仅返回 masked 预览
- [docs/business/tasks/cancel-design.md](docs/business/tasks/cancel-design.md) — GAF 任务取消与清理设计 _(updated 2026-07-05)_
  - `module`: `business.tasks`
  - `applies_to_code_paths`: `backend/tasks/**`, `frontend/src/pages/Tasks/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-05`
  - 概述
  - Phase 6.1-6.4 实现完成：SafePointChecker + CleanupManager + MonitorManager.force_stop_all + force-terminate 端点
- [docs/business/tasks/pipeline-authoring-guide.md](docs/business/tasks/pipeline-authoring-guide.md) — GAF Pipeline JSON 作者指南 — 39 节点类型目录 + 通用字段 + BD2 迁移示例 _(updated 2026-07-22)_
  - `module`: `business.tasks`
  - `applies_to_code_paths`: `backend/tasks/**`, `frontend/src/pages/Tasks/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-26`
  - 节点类型目录（39 类，含状态标记）
  - 通用生命周期字段
  - BD2 get_guild 完整 Pipeline JSON 示例
- [docs/business/tasks/pipeline-design.md](docs/business/tasks/pipeline-design.md) — GAF 自定义任务设计 _(updated 2026-07-27)_
  - `module`: `business.tasks`
  - `applies_to_code_paths`: `backend/tasks/**`, `frontend/src/pages/Tasks/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-29`
  - 可视化编辑器设计
  - 推荐使用 Pipeline 路径而非 Task chain
  - Phase 7 实现：state_machine dispatch + Editor 路由暴露 + Task validate 端点
- [docs/health/procedure.md](docs/health/procedure.md) — GAF 月度健康检查指南 — 全面 19 类可执行检查项 (G 类已迁自动 spec-41, C1/H1/I1/N1 已迁自动 spec-45, 月度跑 72 项) _(updated 2026-07-20)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-15`
- [docs/project-status.md](docs/project-status.md) — GAF 项目状态统一追踪 — 活跃待办/已完成功能/技术债务 (唯一入口) _(updated 2026-08-09)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-09`
- [docs/specs/archived/2026-08/2026-08-22-td389-recovery-metrics.md](docs/specs/archived/2026-08/2026-08-22-td389-recovery-metrics.md) — TD-389 — 恢复（recovery）指标纳入 analytics 聚合 _(updated 2026-08-23)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-28`
- [docs/specs/archived/2026-08/2026-08-23-td390-pipeline-guard.md](docs/specs/archived/2026-08/2026-08-23-td390-pipeline-guard.md) — TD-390 — LLM 生成 Pipeline 运行时守门（静态校验 + 风险评分） _(updated 2026-08-23)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-28`
- [docs/standards/backend-conventions.md](docs/standards/backend-conventions.md) — 后端通用规范 — Django/DRF 命名/序列化/权限/响应/测试，约束 AI 写出格式一致的 Python 代码 _(updated 2026-07-22)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-27`
  - Django app 一个目录一个业务域（accounts/tasks/agents/...），禁止单文件 app
  - 模型字段加 help_text + verbose_name，便于 admin 和 OpenAPI
  - ViewSet 优先用于 CRUD；@api_view 仅用于非 CRUD 业务逻辑（须加 @extend_schema + 注释，见 §4.1）
- [docs/standards/testing-conventions.md](docs/standards/testing-conventions.md) — 测试规范 — 四层测试（后端 pytest/Django TestCase + 前端 Vitest + E2E Playwright + agent 节点 pytest/MagicMock），约束 AI 写出格式一致的测试代码；验证优先级浏览器优先（用户指令 2026-08-27） _(updated 2026-08-27)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-28`
  - 后端用 Django TestCase（DB 测试）/ SimpleTestCase（非 DB），pytest-django 兼容
  - 测试文件位置：<app>/tests/test_<module>.py；集成测试包 __init__.py 必含 TD-068 throttle 补丁
  - 前端用 Vitest + jsdom + @testing-library/react，测试文件同级 __tests__/

### business（1）

- [docs/business/README.md](docs/business/README.md) — business/ 业务视角索引（9 模块，对应前端侧边栏） _(updated 2026-07-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-26`
  - 9 模块对应前端侧边栏：workspace / game-profile / tasks / devices / resources / accounts / ops / ai / system
  - 文档归属强制二选一，跨业务+架构的文档放 architecture/cross-cutting/

### docs（3）

- [docs/README.md](docs/README.md) — docs/ 双线索导航入口（业务 9 模块 + 架构 5 层） _(updated 2026-07-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-09`
  - 双线索导航：业务视角（前端侧边栏 9 模块）+ 架构视角（GAF 五层）
  - 文档归属强制二选一，跨业务+架构的文档放 architecture/cross-cutting/
  - spec 目录单一化：docs/specs/{active,archived}/
- [docs/specs/archived/2026-07/2026-07-26-trae-specs-plans-merge.md](docs/specs/archived/2026-07/2026-07-26-trae-specs-plans-merge.md) — spec-2026-07-26-trae-specs-plans-merge — .trae/specs + .trae/plans 合并到 docs/specs + docs/plans _(updated 2026-07-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-26`
  - 合并 .trae/specs/ (80 文件) → docs/specs/legacy-trae/ (保历史, 不混入 active/archived)
  - 合并 .trae/plans/ (3 文件) → docs/plans/legacy-trae/
  - 更新 6 脚本 + 5 hook + 2 rules 段 + 2 yn-matrices 段的 .trae/specs|plans 路径引用
- [docs/specs/archived/2026-08/2026-08-09-ai-memory-docs-dedup.md](docs/specs/archived/2026-08/2026-08-09-ai-memory-docs-dedup.md) — 清除 .ai-memory/ 与 docs/ 之间的 8 个字节级重复文件 + 4 个 spec-context 重复 + 路径漂移修复 _(updated 2026-08-09)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-09`

### features（1）

- [docs/architecture/features-overview.md](docs/architecture/features-overview.md) — GAF 功能总览（按前端侧边栏 9 模块组织，结合后端技术说明） _(updated 2026-08-08)_
  - `module`: `architecture`
  - `applies_to_code_paths`: `[]` (待新文档填入)
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-19`

### frontend（5）

- [docs/analysis/evaluation-zxcvbn-replacement.md](docs/analysis/evaluation-zxcvbn-replacement.md) — zxcvbn 替换评估 (Phase 4.5) — 评估前端密码强度库 zxcvbn 替换方案, 仅评估未改代码 _(updated 2026-07-12)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-26`
- [docs/business/dashboard/dashboard.md](docs/business/dashboard/dashboard.md) — 工作台 — 概览统计 / Agent 健康 / 快捷操作 / 趋势图表 _(updated 2026-07-29)_
  - `module`: `business.dashboard`
  - `applies_to_code_paths`: `[]` (待新文档填入)
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-31`
  - 无独立 dashboard 后端 app, 数据跨 6 个后端 app 聚合
  - 9 个 Widget 可拖拽布局, localStorage 持久化
  - Agent 健康 WebSocket 实时推送 (agent_heartbeat / agent_status)
- [docs/specs/archived/2026-07/2026-07-26-td335-336-remaining.md](docs/specs/archived/2026-07/2026-07-26-td335-336-remaining.md) — spec-2026-07-26-td335-336-remaining — TD-335 #3 i18n + TD-336 #6 测试断言 + TD-336 #7 agent 节点测试 _(updated 2026-07-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-26`
  - Wave 1 TD-335 #3: i18n 3 大文件 (NotificationPreferences 60 + AppLayout 42 + DeviceOperationPanel 119 = 221 处)
  - Wave 2 TD-336 #6: 测试断言增强 (~23 处 status_code==200 → 加响应体结构断言)
  - Wave 3 TD-336 #7: agent engine/nodes 21 个节点未测试 → 补 smoke tests
- [docs/standards/api-contract.md](docs/standards/api-contract.md) — 前后端接口契约 — URL 约定/请求/响应/错误码/分页/类型共享/版本控制，约束 AI 写出一致的 API _(updated 2026-07-27)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-28`
  - URL 用复数名词 + kebab-case：/api/v2/devices/, /api/v2/agent-instances/
  - 路径以 / 结尾（DRF 默认行为）
  - 当前响应格式：DRF 默认分页 { count, next, previous, results }（统一 { code, message, data } 已实现，通过 GAF_UNIFIED_RESPONSE_ENABLED 开启，默认 False 兼容旧客户端）
- [docs/standards/frontend-conventions.md](docs/standards/frontend-conventions.md) — 前端通用规范 — 组件命名/Props/状态/样式/错误处理/测试，约束 AI 写出格式一致的代码 _(updated 2026-07-18)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-20`
  - 组件命名 PascalCase，文件名同名（DeviceCard.tsx → DeviceCard）
  - Props 用 interface（不用 type alias），可选字段加 ?
  - 状态用 Zustand store（不用 Redux/Context），按业务域拆分（authStore/deviceStore/taskStore）

### pre-commit（1）

- [docs/architecture/cross-cutting/pre-commit-stages.md](docs/architecture/cross-cutting/pre-commit-stages.md) — Pre-commit Hook Stages 治理文档 _(updated 2026-07-22)_
  - `module`: `architecture.cross-cutting`
  - `applies_to_code_paths`: `backend/protocol/**`, `backend/tracing/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-23`

### project（1）

- [docs/business/ops/unattended-setup-checklist.md](docs/business/ops/unattended-setup-checklist.md) — 从零配置到无人值守循环挂机（多号轮换活动脚本）可复用检查清单 — GameProfile/TaskChain/账户/轮换/设备/会话 6 步 _(updated 2026-08-26)_
  - `module`: `business.ops`
  - `applies_to_code_paths`: `backend/monitors/**`, `backend/notifications/**`
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-26`

### scripts（1）

- [docs/specs/archived/2026-07/2026-07-26-ai-governance-execution-rate-fix.md](docs/specs/archived/2026-07/2026-07-26-ai-governance-execution-rate-fix.md) — spec-2026-07-26-ai-governance-execution-rate-fix — 治理体系执行率提升 (N173 hook 强制 + Y/N 矩阵精简 + 性能数据集中) _(updated 2026-07-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-07-26`
  - N173 spec/plan 用时测量改造: check_spec_context.py 强制 spec-context 含 start_ts/end_ts/duration 字段, 缺失则 commit 失败
  - Y/N 矩阵精简: 9 sub-file 150+ 项 → 保留 3 真实执行 + 归档 6 形式化 (转入 archived-yn-matrices/)
  - 性能数据集中: 新建 docs/reference/performance-baseline.md, governance-batch 自动 append (timestamp + 耗时 + pytest 耗时)

### specs（1）

- [docs/specs/README.md](docs/specs/README.md) — specs/ 跨设计文档的 spec 索引 + 进行中/已归档 spec _(updated 2026-07-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-15`
  - spec 目录单一化：合并自原 general/specs/ + superpowers/specs/ + .trae/specs/（.trae/specs/ 工具自动管理，不在本次范围）
  - 进行中 spec 放 active/，已归档按月放 archived/YYYY-MM/
  - dependency-graph.md 由 scripts/governance/spec_dependency_graph.py 自动生成

### workflow（1）

- [docs/archive/2026-07-health-report.md](docs/archive/2026-07-health-report.md) — 2026-07 月度健康检查报告 — 46 项中通过 28/失败 6/需关注 12; 首次基线检查, 发现 Win32 API 泄露 + npm 高危漏洞 + ruff 错误 + 失败测试 _(updated 2026-07-26)_
  - `maintainer`: `ai`
  - `doc_last_updated`: `2026-08-17`

---

## 维护说明

- 修改任何 docs/ 文件 → 更新其 `last_updated` + 重跑本脚本
- 新建 docs/ 文件 → 加 frontmatter + 重跑本脚本
- pre-commit hook: docs/ 改动 → 强制本索引更新
- gaf_init.sh L1: 警告过期文档 (>90 天)
