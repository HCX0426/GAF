# TD-371 verification

- **gaf_init 计数口径**: `awk '/^## Active/{f=1;next} /^## /&&f{f=0} f'` 已限定 Active 段，全文件 grep 不再混入 Retired/Dormant/Archived。
- **N181 退役评估实跑**: `python scripts/governance/n181_retirement_eval.py --check` 输出
  - `📊 Active N## 总数: 36`
  - `🔍 阈值检查: Active N## 36 ≤ 70 (未超阈值)` → N181 紧急评估警告不再触发
  - 条件 A 候选 32 条（N105/N109/N126/.../N206），附条件 B/C 人工复核说明
- **结论**: gaf_init L1 输出真实 Active 计数（36）；Active ≤ 70，N181 警告消静；评估已执行并有记录。TD-371 验证标准满足 ✅
- **副作用**: 无代码/规则变更（评估为只读模式）；Active 计数由 97(误) → 36(真)，治理告警噪声消除。
