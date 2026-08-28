"""Tests for pipeline.models (model layer, DB-backed).

Models under test: Pipeline, PipelineSnapshot, TaskChain, TaskChainNode,
Recording.
"""

from django.test import TestCase

from accounts.models import User
from pipeline.models import (
    Pipeline,
    PipelineSnapshot,
    Recording,
    TaskChain,
    TaskChainNode,
)
from tasks.models import Task


class PipelineModelTests(TestCase):
    """Pipeline model: creation, defaults, __str__, ordering, FK."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='pipe_model_user', password='Pass123!',
        )

    def test_create_pipeline_with_defaults(self):
        pipe = Pipeline.objects.create(name='Test Pipeline', user=self.user)
        self.assertEqual(pipe.description, '')
        self.assertEqual(pipe.graph_data, {})
        self.assertEqual(pipe.version, 1)
        self.assertFalse(pipe.is_template)
        self.assertEqual(pipe.estimated_duration_ms, 0)
        self.assertIsNotNone(pipe.created_at)
        self.assertIsNotNone(pipe.updated_at)

    def test_str_includes_name_and_version(self):
        pipe = Pipeline.objects.create(name='My Pipeline', user=self.user, version=3)
        self.assertEqual(str(pipe), 'My Pipeline (v3)')

    def test_str_default_version(self):
        pipe = Pipeline.objects.create(name='Default', user=self.user)
        self.assertEqual(str(pipe), 'Default (v1)')

    def test_graph_data_custom(self):
        graph = {'nodes': [{'id': 'n1'}], 'edges': []}
        pipe = Pipeline.objects.create(name='Graph', user=self.user, graph_data=graph)
        pipe.refresh_from_db()
        self.assertEqual(pipe.graph_data, graph)

    def test_sub_pipeline_self_reference(self):
        parent = Pipeline.objects.create(name='Parent', user=self.user)
        child = Pipeline.objects.create(
            name='Child', user=self.user, sub_pipeline=parent,
        )
        self.assertEqual(child.sub_pipeline, parent)
        self.assertIn(child, parent.used_by_pipelines.all())

    def test_sub_pipeline_null_by_default(self):
        pipe = Pipeline.objects.create(name='No Sub', user=self.user)
        self.assertIsNone(pipe.sub_pipeline)

    def test_user_related_name(self):
        pipe = Pipeline.objects.create(name='Rel', user=self.user)
        self.assertIn(pipe, self.user.pipelines.all())

    def test_cascade_delete_user_deletes_pipeline(self):
        pipe = Pipeline.objects.create(name='Cascade', user=self.user)
        pipe_id = pipe.id
        self.user.delete()
        self.assertFalse(Pipeline.objects.filter(id=pipe_id).exists())

    def test_ordering_by_updated_at_desc(self):
        import time
        Pipeline.objects.create(name='P1', user=self.user)
        time.sleep(0.01)
        Pipeline.objects.create(name='P2', user=self.user)
        names = list(Pipeline.objects.values_list('name', flat=True))
        self.assertEqual(names[0], 'P2')


class PipelineSnapshotModelTests(TestCase):
    """PipelineSnapshot model: creation, __str__, FK cascade."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='snap_user', password='Pass123!',
        )
        self.pipeline = Pipeline.objects.create(
            name='Snap Pipeline', user=self.user,
            graph_data={'nodes': [], 'edges': []},
        )

    def test_create_snapshot(self):
        snap = PipelineSnapshot.objects.create(
            pipeline=self.pipeline, version=1,
            graph_data={'nodes': [], 'edges': []},
            change_summary='initial',
        )
        self.assertEqual(snap.version, 1)
        self.assertEqual(snap.change_summary, 'initial')

    def test_str_representation(self):
        snap = PipelineSnapshot.objects.create(
            pipeline=self.pipeline, version=2,
            graph_data={'nodes': []},
        )
        self.assertEqual(str(snap), 'Snap Pipeline snapshot v2')

    def test_snapshot_related_name(self):
        snap = PipelineSnapshot.objects.create(
            pipeline=self.pipeline, version=1,
            graph_data={},
        )
        self.assertIn(snap, self.pipeline.snapshots.all())

    def test_cascade_delete_pipeline_deletes_snapshots(self):
        snap = PipelineSnapshot.objects.create(
            pipeline=self.pipeline, version=1, graph_data={},
        )
        snap_id = snap.id
        self.pipeline.delete()
        self.assertFalse(PipelineSnapshot.objects.filter(id=snap_id).exists())

    def test_change_summary_default_empty(self):
        snap = PipelineSnapshot.objects.create(
            pipeline=self.pipeline, version=1, graph_data={},
        )
        self.assertEqual(snap.change_summary, '')

    def test_ordering_by_version_desc(self):
        PipelineSnapshot.objects.create(pipeline=self.pipeline, version=1, graph_data={})
        PipelineSnapshot.objects.create(pipeline=self.pipeline, version=3, graph_data={})
        PipelineSnapshot.objects.create(pipeline=self.pipeline, version=2, graph_data={})
        versions = list(PipelineSnapshot.objects.values_list('version', flat=True))
        self.assertEqual(versions, [3, 2, 1])


class TaskChainModelTests(TestCase):
    """TaskChain model: creation, defaults, __str__, has_circular_dependency."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='chain_user', password='Pass123!',
        )
        self.task = Task.objects.create(name='Chain Task')

    def test_create_task_chain_with_defaults(self):
        chain = TaskChain.objects.create(name='My Chain')
        self.assertEqual(chain.description, '')
        self.assertEqual(chain.dag_data, {})
        self.assertTrue(chain.is_enabled)
        self.assertIsNone(chain.created_by)

    def test_str_representation(self):
        chain = TaskChain.objects.create(name='DAG Chain')
        self.assertEqual(str(chain), 'DAG Chain')

    def test_created_by_relation(self):
        chain = TaskChain.objects.create(name='User Chain', created_by=self.user)
        self.assertEqual(chain.created_by, self.user)
        self.assertIn(chain, self.user.task_chains.all())

    def test_has_circular_dependency_no_cycle(self):
        """Linear chain A -> B -> C has no cycle."""
        chain = TaskChain.objects.create(name='Linear')
        node_a = TaskChainNode.objects.create(chain=chain, task=self.task, order=1)
        node_b = TaskChainNode.objects.create(chain=chain, task=self.task, parent=node_a, order=2)
        TaskChainNode.objects.create(chain=chain, task=self.task, parent=node_b, order=3)
        self.assertFalse(chain.has_circular_dependency())

    def test_has_circular_dependency_with_cycle(self):
        """A -> B -> A creates a cycle."""
        chain = TaskChain.objects.create(name='Cycle')
        node_a = TaskChainNode.objects.create(chain=chain, task=self.task, order=1)
        node_b = TaskChainNode.objects.create(chain=chain, task=self.task, parent=node_a, order=2)
        node_a.parent = node_b
        node_a.save()
        self.assertTrue(chain.has_circular_dependency())

    def test_has_circular_dependency_empty_chain(self):
        chain = TaskChain.objects.create(name='Empty')
        self.assertFalse(chain.has_circular_dependency())

    def test_has_circular_dependency_no_parents(self):
        """Nodes without parents = no edges = no cycle."""
        chain = TaskChain.objects.create(name='No Parents')
        TaskChainNode.objects.create(chain=chain, task=self.task, order=1)
        TaskChainNode.objects.create(chain=chain, task=self.task, order=2)
        self.assertFalse(chain.has_circular_dependency())


class TaskChainNodeModelTests(TestCase):
    """TaskChainNode model: creation, __str__, ordering, FK."""

    def setUp(self):
        self.chain = TaskChain.objects.create(name='Node Chain')
        self.task = Task.objects.create(name='Node Task')

    def test_create_node(self):
        node = TaskChainNode.objects.create(
            chain=self.chain, task=self.task, order=1,
        )
        self.assertEqual(node.order, 1)
        self.assertEqual(node.condition, {})

    def test_str_with_chain(self):
        node = TaskChainNode.objects.create(
            chain=self.chain, task=self.task, order=5,
        )
        self.assertIn('Node Chain', str(node))
        self.assertIn('Node Task', str(node))
        self.assertIn('5', str(node))

    def test_str_without_chain(self):
        node = TaskChainNode.objects.create(
            chain=None, task=self.task, order=2,
        )
        self.assertNotIn('[', str(node))
        self.assertIn('Node Task', str(node))

    def test_chain_related_name(self):
        node = TaskChainNode.objects.create(
            chain=self.chain, task=self.task, order=1,
        )
        self.assertIn(node, self.chain.chain_nodes.all())

    def test_parent_child_relationship(self):
        parent = TaskChainNode.objects.create(
            chain=self.chain, task=self.task, order=1,
        )
        child = TaskChainNode.objects.create(
            chain=self.chain, task=self.task, parent=parent, order=2,
        )
        self.assertIn(child, parent.children.all())

    def test_ordering_by_order_asc(self):
        TaskChainNode.objects.create(chain=self.chain, task=self.task, order=3)
        TaskChainNode.objects.create(chain=self.chain, task=self.task, order=1)
        TaskChainNode.objects.create(chain=self.chain, task=self.task, order=2)
        orders = list(TaskChainNode.objects.values_list('order', flat=True))
        self.assertEqual(orders, [1, 2, 3])

    def test_cascade_delete_chain_deletes_nodes(self):
        node = TaskChainNode.objects.create(
            chain=self.chain, task=self.task, order=1,
        )
        node_id = node.id
        self.chain.delete()
        self.assertFalse(TaskChainNode.objects.filter(id=node_id).exists())


class RecordingModelTests(TestCase):
    """Recording model: creation, defaults, __str__, ordering."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='rec_user', password='Pass123!',
        )

    def test_create_recording_with_defaults(self):
        rec = Recording.objects.create(name='My Recording', user=self.user)
        self.assertEqual(rec.recording_data, {})
        self.assertEqual(rec.pipeline_json, {})
        self.assertEqual(rec.duration, 0)
        self.assertEqual(rec.screenshot_count, 0)
        self.assertEqual(rec.resolution, '1920x1080')

    def test_str_representation(self):
        rec = Recording.objects.create(name='Test Rec', user=self.user)
        self.assertEqual(str(rec), 'Test Rec')

    def test_user_related_name(self):
        rec = Recording.objects.create(name='Rel', user=self.user)
        self.assertIn(rec, self.user.recordings.all())

    def test_cascade_delete_user_deletes_recording(self):
        rec = Recording.objects.create(name='Cascade', user=self.user)
        rec_id = rec.id
        self.user.delete()
        self.assertFalse(Recording.objects.filter(id=rec_id).exists())

    def test_custom_resolution(self):
        rec = Recording.objects.create(
            name='HD', user=self.user, resolution='3840x2160',
        )
        self.assertEqual(rec.resolution, '3840x2160')

    def test_ordering_by_created_at_desc(self):
        import time
        Recording.objects.create(name='R1', user=self.user)
        time.sleep(0.01)
        Recording.objects.create(name='R2', user=self.user)
        names = list(Recording.objects.values_list('name', flat=True))
        self.assertEqual(names[0], 'R2')
