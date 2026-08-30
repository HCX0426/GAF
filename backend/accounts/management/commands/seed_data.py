"""
种子数据管理命令，用于快速填充开发环境数据库。
用法: python manage.py seed_data
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from scheduler.models import RecoveryLog

from accounts.models import User
from agents.models import Agent, Device, DeviceGroup
from monitors.models import MonitorEvent, MonitorRule
from notifications.models import Notification
from resources.models import ResourcePack
from tasks.models import Task, TaskExecution, ExecutionStep


class Command(BaseCommand):
    help = '填充开发环境种子数据（用户、设备、任务、通知、监控、恢复日志等）'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('=== 开始填充种子数据 ==='))

        users = self._create_users()
        self._create_game_profiles()
        resource_pack = self._create_resource_pack()
        agents = self._create_agents()
        devices = self._create_devices(agents)
        self._create_device_groups(devices)
        tasks = self._create_tasks(resource_pack)
        executions = self._create_executions(tasks, agents)
        self._create_task_steps(executions)
        self._create_notifications(users)
        self._create_monitor_events(agents)
        self._create_monitor_rules()
        self._create_recovery_logs()

        # R37-P1: re-run backfill after all seed data is in place to link
        # Device/ResourcePack/Task rows to their GameProfile by window_title /
        # target_app / game_account.game_name. Safe no-op if GameProfile empty.
        from agents.game_binding import backfill_game_profile_links
        backfill_counts = backfill_game_profile_links()
        self.stdout.write(self.style.SUCCESS(
            f'  R37-P1 backfill: devices={backfill_counts["devices"]} '
            f'resource_packs={backfill_counts["resource_packs"]} '
            f'tasks={backfill_counts["tasks"]}'
        ))

        self.stdout.write(self.style.SUCCESS('\n种子数据填充完成！'))
        self.stdout.write('  用户: admin/123 (管理员), operator/operator123 (操作员)')
        self.stdout.write(f'  设备: {len(devices)} 台')
        self.stdout.write(f'  任务: {len(tasks)} 个')
        self.stdout.write(f'  执行记录: {len(executions)} 条')
        self.stdout.write(f'  监控事件: {MonitorEvent.objects.count()} 条')
        self.stdout.write(f'  恢复日志: {RecoveryLog.objects.count()} 条')

    def _create_game_profiles(self):
        """R37-P1: seed GameProfile rows for known games.

        Idempotent via get_or_create. Screenshot method values MUST match the
        frontend options in GameProfilesPage.tsx (bitblt/dxgi_dupl/wgc/gdi).
        """
        from gamestate.models import GameProfile

        profiles_data = [
            {
                'game_name': 'BrownDust II',
                'defaults': {
                    'screenshot_methods': ['bitblt', 'dxgi_dupl', 'wgc', 'gdi'],
                    'ocr_language': 'ch',
                    'ui_reference_resolution': {'w': 1920, 'h': 1080},
                    'resolution_strategy': 'scale',
                },
            },
        ]
        created_profiles = []
        for entry in profiles_data:
            profile, created = GameProfile.objects.get_or_create(
                game_name=entry['game_name'],
                defaults=entry['defaults'],
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'  创建游戏档案: {profile.game_name}'
                ))
            created_profiles.append(profile)
        return created_profiles

    def _create_users(self):
        users = []

        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@gaf.local',
                'role': User.Role.ADMIN,
                'is_staff': True,
                'is_superuser': True,
                'must_change_password': False,
            },
        )
        admin.set_password('123')
        admin.save()
        if created:
            self.stdout.write(self.style.SUCCESS('  创建管理员: admin/123'))
        else:
            self.stdout.write(self.style.WARNING('  管理员已存在，密码已更新'))
        users.append(admin)

        operator, created = User.objects.get_or_create(
            username='operator',
            defaults={
                'email': 'operator@gaf.local',
                'role': User.Role.OPERATOR,
                'is_staff': False,
                'is_superuser': False,
            },
        )
        operator.set_password('operator123')
        operator.save()
        if created:
            self.stdout.write(self.style.SUCCESS('  创建操作员: operator/operator123'))
        else:
            self.stdout.write(self.style.WARNING('  操作员已存在，跳过'))
        users.append(operator)

        return users

    def _create_resource_pack(self):
        pack, created = ResourcePack.objects.get_or_create(
            name='GAF 默认资源包',
            version='1.0.0',
            defaults={
                'target_app': '通用',
                'author': 'GAF Team',
                'directory_path': '/resources/default',
                'is_active': True,
                'description': 'GAF 项目默认资源包，包含通用模板和配置。',
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS('  创建资源包: GAF 默认资源包 v1.0.0'))
        return pack

    def _create_agents(self):
        agent_data = [
            {
                'agent_id': 'agent-windows-001',
                'hostname': 'GAF-Workstation',
                'ip_address': '192.168.1.100',
                'os_info': 'Windows 11 Pro 24H2',
                'status': Agent.Status.ONLINE,
                'is_local': True,
                'capabilities': {'wgc': True, 'ocr': 'rapid', 'onnx': True},
            },
            {
                'agent_id': 'agent-adb-001',
                'hostname': 'GAF-Android',
                'ip_address': '192.168.1.101',
                'os_info': 'Android 14',
                'status': Agent.Status.ONLINE,
                'is_local': False,
                'capabilities': {'adb': True, 'scrcpy': True},
            },
        ]

        agents = []
        for data in agent_data:
            agent, created = Agent.objects.get_or_create(
                agent_id=data['agent_id'],
                defaults={
                    'hostname': data['hostname'],
                    'ip_address': data['ip_address'],
                    'os_info': data['os_info'],
                    'status': data['status'],
                    'is_local': data['is_local'],
                    'capabilities': data['capabilities'],
                    'last_heartbeat': timezone.now(),
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  创建 Agent: {agent.hostname}'))
            agents.append(agent)
        return agents

    def _create_devices(self, agents):
        device_data = [
            {
                'name': '主工作站屏幕',
                'device_type': Device.DeviceType.WINDOWS,
                'status': Device.Status.ONLINE,
                'agent': agents[0],
                'resolution_width': 1920,
                'resolution_height': 1080,
                'screenshot_fps': 30,
            },
            {
                'name': '雷电模拟器 #1',
                'device_type': Device.DeviceType.EMULATOR,
                'status': Device.Status.ONLINE,
                'agent': agents[1],
                'resolution_width': 1280,
                'resolution_height': 720,
                'screenshot_fps': 20,
            },
            {
                'name': 'Pixel 7 (ADB)',
                'device_type': Device.DeviceType.EMULATOR,
                'status': Device.Status.ONLINE,
                'agent': agents[1],
                'resolution_width': 1080,
                'resolution_height': 2400,
                'screenshot_fps': 15,
            },
        ]

        devices = []
        for data in device_data:
            device, created = Device.objects.get_or_create(
                name=data['name'],
                agent=data['agent'],
                defaults={
                    'device_type': data['device_type'],
                    'status': data['status'],
                    'resolution_width': data['resolution_width'],
                    'resolution_height': data['resolution_height'],
                    'screenshot_fps': data['screenshot_fps'],
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  创建设备: {device.name}'))
            devices.append(device)
        return devices

    def _create_device_groups(self, devices):
        admin = User.objects.get(username='admin')
        group, created = DeviceGroup.objects.get_or_create(
            name='自动化集群',
            user=admin,
        )
        if created:
            group.devices.add(*devices[:2])
            self.stdout.write(self.style.SUCCESS(f'  创建设备组: {group.name} (含 2 台设备)'))

    def _create_tasks(self, resource_pack):
        task_data = [
            {
                'name': '每日签到任务',
                'description': '自动登录游戏并完成每日签到，领取奖励物品。',
                'execution_mode': Task.ExecutionMode.PIPELINE,
                'task_definition': {
                    'nodes': [
                        {'id': '启动游戏', 'node_type': 'device_control', 'config': {'action': 'launch_app'}},
                        {'id': '等待加载', 'node_type': 'wait', 'config': {'seconds': 3}, 'retry': {'max_retries': 3}},
                        {'id': '点击签到', 'node_type': 'template_match', 'config': {'template_id': 'sign_btn'}},
                        {'id': '确认领取', 'node_type': 'template_match', 'config': {'template_id': 'confirm_btn'}},
                        {'id': '关闭弹窗', 'node_type': 'template_match', 'config': {'template_id': 'close_btn'}},
                    ],
                },
                'tags': ['每日', '签到', '自动化'],
            },
            {
                'name': '副本扫荡',
                'description': '自动进入指定副本并扫荡，完成后返回主界面。',
                'execution_mode': Task.ExecutionMode.STATE_MACHINE,
                'task_definition': {
                    'nodes': [
                        {'id': '进入副本', 'node_type': 'template_match', 'config': {'template_id': 'dungeon_btn'}},
                        {'id': '选择难度', 'node_type': 'template_match', 'config': {'template_id': 'difficulty_select'}},
                        {'id': '开始战斗', 'node_type': 'template_match', 'config': {'template_id': 'battle_start'}},
                        {'id': '战斗结算', 'node_type': 'template_match', 'config': {'template_id': 'battle_result'}},
                        {'id': '返回主界面', 'node_type': 'template_match', 'config': {'template_id': 'home_btn'}},
                    ],
                },
                'tags': ['副本', '战斗', '自动化'],
            },
            {
                'name': '资源采集',
                'description': '自动采集地图上的可采集资源点。',
                'execution_mode': Task.ExecutionMode.PIPELINE,
                'task_definition': {
                    'nodes': [
                        {'id': '打开地图', 'node_type': 'template_match', 'config': {'template_id': 'map_btn'}},
                        {'id': '定位资源点', 'node_type': 'ocr', 'config': {}},
                        {'id': '采集资源', 'node_type': 'template_match', 'config': {'template_id': 'collect_btn'}},
                    ],
                },
                'tags': ['采集', '资源', '自动化'],
            },
        ]

        tasks = []
        for data in task_data:
            # R37-P0: Task.resource_pack FK was removed in migration 0022.
            # Lookup by name only; resource_pack linkage now goes through GameAccount.
            task, created = Task.objects.get_or_create(
                name=data['name'],
                defaults={
                    'description': data['description'],
                    'execution_mode': data['execution_mode'],
                    'task_definition': data['task_definition'],
                    'tags': data['tags'],
                    'is_enabled': True,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  创建任务: {task.name}'))
            tasks.append(task)
        return tasks

    def _create_executions(self, tasks, agents):
        now = timezone.now()
        exec_data = [
            {
                'task': tasks[0],
                'agent': agents[0],
                'status': TaskExecution.Status.SUCCESS,
                'started_at': now - timezone.timedelta(hours=2),
                'completed_at': now - timezone.timedelta(hours=2) + timezone.timedelta(minutes=3),
                'duration': timezone.timedelta(minutes=3),
            },
            {
                'task': tasks[1],
                'agent': agents[1],
                'status': TaskExecution.Status.FAILED,
                'error_message': '战斗结算超时：等待模板 battle_result 未出现',
                'started_at': now - timezone.timedelta(hours=1),
                'completed_at': now - timezone.timedelta(hours=1) + timezone.timedelta(minutes=8),
                'duration': timezone.timedelta(minutes=8),
            },
            {
                'task': tasks[2],
                'agent': agents[0],
                'status': TaskExecution.Status.SUCCESS,
                'started_at': now - timezone.timedelta(minutes=30),
                'completed_at': now - timezone.timedelta(minutes=30) + timezone.timedelta(minutes=5),
                'duration': timezone.timedelta(minutes=5),
            },
            {
                'task': tasks[0],
                'agent': agents[1],
                'status': TaskExecution.Status.SUCCESS,
                'started_at': now - timezone.timedelta(hours=5),
                'completed_at': now - timezone.timedelta(hours=5) + timezone.timedelta(minutes=4),
                'duration': timezone.timedelta(minutes=4),
            },
            {
                'task': tasks[1],
                'agent': agents[0],
                'status': TaskExecution.Status.CANCELLED,
                'started_at': now - timezone.timedelta(hours=3),
                'completed_at': now - timezone.timedelta(hours=3) + timezone.timedelta(minutes=2),
                'duration': timezone.timedelta(minutes=2),
            },
        ]

        executions = []
        for data in exec_data:
            execution = TaskExecution.objects.create(
                task=data['task'],
                agent=data['agent'],
                status=data['status'],
                error_message=data.get('error_message', ''),
                started_at=data['started_at'],
                completed_at=data['completed_at'],
                duration=data['duration'],
            )
            self.stdout.write(self.style.SUCCESS(
                f'  创建执行记录: {execution.task.name} [{execution.get_status_display()}]'
            ))
            executions.append(execution)
        return executions

    def _create_task_steps(self, executions):
        step_templates = {
            '每日签到任务': [
                ('启动游戏', 'launch_app', 'success', 3.2, 0),
                ('等待加载', 'wait', 'success', 8.5, 0),
                ('点击签到', 'click_template', 'success', 4.1, 0),
                ('确认领取', 'click_template', 'success', 2.0, 0),
                ('关闭弹窗', 'click_template', 'success', 1.5, 0),
            ],
            '副本扫荡': [
                ('进入副本', 'click_template', 'success', 5.0, 0),
                ('选择难度', 'click_template', 'success', 3.0, 0),
                ('开始战斗', 'click_template', 'success', 2.0, 0),
                ('战斗结算', 'wait_template', 'failed', 30.0, 1),
                ('返回主界面', 'click_template', 'skipped', 0, 0),
            ],
            '资源采集': [
                ('打开地图', 'click_template', 'success', 2.5, 0),
                ('定位资源点', 'ocr_detect', 'success', 6.0, 0),
                ('采集资源', 'click_template', 'success', 3.0, 0),
            ],
        }

        for _i, execution in enumerate(executions):
            task_name = execution.task.name
            steps = step_templates.get(task_name, [])
            for idx, (name, stype, status, duration_s, retries) in enumerate(steps):
                started_at = execution.started_at + timezone.timedelta(seconds=sum(
                    s[3] for s in steps[:idx]
                ))
                ExecutionStep.objects.create(
                    task_result=execution,
                    step_index=idx,
                    step_name=name,
                    step_type=stype,
                    status=status,
                    started_at=started_at,
                    duration=timezone.timedelta(seconds=duration_s),
                    retry_count=retries,
                    error_message='战斗结算超时：等待模板 battle_result 未出现' if status == 'failed' else '',
                )
        self.stdout.write(self.style.SUCCESS(f'  创建任务步骤: {sum(len(steps) for steps in step_templates.values())} 条'))

    def _create_monitor_events(self, agents):
        now = timezone.now()
        events_data = [
            {
                'event_type': 'heartbeat_timeout',
                'handling_result': '设备「雷电模拟器 #1」Agent 心跳超时 (>120s)，可能已离线',
                'event_data': {'device': '雷电模拟器 #1', 'timeout_s': 125},
                'agent': agents[1],
                'created_at': now - timezone.timedelta(minutes=5),
            },
            {
                'event_type': 'login_about_to_expire',
                'handling_result': '账户「小号-阿强」登录态即将过期，建议刷新',
                'event_data': {'account': '小号-阿强', 'expires_in_hours': 2},
                'agent': agents[0],
                'created_at': now - timezone.timedelta(minutes=20),
            },
            {
                'event_type': 'template_file_changed',
                'handling_result': '资源包「GAF 默认资源包」模板文件检测到变更',
                'event_data': {'pack': 'GAF 默认资源包', 'changed_files': 3},
                'agent': None,
                'created_at': now - timezone.timedelta(hours=2),
            },
            {
                'event_type': 'step_timeout_warning',
                'handling_result': '执行步骤耗时超过阈值 (180s > 120s)',
                'event_data': {'step': '副本扫荡', 'duration_s': 180, 'threshold_s': 120},
                'agent': agents[1],
                'created_at': now - timezone.timedelta(hours=3),
            },
            {
                'event_type': 'screenshot_all_black',
                'handling_result': '设备截图连续 5 次全黑，可能模拟器崩溃',
                'event_data': {'device': 'Pixel 7', 'black_count': 5},
                'agent': agents[1],
                'created_at': now - timezone.timedelta(hours=4),
            },
            {
                'event_type': 'task_failed',
                'handling_result': '副本扫荡执行失败: 战斗结算超时',
                'event_data': {'task': '副本扫荡', 'error': '战斗结算超时'},
                'agent': agents[1],
                'created_at': now - timezone.timedelta(hours=1),
            },
            {
                'event_type': 'agent_reconnected',
                'handling_result': 'Agent GAF-Workstation 已恢复连接',
                'event_data': {'agent': 'GAF-Workstation', 'offline_duration': '3m 42s'},
                'agent': agents[0],
                'created_at': now - timezone.timedelta(hours=6),
            },
        ]

        for data in events_data:
            MonitorEvent.objects.create(**data)
        self.stdout.write(self.style.SUCCESS(f'  创建监控事件: {len(events_data)} 条'))

    def _create_monitor_rules(self):
        resource_pack = ResourcePack.objects.first()
        rules_data = [
            {
                'name': 'Agent 心跳超时检测',
                'rule_definition': {
                    'type': 'heartbeat',
                    'condition': 'timeout_s > 120',
                    'field': 'heartbeat',
                    'operator': 'gt',
                    'threshold_value': '120',
                    'severity': 'critical',
                    'notification': True,
                },
                'is_enabled': True,
            },
            {
                'name': '步骤执行超时告警',
                'rule_definition': {
                    'type': 'step_duration',
                    'condition': 'duration_s > threshold_s * 1.5',
                    'field': 'step_duration',
                    'operator': 'gt',
                    'threshold_value': '1.5',
                    'severity': 'warning',
                    'notification': False,
                },
                'is_enabled': True,
            },
            {
                'name': '连续失败检测',
                'rule_definition': {
                    'type': 'consecutive_failures',
                    'condition': 'fail_count >= 3',
                    'field': 'fail_count',
                    'operator': 'gte',
                    'threshold_value': '3',
                    'severity': 'critical',
                    'notification': True,
                },
                'is_enabled': True,
            },
        ]

        for data in rules_data:
            MonitorRule.objects.get_or_create(
                name=data['name'],
                resource_pack=resource_pack,
                defaults={'rule_definition': data['rule_definition'], 'is_enabled': data['is_enabled']},
            )
        self.stdout.write(self.style.SUCCESS(f'  创建监控规则: {len(rules_data)} 条'))

    def _create_recovery_logs(self):
        now = timezone.now()
        logs_data = [
            {
                'recovery_level': 'step',
                'trigger_event': 'click_timeout',
                'action_taken': 'retry_click',
                'success': True,
                'details': {'device': 'GAF-Workstation', 'step': '点击签到', 'attempt': 2},
                'created_at': now - timezone.timedelta(hours=6),
            },
            {
                'recovery_level': 'task',
                'trigger_event': 'consecutive_failures',
                'action_taken': 'switch_account',
                'success': True,
                'details': {'device': 'Pixel 7', 'task': '副本扫荡', 'from_account': '主号', 'to_account': '小号'},
                'created_at': now - timezone.timedelta(hours=4),
            },
            {
                'recovery_level': 'app',
                'trigger_event': 'game_freeze_detected',
                'action_taken': 'restart_game',
                'success': True,
                'details': {'device': '雷电模拟器 #1', 'freeze_duration': '120s'},
                'created_at': now - timezone.timedelta(hours=3),
            },
            {
                'recovery_level': 'device',
                'trigger_event': 'adb_disconnected',
                'action_taken': 'reconnect_adb',
                'success': False,
                'details': {'device': 'Pixel 7', 'error': 'device not found'},
                'created_at': now - timezone.timedelta(hours=2),
            },
            {
                'recovery_level': 'system',
                'trigger_event': 'agent_no_response',
                'action_taken': 'mark_offline_notify',
                'success': True,
                'details': {'agent': 'GAF-Android', 'offline_since': (now - timezone.timedelta(minutes=15)).isoformat()},
                'created_at': now - timezone.timedelta(minutes=15),
            },
        ]

        for data in logs_data:
            RecoveryLog.objects.create(**data)
        self.stdout.write(self.style.SUCCESS(f'  创建恢复日志: {len(logs_data)} 条'))

    def _create_notifications(self, users):
        admin_user = users[0]
        notification_data = [
            {
                'user': admin_user,
                'title': '系统已就绪',
                'body': 'GAF V2 开发环境已成功启动，所有模块运行正常。',
                'category': 'system',
                'is_read': True,
            },
            {
                'user': admin_user,
                'title': 'Agent 上线通知',
                'body': 'Agent GAF-Workstation 已成功连接并完成注册。',
                'category': 'agent',
                'is_read': False,
            },
            {
                'user': admin_user,
                'title': '任务执行完成',
                'body': '每日签到任务 执行成功，用时 45 秒。',
                'category': 'task',
                'is_read': False,
                'link': '/executions',
            },
            {
                'user': admin_user,
                'title': '任务执行失败',
                'body': '副本扫荡 执行失败，错误：战斗结算超时。',
                'category': 'task',
                'is_read': False,
                'link': '/executions',
            },
        ]

        for data in notification_data:
            notification, created = Notification.objects.get_or_create(
                user=data['user'],
                title=data['title'],
                defaults={
                    'body': data['body'],
                    'category': data['category'],
                    'is_read': data['is_read'],
                    'link': data.get('link', ''),
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  创建通知: {notification.title}'))
