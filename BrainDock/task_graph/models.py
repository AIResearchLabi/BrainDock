"""Data models for the Task Graph."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class RiskNode:
    """A risk associated with a task."""
    description: str
    severity: str = "medium"  # low | medium | high
    mitigation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RiskNode:
        return cls(
            description=data["description"],
            severity=data.get("severity", "medium"),
            mitigation=data.get("mitigation", ""),
        )


@dataclass
class TaskNode:
    """A single task in the task graph."""
    id: str
    title: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    estimated_effort: str = "medium"  # small | medium | large
    risks: list[RiskNode] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | in_progress | completed | failed
    output: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> TaskNode:
        risks = [
            RiskNode.from_dict(r) if isinstance(r, dict) else r
            for r in data.get("risks", [])
        ]
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            depends_on=data.get("depends_on", []),
            estimated_effort=data.get("estimated_effort", "medium"),
            risks=risks,
            tags=data.get("tags", []),
            status=data.get("status", "pending"),
            output=data.get("output", ""),
        )


@dataclass
class TaskGraph:
    """Directed acyclic graph of tasks with dependency tracking."""
    tasks: list[TaskNode] = field(default_factory=list)
    project_title: str = ""

    def get_task(self, task_id: str) -> TaskNode | None:
        """Get a task by id."""
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def get_ready_tasks(self) -> list[TaskNode]:
        """Get tasks whose dependencies are all completed."""
        completed_ids = {t.id for t in self.tasks if t.status == "completed"}
        return [
            t for t in self.tasks
            if t.status == "pending"
            and all(dep in completed_ids for dep in t.depends_on)
        ]

    def get_parallel_groups(self) -> list[list[TaskNode]]:
        """Get tasks grouped by execution wave (topological layers).

        Each group can be executed in parallel. Groups must be executed
        in order (group 0 before group 1, etc.).
        """
        completed: set[str] = set()
        remaining = [t for t in self.tasks if t.status == "pending"]
        groups: list[list[TaskNode]] = []

        while remaining:
            # Find all tasks whose deps are satisfied
            ready = [
                t for t in remaining
                if all(dep in completed for dep in t.depends_on)
            ]
            if not ready:
                # Circular dependency or unresolvable — add remaining as-is
                groups.append(remaining)
                break
            groups.append(ready)
            completed.update(t.id for t in ready)
            remaining = [t for t in remaining if t.id not in completed]

        return groups

    def mark_completed(self, task_id: str, output: str = "") -> None:
        """Mark a task as completed."""
        task = self.get_task(task_id)
        if task:
            task.status = "completed"
            task.output = output

    def mark_failed(self, task_id: str, output: str = "") -> None:
        """Mark a task as failed."""
        task = self.get_task(task_id)
        if task:
            task.status = "failed"
            task.output = output

    def all_completed(self) -> bool:
        """Check if all tasks are completed."""
        return all(t.status == "completed" for t in self.tasks)

    def to_dict(self) -> dict:
        return {
            "project_title": self.project_title,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaskGraph:
        return cls(
            project_title=data.get("project_title", ""),
            tasks=[TaskNode.from_dict(t) for t in data.get("tasks", [])],
        )
