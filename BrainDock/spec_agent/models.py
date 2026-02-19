"""Data models for the Spec Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Decision:
    """A decision the agent made autonomously (not asked to user)."""
    id: str
    topic: str
    decision: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Question:
    """A clarifying question the agent asks the user."""
    id: str
    question: str
    why: str
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Milestone:
    """A project milestone with deliverables."""
    name: str
    description: str
    deliverables: list[str] = field(default_factory=list)


@dataclass
class FunctionalRequirement:
    """A functional requirement with acceptance criteria."""
    feature: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    priority: str = "must-have"  # must-have | should-have | nice-to-have


@dataclass
class ProjectSpec:
    """The final structured project specification."""
    title: str = ""
    summary: str = ""
    problem_statement: str = ""
    goals: list[str] = field(default_factory=list)
    target_users: str = ""
    user_stories: list[str] = field(default_factory=list)
    functional_requirements: list[FunctionalRequirement] = field(default_factory=list)
    non_functional_requirements: list[str] = field(default_factory=list)
    tech_stack: dict[str, str] = field(default_factory=dict)
    architecture_overview: str = ""
    data_models: list[dict[str, Any]] = field(default_factory=list)
    api_endpoints: list[dict[str, str]] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> ProjectSpec:
        spec = cls()
        # Simple fields
        for key in ("title", "summary", "problem_statement", "target_users",
                     "architecture_overview"):
            if key in data:
                setattr(spec, key, data[key])

        # List of strings
        for key in ("goals", "user_stories", "non_functional_requirements",
                     "constraints", "assumptions", "open_questions"):
            if key in data and isinstance(data[key], list):
                setattr(spec, key, data[key])

        # Tech stack dict
        if "tech_stack" in data and isinstance(data["tech_stack"], dict):
            spec.tech_stack = data["tech_stack"]

        # Functional requirements
        if "functional_requirements" in data:
            spec.functional_requirements = [
                FunctionalRequirement(**fr) if isinstance(fr, dict) else fr
                for fr in data["functional_requirements"]
            ]

        # Milestones
        if "milestones" in data:
            spec.milestones = [
                Milestone(**m) if isinstance(m, dict) else m
                for m in data["milestones"]
            ]

        # Pass-through lists of dicts
        for key in ("data_models", "api_endpoints"):
            if key in data and isinstance(data[key], list):
                setattr(spec, key, data[key])

        return spec
