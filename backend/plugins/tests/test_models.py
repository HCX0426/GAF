"""Tests for plugins models: PluginHook, PluginPackage, PluginSandbox."""

from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from plugins.models import PluginHook, PluginPackage, PluginSandbox


class PluginHookModelTests(TestCase):
    """PluginHook model creation, defaults, __str__, constraints."""

    def test_create_with_defaults(self):
        """PluginHook created with only required fields gets sensible defaults."""
        hook = PluginHook.objects.create(
            plugin_name='test-plugin',
            event_type='on_task_start',
            hook_function='my_hook',
        )
        self.assertEqual(hook.priority, 0)
        self.assertTrue(hook.is_active)

    def test_str_representation(self):
        """__str__ includes plugin name, hook function and event type."""
        hook = PluginHook.objects.create(
            plugin_name='my-plugin',
            event_type='on_click',
            hook_function='before_click',
            priority=5,
        )
        self.assertEqual(str(hook), 'my-plugin.before_click [on_click]')

    def test_ordering_by_priority_desc(self):
        """PluginHook Meta ordering is -priority (highest first)."""
        PluginHook.objects.create(plugin_name='p', event_type='e', hook_function='h1', priority=1)
        PluginHook.objects.create(plugin_name='p', event_type='e', hook_function='h2', priority=10)
        PluginHook.objects.create(plugin_name='p', event_type='e', hook_function='h3', priority=5)
        hooks = list(PluginHook.objects.all())
        self.assertEqual(hooks[0].priority, 10)
        self.assertEqual(hooks[1].priority, 5)
        self.assertEqual(hooks[2].priority, 1)

    def test_unique_together_constraint(self):
        """Duplicate (plugin_name, event_type, hook_function) raises IntegrityError."""
        PluginHook.objects.create(
            plugin_name='dup', event_type='evt', hook_function='fn',
        )
        with self.assertRaises(IntegrityError):
            PluginHook.objects.create(
                plugin_name='dup', event_type='evt', hook_function='fn',
            )

    def test_same_hook_different_event_allowed(self):
        """Same plugin + function but different event_type is allowed."""
        PluginHook.objects.create(
            plugin_name='p', event_type='e1', hook_function='fn',
        )
        PluginHook.objects.create(
            plugin_name='p', event_type='e2', hook_function='fn',
        )
        self.assertEqual(PluginHook.objects.count(), 2)


class PluginPackageModelTests(TestCase):
    """PluginPackage model creation, defaults, __str__, uniqueness."""

    def test_create_with_defaults(self):
        """PluginPackage created with name + version gets default values."""
        pkg = PluginPackage.objects.create(name='demo', version='1.0.0')
        self.assertEqual(pkg.author, '')
        self.assertEqual(pkg.description, '')
        self.assertEqual(pkg.manifest, {})
        self.assertEqual(pkg.package_path, '')
        self.assertFalse(pkg.is_installed)
        self.assertFalse(pkg.is_active)
        self.assertIsNone(pkg.installed_at)
        self.assertEqual(pkg.checksum, '')
        self.assertIsNotNone(pkg.created_at)
        self.assertIsNotNone(pkg.updated_at)

    def test_str_representation(self):
        """__str__ shows name and version."""
        pkg = PluginPackage.objects.create(name='my-plugin', version='2.3.1')
        self.assertEqual(str(pkg), 'my-plugin v2.3.1')

    def test_name_unique(self):
        """PluginPackage name must be unique."""
        PluginPackage.objects.create(name='unique-pkg', version='1.0')
        with self.assertRaises(IntegrityError):
            PluginPackage.objects.create(name='unique-pkg', version='2.0')

    def test_ordering_by_created_at_desc(self):
        """PluginPackage Meta ordering is -created_at (newest first)."""
        first = PluginPackage.objects.create(name='a', version='1.0')
        # Force distinct timestamps (auto_now_add ignores explicit created_at on create)
        PluginPackage.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(seconds=10),
        )
        second = PluginPackage.objects.create(name='b', version='1.0')
        pkgs = list(PluginPackage.objects.all())
        self.assertEqual(pkgs[0], second)
        self.assertEqual(pkgs[1], first)


class PluginSandboxModelTests(TestCase):
    """PluginSandbox model creation, defaults, __str__, FK cascade."""

    def setUp(self):
        self.pkg = PluginPackage.objects.create(name='sandbox-pkg', version='1.0.0')

    def test_create_with_defaults(self):
        """PluginSandbox created with only plugin gets default status idle."""
        sb = PluginSandbox.objects.create(plugin=self.pkg)
        self.assertEqual(sb.status, 'idle')
        self.assertIsNone(sb.pid)
        self.assertIsNotNone(sb.created_at)

    def test_str_representation(self):
        """__str__ includes plugin name and status."""
        sb = PluginSandbox.objects.create(plugin=self.pkg, pid=12345, status='running')
        self.assertEqual(str(sb), 'Sandbox(sandbox-pkg) [running]')

    def test_status_choices(self):
        """All four status choices can be stored."""
        for s in ('idle', 'running', 'stopped', 'error'):
            PluginSandbox.objects.create(plugin=self.pkg, status=s)
        self.assertEqual(PluginSandbox.objects.count(), 4)

    def test_cascade_delete_on_plugin(self):
        """Deleting a PluginPackage cascades to its sandboxes."""
        sb = PluginSandbox.objects.create(plugin=self.pkg, status='running')
        self.pkg.delete()
        self.assertFalse(PluginSandbox.objects.filter(pk=sb.pk).exists())

    def test_related_name_sandboxes(self):
        """PluginPackage.sandboxes related_name works."""
        PluginSandbox.objects.create(plugin=self.pkg, status='running')
        PluginSandbox.objects.create(plugin=self.pkg, status='idle')
        self.assertEqual(self.pkg.sandboxes.count(), 2)
