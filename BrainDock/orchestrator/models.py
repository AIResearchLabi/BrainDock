"""Data models for the Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Mode(str, Enum):
    """The 8 modes of the BrainDock pipeline."""
    SPECIFICATION = "specification"     # Mode 1
    TASK_GRAPH = "task_graph"           # Mode 2
    PLANNING = "planning"               # Mode 3
    CONTROLLER = "controller"           # Mode 4
    EXECUTION = "execution"             # Mode 5
    SKILL_LEARNING = "skill_learning"   # Mode 6
    REFLECTION = "reflection"           # Mode 7
    DEBATE = "debate"                   # Mode 8


@dataclass
class RunConfig:
    """Configuration for an orchestrator run."""
    output_dir: str = "output"
    max_task_retries: int = 2
    max_reflection_iterations: int = 2
    max_debate_rounds: int = 3
    min_confidence: float = 0.6
    max_entropy: float = 0.7
    skip_execution: bool = False
    skip_skill_learning: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RunConfig:
        return cls(
            output_dir=data.get("output_dir", "output"),
            max_task_retries=data.get("max_task_retries", 2),
            max_reflection_iterations=data.get("max_reflection_iterations", 2),
            max_debate_rounds=data.get("max_debate_rounds", 3),
            min_confidence=data.get("min_confidence", 0.6),
            max_entropy=data.get("max_entropy", 0.7),
            skip_execution=data.get("skip_execution", False),
            skip_skill_learning=data.get("skip_skill_learning", False),
        )


@dataclass
class PipelineState:
    """Tracks the state of the entire pipeline run."""
    current_mode: str = Mode.SPECIFICATION.value
    spec: dict = field(default_factory=dict)
    task_graph: dict = field(default_factory=dict)
    plans: list[dict] = field(default_factory=list)
    execution_results: list[dict] = field(default_factory=list)
    learned_skills: list[dict] = field(default_factory=list)
    reflections: list[dict] = field(default_factory=list)
    debates: list[dict] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PipelineState:
        state = cls()
        for key in (
            "current_mode", "spec", "task_graph", "plans",
            "execution_results", "learned_skills", "reflections",
            "debates", "completed_tasks", "failed_tasks", "error",
        ):
            if key in data:
                setattr(state, key, data[key])
        return state
