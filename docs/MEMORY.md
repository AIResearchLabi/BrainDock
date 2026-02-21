# Memory

## Project: BrainDock
- Autonomous AI project creator — 8-mode gated pipeline
- Python 3.10+ stdlib only, LLM via `claude` CLI subprocess
- 261 tests, all passing — run with `python -m unittest discover -s tests -v`
- See [architecture.md](architecture.md) for full project reference
- See [../CLAUDE.md](../CLAUDE.md) for project-level instructions

## Key Architecture
- Pipeline: SPEC → TASK_GRAPH → PLAN → CONTROLLER → EXECUTE → SKILL_LEARN → REFLECT (on fail) → DEBATE (on uncertainty)
- Orchestrator at `BrainDock/orchestrator/agent.py` coordinates all modes
- Protocol-based LLM: ClaudeCLIBackend (prod), CallableBackend (test), LoggingBackend (monitoring)
- All state serialized as dicts in PipelineState, saved to pipeline_state.json for resume
- Human escalation via ask_fn when tasks stuck (auth, retries exhausted, token budget)
- Dashboard web UI at `BrainDock/dashboard/` with REST API

## Conventions
- Tests use unittest only (no pytest), CallableBackend with mock JSON responses
- Each agent module: agent.py, models.py, prompts.py, __init__.py
- Preambles in BrainDock/preambles/*.md — auto-reload on edit via mtime cache
- Output goes to output/<slug>/ with pipeline_state.json, spec, task_graph, project/
