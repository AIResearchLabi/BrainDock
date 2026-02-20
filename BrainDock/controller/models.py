"""Data models for the Controller."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum


class GateAction(str, Enum):
    """Action to take based on gate check."""
    PROCEED = "proceed"
    REFLECT = "reflect"
    DEBATE = "debate"
    ABORT = "abort"


@dataclass
class GateThresholds:
    """Configurable thresholds for quality gates."""
    min_confidence: float = 0.6
    max_entropy: float = 0.7
    max_failures: int = 3
    max_reflection_iterations: int = 2
    max_debate_rounds: int = 3

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> GateThresholds:
        return cls(
            min_confidence=data.get("min_confidence", 0.6),
            max_entropy=data.get("max_entropy", 0.7),
            max_failures=data.get("max_failures", 3),
            max_reflection_iterations=data.get("max_reflection_iterations", 2),
            max_debate_rounds=data.get("max_debate_rounds", 3),
        )


@dataclass
class GateResult:
    """Result of a quality gate check."""
    gate_name: str
    passed: bool
    action: str = "proceed"  # proceed | reflect | debate | abort
    reason: str = ""
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> GateResult:
        return cls(
            gate_name=data["gate_name"],
            passed=data["passed"],
            action=data.get("action", "proceed"),
            reason=data.get("reason", ""),
            metrics=data.get("metrics", {}),
        )


@dataclass
class ControllerState:
    """Tracks controller state across the pipeline."""
    failure_count: int = 0
    reflection_count: int = 0
    debate_count: int = 0
    gate_history: list[dict] = field(default_factory=list)

    def record_gate(self, result: GateResult) -> None:
        """Record a gate check result."""
        self.gate_history.append(result.to_dict())
        if not result.passed:
            self.failure_count += 1

    def record_reflection(self) -> None:
        """Record that a reflection iteration occurred."""
        self.reflection_count += 1

    def record_debate(self) -> None:
        """Record that a debate round occurred."""
        self.debate_count += 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ControllerState:
        state = cls(
            failure_count=data.get("failure_count", 0),
            reflection_count=data.get("reflection_count", 0),
            debate_count=data.get("debate_count", 0),
        )
        state.gate_history = data.get("gate_history", [])
        return state
