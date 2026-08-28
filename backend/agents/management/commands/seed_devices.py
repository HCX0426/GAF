"""
Seed 测试设备数据到数据库
用法: python manage.py seed_devices
"""
from django.core.management.base import BaseCommand

from agents.models import Device


class Command(BaseCommand):
    help = '向数据库插入测试设备数据'

    def handle(self, *args, **options):
        existing = Device.objects.count()
        if existing > 0:
            self.stdout.write(f'数据库中已有 {existing} 台设备，跳过 seed')
            return

        devices_data = [
            {
                'name': '雷电模拟器-主力',
                'device_type': Device.DeviceType.EMULATOR,
                'status': Device.Status.ONLINE,
                'resolution_width': 1920,
                'resolution_height': 1080,
                'screenshot_fps': 30,
                'adb_serial': '127.0.0.1:5555',
                'emulator': 'ldplayer',
                'extra_info': {'android_version': '12', 'cpu': 'Intel i7-12700', 'memory': '8GB'},
            },
            {
                'name': 'MuMu模拟器-备用',
                'device_type': Device.DeviceType.EMULATOR,
                'status': Device.Status.OFFLINE,
                'resolution_width': 1280,
                'resolution_height': 720,
                'screenshot_fps': 0,
                'adb_serial': '127.0.0.1:7555',
                'emulator': 'mumu',
                'extra_info': {'android_version': '9', 'cpu': '', 'memory': '4GB'},
            },
            {
                'name': 'Windows-主控',
                'device_type': Device.DeviceType.WINDOWS,
                'status': Device.Status.ONLINE,
                'resolution_width': 2560,
                'resolution_height': 1440,
                'screenshot_fps': 60,
                'window_handle': '0x123456',
                'extra_info': {'os': 'Windows 11', 'process_name': 'explorer.exe'},
            },
            {
                'name': 'ADB-物理机',
                'device_type': Device.DeviceType.ADB,
                'status': Device.Status.BUSY,
                'resolution_width': 1080,
                'resolution_height': 2400,
                'screenshot_fps': 15,
                'adb_serial': '192.168.1.100:5555',
                'extra_info': {'android_version': '13', 'manufacturer': 'Xiaomi', 'model': 'Mi 13'},
            },
            {
                'name': '夜神模拟器-测试',
                'device_type': Device.DeviceType.EMULATOR,
                'status': Device.Status.ONLINE,
                'resolution_width': 1600,
                'resolution_height': 900,
                'screenshot_fps': 24,
                'adb_serial': '127.0.0.1:62001',
                'emulator': 'nox',
                'extra_info': {'android_version': '7', 'cpu': 'AMD Ryzen 7', 'memory': '6GB'},
            },
        ]

        for data in devices_data:
            Device.objects.create(**data)

        self.stdout.write(self.style.SUCCESS(f'成功插入 {len(devices_data)} 台测试设备'))
