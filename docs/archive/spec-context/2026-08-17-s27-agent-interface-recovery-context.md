# Spec-Context: S2-2.7 Agent Interface Recovery Wiring (2026-08-17)

## 用户决策原文
- 2026-08-16 AI 大脑 + 工作流全面评估 Phase 1 获批后执行：S1 协议可靠性 → S2 恢复链接线 → S3 RAG 复活 + 诊断成本闭环 → 文档同步 + 每 spec 一次 commit
- "S2-2.7 agent 端界面恢复（yaml 状态机）单独排期，本 Phase 只接 backend 侧" — S2 范围收窄决策（S2-2.7 排期到 2026-08-17 单独 spec）
- "Continue if you have next steps"（2026-08-17）— 授权继续执行排期的 S2-2.7

## N151 5 步法评估
1. **架构盘点**: agent 端 InterfaceRecoveryManager（backend/scheduler/recovery_engine.py 同源类）已有恢复流程执行能力（恢复步骤读 node_params.section 的 template_match/click/wait 等），但缺失: (a) agent 端 yaml 状态机加载（config.py 无 interface_states_path 等 5 字段）; (b) engine.load 无 recovery_manager 注入 + 恢复重试上限硬编码 2; (c) orchestrator 未注入 Manager; (d) 无 interface_states.yaml 资源; (e) handler_map 无 device.command 命令处理（device 命令无 agent 端执行者）; (f) backend recovery_engine._action_semantic 的 restart/switch_account 诚实降级（无法解析时返回 failure 不派发）
2. **识别反模式**: P5 中 restart/switch_account 的降级行为（S2 早期 backend 侧接线时对无 agent 执行器的命令降级返回 failure）；restart_app 等命令在 handler.py 被整段删除（spec-35 曾移除，现需恢复）；orchestrator 手工构造恢复步骤 params 与 Manager 格式契约不一致风险
3. **备选方案**: A) 全链路接线（config 字段 + engine 注入 + orchestrator Manager + yaml 资源 + handler_map device.command + backend 派发，共 6 层） B) 只接 backend 派发（agent 端继续降级，恢复动作全失败）— 半途而废，拒绝 C) 只在 yaml 层接入（状态机文件先行，接线后续）— 增加中间态，拒绝
4. **拒绝反模式**: 拒绝 B（S2 范围收窄时明确 2.7 留待单独排期，继续降级 = 恢复功能假死）、C（拆两半引入中间态）；选 A
5. **AI 自决边界**: 恢复动作支持 5 类（template_match/key_press/click/swipe/wait）+ popup_handler 使用 monitor_manager 的（自决一致）；init 失败降级 warning 不阻塞主流程；P5 中 restart_app/relogin 等无 agent 执行器的命令登记 spec 已知限制（backend 派发 + agent 显式 not-implemented 上报，不在本 spec 实现执行器）

## N167 七维度评分
- **架构长远性**: 全链路接线让 yaml 状态机从"backend 只有文件"变为"agent 真实加载执行"，恢复能力闭环 — 4
- **全局归一化**: 恢复流程 backend 与 agent 端共用同一 yaml 契约 + 同一参数格式（node_params），无第二套契约 — 4
- **新旧兼容**: 不接线时行为不变（recovery_manager=None 时 retry 逻辑照旧）；新字段全部 optional 默认 None；backend 对无执行器命令从降级 failure 变为显式 error 上报（更诚实）— 4
- **现有业务完善**: 恢复链路可真实执行（template_match 等动作在 agent 端原生支持），非占位 — 4
- **性能资源优化**: 无性能影响（Manager 懒加载 + 初始化失败降级）— 3
- **安全合规加固**: 无涉 — 2
- **长期维护成本**: yaml 一处维护，两端读取；命令处理集中 handler_map 注册 — 4
- **总分**: 25（方案 A，≥19 且领先 ≥5 → AI 自决）

## 关键实施决策
- **AgentConfig 5 字段**: interface_states_path=None / unknown_state_archive_dir="debug/unknown_states" / max_recovery_steps=5 / max_recovery_retries=2 / archive_dedupe_window=10 — from_args **kwargs 自动透传，避免逐字段手写解析
- **engine.load 签名扩展**: recovery_manager=None + max_recovery_retries=2 两个新参数，硬编码 2 的 _attempt_recovery 改为消费 self._max_recovery_retries；pipeline_name 从 metadata 提取设置（恢复目标用）
- **orchestrator 注入**: 按 Path(interface_states_path).is_file() 条件创建（无文件不创建），_resolved_find_template 包装 resolve_resource_path 让恢复步骤模板路径可解析；初始化异常 → warning + recovery_manager=None（不阻塞 pipeline）
- **P5 命令处理恢复**: handler.py 原 spec-35 删除点恢复 handle_device_command；not-implemented 命令显式返回 {"success": False, "not_implemented": True} 而非静默；上报 device.action_result 带 trace_id（ContextVar）
- **backend 派发语义**: _action_semantic 的 restart/switch_account 不再降级 — 解析 execution → agent → ONLINE device → _action_device_command 派发 device.command（restart → restart_app 映射）；任一层解析失败 → 显式 error
- **yaml 资源命名**: 目录实际名带空格 `resources/BrownDust II/`（recovery-design.md 写的 `BrownDust-II` 是文档错误，实现按实际目录）；yaml 内模板路径用现有格式 `BrownDust II/templates/public/主界面.png`
- **主界面.png 不存在**: yaml 引用现成模板文件主界面.png 不存在（resources 模板目录无该文件）— 保持 yaml 存在（状态机先于模板制作），恢复执行时模板缺失会 fallback 到截图匹配（Manager 契约），登记 spec 已知限制
- **test_scheduler.py 旧测试更新**: test_semantic_action_returns_success（:2806）原断言 placeholder 行为，更新为 S2-2.7 语义（retry/skip 宽容、restart/switch_account 显式 error）
- **环境坑**: PowerShell 5.1 GBK 控制台读写 — 禁止 Get-Content/Set-Content 处理 UTF-8 文件（曾 GBK 写坏 spec）；文本编辑一律 Edit 工具；python 必须 `D:\code\environment\conda\envs\gaf\python.exe`（`python` 不在 PATH）
- **测试命令**: agent 测试 `-p no:django -o addopts=""`；backend 默认配置（test_scheduler.py e2e 标记默认 deselected，需 -m e2e）
- **git status 噪声**: 工作区 477 个 ` M`（CRLF/LF 归一化差异，core.autocrlf=true），git diff 仅 10 个真实内容差异文件 — 只 add 本 spec 13 个文件，避免把 EOL 噪声卷入 commit

## 已知限制（spec 记录，非本次实现）
- restart_app/relogin/notify_only/switch_backup/switch_account/restart 命令无 agent 端执行器 → 显式 not-implemented 上报（backend 已派发 + 记录）
- interface_states.yaml 中主界面.png 模板文件尚不存在（模板制作排期后），恢复执行时 template_match 会 fallback
- yaml 状态机仅 2 状态 1 转移（main_menu/map_view），后续按游戏实际界面扩展

## N173 用时字段
- start_ts: 2026-08-17T15:30:00+08:00
- end_ts: 2026-08-17T18:10:00+08:00
- duration_min: ~160
- within_baseline: false（大修改基线 < 60 min）
- root_cause_if_over: 实现前 gap 调查（config/engine/orchestrator/handler/backend 5 处接线点确认）+ 新增 26 个测试（21 agent + 5 backend）+ 全量回归（agent 2281 + backend scheduler 47 + protocol 268）+ P6 语义设计往返，属本 spec 真实工作量（P1-P7 全链路接线），非异常
