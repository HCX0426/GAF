---
maintainer: manual
source: BD2 get_email pipeline 测试
load_when: [venv-deploy, dep-drift, rapidocr, OCR-engine, 部署脚本]
priority: high
symptom: [kb:venv-dep-drift, rapidocr-missing, N187, TD-337]
solution: venv gaf-agent 与 conda gaf env 双环境都需要装的依赖必须同步; agent/requirements.txt 补 rapidocr-onnxruntime
diff_keywords: ["requirements", "base", "setup", "dev", "env", "setup-dev-env", "tech", "stack", "tech-stack", "deployment", "design", "deployment-design"]
related_files:
  - agent/requirements.txt
  - backend/requirements/base.txt
  - scripts/setup-dev-env.ps1
  - docs/reference/tech-stack.md
  - docs/architecture/desktop/deployment-design.md
created_by: AI
topic: platform-env
last_updated: 2026-08-02
---


# N187 — venv 部署脚本依赖漂移 (TD-337)

## Problem（症状 / 触发条件）

BD2 get_email pipeline execution 100 失败, OCR 节点 `wait_regular_email` 报:
```
RapidOCR 未安装, 请执行: pip install rapidocr-onnxruntime
```

触发条件: 在 venv gaf-agent 环境下跑含 OCR 节点的 pipeline.

根因链:
1. `agent/requirements.txt` 未列 `rapidocr-onnxruntime`
2. `scripts/setup-dev-env.ps1` L351-363 用 `pip install -r agent/requirements.txt` 装 venv gaf-agent → venv 缺 rapidocr
3. `backend/requirements/base.txt` L16 列了 `rapidocr-onnxruntime>=1.3`, 但装到 conda gaf env, 不装到 venv gaf-agent
4. `agent/src/recognition/ocr/rapid_engine.py` 是默认 OCR 引擎 (orchestrator 启动时注册), 但用懒加载 — agent 启动时无 rapidocr 不报错, pipeline OCR 节点首次执行才报错

影响范围: 任何含 OCR 节点的 pipeline 在 venv gaf-agent 跑必失败, 用户需手动 `pip install rapidocr-onnxruntime` 兜底.

## Solution（解决步骤）

1. `agent/requirements.txt` 加 `rapidocr-onnxruntime>=1.3,<2.0` (与 `backend/requirements/base.txt` 版本对齐, 加上界 `<2.0` 防止 breaking change)
2. `docs/reference/tech-stack.md` §3.1 agent 依赖表补 `rapidocr-onnxruntime` 行 + `msgpack` 行 (顺带补齐 spec-42/TD-287 遗漏)
3. `docs/architecture/desktop/deployment-design.md` §2.4 补"双环境依赖说明"表格, 明确两环境装的依赖清单 + 刻意隔离原因 (opencv headless vs full)
4. `README.md` 技术栈表 Agent 行补 "RapidOCR (TD-337)" 标注

关键设计原则 (重要):
- **双环境隔离是官方设计** (README L88-110 / scripts/setup-dev-env.ps1 / deployment-design.md §2.3 明确), 不可合并
- conda gaf env (backend) 用 `opencv-python-headless` (服务器无 GUI)
- venv gaf-agent (agent) 用 `opencv-python` (含 GUI, 录制/显示需要)
- **两环境都需要装的依赖** (rapidocr-onnxruntime / numpy / Pillow / cryptography 等) 必须在 `agent/requirements.txt` 与 `backend/requirements/base.txt` 同步, 不能假设一边装了另一边就有

## Verification（验证）

```bash
# 1. 验证 agent/requirements.txt 已列 rapidocr
grep rapidocr d:/code/GAF/agent/requirements.txt
# 预期: rapidocr-onnxruntime>=1.3,<2.0

# 2. 验证 venv gaf-agent 已装 (临时 mitigation 已手动装)
D:\code\environment\venvs\gaf-agent\Scripts\python.exe -c "import rapidocr_onnxruntime; print(rapidocr_onnxruntime.__version__)"
# 预期: 1.4.4 (或 >=1.3 的版本)

# 3. 重装环境验证 (理论)
# 删除 venv gaf-agent → 重跑 scripts/setup-dev-env.ps1 → venv 应自动装 rapidocr
# (实际未执行重装, 仅验证 requirements.txt 已补)

# 4. tech-stack.md §3.1 验证
grep "rapidocr" d:/code/GAF/docs/reference/tech-stack.md
# 预期: 2 行 (§1.1 backend + §3.1 agent)
```

预期: `agent/requirements.txt` 包含 rapidocr, venv gaf-agent 可 import, tech-stack.md 双环境都列.

## 反思

**懒加载掩盖问题**: `rapid_engine.py` 用懒加载, agent 启动时无 rapidocr 不报错, 直到 pipeline OCR 节点首次执行才报错. 这种"延迟失败"模式让部署时缺依赖的问题难以在启动期发现. 教训: 核心能力依赖 (OCR 是 agent 核心能力) 不应用懒加载掩盖缺失, 应在启动时主动检查并警告 (但本 lesson 不改 rapid_engine.py, 仅补 requirements).

**为何 backend 没踩坑**: backend 的 OCR API 端点用 conda gaf env, base.txt 列了 rapidocr, 装的时候一起装了. agent 用独立 venv, requirements.txt 漏列, 就缺了. 双环境隔离的代价: 依赖清单要双份维护.

**编号冲突关联**: 与 N186 同源 (BD2 测试暴露), 同一天登记. 同样踩了 TD 编号冲突的坑 (TD-337 最初想用 TD-335, 与 fixed.md 已闭环的 TD-335 冲突, 后改为 TD-337).

---

## 后续变更 (N199, 2026-08-02 环境归一化)

2026-08-02 归一化: 所有服务统一使用 `conda gaf` 环境, 取消 `venv gaf-agent` 双环境设计.

**变更内容**:
- `scripts/gaf_services.ps1`: `$AgentPython` 从 venv 改为 conda 路径, backend 启动从 `runserver` 改为 `daphne`
- `scripts/setup-dev-env.ps1`: 去掉 venv 创建步骤, agent 依赖安装到 conda 环境
- `docs/architecture/desktop/deployment-design.md`: 双环境说明 → 环境归一化说明
- `.trae/rules/env-hardrules.md`: 双环境隔离段 → 环境归一化段

**归一化原因**: 原双环境设计基于 opencv 差异 (backend headless vs agent full GUI), 实际 agent 代码未使用任何 GUI 函数, `opencv-python-headless` 完全满足需求. 双环境导致 agent 启动入口不统一, 多次出现多进程冲突.

**影响**: 本 lesson 中的"双环境隔离是官方设计, 不可合并"的结论已作废. 旧 `venv gaf-agent` 目录已废弃.
