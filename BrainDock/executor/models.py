"""Data models for the Executor."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class TaskOutcome:
    """Outcome of executing a single action step."""
    step_id: str
    success: bool
    output: str = ""
    error: str = ""
    affected_file: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TaskOutcome:
        return cls(
            step_id=data["step_id"],
            success=data["success"],
            output=data.get("output", ""),
            error=data.get("error", ""),
            affected_file=data.get("affected_file", ""),
        )


@dataclass
class VerifyResult:
    """Result of running project verification."""
    success: bool
    command: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    error_summary: str = ""
    detection_method: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StopCondition:
    """Conditions that stop execution."""
    max_steps: int = 50
    max_failures: int = 3
    timeout_seconds: int = 300

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> StopCondition:
        return cls(
            max_steps=data.get("max_steps", 50),
            max_failures=data.get("max_failures", 3),
            timeout_seconds=data.get("timeout_seconds", 300),
        )


@dataclass
class ExecutionResult:
    """Result of executing an action plan."""
    task_id: str
    success: bool
    outcomes: list[TaskOutcome] = field(default_factory=list)
    steps_completed: int = 0
    steps_total: int = 0
    failure_count: int = 0
    stop_reason: str = ""
    generated_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "failure_count": self.failure_count,
            "stop_reason": self.stop_reason,
            "generated_files": self.generated_files,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExecutionResult:
        return cls(
            task_id=data["task_id"],
            success=data["success"],
            outcomes=[TaskOutcome.from_dict(o) for o in data.get("outcomes", [])],
            steps_completed=data.get("steps_completed", 0),
            steps_total=data.get("steps_total", 0),
            failure_count=data.get("failure_count", 0),
            stop_reason=data.get("stop_reason", ""),
            generated_files=data.get("generated_files", []),
        )
