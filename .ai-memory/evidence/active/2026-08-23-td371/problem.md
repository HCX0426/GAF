# TD-371 problem

- **症状**: `bash scripts/gaf_init.sh` 实跑报 "97 entries" 触发 N181 紧急评估警告；但 `failure-modes.md` 实测 Active 71 / Retired 16 / Dormant 10 = 97 全文件计数，文档声称 s28 退役 9 条后 "Active ~68" 与实测 71 不符；计数口径混淆（全文件 grep vs Active 段 grep）。
- **根因**: `gaf_init.sh` 原 `grep -cE "^\| N[0-9]+"` 统计全文件（含 Retired/Dormant/Archived 段），未限定 Active 段；硬阈值判定用错口径。
- **影响**: N181 硬阈值机制失真（97 vs 真实 Active 两个数字），每轮触发紧急评估警告却无实质动作，机制失效。
