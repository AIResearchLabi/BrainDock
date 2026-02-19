"""CLI entry point for the Spec Agent.

Usage:
    python -m BrainDock.spec_agent "Your problem statement here"
    python -m BrainDock.spec_agent  # interactive prompt
    python -m BrainDock.spec_agent --list          # list all spec projects
    python -m BrainDock.spec_agent --resume <slug> # resume a specific project
"""

from __future__ import annotations

import re
import sys
import os
from pathlib import Path

from .models import Question, Decision
from .agent import SpecAgent
from .output import save_spec, to_markdown


BASE_OUTPUT_DIR = os.path.join("output", "spec_agent")


def _slugify(text: str, max_len: int = 60) -> str:
    """Turn a problem statement into a filesystem-safe folder name."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)        # remove non-word chars
    text = re.sub(r"[\s_]+", "-", text)          # spaces/underscores → hyphens
    text = re.sub(r"-{2,}", "-", text)           # collapse multiple hyphens
    text = text.strip("-")
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0]  # cut at word boundary
    return text or "project"


def _find_existing_sessions(base_dir: str = BASE_OUTPUT_DIR) -> list[dict]:
    """Scan spec_output/ for project folders with active sessions."""
    base = Path(base_dir)
    if not base.exists():
        return []
    sessions = []
    for folder in sorted(base.iterdir()):
        session_file = folder / "session.json"
        if folder.is_dir() and session_file.exists():
            agent = SpecAgent.load_session(session_file=str(session_file))
            if agent:
                sessions.append({
                    "slug": folder.name,
                    "path": str(folder),
                    "session_file": str(session_file),
                    "problem": agent.problem,
                    "round": agent._round,
                    "answers": sum(1 for e in agent.conversation if e["role"] == "answers"),
                })
    return sessions


def _find_project_dir(problem: str, base_dir: str = BASE_OUTPUT_DIR) -> str:
    """Get or create a project directory for the given problem.

    If a folder already exists with a matching slug, reuse it.
    """
    slug = _slugify(problem)
    project_dir = os.path.join(base_dir, slug)
    os.makedirs(project_dir, exist_ok=True)
    return project_dir


# ANSI color helpers (no external deps)
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


def _print_header():
    print()
    print(_bold("=" * 60))
    print(_bold("  SPEC AGENT — Interactive Project Specification Builder"))
    print(_bold("=" * 60))
    print()


def _ask_user(
    questions: list[Question],
    decisions: list[Decision],
    understanding: str,
) -> dict[str, str]:
    """Interactive CLI callback.

    Displays the LLM's autonomous decisions, then asks only
    the critical questions that need user input.
    """
    print()
    print(_cyan(f"  Understanding: {understanding}"))
    print()

    # Show what the agent decided on its own
    if decisions:
        print(_magenta(f"  Decisions I made (you can override in your answers):"))
        print(_dim("  " + "-" * 50))
        for d in decisions:
            print(f"    {_bold(d.topic)}")
            print(f"    {_dim('->')} {d.decision}")
            print()

    # If no questions, just return
    if not questions:
        print(_green("  No critical questions — I have enough to proceed."))
        print()
        return {}

    # Ask critical questions
    print(_yellow(f"  {len(questions)} critical question(s) that need your input:"))
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
                choice = input(_green("      Your choice (number or type answer): ")).strip()
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
                    # They typed a free-form answer
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


def main():
    _print_header()

    base_dir = os.environ.get("SPEC_OUTPUT_DIR", BASE_OUTPUT_DIR)
    agent = None
    project_dir = None

    # Handle --list flag
    if "--list" in sys.argv:
        sessions = _find_existing_sessions(base_dir)
        completed = []
        base = Path(base_dir)
        if base.exists():
            for folder in sorted(base.iterdir()):
                if folder.is_dir() and (folder / "spec.json").exists():
                    # Check if it has an active session (in-progress) or is done
                    has_session = (folder / "session.json").exists()
                    if not has_session:
                        completed.append(folder.name)

        if not sessions and not completed:
            print("  No spec projects found.")
        else:
            if sessions:
                print(_yellow("  In-progress (resumable):"))
                for s in sessions:
                    print(f"    {_bold(s['slug'])}")
                    print(f"      {_dim(s['problem'][:80])}")
                    print(f"      Round {s['round']}, {s['answers']} answer(s)")
                    print()
            if completed:
                print(_green("  Completed:"))
                for slug in completed:
                    print(f"    {_bold(slug)}")
                print()
        sys.exit(0)

    # Handle --resume <slug> flag
    if "--resume" in sys.argv:
        idx = sys.argv.index("--resume")
        if idx + 1 >= len(sys.argv):
            print("  Usage: python -m BrainDock.spec_agent --resume <project-slug>")
            sys.exit(1)
        slug = sys.argv[idx + 1]
        session_file = os.path.join(base_dir, slug, "session.json")
        agent = SpecAgent.load_session(session_file=session_file)
        if agent is None:
            print(f"  No active session found for '{slug}'.")
            sys.exit(1)
        project_dir = os.path.join(base_dir, slug)
        print(f"  Resuming: {_bold(agent.problem)}")
        print()

    # Auto-detect: check if problem matches an existing project with a session
    if agent is None:
        # Get problem statement
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        if args:
            problem = " ".join(args)
        else:
            print("  Describe your project idea or problem statement.")
            print(_dim("  (Be as detailed or brief as you'd like — I'll ask follow-ups)"))
            print()
            problem = input(_green("  > ")).strip()
            if not problem:
                print("  No problem statement provided. Exiting.")
                sys.exit(1)

        # Derive project folder from problem
        project_dir = _find_project_dir(problem, base_dir)
        session_file = os.path.join(project_dir, "session.json")

        # Check for existing session in this project's folder
        existing = SpecAgent.load_session(session_file=session_file)
        if existing is not None:
            print(_yellow("  Found an interrupted session for this project!"))
            print(f"  Folder: {_cyan(project_dir)}")
            print(f"  Round: {existing._round}, "
                  f"Q&A so far: {sum(1 for e in existing.conversation if e['role'] == 'answers')}")
            print()
            choice = input(_green("  Resume? [Y/n/discard]: ")).strip().lower()
            if choice in ("", "y", "yes"):
                agent = existing
                print()
                print(_dim("  Resuming session..."))
                print()
            elif choice in ("discard", "d"):
                existing._clear_session()
                print(_dim("  Session discarded. Starting fresh."))
                print()
            else:
                print(_dim("  Starting fresh (previous session kept on disk)."))
                print()

        if agent is None:
            print(f"  Problem: {_bold(problem)}")
            print(f"  Project: {_cyan(project_dir)}")
            print()
            print(_dim("  Analyzing your problem statement..."))
            print()
            agent = SpecAgent(problem=problem, session_file=session_file)

    spec = agent.run(ask_fn=_ask_user)

    # Save outputs into the project folder
    json_path, md_path = save_spec(spec, output_dir=project_dir)

    print()
    print(_bold("=" * 60))
    print(_green("  Specification generated successfully!"))
    print(_bold("=" * 60))
    print()
    print(f"  JSON: {_cyan(json_path)}")
    print(f"  Markdown: {_cyan(md_path)}")
    print()

    # Also print the markdown to stdout
    print(_dim("-" * 60))
    print(to_markdown(spec))


if __name__ == "__main__":
    main()
