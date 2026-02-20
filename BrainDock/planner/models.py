"""Data models for the Planner."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class ActionStep:
    """A single step in an action plan."""
    id: str
    action: str
    description: str
    tool: str = ""  # e.g. "write_file", "run_command", "edit_file"
    expected_output: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ActionStep:
        return cls(
            id=data["id"],
            action=data["action"],
            description=data["description"],
            tool=data.get("tool", ""),
            expected_output=data.get("expected_output", ""),
        )


@dataclass
class PlanMetrics:
    """Metrics for plan quality assessment."""
    confidence: float = 0.0  # 0.0 - 1.0
    entropy: float = 0.0  # 0.0 - 1.0 (lower = more certain)
    estimated_steps: int = 0
    complexity: str = "medium"  # low | medium | high

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PlanMetrics:
        return cls(
            confidence=data.get("confidence", 0.0),
            entropy=data.get("entropy", 0.0),
            estimated_steps=data.get("estimated_steps", 0),
            complexity=data.get("complexity", "medium"),
        )


@dataclass
class ActionPlan:
    """A complete action plan for a task."""
    task_id: str
    task_title: str
    steps: list[ActionStep] = field(default_factory=list)
    metrics: PlanMetrics = field(default_factory=PlanMetrics)
    relevant_skills: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_title": self.task_title,
            "steps": [s.to_dict() for s in self.steps],
            "metrics": self.metrics.to_dict(),
            "relevant_skills": self.relevant_skills,
            "assumptions": self.assumptions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ActionPlan:
        return cls(
            task_id=data["task_id"],
            task_title=data["task_title"],
            steps=[ActionStep.from_dict(s) for s in data.get("steps", [])],
            metrics=PlanMetrics.from_dict(data.get("metrics", {})),
            relevant_skills=data.get("relevant_skills", []),
            assumptions=data.get("assumptions", []),
        )
