"""Debate — Multi-perspective design reasoning (Mode 8).

When a plan has high entropy/uncertainty, the debate module generates
multiple perspectives and critiques to converge on a better approach.
Limited to max 3 exchanges.

Usage:
    from BrainDock.debate import DebateAgent, DebateOutcome

    agent = DebateAgent(llm=my_backend)
    outcome = agent.debate(plan_dict, context)
"""

from .models import DebatePlan, Critique, DebateOutcome
from .agent import DebateAgent

__all__ = [
    "DebatePlan",
    "Critique",
    "DebateOutcome",
    "DebateAgent",
]
