# Checklist — GameAccount.game_name 退役 (2026-08-29)

> 每项验收以实测/测试输出为证据，无证据不算通过。状态: ⏳ 待做 / ✅ 已做 / ❌ 失败。

## P1 后端写入/读取路径迁移

- [ ] ⏳ P1-1 创建/更新 serializer 支持 `game_profile_id`，并保留 `game_name` 兼容（get_or_create + 绑定）
- [ ] ⏳ P1-2 列表/详情 `game_name` 输出改为从 `game_profile.game_name` 读取（profile 存在时）
- [ ] ⏳ P1-3 `accounts/views.py` 的 `game_name` 查询过滤改走 `game_profile__game_name`（保留参数兼容）
- [ ] ⏳ P1-4 新增 serializer 单测：建账户绑 profile / 只给 game_name 自动建 profile / list 展示来自 profile / 兼容旧体 game_name

## P2 数据回填 + 约束迁移

- [ ] ⏳ P2-1 数据迁移 RunPython 将 4 条账户按 game_name get_or_create profile 并绑定（dry-run 先验证）
- [ ] ⏳ P2-2 迁移后断言：`GameAccount.objects.filter(game_profile__isnull=True).count() == 0`
- [ ] ⏳ P2-3 `game_profile` 列 NOT NULL + blank=False（AlterField）
- [ ] ⏳ P2-4 `unique_together` 迁移为 `(owner, game_profile, username)`（旧 game_name 约束随字段 P3 drop）
- [ ] ⏳ P2-5 `makemigrations --check` 无漂移；`migrate` 成功后数据回填率 100%

## P3 断开字符串 + drop 字段 + 前端契约

- [ ] ⏳ P3-1 移除后端对 `game_name` 的写/读硬依赖：__str__、admin list_display/search、批量导入校验、登录测试 message、统计 payload → 全部改 `game_profile`
- [ ] ⏳ P3-2 `migrations.RemoveField('game_name')` + 同步移除 unique_together 中 game_name
- [ ] ⏳ P3-3 前端 `GameAccountEditor` 表单：`game_name` 字段 → `game_profile_id` 选择；提交 body 变更
- [ ] ⏳ P3-4 前端展示路径（TaskDetailDrawer/auth.ts models）改读 game_profile 相关字段
- [ ] ⏳ P3-5 `npm run generate:api-types` 再生成 api.generated.ts（先重启 backend 加载新 schema）
- [ ] ⏳ P3-6 前端残留 grep：`GameAccount` 上下文内 `game_name` 引用清零（GameProfile 自身字段除外）

## P4 验收

- [ ] ⏳ P4-1 accounts 全量测试 + 涉及 serializer/views/批量导入/登录测试 的回归全绿
- [ ] ⏳ P4-2 账户流程 e2e：创建（选 profile）/编辑/批量导入/登录测试 均可用（真实无头浏览器）
- [ ] ⏳ P4-3 全量回归：`pytest backend/ -n 8` 通过；`manage.py check` 无 issue
- [ ] ⏳ P4-4 spec 状态全部 ✅ 后按 §3.4 归档：spec 归档 + hash 回填 + completed-features + spec-context 落盘