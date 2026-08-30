"""TaskExecutor — unified entry point for all agent task execution.

Phase 1 (2026-08-08, Task 1.2): Introduces the ``BaseEngine`` ABC and
``TaskExecutor`` to provide a single ``execute()`` interface that routes
to the appropriate engine implementation based on ``task_type``.

Currently supports:
  - ``"pipeline"`` → delegated to ``PipelineEngine``

Extensible for future task types (e.g. ``"state_machine"``; legacy alias ``"chain"`` also accepted)
by registering additional engines in ``TaskExecutor.engines``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from core.result import AutoResult

# Lazy import for StateMachineEngine to avoid circular dependency
# (state_machine_engine.py imports BaseEngine from this module).
_state_machine_engine: Any = None

def _get_state_machine_engine() -> BaseEngine:
    global _state_machine_engine
    if _state_machine_engine is None:
        from engine.state_machine_engine import StateMachineEngine
        _state_machine_engine = StateMachineEngine()
    return _state_machine_engine

logger = logging.getLogger(__name__)


class BaseEngine(ABC):
    """Abstract base class for all execution engines.

    Each engine implementation handles a specific task type and must
    implement ``run()``.
    """

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> AutoResult:
        """Execute a task and return the result.

        Args:
            *args: Engine-specific positional arguments.
            **kwargs: Engine-specific keyword arguments.

        Returns:
            ``AutoResult`` with ``success`` and result data.
        """
        ...


class PipelineEngineAdapter(BaseEngine):
    """Adapter that wraps the existing ``PipelineEngine`` into the ``BaseEngine`` interface.

    The actual ``PipelineEngine`` is imported lazily to avoid circular
    dependency with the ``engine`` package.
    """

    def run(self, pipeline_json: dict, **kwargs: Any) -> AutoResult:
        """Execute a pipeline via ``PipelineEngine``.

        Args:
            pipeline_json: Pipeline definition dict (with nodes, edges, etc.)
            **kwargs: Additional arguments forwarded to ``PipelineEngine.load()``
                and ``PipelineEngine.execute()``. Common keys include:
                - device: Device instance for device injection
                - coord_transformer: CoordinateTransformer for DPI-aware coords
                - debug_mode: Enable debug screenshots
                - debug_dir: Debug output directory
                - execution_id: Server-provided execution ID for structured logs
                - start_step_index: Skip N steps (retry-from-step)
                - previous_results: Previous step results for retry

        Returns:
            ``AutoResult`` with execution outcome.
        """
        from engine.pipeline_engine import PipelineEngine

        engine = PipelineEngine()

        # Extract known PipelineEngine.load() kwargs
        load_kwargs = {
            k: kwargs[k]
            for k in ("device", "coord_transformer", "debug_mode", "debug_dir", "coord_system", "recovery_manager", "verifier", "wait_freezes")
            if k in kwargs
        }
        engine.load(pipeline_json, **load_kwargs)

        # Extract known PipelineEngine.execute() kwargs
        execute_kwargs = {
            k: kwargs[k]
            for k in ("start_step_index", "previous_results", "execution_id")
            if k in kwargs
        }
        return engine.execute(**execute_kwargs)


class TaskExecutor:
    """Unified task execution entry point.

    Usage::

        executor = TaskExecutor()
        result = executor.execute("pipeline", pipeline_data, device=device_obj)
    """

    def __init__(self) -> None:
        _sm_engine = _get_state_machine_engine()
        self._engines: dict[str, BaseEngine] = {
            "pipeline": PipelineEngineAdapter(),
            "state_machine": _sm_engine,
            "chain": _sm_engine,  # deprecated alias for "state_machine"
        }

    @property
    def engines(self) -> dict[str, BaseEngine]:
        """Return registered engines (read-only view)."""
        return dict(self._engines)

    def register_engine(self, task_type: str, engine: BaseEngine) -> None:
        """Register a new engine for a task type.

        Args:
            task_type: Task type identifier (e.g. ``"state_machine"``; legacy alias ``"chain"`` accepted).
            engine: Engine implementation.

        Raises:
            ValueError: If ``task_type`` is already registered.
        """
        if task_type in self._engines:
            raise ValueError(f"Engine for task type '{task_type}' is already registered")
        self._engines[task_type] = engine

    def execute(self, task_type: str, task_data: dict, **kwargs: Any) -> AutoResult:
        """Execute a task by routing to the appropriate engine.

        Args:
            task_type: Type of task to execute (``"pipeline"``, etc.).
            task_data: Task definition data (pipeline JSON, chain data, etc.).
            **kwargs: Additional arguments forwarded to the engine's ``run()``.

        Returns:
            ``AutoResult`` with execution outcome.

        Raises:
            ValueError: If ``task_type`` is not registered.
        """
        engine = self._engines.get(task_type)
        if engine is None:
            raise ValueError(
                f"Unknown task type: '{task_type}'. "
                f"Registered types: {list(self._engines.keys())}"
            )
        logger.info(
            "TaskExecutor dispatching task_type=%s to engine=%s",
            task_type,
            type(engine).__name__,
        )
        return engine.run(task_data, **kwargs)
