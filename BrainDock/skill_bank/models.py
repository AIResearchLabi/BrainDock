"""Data models for the Skill Bank."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Skill:
    """A reusable skill learned from a successful task execution."""
    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    pattern: str = ""
    example_code: str = ""
    source_task: str = ""
    usage_count: int = 0
    category: str = ""
    success_count: int = 0
    failure_count: int = 0

    @property
    def reliability_score(self) -> float:
        """Success rate. Defaults to 1.0 if no outcome data."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Skill:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            tags=data.get("tags", []),
            pattern=data.get("pattern", ""),
            example_code=data.get("example_code", ""),
            source_task=data.get("source_task", ""),
            usage_count=data.get("usage_count", 0),
            category=data.get("category", ""),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
        )


@dataclass
class SkillBank:
    """Collection of learned skills with search capabilities."""
    skills: list[Skill] = field(default_factory=list)

    def add(self, skill: Skill) -> None:
        """Add a skill to the bank, replacing if same id exists."""
        self.skills = [s for s in self.skills if s.id != skill.id]
        self.skills.append(skill)

    def find_by_tags(self, tags: list[str]) -> list[Skill]:
        """Find skills matching any of the given tags."""
        tag_set = set(t.lower() for t in tags)
        return [
            s for s in self.skills
            if tag_set & set(t.lower() for t in s.tags)
        ]

    def find_by_category(self, prefix: str) -> list[Skill]:
        """Find skills matching exact category or sub-categories.

        ``"code"`` matches ``"code"`` and ``"code/scaffolding"``.
        """
        p = prefix.lower()
        return [
            s for s in self.skills
            if s.category.lower() == p or s.category.lower().startswith(p + "/")
        ]

    def find_by_name(self, query: str) -> list[Skill]:
        """Find skills whose name contains the query string."""
        q = query.lower()
        return [s for s in self.skills if q in s.name.lower()]

    def get(self, skill_id: str) -> Skill | None:
        """Get a skill by id."""
        for s in self.skills:
            if s.id == skill_id:
                return s
        return None

    def record_usage(self, skill_id: str) -> None:
        """Increment usage count for a skill."""
        skill = self.get(skill_id)
        if skill:
            skill.usage_count += 1

    def record_success(self, skill_id: str) -> None:
        """Record a successful outcome for a skill."""
        skill = self.get(skill_id)
        if skill:
            skill.success_count += 1
            skill.usage_count += 1

    def record_failure(self, skill_id: str) -> None:
        """Record a failed outcome for a skill."""
        skill = self.get(skill_id)
        if skill:
            skill.failure_count += 1
            skill.usage_count += 1

    def get_reliable_skills(self, min_reliability: float = 0.3) -> list[Skill]:
        """Return skills with reliability score >= min_reliability."""
        return [s for s in self.skills if s.reliability_score >= min_reliability]

    def merge(self, other: SkillBank) -> int:
        """Merge skills from another bank. Returns count of new skills added."""
        added = 0
        for skill in other.skills:
            if self.get(skill.id) is None:
                added += 1
            self.add(skill)
        return added

    def to_dict(self) -> dict:
        return {"skills": [s.to_dict() for s in self.skills]}

    @classmethod
    def from_dict(cls, data: dict) -> SkillBank:
        return cls(
            skills=[Skill.from_dict(s) for s in data.get("skills", [])]
        )
