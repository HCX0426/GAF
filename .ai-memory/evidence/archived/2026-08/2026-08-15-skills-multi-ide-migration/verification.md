# Verification: 迁移后验证

## 工具链检查
- `sync_skills.py --check`: EXIT=0
- `check_doc_path_drift.py`: 0 violation (2415 文件)
- `check_lessons_updated.py`: 143 lessons validated, EXIT=0 (含修复 archived-early 11 处 related_files 失效引用)
- pytest: 74 passed / 1 skipped (test_sync_spec_index 历史 skip), agent 侧 63 passed

## junction 检查
- [x] .trae/skills → .skills/skills (Junction)
- [x] .trae/rules → .skills/rules (Junction)
- [x] .opencode/skills → .skills/skills (Junction)
- [x] .opencode/rules → .skills/rules (Junction)

## 残留 .trae 引用
- 118 处残留全部复核: 历史记录、运行时缓存、junction 说明、全局 ~/.trae-cn 目录、死工具 n181_retirement_eval.py, 均有意保留
- docs-index.md 已重新生成 (generated: 2026-08-15), related_files 指向 .skills/...