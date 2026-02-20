"""Data models for the Reflection module."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class RootCause:
    """An identified root cause of a failure."""
    description: str
    category: str = ""  # e.g. "missing_dependency", "wrong_approach", "env_issue"
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RootCause:
        return cls(
            description=data["description"],
            category=data.get("category", ""),
            confidence=data.get("confidence", 0.0),
        )


@dataclass
class PlanModification:
    """A proposed modification to the action plan."""
    action: str  # add_step | remove_step | modify_step | reorder
    target_step_id: str = ""
    description: str = ""
    new_step: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PlanModification:
        return cls(
            action=data["action"],
            target_step_id=data.get("target_step_id", ""),
            description=data.get("description", ""),
            new_step=data.get("new_step", {}),
        )


@dataclass
class ReflectionResult:
    """Result of a reflection analysis."""
    root_causes: list[RootCause] = field(default_factory=list)
    modifications: list[PlanModification] = field(default_factory=list)
    summary: str = ""
    should_retry: bool = False
    modified_plan: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "root_causes": [r.to_dict() for r in self.root_causes],
            "modifications": [m.to_dict() for m in self.modifications],
            "summary": self.summary,
            "should_retry": self.should_retry,
            "modified_plan": self.modified_plan,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ReflectionResult:
        return cls(
            root_causes=[RootCause.from_dict(r) for r in data.get("root_causes", [])],
            modifications=[PlanModification.from_dict(m) for m in data.get("modifications", [])],
            summary=data.get("summary", ""),
            should_retry=data.get("should_retry", False),
            modified_plan=data.get("modified_plan", {}),
        )
