# spec-25: TD-241~TD-250 [B] 类技术债务清理 (2026-07-18)

> **触发**: 用户反馈 2026-07-18 — "要是有技术债务，为啥会延后，延后也是指在做完上一个类别接着做，而不是等我的指令"
> **来源**: spec-24 L3 Round 25 登记的 10 条 [B] 类技术债务 (TD-241~TD-250)
> **范围**: 修复全部 10 条 [B] 类, P2 (5 条) + P3 (5 条), 不延后

## 阶段状态表

| Phase | 内容 | 状态 | 完成时间 | commit hash | 验收 evidence |
|:-----:|------|:---:|:---------:|:-----------:|--------------|
| Phase 1 | TD-241 version-sync→version-compat + TD-249 时间戳同步 | ✅ | 2026-07-18 | (本 spec commit) | hook 通过 + grep 确认 |
| Phase 2 | TD-242 topic 命名映射注释 | ✅ | 2026-07-18 | (本 spec commit) | hook 通过 |
| Phase 3 | TD-243+TD-244 L3-1 路径归一 | ✅ | 2026-07-18 | (本 spec commit) | grep 确认路径 |
| Phase 4 | TD-245+TD-246 重复内容瘦身 | ✅ | 2026-07-18 | (本 spec commit) | 行数减少 |
| Phase 5 | TD-247 N108 退役 + TD-248 N155 cross-topic 迁移 + TD-250 记法区分 | ✅ | 2026-07-18 | (本 spec commit) | hook 通过 + sync_ai_memory OK |
| Phase 6 | sync 验证 + commit + Round 29 | ✅ | 2026-07-18 | - | sync_ai_memory.py 通过 (2.85s, 4 regenerated, 0 conflict) |

## TD 清单

| TD | 优先级 | 症状 | 修复方案 | 状态 |
|:--:|:-----:|------|---------|:---:|
| TD-241 | P2 | version-sync.md vs version-compat.md 文件名不一致 | ai-operating-handbook.md L4/L45 version-sync→version-compat | ✅ |
| TD-242 | P2 | topic 命名不归一: architecture (lessons) vs refactor-dimensions (yn-matrices) | yn-matrices.md L40 加映射注释 "(= lessons/architecture topic 的 Y/N 矩阵分组)" | ✅ |
| TD-243 | P2 | L3-1 monthly-health-check 路径不归一 | project_rules.md §3.7 + _workflow.md 路径归一为 `.ai-memory/ops/monthly-health-checks/` | ✅ |
| TD-244 | P2 | L3-1 architecture evaluation 路径不归一 | project_rules.md §3.7 + _workflow.md 路径归一为 `docs/architecture/*-evaluation.md` | ✅ |
| TD-245 | P2 | L3-1 9 维度清单重复内容 | gaf-orchestrator/SKILL.md 9 维度瘦身为标题引用, 单一权威源指向 rules | ✅ |
| TD-246 | P3 | 7 维度评估清单重复内容 | project_rules.md §2.0.5 删除维度适用场景清单, 引用 _refactor-dimensions.md | ✅ |
| TD-247 | P3 | N108 在 Active 但无 yn-matrices 引用 | N108 从 Active 移到 §Retired (M0.M 闭环, 硬约束已沉淀到 §3.4) | ✅ |
| TD-248 | P3 | N155 Y/N 矩阵跨 topic 历史遗留 | N155 Y/N 矩阵从 _ai-autonomy.md §㉖ 迁到 _misc.md §12 platform-env, 与 lesson topic 一致 | ✅ |
| TD-249 | P3 | ai-operating-handbook.md updated 时间戳过期 | L3 frontmatter updated 同步到 2026-07-18 | ✅ |
| TD-250 | P3 | lessons/README.md "(+N archived)" 记法歧义 | 区分 "(+N early unnumbered archived in `archived-early/`)" vs N## 归档 (如 N30) | ✅ |

## Phase 详情

### Phase 1: TD-241 + TD-249 (version-sync→version-compat + 时间戳同步)

**文件**: `.ai-memory/meta/ai-operating-handbook.md`
- L3 frontmatter `updated: 2026-07-16` → `updated: 2026-07-18 (spec-25 Phase 1+5: TD-241 version-sync→version-compat 修正 + TD-249 时间戳同步)`
- L4 `version-sync.md` → `version-compat.md`
- L45 `| 涉及版本/依赖/TS 严格选项 | \`version-sync.md\` | Read |` → `| 涉及版本/依赖/TS 严格选项 | \`version-compat.md\` | Read |`

**验收**: grep 确认无 `version-sync.md` 引用

### Phase 2: TD-242 (topic 命名映射注释)

**文件**: `.ai-memory/meta/yn-matrices.md` L40
- refactor-dimensions 行的 "触发场景" 列追加 "(= lessons/architecture topic 的 Y/N 矩阵分组, spec-25 Phase 2 TD-242 命名归一)"

**注**: 最初把注释加在 topic 名列, 导致 hook 查找文件失败, 已修正移到 "触发场景" 列。

### Phase 3: TD-243 + TD-244 (L3-1 路径归一)

**文件**: `.trae/rules/project_rules.md` §3.7 L299 + `.ai-memory/meta/yn-matrices/_workflow.md` L340
- `monthly-health-check.md` → `` `.ai-memory/ops/monthly-health-checks/` ``
- `architecture/*-evaluation.md` → `` `docs/architecture/*-evaluation.md` ``

### Phase 4: TD-245 + TD-246 (重复内容瘦身)

**文件**: `.trae/skills/gaf-orchestrator/SKILL.md` L313-325 + `.trae/rules/project_rules.md` §2.0.5 L166-186
- TD-245: 9 维度清单从完整描述瘦身为标题引用, 详情指向 rules §3.7 单一权威源
- TD-246: 7 维度评估清单删除 "维度适用场景" 7 行 + "GAF 项目定位" 段, 引用 _refactor-dimensions.md 单一权威源

### Phase 5: TD-247 + TD-248 + TD-250

**TD-247 (N108 退役)**:
- `.ai-memory/meta/failure-modes.md`: N108 从 Active 表移到 §Retired 表 (闭环原因: M0.M 闭环, 硬约束已沉淀到 project_rules.md §3.4)
- 计数同步: 51→50 Active, 4→5 Retired
- `.ai-memory/meta/archived-lessons.md` + `.ai-memory/lessons/README.md` frontmatter 计数同步

**TD-248 (N155 cross-topic 迁移)**:
- `.ai-memory/meta/yn-matrices/_misc.md`: 新增 §12 platform-env 段, 合并 N154 + N155 Y/N 矩阵
- `.ai-memory/meta/yn-matrices/_ai-autonomy.md`: §㉖ N155 Y/N 矩阵改为指针 (非 `### N###` heading 避免索引漂移)
- `.ai-memory/meta/yn-matrices.md`: ai-autonomy 行移除 N155, misc 行加 N154/N155
- `.ai-memory/meta/failure-modes.md` §Dormant N155 行: Y/N 矩阵位置改为 `_misc.md §12 platform-env`

**TD-250 (记法区分)**:
- `.ai-memory/lessons/README.md` topic 表: "(+N archived)" → "(+N early unnumbered archived in `archived-early/`)" (4 处: api-design/agent-protocol/pipeline/spec)
- N## 归档 (如 N30) 保持 "archived N30" 明确记法

### Phase 6: sync 验证 + commit + Round 29

- `sync_ai_memory.py`: ✅ regenerated=4 skipped=104 conflict=0
- `sync_skills.py --check`: ✅ 4 skills + 1 rule 副本一致
- `check_yn_matrices_index.py`: ✅ index and sub-files agree
- active.md TD-241~TD-250 标 ✅ FIXED
- git commit
- L3 Round 29 扫描验证无新 [A] 类

## 验收标准

- [x] TD-241~TD-250 全部修复
- [x] sync_ai_memory.py 无冲突
- [x] sync_skills.py --check 副本一致
- [x] check_yn_matrices_index.py 通过
- [x] active.md TD-241~TD-250 标 ✅ FIXED
- [ ] git commit 成功
- [ ] L3 Round 29 无新 [A] 类
