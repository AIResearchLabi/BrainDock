"""Executor — Sandboxed task execution (Mode 5).

Executes action plan steps with budget enforcement and stop conditions.

Usage:
    from BrainDock.executor import ExecutorAgent, ExecutionResult, TaskOutcome

    agent = ExecutorAgent(llm=my_backend)
    result = agent.execute(plan_dict, project_dir)
"""

from .models import TaskOutcome, StopCondition, ExecutionResult, VerifyResult
from .agent import ExecutorAgent

__all__ = [
    "TaskOutcome",
    "StopCondition",
    "ExecutionResult",
    "VerifyResult",
    "ExecutorAgent",
]
