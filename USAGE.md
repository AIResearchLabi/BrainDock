# BrainDock Usage Guide

BrainDock is an 8-mode autonomous pipeline that takes a problem statement and produces a working project. It plans, executes, verifies, reflects on errors, and learns reusable skills — all orchestrated through Claude.

## Requirements

- Python 3.10+
- `claude` CLI installed and authenticated (no API key needed)
- No pip dependencies — stdlib only

## Quick Start

### CLI (recommended for first run)

```bash
# Run with a problem statement
python -m BrainDock "Build a CLI calculator in Python"

# Give it a title for easy resume
python -m BrainDock --title "my-calc" "Build a CLI calculator in Python"
```

BrainDock will walk you through a short Q&A to clarify requirements, then plan and build the project automatically.

### Dashboard (visual monitoring)

```bash
# Start the web dashboard
python -m BrainDock.dashboard

# Custom port
python -m BrainDock.dashboard --port 8080
```

Open `http://localhost:3000` in your browser. Enter a title and problem statement, then click **Start Pipeline**. Answer any questions that appear in the UI.

## CLI Reference

```
python -m BrainDock [OPTIONS] [PROBLEM]
```

| Flag | Description |
|---|---|
| `PROBLEM` | Problem statement (positional). If omitted, you'll be prompted. |
| `--title TITLE` | Name for this run. Used for the output directory and resume. |
| `--resume TITLE` | Resume a previous run by its title. |
| `--list` | List all existing runs and their status. |
| `--plan-only` | Stop after planning — skip execution entirely. |
| `--no-skill-learning` | Skip skill extraction after successful tasks. |
| `--output-dir DIR` | Base output directory (default: `output`). |
| `--help`, `-h` | Show help. |

### Examples

```bash
# Start a new project
python -m BrainDock --title "todo-app" "Build a todo app with local storage"

# Resume after a crash or partial failure
python -m BrainDock --resume "todo-app"

# See all runs
python -m BrainDock --list

# Plan only (no code generation)
python -m BrainDock --plan-only "Design a REST API for a blog"
```

## How a Run Works

### Step 1 — Specification (interactive)

BrainDock analyzes your problem statement and may ask clarifying questions. In the CLI, you pick from numbered options or type a custom answer. In the dashboard, a question card appears.

The agent also makes autonomous decisions (e.g., choosing a language or framework) and shows them to you for awareness.

Once requirements are clear, it produces a detailed project specification.

### Step 2 — Task Graph

The specification is decomposed into a dependency graph of tasks. Tasks are grouped into waves that can theoretically run in parallel. Each task has an ID, title, description, dependencies, and effort estimate.

### Step 3 — Per-Task Pipeline

For each task (processed wave by wave):

1. **Planning** — The planner creates a step-by-step action plan with confidence and entropy scores. It sees all existing project files and prefers editing over rewriting.

2. **Controller Gate** — A deterministic check (no LLM call). If confidence is too low or entropy too high, it triggers a debate round.

3. **Debate** (if needed) — Multiple perspectives propose, critique, and synthesize an improved plan.

4. **Execution** — Each plan step is executed in a sandboxed `project/` directory. Supported actions: `write_file`, `edit_file`, `run_command`, `create_dir`, `test`. The executor sees existing project files and can read them before editing.

5. **Verification** — BrainDock automatically detects the project's entry point (`main.py`, `app.py`, `package.json` scripts, `run.sh`, or `Makefile`) and runs it. Output is checked for error patterns (Traceback, SyntaxError, ModuleNotFoundError, etc.). A server that stays alive past the timeout is treated as success.

6. **Reflection** (if execution or verification failed) — Root-cause analysis produces a modified plan. The retry loop runs up to `max_reflection_iterations` (default: 2) times, re-executing and re-verifying each attempt.

7. **Skill Learning** (if successful) — Reusable patterns are extracted and stored. Future tasks in the same run (and resumed runs) can reference these skills.

### Step 4 — Done

A summary is printed with completion stats. The generated project lives in `output/<slug>/project/`.

## Output Directory Structure

```
output/
  <project-slug>/
    pipeline_state.json       # Full pipeline state (used for resume + dashboard)
    spec_agent/
      spec.json               # Project specification
      spec.md                 # Human-readable spec
    task_graph/
      task_graph.json         # Task dependency graph
    project/                  # The generated project files
      main.py
      ...
    skill_bank/
      skills.json             # Learned reusable skills
```

The `pipeline_state.json` file is updated after every mode change. This is how:
- The dashboard polls for live updates
- `--resume` knows where to pick up
- `--list` reads completion status

## Dashboard Guide

### Starting the Dashboard

```bash
python -m BrainDock.dashboard
```

### Dashboard Tabs

**Project tab** — The main view:
- Start a new run or resume a previous one
- Answer specification questions when they appear
- Watch the 8-node pipeline visualization (active nodes pulse, completed nodes turn green)
- View task graph progress grouped by wave
- Inspect results: specs, plans, execution logs, reflections, debates, skills

**Agents tab** — Live activity feed showing every event from every agent with timestamps and color-coded badges.

**Chat tab** — Message log with system messages, questions, and answers. You can also type messages here.

### Dashboard API

| Endpoint | Method | Description |
|---|---|---|
| `/api/state` | GET | Current pipeline state |
| `/api/runs` | GET | List all runs |
| `/api/activities?since=N` | GET | Activity log (cursor-based) |
| `/api/chat?since=N` | GET | Chat messages (cursor-based) |
| `/api/start` | POST | Start new run (`{title, problem}`) |
| `/api/resume` | POST | Resume run (`{title}`) |
| `/api/answers` | POST | Submit spec answers (`{answers: {qid: answer}}`) |
| `/api/chat` | POST | Send chat message (`{message}`) |

## Running Individual Modules

Each pipeline stage can be run standalone for testing or debugging:

```bash
python -m BrainDock.spec_agent       # Interactive specification only
python -m BrainDock.task_graph       # Task decomposition only
python -m BrainDock.planner          # Planning only (reads task_graph.json)
python -m BrainDock.executor         # Execution only (reads plan.json)
```

## Configuration Defaults

| Setting | Default | Description |
|---|---|---|
| `output_dir` | `output` | Base output directory |
| `max_task_retries` | 2 | Max retries for failed tasks |
| `max_reflection_iterations` | 2 | Max reflect-retry loops per task |
| `max_debate_rounds` | 3 | Max debate rounds per uncertain plan |
| `min_confidence` | 0.6 | Plan confidence threshold |
| `max_entropy` | 0.7 | Plan entropy threshold (above triggers debate) |

These are set in `RunConfig` and can be adjusted programmatically when using BrainDock as a library.

## Using BrainDock as a Library

```python
from BrainDock.orchestrator import OrchestratorAgent, RunConfig

config = RunConfig(output_dir="my_output", max_reflection_iterations=3)
orchestrator = OrchestratorAgent(config=config)

def ask_fn(questions, decisions, understanding):
    # Return answers as {question_id: answer_text}
    return {}

state = orchestrator.run(
    problem="Build a markdown blog generator",
    ask_fn=ask_fn,
    title="blog-gen",
)

print(f"Completed: {state.completed_tasks}")
print(f"Failed: {state.failed_tasks}")
print(f"Skills learned: {len(state.learned_skills)}")
print(f"Verification results: {len(state.verification_results)}")
```

## Resuming a Run

Runs are automatically resumable. If BrainDock crashes, gets interrupted, or a task fails:

```bash
# Resume by title
python -m BrainDock --resume "my-project"

# Or from the dashboard: click "Resume" on a previous run
```

On resume:
- Completed modes (spec, task graph) are skipped
- Completed tasks are skipped
- Previously failed tasks are retried
- The skill bank persists across runs

## Troubleshooting

**"claude: command not found"** — Install the Claude CLI: `npm install -g @anthropic-ai/claude-code` or check your PATH.

**Pipeline stuck on specification** — The spec agent is waiting for answers. Check the terminal for numbered questions (CLI) or the question card (dashboard).

**Task keeps failing after reflection** — Check the verification errors in `pipeline_state.json` or the dashboard's Agents tab. The `verification_results` array shows exactly what command was run and what error was detected.

**Want to start fresh** — Delete the project's output directory (`output/<slug>/`) and run again.

## Running Tests

```bash
python -m unittest tests.orchestrator.test_orchestrator -v
```
