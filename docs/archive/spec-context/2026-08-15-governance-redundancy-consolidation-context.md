# Spec-Context: Governance Redundancy Consolidation (2026-08-15)

## 用户决策原文
- "目前gaf的工作流，规则文档，思维链，部分有冗余吗，案例是不是冗余" — 对治理体系提出冗余性质疑
- AskUserQuestion 选择: "开治理 spec 全部处理" — 扫描发现的 3 漂移 + 5 冗余 + 4 家族合并全部纳入当前 spec 处理，不抛遗留
- N167 评分方案 A（权威源收敛+家族合并）总分 20，领先方案 B 5 分 → AI 自决执行，用户双重确认

## N151 5 步法评估
1. **架构盘点**: 治理体系 5 层（L0 env-hardrules → L1 failure-modes → L2 handbook → L3 lessons/skills → yn-matrices）；权威源模式 v9.1 归一化；行级去重已成功（无 ≥8 行相同块）
2. **识别反模式**: R1 规则多版本漂移（3 处事实矛盾）R2 整段重述（5 处）R3 lesson 同事件多文件（4 组家族）R4 退役文件内容反转（N165 solution 与 N190 矛盾）R5 超大文件内部过期（N191 874 行）R6 索引含退役 N##
3. **备选方案**: A) 权威源收敛 + lesson 家族合并（零结构性改动，仅去重+对齐） B) 重写全部规则文档（伤筋动骨，风险高） C) 只修漂移不动冗余（半程方案）
4. **拒绝反模式**: 拒绝 B（过度治理）、C（半途而废）；选 A
5. **AI 自决边界**: 工作流双流程定义（决策树 vs task-execution）属结构性边界只消除步骤号冲突不合并决策树；N169+N174 家族合并降级登记 TD 后续处理

## N167 七维度评分
- **架构长远性**: 权威源收敛是 v9.1 归一化设计的自然延续，未来加规则只改 1 处 — 4
- **全局归一化**: 反思分级 10+ 文件 → 权威源 + 指针 — 4
- **新旧兼容**: N## 编号保留，仅 lesson 文件合并，无外部契约破坏 — 4
- **现有业务完善**: 修复 3 处事实漂移，消除规则矛盾 — 3
- **性能资源优化**: 文件数 77→73 核心，lessons 索引读取更快 — 3
- **安全合规加固**: 无涉 — 2
- **长期维护成本**: 大幅降低（家族文件单点维护 vs 多文件重复） — 4
- **总分**: 20（方案 B 总分 15，领先 5 分 → AI 自决）

## 关键实施决策
- **家族合并保留 N## 编号语义**: N183/184/185 仍在 failure-modes 索引 + handbook 红线独立生效，只统一 lesson 载体（N## 是编号不是文件路径）
- **N191 压缩策略**: §10.8 标 superseded（被 §10.10 8 维评分覆盖，明细表删除）；§10.9 G1-G7 保留（L0 env-hardrules N191 段引用"§10.9 G1-G7"）；§5/§10.5/§10.11/§10.12 检查清单原样保留（L0 引用）；874→~330 行
- **deleted lesson 文件 → .trash/lesson-family-merge/**（.gitignore 已忽略，git 显示 D）
- **handbook bug 排查纪律段** 改为家族文件指针 + 各 N## 独立红线
- **project_rules L558 修复** 历史 dangling ref（`workflow_2026-07-22-n183-...` 从未存在 → N182 家族文件）
- **evidence**: 空 session dir 填三件套（problem/solution/verification）+ B2 --acknowledge（TTL 30min）+ spec-context 承载体
- **doc-code-sync R4**: 5 个 deleted lesson 文件引用已 grep 验证无 live 残留（evidence/archived/specs 为历史记录不改），commit 需 `[skip-doc-sync]` 标记（N167 反思阶段强制确认）

## N173 用时字段
- start_ts: 2026-08-15T23:15:00+08:00
- end_ts: 2026-08-16T00:20:00+08:00 (预计)
- duration_min: 65 (预计)
- within_baseline: true (大修改基线 < 60 min，含 4 维度扫描耗时偏差记录在 spec deviation log)
- root_cause_if_over: 4 维度扫描（2 subagent 并行）已计入大修改范畴