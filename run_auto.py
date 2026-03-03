"""Non-interactive runner that auto-selects option 1 for all questions."""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from BrainDock.spec_agent.models import Question, Decision
from BrainDock.orchestrator.agent import OrchestratorAgent
from BrainDock.orchestrator.models import RunConfig


def auto_ask_fn(
    questions: list[Question],
    decisions: list[Decision],
    understanding: str,
) -> dict[str, str]:
    """Auto-select option 1 (easiest) for every question."""
    print(f"\n  [AUTO] Understanding: {understanding}\n")

    if decisions:
        print("  [AUTO] Decisions made:")
        for d in decisions:
            print(f"    {d.topic} -> {d.decision}")
        print()

    if not questions:
        print("  [AUTO] No questions — proceeding.\n")
        return {}

    answers = {}
    for i, q in enumerate(questions, 1):
        if q.options:
            answer = q.options[0]  # Always pick first option (easiest)
        else:
            answer = "Yes, proceed with the default approach."
        answers[q.id] = answer
        print(f"  [AUTO] Q{i}: {q.question}")
        print(f"         -> {answer}")
    print()
    return answers


def main():
    title = sys.argv[1] if len(sys.argv) > 1 else "idea-market-survey"
    problem = sys.argv[2] if len(sys.argv) > 2 else (
        "create ability to send whatsapp and linkedin messages by using headed browser "
        "logged in account for idea market survey. create a list of potential contact on "
        "both and confirm with human before sending actual communication"
    )

    config = RunConfig()
    orchestrator = OrchestratorAgent(config=config)

    print(f"\n  Running: {title}")
    print(f"  Problem: {problem}\n")

    state = orchestrator.run(problem=problem, ask_fn=auto_ask_fn, title=title)

    print(f"\n  Done! Completed: {len(state.completed_tasks)}, Failed: {len(state.failed_tasks)}")
    print(f"  Output: output/{state.title}/\n")


if __name__ == "__main__":
    main()
