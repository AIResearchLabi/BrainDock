"""Output formatters for the Task Graph."""

from __future__ import annotations

import json
from pathlib import Path

from .models import TaskGraph


def to_json(graph: TaskGraph, indent: int = 2) -> str:
    """Convert a TaskGraph to formatted JSON string."""
    return json.dumps(graph.to_dict(), indent=indent)


def to_markdown(graph: TaskGraph) -> str:
    """Convert a TaskGraph to a human-readable Markdown document."""
    lines: list[str] = []

    lines.append(f"# Task Graph: {graph.project_title}")
    lines.append("")

    groups = graph.get_parallel_groups()
    for i, group in enumerate(groups):
        lines.append(f"## Wave {i + 1} (parallel)")
        lines.append("")
        for task in group:
            effort_tag = f" `[{task.estimated_effort}]`"
            status_tag = f" `[{task.status}]`" if task.status != "pending" else ""
            lines.append(f"### {task.id}: {task.title}{effort_tag}{status_tag}")
            lines.append("")
            lines.append(task.description)
            lines.append("")
            if task.depends_on:
                lines.append(f"**Depends on:** {', '.join(task.depends_on)}")
                lines.append("")
            if task.risks:
                lines.append("**Risks:**")
                for r in task.risks:
                    lines.append(f"- [{r.severity}] {r.description}")
                    if r.mitigation:
                        lines.append(f"  - Mitigation: {r.mitigation}")
                lines.append("")

    return "\n".join(lines)


def save_task_graph(graph: TaskGraph, output_dir: str = "output/task_graph") -> tuple[str, str]:
    """Save task graph as both JSON and Markdown files."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    json_path = path / "task_graph.json"
    md_path = path / "task_graph.md"

    json_path.write_text(to_json(graph))
    md_path.write_text(to_markdown(graph))

    return str(json_path), str(md_path)
