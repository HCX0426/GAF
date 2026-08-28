"""R37-P1 game_profile binding helpers.

Pure service layer — no model definitions. Uses lazy imports inside functions
to avoid the circular import chain:
  agents.models ↔ tasks.models (Task imports Agent)
  resources.models ↔ tasks.models (Task imports ResourcePack)

Public API:
  bind_game_profile_by_title(window_title, device_type_hint=None) -> Optional[GameProfile]
  bind_game_profile_by_target_app(target_app, device_type_hint=None) -> Optional[GameProfile]
  backfill_game_profile_links() -> dict[str, int]

Call sites:
  - agents.views.DeviceRegisterView (HTTP path) — bind on create/update
  - protocol.consumers._db_register_device (WS path) — bind in defaults dict
  - accounts/management/commands/seed_data.py — re-run backfill after seeding
  - migrations — RunPython calls backfill_game_profile_links (best-effort)

TD-333 (2026-07-22): device_type_hint 接入过滤逻辑。
  - 传入 hint 时优先匹配 gp.device_type_hint == hint
  - 其次匹配 gp.device_type_hint == '' (兼容旧数据)
  - 排除冲突 hint (gp.hint != '' 且 gp.hint != hint)
  - 不传 hint 时行为不变 (匹配所有, 向后兼容)
"""


def _filter_by_hint(profiles_iter, device_type_hint):
    """两轮过滤 GameProfile 候选: 优先 hint 相同, 其次 hint 为空.

    Args:
        profiles_iter: GameProfile 迭代器 (已按 game_name 排序)
        device_type_hint: 'windows' / 'emulator' / None

    Returns:
        第一个匹配的 GameProfile, 或 None

    当 device_type_hint 为 None 时, 不过滤 (向后兼容).
    """
    if device_type_hint is None:
        # Legacy path: 不传 hint 时不过滤, 返回第一个 game_name 子串匹配的
        for gp in profiles_iter:
            yield gp
        return

    # 第一轮: 收集 hint 相同 + hint 为空的候选, 优先返回 hint 相同的
    same_hint_candidates = []
    empty_hint_candidates = []
    for gp in profiles_iter:
        if gp.device_type_hint == device_type_hint:
            same_hint_candidates.append(gp)
        elif not gp.device_type_hint:
            empty_hint_candidates.append(gp)
        # else: hint 冲突, 跳过

    # 优先 hint 相同的, 其次 hint 为空的
    for gp in same_hint_candidates:
        yield gp
    for gp in empty_hint_candidates:
        yield gp


def bind_game_profile_by_title(window_title: str, device_type_hint=None):
    """Match window_title to GameProfile.game_name (case-insensitive substring).

    Iterates all GameProfile rows and returns the first whose game_name appears
    as a substring of window_title (case-insensitive). Returns None if:
      - window_title is empty
      - GameProfile table is empty
      - no game_name matches (after hint filtering)

    Args:
        window_title: Window title string from agent report
        device_type_hint: Optional 'windows' / 'emulator'. When provided,
            filters candidates by GameProfile.device_type_hint:
            - Priority 1: gp.hint == device_type_hint
            - Priority 2: gp.hint == '' (legacy data, untyped)
            - Excluded: gp.hint conflicts with device_type_hint
            When None, no filtering (legacy behavior, backward compatible).

    Example:
        window_title="BrownDust II - Steam" → matches GameProfile(game_name="BrownDust II")
        window_title="BrownDust II", device_type_hint='windows'
            → prefers gp with hint='windows' over gp with hint=''

    Performance: O(profiles × 1) — fine for ~10 GameProfile rows.
    """
    if not window_title:
        return None

    # Lazy import to avoid circular dependency at module load time.
    from gamestate.models import GameProfile

    title_lower = window_title.lower()
    # TD-333: 先按 game_name 子串匹配, 再按 hint 过滤排序
    matched = [
        gp for gp in GameProfile.objects.all().order_by('game_name')
        if gp.game_name.lower() in title_lower
    ]
    for gp in _filter_by_hint(matched, device_type_hint):
        return gp
    return None


def bind_game_profile_by_target_app(target_app: str, device_type_hint=None):
    """Match ResourcePack.target_app to GameProfile.game_name.

    Similar to bind_game_profile_by_title but for ResourcePack.target_app field.
    Used in backfill when window_title is unavailable.

    Args:
        target_app: ResourcePack.target_app value
        device_type_hint: See bind_game_profile_by_title docstring.
    """
    if not target_app:
        return None

    from gamestate.models import GameProfile

    app_lower = target_app.lower()
    matched = []
    for gp in GameProfile.objects.all().order_by('game_name'):
        # Match either direction: target_app contains game_name OR
        # game_name contains target_app (handles "browndust2" vs "BrownDust II"
        # only when one is substring of the other; for full fuzzy match see below).
        if gp.game_name.lower() in app_lower or app_lower in gp.game_name.lower():
            matched.append(gp)
    for gp in _filter_by_hint(matched, device_type_hint):
        return gp
    return None


def backfill_game_profile_links() -> dict:
    """Backfill game_profile FK on existing Device/ResourcePack/Task rows.

    Best-effort: if GameProfile table is empty, returns zero counts without error.
    Idempotent: rows already having game_profile_id are skipped (user choice preserved).

    Returns:
        dict: {'devices': int, 'resource_packs': int, 'tasks': int} — count of
              rows updated by this call.
    """
    from agents.models import Device
    from gamestate.models import GameProfile
    from resources.models import ResourcePack
    from tasks.models import Task

    # If no GameProfile exists, backfill is a no-op (safe for first migrate).
    if not GameProfile.objects.exists():
        return {'devices': 0, 'resource_packs': 0, 'tasks': 0}

    device_count = 0
    for device in Device.objects.filter(game_profile__isnull=True):
        window_title = (device.extra_info or {}).get('window_title', '')
        # TD-333: 传 device.device_type 作为 hint, 避免 windows 设备误绑到
        # emulator 类型的 GameProfile (BD2 误绑事件根因)
        gp = bind_game_profile_by_title(window_title, device_type_hint=device.device_type)
        if gp:
            device.game_profile = gp
            device.save(update_fields=['game_profile'])
            device_count += 1

    resource_pack_count = 0
    for rp in ResourcePack.objects.filter(game_profile__isnull=True):
        # Try target_app first (most reliable for ResourcePack).
        # ResourcePack 无 device_type 信号, 不传 hint (沿用旧行为)
        gp = bind_game_profile_by_target_app(rp.target_app)
        if not gp:
            # Fallback: try name field (some packs have game in name).
            gp = bind_game_profile_by_title(rp.name)
        if gp:
            rp.game_profile = gp
            rp.save(update_fields=['game_profile'])
            resource_pack_count += 1

    task_count = 0
    for task in Task.objects.filter(game_profile__isnull=True):
        # Try first bound game_account's game name.
        # Task 无 device_type 信号, 不传 hint (沿用旧行为)
        game_account = task.game_accounts.first() if hasattr(task, 'game_accounts') else None
        if game_account:
            gp = bind_game_profile_by_title(game_account.game_name)
            if gp:
                task.game_profile = gp
                task.save(update_fields=['game_profile'])
                task_count += 1
                continue
        # Fallback: try task name.
        gp = bind_game_profile_by_title(task.name)
        if gp:
            task.game_profile = gp
            task.save(update_fields=['game_profile'])
            task_count += 1

    return {
        'devices': device_count,
        'resource_packs': resource_pack_count,
        'tasks': task_count,
    }
