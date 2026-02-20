"""Reflection — Failure root-cause analysis (Mode 7).

Analyzes execution failures to identify root causes and propose plan
modifications. Limited to max 2 iterations to prevent infinite loops.

Usage:
    from BrainDock.reflection import ReflectionAgent, ReflectionResult

    agent = ReflectionAgent(llm=my_backend)
    result = agent.reflect(execution_result, plan, context)
"""

from .models import RootCause, PlanModification, ReflectionResult
from .agent import ReflectionAgent

__all__ = [
    "RootCause",
    "PlanModification",
    "ReflectionResult",
    "ReflectionAgent",
]
