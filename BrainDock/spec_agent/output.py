"""Output formatters for the Spec Agent."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ProjectSpec


def to_json(spec: ProjectSpec, indent: int = 2) -> str:
    """Convert a ProjectSpec to formatted JSON string."""
    return json.dumps(spec.to_dict(), indent=indent)


def to_markdown(spec: ProjectSpec) -> str:
    """Convert a ProjectSpec to a Markdown document."""
    lines = []

    lines.append(f"# {spec.title}")
    if spec.summary:
        lines.append(f"\n{spec.summary}")

    if spec.problem_statement:
        lines.append("\n## Problem Statement")
        lines.append(spec.problem_statement)

    if spec.goals:
        lines.append("\n## Goals")
        for goal in spec.goals:
            lines.append(f"- {goal}")

    if spec.target_users:
        lines.append("\n## Target Users")
        lines.append(spec.target_users)

    if spec.user_stories:
        lines.append("\n## User Stories")
        for story in spec.user_stories:
            if isinstance(story, dict):
                lines.append(f"- {story.get('story', story)}")
            else:
                lines.append(f"- {story}")

    if spec.functional_requirements:
        lines.append("\n## Functional Requirements")
        for req in spec.functional_requirements:
            if hasattr(req, "feature"):
                lines.append(f"\n### {req.feature}")
                lines.append(req.description)
                if req.acceptance_criteria:
                    for ac in req.acceptance_criteria:
                        lines.append(f"- {ac}")
            elif isinstance(req, dict):
                lines.append(f"\n### {req.get('feature', '')}")
                lines.append(req.get("description", ""))

    if spec.tech_stack:
        lines.append("\n## Tech Stack")
        lines.append("\n| Layer | Technology |")
        lines.append("|-------|------------|")
        for layer, tech in spec.tech_stack.items():
            lines.append(f"| {layer} | {tech} |")

    if spec.architecture_overview:
        lines.append("\n## Architecture Overview")
        lines.append(spec.architecture_overview)

    if spec.milestones:
        lines.append("\n## Milestones")
        for ms in spec.milestones:
            if hasattr(ms, "name"):
                lines.append(f"\n### {ms.name}")
                lines.append(ms.description)
                if ms.deliverables:
                    for d in ms.deliverables:
                        lines.append(f"- {d}")
            elif isinstance(ms, dict):
                lines.append(f"\n### {ms.get('name', '')}")

    if spec.constraints:
        lines.append("\n## Constraints")
        for c in spec.constraints:
            lines.append(f"- {c}")

    if spec.assumptions:
        lines.append("\n## Assumptions")
        for a in spec.assumptions:
            lines.append(f"- {a}")

    if spec.open_questions:
        lines.append("\n## Open Questions")
        for q in spec.open_questions:
            lines.append(f"- {q}")

    return "\n".join(lines)


def save_spec(spec: ProjectSpec, output_dir: str = "output/spec_agent") -> tuple[str, str]:
    """Save project spec as JSON and Markdown files.

    Returns a tuple of (json_path, md_path).
    """
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    json_path = path / "spec.json"
    json_path.write_text(to_json(spec))

    md_path = path / "spec.md"
    md_path.write_text(to_markdown(spec))

    return str(json_path), str(md_path)
