"""factory_boy factories for the tasks app."""

import factory

from accounts.factories import UserFactory
from agents.factories import AgentFactory
from tasks.models import Task, TaskExecution


class TaskFactory(factory.django.DjangoModelFactory):
    """Factory for generating test tasks."""

    class Meta:
        model = Task
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"task-{n}")
    description = factory.Sequence(lambda n: f"Test task description {n}")
    execution_mode = Task.ExecutionMode.PIPELINE
    task_definition = factory.LazyFunction(lambda: {"nodes": []})
    params_config = factory.LazyFunction(dict)
    is_enabled = True
    source_type = Task.SourceType.MANUAL


class TaskExecutionFactory(factory.django.DjangoModelFactory):
    """Factory for generating test task executions."""

    class Meta:
        model = TaskExecution
        skip_postgeneration_save = True

    task = factory.SubFactory(TaskFactory)
    agent = factory.SubFactory(AgentFactory)
    triggered_by = factory.SubFactory(UserFactory)
    status = TaskExecution.Status.PENDING
    result_data = factory.LazyFunction(dict)
