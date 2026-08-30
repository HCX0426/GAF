"""自动按 game_profile 关联 GameAccount ↔ ResourcePack.

N194 fix (2026-07-28, BD2 资源包没绑定根因):
    TaskExecution.game_account.resource_pack 为 None 时, dispatch_task
    无法派发 resource_pack 给 agent, 导致 agent 用错资源包/模板找不到窗口.
    本命令按 GameAccount.game_profile 反查 ResourcePack.game_profile,
    自动补绑 resource_pack FK, 同时也修复 Device.game_profile 缺失.

触发场景:
    - 升级到 N194 后, 旧 GameAccount.resource_pack 全部为 None
    - 新增 GameProfile + ResourcePack 后, 旧 GameAccount 未自动绑定
    - 数据迁移 / 备份恢复后, FK 丢失

Usage:
    conda run -n gaf python manage.py bind_resource_packs            # 执行
    conda run -n gaf python manage.py bind_resource_packs --dry-run  # 预览
    conda run -n gaf python manage.py bind_resource_packs --include-devices  # 同时修 Device.game_profile
"""
from django.core.management.base import BaseCommand
from workers.models import Device

from accounts.models import GameAccount
from resources.models import ResourcePack


class Command(BaseCommand):
    help = '按 game_profile 自动关联 GameAccount ↔ ResourcePack (N194 fix)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只打印将要做的修改, 不实际写库',
        )
        parser.add_argument(
            '--include-devices',
            action='store_true',
            help='同时修复 Device.game_profile 缺失 (按 extra_info.window_title 反查)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        include_devices = options['include_devices']

        self.stdout.write(self.style.MIGRATE_HEADING(
            '=== N194 bind_resource_packs: GameAccount ↔ ResourcePack ==='
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] 不实际写库'))

        # Build GameProfile → ResourcePack index (one profile may map to
        # multiple ResourcePack versions; pick the latest active one).
        rp_by_profile = {}
        for rp in ResourcePack.objects.filter(is_active=True).order_by('-updated_at'):
            if rp.game_profile_id and rp.game_profile_id not in rp_by_profile:
                rp_by_profile[rp.game_profile_id] = rp
        self.stdout.write(f'已建立 GameProfile → ResourcePack 索引: '
                          f'{len(rp_by_profile)} 个 profile 有可用 ResourcePack')

        # Pass 1: GameAccount.resource_pack
        ga_bound = 0
        ga_skipped = 0
        ga_missing_profile = 0
        ga_missing_rp = 0
        for ga in GameAccount.objects.select_related('game_profile').all():
            if ga.resource_pack_id:
                ga_skipped += 1
                continue

            profile = ga.game_profile
            if not profile:
                ga_missing_profile += 1
                self.stdout.write(self.style.WARNING(
                    f'  [SKIP] GameAccount {ga.id} ({ga.username!r}): '
                    f'game_profile 为空, 无法自动匹配 (需用户手动绑定)'
                ))
                continue

            rp = rp_by_profile.get(profile.id)
            if not rp:
                ga_missing_rp += 1
                self.stdout.write(self.style.WARNING(
                    f'  [SKIP] GameAccount {ga.id} ({ga.username!r}): '
                    f'game_profile={profile.game_name!r} 无对应 ResourcePack'
                ))
                continue

            self.stdout.write(self.style.SUCCESS(
                f'  [BIND] GameAccount {ga.id} ({ga.username!r}) '
                f'← ResourcePack {rp.id} ({rp.name!r} v{rp.version}) '
                f'[profile={profile.game_name!r}]'
            ))
            if not dry_run:
                ga.resource_pack = rp
                ga.save(update_fields=['resource_pack', 'updated_at'])
            ga_bound += 1

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'GameAccount 汇总: 绑定={ga_bound}, 跳过(已有)={ga_skipped}, '
            f'缺 profile={ga_missing_profile}, 缺 RP={ga_missing_rp}'
        ))

        # Pass 2 (optional): Device.game_profile by window_title
        if include_devices:
            self.stdout.write('')
            self.stdout.write(self.style.MIGRATE_HEADING(
                '=== Pass 2: Device.game_profile (按 extra_info.window_title) ==='
            ))
            from workers.game_binding import bind_game_profile_by_title
            dev_bound = 0
            dev_skipped = 0
            for dev in Device.objects.all():
                if dev.game_profile_id:
                    dev_skipped += 1
                    continue
                wt = (dev.extra_info or {}).get('window_title', '') or ''
                if not wt:
                    self.stdout.write(self.style.WARNING(
                        f'  [SKIP] Device {dev.id} ({dev.name!r}): '
                        f'window_title 为空 (N194 修复 #2 上线后, agent 会自动上报)'
                    ))
                    continue
                gp = bind_game_profile_by_title(wt, device_type_hint=dev.device_type)
                if not gp:
                    self.stdout.write(self.style.WARNING(
                        f'  [SKIP] Device {dev.id} ({dev.name!r}): '
                        f'window_title={wt!r} 无匹配 GameProfile'
                    ))
                    continue
                self.stdout.write(self.style.SUCCESS(
                    f'  [BIND] Device {dev.id} ({dev.name!r}) '
                    f'← GameProfile {gp.id} ({gp.game_name!r}) [title={wt!r}]'
                ))
                if not dry_run:
                    dev.game_profile = gp
                    dev.save(update_fields=['game_profile', 'updated_at'])
                dev_bound += 1
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'Device 汇总: 绑定={dev_bound}, 跳过(已有)={dev_skipped}'
            ))

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                '[DRY-RUN] 完成 — 实际运行请去掉 --dry-run'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('完成.'))
