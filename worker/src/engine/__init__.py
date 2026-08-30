"""Engine package — Pipeline execution and task orchestration.

Phase 1 (2026-08-08, Task 1.2):
  - ``engine.py`` → renamed to ``pipeline_engine.py``
  - Added ``executor.py`` with ``TaskExecutor`` (unified entry point)
"""

# PipelineEngine — the core pipeline execution engine
# StateMachineEngine — StateMachine execution engine wrapper
from engine.state_machine_engine import StateMachineEngine

# TaskExecutor — unified entry point for all task types
from engine.executor import BaseEngine, PipelineEngineAdapter, TaskExecutor
from engine.pipeline_engine import MAX_STEP_TIMEOUT, PipelineEngine, PipelineResult

__all__ = [
    "PipelineEngine",
    "PipelineResult",
    "MAX_STEP_TIMEOUT",
    "BaseEngine",
    "PipelineEngineAdapter",
    "TaskExecutor",
    "StateMachineEngine",
]
