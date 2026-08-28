---
date: 2026-06-21
symptom:
- audit
- false-negative
- scope
- backend
- agent
- frontend
solution: 'Audit scope must cover all three code trees: GAF/backend/, GAF/agent/,
  and GAF/frontend/. Searching only one tree creates false negatives.'
diff_keywords: ["script", "dsl", "script_dsl", "audit"]
related_files:
- agent/src/core/script_dsl.py
- agent/src/engine/nodes/maa_actions.py
- agent/src/core/wait_freezes.py
- agent/src/devices/emulator_discovery.py
- agent/src/core/worker_pool.py
- agent/src/recognition/ocr/onnx_paddle_engine.py
created_by: AI
level: L1
n_id: N129
topic: honest-status
---






# N129: Audit Scope Must Be Comprehensive (2026-06-21)



> **Source**: N128 audit follow-up — N128 falsely marked 6/7 N126-F tasks as "❌ 未实现" because audit only searched `backend/`, missing `agent/` where all implementations actually live.

> **Severity**: High — N128 created false-negatives (misjudged implemented as not-implemented), which is the mirror of N14/N126 false-positives.

> **Repeats**: N128 (false-positive) → **N129 (false-negative)** — same root cause (insufficient verification), opposite direction.



## 1. What Happened



After N128 (which found 6/7 N126-F tasks falsely marked ✅ in pending-roadmap.md), AI started "real implementation" of N126-F3 Script DSL. On checking `agent/src/core/script_dsl.py`:



- **N128 audit** only ran `Glob GAF/backend/**/verify*.py` and `Grep` in `backend/`

- **N128 missed** that GAF has TWO parallel code trees:

  - `backend/` — Django backend (handlers/, platforms/, etc.)

  - `agent/` — Standalone agent module (src/core/, src/devices/, src/recognition/, src/engine/)

- All N126-F2~F7 implementations live in `agent/`, not `backend/`



**Actual state (N129 audit)**:

| Task | N128 Verdict | N129 Reality | Location |

|------|-------------|--------------|----------|

| N126-F1 VerifyHandler | ❌ (real impl by N128) | ✅ N128 real impl | `backend/device_bridge/handlers/verify.py` (39 tests) |

| N126-F2 Maa JumpBack/WaitFreezes | ❌ not implemented | ✅ real impl | `agent/src/engine/nodes/maa_actions.py` + `agent/src/core/wait_freezes.py` |

| N126-F3 DSLCompiler | ❌ not implemented | ✅ real impl | `agent/src/core/script_dsl.py` (626 lines, 46 tests) |

| N126-F4 MuiCache/UserAssist/vbox-conf | 🔧 partial | ✅ real impl | `agent/src/devices/emulator_discovery.py` |

| N126-F5 WorkerPool | ❌ not implemented | ✅ real impl | `agent/src/core/worker_pool.py` |

| N126-F6 ONNXPaddleOCR/DGOCR | ❌ not implemented | ✅ real impl | `agent/src/recognition/ocr/onnx_paddle_engine.py` + `dgocr_engine.py` + `opencc_converter.py` |

| N126-F7 ascreencap_nc | ❌ not implemented | ✅ real impl | `agent/src/devices/adb/device.py` |



**Test verification**: `pytest GAF/agent/tests/test_maa_actions.py test_script_dsl.py test_emulator_discovery.py test_worker_pool.py test_ocr_engines_extended.py test_adb_device_extended.py -p no:django` → **223 passed, 2 skipped**.



## 2. Root Cause



N128 audit used **too narrow search scope**:

- Only searched `backend/` (Django backend)

- Did not search `agent/` (standalone agent module)

- Did not search `frontend/` (React frontend)



GAF has **3 parallel code trees**:

1. `backend/` — Django REST API + business logic

2. `agent/` — Standalone automation agent (core engine, devices, recognition)

3. `frontend/` — React SPA



N128 audit assumed all backend code lives in `backend/`, but the automation engine (VerifyHandler/DSLCompiler/WorkerPool/OCR/Maa/ADB) lives in `agent/`.



## 3. Lesson



**审计范围必须全面 (N128 假阳性 → N129 假阴性)**:



1. **3 棵代码树全搜** (写入 project_rules §5.15):

   - `backend/` — Django backend

   - `agent/` — Standalone agent module

   - `frontend/` — React frontend

2. **Glob/Grep 必须覆盖 3 棵树**: 不能只搜 `backend/`, 必须同时搜 `agent/` 和 `frontend/`

3. **假阴性 = 假阳性**: N128 假阳性 (虚报 ✅) 与 N129 假阴性 (误判已实现为未实现) 一样严重, 都导致错误决策

4. **审计前先列代码树**: 审计前先 `LS GAF/` 列出所有子目录, 确认搜索范围



## 4. Fix Applied (This Session)



1. **修正 pending-roadmap.md §二.20**: N126-F2~F7 全部改回 ✅ 已完成 (附 N129 审计证据: 文件路径 + 223 tests passed)

2. **修正 GAF-optimal-solution.md §七**: 在 N128 审计警告下加 N129 审计修正, 说明 N128 范围错误 + N129 真实状态

3. **N126-F1 仍是 N128 真实补全**: `backend/device_bridge/handlers/verify.py` (39 tests) — 这是 N128 唯一的真实贡献



## 5. 5-Layer Distribution (N95)



| # | Layer | Path | Status |

|:--:|------|------|:------:|

| ① | .ai-memory/lessons/ | `N129-audit-scope-must-be-comprehensive.md` (本文件) | ✅ |

| ② | .ai-memory/summaries/ | `architecture-mistakes.md #55 N129` | ✅ |

| ③ | spec/pending-roadmap.md | §二.20 (N126-F2~F7 状态修正回 ✅) | ✅ |

| ④ | gaf-orchestrator/SKILL.md | §3.2 ㉒ N129 Y/N matrix | ⏳ |

| ⑤ | project_rules.md | §5.15 N129 (3-tree audit scope) | ⏳ |



## 6. Reflection Checklist (5 Questions per N127)



1. **本段做了什么?** — 发现 N128 审计范围错误 (只搜 backend/ 没搜 agent/), 修正 N126-F2~F7 状态从 ❌ 改回 ✅ 真实实现 (223 tests passed)

2. **有什么教训?** — 审计范围必须全面 (backend/ + agent/ + frontend/ 3 棵树), 假阴性 = 假阳性 一样严重

3. **是否需 5 层分发?** — 是, 本文件 + architecture-mistakes #55 + pending-roadmap §二.20 + SKILL ㉒ + rules §5.15

4. **ROADMAP 是否更新?** — 是, N126-F2~F7 全部 ✅ 真实实现 (附 N129 审计证据)

5. **下一段是什么?** — N126-F1~F7 全部完成, 转 P-033 Phase 3 长尾页面 i18n 或其他简单任务



## 7. References



- N14 lesson: honest status marking

- N126 lesson: 5 false positives (color_detect/feature_match/Script DSL/VerifyHandler 2-5/emulator)

- N128 lesson: 6/7 false positives + fabricated test counts (audit scope too narrow → false-negatives)

- N129 (本文件): audit scope must cover 3 code trees (backend/ + agent/ + frontend/)

- GAF code structure: `backend/` (Django) + `agent/` (standalone agent) + `frontend/` (React)
