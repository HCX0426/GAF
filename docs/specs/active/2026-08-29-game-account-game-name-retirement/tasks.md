# Tasks — GameAccount.game_name 退役 (2026-08-29)

> 面向执行代理：逐任务 TDD（先写测试看红 → 实现看绿 → commit）。每任务独立 commit；阶段完成更新 spec.md 状态表。

---

### 任务 1 (P1): Serializer 写入路径迁移 — game_profile_id 优先 + game_name 兼容

**文件：**
- 修改：`backend/accounts/serializers.py`（GameAccountCreateSerializer / GameAccountUpdateSerializer）
- 新增测试：`backend/accounts/tests/test_game_account_profile.py`

- [ ] **步骤 1：写失败测试** — 建账户传 `game_profile_id: 1` 时应绑定 profile；只传 `game_name: 'BD2'` 时应自动创建/复用全局同名 profile 并绑定

```python
from rest_framework.test import APITestCase
from accounts.models import GameAccount
from gamestate.models import GameProfile


class GameAccountProfileBindingTest(APITestCase):
    def setUp(self):
        from accounts.models import User  # adapt to actual User model per test conventions
        self.user = User.objects.create_user(username='p1', password='x')
        self.client.force_authenticate(self.user)

    def test_create_with_profile_id_binds(self):
        profile = GameProfile.objects.create(game_name='BD2')
        res = self.client.post('/api/v2/accounts/game-accounts/', {
            'game_profile_id': profile.id, 'username': 'acc1', 'password': 'p',
        })
        self.assertEqual(res.status_code, 201)
        acc = GameAccount.objects.get(username='acc1')
        self.assertEqual(acc.game_profile_id, profile.id)

    def test_create_with_game_name_resolves_profile(self):
        res = self.client.post('/api/v2/accounts/game-accounts/', {
            'game_name': 'BD2', 'username': 'acc2', 'password': 'p',
        })
        self.assertEqual(res.status_code, 201)
        acc = GameAccount.objects.get(username='acc2')
        self.assertIsNotNone(acc.game_profile)
        self.assertEqual(acc.game_profile.game_name, 'BD2')
        self.assertEqual(GameProfile.objects.filter(game_name='BD2').count(), 1)  # reused, not duplicated
```

- [ ] **步骤 2：运行确认失败** — `conda run -n gaf python -m pytest backend/accounts/tests/test_game_account_profile.py -q --tb=short -o addopts=""` → 预期 FAIL（serializer 未接收 game_profile_id / game_name 未解析 profile）
- [ ] **步骤 3：实现** — `GameAccountCreateSerializer`/`UpdateSerializer`：

```python
game_profile_id = serializers.PrimaryKeyRelatedField(
    queryset=GameProfile.objects.all(), source='game_profile',
    required=False, allow_null=False, write_only=True,
)

def _resolve_profile(self, validated):
    profile = validated.pop('game_profile', None)
    raw_name = validated.pop('game_name', None)
    if profile is None and raw_name:
        profile, _ = GameProfile.objects.get_or_create(game_name=raw_name)
    if profile is not None:
        validated['game_profile'] = profile
        validated['game_name'] = profile.game_name  # keep string synced until P3 drop
    elif raw_name:
        validated['game_name'] = raw_name
    return validated
```

  - create(): `validated_data = self._resolve_profile(validated_data)` 后再加密密码入库
  - update(): 同法 resolve
  - >>> 顶部 `from gamestate.models import GameProfile`（`gamestate` 无跨 app 循环 import 风险）
- [ ] **步骤 4：运行确认通过** — 上面 pytest → 2 passed
- [ ] **步骤 5：Commit** — `git add backend/accounts/serializers.py backend/accounts/tests/test_game_account_profile.py && git commit -m "feat(accounts): GameAccount 写入支持 game_profile 绑定, game_name 兼容解析 (spec-2026-08-29-game-account-game-name-retirement P1)"`

---

### 任务 2 (P1): 展示路径迁移 — list/detail game_name 输出 = profile.game_name + 视图过滤

**文件：**
- 修改：`backend/accounts/serializers.py`（GameAccountListSerializer）、`backend/accounts/views.py`（game_name 过滤处）

- [ ] **步骤 1：写失败测试** — list 中已绑 profile 的账户，`game_name` 应来自 profile 名（改名 profile 后 list 输出跟随）

```python
def test_list_game_name_follows_profile(self):
    profile = GameProfile.objects.create(game_name='BD2')
    self.client.post('/api/v2/accounts/game-accounts/', {
        'game_profile_id': profile.id, 'username': 'acc3', 'password': 'p',
    })
    profile.game_name = 'BD2-Reforged'
    profile.save()
    res = self.client.get('/api/v2/accounts/game-accounts/')
    item = next(i for i in res.data['results'] if i['username'] == 'acc3')
    self.assertEqual(item['game_name'], 'BD2-Reforged')
```

- [ ] **步骤 2：运行确认失败** — 现状输出为库存的字符串 → FAIL
- [ ] **步骤 3：实现** — ListSerializer 增加 `game_name = serializers.SerializerMethodField()` + `def get_game_name(self, obj): return obj.game_profile.game_name if obj.game_profile_id else obj.game_name`（P1/P2 过渡：profile 缺失时 fallback 旧值）；`accounts/views.py` 中所有 `filter(game_name__icontains=...)` 改 `filter(game_profile__game_name__icontains=...)`
- [ ] **步骤 4：运行确认** — 该测试 PASS + 既有 accounts 测试不回归
- [ ] **步骤 5：Commit** — `feat(accounts): 展示层游戏名统一来自 game_profile (P1)`

---

### 任务 3 (P2): 数据回填 + NOT NULL + unique_together 迁移

**文件：**
- 修改：`backend/accounts/models.py`（game_profile null→False; unique_together）
- 新增：`backend/accounts/migrations/00XX_game_account_profile_retire.py`（RunPython + AlterField + AlterUniqueTogether）

- [ ] **步骤 1：dry-run 回填验证**（临时脚本，不进 commit）：遍历 4 条账户确认 game_name 均非空、无 profile 冲突 `GameProfile.objects.get_or_create(game_name=acc.game_name)` 可 1:1 完成
- [ ] **步骤 2：写迁移** — `migrations.RunPython(bind_profiles, reverse=migrations.RunPython.noop)`（bind 逻辑如前 dry-run）+ `AlterField(game_profile, null=False, blank=False)` + `AlterUniqueTogether(unique_together={('owner', 'game_profile', 'username')})`
- [ ] **步骤 3：`makemigrations --check`** 无漂移；`migrate` 后断言 `GameAccount.objects.filter(game_profile__isnull=True).count() == 0`
- [ ] **步骤 4：写迁移测试** — 用 `MigrationExecutor` 或复用现有迁移测试模式断言：迁移作用后全部账户有 profile、唯一约束可插入重名 username 不同 profile
- [ ] **步骤 5：Commit** — `feat(accounts): 数据回填 game_profile + 约束迁移 (P2)`

---

### 任务 4 (P3): 断开字符串依赖 + drop 字段

**文件：**
- 修改：`backend/accounts/views.py`（__str__ 相关→models 层）、`backend/accounts/models.py`（__str__、Meta、字段）、`backend/accounts/admin.py`、批量导入/登录测试/统计处、serializer（去除 game_name 写）
- 新增迁移：`RemoveField('game_name')`
- 新增测试：`test_game_account_views.py` 内批量导入/登录测试改用 profile

- [ ] **步骤 1：models** — `__str__ → f'{self.game_profile.game_name} - {self.username}'`（P2 后 profile 必填）；Meta 移除 `unique_together` 中 game_name（迁移已改）
- [ ] **步骤 2：views/admin/import/login-test/stats** 全部 `game_name` → `game_profile.game_name`；批量导入入口校验改收 `game_profile_id`（或 game_name → find_or_create）
- [ ] **步骤 3：serializer** — 移除 game_name 写入与 method field fallback（profile 必填后只输出 profile 派生字段）
- [ ] **步骤 4：新增迁移** — `migrations.RemoveField(... 'game_name')`；`migrate` 后 `inspectdb`/查询确认列已删
- [ ] **步骤 5：测试** — 上述改动处全量测试通过；`grep -rn "game_name" backend/accounts/` 仅剩 models 注释与历史迁移文件无实际引用
- [ ] **步骤 6：Commit** — `feat(accounts): 退役 GameAccount.game_name 字段, 全依赖收敛到 game_profile (P3)`

---

### 任务 5 (P3): 前端表单/展示/契约同步

**文件：**
- 修改：`frontend/src/pages/Accounts/GameAccountEditor.tsx`、`frontend/src/types/models/auth.ts`、`frontend/src/components/Task/TaskDetailDrawer.tsx`
- 生成：`frontend/src/types/api.generated.ts`

- [ ] **步骤 1：表单** — 提交字段 `game_name` → `game_profile_id`（保留下拉选择，选中 profile 传 id）；回填 `game_profile_id: account.game_profile?.id`（列表接口同时出 profile 摘要）
- [ ] **步骤 2：展示** — TaskDetailDrawer `acc.game_name` → `acc.game_profile_name`（serializer 输出别名，P3 序列化器加 `game_profile_name` read-only）或保留 read-only game_name 派生输出；auth.ts models 同步
- [ ] **步骤 3：重启 backend + `npm run generate:api-types`** → api.generated.ts 反映新契约；`npx tsc -b` 通过
- [ ] **步骤 4：Commit** — `feat(accounts): 前端账户表单/展示迁移到 game_profile 契约 (P3)`

---

### 任务 6 (P4): 验收 + 归档

- [ ] **步骤 1**：accounts 全量 + 前端 vitest/tsc 全绿
- [ ] **步骤 2**：账户 e2e（真实无头浏览器）：创建（选 profile）/编辑/批量导入/登录测试
- [ ] **步骤 3**：全量回归 `pytest backend/ -n 8`（含 scheduler/executions/tasks）
- [ ] **步骤 4**：归档：spec/checklist 状态 ✅、spec-context 落盘、completed-features 记录、hash 回填、active 副本移除（按 §3.4/TD-380 单条 docs commit）