"""CLI entry point for the Task Graph module.

Usage:
    python -m BrainDock.task_graph <spec.json>
    python -m BrainDock.task_graph --help
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .agent import TaskGraphAgent
from .output import save_task_graph, to_markdown


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python -m BrainDock.task_graph <spec.json> [--output-dir DIR]")
        print()
        print("Decomposes a project specification into a task dependency graph.")
        sys.exit(0)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Error: Please provide a spec.json file path.")
        print("Usage: python -m BrainDock.task_graph <spec.json>")
        sys.exit(1)

    spec_path = args[0]
    spec = json.loads(Path(spec_path).read_text())

    output_dir = "output/task_graph"
    if "--output-dir" in sys.argv:
        idx = sys.argv.index("--output-dir")
        if idx + 1 < len(sys.argv):
            output_dir = sys.argv[idx + 1]

    print("Decomposing specification into task graph...")
    agent = TaskGraphAgent()
    graph = agent.decompose(spec)

    json_path, md_path = save_task_graph(graph, output_dir=output_dir)
    print(f"Task graph saved to: {json_path}")
    print(f"Markdown saved to: {md_path}")
    print()
    print(to_markdown(graph))


if __name__ == "__main__":
    main()
