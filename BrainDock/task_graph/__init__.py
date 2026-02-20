"""Task Graph — Task decomposition and dependency graph (Mode 2).

Decomposes a project specification into a directed acyclic graph of tasks
with dependencies, risk annotations, and parallelization hints.

Usage:
    from BrainDock.task_graph import TaskGraphAgent, TaskGraph, TaskNode

    agent = TaskGraphAgent(llm=my_backend)
    graph = agent.decompose(spec_dict)
"""

from .models import TaskNode, RiskNode, TaskGraph
from .agent import TaskGraphAgent

__all__ = [
    "TaskNode",
    "RiskNode",
    "TaskGraph",
    "TaskGraphAgent",
]
