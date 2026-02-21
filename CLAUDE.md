# CLAUDE.md — BrainDock Project Instructions

## What is this project?
BrainDock is an autonomous AI project creator — an 8-mode gated pipeline that takes a problem statement and produces complete projects through specification, planning, execution, and learning. Uses Claude via `claude` CLI (no API key).

## Quick Commands
```bash
# Run all tests (261 tests, must all pass)
python -m unittest discover -s tests -v

# Run tests for a specific module
python -m unittest tests.<module>.test_<module> -v

# Start the dashboard
python -m BrainDock.dashboard --port 3000

# Run pipeline from CLI
python -m BrainDock "Build a todo app"
```

## Architecture
**8-mode pipeline**: SPEC → TASK_GRAPH → PLAN → CONTROLLER → EXECUTE → SKILL_LEARN → REFLECT (on failure) → DEBATE (on uncertainty)

- **Orchestrator** (`BrainDock/orchestrator/agent.py`): Main loop coordinating all modes
- **Models** (`BrainDock/orchestrator/models.py`): `Mode` enum, `RunConfig`, `PipelineState`
- **LLM** (`BrainDock/llm.py`): Protocol-based — `ClaudeCLIBackend` (prod), `CallableBackend` (test), `LoggingBackend` (monitoring)
- **Controller** (`BrainDock/controller/`): Deterministic quality gates, no LLM calls
- **Dashboard** (`BrainDock/dashboard/`): Web UI with REST API at `/api/*`

## Module Structure
Each agent module follows: `agent.py`, `models.py`, `prompts.py`, `__init__.py`
Modules: spec_agent, task_graph, planner, controller, executor, skill_bank, reflection, debate, market_study

## Code Conventions
- **Python 3.10+ stdlib only** — no pip dependencies
- **Tests**: unittest only (no pytest), `CallableBackend` with mock JSON responses
- **Serialization**: All models use `to_dict()`/`from_dict()` with `dataclasses.asdict`
- **State**: Orchestrator stores dicts (not objects) in `PipelineState` for JSON serialization
- **Preambles**: Edit `BrainDock/preambles/*.md` to customize agent prompts (auto-reload)

## Key Thresholds (RunConfig)
- `min_confidence`: 0.6 — below triggers reflection
- `max_entropy`: 0.7 — above triggers debate
- `max_reflection_iterations`: 2 — retries per task
- `max_debate_rounds`: 3 — debate convergence limit
- `escalation_token_budget`: 50000 — per-task token limit before human escalation

## Human Escalation
Three triggers pause pipeline and ask human via `ask_fn`:
1. Reflection detects `needs_human` (auth, credentials, external setup)
2. All reflection retries exhausted
3. Token budget exceeded

Human options: **skip** (mark failed), **retry with hint**, **abort pipeline**

## Testing Requirements
- All 261 tests must pass before any change goes to production
- New features must include tests in `tests/<module>/test_<module>.py`
- Use `CallableBackend` for mock LLM responses in tests

## Output
Generated projects go to `output/<slug>/` with `pipeline_state.json` for resume support.
