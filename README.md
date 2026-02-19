# BrainDock

Autonomous Project Development Framework — a modular system with pluggable agents for end-to-end project development.

## Modules

### Spec Agent (`BrainDock.spec_agent`)

An interactive agent that takes a problem statement, autonomously decides routine technical questions, asks the user only critical/ambiguous ones, and produces a structured project specification (JSON + Markdown).

**Features:**
- LLM self-decides tech stack, architecture, data models — only escalates critical questions to the user
- Session persistence — resume after interrupts
- Per-project output folders with auto-resume on re-run
- Zero external dependencies — Python 3.10+ stdlib only, uses `claude -p` CLI as LLM backend
- Swappable LLM backend for testing or custom providers

### Coming Soon

- **Implementation Planner** — turns specs into actionable implementation plans
- **Skill Bank** — reusable skill/pattern library
- **Knowledge Bank** — project context and learnings
- **LLM Debater** — multi-perspective reasoning for design decisions

## Quick Start

```bash
# Run spec agent with a problem statement
python -m BrainDock.spec_agent "Build a todo app with authentication"

# Interactive mode
python -m BrainDock.spec_agent

# List all spec projects
python -m BrainDock.spec_agent --list

# Resume a specific project
python -m BrainDock.spec_agent --resume <project-slug>
```

### Library Usage

```python
from BrainDock.spec_agent import SpecAgent, ProjectSpec

agent = SpecAgent(problem="Build a todo app with auth")
spec = agent.run(ask_fn=my_question_handler)
# spec is a ProjectSpec dataclass
```

## Project Structure

```
BrainDock/                          # Main package
├── __init__.py
└── spec_agent/                     # Spec agent module
    ├── __init__.py
    ├── __main__.py                 # python -m BrainDock.spec_agent
    ├── agent.py                    # Core agent loop: analyze → ask → refine → generate
    ├── cli.py                      # Interactive terminal UI
    ├── llm.py                      # LLM backends (ClaudeCLI, Callable)
    ├── models.py                   # Data classes: ProjectSpec, Question, Decision, etc.
    ├── output.py                   # JSON + Markdown formatters
    └── prompts.py                  # LLM prompt templates
tests/                              # All module tests
└── spec_agent/
    └── test_agent.py               # 28 tests with mock LLM
output/                             # All module outputs (gitignored)
└── spec_agent/
    └── <project-slug>/             # Per-problem folders
        ├── session.json            # Active session (deleted on completion)
        ├── spec.json               # Structured JSON spec
        └── spec.md                 # Human-readable Markdown spec
```

## Running Tests

```bash
python -m unittest tests.spec_agent.test_agent -v
```

## Requirements

- Python 3.10+
- `claude` CLI (Claude Code) for the default LLM backend
- No pip dependencies required
