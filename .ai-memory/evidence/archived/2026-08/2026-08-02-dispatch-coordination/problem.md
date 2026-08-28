# Problem: Dispatch Coordination Missing + URL Normalization + Perf Monitor

## 现象
1. 调度协调在架构层面从未被设计，代码中"长出来"的机制 — 无 Pending 自动恢复、无服务单例保证、无自动服务恢复
2. 子 pipeline 执行时 `pipeline_name_p0` 变量作用域错误导致 NameError → 线程静默崩溃
3. `handler.py` 异常未捕获，任务卡住
4. URL 拼接和配置分散在各层硬编码，缺乏统一归一化
5. 架构文档缺失调度链路、服务协调、异常恢复等关键内容
6. 缺乏全链路性能计量能力

## 影响
- 执行卡在 PENDING 永久 (3次)
- 重复进程导致调度冲突 (2次)
- 服务挂了无人重启 (2次)
- 配置文件 `.env.example` 和 3 个 app 层 URL 硬编码版本号
- 无法定位性能瓶颈