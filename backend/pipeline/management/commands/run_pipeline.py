"""run_pipeline command — execute a Pipeline via dispatch_task (spec-2026-08-02).

Usage:
    conda run -n gaf python backend/manage.py run_pipeline <pipeline_id> [--device <device_id>] [--agent <agent_id>] [--wait]

The command creates a TaskExecution (task=None, pipeline FK) and dispatches
it through the unified dispatch_task path — same as PipelineViewSet.execute.
With --wait, it polls the execution status every 5s and prints the result.
"""

import time
import uuid

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Execute a Pipeline via dispatch_task (unified execution path)'

    def add_arguments(self, parser):
        parser.add_argument('pipeline_id', type=int, help='Pipeline ID to execute')
        parser.add_argument('--device', type=int, default=None, help='Device ID (auto-detect if omitted)')
        parser.add_argument('--agent', type=str, default=None, help='Agent ID (auto-pick if omitted)')
        parser.add_argument('--wait', action='store_true', default=False, help='Wait for execution to complete')

    def handle(self, *args, **options):
        pipeline_id = options['pipeline_id']
        device_id = options['device']
        agent_id = options['agent']
        wait = options['wait']

        from workers.models import Device

        from pipeline.models import Pipeline
        from tasks.models import TaskExecution

        try:
            pipeline = Pipeline.objects.get(pk=pipeline_id)
        except Pipeline.DoesNotExist as exc:
            raise CommandError(f'Pipeline {pipeline_id} 不存在') from exc

        # Resolve agent (B1 2026-08-27: shared resolver — same selection
        # semantics as TaskViewSet.execute / PipelineViewSet.execute).
        from tasks.services.worker_resolver import resolve_online_worker

        agent = resolve_online_worker(agent_id)
        if not agent:
            hint = f'Worker {agent_id} 不存在或不在线' if agent_id else '没有在线 Worker'
            self.stderr.write(hint)
            return

        # Resolve device
        device = None
        if device_id:
            try:
                device = Device.objects.get(pk=device_id)
            except Device.DoesNotExist:
                self.stderr.write(f'Device {device_id} 不存在')
                return
        else:
            device = Device.objects.filter(
                agent=agent, status='online',
            ).exclude(device_type='adb').exclude(device_type='emulator').first()
            if device:
                self.stdout.write(f'自动检测设备: {device.name} (id={device.id})')
            else:
                self.stdout.write('未找到可用设备，执行将无设备绑定')

        # Create TaskExecution
        execution = TaskExecution.objects.create(
            task=None,
            pipeline=pipeline,
            agent=agent,
            device=device,
            status=TaskExecution.Status.PENDING,
            trace_id=str(uuid.uuid4()),
        )
        self.stdout.write(f'已创建 Execution #{execution.id} (Pipeline: {pipeline.name})')

        # Dispatch
        from tasks.tasks import dispatch_task
        dispatch_task.delay(execution.id, trace_id=str(uuid.uuid4()))

        if not wait:
            self.stdout.write(f'已分发，执行 ID: {execution.id}')
            self.stdout.write(f'查看状态: curl http://localhost:8000/api/v2/tasks/task-executions/{execution.id}/')
            return

        # Wait for completion
        self.stdout.write('等待执行完成...')
        timeout = 600  # 10 minutes max
        poll_interval = 5
        start_time = time.time()

        while time.time() - start_time < timeout:
            execution.refresh_from_db()
            status = execution.status
            if status == TaskExecution.Status.RUNNING:
                self.stdout.write(f'  ... 执行中 ({int(time.time() - start_time)}s)', ending='\r')
            elif status == TaskExecution.Status.SUCCESS:
                self.stdout.write(f'\n✅ 执行成功 ({int(time.time() - start_time)}s)')
                self.stdout.write(f'   Agent: {execution.agent.agent_id if execution.agent else "N/A"}')
                self.stdout.write(f'   Device: {execution.device.name if execution.device else "N/A"}')
                if execution.trace_id:
                    self.stdout.write(f'   Trace ID: {execution.trace_id}')
                self.stdout.write(f'   日志目录: {getattr(execution, "debug_dir", "")}')
                return
            elif status in (TaskExecution.Status.FAILED, TaskExecution.Status.CANCELLED):
                self.stdout.write(f'\n❌ 执行失败 ({int(time.time() - start_time)}s)')
                self.stdout.write(f'   状态: {status}')
                self.stdout.write(f'   错误: {execution.error_message or "未知错误"}')
                return
            else:
                self.stdout.write(f'  ... 状态={status} ({int(time.time() - start_time)}s)', ending='\r')
            time.sleep(poll_interval)

        self.stderr.write(f'\n⏰ 等待超时 ({timeout}s)，执行仍在进行中')
        self.stderr.write(f'   查看状态: curl http://localhost:8000/api/v2/tasks/task-executions/{execution.id}/')
