"""Data models for the Debate module."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class DebatePlan:
    """An alternative plan proposed during debate."""
    perspective: str
    approach: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> DebatePlan:
        return cls(
            perspective=data["perspective"],
            approach=data["approach"],
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            confidence=data.get("confidence", 0.0),
        )


@dataclass
class Critique:
    """A critique of a proposed plan."""
    target_perspective: str
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Critique:
        return cls(
            target_perspective=data["target_perspective"],
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
        )


@dataclass
class DebateOutcome:
    """The converged outcome of a debate."""
    proposals: list[DebatePlan] = field(default_factory=list)
    critiques: list[Critique] = field(default_factory=list)
    winning_approach: str = ""
    synthesis: str = ""
    improved_plan: dict = field(default_factory=dict)
    rounds_used: int = 0
    converged: bool = False

    def to_dict(self) -> dict:
        return {
            "proposals": [p.to_dict() for p in self.proposals],
            "critiques": [c.to_dict() for c in self.critiques],
            "winning_approach": self.winning_approach,
            "synthesis": self.synthesis,
            "improved_plan": self.improved_plan,
            "rounds_used": self.rounds_used,
            "converged": self.converged,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DebateOutcome:
        return cls(
            proposals=[DebatePlan.from_dict(p) for p in data.get("proposals", [])],
            critiques=[Critique.from_dict(c) for c in data.get("critiques", [])],
            winning_approach=data.get("winning_approach", ""),
            synthesis=data.get("synthesis", ""),
            improved_plan=data.get("improved_plan", {}),
            rounds_used=data.get("rounds_used", 0),
            converged=data.get("converged", False),
        )
