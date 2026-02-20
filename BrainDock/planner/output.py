"""Output formatters for the Planner."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ActionPlan


def to_json(plan: ActionPlan, indent: int = 2) -> str:
    """Convert an ActionPlan to formatted JSON string."""
    return json.dumps(plan.to_dict(), indent=indent)


def to_markdown(plan: ActionPlan) -> str:
    """Convert an ActionPlan to a human-readable Markdown document."""
    lines: list[str] = []

    lines.append(f"# Action Plan: {plan.task_title}")
    lines.append(f"*Task ID: {plan.task_id}*")
    lines.append("")

    m = plan.metrics
    lines.append("## Metrics")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Confidence | {m.confidence:.0%} |")
    lines.append(f"| Entropy | {m.entropy:.0%} |")
    lines.append(f"| Complexity | {m.complexity} |")
    lines.append(f"| Steps | {m.estimated_steps} |")
    lines.append("")

    if plan.steps:
        lines.append("## Steps")
        lines.append("")
        for step in plan.steps:
            tool_tag = f" `[{step.tool}]`" if step.tool else ""
            lines.append(f"### {step.id}. {step.action}{tool_tag}")
            lines.append("")
            lines.append(step.description)
            if step.expected_output:
                lines.append(f"\n*Expected:* {step.expected_output}")
            lines.append("")

    if plan.assumptions:
        lines.append("## Assumptions")
        lines.append("")
        for a in plan.assumptions:
            lines.append(f"- {a}")
        lines.append("")

    if plan.relevant_skills:
        lines.append("## Relevant Skills")
        lines.append("")
        for s in plan.relevant_skills:
            lines.append(f"- {s}")
        lines.append("")

    return "\n".join(lines)


def save_plan(plan: ActionPlan, output_dir: str = "output/planner") -> tuple[str, str]:
    """Save action plan as both JSON and Markdown files."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    json_path = path / f"plan_{plan.task_id}.json"
    md_path = path / f"plan_{plan.task_id}.md"

    json_path.write_text(to_json(plan))
    md_path.write_text(to_markdown(plan))

    return str(json_path), str(md_path)
