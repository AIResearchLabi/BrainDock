"""Planner — Action planning with entropy thresholds (Mode 3).

Converts task graph nodes into detailed action plans with step-by-step
instructions, metrics, and confidence scoring.

Usage:
    from BrainDock.planner import PlannerAgent, ActionPlan, ActionStep

    agent = PlannerAgent(llm=my_backend)
    plan = agent.plan_task(task_dict, context)
"""

from .models import ActionStep, PlanMetrics, ActionPlan
from .agent import PlannerAgent

__all__ = [
    "ActionStep",
    "PlanMetrics",
    "ActionPlan",
    "PlannerAgent",
]
