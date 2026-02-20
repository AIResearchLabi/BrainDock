"""Orchestrator — Pipeline orchestrator for the 8-mode system.

Coordinates all modes in a gated pipeline:
  SPEC → TASK_GRAPH → PLAN → CONTROLLER → EXECUTE → SKILL_LEARN → (REFLECT) → (DEBATE)

Usage:
    from BrainDock.orchestrator import OrchestratorAgent, RunConfig, PipelineState

    orchestrator = OrchestratorAgent(config=RunConfig(...))
    result = orchestrator.run(problem="Build a todo app", ask_fn=my_callback)
"""

from .models import Mode, PipelineState, RunConfig
from .agent import OrchestratorAgent

__all__ = [
    "Mode",
    "PipelineState",
    "RunConfig",
    "OrchestratorAgent",
]
