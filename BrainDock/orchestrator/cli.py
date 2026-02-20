"""CLI entry point for the full BrainDock pipeline.

Usage:
    python -m BrainDock "Build a todo app with auth"
    python -m BrainDock --help
    python -m BrainDock --plan-only "Build a todo app"
"""

from __future__ import annotations

import sys
import os

from BrainDock.spec_agent.models import Question, Decision
from .agent import OrchestratorAgent
from .models import RunConfig, Mode


# ANSI color helpers
def _c(code: int, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"

def _bold(text: str) -> str:
    return _c(1, text)

def _cyan(text: str) -> str:
    return _c(36, text)

def _green(text: str) -> str:
    return _c(32, text)

def _yellow(text: str) -> str:
    return _c(33, text)

def _dim(text: str) -> str:
    return _c(2, text)

def _magenta(text: str) -> str:
    return _c(35, text)

def _red(text: str) -> str:
    return _c(31, text)


MODE_LABELS = {
    Mode.SPECIFICATION.value: "Mode 1: Specification",
    Mode.TASK_GRAPH.value: "Mode 2: Task Graph",
    Mode.PLANNING.value: "Mode 3: Planning",
    Mode.CONTROLLER.value: "Mode 4: Controller",
    Mode.EXECUTION.value: "Mode 5: Execution",
    Mode.SKILL_LEARNING.value: "Mode 6: Skill Learning",
    Mode.REFLECTION.value: "Mode 7: Reflection",
    Mode.DEBATE.value: "Mode 8: Debate",
}


def _print_header():
    print()
    print(_bold("=" * 60))
    print(_bold("  BRAINDOCK — Autonomous AI Project Creator"))
    print(_bold("=" * 60))
    print()
    print(_dim("  8-Mode Gated Pipeline:"))
    print(_dim("  SPEC -> TASK_GRAPH -> PLAN -> GATE -> EXECUTE -> LEARN"))
    print(_dim("                                  |-> REFLECT (on failure)"))
    print(_dim("                                  |-> DEBATE  (on uncertainty)"))
    print()


def _ask_user(
    questions: list[Question],
    decisions: list[Decision],
    understanding: str,
) -> dict[str, str]:
    """Interactive CLI callback for spec_agent questions."""
    print()
    print(_cyan(f"  Understanding: {understanding}"))
    print()

    if decisions:
        print(_magenta("  Decisions I made:"))
        print(_dim("  " + "-" * 50))
        for d in decisions:
            print(f"    {_bold(d.topic)}")
            print(f"    {_dim('->')} {d.decision}")
            print()

    if not questions:
        print(_green("  No critical questions — proceeding."))
        print()
        return {}

    print(_yellow(f"  {len(questions)} question(s) need your input:"))
    print(_dim("  " + "-" * 50))

    answers = {}
    for i, q in enumerate(questions, 1):
        print()
        print(_bold(f"  Q{i}. {q.question}"))
        print(_dim(f"      Why: {q.why}"))

        if q.options:
            print()
            for j, opt in enumerate(q.options, 1):
                print(f"      {_yellow(str(j))}. {opt}")
            print(f"      {_yellow('0')}. Custom answer")
            print()

            while True:
                choice = input(_green("      Your choice: ")).strip()
                if not choice:
                    print("      Please provide an answer.")
                    continue
                try:
                    idx = int(choice)
                    if idx == 0:
                        answer = input(_green("      Your answer: ")).strip()
                        if answer:
                            break
                        print("      Please provide an answer.")
                    elif 1 <= idx <= len(q.options):
                        answer = q.options[idx - 1]
                        break
                    else:
                        print(f"      Please enter 0-{len(q.options)}")
                except ValueError:
                    answer = choice
                    break
        else:
            print()
            answer = ""
            while not answer:
                answer = input(_green("      Your answer: ")).strip()
                if not answer:
                    print("      Please provide an answer.")

        answers[q.id] = answer
        print(_dim(f"      -> {answer}"))

    return answers


def _print_help():
    print("Usage: python -m BrainDock [OPTIONS] [PROBLEM]")
    print()
    print("Arguments:")
    print("  PROBLEM              Problem statement (or interactive if omitted)")
    print()
    print("Options:")
    print("  --help, -h           Show this help message")
    print("  --plan-only          Stop after planning (skip execution)")
    print("  --no-skill-learning  Skip skill extraction")
    print("  --output-dir DIR     Output directory (default: output)")
    print()
    print("Examples:")
    print('  python -m BrainDock "Build a todo app with authentication"')
    print("  python -m BrainDock --plan-only")
    print()
    print("Individual modules:")
    print("  python -m BrainDock.spec_agent  -- Specification only")
    print("  python -m BrainDock.task_graph  -- Task decomposition only")
    print("  python -m BrainDock.planner     -- Planning only")
    print("  python -m BrainDock.executor    -- Execution only")
    print()
    print("Dashboard:")
    print("  python -m BrainDock.dashboard          -- Live pipeline dashboard")
    print("  python -m BrainDock.dashboard --port N  -- Custom port (default: 8080)")


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        _print_header()
        _print_help()
        sys.exit(0)

    _print_header()

    # Parse config from CLI flags
    config = RunConfig()

    if "--plan-only" in sys.argv:
        config.skip_execution = True

    if "--no-skill-learning" in sys.argv:
        config.skip_skill_learning = True

    if "--output-dir" in sys.argv:
        idx = sys.argv.index("--output-dir")
        if idx + 1 < len(sys.argv):
            config.output_dir = sys.argv[idx + 1]

    # Get problem statement
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # Filter out values of --output-dir
    if "--output-dir" in sys.argv:
        idx = sys.argv.index("--output-dir")
        if idx + 1 < len(sys.argv):
            val = sys.argv[idx + 1]
            args = [a for a in args if a != val]

    if args:
        problem = " ".join(args)
    else:
        print("  Describe your project idea or problem statement.")
        print(_dim("  (Be as detailed or brief as you'd like)"))
        print()
        problem = input(_green("  > ")).strip()
        if not problem:
            print("  No problem statement provided. Exiting.")
            sys.exit(1)

    print(f"  Problem: {_bold(problem)}")
    print()

    # Run the pipeline
    orchestrator = OrchestratorAgent(config=config)

    print(_dim("  Starting pipeline..."))
    print()

    state = orchestrator.run(problem=problem, ask_fn=_ask_user)

    # Summary
    print()
    print(_bold("=" * 60))
    print(_green("  Pipeline Complete!"))
    print(_bold("=" * 60))
    print()
    print(f"  Spec: {_cyan(state.spec.get('title', 'N/A'))}")
    print(f"  Tasks: {len(state.task_graph.get('tasks', []))}")
    print(f"  Plans: {len(state.plans)}")
    print(f"  Completed: {_green(str(len(state.completed_tasks)))}")
    print(f"  Failed: {_red(str(len(state.failed_tasks))) if state.failed_tasks else '0'}")
    print(f"  Skills learned: {len(state.learned_skills)}")
    print(f"  Reflections: {len(state.reflections)}")
    print(f"  Debates: {len(state.debates)}")
    print()
    print(f"  Output: {_cyan(config.output_dir)}/")
    print()


if __name__ == "__main__":
    main()
