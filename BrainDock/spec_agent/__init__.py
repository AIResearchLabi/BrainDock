"""Spec Agent — Interactive Project Specification Builder.

Usage as a library:
    from BrainDock.spec_agent import SpecAgent, ProjectSpec

    agent = SpecAgent(problem="Build a todo app with auth")
    spec = agent.run(ask_fn=my_question_handler)
    # spec is a ProjectSpec dataclass

Usage from CLI:
    python -m BrainDock.spec_agent "Build a todo app with auth"
"""

from .agent import SpecAgent, AnalyzeResult
from .models import ProjectSpec, Question, Decision, FunctionalRequirement, Milestone
from .output import to_json, to_markdown, save_spec
from .llm import ClaudeCLIBackend, CallableBackend

__all__ = [
    "SpecAgent",
    "AnalyzeResult",
    "ProjectSpec",
    "Question",
    "Decision",
    "FunctionalRequirement",
    "Milestone",
    "to_json",
    "to_markdown",
    "save_spec",
    "ClaudeCLIBackend",
    "CallableBackend",
]
