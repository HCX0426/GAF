# problem.md — P3 reflection (git mv agent/ -> worker/)

任务: naming-g P3 — agent 进程目录 `agent/` -> `worker/` + 符号 G-4/G-5/G-10/G-11 + `__main__` 入口。

范围边界: 只做执行节点目录搬迁 + 路径/launcher 引用改写 + 两类已列出符号；不碰协议/WS 符号 (P4)、其余后端符号 (P5)、前端类型 (P6)。

直接复用: 既有后端 agent_runtime spawn/kill + worker/src sys.path 语义；references 大量是纯路径字符串。

风险: PowerShell/CJK 文件损坏 (已有 6 文件修复史)、rename 后忽略追踪变化、既有 ruff 基线干扰"新增违规"判定、lesson related_files 断链。

验收: worker 全套绿 + backend 切片绿 + makemigrations --check 干净 + ruff 无相对 HEAD 新增 + 治理全过。

## 反思 ① 四问
- 本轮做什么? 见上"任务"。
- 可复用: bulk byte-safe 替换脚本模式 (P1/P2 验证过) + git mv R100 保证内容不变。
- 风险/依赖: Edit 工具在多行缩进代码上丢前导空格 (本次 2 次触发: test_ws_rpc.py + check_schema_unification.py)；日志 handler 测试依赖 logger level。
- 验收标准: 2278 passed / 0 failed (worker) + 490 passed (backend/hook 切片) + ruff 无新增 + b34d183 治理 18 项全过。

## 反思 ② A/B/C 分类
- [A] 已修复: background_key_input.py:183 隐性 import bug (worker/src sys.path 根因) — 真 bug, 非 rename 附带
- [A] 已修复: check_schema_unification.py 两次 Edit 缩进丢失 (invalid-syntax) — 工具陷阱, 立即 py_compile 验证
- [A] 已修复: 2 个 log_rotation 测试未设 logger level (默认 WARNING 吞 INFO → emit 从不触发) — TD-415 测试缺陷, 非产品回归
- [B] 待接: P4/P5/P6 符号与前端继续 (计划内)
- [C] worker/src 预存 N801/N802 ruff 债 (194 条基线) — hook 不拦 worker/src, R100 未动内容, 登记不新增 (见 verification.md 基线对比)

## 反思 ③ Round
- R1: ruff vs HEAD 基线对比 16 文件, 证明无新增 (agent_runtime 3->0, tasks_rag 1->0, 余持平); 抓出 check_schema_unification 2 条 invalid-syntax → 修复
- R2: 全仓活文件 agent/ 前缀残留扫描 → N187 related_files + setup-dev-env.ps1 + 5 个活文档 agent/requirements.txt -> worker/requirements.txt; archived YN 矩阵保留历史
- 终止: 连续 2 轮无新增 A 类

## 反思 ④ 状态标记
Y — ✓: rename 后 worker/ 全套测试证明可用 (2278 passed)；frontend 状态未变 (P6)。