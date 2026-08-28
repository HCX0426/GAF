# s38 verification evidence

## 验收标准逐项

| # | 标准 | 结果 |
|---|------|------|
| 1 | 主文件 < 1000 行，15 函数移出 | ✅ 1384 → 910 行；collect 7 + mtime_cache 5 + counters 3 = 15 函数移出，函数名/签名不变 |
| 2 | 4 个直接依赖测试文件全绿（yaml/REPO_ROOT_DEFAULT patch 语义保持） | ✅ `pytest scripts/tests/test_sync_ai_memory.py test_sync_ai_memory_cache.py test_sync_conflict.py test_sync_lock.py` = 64 passed（基线 64） |
| 3 | scripts/tests 全量与基线一致 | ✅ 606 passed + 2 skipped + 2 failed（1 = e2e 前端未启动环境性，基线同；1 = benchmark 抖动，stash 基线对比确认同为 1.05s 失败，非回归） |
| 4 | 三调用路径冒烟 | ✅ CLI `python scripts/bootstrap/sync_ai_memory.py --stats` rc 0；`from scripts.bootstrap import sync_ai_memory` re-exports NONE missing；governance batch **13/13 passed**（`python scripts/hooks/gaf_governance_batch.py`） |
| 5 | ruff | ✅ 主文件 60 errors（预存风格 UP006/UP035/E402 等）+ 新文件 37 errors（30 UP006/3 UP035 预存风格 + 已修 I001×2/F841×1），无新增 F401/F821 等功能性错误；全目录 409 → 375（净减少） |

## 基线对比

- stash 主文件还原后跑 benchmark 失败测试：**同样 1.05s 失败** → 确认抖动非拆分引入（N202 ⑯ 基线对比法）。
- test_e2e_run_all：ERR_CONNECTION_REFUSED 127.0.0.1:5173（前端未启动，环境性）。

## 关键命令

```powershell
D:\code\environment\conda\envs\gaf\python.exe -m pytest scripts/tests/test_sync_ai_memory.py scripts/tests/test_sync_ai_memory_cache.py scripts/tests/test_sync_conflict.py scripts/tests/test_sync_lock.py -p no:django -o addopts="" -q
# 64 passed
D:\code\environment\conda\envs\gaf\python.exe -m pytest scripts/tests/ -p no:django -o addopts="" -q
# 606 passed, 2 skipped, 2 failed (环境性/抖动)
```

## 时间

- N173：start 20:30 / end 21:15 / duration 45min / within_baseline（大修改 < 60min 基线 ✅）/ root_cause：D1 re-export 位置 + D2 两层循环（多模块名 + win32/scripts 顶层包名冲突，单路径探测定位）