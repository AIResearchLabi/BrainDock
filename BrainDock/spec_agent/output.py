"""Output formatters for ProjectSpec → JSON and Markdown."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .models import ProjectSpec


def to_json(spec: ProjectSpec, indent: int = 2) -> str:
    """Convert a ProjectSpec to formatted JSON string."""
    return spec.to_json(indent=indent)


def to_markdown(spec: ProjectSpec) -> str:
    """Convert a ProjectSpec to a human-readable Markdown document."""
    lines: list[str] = []

    lines.append(f"# {spec.title}")
    lines.append("")
    lines.append(f"> {spec.summary}")
    lines.append("")

    # Problem Statement
    lines.append("## Problem Statement")
    lines.append("")
    lines.append(spec.problem_statement)
    lines.append("")

    # Goals
    if spec.goals:
        lines.append("## Goals")
        lines.append("")
        for goal in spec.goals:
            lines.append(f"- {goal}")
        lines.append("")

    # Target Users
    if spec.target_users:
        lines.append("## Target Users")
        lines.append("")
        lines.append(spec.target_users)
        lines.append("")

    # User Stories
    if spec.user_stories:
        lines.append("## User Stories")
        lines.append("")
        for story in spec.user_stories:
            lines.append(f"- {story}")
        lines.append("")

    # Functional Requirements
    if spec.functional_requirements:
        lines.append("## Functional Requirements")
        lines.append("")
        for fr in spec.functional_requirements:
            priority_tag = f" `[{fr.priority}]`" if fr.priority else ""
            lines.append(f"### {fr.feature}{priority_tag}")
            lines.append("")
            lines.append(fr.description)
            lines.append("")
            if fr.acceptance_criteria:
                lines.append("**Acceptance Criteria:**")
                for ac in fr.acceptance_criteria:
                    lines.append(f"- [ ] {ac}")
                lines.append("")

    # Non-Functional Requirements
    if spec.non_functional_requirements:
        lines.append("## Non-Functional Requirements")
        lines.append("")
        for nfr in spec.non_functional_requirements:
            lines.append(f"- {nfr}")
        lines.append("")

    # Tech Stack
    if spec.tech_stack:
        lines.append("## Tech Stack")
        lines.append("")
        lines.append("| Layer | Technology |")
        lines.append("|-------|-----------|")
        for layer, tech in spec.tech_stack.items():
            lines.append(f"| {layer} | {tech} |")
        lines.append("")

    # Architecture
    if spec.architecture_overview:
        lines.append("## Architecture Overview")
        lines.append("")
        lines.append(spec.architecture_overview)
        lines.append("")

    # Data Models
    if spec.data_models:
        lines.append("## Data Models")
        lines.append("")
        for model in spec.data_models:
            name = model.get("name", "Unknown")
            lines.append(f"### {name}")
            lines.append("")
            fields = model.get("fields", {})
            if fields:
                lines.append("| Field | Type |")
                lines.append("|-------|------|")
                for field_name, field_type in fields.items():
                    lines.append(f"| {field_name} | {field_type} |")
                lines.append("")
            rels = model.get("relationships", "")
            if rels:
                lines.append(f"*Relationships:* {rels}")
                lines.append("")

    # API Endpoints
    if spec.api_endpoints:
        lines.append("## API Endpoints")
        lines.append("")
        lines.append("| Method | Path | Description |")
        lines.append("|--------|------|-------------|")
        for ep in spec.api_endpoints:
            method = ep.get("method", "")
            path = ep.get("path", "")
            desc = ep.get("description", "")
            lines.append(f"| `{method}` | `{path}` | {desc} |")
        lines.append("")

    # Milestones
    if spec.milestones:
        lines.append("## Milestones")
        lines.append("")
        for ms in spec.milestones:
            lines.append(f"### {ms.name}")
            lines.append("")
            lines.append(ms.description)
            lines.append("")
            if ms.deliverables:
                for d in ms.deliverables:
                    lines.append(f"- [ ] {d}")
                lines.append("")

    # Constraints
    if spec.constraints:
        lines.append("## Constraints")
        lines.append("")
        for c in spec.constraints:
            lines.append(f"- {c}")
        lines.append("")

    # Assumptions
    if spec.assumptions:
        lines.append("## Assumptions")
        lines.append("")
        for a in spec.assumptions:
            lines.append(f"- {a}")
        lines.append("")

    # Open Questions
    if spec.open_questions:
        lines.append("## Open Questions")
        lines.append("")
        for q in spec.open_questions:
            lines.append(f"- {q}")
        lines.append("")

    return "\n".join(lines)


def save_spec(spec: ProjectSpec, output_dir: str = "spec_output") -> tuple[str, str]:
    """Save spec as both JSON and Markdown files.

    Returns:
        Tuple of (json_path, markdown_path).
    """
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    json_path = path / "spec.json"
    md_path = path / "spec.md"

    json_path.write_text(to_json(spec))
    md_path.write_text(to_markdown(spec))

    return str(json_path), str(md_path)
