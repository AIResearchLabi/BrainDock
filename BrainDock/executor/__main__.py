"""CLI entry point for the Executor module.

Usage:
    python -m BrainDock.executor <plan.json> [--project-dir DIR]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .agent import ExecutorAgent


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python -m BrainDock.executor <plan.json> [--project-dir DIR]")
        print()
        print("Executes an action plan step by step.")
        sys.exit(0)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Error: Please provide a plan JSON file path.")
        sys.exit(1)

    plan = json.loads(Path(args[0]).read_text())

    project_dir = "."
    if "--project-dir" in sys.argv:
        idx = sys.argv.index("--project-dir")
        if idx + 1 < len(sys.argv):
            project_dir = sys.argv[idx + 1]

    print(f"Executing plan for task: {plan.get('task_id', 'unknown')}...")
    agent = ExecutorAgent()
    result = agent.execute(plan, project_dir=project_dir)

    print(f"Success: {result.success}")
    print(f"Steps completed: {result.steps_completed}/{result.steps_total}")
    if result.stop_reason:
        print(f"Stop reason: {result.stop_reason}")

    for o in result.outcomes:
        status = "OK" if o.success else "FAIL"
        print(f"  [{status}] {o.step_id}: {o.output[:100]}")


if __name__ == "__main__":
    main()
