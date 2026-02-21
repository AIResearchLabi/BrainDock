"""Data models for Market Study results."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class MarketStudyResult:
    """Result of a market study analysis for a task."""
    task_id: str = ""
    competitors: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    target_audience: str = ""
    positioning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> MarketStudyResult:
        return cls(
            task_id=data.get("task_id", ""),
            competitors=data.get("competitors", []),
            recommendations=data.get("recommendations", []),
            risks=data.get("risks", []),
            target_audience=data.get("target_audience", ""),
            positioning=data.get("positioning", ""),
        )

    def to_context_string(self) -> str:
        """Format the market study as a context string for LLM prompts."""
        parts = [f"Market Study for task {self.task_id}:"]
        if self.target_audience:
            parts.append(f"Target Audience: {self.target_audience}")
        if self.positioning:
            parts.append(f"Positioning: {self.positioning}")
        if self.competitors:
            parts.append("Competitors: " + ", ".join(self.competitors))
        if self.recommendations:
            parts.append("Recommendations:")
            for r in self.recommendations:
                parts.append(f"  - {r}")
        if self.risks:
            parts.append("Market Risks:")
            for r in self.risks:
                parts.append(f"  - {r}")
        return "\n".join(parts)
