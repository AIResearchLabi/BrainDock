"""CLI entry point for the Planner module.

Usage:
    python -m BrainDock.planner <task_graph.json> [--task TASK_ID]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .agent import PlannerAgent
from .output import save_plan, to_markdown


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python -m BrainDock.planner <task_graph.json> [--task TASK_ID]")
        print()
        print("Creates action plans for tasks in a task graph.")
        sys.exit(0)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Error: Please provide a task_graph.json file path.")
        sys.exit(1)

    graph_data = json.loads(Path(args[0]).read_text())

    task_id = None
    if "--task" in sys.argv:
        idx = sys.argv.index("--task")
        if idx + 1 < len(sys.argv):
            task_id = sys.argv[idx + 1]

    agent = PlannerAgent()
    context = f"Project: {graph_data.get('project_title', 'Unknown')}"

    tasks = graph_data.get("tasks", [])
    if task_id:
        tasks = [t for t in tasks if t["id"] == task_id]
        if not tasks:
            print(f"Error: Task '{task_id}' not found.")
            sys.exit(1)

    for task in tasks:
        print(f"Planning task: {task['id']} — {task['title']}...")
        plan = agent.plan_task(task, context=context)
        save_plan(plan)
        print(to_markdown(plan))
        print()


if __name__ == "__main__":
    main()
