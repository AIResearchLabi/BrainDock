"""Data models for the Spec Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict


@dataclass
class Question:
    """A question the LLM needs the user to answer."""
    id: str
    question: str
    why: str
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Question:
        return cls(
            id=data["id"],
            question=data["question"],
            why=data["why"],
            options=data.get("options", []),
        )


@dataclass
class FunctionalRequirement:
    """A functional requirement for the project."""
    feature: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    priority: str = "must-have"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> FunctionalRequirement:
        return cls(
            feature=data.get("feature", ""),
            description=data.get("description", ""),
            acceptance_criteria=data.get("acceptance_criteria", []),
            priority=data.get("priority", "must-have"),
        )


@dataclass
class Milestone:
    """A project milestone."""
    name: str
    description: str
    deliverables: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Milestone:
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            deliverables=data.get("deliverables", []),
        )


@dataclass
class Decision:
    """A decision the LLM made autonomously."""
    id: str
    topic: str
    decision: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Decision:
        return cls(
            id=data["id"],
            topic=data["topic"],
            decision=data["decision"],
        )


@dataclass
class ProjectSpec:
    """Complete project specification produced by the Spec Agent."""
    title: str = ""
    summary: str = ""
    problem_statement: str = ""
    goals: list[str] = field(default_factory=list)
    target_users: str = ""
    user_stories: list[dict] = field(default_factory=list)
    functional_requirements: list[FunctionalRequirement] = field(default_factory=list)
    non_functional_requirements: list[dict] = field(default_factory=list)
    tech_stack: dict = field(default_factory=dict)
    architecture_overview: str = ""
    data_models: list[dict] = field(default_factory=list)
    api_endpoints: list[dict] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> ProjectSpec:
        raw_fr = data.get("functional_requirements", [])
        functional_requirements = [
            FunctionalRequirement.from_dict(r) if isinstance(r, dict) else r
            for r in raw_fr
        ]
        raw_ms = data.get("milestones", [])
        milestones = [
            Milestone.from_dict(m) if isinstance(m, dict) else m
            for m in raw_ms
        ]
        return cls(
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            problem_statement=data.get("problem_statement", ""),
            goals=data.get("goals", []),
            target_users=data.get("target_users", ""),
            user_stories=data.get("user_stories", []),
            functional_requirements=functional_requirements,
            non_functional_requirements=data.get("non_functional_requirements", []),
            tech_stack=data.get("tech_stack", {}),
            architecture_overview=data.get("architecture_overview", ""),
            data_models=data.get("data_models", []),
            api_endpoints=data.get("api_endpoints", []),
            milestones=milestones,
            constraints=data.get("constraints", []),
            assumptions=data.get("assumptions", []),
            open_questions=data.get("open_questions", []),
        )
