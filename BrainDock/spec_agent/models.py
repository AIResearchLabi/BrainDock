"""Data models for the Spec Agent."""

from __future__ import annotations

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
    functional_requirements: list[dict] = field(default_factory=list)
    non_functional_requirements: list[dict] = field(default_factory=list)
    tech_stack: dict = field(default_factory=dict)
    architecture_overview: str = ""
    data_models: list[dict] = field(default_factory=list)
    api_endpoints: list[dict] = field(default_factory=list)
    milestones: list[dict] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ProjectSpec:
        return cls(
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            problem_statement=data.get("problem_statement", ""),
            goals=data.get("goals", []),
            target_users=data.get("target_users", ""),
            user_stories=data.get("user_stories", []),
            functional_requirements=data.get("functional_requirements", []),
            non_functional_requirements=data.get("non_functional_requirements", []),
            tech_stack=data.get("tech_stack", {}),
            architecture_overview=data.get("architecture_overview", ""),
            data_models=data.get("data_models", []),
            api_endpoints=data.get("api_endpoints", []),
            milestones=data.get("milestones", []),
            constraints=data.get("constraints", []),
            assumptions=data.get("assumptions", []),
            open_questions=data.get("open_questions", []),
        )
