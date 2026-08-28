"""
Management command to migrate/import resource packs.

Usage:
    python manage.py migrate_resource_pack <path> [--activate] [--deep-import]
    python manage.py migrate_resource_pack --default [--deep-import]
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from resources.import_utils import migrate_resource_pack


class Command(BaseCommand):
    help = '导入资源包到数据库（支持 --default 导入默认资源包）'

    def add_arguments(self, parser):
        parser.add_argument(
            'path',
            nargs='?',
            help='资源包目录路径（省略时需指定 --default）',
        )
        parser.add_argument(
            '--default',
            action='store_true',
            help='导入 GAF 默认资源包（resources/default/）',
        )
        parser.add_argument(
            '--activate',
            action='store_true',
            help='导入后自动激活资源包（--default 模式下始终激活）',
        )
        parser.add_argument(
            '--deep-import',
            action='store_true',
            help='深度导入：同时导入 pipelines/tasks/templates/monitors/config',
        )

    def handle(self, *args, **options):
        if options['default']:
            base_dir = Path(settings.BASE_DIR)
            default_pack_path = base_dir / 'resources' / 'default'
            if not default_pack_path.is_dir():
                raise CommandError(f'默认资源包目录不存在: {default_pack_path}')
            pack_path = str(default_pack_path)
            should_activate = True
        elif options['path']:
            pack_path = options['path']
            should_activate = options['activate']
        else:
            raise CommandError('请指定资源包路径或使用 --default')

        self.stdout.write(self.style.MIGRATE_HEADING(f'开始导入资源包: {pack_path}'))
        result = migrate_resource_pack(pack_path, activate=should_activate, deep_import=options['deep_import'])
        self.stdout.write(self.style.SUCCESS('导入结果:'))
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))
