# Solution: 治理冗余收敛 spec-2026-08-15-governance-redundancy-consolidation

## 方案
采用 N167 七维度评分方案 A（总分 20，领先方案 B 5 分，AI 自决）：

**Phase 1 规则漂移对齐（3 处）**：
- D1 `-F` 禁用：handbook L247-248 删除等价句改指向 env-hardrules N190；project_rules + task-execution 2 处残留同步修复
- D2 反思分级：project_rules §4.6 N179-C2 对齐 reflect-and-evolve §2（行数判定，中=5 项）
- D3 沉淀判定：handbook 改"问 1 个问题"（对齐 project_rules §3.8）

**Phase 2 整段冗余收敛（5 处）**：
- R1 N199 重述删 7 行留 1 行指针；R2 N177 重复 MemoryError 细节删除；R3 七维度阈值收敛到 2 处权威；R4 gaf_init 经查无冗余跳过；R5 UTF-8 注释保留

**Phase 3 lesson 家族合并（4 组）**：
- N182-185 合并为家族文件（N183/184/185 移 .trash）；N172+175 合并；N171+173 合并；N165 标 superseded_by N190；N191 压缩 874→~330 行（§10.8 superseded，检查清单保留）

**Phase 4 验证**：check_lessons_updated 77 lessons ✅ / sync_skills ✅ / sync_ai_memory 重算 lessons_count=67 ✅ / check_yn_matrices ✅ / check_path_consistency 0 error ✅