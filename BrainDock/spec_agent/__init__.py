"""Spec Agent — Interactive project specification (Mode 1).

Analyzes a problem statement, makes routine decisions autonomously,
asks the user about critical/ambiguous choices, and generates a
complete project specification.

Usage:
    from BrainDock.spec_agent import SpecAgent, ProjectSpec

    agent = SpecAgent(problem="Build a todo app", llm=my_backend)
    spec = agent.run(ask_fn=my_question_handler)
"""

from .models import Question, Decision, ProjectSpec
from .agent import SpecAgent

__all__ = [
    "Question",
    "Decision",
    "ProjectSpec",
    "SpecAgent",
]
